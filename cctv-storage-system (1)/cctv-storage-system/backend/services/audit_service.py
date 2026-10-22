"""Append-only audit trail."""
from database import connection as db


def log(user, action, description=""):
    """`user` may be a user dict, a user_id, or None (system / unauthenticated)."""
    uid = user.get("user_id") if isinstance(user, dict) else user
    db.execute("INSERT INTO audit_logs (user_id, action, description) VALUES (%s,%s,%s)", (uid, action, description))


def fetch(user_filter=None, action_filter=None, limit=500):
    sql = ("SELECT a.log_id, a.created_at, COALESCE(u.username,'system') AS user, a.action, a.description "
           "FROM audit_logs a LEFT JOIN users u USING(user_id) WHERE 1=1")
    p = []
    if user_filter:
        sql += " AND u.username = %s"; p.append(user_filter)
    if action_filter:
        sql += " AND a.action = %s"; p.append(action_filter)
    sql += " ORDER BY a.log_id DESC LIMIT %s"
    p.append(limit)
    return db.fetch_df(sql, p)


def distinct_actions():
    return [r["action"] for r in db.fetch_all("SELECT DISTINCT action FROM audit_logs ORDER BY 1")]
