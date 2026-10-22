"""Login / logout / session management on top of st.session_state."""
from datetime import datetime, timedelta

import streamlit as st

from backend.auth.rbac import PermissionDenied, has_permission
from backend.auth.security import dummy_verify, verify_password
from backend.config.settings import LOCKOUT_MINUTES, MAX_FAILED_LOGINS, SESSION_TIMEOUT_MIN
from database import connection as db
from backend.services import audit_service


def authenticate(username, password):
    """Return (user_dict | None, message)."""
    u = db.fetch_one("SELECT u.*, r.role_name FROM users u JOIN roles r USING(role_id) WHERE u.username=%s",
                     (username.strip(),))
    if not u:
        dummy_verify(password)
        audit_service.log(None, "LOGIN_FAILED", f"Unknown username '{username}'")
        return None, "Invalid username or password."
    if not u["is_active"]:
        return None, "This account is disabled."
    if u["locked_until"] and u["locked_until"] > datetime.now():
        mins = int((u["locked_until"] - datetime.now()).total_seconds() // 60) + 1
        return None, f"Account locked after repeated failures. Try again in about {mins} min."
    if not verify_password(password, u["password_hash"]):
        attempts = u["failed_attempts"] + 1
        lock = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES) if attempts >= MAX_FAILED_LOGINS else None
        db.execute("UPDATE users SET failed_attempts=%s, locked_until=%s WHERE user_id=%s",
                   (0 if lock else attempts, lock, u["user_id"]))
        audit_service.log(u["user_id"], "LOGIN_FAILED", f"Wrong password ({attempts}/{MAX_FAILED_LOGINS})")
        return None, "Invalid username or password."
    db.execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE user_id=%s", (u["user_id"],))
    audit_service.log(u["user_id"], "LOGIN", "User logged in")
    return {"user_id": u["user_id"], "username": u["username"], "role": u["role_name"]}, "OK"


def current_user():
    """Logged-in user dict, or None if not logged in / session expired."""
    user = st.session_state.get("user")
    if not user:
        return None
    last = st.session_state.get("last_active", datetime.now())
    if datetime.now() - last > timedelta(minutes=SESSION_TIMEOUT_MIN):
        audit_service.log(user["user_id"], "SESSION_TIMEOUT", "Session expired due to inactivity")
        st.session_state.clear()
        st.session_state["flash"] = "Session expired. Please log in again."
        return None
    st.session_state["last_active"] = datetime.now()
    return user


def logout():
    user = st.session_state.get("user")
    if user:
        audit_service.log(user["user_id"], "LOGOUT", "User logged out")
    st.session_state.clear()


def require(perm):
    """Page guard: returns the user or stops the page with an Access Denied message (and audits it)."""
    user = current_user()
    if not user:
        st.error("Please log in."); st.stop()
    if not has_permission(user["role"], perm):
        audit_service.log(user["user_id"], "ACCESS_DENIED", f"Attempted to open a page requiring '{perm}'")
        st.error(f"Access denied: the **{user['role']}** role cannot open this page.")
        st.stop()
    return user


def login_page():
    st.markdown("## 🗄️ ICSLOS — CCTV Storage Console")
    st.caption("Intelligent CCTV Storage Lifecycle and Optimization System")
    if st.session_state.get("flash"):
        st.warning(st.session_state.pop("flash"))
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", type="primary")
        if ok:
            user, msg = authenticate(username, password)
            if user:
                st.session_state["user"] = user
                st.session_state["last_active"] = datetime.now()
                st.rerun()
            st.error(msg)
        st.caption("Demo accounts are created by `python -m db.init_db` (see README).")
