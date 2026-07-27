"""
Core screening logic: fetch data, compute indicators, filter, rank.

This module is intentionally Streamlit-free — app.py wraps the two fetch
functions (`fetch_price_history`, `fetch_fundamentals`) with
`st.cache_data(ttl=...)` so caching stays a UI-layer concern and this module
stays testable on its own.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from .indicators import compute_rsi, compute_volume_ratio

logger = logging.getLogger(__name__)


@dataclass
class ScreenParams:
    pe_max: float = 20.0
    volume_multiple: float = 2.0
    rsi_min: float = 50.0
    top_n: int = 50


def fetch_price_history(tickers: List[str], period: str = "4mo") -> Dict[str, pd.DataFrame]:
    """Batched download of daily OHLCV history for all tickers in one call.
    Far faster than looping yf.Ticker(t).history() per ticker."""
    if not tickers:
        return {}

    raw = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=False,
    )

    result: Dict[str, pd.DataFrame] = {}

    if len(tickers) == 1:
        # yf.download returns a flat frame (no ticker-level column grouping)
        # when only one ticker is requested.
        t = tickers[0]
        if not raw.empty:
            result[t] = raw
        return result

    for t in tickers:
        try:
            df = raw[t].dropna(how="all")
            if not df.empty:
                result[t] = df
        except (KeyError, TypeError):
            continue

    return result


def _fetch_one_fundamental(ticker: str) -> Optional[dict]:
    try:
        info = yf.Ticker(ticker).get_info()
        pe = info.get("trailingPE")
        return {"ticker": ticker, "pe": pe}
    except Exception as exc:  # noqa: BLE001 - one bad ticker shouldn't kill the batch
        logger.debug("Fundamentals fetch failed for %s: %s", ticker, exc)
        return {"ticker": ticker, "pe": None}


def fetch_fundamentals(tickers: List[str], max_workers: int = 16) -> Dict[str, Optional[float]]:
    """Threaded fetch of trailing P/E for each ticker. This hits Yahoo's
    slower per-ticker `.info` endpoint, so it's cached longer (30 min) than
    price history in app.py — P/E doesn't meaningfully change minute to minute."""
    if not tickers:
        return {}

    pe_by_ticker: Dict[str, Optional[float]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one_fundamental, t): t for t in tickers}
        for future in as_completed(futures):
            res = future.result()
            if res:
                pe_by_ticker[res["ticker"]] = res["pe"]

    return pe_by_ticker


def compute_score(pe: float, vol_ratio: float, rsi: float, params: ScreenParams) -> float:
    """Composite ranking score, weighted 40% volume spike / 30% RSI strength
    / 30% cheapness. Each term is normalized to roughly [0, 1] before
    weighting. Tune weights here — nowhere else."""
    vol_component = min(vol_ratio / 5.0, 1.0)          # a 5x+ spike maxes this term out
    rsi_component = max(min((rsi - 50.0) / 50.0, 1.0), 0.0)
    pe_component = max(min((params.pe_max - pe) / params.pe_max, 1.0), 0.0)

    return 0.4 * vol_component + 0.3 * rsi_component + 0.3 * pe_component


def run_screen(
    price_data: Dict[str, pd.DataFrame],
    pe_data: Dict[str, Optional[float]],
    params: ScreenParams,
) -> pd.DataFrame:
    """Combine price history + fundamentals, apply filters, rank, return a
    DataFrame ready to display."""
    rows = []

    for ticker, df in price_data.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue

        close = df["Close"].dropna()
        volume = df["Volume"].dropna()
        if close.empty or volume.empty:
            continue

        pe = pe_data.get(ticker)
        if pe is None or pe <= 0 or pe >= params.pe_max:
            continue

        vol_ratio = compute_volume_ratio(volume, period=20)
        if vol_ratio is None or vol_ratio < params.volume_multiple:
            continue

        rsi = compute_rsi(close, period=14)
        if rsi is None or rsi <= params.rsi_min:
            continue

        current_price = float(close.iloc[-1])
        score = compute_score(pe, vol_ratio, rsi, params)

        rows.append(
            {
                "Ticker": ticker,
                "Price": round(current_price, 2),
                "P/E": round(pe, 2),
                "Volume Ratio": round(vol_ratio, 2),
                "RSI": round(rsi, 1),
                "Score": round(score, 4),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["Rank", "Ticker", "Price", "P/E", "Volume Ratio", "RSI", "Score"])

    out = pd.DataFrame(rows).sort_values("Score", ascending=False).head(params.top_n)
    out.insert(0, "Rank", range(1, len(out) + 1))
    out = out.reset_index(drop=True)
    return out
