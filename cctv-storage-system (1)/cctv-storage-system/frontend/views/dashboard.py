import streamlit as st
from backend.auth import session
from frontend.components import charts
from frontend.components.ui import fmt_gb, header, sev
from backend.services import alert_service, backup_service, camera_service, forecast_service, settings_service as ss, storage_service

user = session.require("dashboard")
clock = ss.get_clock()
header("Storage Monitoring Dashboard", f"Simulation time {clock:%Y-%m-%d %H:%M} · figures are computed from footage metadata")

if st.button("🔄 Re-evaluate alerts"):
    alert_service.sync(clock)

s = ss.get_all()
stt = storage_service.pool_state()
fc = forecast_service.compute(clock)
bk = backup_service.status(clock)
cams = camera_service.list_cameras()
active = [c for c in cams if c["status"] == "Active"]
open_alerts = alert_service.list_alerts(status="Open")
tiers = {t["name"]: t for t in stt["tiers"]}

c = st.columns(6)
c[0].metric("Total storage", fmt_gb(stt["capacity_gb"]))
c[1].metric("Used", fmt_gb(stt["used_gb"]))
c[2].metric("Free", fmt_gb(stt["free_gb"]))
c[3].metric("Utilization", f"{stt['util_pct']:.1f}%")
c[4].metric("Cameras", f"{len(active)} active / {len(cams)}")
c[5].metric("Daily generation", fmt_gb(fc["daily_generation_gb"]) + "/day")

c = st.columns(6)
for i, n in enumerate(("Hot", "Warm", "Cold")):
    c[i].metric(f"{n} storage", fmt_gb(tiers[n]["used_gb"]), f"{tiers[n]['util']:.0f}% of {tiers[n]['capacity_tb']:g} TB", delta_color="off")
c[3].metric("Archived footage", f"{stt['arch_clips']:,} clips", fmt_gb(stt["arch_gb"]), delta_color="off")
c[4].metric("Deleted footage", f"{stt['del_clips']:,} clips", fmt_gb(stt["del_gb"]), delta_color="off")
r = fc["result"]
d80 = "n/a" if not r.get("ok") or r.get("days_to_80") is None else f"{r['days_to_80']:.0f} days"
c[5].metric("Days to 80% full", d80, "linear trend" if r.get("ok") else "needs ≥7 days data", delta_color="off")

c = st.columns(4)
if bk["last_success"]:
    c[0].metric("Last good backup", f"{bk['age_hours']:.1f} h ago", "RPO met" if bk["rpo_ok"] else "RPO VIOLATED",
                delta_color="normal" if bk["rpo_ok"] else "inverse")
else:
    c[0].metric("Last good backup", "none", "RPO VIOLATED", delta_color="inverse")
c[1].metric("Estimated RTO", "n/a" if bk["est_rto_hours"] is None else f"{bk['est_rto_hours']:.1f} h",
            f"target {s['rto_hours']} h", delta_color="off")
c[2].metric("Active alerts", len(open_alerts))
c[3].metric("Monthly storage cost (est.)", f"{stt['monthly_cost']:,.0f}",
            f"{stt['all_hot_cost'] - stt['monthly_cost']:,.0f} saved vs all-Hot", delta_color="normal")

demo_videos = {
    "North Entrance": "https://videos.pexels.com/video-files/3045163/3045163-hd_1920_1080_25fps.mp4",
    "Car Park": "https://videos.pexels.com/video-files/3195394/3195394-hd_1920_1080_25fps.mp4",
    "Warehouse Gate": "https://videos.pexels.com/video-files/3860251/3860251-hd_1920_1080_25fps.mp4",
}
if "demo_video" not in st.session_state:
    st.session_state["demo_video"] = next(iter(demo_videos))

st.divider()
st.subheader("Demo footage")
st.caption("Public sample clips are shown only to make the dashboard feel closer to a live CCTV monitor. The project still stores metadata only, not raw video files.")
video_choice = st.selectbox("Camera feed preview", list(demo_videos.keys()), index=list(demo_videos.keys()).index(st.session_state["demo_video"]))
if video_choice != st.session_state["demo_video"]:
    st.session_state["demo_video"] = video_choice
st.video(demo_videos[st.session_state["demo_video"]], format="video/mp4")
st.markdown(
    f"Previewing **{st.session_state['demo_video']}**. This feed is a demonstration of how a real CCTV stream would be tagged, retained, and moved across hot/warm/cold tiers based on policy. "
    "The system still makes storage decisions from metadata, not by storing raw video files."
)

st.divider()
insight_cols = st.columns(3)
utilization = stt["util_pct"]
if utilization >= 80:
    insight_cols[0].warning("High utilization: review lifecycle actions and consider moving older footage to lower tiers.")
elif utilization >= 60:
    insight_cols[0].info("Storage is approaching the warning zone; keep an eye on tier pressure and retention review.")
else:
    insight_cols[0].success("Storage is healthy; current capacity headroom is above the warning threshold.")

if not bk["last_success"]:
    insight_cols[1].error("No recent successful backup was detected. RPO is at risk and the backup policy should be reviewed.")
else:
    insight_cols[1].success(f"Last successful backup was {bk['age_hours']:.1f} hours ago and is within the configured recovery target.")

if open_alerts.empty:
    insight_cols[2].success("No open alerts right now; the environment is stable.")
else:
    insight_cols[2].warning(f"{len(open_alerts)} open alert(s) require attention; review the alert list below.")

st.divider()
l, rr = st.columns(2)
l.plotly_chart(charts.tier_donut(stt["tiers"]), key="donut")
rr.plotly_chart(charts.utilization_timeline(storage_service.metrics_history(), stt["capacity_gb"], s), key="timeline")
l, rr = st.columns(2)
cons = camera_service.consumption()
if not cons.empty:
    l.plotly_chart(charts.camera_bar(cons), key="camera")
rr.plotly_chart(charts.tier_capacity(stt["tiers"]), key="tiercap")

st.subheader("Active alerts")
if open_alerts.empty:
    st.success("No open alerts.")
else:
    v = open_alerts[["alert", "created_at", "severity", "category", "description", "recommended_action"]].head(8).copy()
    v["severity"] = v["severity"].map(sev)
    st.dataframe(v, hide_index=True)
