"""Alert persistence: evaluate state -> insert (deduplicated) / refresh / auto-resolve."""
from backend.auth import rbac
from database import connection as db
from backend.engines import alert_engine as ae
from backend.services import audit_service, settings_service as ss

SEV_RANK = "CASE severity WHEN 'Critical' THEN 4 WHEN 'High' THEN 3 WHEN 'Warning' THEN 2 ELSE 1 END"


def build_state(now=None):
    from backend.services import backup_service, forecast_service, raid_service, storage_service
    now = now or ss.get_clock()
    st = storage_service.pool_state()
    viol, review = storage_service.retention_counts(now)
    raid = raid_service.get_config()
    fc = forecast_service.compute(now)
    return {"pool_util": st["util_pct"], "used_gb": st["used_gb"],
            "tiers": [{"name": t["name"], "util": t["util"], "capacity_tb": t["capacity_tb"]} for t in st["tiers"]],
            "backup": backup_service.status(now),
            "raid": {"status": raid["status"], "level": raid["raid_level"], "failed": raid["failed_disks"]} if raid else None,
            "retention_violations": viol, "protected_review": review, "forecast": fc["result"]}


def sync(now=None):
    now = now or ss.get_clock()
    s = ss.get_all()
    th = {k: float(s[k]) for k in ("util_warn", "util_high", "util_critical", "forecast_alert_days")}
    specs = ae.evaluate(build_state(now), th)
    keys = {sp["dedup_key"] for sp in specs}
    new = 0
    for sp in specs:
        new += db.execute(
            "INSERT INTO alerts (created_at,severity,category,description,recommended_action,dedup_key) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (dedup_key) WHERE status='Open' DO NOTHING",
            (now, sp["severity"], sp["category"], sp["description"], sp["recommended_action"], sp["dedup_key"]))
        db.execute("UPDATE alerts SET description=%s, recommended_action=%s WHERE status='Open' AND dedup_key=%s",
                   (sp["description"], sp["recommended_action"], sp["dedup_key"]))
    for a in db.fetch_all("SELECT alert_id, dedup_key FROM alerts WHERE status='Open' AND dedup_key IS NOT NULL"):
        if a["dedup_key"].startswith(ae.AUTO_PREFIXES) and a["dedup_key"] not in keys:
            db.execute("UPDATE alerts SET status='Resolved', resolved_at=%s WHERE alert_id=%s", (now, a["alert_id"]))
    return new


def raise_manual(severity, category, description, action, key):
    db.execute("INSERT INTO alerts (created_at,severity,category,description,recommended_action,dedup_key) "
               "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (dedup_key) WHERE status='Open' DO NOTHING",
               (ss.get_clock(), severity, category, description, action, key))


def list_alerts(status=None, severity=None):
    sql = ("SELECT a.alert_id, 'A-'||LPAD(a.alert_id::text,4,'0') AS alert, a.created_at, a.severity, a.category, "
           "a.description, a.recommended_action, a.status, COALESCE(u.username, CASE WHEN a.status='Resolved' THEN 'auto' END) AS resolved_by "
           "FROM alerts a LEFT JOIN users u ON u.user_id=a.resolved_by WHERE 1=1")
    p = []
    if status:
        sql += " AND a.status=%s"; p.append(status)
    if severity:
        sql += " AND a.severity = ANY(%s)"; p.append(list(severity))
    sql = sql.replace("SELECT a.alert_id", f"SELECT {SEV_RANK.replace('severity', 'a.severity')} AS _r, a.alert_id", 1)
    sql += " ORDER BY (a.status='Open') DESC, _r DESC, a.alert_id DESC"
    df = db.fetch_df(sql, p)
    return df.drop(columns=["_r"]) if not df.empty else df


def counts():
    return db.fetch_all("SELECT severity, COUNT(*) AS n FROM alerts WHERE status='Open' GROUP BY severity")


def resolve(user, alert_id):
    rbac.check(user, "resolve_alerts")
    n = db.execute("UPDATE alerts SET status='Resolved', resolved_by=%s, resolved_at=%s WHERE alert_id=%s AND status='Open'",
                   (user["user_id"], ss.get_clock(), alert_id))
    if n:
        audit_service.log(user, "ALERT_RESOLVED", f"A-{alert_id:04d} resolved")
    return n
