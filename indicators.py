"""Technical indicators. Pure-pandas, no external TA libraries."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
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


def volume_ratio(volume: pd.Series, window: int = 20, use_yesterday: bool = False) -> float:
    """
    Volume vs trailing `window`-day average.

    use_yesterday=False (default): today's volume ÷ avg of prior `window` days.
        Use after market close (4 PM ET) for accurate results.

    use_yesterday=True: yesterday's volume ÷ avg of `window` days before yesterday.
        Use during market hours — yesterday's bar is complete, today's isn't.
    """
    if volume is None:
        return float("nan")

    if use_yesterday:
        if len(volume) < window + 2:
            return float("nan")
        target = float(volume.iloc[-2])  # yesterday
        avg = float(volume.iloc[-(window + 2):-2].mean())
    else:
        if len(volume) < window + 1:
            return float("nan")
        target = float(volume.iloc[-1])  # today
        avg = float(volume.iloc[-(window + 1):-1].mean())

    if avg <= 0 or np.isnan(avg):
        return float("nan")
    return target / avg


def latest_rsi(close: pd.Series, period: int = 14, use_yesterday: bool = False) -> float:
    """
    Most recent RSI value. If use_yesterday=True, returns RSI as of yesterday
    (one bar earlier).
    """
    series = rsi_wilder(close, period=period)
    if len(series) == 0:
        return float("nan")
    idx = -2 if use_yesterday else -1
    if len(series) < abs(idx):
        return float("nan")
    val = series.iloc[idx]
    return float(val) if pd.notna(val) else float("nan")
