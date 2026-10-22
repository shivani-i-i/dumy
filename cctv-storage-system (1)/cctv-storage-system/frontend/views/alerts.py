import streamlit as st
from backend.auth import session
from backend.auth.rbac import has_permission
from frontend.components.ui import SEV_ICON, header
from backend.services import alert_service

user = session.require("alerts_view")
can_resolve = has_permission(user["role"], "resolve_alerts")
header("Alerts & Notifications", "Conditions are de-duplicated; alerts clear automatically when the condition disappears.")
c1, c2 = st.columns([1, 3])
if c1.button("🔄 Re-evaluate now"):
    st.toast(f"{alert_service.sync()} new alert(s)")
status = c2.radio("Show", ["Open", "Resolved", "All"], horizontal=True)
sevs = st.multiselect("Severity", list(SEV_ICON), default=list(SEV_ICON))
df = alert_service.list_alerts(None if status == "All" else status, sevs)
if df.empty:
    st.success("No alerts match.")
else:
    for _, a in df.head(100).iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"{SEV_ICON[a['severity']]} **{a['alert']}** · {a['severity']} · *{a['category']}* · {a['created_at']:%Y-%m-%d %H:%M} · {a['status']}")
            c1.write(a["description"])
            c1.caption("Recommended action: " + str(a["recommended_action"]))
            if a["status"] == "Open" and can_resolve:
                if c2.button("Mark resolved", key=f"r{a['alert_id']}"):
                    alert_service.resolve(user, int(a["alert_id"])); st.rerun()
            elif a["status"] == "Resolved":
                c2.caption(f"by {a['resolved_by']}")
