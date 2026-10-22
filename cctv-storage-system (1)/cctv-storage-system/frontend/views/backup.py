import streamlit as st
from backend.auth import session
from backend.auth.rbac import has_permission
from frontend.components.ui import flash, fmt_gb, header, sim_notice
from backend.services import backup_service as bs, settings_service as ss

user = session.require("backup_view")
can_run = has_permission(user["role"], "run_backup")
can_cfg = has_permission(user["role"], "config_backup")
header("Backup & Recovery", "Simulated backups with RPO / RTO verification.")
sim_notice("Backups and recovery are simulated: sizes are derived from footage metadata and durations from configured speeds.")
s = ss.get_all()
e = bs.status()

m = st.columns(5)
m[0].metric("Last successful backup", "none" if not e["last_success"] else f"{e['age_hours']:.1f} h ago")
m[1].metric("Frequency", f"every {s['backup_frequency_hours']} h")
m[2].metric("Destination", str(s["backup_destination"]))
m[3].metric("RPO target", f"{s['rpo_hours']} h", "met" if e["rpo_ok"] else "VIOLATED", delta_color="normal" if e["rpo_ok"] else "inverse")
m[4].metric("RTO target", f"{s['rto_hours']} h", "n/a" if e["est_rto_hours"] is None else f"est. {e['est_rto_hours']:.1f} h",
            delta_color="off" if e["est_rto_hours"] is None else ("normal" if e["rto_ok"] else "inverse"))
(st.success if e["rpo_ok"] else st.error)("RPO — " + e["rpo_msg"])
(st.success if e["rto_ok"] else st.error)("RTO — " + e["rto_msg"])
if e["latest_failed"]:
    st.error("The latest backup attempt FAILED.")
st.caption("RPO = how much recent data we can afford to lose (age of newest recovery point). "
           "RTO = how quickly service must be restored (restore size ÷ restore speed + overhead). "
           "Scope: Hot + Warm tiers; Cold is already an archive copy.")

if can_run:
    b = st.columns(5)
    for col, (label, kw) in zip(b, [("Full backup", ("Full", False)), ("Incremental backup", ("Incremental", False)),
                                    ("Simulate FAILED backup", ("Full", True))]):
        if col.button(label):
            try:
                size, dur, ok = bs.run_backup(user, *kw)
                flash(f"{kw[0]} backup {'completed' if ok else 'FAILED (simulated)'}: {fmt_gb(size)} in {dur:.2f} h",
                      "success" if ok else "error")
                st.rerun()
            except Exception as ex:
                st.error(str(ex))
    if b[3].button("Simulate recovery"):
        try:
            r = bs.run_recovery(user)
            flash(f"Recovered {fmt_gb(r['restore_gb'])} in ~{r['est_rto_hours']:.1f} h - RTO {'met' if r['rto_ok'] else 'MISSED'}",
                  "success" if r["rto_ok"] else "error")
            st.rerun()
        except Exception as ex:
            st.error(str(ex))
    if b[4].button("Refresh view"):
        st.rerun()
else:
    st.info("Only an Admin can run backups. You can monitor status here.")

st.subheader("Backup history")
h = bs.list_backups()
st.dataframe(h, hide_index=True) if not h.empty else st.info("No backups yet.")

if can_cfg:
    with st.expander("Configure RPO / RTO and backup settings (Admin)"):
        with st.form("bk"):
            c1, c2, c3 = st.columns(3)
            rpo = c1.number_input("RPO target (hours)", 0.5, 720.0, float(s["rpo_hours"]))
            rto = c2.number_input("RTO target (hours)", 0.25, 720.0, float(s["rto_hours"]))
            freq = c3.number_input("Backup frequency (hours)", 1.0, 720.0, float(s["backup_frequency_hours"]))
            c1, c2, c3 = st.columns(3)
            dest = c1.text_input("Destination", str(s["backup_destination"]))
            bsp = c2.number_input("Backup speed (GB/h)", 10.0, 100000.0, float(s["backup_speed_gb_per_hr"]))
            rsp = c3.number_input("Restore speed (GB/h)", 10.0, 100000.0, float(s["restore_speed_gb_per_hr"]))
            if st.form_submit_button("Save", type="primary"):
                ss.update(user, dict(rpo_hours=rpo, rto_hours=rto, backup_frequency_hours=freq, backup_destination=dest,
                                     backup_speed_gb_per_hr=bsp, restore_speed_gb_per_hr=rsp))
                from backend.services import alert_service; alert_service.sync()
                flash("Saved."); st.rerun()
