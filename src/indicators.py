"""Technical indicator math: RSI(14) and volume-spike ratio.

Kept dependency-free (pandas/numpy only) rather than pulling in a TA library,
so behavior is transparent and easy to audit/tune.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder's RSI over the given close-price series. Returns the most
    recent RSI value, or None if there isn't enough history."""
    if close is None or len(close) < period + 1:
        return None

    delta = close.diff().dropna()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)

    # Wilder's smoothing (equivalent to an EMA with alpha = 1/period)
    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]

    if pd.isna(last_gain) or pd.isna(last_loss):
        return None
    if last_loss == 0:
        return 100.0

    rs = last_gain / last_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi)


def compute_volume_ratio(volume: pd.Series, period: int = 20) -> float | None:
    """Ratio of the most recent day's volume to the trailing `period`-day
    average volume (average excludes the most recent day itself, so a
    genuine spike isn't diluted by including itself in its own baseline)."""
    if volume is None or len(volume) < period + 1:
        return None

    latest = volume.iloc[-1]
    baseline = volume.iloc[-(period + 1):-1]  # the `period` days before the latest
    baseline_avg = baseline.mean()

    if baseline_avg == 0 or pd.isna(baseline_avg) or pd.isna(latest):
        return None

    return float(latest / baseline_avg)
