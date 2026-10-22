import pandas as pd
import streamlit as st
from backend.auth import session
from backend.auth.rbac import has_permission
from frontend.components import charts
from frontend.components.ui import flash, header, sim_notice
from backend.engines import raid_engine as rd
from backend.services import raid_service

user = session.require("raid_view")
can_edit = has_permission(user["role"], "edit_raid")
header("RAID Management")
sim_notice("This module is a calculation and simulation tool. It does not configure hardware or software RAID. "
           "RAID protects against disk failure only — it is <b>not</b> a backup.")

t1, t2, t3, t4 = st.tabs(["Level reference", "Calculator", "Recommender", "Current array"])

with t1:
    st.dataframe(pd.DataFrame([{"Level": v["label"], "Min disks": v["min"], "Fault tolerance": v["tolerance"],
                                "Usable capacity": f, "Performance": v["perf"], "Notes": v["note"]}
                               for (k, v), f in zip(rd.RAID_INFO.items(), ["N × C", "C (N-way mirror)", "(N-1) × C", "(N-2) × C", "(N/2) × C"])]),
                 hide_index=True)

with t2:
    c1, c2 = st.columns(2)
    n = c1.number_input("Number of disks", 2, 64, 8)
    cap = c2.number_input("Disk capacity (TB)", 0.5, 30.0, 4.0)
    rows = []
    for lv in rd.LEVELS:
        c = rd.calculate(lv, int(n), cap)
        rows.append({"Level": rd.RAID_INFO[lv]["label"], "Valid": "✅" if c["valid"] else "❌ " + c["message"],
                     "Raw (TB)": c["raw_tb"], "Usable (TB)": round(c["usable_tb"], 2),
                     "Redundancy overhead (TB)": round(c.get("redundancy_tb", 0), 2),
                     "Efficiency (%)": round(c["efficiency"] * 100, 1), "Fault tolerance (disks)": c["fault_tolerance"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True)

with t3:
    c1, c2 = st.columns(2)
    need = c1.number_input("Required usable capacity (TB)", 1.0, 1000.0, 20.0)
    dsk = c2.number_input("Disk size (TB)", 1.0, 30.0, 4.0, key="rec_d")
    goal = st.radio("Priority", ["Lowest cost", "Balanced", "High availability + fault tolerance"], index=2, horizontal=True)
    c1, c2 = st.columns(2)
    wh = c1.checkbox("Write-heavy workload (many high-bitrate cameras)")
    bf = c2.checkbox("Budget is flexible")
    rec = rd.recommend(need, dsk, goal, wh, bf)
    st.success(f"Recommendation: **{rd.RAID_INFO[rec['level']]['label']}** with **{rec['disks']} × {dsk:g} TB** disks "
               f"→ {rec['calc']['usable_tb']:.1f} TB usable ({rec['calc']['efficiency'] * 100:.0f}% efficiency)")
    for r in rec["reasons"]:
        st.write("• " + r)
    st.dataframe(pd.DataFrame(rec["alternatives"]), hide_index=True)
    st.plotly_chart(charts.raid_compare(rec["alternatives"]), key="raidcmp")

with t4:
    cfg = raid_service.get_config()
    calc = rd.calculate(cfg["raid_level"], cfg["disk_count"], cfg["disk_size_tb"])
    m = st.columns(5)
    m[0].metric("Level", rd.RAID_INFO[cfg["raid_level"]]["label"])
    m[1].metric("Disks", f"{cfg['disk_count']} × {cfg['disk_size_tb']:g} TB")
    m[2].metric("Raw / Usable", f"{calc['raw_tb']:.0f} / {calc['usable_tb']:.0f} TB")
    m[3].metric("Failed disks", cfg["failed_disks"], f"tolerates {calc['fault_tolerance']}", delta_color="off")
    m[4].metric("Status", cfg["status"])
    if cfg["status"] == "Degraded":
        st.warning("Array is DEGRADED: one more failure than the tolerance loses data. Replace the disk and rebuild.")
    elif cfg["status"] == "Failed":
        st.error("Array FAILED: data unavailable. Restore from backup (see Backup & Recovery).")
    st.caption(f"Pool capacity is derived from RAID usable capacity ({cfg['total_capacity_tb']:.1f} TB). "
               f"Estimated rebuild of one disk: ~{rd.rebuild_hours(cfg['raid_level'], cfg['disk_size_tb'])} h.")
    if can_edit:
        st.markdown("##### Administration (simulation)")
        b = st.columns(3)
        if b[0].button("💥 Simulate disk failure"):
            flash(f"Array is now {raid_service.simulate_failure(user)}", "warning"); st.rerun()
        if b[1].button("🔧 Replace disk & rebuild"):
            flash(f"Rebuild simulated (~{raid_service.rebuild(user)} h)"); st.rerun()
        with st.expander("Change RAID configuration / add disks"):
            lv = st.selectbox("Level", rd.LEVELS, index=rd.LEVELS.index(cfg["raid_level"]), format_func=lambda x: rd.RAID_INFO[x]["label"])
            nn = st.number_input("Disks", 2, 64, int(cfg["disk_count"]), key="cfg_n")
            dd = st.number_input("Disk size (TB)", 0.5, 30.0, float(cfg["disk_size_tb"]), key="cfg_d")
            if st.button("Apply configuration"):
                try:
                    raid_service.save_config(user, lv, int(nn), dd); flash("Configuration saved."); st.rerun()
                except Exception as ex:
                    st.error(str(ex))
            add = st.number_input("Add disks (capacity expansion)", 1, 16, 2)
            if st.button("Add disks"):
                try:
                    raid_service.add_disks(user, int(add)); flash("Disks added."); st.rerun()
                except Exception as ex:
                    st.error(str(ex))
    else:
        st.info("Only an Admin can change the RAID configuration.")
