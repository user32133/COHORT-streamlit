import streamlit as st

st.set_page_config(
    layout="wide",
    page_title="COHORT",
    page_icon="🛡",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("COHORT")
st.sidebar.caption("Multi-Agent Cybersecurity Framework")

page = st.sidebar.radio(
    "Navigate",
    ["Conversations", "Results"],
)

st.sidebar.divider()

# ── Page routing ──────────────────────────────────────────────────────────────
if page == "Conversations":
    from app.pages.conversations import render_conversations_page
    render_conversations_page()

elif page == "Results":
    from app.pages.results import render_results_page
    render_results_page()
