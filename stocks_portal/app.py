"""
EquityTerm — clean v2 entry point.

Uses st.navigation() to define exactly which pages appear in the sidebar,
overriding Streamlit's pages/ folder auto-discovery. The /pages_archive/
folder is preserved on disk for reference (LeveragedETFHub etc.) but is
NOT shown in the UI.
"""

import os
import streamlit as st

# ── Streamlit Cloud Secrets bootstrap ─────────────────────────────────
# On Streamlit Community Cloud, API keys live in the "Secrets" panel and
# are exposed only via st.secrets. Copy them into os.environ here BEFORE
# any lib/* module imports, so existing os.getenv() calls work unchanged.
try:
    for _key in ("FINNHUB_API_KEY", "FMP_API_KEY", "FRED_API_KEY",
                 "GROQ_API_KEY", "OLLAMA_HOST", "OLLAMA_MODEL",
                 "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                 "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_GROUNDING",
                 "AI_COMPARE_MODE"):
        if _key in st.secrets and not os.getenv(_key):
            os.environ[_key] = str(st.secrets[_key])
except (FileNotFoundError, KeyError, AttributeError):
    pass  # Running locally without secrets.toml — .env handles it

# Define the 6 essential pages — in order shown in sidebar
NAV = {
    "EquityTerm": [
        st.Page("views/today.py",       title="Today",         icon="🎯", default=True),
        st.Page("views/macro.py",       title="Macro",         icon="🌍"),
        st.Page("views/crypto.py",      title="Crypto Cycle",  icon="₿"),
        st.Page("views/funnel.py",      title="Funnel",        icon="🎣"),
        st.Page("views/discovery.py",   title="Discovery",     icon="🔍"),
        st.Page("views/canslim.py",     title="CAN SLIM",      icon="🏆"),
        st.Page("views/valuation.py",   title="Valuation",     icon="💎"),
        st.Page("views/smart_money.py", title="Smart Money",   icon="💰"),
        st.Page("views/news.py",        title="News",          icon="📰"),
        st.Page("views/options.py",     title="Options Flow",  icon="⚡"),
    ],
}

st.set_page_config(
    page_title="EquityTerm",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation(NAV, position="sidebar")
pg.run()
