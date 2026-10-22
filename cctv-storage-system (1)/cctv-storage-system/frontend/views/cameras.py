import streamlit as st
from backend.auth import session
from backend.auth.rbac import has_permission
from frontend.components import charts
from frontend.components.ui import flash, header
from backend.config.constants import CODECS, PRIORITIES, RECORDING_MODES, RESOLUTIONS, TIERS
from backend.engines import capacity_engine as ce
from backend.services import camera_service as cs, settings_service as ss

user = session.require("view_cameras")
can_edit = has_permission(user["role"], "manage_cameras")
header("Camera Management", "Every camera's recording parameters drive its storage estimate and lifecycle behaviour.")
fac = ss.codec_factors()
cams = cs.list_cameras()

tabs = st.tabs(["Fleet", "Consumption"] + (["Add camera", "Edit / remove"] if can_edit else []))

with tabs[0]:
    if cams:
        import pandas as pd
        df = pd.DataFrame(cams)[["camera_code", "name", "location", "resolution", "fps", "compression", "bitrate_mbps",
                                  "recording_mode", "priority", "retention_days", "status", "default_tier", "est_gb_day", "est_gb_month"]]
        df = df.rename(columns={"camera_code": "ID", "bitrate_mbps": "Mbps", "retention_days": "Retention (d)",
                                "default_tier": "Tier", "est_gb_day": "GB/day", "est_gb_month": "GB/month"})
        st.dataframe(df.round(2), hide_index=True)
        a = [c for c in cams if c["status"] == "Active"]
        st.info(f"Estimated total for {len(a)} active cameras: **{sum(c['est_gb_day'] for c in a):,.1f} GB/day** · "
                f"**{sum(c['est_gb_month'] for c in a) / 1000:,.2f} TB/month**")
    else:
        st.info("No cameras yet." + (" Add one, or load the demo cameras from Settings > Simulation." if can_edit else ""))

with tabs[1]:
    cons = cs.consumption()
    if cons.empty or cons["total_gb"].sum() == 0:
        st.info("No stored footage yet. Generate footage from Settings > Simulation.")
    else:
        st.plotly_chart(charts.camera_bar(cons), key="cons")
        st.dataframe(cons.round(1), hide_index=True)

if can_edit:
    with tabs[2]:
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Camera name", key="a_name")
        loc = c2.text_input("Location", key="a_loc")
        code = c3.text_input("Camera ID", value=cs.next_code(), key="a_code")
        c1, c2, c3, c4 = st.columns(4)
        res = c1.selectbox("Resolution", RESOLUTIONS, index=1, key="a_res")
        fps = c2.number_input("FPS", 1, 60, 30, key="a_fps")
        codec = c3.selectbox("Compression", CODECS, index=1, key="a_codec")
        mode = c4.selectbox("Recording mode", RECORDING_MODES, key="a_mode")
        c1, c2, c3, c4 = st.columns(4)
        pri = c1.selectbox("Priority", PRIORITIES, index=1, key="a_pri")
        ret = c2.number_input("Retention (days)", 1, 3650, 30, key="a_ret")
        hrs = c3.number_input("Recording hours/day", 1.0, 24.0, 24.0, key="a_hrs")
        tier = c4.selectbox("Default tier", TIERS, key="a_tier")
        est = ce.effective_bitrate(res, fps, codec, fac)
        manual = st.checkbox("Enter bitrate manually", key="a_manual")
        br = st.number_input("Bitrate (Mbps)", 0.1, 100.0, float(est), key=f"a_br_{est}") if manual else est
        e = ce.camera_storage(br, hrs, mode, ss.mode_factors())
        st.info(f"Bitrate **{br:.2f} Mbps** → **{e['gb_day']:.1f} GB/day** · **{e['gb_month'] / 1000:.2f} TB/month** · "
                f"retention {ret} d needs **{e['gb_day'] * ret / 1000:.2f} TB**")
        if st.button("Add camera", type="primary"):
            try:
                new = cs.add_camera(user, dict(camera_code=code, name=name, location=loc, resolution=res, fps=int(fps),
                                               compression=codec, bitrate_mbps=float(br), recording_mode=mode,
                                               recording_hours=float(hrs), priority=pri, retention_days=int(ret), default_tier=tier))
                flash(f"Camera {new} added."); st.rerun()
            except Exception as ex:
                st.error(str(ex))

    with tabs[3]:
        if not cams:
            st.info("Nothing to edit.")
        else:
            sel = st.selectbox("Camera", cams, format_func=lambda c: f"{c['camera_code']} – {c['name']} ({c['location']})")
            k = sel["camera_id"]
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Name", sel["name"], key=f"e_n{k}")
            loc = c2.text_input("Location", sel["location"], key=f"e_l{k}")
            status = c3.selectbox("Status", ["Active", "Inactive"], index=["Active", "Inactive"].index(sel["status"]), key=f"e_s{k}")
            c1, c2, c3, c4 = st.columns(4)
            res = c1.selectbox("Resolution", RESOLUTIONS, index=RESOLUTIONS.index(sel["resolution"]), key=f"e_r{k}")
            fps = c2.number_input("FPS", 1, 60, int(sel["fps"]), key=f"e_f{k}")
            codec = c3.selectbox("Compression", CODECS, index=CODECS.index(sel["compression"]), key=f"e_c{k}")
            mode = c4.selectbox("Mode", RECORDING_MODES, index=RECORDING_MODES.index(sel["recording_mode"]), key=f"e_m{k}")
            c1, c2, c3, c4 = st.columns(4)
            pri = c1.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(sel["priority"]), key=f"e_p{k}")
            ret = c2.number_input("Retention (days)", 1, 3650, int(sel["retention_days"]), key=f"e_t{k}")
            hrs = c3.number_input("Hours/day", 1.0, 24.0, float(sel["recording_hours"]), key=f"e_h{k}")
            br = c4.number_input("Bitrate (Mbps)", 0.1, 100.0, float(sel["bitrate_mbps"]), key=f"e_b{k}")
            b1, b2 = st.columns(2)
            if b1.button("Save changes", type="primary"):
                try:
                    cs.update_camera(user, k, dict(name=name, location=loc, resolution=res, fps=int(fps), compression=codec,
                                                   bitrate_mbps=float(br), recording_mode=mode, recording_hours=float(hrs),
                                                   priority=pri, retention_days=int(ret), status=status,
                                                   default_tier=sel["default_tier"] or "Hot"))
                    flash("Saved."); st.rerun()
                except Exception as ex:
                    st.error(str(ex))
            if b2.button("Remove camera"):
                flash(f"Camera {cs.remove_camera(user, k)}."); st.rerun()
