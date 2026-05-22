"""Screening logic: apply filters, compute metrics, rank results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from indicators import latest_rsi, volume_ratio


@dataclass
class ScreenCriteria:
    price_min: float = 5.0
    price_max: float = 100.0
    pe_min: float = 0.0
    pe_max: float = 20.0
    vol_ratio_min: float = 2.0
    rsi_min: float = 50.0
    rsi_max: float = 100.0
    use_yesterday: bool = False  # if True, all metrics computed from yesterday's bar


def _composite_score(row: pd.Series, criteria: ScreenCriteria) -> float:
    vol_component = min(row["volume_ratio"], 5.0) / 5.0
    rsi_component = max(0.0, min(row["rsi"] - criteria.rsi_min, 30.0)) / 30.0
    pe_room = max(0.0, criteria.pe_max - row["pe_ratio"]) / max(criteria.pe_max, 1e-6)
    pe_component = min(pe_room, 1.0)
    return 0.40 * vol_component + 0.30 * rsi_component + 0.30 * pe_component


def prefilter_by_price(
    yf_symbols: List[str],
    ohlcv: Dict[str, pd.DataFrame],
    price_min: float,
    price_max: float,
    use_yesterday: bool = False,
) -> List[str]:
    """Return tickers whose latest (or yesterday's) close is within [price_min, price_max]."""
    idx = -2 if use_yesterday else -1
    keep: List[str] = []
    for sym in yf_symbols:
        df = ohlcv.get(sym)
        if df is None or df.empty:
            continue
        close = df["Close"].dropna()
        if len(close) < abs(idx):
            continue
        price = float(close.iloc[idx])
        if not np.isfinite(price):
            continue
        if price_min <= price <= price_max:
            keep.append(sym)
    return keep


def screen(
    yf_symbols: List[str],
    ohlcv: Dict[str, pd.DataFrame],
    pe_map: Dict[str, float],
    criteria: ScreenCriteria,
) -> pd.DataFrame:
    """Apply all criteria. Returns DataFrame sorted by composite score (desc)."""
    rows: list[dict] = []
    use_y = criteria.use_yesterday
    # Need 22 bars in yesterday mode (20 + yesterday + day-before), 21 in today mode
    min_bars = 22 if use_y else 21

    for sym in yf_symbols:
        df = ohlcv.get(sym)
        if df is None or df.empty or len(df) < min_bars:
            continue

        close = df["Close"].dropna()
        vol = df["Volume"].dropna()
        if len(close) < min_bars or len(vol) < min_bars:
            continue

        idx = -2 if use_y else -1
        price = float(close.iloc[idx])
        vr = volume_ratio(vol, window=20, use_yesterday=use_y)
        rsi = latest_rsi(close, period=14, use_yesterday=use_y)
        pe = pe_map.get(sym, float("nan"))

        if not all(np.isfinite(x) for x in (price, vr, rsi, pe)):
            continue

        # Change %: compare reference day to the bar before it
        prev_idx = idx - 1
        if len(close) >= abs(prev_idx):
            prev = float(close.iloc[prev_idx])
            chg_pct = ((price - prev) / prev * 100.0) if prev > 0 else 0.0
        else:
            chg_pct = 0.0

        # Sparkline: last 30 bars ending at the reference day
        end_idx = len(close) + idx + 1 if use_y else len(close)
        spark = close.iloc[max(0, end_idx - 30):end_idx].round(2).tolist()

        rows.append({
            "ticker": sym,
            "price": price,
            "change_pct": chg_pct,
            "pe_ratio": pe,
            "volume_ratio": vr,
            "rsi": rsi,
            "sparkline": spark,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "price", "change_pct", "pe_ratio", "volume_ratio",
            "rsi", "score", "sparkline"
        ])

    df = pd.DataFrame(rows)

    mask = (
        (df["price"] >= criteria.price_min)
        & (df["price"] <= criteria.price_max)
        & (df["pe_ratio"] >= criteria.pe_min)
        & (df["pe_ratio"] <= criteria.pe_max)
        & (df["volume_ratio"] > criteria.vol_ratio_min)
        & (df["rsi"] > criteria.rsi_min)
        & (df["rsi"] <= criteria.rsi_max)
    )
    df = df[mask].copy()

    if df.empty:
        return df.assign(score=pd.Series(dtype=float))

    df["score"] = df.apply(lambda r: _composite_score(r, criteria), axis=1)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df
