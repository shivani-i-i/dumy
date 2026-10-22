import streamlit as st
from backend.auth import session
from frontend.components.ui import flash, header, sim_notice
from backend.config.constants import ROLES
from backend.services import (alert_service, camera_service, settings_service as ss, simulation_service as sim)

user = session.require("settings_view")
header("Settings", "Thresholds, assumptions, retention policy, users and the simulation controls.")
s = ss.get_all()
t1, t2, t3, t4, t5 = st.tabs(["Lifecycle & alerts", "Capacity assumptions", "Retention policy", "Users", "Simulation"])


def form(fields, key):
    """fields: list of (setting_key, label, min, max, step). Saves changed values via the audited service."""
    with st.form(key):
        cols = st.columns(3)
        vals = {k: cols[i % 3].number_input(label, float(lo), float(hi), float(s[k]), float(step)) for i, (k, label, lo, hi, step) in enumerate(fields)}
        if st.form_submit_button("Save", type="primary"):
            ss.update(user, {k: (int(v) if float(v).is_integer() else v) for k, v in vals.items()})
            alert_service.sync(); flash("Saved."); st.rerun()


with t1:
    st.markdown("**Tier windows and priority multipliers**")
    form([("hot_window_days", "Hot window (days)", 1, 365, 1), ("warm_window_days", "Warm window (days)", 1, 3650, 1),
          ("priority_mult_low", "Low priority ×", 0.1, 5, 0.1), ("priority_mult_medium", "Medium ×", 0.1, 5, 0.1),
          ("priority_mult_high", "High ×", 0.1, 5, 0.1), ("priority_mult_critical", "Critical ×", 0.1, 5, 0.1)], "f1")
    st.markdown("**Pressure overlay & alert thresholds (% utilization)**")
    form([("pressure_l1", "Pressure level 1 (>%)", 1, 100, 1), ("pressure_l2", "Pressure level 2 (>%)", 1, 100, 1),
          ("pressure_shrink", "Hot-window shrink factor", 0.1, 1, 0.05), ("util_warn", "Warning alert (>%)", 1, 100, 1),
          ("util_high", "High alert (>%)", 1, 100, 1), ("util_critical", "Critical alert (>%)", 1, 100, 1),
          ("forecast_alert_days", "Forecast alert horizon (days)", 1, 365, 1)], "f2")

with t2:
    sim_notice("Codec factors are configurable assumptions (typical vendor figures), not measured results.")
    form([("overhead_pct", "Overhead (%)", 0, 50, 1), ("headroom_pct", "Headroom (%)", 0, 100, 1),
          ("codec_H264", "H.264 factor", 0.1, 5, 0.05), ("codec_H265", "H.265 factor", 0.1, 5, 0.05),
          ("codec_H265plus", "H.265+ factor", 0.1, 5, 0.05), ("codec_MJPEG", "MJPEG factor", 0.1, 10, 0.1),
          ("motion_factor", "Motion-mode duty factor", 0.05, 1, 0.05)], "f3")

with t3:
    p = ss.get_policy()
    with st.form("pol"):
        c = st.columns(4)
        n = c[0].number_input("Normal (days)", 1, 3650, p["normal_days"])
        i = c[1].number_input("Important (days)", 1, 3650, p["important_days"])
        inc = c[2].number_input("Incident (days)", 1, 3650, p["incident_days"])
        cr = c[3].number_input("Critical evidence (days)", 1, 3650, p["critical_days"])
        if st.form_submit_button("Save policy", type="primary"):
            ss.update_policy(user, int(n), int(i), int(inc), int(cr)); flash("Policy saved (applies to newly classified footage)."); st.rerun()
    st.caption("A camera's own retention is used for Normal footage; higher classes extend, never shorten, retention.")

with t4:
    st.dataframe(ss.list_users(user), hide_index=True)
    with st.form("nu"):
        c = st.columns(3)
        un = c[0].text_input("Username"); pw = c[1].text_input("Password", type="password"); ro = c[2].selectbox("Role", ROLES)
        if st.form_submit_button("Add user"):
            try:
                ss.add_user(user, un, pw, ro); flash("User created."); st.rerun()
            except Exception as ex:
                st.error(str(ex))
    users = ss.list_users(user)
    c = st.columns(3)
    pick = c[0].selectbox("User", users["user_id"], format_func=lambda i: users.set_index("user_id").loc[i, "username"])
    if c[1].button("Enable / disable"):
        try:
            cur = bool(users.set_index("user_id").loc[pick, "is_active"])
            ss.set_user_active(user, int(pick), not cur); st.rerun()
        except Exception as ex:
            st.error(str(ex))
    newpw = c[2].text_input("New password", type="password", key="npw")
    if st.button("Reset password"):
        try:
            ss.reset_password(user, int(pick), newpw); st.success("Password reset.")
        except Exception as ex:
            st.error(str(ex))

with t5:
    st.write(f"Simulation clock: **{ss.get_clock():%Y-%m-%d %H:%M}**")
    sim_notice("Footage rows are generated metadata sized from each camera's bitrate. Advancing time creates footage and (optionally) "
               "runs the lifecycle engine and deletes expired footage each simulated day.")
    c = st.columns(3)
    if c[0].button("Load 10 demo cameras"):
        try:
            camera_service.load_demo(user); flash("Loaded."); st.rerun()
        except Exception as ex:
            st.error(str(ex))
    days = c[1].number_input("History days", 1, 120, 7)
    if c[2].button("Generate history (all Hot)"):
        with st.spinner("Generating…"):
            try:
                sim.generate_history(user, int(days)); flash("History generated."); st.rerun()
            except Exception as ex:
                st.error(str(ex))
    st.markdown("**Advance time**")
    c = st.columns(4)
    amt = c[0].number_input("Amount", 1, 2880, 10)
    unit = c[1].selectbox("Unit", ["days", "hours"])
    lc = c[2].checkbox("Auto-run lifecycle each day", True)
    pg = c[3].checkbox("Auto-delete expired", True)
    if st.button("⏩ Advance clock", type="primary"):
        with st.spinner("Simulating…"):
            try:
                tot, purged = sim.advance(user, amt * (24 if unit == "days" else 1), lc, pg)
                flash(f"Done. To Warm {tot['to_warm']}, archived {tot['to_cold']}, marked {tot['marked']}, deleted {purged}."); st.rerun()
            except Exception as ex:
                st.error(str(ex))
    st.markdown("**Reset**")
    rc = st.checkbox("Also remove all cameras")
    if st.button("Reset simulation data"):
        sim.reset(user, rc); flash("Reset."); st.rerun()
