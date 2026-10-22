"""Create schema and seed reference data.
Usage:  python -m database.init_db            (first-time setup)
        python -m database.init_db --reset    (DROP everything and recreate)
        python -m database.init_db --demo     (also load the 10-camera demo)"""
import sys
from pathlib import Path

from backend.auth.security import hash_password
from backend.config.constants import DEFAULT_SETTINGS, ROLES
from database import connection as db

DEMO_USERS = [("admin", "Admin@123", "Admin"), ("manager", "Manager@123", "Storage Manager"),
              ("viewer", "Viewer@123", "Viewer")]


def create_schema(reset=False):
    if reset:
        db.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    db.execute(Path(__file__).with_name("schema.sql").read_text())


def seed():
    for r in ROLES:
        db.execute("INSERT INTO roles (role_name) VALUES (%s) ON CONFLICT DO NOTHING", (r,))
    for name, pw, role in DEMO_USERS:
        db.execute("INSERT INTO users (username,password_hash,role_id) SELECT %s,%s,role_id FROM roles WHERE role_name=%s "
                   "ON CONFLICT DO NOTHING", (name, hash_password(pw), role))
    # 7 x 4 TB in RAID 6 = (7-2) x 4 = 20 TB usable
    pool = db.fetch_one("INSERT INTO storage_pools (name,total_capacity_tb) VALUES ('Campus CCTV Pool', 20) RETURNING pool_id")
    pid = pool["pool_id"]
    for name, cap, cost, speed in [("Hot", 4, 20, "Fast (SSD/SAS class)"), ("Warm", 10, 8, "Moderate (NL-SAS)"),
                                   ("Cold", 6, 2, "Slow (archive / tape-like)")]:
        db.execute("INSERT INTO storage_tiers (pool_id,tier_name,capacity_tb,cost_per_tb_month,access_speed) VALUES (%s,%s,%s,%s,%s)",
                   (pid, name, cap, cost, speed))
    db.execute("INSERT INTO retention_policies (name,normal_days,important_days,incident_days,critical_days) "
               "VALUES ('Default policy',30,90,180,365)")
    db.execute("INSERT INTO raid_configurations (pool_id,raid_level,disk_count,disk_size_tb) VALUES (%s,'RAID6',7,4)", (pid,))
    for k, v in DEFAULT_SETTINGS.items():
        db.execute("INSERT INTO system_settings (key,value) VALUES (%s,%s) ON CONFLICT DO NOTHING", (k, v))


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    create_schema(reset)
    seed()
    print("Schema created and seeded.")
    print("Logins:  admin / Admin@123   manager / Manager@123   viewer / Viewer@123   (change after first login)")
    if "--demo" in sys.argv:
        from backend.services import camera_service
        admin = db.fetch_one("SELECT user_id, 'Admin' AS role FROM users WHERE username='admin'")
        camera_service.load_demo(admin)
        print("Loaded 10 demo cameras.")
