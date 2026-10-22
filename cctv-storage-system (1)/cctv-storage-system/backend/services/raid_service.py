"""RAID configuration of the storage pool (calculation/simulation only)."""
from backend.auth import rbac
from database import connection as db
from backend.engines import raid_engine as re_
from backend.services import audit_service


def get_config():
    return db.fetch_one("SELECT r.*, p.total_capacity_tb FROM raid_configurations r JOIN storage_pools p USING(pool_id) "
                        "ORDER BY r.raid_id LIMIT 1")


def _sync(cfg_id, level, n, size, failed):
    calc = re_.calculate(level, n, size)
    status = re_.array_status(level, n, failed)
    db.execute("UPDATE raid_configurations SET raid_level=%s, disk_count=%s, disk_size_tb=%s, failed_disks=%s, status=%s "
               "WHERE raid_id=%s", (level, n, size, failed, status, cfg_id))
    db.execute("UPDATE storage_pools SET total_capacity_tb=%s WHERE pool_id=(SELECT pool_id FROM raid_configurations WHERE raid_id=%s)",
               (calc["usable_tb"], cfg_id))
    from backend.services import alert_service
    alert_service.sync()
    return calc, status


def save_config(user, level, n, size):
    rbac.check(user, "edit_raid")
    calc = re_.calculate(level, n, size)
    if not calc["valid"]:
        raise ValueError(calc["message"])
    cfg = get_config()
    _sync(cfg["raid_id"], level, n, size, 0)
    audit_service.log(user, "RAID_CONFIG_CHANGED", f"{cfg['raid_level']} {cfg['disk_count']}x{cfg['disk_size_tb']}TB -> "
                      f"{level} {n}x{size}TB (usable {calc['usable_tb']:.1f} TB)")


def simulate_failure(user):
    rbac.check(user, "edit_raid")
    c = get_config()
    failed = min(c["failed_disks"] + 1, c["disk_count"])
    _, status = _sync(c["raid_id"], c["raid_level"], c["disk_count"], c["disk_size_tb"], failed)
    audit_service.log(user, "RAID_FAILURE_SIMULATED", f"{failed} failed disk(s); array is {status}")
    return status


def rebuild(user):
    rbac.check(user, "edit_raid")
    c = get_config()
    hrs = re_.rebuild_hours(c["raid_level"], c["disk_size_tb"])
    _sync(c["raid_id"], c["raid_level"], c["disk_count"], c["disk_size_tb"], 0)
    audit_service.log(user, "RAID_REBUILD", f"Replaced failed disk(s); estimated rebuild {hrs} h")
    return hrs


def add_disks(user, n):
    rbac.check(user, "edit_raid")
    c = get_config()
    total = c["disk_count"] + n
    if c["raid_level"] == "RAID10" and total % 2:
        raise ValueError("RAID 10 needs an even number of disks.")
    _sync(c["raid_id"], c["raid_level"], total, c["disk_size_tb"], c["failed_disks"])
    audit_service.log(user, "RAID_CAPACITY_ADDED", f"Added {n} disk(s): {c['disk_count']} -> {total}")
