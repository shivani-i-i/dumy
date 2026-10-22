import streamlit as st
from backend.auth import session
from frontend.components.ui import header
from backend.services import audit_service

session.require("audit_view")
header("Audit Logs", "Append-only record of security and storage-relevant actions.")
c1, c2 = st.columns(2)
u = c1.text_input("Filter by username")
a = c2.selectbox("Filter by action", [""] + audit_service.distinct_actions())
df = audit_service.fetch(u or None, a or None)
st.caption(f"{len(df)} entries (newest first, max 500)")
st.dataframe(df, hide_index=True)
st.download_button("Download CSV", df.to_csv(index=False), "audit_log.csv", "text/csv")
