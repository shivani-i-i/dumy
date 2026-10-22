import streamlit as st
from backend.auth import session
from frontend.components.ui import fmt_gb, header
from backend.services import footage_service as fs, storage_service

session.require("archive_view")
header("Archive & Retention", "Cold-tier archive, items awaiting deletion, deleted records and protected evidence.")
stt = storage_service.pool_state()
m = st.columns(4)
m[0].metric("Archived (Cold)", f"{stt['arch_clips']:,}", fmt_gb(stt["arch_gb"]), delta_color="off")
m[1].metric("Marked for deletion", f"{stt['marked_clips']:,}", fmt_gb(stt["marked_gb"]), delta_color="off")
m[2].metric("Deleted", f"{stt['del_clips']:,}", fmt_gb(stt["del_gb"]), delta_color="off")
t1, t2, t3, t4 = st.tabs(["Archived", "Marked for deletion", "Protected evidence", "Deleted log"])
cols = lambda d: d.drop(columns=["footage_id"]) if not d.empty else d
with t1:
    st.dataframe(cols(fs.search(archive_status="Archived", deletion_status=["Retained", "Marked"], limit=500)), hide_index=True)
with t2:
    st.dataframe(cols(fs.search(deletion_status=["Marked"], limit=500)), hide_index=True)
with t3:
    d = fs.search(incident_only=True, deletion_status=["Retained", "Marked"], limit=500)
    st.caption("These records are never auto-deleted; the database also blocks deletion with a trigger.")
    st.dataframe(cols(d), hide_index=True)
with t4:
    st.dataframe(cols(fs.search(deletion_status=["Deleted"], limit=500)), hide_index=True)
