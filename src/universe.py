"""
Ticker universe helpers for the two supported markets: NSE Nifty 500 (India)
and NYSE (US).

yfinance has no official "give me index constituents" endpoint, so for each
market we:
  1. Try a live fetch from a public source.
  2. Fall back to a bundled static list if the live fetch fails or is blocked
     (this happens often with NSE, which frequently rejects non-browser
     requests).

Every ticker returned is already in the format yfinance expects
(NSE tickers get a ".NS" suffix, NYSE tickers are used as-is).
"""

from __future__ import annotations

import io
import logging
from typing import List

import requests

logger = logging.getLogger(__name__)

NSE_ARCHIVE_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
NASDAQ_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# Browser-like headers help avoid instant blocking on NSE's archive endpoint.
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,text/plain,*/*",
}

# --------------------------------------------------------------------------
# Fallback lists. These are intentionally NOT exhaustive (500 / thousands of
# tickers). They cover well-known, liquid, large/mid-cap names so the app is
# always usable even when the live fetch is blocked, and so "Quick scan" mode
# stays fast against the 1-minute refresh requirement. Extend these freely.
# --------------------------------------------------------------------------

NIFTY_FALLBACK: List[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "BAJFINANCE.NS",
    "KOTAKBANK.NS", "LT.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "NESTLEIND.NS", "ADANIENT.NS", "ADANIPORTS.NS", "BAJAJFINSV.NS", "M&M.NS",
    "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "TATAMOTORS.NS", "TATASTEEL.NS",
    "JSWSTEEL.NS", "COALINDIA.NS", "TECHM.NS", "HDFCLIFE.NS", "SBILIFE.NS",
    "GRASIM.NS", "BRITANNIA.NS", "DIVISLAB.NS", "DRREDDY.NS", "CIPLA.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "APOLLOHOSP.NS",
    "INDUSINDBK.NS", "UPL.NS", "BPCL.NS", "TATACONSUM.NS", "SHREECEM.NS",
    "HINDALCO.NS", "VEDL.NS", "PIDILITIND.NS", "DABUR.NS", "GODREJCP.NS",
    "MARICO.NS", "SIEMENS.NS", "DLF.NS", "AMBUJACEM.NS", "BANKBARODA.NS",
    "PNB.NS", "IDFCFIRSTB.NS", "CANBK.NS", "BEL.NS", "HAL.NS", "IRCTC.NS",
    "ZOMATO.NS", "NYKAA.NS", "PAYTM.NS", "POLICYBZR.NS", "TRENT.NS",
    "PAGEIND.NS", "HAVELLS.NS", "VOLTAS.NS", "MOTHERSON.NS", "BOSCHLTD.NS",
    "MUTHOOTFIN.NS", "CHOLAFIN.NS", "LICHSGFIN.NS", "PFC.NS", "RECLTD.NS",
    "GAIL.NS", "IOC.NS", "PETRONET.NS", "INDIGO.NS", "LUPIN.NS", "AUROPHARMA.NS",
    "TORNTPHARM.NS", "ALKEM.NS", "BIOCON.NS", "MPHASIS.NS", "LTIM.NS",
    "PERSISTENT.NS", "COFORGE.NS", "OFSS.NS", "NAUKRI.NS", "COLPAL.NS",
    "UBL.NS", "MCDOWELL-N.NS", "ABB.NS", "CUMMINSIND.NS", "SRF.NS",
]

NYSE_FALLBACK: List[str] = [
    "JPM", "BAC", "WFC", "C", "GS", "MS", "V", "MA", "JNJ", "PFE", "MRK",
    "UNH", "ABBV", "LLY", "XOM", "CVX", "COP", "HD", "LOW", "MCD", "SBUX",
    "NKE", "DIS", "KO", "PEP", "PG", "WMT", "TGT", "COST", "BA", "CAT",
    "GE", "HON", "UPS", "RTX", "LMT", "MMM", "IBM", "ORCL", "CSCO", "VZ",
    "T", "CMCSA", "NFLX", "ABT", "TMO", "DHR", "MDT", "BMY", "AMGN", "GILD",
    "NEE", "DUK", "SO", "AEP", "D", "SLB", "OXY", "MPC", "PSX", "VLO",
    "GM", "F", "DE", "EMR", "ETN", "ITW", "PH", "NOC", "GD", "SPGI", "BLK",
    "SCHW", "AXP", "USB", "PNC", "TFC", "COF", "MET", "PRU", "ALL", "TRV",
    "PGR", "AIG", "CB", "MMC", "AON", "ADP", "PAYX", "IBM", "TXN", "ADI",
    "AMAT", "LRCX", "MU", "QCOM", "AVGO", "CRM", "NOW", "INTU", "IQV",
]


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def fetch_nifty500_live() -> List[str]:
    """Attempt to fetch the official Nifty 500 constituent list from NSE."""
    resp = requests.get(NSE_ARCHIVE_URL, headers=_NSE_HEADERS, timeout=10)
    resp.raise_for_status()
    text = resp.text
    if "Symbol" not in text:
        raise ValueError("Unexpected NSE response format")

    symbols = []
    reader = io.StringIO(text)
    header = reader.readline()
    col_names = [c.strip().strip('"') for c in header.split(",")]
    symbol_idx = col_names.index("Symbol") if "Symbol" in col_names else 2

    for line in reader:
        parts = line.strip().split(",")
        if len(parts) > symbol_idx:
            sym = parts[symbol_idx].strip().strip('"')
            if sym:
                symbols.append(f"{sym}.NS")

    if len(symbols) < 100:
        raise ValueError("Live Nifty 500 fetch returned too few symbols")

    return _dedupe_preserve_order(symbols)


def fetch_nyse_full_live() -> List[str]:
    """Fetch the full list of NYSE-listed tickers from Nasdaq Trader's
    otherlisted.txt (this includes AMEX/ARCA too, filtered down to NYSE)."""
    resp = requests.get(NASDAQ_OTHER_LISTED_URL, timeout=15)
    resp.raise_for_status()
    lines = resp.text.splitlines()

    symbols = []
    header = lines[0].split("|")
    col_names = [c.strip() for c in header]
    try:
        symbol_idx = col_names.index("ACT Symbol")
        exchange_idx = col_names.index("Exchange")
    except ValueError:
        raise ValueError("Unexpected Nasdaq Trader file format")

    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) <= max(symbol_idx, exchange_idx):
            continue
        if parts[exchange_idx].strip() == "N":  # 'N' = NYSE
            sym = parts[symbol_idx].strip()
            if sym and "$" not in sym and "." not in sym:
                symbols.append(sym)

    if len(symbols) < 100:
        raise ValueError("Live NYSE fetch returned too few symbols")

    return _dedupe_preserve_order(symbols)


def get_nifty500_symbols() -> List[str]:
    """Return the Nifty 500 ticker universe (live fetch, falling back to a
    bundled static list of large/mid-caps if the live source is unreachable)."""
    try:
        return fetch_nifty500_live()
    except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a best-effort fetch
        logger.warning("Live Nifty 500 fetch failed (%s); using fallback list.", exc)
        return NIFTY_FALLBACK


def get_nyse_symbols(full: bool = False) -> List[str]:
    """Return the NYSE ticker universe.

    full=False (default, "Quick scan"): curated ~100 liquid large-caps, fast
        enough to comfortably re-scan every 60 seconds.
    full=True ("Full scan"): all NYSE-listed tickers from Nasdaq Trader,
        falls back to the curated list if the live fetch fails.
    """
    if not full:
        return NYSE_FALLBACK
    try:
        return fetch_nyse_full_live()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live NYSE fetch failed (%s); using fallback list.", exc)
        return NYSE_FALLBACK
