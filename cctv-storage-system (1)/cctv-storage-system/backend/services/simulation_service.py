"""Simulation clock + CCTV footage-metadata generator. Lets a demo 'pass time' in seconds."""
import random
from datetime import datetime, timedelta

from backend.auth import rbac
from database import connection as db
from backend.engines import retention_engine as rt
from backend.services import audit_service, camera_service, settings_service as ss, storage_service


def _generate(cams, policy, tier_ids, start, seg_h, rng):
    end = start + timedelta(hours=seg_h)
    rows = []
    for c in cams:
        mf = 0.35 if c["recording_mode"] == "Motion" else 1.0
        noise = rng.uniform(0.5, 1.6) if c["recording_mode"] == "Motion" else rng.uniform(0.9, 1.1)
        mfac = ss.mode_factors()[c["recording_mode"]]
        size = c["bitrate_mbps"] * 0.45 * seg_h * (c["recording_hours"] / 24) * mfac * noise
        tid = c["default_tier_id"] or tier_ids["Hot"]
        rows.append((c["camera_id"], start, end, round(size, 3), c["resolution"], c["compression"], tid, "Normal",
                     rt.expiry(end, "Normal", c["retention_days"], policy), "Archived" if tid == tier_ids["Cold"] else "Active"))
    return rows


def advance(user, hours, auto_lifecycle=True, auto_purge=True):
    """Move the simulation clock forward, generating footage as time passes."""
    rbac.check(user, "simulate")
    s = ss.get_all()
    clock = ss.get_clock()
    target = clock + timedelta(hours=hours)
    seg_h = 24 / int(s["segments_per_day"])
    gen = datetime.fromisoformat(s["generated_until"]) if s["generated_until"] else clock
    cams = camera_service.list_cameras(active_only=True)
    if not cams:
        raise ValueError("Add cameras first (Cameras page or Settings > Simulation > Load demo).")
    policy = ss.get_policy()
    tier_ids = {t["name"]: t["tier_id"] for t in storage_service.pool_state()["tiers"]}
    rng = random.Random()
    total = {"to_warm": 0, "to_cold": 0, "marked": 0}
    purged = 0
    cur = clock
    while cur < target:
        nxt = min(cur + timedelta(hours=24), target)
        rows = []
        while gen + timedelta(hours=seg_h) <= nxt:
            rows += _generate(cams, policy, tier_ids, gen, seg_h, rng)
            gen += timedelta(hours=seg_h)
        db.execute_values("INSERT INTO footage (camera_id,start_time,end_time,size_gb,resolution,compression,tier_id,"
                          "importance,retention_expiry,archive_status) VALUES %s", rows)
        ss.set_raw("sim_clock", nxt.isoformat())
        if auto_lifecycle:
            r = storage_service.run_lifecycle(user, apply=True, now=nxt, quiet=True, sync_alerts=False)
            for k in total:
                total[k] += r["counts"][k]
        if auto_purge:
            purged += storage_service.purge_marked(user, now=nxt, quiet=True)[0]
        storage_service.snapshot_metrics(nxt)
        cur = nxt
    ss.set_raw("generated_until", gen.isoformat())
    audit_service.log(user, "SIM_ADVANCED", f"Clock +{hours:g} h -> {target:%Y-%m-%d %H:%M}; lifecycle={'on' if auto_lifecycle else 'off'}; "
                      f"to Warm {total['to_warm']}, archived {total['to_cold']}, marked {total['marked']}, purged {purged}")
    if total["to_cold"]:
        audit_service.log(user, "FOOTAGE_ARCHIVED", f"{total['to_cold']} clip(s) archived to Cold during simulation")
    if purged:
        audit_service.log(user, "FOOTAGE_DELETED", f"{purged} expired clip(s) deleted during simulation")
    from backend.services import alert_service
    alert_service.sync(target)
    return total, purged


def reset(user, remove_cameras=False):
    rbac.check(user, "simulate")
    db.execute("TRUNCATE lifecycle_decisions, incidents, footage, storage_metrics, backups, alerts RESTART IDENTITY CASCADE")
    if remove_cameras:
        db.execute("DELETE FROM cameras")
    db.execute("UPDATE raid_configurations SET failed_disks=0, status='Healthy'")
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ss.set_raw("sim_clock", start.isoformat())
    ss.set_raw("generated_until", start.isoformat())
    audit_service.log(user, "SIM_RESET", f"Simulation data reset (cameras removed: {remove_cameras})")


def generate_history(user, days):
    """Rewind the clock `days` into the past and create that much footage. Lifecycle OFF so everything is Hot."""
    rbac.check(user, "simulate")
    reset(user, remove_cameras=False)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    ss.set_raw("sim_clock", start.isoformat())
    ss.set_raw("generated_until", start.isoformat())
    return advance(user, days * 24, auto_lifecycle=False, auto_purge=False)
