"""
Momentum Value Screener — Streamlit dashboard.

Run with:
    streamlit run app.py --server.port 8501

See CLAUDE.md for architecture/design rationale and known limitations.
"""

import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from src.screener import ScreenParams, fetch_fundamentals, fetch_price_history, run_screen
from src.universe import get_nifty500_symbols, get_nyse_symbols

REFRESH_MS = 60_000  # 1 minute, per project spec

st.set_page_config(page_title="Momentum Value Screener", layout="wide", page_icon="📈")


# ---------------------------------------------------------------------------
# Cached data-fetch wrappers. Two tiers, as documented in CLAUDE.md:
#   - price history: 60s TTL   (fast batched call, matches refresh cadence)
#   - fundamentals (P/E): 30min TTL (slow per-ticker call, changes rarely)
#   - universe list: 1hr TTL   (index composition barely ever changes intraday)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def cached_universe(market: str, full_nyse: bool):
    if market == "NSE (Nifty 500)":
        return get_nifty500_symbols()
    return get_nyse_symbols(full=full_nyse)


@st.cache_data(ttl=60, show_spinner=False)
def cached_price_history(tickers_tuple: tuple, period: str):
    return fetch_price_history(list(tickers_tuple), period=period)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_fundamentals(tickers_tuple: tuple):
    return fetch_fundamentals(list(tickers_tuple))


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

st.sidebar.title("⚙️ Screener Settings")

market = st.sidebar.radio("Market", ["NSE (Nifty 500)", "NYSE (US)"])

full_nyse = False
if market == "NYSE (US)":
    scan_mode = st.sidebar.radio(
        "Universe size",
        ["Quick scan (~100 liquid large-caps)", "Full scan (all NYSE tickers — slower, more rate-limit risk)"],
    )
    full_nyse = scan_mode.startswith("Full")

st.sidebar.markdown("### Filters")
pe_max = st.sidebar.slider("Max P/E", 5, 50, 20)
vol_mult = st.sidebar.slider("Min Volume Spike (× 20-day avg)", 1.0, 5.0, 2.0, step=0.1)
rsi_min = st.sidebar.slider("Min RSI", 30, 80, 50)
top_n = st.sidebar.slider("Top N results", 10, 100, 50, step=10)

st.sidebar.markdown("### Refresh")
auto_refresh = st.sidebar.checkbox("Auto-refresh every 60s", value=True)
manual_refresh = st.sidebar.button("🔄 Refresh Now")

if auto_refresh:
    st_autorefresh(interval=REFRESH_MS, key="autorefresh_tick")

if manual_refresh:
    cached_price_history.clear()
    cached_fundamentals.clear()

# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

st.title("📈 Momentum Value Screener")
st.caption(
    f"P/E < {pe_max} · Volume > {vol_mult}× 20-day avg · RSI > {rsi_min} "
    "— ranked by a composite score (40% volume spike / 30% RSI / 30% cheapness)"
)

params = ScreenParams(pe_max=pe_max, volume_multiple=vol_mult, rsi_min=rsi_min, top_n=top_n)

status = st.empty()

try:
    status.info("Loading ticker universe...")
    tickers = cached_universe(market, full_nyse)
    st.sidebar.info(f"Universe size: {len(tickers)} tickers")

    status.info(f"Fetching price/volume history for {len(tickers)} tickers...")
    price_data = cached_price_history(tuple(sorted(tickers)), "4mo")

    status.info(f"Fetching fundamentals (P/E) for {len(tickers)} tickers — cached for 30 min...")
    pe_data = cached_fundamentals(tuple(sorted(tickers)))

    status.empty()

    result_df = run_screen(price_data, pe_data, params)

    last_updated = time.strftime("%Y-%m-%d %H:%M:%S")
    scanned = len(price_data)
    st.caption(f"🕒 Last updated: {last_updated}  ·  {len(result_df)} passed filters out of {scanned} scanned")

    if result_df.empty:
        st.warning(
            "No stocks currently pass all three filters. Try loosening thresholds in the sidebar, "
            "or switch to Full scan for a wider universe."
        )
    else:
        st.dataframe(
            result_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0.0, max_value=1.0, format="%.2f"
                ),
                "Volume Ratio": st.column_config.NumberColumn("Volume Ratio", format="%.2fx"),
                "RSI": st.column_config.NumberColumn("RSI", format="%.1f"),
                "P/E": st.column_config.NumberColumn("P/E", format="%.2f"),
            },
        )

except Exception as exc:  # noqa: BLE001 - surface any failure to the user instead of a blank page
    status.empty()
    st.error(f"Something went wrong while fetching/screening data: {exc}")
    st.info("This is often a temporary Yahoo Finance rate-limit. Try 'Refresh Now' in a moment.")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Data via yfinance (Yahoo Finance, unofficial & delayed). "
    "Not investment advice — for research/educational use only."
)
