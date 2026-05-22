"""Screening logic: apply filters, compute metrics, rank results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from indicators import latest_rsi, volume_ratio


@dataclass
class ScreenCriteria:
    price_min: float = 5.0
    price_max: float = 100.0
    pe_max: float = 20.0
    vol_ratio_min: float = 2.0
    rsi_min: float = 50.0
    rsi_max: float = 100.0


def _composite_score(row: pd.Series, criteria: ScreenCriteria) -> float:
    """40% volume, 30% RSI distance, 30% inverse P/E. Higher = better."""
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
) -> List[str]:
    """Return tickers whose latest close is within [price_min, price_max]."""
    keep: List[str] = []
    for sym in yf_symbols:
        df = ohlcv.get(sym)
        if df is None or df.empty:
            continue
        close = df["Close"].dropna()
        if close.empty:
            continue
        price = float(close.iloc[-1])
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
    """
    Apply all criteria. Returns DataFrame sorted by composite score (desc).
    Columns: ticker, price, pe_ratio, volume_ratio, rsi, score, sparkline.
    """
    rows: list[dict] = []

    for sym in yf_symbols:
        df = ohlcv.get(sym)
        if df is None or df.empty or len(df) < 21:
            continue

        close = df["Close"].dropna()
        vol = df["Volume"].dropna()
        if len(close) < 21 or len(vol) < 21:
            continue

        price = float(close.iloc[-1])
        vr = volume_ratio(vol, window=20)
        rsi = latest_rsi(close, period=14)
        pe = pe_map.get(sym, float("nan"))

        if not (np.isfinite(price) and np.isfinite(vr) and np.isfinite(rsi) and np.isfinite(pe)):
            continue
        if pe <= 0:
            continue

        # Percent change today vs prior close (for the UI)
        if len(close) >= 2:
            prev = float(close.iloc[-2])
            pct = ((price - prev) / prev * 100.0) if prev > 0 else 0.0
        else:
            pct = 0.0

        rows.append({
            "ticker": sym,
            "price": price,
            "change_pct": pct,
            "pe_ratio": pe,
            "volume_ratio": vr,
            "rsi": rsi,
            "sparkline": close.tail(30).round(2).tolist(),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "price", "change_pct", "pe_ratio", "volume_ratio", "rsi", "score", "sparkline"
        ])

    df = pd.DataFrame(rows)

    mask = (
        (df["price"] >= criteria.price_min)
        & (df["price"] <= criteria.price_max)
        & (df["pe_ratio"] < criteria.pe_max)
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
