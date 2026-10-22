"""Small reusable UI helpers."""
import streamlit as st

SEV_ICON = {"Critical": "🔴", "High": "🟠", "Warning": "🟡", "Info": "🔵"}


def inject_css():
    st.markdown("""<style>
    .block-container {padding-top: 1.6rem;}
    h1, h2, h3 {letter-spacing: -0.01em;}
    [data-testid="stMetric"] {background: rgba(128,128,128,0.08); border: 1px solid rgba(128,128,128,0.2);
        padding: 10px 14px; border-radius: 8px;}
    [data-testid="stMetricLabel"] {opacity: .75;}
    .why {border-left: 3px solid #4c78a8; padding: 6px 12px; margin: 6px 0; background: rgba(76,120,168,0.08);
        border-radius: 0 6px 6px 0; font-size: 0.92rem;}
    .sim {border: 1px dashed #b07d00; color: #b07d00; padding: 8px 12px; border-radius: 6px; font-size: .9rem;}
    </style>""", unsafe_allow_html=True)


def flash(msg, kind="success"):
    """Message that survives st.rerun()."""
    st.session_state["_flash"] = (kind, msg)


def header(title, caption=None):
    st.title(title)
    if caption:
        st.caption(caption)
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind)(msg)


def sim_notice(text):
    st.markdown(f'<div class="sim">⚠️ {text}</div>', unsafe_allow_html=True)


def why(text):
    st.markdown(f'<div class="why">{text}</div>', unsafe_allow_html=True)


def fmt_gb(gb):
    return f"{gb / 1000:,.2f} TB" if abs(gb) >= 1000 else f"{gb:,.1f} GB"


def sev(s):
    return f"{SEV_ICON.get(s, '')} {s}"


def util_bar(label, pct, detail=""):
    st.write(f"**{label}** — {pct:.1f}% {detail}")
    st.progress(min(max(pct, 0), 100) / 100)
