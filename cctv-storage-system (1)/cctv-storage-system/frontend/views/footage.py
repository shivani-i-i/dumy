from datetime import date, timedelta

import streamlit as st
from backend.auth import session
from backend.auth.rbac import has_permission
from frontend.components.ui import flash, header, why
from backend.config.constants import IMPORTANCE, TIERS
from backend.services import camera_service, footage_service as fs, storage_service

user = session.require("footage_view")
can_flag = has_permission(user["role"], "flag_footage")
can_req = has_permission(user["role"], "request_flag")
header("Footage Metadata", "Searchable CCTV footage records (metadata only — no video files are stored).")

cams = camera_service.list_cameras()
with st.expander("Search filters", expanded=True):
    c1, c2, c3 = st.columns(3)
    sel_c = c1.multiselect("Camera", [c["camera_code"] for c in cams])
    loc = c2.text_input("Location contains")
    use_dates = c3.checkbox("Filter by date", value=False)
    d1 = d2 = None
    if use_dates:
        a, b = c3.columns(2)
        d1 = a.date_input("From", date.today() - timedelta(days=30)); d2 = b.date_input("To", date.today())
    c1, c2, c3 = st.columns(3)
    imp = c1.multiselect("Importance", IMPORTANCE)
    tier = c2.multiselect("Storage tier", TIERS)
    inc = c3.checkbox("Incident / evidence only")
    show_deleted = st.checkbox("Include deleted records", value=False)

df = fs.search(sel_c or None, loc or None, d1, d2, imp or None, inc, tier or None,
               deletion_status=None if show_deleted else ["Retained", "Marked"])
st.caption(f"{len(df):,} record(s) (max 1000 shown)")
st.dataframe(df.drop(columns=["footage_id"]) if not df.empty else df, hide_index=True)

if not df.empty:
    st.subheader("Clip details")
    sel = st.selectbox("Select a clip", df.head(500)["footage_id"], format_func=lambda i: f"F-{i:06d}")
    f = fs.get_detail(int(sel))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Camera", f"{f['camera_code']} · {f['location']}")
    c2.metric("Size", f"{f['size_gb']:.2f} GB")
    c3.metric("Tier", f["tier"])
    c4.metric("Class", f["importance"] + (" + hold" if f["legal_hold"] else ""))
    exp_txt = "never (legal hold)" if f["legal_hold"] else f"{f['retention_expiry']:%Y-%m-%d}"
    st.write(f"Recorded {f['start_time']:%Y-%m-%d %H:%M} → {f['end_time']:%H:%M} · {f['resolution']} {f['compression']} · "
             f"retention expiry **{exp_txt}** · {f['archive_status']} · {f['deletion_status']}")
    hist = storage_service.decisions_for(int(sel))
    if not hist.empty:
        st.markdown("**Why is it where it is?**")
        for _, r in hist.iterrows():
            why(f"{r['decided_at']:%Y-%m-%d}: {r['reason_text']}")

    if can_flag:
        st.markdown("##### Classify footage")
        c1, c2 = st.columns(2)
        new = c1.selectbox("Importance", IMPORTANCE, index=IMPORTANCE.index(f["importance"]), key=f"imp{sel}")
        hold = c2.checkbox("Legal hold (never expires)", value=f["legal_hold"], key=f"hold{sel}")
        note = st.text_input("Incident note", f["incident_note"] or "", key=f"note{sel}")
        if st.button("Save classification", type="primary"):
            try:
                exp = fs.set_importance(user, int(sel), new, note, hold)
                flash("Saved. Legal hold applied." if hold else f"Saved. New retention expiry: {exp:%Y-%m-%d}")
                st.rerun()
            except Exception as ex:
                st.error(str(ex))
    elif can_req:
        st.markdown("##### Request incident classification")
        st.caption("Viewers cannot change retention. Your request is sent to the Storage Manager / Admin as an alert.")
        req = st.selectbox("Requested class", ["Important", "Incident", "Critical Evidence"])
        note = st.text_input("Reason")
        if st.button("Send request"):
            try:
                fs.request_flag(user, int(sel), req, note); st.success("Request sent.")
            except Exception as ex:
                st.error(str(ex))
