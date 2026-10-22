"""System settings (thresholds, RPO/RTO, simulation clock) + retention policy + users."""
from datetime import datetime

from backend.auth import rbac
from backend.auth.security import hash_password, password_problem
from backend.config.constants import DEFAULT_SETTINGS
from database import connection as db
from backend.services import audit_service


def _cast(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return float(v)
        except (TypeError, ValueError):
            return v


def get_all():
    rows = db.fetch_all("SELECT key, value FROM system_settings")
    s = {k: v for k, v in DEFAULT_SETTINGS.items()}
    s.update({r["key"]: r["value"] for r in rows})
    return {k: _cast(v) for k, v in s.items()}


def set_raw(key, value):
    """Internal (no RBAC): used by the simulation clock."""
    db.execute("INSERT INTO system_settings (key,value) VALUES (%s,%s) "
               "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (key, str(value)))


def update(user, changes: dict):
    rbac.check(user, "edit_settings")
    old = get_all()
    for k, v in changes.items():
        if str(old.get(k)) != str(v):
            set_raw(k, v)
            action = "RPO_RTO_CHANGED" if k in ("rpo_hours", "rto_hours") else "SETTING_CHANGED"
            audit_service.log(user, action, f"{k}: {old.get(k)} -> {v}")


def get_clock():
    v = get_all()["sim_clock"]
    if not v:
        v = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        set_raw("sim_clock", v)
    return datetime.fromisoformat(str(v))


def codec_factors(s=None):
    s = s or get_all()
    return {"H.264": float(s["codec_H264"]), "H.265": float(s["codec_H265"]),
            "H.265+": float(s["codec_H265plus"]), "MJPEG": float(s["codec_MJPEG"])}


def mode_factors(s=None):
    s = s or get_all()
    return {"Continuous": 1.0, "Motion": float(s["motion_factor"]), "Scheduled": 1.0}


# ---- retention policy ----
def get_policy():
    return db.fetch_one("SELECT * FROM retention_policies ORDER BY policy_id LIMIT 1")


def update_policy(user, normal, important, incident, critical):
    rbac.check(user, "edit_settings")
    p = get_policy()
    db.execute("UPDATE retention_policies SET normal_days=%s, important_days=%s, incident_days=%s, critical_days=%s "
               "WHERE policy_id=%s", (normal, important, incident, critical, p["policy_id"]))
    audit_service.log(user, "RETENTION_POLICY_CHANGED",
                      f"normal {p['normal_days']}->{normal}, important {p['important_days']}->{important}, "
                      f"incident {p['incident_days']}->{incident}, critical {p['critical_days']}->{critical}")


# ---- users ----
def list_users(user):
    rbac.check(user, "manage_users")
    return db.fetch_df("SELECT u.user_id, u.username, r.role_name AS role, u.is_active, u.failed_attempts, u.created_at "
                       "FROM users u JOIN roles r USING(role_id) ORDER BY u.user_id")


def add_user(user, username, password, role):
    rbac.check(user, "manage_users")
    if not username.strip():
        raise ValueError("Username is required.")
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    rid = db.fetch_one("SELECT role_id FROM roles WHERE role_name=%s", (role,))
    if not rid:
        raise ValueError("Unknown role.")
    if db.fetch_one("SELECT 1 FROM users WHERE username=%s", (username.strip(),)):
        raise ValueError("Username already exists.")
    db.execute("INSERT INTO users (username,password_hash,role_id) VALUES (%s,%s,%s)",
               (username.strip(), hash_password(password), rid["role_id"]))
    audit_service.log(user, "USER_ADDED", f"Created user '{username}' with role {role}")


def set_user_active(user, user_id, active):
    rbac.check(user, "manage_users")
    if user_id == user["user_id"]:
        raise ValueError("You cannot disable your own account.")
    db.execute("UPDATE users SET is_active=%s, failed_attempts=0, locked_until=NULL WHERE user_id=%s", (active, user_id))
    audit_service.log(user, "USER_ENABLED" if active else "USER_DISABLED", f"user_id={user_id}")


def reset_password(user, user_id, new_password):
    rbac.check(user, "manage_users")
    problem = password_problem(new_password)
    if problem:
        raise ValueError(problem)
    db.execute("UPDATE users SET password_hash=%s, failed_attempts=0, locked_until=NULL WHERE user_id=%s",
               (hash_password(new_password), user_id))
    audit_service.log(user, "PASSWORD_RESET", f"user_id={user_id}")
