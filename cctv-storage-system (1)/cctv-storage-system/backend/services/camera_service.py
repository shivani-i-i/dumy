"""Camera CRUD + per-camera storage estimates."""
from backend.auth import rbac
from backend.config.constants import DEMO_CAMERAS
from database import connection as db
from backend.engines import capacity_engine as ce
from backend.services import audit_service, settings_service as ss


def tier_id(name):
    r = db.fetch_one("SELECT tier_id FROM storage_tiers WHERE tier_name=%s", (name,))
    return r["tier_id"] if r else None


def next_code():
    rows = db.fetch_all("SELECT camera_code FROM cameras")
    nums = [int(r["camera_code"][1:]) for r in rows if r["camera_code"][1:].isdigit()]
    return f"C{(max(nums) + 1) if nums else 1:02d}"


def list_cameras(active_only=False):
    cams = db.fetch_all("SELECT c.*, t.tier_name AS default_tier FROM cameras c "
                        "LEFT JOIN storage_tiers t ON t.tier_id=c.default_tier_id "
                        + ("WHERE c.status='Active' " if active_only else "") + "ORDER BY c.camera_code")
    mf = ss.mode_factors()
    for c in cams:
        e = ce.camera_storage(c["bitrate_mbps"], c["recording_hours"], c["recording_mode"], mf)
        c["est_gb_day"], c["est_gb_month"] = e["gb_day"], e["gb_month"]
    return cams


def consumption():
    """Actual stored GB per camera (non-deleted footage), by tier."""
    return db.fetch_df(
        "SELECT c.camera_code, c.location, c.priority, "
        "COALESCE(SUM(f.size_gb) FILTER (WHERE t.tier_name='Hot' AND f.deletion_status<>'Deleted'),0) AS hot_gb, "
        "COALESCE(SUM(f.size_gb) FILTER (WHERE t.tier_name='Warm' AND f.deletion_status<>'Deleted'),0) AS warm_gb, "
        "COALESCE(SUM(f.size_gb) FILTER (WHERE t.tier_name='Cold' AND f.deletion_status<>'Deleted'),0) AS cold_gb, "
        "COALESCE(SUM(f.size_gb) FILTER (WHERE f.deletion_status<>'Deleted'),0) AS total_gb "
        "FROM cameras c LEFT JOIN footage f ON f.camera_id=c.camera_id "
        "LEFT JOIN storage_tiers t ON t.tier_id=f.tier_id GROUP BY c.camera_id ORDER BY c.camera_code")


def _validate(d):
    if not d["name"].strip() or not d["location"].strip():
        raise ValueError("Name and location are required.")
    if not 1 <= d["fps"] <= 60:
        raise ValueError("FPS must be between 1 and 60.")
    if d["bitrate_mbps"] <= 0:
        raise ValueError("Bitrate must be positive.")
    if d["retention_days"] < 1:
        raise ValueError("Retention must be at least 1 day.")


def add_camera(user, d):
    rbac.check(user, "manage_cameras")
    _validate(d)
    code = d.get("camera_code") or next_code()
    if db.fetch_one("SELECT 1 FROM cameras WHERE camera_code=%s", (code,)):
        raise ValueError(f"Camera ID {code} already exists.")
    pol = ss.get_policy()
    db.execute("INSERT INTO cameras (camera_code,name,location,resolution,fps,compression,bitrate_mbps,recording_mode,"
               "recording_hours,priority,retention_days,policy_id,status,default_tier_id) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
               (code, d["name"], d["location"], d["resolution"], d["fps"], d["compression"], d["bitrate_mbps"],
                d["recording_mode"], d["recording_hours"], d["priority"], d["retention_days"], pol["policy_id"],
                d.get("status", "Active"), tier_id(d.get("default_tier", "Hot"))))
    audit_service.log(user, "CAMERA_ADDED", f"{code} {d['name']} @ {d['location']} ({d['resolution']}/{d['fps']}fps/"
                      f"{d['compression']}, {d['priority']} priority, {d['retention_days']} d)")
    return code


def update_camera(user, camera_id, d):
    rbac.check(user, "manage_cameras")
    _validate(d)
    db.execute("UPDATE cameras SET name=%s, location=%s, resolution=%s, fps=%s, compression=%s, bitrate_mbps=%s, "
               "recording_mode=%s, recording_hours=%s, priority=%s, retention_days=%s, status=%s, default_tier_id=%s "
               "WHERE camera_id=%s",
               (d["name"], d["location"], d["resolution"], d["fps"], d["compression"], d["bitrate_mbps"],
                d["recording_mode"], d["recording_hours"], d["priority"], d["retention_days"], d["status"],
                tier_id(d.get("default_tier", "Hot")), camera_id))
    audit_service.log(user, "CAMERA_MODIFIED", f"camera_id={camera_id}: {d['name']} priority={d['priority']} "
                      f"retention={d['retention_days']} d status={d['status']}")


def remove_camera(user, camera_id):
    """Hard delete only if no footage exists; otherwise deactivate (keeps evidence trail)."""
    rbac.check(user, "manage_cameras")
    has = db.fetch_one("SELECT 1 FROM footage WHERE camera_id=%s LIMIT 1", (camera_id,))
    if has:
        db.execute("UPDATE cameras SET status='Inactive' WHERE camera_id=%s", (camera_id,))
        audit_service.log(user, "CAMERA_DEACTIVATED", f"camera_id={camera_id} has footage; deactivated instead of deleted")
        return "deactivated"
    db.execute("DELETE FROM cameras WHERE camera_id=%s", (camera_id,))
    audit_service.log(user, "CAMERA_REMOVED", f"camera_id={camera_id}")
    return "deleted"


def load_demo(user):
    rbac.check(user, "manage_cameras")
    if db.fetch_one("SELECT 1 FROM cameras LIMIT 1"):
        raise ValueError("Cameras already exist. Use Settings > Simulation > Reset (remove cameras) first.")
    f = ss.codec_factors()
    for code, name, loc, res, fps, codec, mode, pri, ret in DEMO_CAMERAS:
        add_camera(user, dict(camera_code=code, name=name, location=loc, resolution=res, fps=fps, compression=codec,
                              bitrate_mbps=ce.effective_bitrate(res, fps, codec, f), recording_mode=mode,
                              recording_hours=24, priority=pri, retention_days=ret))
    audit_service.log(user, "DEMO_LOADED", "Loaded 10 demo cameras")
