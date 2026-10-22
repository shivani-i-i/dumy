"""Environment-based configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "cctv_storage"),
    user=os.getenv("DB_USER", "cctv_admin"),
    password=os.getenv("DB_PASSWORD", "change_me"),
)
SESSION_TIMEOUT_MIN = int(os.getenv("SESSION_TIMEOUT_MIN", 30))
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 5
