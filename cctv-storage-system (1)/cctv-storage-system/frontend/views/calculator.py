import pandas as pd
import streamlit as st
from backend.auth import session
from frontend.components import charts
from frontend.components.ui import header, sim_notice
from backend.config.constants import CODECS, RECORDING_MODES, RESOLUTIONS
from backend.engines import capacity_engine as ce, compression_engine as comp, raid_engine as rd
from backend.services import camera_service, settings_service as ss

user = session.require("calculator")
header("Storage Capacity Calculator", "Bitrate-based sizing: GB/hour = Mbps × 3600 ÷ 8 ÷ 1000")
s = ss.get_all()
fac, mfac = ss.codec_factors(s), ss.mode_factors(s)
t1, t2, t3 = st.tabs(["Calculator", "From registered cameras", "Compression analysis"])

with t1:
    c1, c2, c3, c4 = st.columns(4)
    n = c1.number_input("Number of cameras", 1, 1000, 10)
    res = c2.selectbox("Resolution", RESOLUTIONS, index=1)
    fps = c3.number_input("FPS", 1, 60, 30)
    codec = c4.selectbox("Compression", CODECS, index=1)
    c1, c2, c3, c4 = st.columns(4)
    hours = c1.number_input("Recording hours/day", 1.0, 24.0, 24.0)
    ret = c2.number_input("Retention days", 1, 3650, 30)
    mode = c3.selectbox("Recording mode", RECORDING_MODES)
    est = ce.effective_bitrate(res, fps, codec, fac)
    manual = c4.checkbox(f"Override bitrate (estimate {est} Mbps)")
    br = st.number_input("Bitrate (Mbps)", 0.1, 100.0, float(est), key=f"br{est}") if manual else None
    ovh = st.slider("File-system / metadata overhead (%)", 0, 30, int(s["overhead_pct"]))
    head = st.slider("Headroom (%)", 0, 50, int(s["headroom_pct"]))
    r = ce.manual_calculation(int(n), res, int(fps), codec, hours, int(ret), mode, br, ovh, head, fac, mfac)
    m = st.columns(5)
    m[0].metric("GB / camera / hour", f"{r['gb_hour']:.2f}")
    m[1].metric("GB / camera / day", f"{r['gb_day']:.1f}")
    m[2].metric("Total daily", f"{r['total_daily_gb']:,.0f} GB")
    m[3].metric("Total monthly", f"{r['total_monthly_gb'] / 1000:,.2f} TB")
    m[4].metric("Recommended capacity", f"{r['recommended_tb']:,.2f} TB")
    st.markdown("##### Worked calculation")
    st.table(pd.DataFrame(r["steps"], columns=["Step", "Formula / substitution", "Result"]).set_index("Step"))
    st.caption("Decimal units (1 TB = 1000 GB) as used by disk vendors. FPS scaling is linear — a simplification; "
               "real codecs scale sub-linearly. Bitrate/codec figures are typical vendor assumptions, not guarantees.")
    st.markdown("##### Translate to RAID disks")
    d = st.number_input("Disk size (TB)", 1.0, 30.0, 4.0, key="calc_disk")
    rows = []
    for lv in rd.LEVELS:
        nn = rd.disks_needed(lv, r["recommended_tb"], d)
        if nn:
            cc = rd.calculate(lv, nn, d)
            rows.append({"Level": rd.RAID_INFO[lv]["label"], "Disks": nn, "Raw (TB)": round(cc["raw_tb"], 1),
                         "Usable (TB)": round(cc["usable_tb"], 1), "Efficiency (%)": round(cc["efficiency"] * 100, 1)})
    st.dataframe(pd.DataFrame(rows), hide_index=True)

with t2:
    cams = camera_service.list_cameras(active_only=True)
    if not cams:
        st.info("No active cameras.")
    else:
        p = ce.plan([dict(c, label=c["camera_code"]) for c in cams], s["overhead_pct"], s["headroom_pct"], mfac)
        m = st.columns(4)
        m[0].metric("Daily", f"{p['daily_gb']:,.0f} GB")
        m[1].metric("Monthly", f"{p['monthly_gb'] / 1000:,.2f} TB")
        m[2].metric("Retention need", f"{p['base_gb'] / 1000:,.2f} TB")
        m[3].metric("Recommended", f"{p['recommended_tb']:,.2f} TB")
        df = pd.DataFrame(p["rows"]).rename(columns={"camera": "Camera", "gb_hour": "GB/h", "gb_day": "GB/day", "gb_month": "GB/month",
                                                     "retention_days": "Retention (d)", "retention_gb": "Retention (GB)"})
        st.dataframe(df.round(2), hide_index=True)
        st.write(f"Retention {p['base_gb'] / 1000:.2f} TB + overhead {p['overhead_gb'] / 1000:.2f} TB "
                 f"+ headroom {p['headroom_gb'] / 1000:.2f} TB = **{p['recommended_tb']:.2f} TB usable**")

with t3:
    sim_notice("Estimated savings use configurable codec factors (Settings). No video is re-encoded.")
    c1, c2, c3, c4 = st.columns(4)
    br0 = c1.number_input("Camera bitrate (Mbps)", 0.1, 100.0, 4.0)
    cur = c2.selectbox("Codec of that bitrate", CODECS, index=0, key="cc")
    ncam = c3.number_input("Cameras", 1, 1000, 10, key="cn")
    hrs2 = c4.number_input("Hours/day", 1.0, 24.0, 24.0, key="ch")
    rows = comp.compare(br0, cur, hrs2, "Continuous", int(ncam), 30, fac)
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.plotly_chart(charts.compression_bar(rows, "Saving vs H.264 (%)"), key="compchart")
    h265 = next(r for r in rows if r["Codec"] == "H.265")
    st.success(f"H.265 vs H.264 for {ncam} cameras: saves about **{h265['Saving vs H.264 (%)']:.0f}%** "
               f"({rows[0]['GB / day'] - h265['GB / day']:,.0f} GB/day).")
