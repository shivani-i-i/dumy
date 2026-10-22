"""Footage metadata search and incident / importance classification."""
from backend.auth import rbac
from backend.config.constants import IMPORTANCE, PROTECTED_CLASSES
from database import connection as db
from backend.engines import retention_engine as rt
from backend.services import audit_service, settings_service as ss


def search(camera_codes=None, location=None, date_from=None, date_to=None, importance=None, incident_only=False,
           tier=None, archive_status=None, deletion_status=None, limit=1000):
    sql = ("SELECT f.footage_id, 'F-'||LPAD(f.footage_id::text,6,'0') AS footage, c.camera_code AS camera, c.location, "
           "f.start_time, f.end_time, ROUND(f.size_gb,2) AS size_gb, f.resolution, f.compression, t.tier_name AS tier, "
           "f.importance, (f.importance IN ('Incident','Critical Evidence') OR COALESCE(i.legal_hold,false)) AS incident, "
           "f.retention_expiry, f.archive_status, f.deletion_status "
           "FROM footage f JOIN cameras c USING(camera_id) JOIN storage_tiers t ON t.tier_id=f.tier_id "
           "LEFT JOIN incidents i ON i.footage_id=f.footage_id WHERE 1=1")
    p = []
    if camera_codes:
        sql += " AND c.camera_code = ANY(%s)"; p.append(list(camera_codes))
    if location:
        sql += " AND c.location ILIKE %s"; p.append(f"%{location}%")
    if date_from:
        sql += " AND f.end_time >= %s"; p.append(date_from)
    if date_to:
        sql += " AND f.start_time < %s + interval '1 day'"; p.append(date_to)
    if importance:
        sql += " AND f.importance = ANY(%s)"; p.append(list(importance))
    if incident_only:
        sql += " AND (f.importance IN ('Incident','Critical Evidence') OR COALESCE(i.legal_hold,false))"
    if tier:
        sql += " AND t.tier_name = ANY(%s)"; p.append(list(tier))
    if archive_status:
        sql += " AND f.archive_status = %s"; p.append(archive_status)
    if deletion_status:
        sql += " AND f.deletion_status = ANY(%s)"; p.append(list(deletion_status))
    sql += " ORDER BY f.start_time DESC LIMIT %s"
    p.append(limit)
    return db.fetch_df(sql, p)


def get_detail(footage_id):
    return db.fetch_one("SELECT f.*, c.camera_code, c.name AS camera_name, c.location, c.priority, c.retention_days, "
                        "t.tier_name AS tier, COALESCE(i.legal_hold,false) AS legal_hold, i.description AS incident_note "
                        "FROM footage f JOIN cameras c USING(camera_id) JOIN storage_tiers t ON t.tier_id=f.tier_id "
                        "LEFT JOIN incidents i ON i.footage_id=f.footage_id WHERE f.footage_id=%s", (footage_id,))


def set_importance(user, footage_id, importance, note="", legal_hold=False):
    """Classify footage. Incident / Critical Evidence / legal hold => extended retention + deletion blocked."""
    rbac.check(user, "flag_footage")
    if importance not in IMPORTANCE:
        raise ValueError("Unknown importance class.")
    f = get_detail(footage_id)
    if not f:
        raise ValueError("Footage not found.")
    if f["deletion_status"] == "Deleted":
        raise ValueError("This footage has already been deleted.")
    was_prot = rt.is_protected(f["importance"], f["legal_hold"])
    now_prot = rt.is_protected(importance, legal_hold)
    if was_prot and not now_prot:
        rbac.check(user, "downgrade_footage")      # only Admin may release protected evidence
    policy = ss.get_policy()
    new_exp = rt.expiry(f["end_time"], importance, f["retention_days"], policy, legal_hold)
    db.execute("UPDATE footage SET importance=%s, retention_expiry=%s, "
               "deletion_status=CASE WHEN deletion_status='Marked' THEN 'Retained' ELSE deletion_status END "
               "WHERE footage_id=%s", (importance, new_exp, footage_id))
    if importance in PROTECTED_CLASSES or legal_hold:
        db.execute("INSERT INTO incidents (footage_id,severity,description,flagged_by,legal_hold) VALUES (%s,%s,%s,%s,%s) "
                   "ON CONFLICT (footage_id) DO UPDATE SET severity=EXCLUDED.severity, description=EXCLUDED.description, "
                   "legal_hold=EXCLUDED.legal_hold, flagged_by=EXCLUDED.flagged_by, flagged_at=now()",
                   (footage_id, importance, note, user["user_id"], legal_hold))
    else:
        db.execute("DELETE FROM incidents WHERE footage_id=%s", (footage_id,))
    action = "INCIDENT_FLAGGED" if importance in PROTECTED_CLASSES or legal_hold else "FOOTAGE_CLASSIFIED"
    audit_service.log(user, action, f"F-{footage_id:06d} {f['importance']} -> {importance}"
                      f"{' + legal hold' if legal_hold else ''}; expiry {f['retention_expiry']:%Y-%m-%d} -> "
                      f"{'never' if legal_hold else format(new_exp, '%Y-%m-%d')}. {note}")
    from backend.services import storage_service
    storage_service.run_lifecycle(user, apply=True, ids=[footage_id], quiet=True)   # e.g. restore from Cold
    return new_exp


def request_flag(user, footage_id, requested, note):
    """Viewers cannot change retention; they raise a request that Storage Manager / Admin review."""
    rbac.check(user, "request_flag")
    from backend.services import alert_service
    f = get_detail(footage_id)
    if not f:
        raise ValueError("Footage not found.")
    alert_service.raise_manual(
        "Info", "Incident Request",
        f"{user['username']} requests F-{footage_id:06d} ({f['camera_code']} {f['location']}) be classed '{requested}'. Note: {note}",
        "Review the clip on the Footage page and classify it if justified.", f"REQ_{footage_id}_{requested}")
    audit_service.log(user, "FLAG_REQUESTED", f"F-{footage_id:06d} -> {requested}")
