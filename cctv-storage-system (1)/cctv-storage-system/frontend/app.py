"""ICSLOS - Intelligent CCTV Storage Lifecycle and Optimization System (entry point).
Run:  streamlit run frontend/app.py"""
import sys
from pathlib import Path

import streamlit as st

# Make `backend`, `database` and `frontend` importable when launched as `streamlit run frontend/app.py`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="ICSLOS - CCTV Storage Console", page_icon="🗄️", layout="wide")

from backend.auth import session                     # noqa: E402
from backend.auth.rbac import has_permission        # noqa: E402
from frontend.components.ui import inject_css        # noqa: E402

inject_css()
try:
    user = session.current_user()
except Exception as e:                       # DB not reachable / not initialised
    st.error("Cannot reach the database. Check `.env` and run `python -m database.init_db`.")
    st.exception(e)
    st.stop()

if not user:
    session.login_page()
    st.stop()

# (file, title, icon, permission)  - order matches the required sidebar
PAGES = [
    ("views/dashboard.py", "Dashboard", "📊", "dashboard"),
    ("views/cameras.py", "Cameras", "📹", "view_cameras"),
    ("views/calculator.py", "Storage Calculator", "🧮", "calculator"),
    ("views/raid.py", "RAID Management", "💽", "raid_view"),
    ("views/tiers.py", "Storage Tiers", "🧱", "tiers_view"),
    ("views/footage.py", "Footage", "🎞️", "footage_view"),
    ("views/archive.py", "Archive", "🗃️", "archive_view"),
    ("views/backup.py", "Backup & Recovery", "💾", "backup_view"),
    ("views/forecast.py", "Capacity Forecast", "📈", "forecast_view"),
    ("views/alerts.py", "Alerts", "🚨", "alerts_view"),
    ("views/audit.py", "Audit Logs", "📜", "audit_view"),
    ("views/settings.py", "Settings", "⚙️", "settings_view"),
]
allowed = [p for p in PAGES if has_permission(user["role"], p[3])]
pages = [st.Page(f, title=t, icon=i, default=True) if n == 0 else st.Page(f, title=t, icon=i, url_path=f.split("/")[1][:-3])
         for n, (f, t, i, _) in enumerate(allowed)]

from backend.services import settings_service as ss   # noqa: E402

with st.sidebar:
    st.markdown("### 🗄️ ICSLOS")
    st.caption(f"👤 **{user['username']}** · {user['role']}")
    try:
        st.caption(f"🕒 Simulation clock: {ss.get_clock():%Y-%m-%d %H:%M}")
    except Exception:
        pass
    if st.button("Log out"):
        session.logout()
        st.rerun()
    st.divider()

st.navigation(pages).run()
