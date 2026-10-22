import pandas as pd
import streamlit as st
from backend.auth import session
from backend.auth.rbac import has_permission
from frontend.components import charts
from frontend.components.ui import flash, fmt_gb, header, why
from backend.engines import lifecycle_engine as le
from backend.services import alert_service, settings_service as ss, storage_service as sv

user = session.require("tiers_view")
can_run = has_permission(user["role"], "run_lifecycle")
can_cfg = has_permission(user["role"], "edit_tiers")
header("Storage Tiers & Lifecycle Engine", "Rule-based Storage Optimization Engine (not AI): every decision stores the rule and numbers behind it.")
s = ss.get_all()
stt = sv.pool_state()
cfg = sv.lifecycle_config(s)
t1, t2, t3, t4 = st.tabs(["Tier overview", "Lifecycle engine", "Optimization recommendations", "Decision log"])

with t1:
    cols = st.columns(3)
    for col, t in zip(cols, stt["tiers"]):
        col.metric(f"{t['name']} tier", fmt_gb(t["used_gb"]), f"{t['util']:.0f}% of {t['capacity_tb']:g} TB", delta_color="off")
        col.caption(f"{t['access_speed']} · cost {t['cost_per_tb_month']:g}/TB/month · {t['clips']:,} clips")
        col.progress(min(t["util"], 100) / 100)
    st.plotly_chart(charts.tier_capacity(stt["tiers"]), key="tcap")
    st.info(f"Estimated monthly storage cost **{stt['monthly_cost']:,.0f}** versus **{stt['all_hot_cost']:,.0f}** if everything "
            f"sat in Hot → tiering saves **{stt['all_hot_cost'] - stt['monthly_cost']:,.0f}** per month (relative cost units).")
    sc = sum(t["capacity_tb"] for t in stt["tiers"])
    if abs(sc - stt["pool"]["total_capacity_tb"]) > 0.01:
        st.warning(f"Tier capacities sum to {sc:g} TB but the pool (RAID usable) is {stt['pool']['total_capacity_tb']:g} TB.")
    if can_cfg:
        with st.expander("Edit tier configuration (Admin)"):
            for t in stt["tiers"]:
                c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
                c1.write(f"**{t['name']}**")
                cap = c2.number_input("Capacity (TB)", 0.1, 1000.0, float(t["capacity_tb"]), key=f"cap{t['tier_id']}")
                cost = c3.number_input("Cost/TB/month", 0.0, 1000.0, float(t["cost_per_tb_month"]), key=f"cost{t['tier_id']}")
                if c4.button("Save", key=f"sv{t['tier_id']}"):
                    sv.update_tier(user, t["tier_id"], cap, cost, t["access_speed"]); st.rerun()

with t2:
    st.markdown("**Current rules** (change them in Settings → Lifecycle)")
    st.markdown(f"""
| Rule | Condition | Result |
|---|---|---|
| R1 | Incident / Critical Evidence / legal hold | Keep in Hot/Warm · never auto-deleted |
| R2 | Age ≥ retention expiry (unprotected) | Mark for deletion |
| R3 | Age ≤ hot window (**{cfg.hot_window:g} d** × priority: {', '.join(f'{k} {v:g}×' for k, v in cfg.priority_mult.items())}) | Hot |
| R4 | Age ≤ warm window (**{cfg.warm_window:g} d**) | Warm |
| R5 | Older | Cold (archive) |
| Pressure | Pool > **{cfg.pressure_l1:g}%** / > **{cfg.pressure_l2:g}%** | Hot windows shrink ×{cfg.shrink:g} |
""")
    st.write(f"Pool utilization now: **{stt['util_pct']:.1f}%**")
    whatif = st.checkbox("What-if: override utilization for the dry run")
    ov = st.slider("Simulated utilization (%)", 0, 100, int(stt["util_pct"])) if whatif else None
    res = sv.run_lifecycle(user, apply=False, util_override=ov) if can_run else None
    if res is not None:
        c = res["counts"]
        m = st.columns(5)
        m[0].metric("Pending decisions", res["count"])
        m[1].metric("→ Warm", c["to_warm"]); m[2].metric("→ Cold", c["to_cold"])
        m[3].metric("Mark for deletion", c["marked"]); m[4].metric("Pressure level", res["pressure"])
        if res["decisions"].empty:
            st.success("Dry run: nothing to change. The storage layout already satisfies every rule (idempotent).")
        else:
            st.markdown("##### Dry run — what would change and why")
            st.dataframe(res["decisions"].head(300), hide_index=True)
            for _, r in res["decisions"].head(3).iterrows():
                why(r["Why"])
        b = st.columns(3)
        if b[0].button("▶ Apply lifecycle now", type="primary"):
            r2 = sv.run_lifecycle(user, apply=True)
            flash(f"Applied {r2['count']} decisions."); st.rerun()
        if b[1].button("🗑 Delete expired (unprotected) footage"):
            n, gb = sv.purge_marked(user)
            alert_service.sync()
            flash(f"Deleted {n} clips ({gb:.1f} GB). Protected evidence is never deleted."); st.rerun()
    else:
        st.info("Only Admin / Storage Manager can run the engine.")

with t3:
    recs = sv.recommendations()
    if not recs:
        st.success(f"Utilization ({stt['util_pct']:.1f}%) is below the warning threshold ({s['util_warn']}%) — no optimization needed.")
    else:
        st.warning(f"Pool utilization is {stt['util_pct']:.1f}%. Ranked recommendations (largest saving first):")
        for r in recs:
            st.markdown(f"**{r['rank']}. {r['action']}**")
            st.caption(f"Estimated saving: {fmt_gb(r['saving_gb'])} → utilization ≈ {r['util_after']:.1f}%")
            why(r["why"])
        if can_run:
            b = st.columns(2)
            if b[0].button("Apply: simulate H.264 → H.265 re-compression (Warm/Cold)"):
                n, gb = sv.apply_compression(user); flash(f"{n} clips re-compressed (simulated), ~{gb:.1f} GB freed."); st.rerun()
            if b[1].button("Apply: run lifecycle under high-pressure profile"):
                r2 = sv.run_lifecycle(user, apply=True, util_override=max(stt["util_pct"], cfg.pressure_l2 + 0.1))
                flash(f"Applied {r2['count']} decisions."); st.rerun()

with t4:
    d = sv.recent_decisions()
    st.dataframe(d, hide_index=True) if not d.empty else st.info("No decisions yet.")
