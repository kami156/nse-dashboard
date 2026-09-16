"""Streamlit launcher for the NSE Institutional Dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import generate_dashboard

st.set_page_config(
    page_title="NSE Intelligence Launcher",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("NSE Institutional Dashboard")
st.caption("Generate a self-contained Apple-style HTML report, then view it here or in a browser.")

default_wl = ROOT / "config" / "watchlists.yaml"
html_path = ROOT / "output" / "dashboard.html"

with st.sidebar:
    st.header("Controls")
    wl_path = st.text_input("Watchlists YAML", value=str(default_wl))
    force_refresh = st.checkbox("Force refresh cache", value=False)
    skip_news = st.checkbox("Skip news fetch", value=False)
    run = st.button("Generate / Refresh dashboard", type="primary", use_container_width=True)
    st.divider()
    st.markdown("CLI equivalent:")
    st.code("python generate_dashboard.py", language="bash")

if run:
    with st.spinner("Fetching market data and rendering HTML…"):
        try:
            payload = generate_dashboard(
                project_root=ROOT,
                watchlists_path=Path(wl_path),
                force_refresh=force_refresh,
                skip_news=skip_news,
            )
            st.session_state["last_payload"] = {
                "generated_at": payload.get("generated_at"),
                "html_path": payload.get("html_path"),
                "warnings": payload.get("warnings") or [],
                "sentiment": (payload.get("regime") or {}).get("market_sentiment"),
                "opportunities": len(payload.get("opportunities") or []),
            }
            st.success(f"Dashboard generated at {payload.get('generated_at')}")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")
            st.exception(exc)

meta = st.session_state.get("last_payload")
if meta:
    c1, c2, c3 = st.columns(3)
    c1.metric("Last generated", meta.get("generated_at") or "—")
    c2.metric("Sentiment", meta.get("sentiment") or "—")
    c3.metric("Opportunities", meta.get("opportunities") or 0)
    warns = meta.get("warnings") or []
    if warns:
        with st.expander(f"Fetch warnings ({len(warns)})"):
            for w in warns[:50]:
                st.write(f"- {w}")

if html_path.exists():
    st.subheader("Dashboard preview")
    st.markdown(f"File: `{html_path}`")
    html = html_path.read_text(encoding="utf-8")
    st.components.v1.html(html, height=900, scrolling=True)
    st.download_button(
        "Download dashboard.html",
        data=html.encode("utf-8"),
        file_name="dashboard.html",
        mime="text/html",
    )
else:
    st.info("No dashboard.html yet. Click **Generate / Refresh dashboard** to create one.")
