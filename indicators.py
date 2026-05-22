"""Technical indicators. Pure-pandas, no external TA libraries."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Returns NaN for first `period` values."""
    if close is None or len(close) < period + 1:
        return pd.Series(
            [np.nan] * len(close) if close is not None else [],
            index=close.index if close is not None else None,
        )

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    return rsi


def volume_ratio(volume: pd.Series, window: int = 20) -> float:
    """Today's volume ÷ trailing `window`-day average (excluding today)."""
    if volume is None or len(volume) < window + 1:
        return float("nan")
    today = float(volume.iloc[-1])
    avg = float(volume.iloc[-(window + 1):-1].mean())
    if avg <= 0 or np.isnan(avg):
        return float("nan")
    return today / avg


def latest_rsi(close: pd.Series, period: int = 14) -> float:
    series = rsi_wilder(close, period=period)
    if len(series) == 0:
        return float("nan")
    val = series.iloc[-1]
    return float(val) if pd.notna(val) else float("nan")
