"""Simulated backup / recovery and RPO-RTO evaluation."""
from datetime import timedelta

from backend.auth import rbac
from database import connection as db
from backend.engines import backup_engine as be
from backend.services import audit_service, settings_service as ss, storage_service


def list_backups(limit=100):
    return db.fetch_df("SELECT backup_id, backup_type, started_at, finished_at, size_gb, destination, status, recovery_status "
                       "FROM backups ORDER BY started_at DESC, backup_id DESC LIMIT %s", (limit,))


def _all():
    return db.fetch_all("SELECT * FROM backups ORDER BY started_at, backup_id")


def status(now=None):
    s = ss.get_all()
    now = now or ss.get_clock()
    return be.evaluate(_all(), now, float(s["rpo_hours"]), float(s["rto_hours"]), float(s["restore_speed_gb_per_hr"]),
                       float(s["restore_overhead_hours"]), float(s["backup_frequency_hours"]))


def run_backup(user, btype, fail=False):
    rbac.check(user, "run_backup")
    s = ss.get_all()
    now = ss.get_clock()
    st = storage_service.pool_state()
    pool_id = st["pool"]["pool_id"]
    tiers = {t["name"]: t["used_gb"] for t in st["tiers"]}
    last_ok = [b for b in _all() if b["status"] == "Success"]
    if btype == "Full":
        size = be.full_backup_size(tiers["Hot"], tiers["Warm"])
    else:
        if not any(b["backup_type"] == "Full" for b in last_ok):
            raise ValueError("Run a Full backup first - an incremental needs a base to build on.")
        since = max(b["started_at"] for b in last_ok)
        size = db.fetch_one("SELECT COALESCE(SUM(f.size_gb),0) AS gb FROM footage f JOIN storage_tiers t USING(tier_id) "
                            "WHERE f.end_time > %s AND f.deletion_status<>'Deleted' AND t.tier_name<>'Cold'", (since,))["gb"]
    dur = be.duration_hours(size, float(s["backup_speed_gb_per_hr"]))
    ok = not fail
    db.execute("INSERT INTO backups (pool_id,backup_type,started_at,finished_at,size_gb,destination,status) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s)",
               (pool_id, btype, now, now + timedelta(hours=dur), size if ok else 0, s["backup_destination"],
                "Success" if ok else "Failed"))
    audit_service.log(user, "BACKUP_INITIATED" if ok else "BACKUP_FAILED_SIMULATED",
                      f"{btype} backup {'completed' if ok else 'FAILED (simulated)'}: {size:,.1f} GB in {dur:.2f} h "
                      f"-> {s['backup_destination']}")
    from backend.services import alert_service
    alert_service.sync(now)
    return size, dur, ok


def run_recovery(user):
    """Simulate restoring the newest restorable chain and compare the estimated time with the RTO."""
    rbac.check(user, "run_backup")
    st = status()
    if not st["chain"]:
        raise ValueError("No restorable backup chain exists - run a successful Full backup first.")
    rto, ok = st["est_rto_hours"], st["rto_ok"]
    label = f"Recovered OK in ~{rto:.1f} h (RTO {'met' if ok else 'MISSED'})"
    ids = [b["backup_id"] for b in st["chain"]]
    db.execute("UPDATE backups SET recovery_status=%s WHERE backup_id = ANY(%s)", (label, ids))
    audit_service.log(user, "RECOVERY_SIMULATED", f"Restored {len(ids)} backup(s), {st['restore_gb']:,.0f} GB; {label}")
    return st
