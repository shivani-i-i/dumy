"""Pool/tier state, the lifecycle run (dry-run or apply), purge, compression simulation, metrics."""
import pandas as pd

from backend.auth import rbac
from backend.config.constants import TIERS
from database import connection as db
from backend.engines import compression_engine as comp
from backend.engines import lifecycle_engine as le
from backend.services import audit_service, settings_service as ss

PROT_SQL = "('Incident','Critical Evidence')"


def get_pool():
    return db.fetch_one("SELECT * FROM storage_pools ORDER BY pool_id LIMIT 1")


def lifecycle_config(s=None):
    s = s or ss.get_all()
    return le.LifecycleConfig(
        hot_window=float(s["hot_window_days"]), warm_window=float(s["warm_window_days"]),
        priority_mult={"Low": float(s["priority_mult_low"]), "Medium": float(s["priority_mult_medium"]),
                       "High": float(s["priority_mult_high"]), "Critical": float(s["priority_mult_critical"])},
        pressure_l1=float(s["pressure_l1"]), pressure_l2=float(s["pressure_l2"]), shrink=float(s["pressure_shrink"]))


def pool_state():
    pool = get_pool()
    rows = db.fetch_all(
        "SELECT t.tier_id, t.tier_name AS name, t.capacity_tb, t.cost_per_tb_month, t.access_speed, "
        "COALESCE(SUM(f.size_gb) FILTER (WHERE f.deletion_status<>'Deleted'),0) AS used_gb, "
        "COUNT(f.footage_id) FILTER (WHERE f.deletion_status<>'Deleted') AS clips "
        "FROM storage_tiers t LEFT JOIN footage f ON f.tier_id=t.tier_id WHERE t.pool_id=%s GROUP BY t.tier_id", (pool["pool_id"],))
    rows.sort(key=lambda r: TIERS.index(r["name"]))
    for r in rows:
        r["util"] = r["used_gb"] / (r["capacity_tb"] * 1000) * 100
    used = sum(r["used_gb"] for r in rows)
    cap = pool["total_capacity_tb"] * 1000
    extra = db.fetch_one(
        "SELECT COUNT(*) FILTER (WHERE deletion_status='Deleted') AS del_clips, "
        "COALESCE(SUM(size_gb) FILTER (WHERE deletion_status='Deleted'),0) AS del_gb, "
        "COUNT(*) FILTER (WHERE deletion_status='Marked') AS marked_clips, "
        "COALESCE(SUM(size_gb) FILTER (WHERE deletion_status='Marked'),0) AS marked_gb, "
        "COUNT(*) FILTER (WHERE archive_status='Archived' AND deletion_status<>'Deleted') AS arch_clips, "
        "COALESCE(SUM(size_gb) FILTER (WHERE archive_status='Archived' AND deletion_status<>'Deleted'),0) AS arch_gb "
        "FROM footage")
    cost = sum(r["used_gb"] / 1000 * r["cost_per_tb_month"] for r in rows)
    hot_cost = rows[0]["cost_per_tb_month"] if rows else 0
    return {"pool": pool, "tiers": rows, "used_gb": used, "capacity_gb": cap, "free_gb": cap - used,
            "util_pct": used / cap * 100 if cap else 0, "monthly_cost": cost,
            "all_hot_cost": used / 1000 * hot_cost, **extra}


def retention_counts(now):
    r = db.fetch_one(
        f"SELECT COUNT(*) FILTER (WHERE f.importance NOT IN {PROT_SQL} AND NOT COALESCE(i.legal_hold,false) "
        f"AND f.deletion_status='Retained' AND f.retention_expiry<=%s) AS violations, "
        f"COUNT(*) FILTER (WHERE f.importance IN {PROT_SQL} AND f.retention_expiry<=%s) AS protected_review "
        f"FROM footage f LEFT JOIN incidents i ON i.footage_id=f.footage_id WHERE f.deletion_status<>'Deleted'", (now, now))
    return r["violations"], r["protected_review"]


def _load_footage(ids=None):
    sql = ("SELECT f.footage_id, f.start_time, f.end_time, f.size_gb, f.importance, f.retention_expiry, f.deletion_status, "
           "t.tier_name AS tier, c.camera_code, c.name AS camera_name, c.priority, COALESCE(i.legal_hold,false) AS legal_hold "
           "FROM footage f JOIN cameras c USING(camera_id) JOIN storage_tiers t ON t.tier_id=f.tier_id "
           "LEFT JOIN incidents i ON i.footage_id=f.footage_id WHERE f.deletion_status<>'Deleted'")
    p = []
    if ids:
        sql += " AND f.footage_id = ANY(%s)"
        p.append(list(ids))
    return db.fetch_all(sql, p or None)


def run_lifecycle(user, apply=False, now=None, util_override=None, ids=None, quiet=False, sync_alerts=True):
    """Evaluate every footage record. apply=False is a DRY RUN (nothing is changed)."""
    rbac.check(user, "run_lifecycle")
    now = now or ss.get_clock()
    cfg = lifecycle_config()
    st = pool_state()
    util = util_override if util_override is not None else st["util_pct"]
    footage = _load_footage(ids)
    by_id = {f["footage_id"]: f for f in footage}
    decisions = le.run(footage, now, cfg, util)
    counts = {"to_warm": 0, "to_cold": 0, "marked": 0, "unmarked": 0, "restored": 0}
    for d in decisions:
        if d.action == "mark_delete":
            counts["marked"] += 1
        elif d.action == "unmark":
            counts["unmarked"] += 1
        elif d.from_tier == "Cold":
            counts["restored"] += 1
        elif d.to_tier == "Warm":
            counts["to_warm"] += 1
        elif d.to_tier == "Cold":
            counts["to_cold"] += 1
    if apply and decisions:
        tid = {t["name"]: t["tier_id"] for t in st["tiers"]}
        db.execute_values(
            "UPDATE footage f SET tier_id=v.tier_id, archive_status=v.arch, deletion_status=v.dst "
            "FROM (VALUES %s) AS v(id,tier_id,arch,dst) WHERE f.footage_id=v.id",
            [(d.footage_id, tid[d.to_tier], "Archived" if d.to_tier == "Cold" else "Active", d.deletion_status)
             for d in decisions], template="(%s::bigint,%s::int,%s::text,%s::text)")
        db.execute_values(
            "INSERT INTO lifecycle_decisions (footage_id,decided_at,from_tier,to_tier,action,reason_text) VALUES %s",
            [(d.footage_id, now, d.from_tier, d.to_tier, d.action, d.reason) for d in decisions])
        if not quiet:
            if counts["to_warm"]:
                audit_service.log(user, "FOOTAGE_TIERED", f"{counts['to_warm']} clip(s) moved Hot -> Warm")
            if counts["to_cold"]:
                audit_service.log(user, "FOOTAGE_ARCHIVED", f"{counts['to_cold']} clip(s) archived to Cold")
            if counts["marked"]:
                audit_service.log(user, "FOOTAGE_MARKED_DELETE", f"{counts['marked']} expired clip(s) marked for deletion")
    if apply and not quiet:
        audit_service.log(user, "LIFECYCLE_RUN", f"Applied {len(decisions)} decision(s); pool utilization {util:.1f}%")
    if apply and sync_alerts:
        from backend.services import alert_service
        alert_service.sync(now)
    rows = [{"Footage": le.fid(d.footage_id), "Camera": by_id[d.footage_id]["camera_code"],
             "Action": d.action, "From": d.from_tier, "To": d.to_tier, "Rule": d.rule,
             "Size (GB)": round(by_id[d.footage_id]["size_gb"], 2), "Why": d.reason} for d in decisions]
    return {"decisions": pd.DataFrame(rows), "count": len(decisions), "counts": counts, "util": util,
            "pressure": le.pressure_level(util, cfg), "applied": apply}


def purge_marked(user, now=None, quiet=False):
    """Soft-delete (metadata kept) every Marked clip that is not protected. DB trigger is a 2nd guard."""
    rbac.check(user, "run_lifecycle")
    now = now or ss.get_clock()
    with db.transaction() as cur:
        cur.execute(f"UPDATE footage SET deletion_status='Deleted' WHERE deletion_status='Marked' "
                    f"AND importance NOT IN {PROT_SQL} AND NOT EXISTS (SELECT 1 FROM incidents i "
                    f"WHERE i.footage_id=footage.footage_id AND i.legal_hold) RETURNING footage_id, size_gb, tier_id")
        rows = cur.fetchall()
    if rows:
        db.execute_values("INSERT INTO lifecycle_decisions (footage_id,decided_at,from_tier,to_tier,action,reason_text) VALUES %s",
                          [(r["footage_id"], now, None, None, "deleted",
                            "Retention expired and footage was not protected; deleted (soft delete - metadata retained).")
                           for r in rows])
        if not quiet:
            audit_service.log(user, "FOOTAGE_DELETED", f"{len(rows)} clip(s), {sum(r['size_gb'] for r in rows):.1f} GB deleted")
    return len(rows), sum(r["size_gb"] for r in rows)


def optimization_stats(now=None):
    now = now or ss.get_clock()
    st = pool_state()
    f = ss.codec_factors()
    rows = db.fetch_all("SELECT f.compression, SUM(f.size_gb) AS gb FROM footage f JOIN storage_tiers t USING(tier_id) "
                        "WHERE t.tier_name IN ('Warm','Cold') AND f.deletion_status<>'Deleted' GROUP BY f.compression")
    recompress = sum(comp.recompression_saving(r["gb"], r["compression"], "H.265", f) for r in rows)
    hot_mv = db.fetch_one(f"SELECT COALESCE(SUM(f.size_gb),0) AS gb FROM footage f JOIN storage_tiers t USING(tier_id) "
                          f"WHERE t.tier_name='Hot' AND f.deletion_status<>'Deleted' AND f.importance NOT IN {PROT_SQL} "
                          f"AND f.end_time < %s - interval '2 days'", (now,))["gb"]
    exp = db.fetch_one(f"SELECT COALESCE(SUM(size_gb),0) AS gb FROM footage WHERE importance='Normal' "
                       f"AND deletion_status='Retained' AND end_time + (retention_expiry-end_time)*0.8::float8 <= %s", (now,))["gb"]
    return {"pool_util": st["util_pct"], "hot_util": st["tiers"][0]["util"], "used_gb": st["used_gb"],
            "capacity_gb": st["capacity_gb"], "recompress_gb": recompress, "hot_movable_gb": hot_mv, "expiring_gb": exp}


def recommendations(now=None):
    s = ss.get_all()
    return le.recommend_actions(optimization_stats(now), util_warn=float(s["util_warn"]))


def apply_compression(user):
    """SIMULATED re-encode: shrink H.264/MJPEG footage in Warm/Cold to the H.265 factor. No video is touched."""
    rbac.check(user, "run_lifecycle")
    f = ss.codec_factors()
    tids = [t["tier_id"] for t in pool_state()["tiers"] if t["name"] in ("Warm", "Cold")]
    saved, n = 0.0, 0
    for codec in ("H.264", "MJPEG"):
        ratio = f["H.265"] / f[codec]
        with db.transaction() as cur:
            cur.execute("SELECT COALESCE(SUM(size_gb),0) AS gb, COUNT(*) AS n FROM footage WHERE compression=%s "
                        "AND tier_id = ANY(%s) AND deletion_status<>'Deleted'", (codec, tids))
            r = cur.fetchone()
            cur.execute("UPDATE footage SET size_gb=ROUND(size_gb*%s,3), compression='H.265' WHERE compression=%s "
                        "AND tier_id = ANY(%s) AND deletion_status<>'Deleted'", (ratio, codec, tids))
        saved += r["gb"] * (1 - ratio) if ratio < 1 else 0
        n += r["n"]
    audit_service.log(user, "COMPRESSION_SIMULATED", f"Simulated re-compression of {n} clip(s) to H.265; ~{saved:.1f} GB saved")
    from backend.services import alert_service
    alert_service.sync()
    return n, saved


def snapshot_metrics(now):
    st = pool_state()
    t = {x["name"]: x["used_gb"] for x in st["tiers"]}
    db.execute("INSERT INTO storage_metrics (pool_id,recorded_on,used_gb,hot_gb,warm_gb,cold_gb) VALUES (%s,%s,%s,%s,%s,%s) "
               "ON CONFLICT (pool_id,recorded_on) DO UPDATE SET used_gb=EXCLUDED.used_gb, hot_gb=EXCLUDED.hot_gb, "
               "warm_gb=EXCLUDED.warm_gb, cold_gb=EXCLUDED.cold_gb",
               (st["pool"]["pool_id"], now.date(), st["used_gb"], t["Hot"], t["Warm"], t["Cold"]))


def metrics_history(days=365):
    df = db.fetch_df("SELECT recorded_on, used_gb, hot_gb, warm_gb, cold_gb FROM storage_metrics "
                     "ORDER BY recorded_on DESC LIMIT %s", (days,))
    return df.sort_values("recorded_on").reset_index(drop=True) if not df.empty else df


def update_tier(user, tier_id, capacity_tb, cost, speed):
    rbac.check(user, "edit_tiers")
    if capacity_tb <= 0 or cost < 0:
        raise ValueError("Capacity must be positive and cost non-negative.")
    db.execute("UPDATE storage_tiers SET capacity_tb=%s, cost_per_tb_month=%s, access_speed=%s WHERE tier_id=%s",
               (capacity_tb, cost, speed, tier_id))
    audit_service.log(user, "TIER_CONFIG_CHANGED", f"tier_id={tier_id}: capacity {capacity_tb} TB, cost {cost}/TB/month")


def decisions_for(footage_id):
    return db.fetch_df("SELECT decided_at, action, from_tier, to_tier, reason_text FROM lifecycle_decisions "
                       "WHERE footage_id=%s ORDER BY decision_id", (footage_id,))


def recent_decisions(limit=200):
    return db.fetch_df("SELECT d.decided_at, 'F-'||LPAD(d.footage_id::text,6,'0') AS footage, d.action, d.from_tier, d.to_tier, "
                       "d.reason_text FROM lifecycle_decisions d ORDER BY d.decision_id DESC LIMIT %s", (limit,))
