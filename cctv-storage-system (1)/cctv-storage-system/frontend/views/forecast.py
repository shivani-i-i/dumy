import streamlit as st
from backend.auth import session
from frontend.components import charts
from frontend.components.ui import fmt_gb, header
from backend.services import forecast_service

session.require("forecast_view")
header("Capacity Forecast", "Statistical trend forecasting: ordinary least-squares line fitted to daily used-storage history (not AI).")
c = forecast_service.compute()
r, hist = c["result"], c["history"]
if not r["ok"]:
    st.warning(r["message"] + " Use Settings → Simulation to generate history.")
    st.stop()
(st.error if r["days_to_80"] == 0 else st.info)(f"**{r['message']}**")
m = st.columns(4)
m[0].metric("Daily growth", fmt_gb(r["daily_gb"])); m[1].metric("Weekly growth", fmt_gb(r["weekly_gb"]))
m[2].metric("Monthly growth", fmt_gb(r["monthly_gb"])); m[3].metric("Fit quality R²", f"{r['r2']:.3f}")
m = st.columns(4)
fmt = lambda d: "—" if d is None else f"{d:%Y-%m-%d}"
m[0].metric("80% reached on", fmt(r["date_80"])); m[1].metric("Full (100%) on", fmt(r["date_100"]))
m[2].metric("Current utilization", f"{r['current_util']:.1f}%"); m[3].metric("Data points used", r["points"])
st.plotly_chart(charts.forecast_chart(hist, r["line"], c["capacity_gb"]), key="fc")
if "steady_msg" in r:
    (st.error if r["steady_exceeds"] else st.success)("**Retention-aware steady state:** " + r["steady_msg"])
st.caption("Why both? A straight line keeps rising, but retention deletes old footage so real usage plateaus near "
           "Σ(daily GB × retention days) + protected evidence. Showing both avoids false 'disk full' predictions "
           "and also catches policies that can never fit. R² near 1 = the trend is very linear; low R² = treat with caution.")
