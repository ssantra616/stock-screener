"""US ticker universe: S&P 500 + NASDAQ-100 union from Wikipedia.

This is the ~600 large-cap universe covering nearly all meaningful NYSE +
NASDAQ trading activity. Smaller than Russell 3000, faster to scan, fewer
illiquid micro-caps.

Tiered fallback:
  1. S&P 500 + NASDAQ-100 union from Wikipedia (~600)
  2. Hardcoded ~110-ticker minimal list
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import pandas as pd

CACHE_DIR = Path(os.environ.get("CACHE_DIR", Path(__file__).parent / ".cache"))
CACHE_DIR.mkdir(exist_ok=True, parents=True)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

MINIMAL_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK-B", "JPM",
    "V", "JNJ", "WMT", "PG", "MA", "XOM", "HD", "CVX", "LLY", "ABBV",
    "PFE", "KO", "PEP", "MRK", "BAC", "TMO", "COST", "CSCO", "AVGO", "ADBE",
    "ACN", "MCD", "ABT", "DHR", "WFC", "CRM", "VZ", "NKE", "TXN", "NEE",
    "DIS", "INTC", "PM", "RTX", "QCOM", "UPS", "ORCL", "HON", "AMGN", "IBM",
    "GS", "NFLX", "AMD", "TMUS", "INTU", "AMAT", "BKNG", "ISRG", "VRTX", "ADI",
    "LRCX", "MU", "GILD", "MDLZ", "REGN", "PANW", "ADP", "KLAC", "SBUX", "SNPS",
    "CDNS", "MELI", "ASML", "CRWD", "MAR", "PYPL", "ORLY", "FTNT", "ABNB", "CSX",
    "MNST", "CHTR", "MS", "BLK", "T", "CMCSA", "SCHW", "SPGI", "AXP", "DE",
    "BA", "C", "CAT", "GE", "LOW", "MDT", "F", "GM", "TGT", "DAL",
    "UAL", "AAL", "PLTR", "SOFI", "RIVN", "LCID", "NIO", "PINS", "SNAP",
]


def _fetch_sp500_wikipedia() -> List[str]:
    tables = pd.read_html(SP500_URL, storage_options=HEADERS)
    df = tables[0]
    return (
        df["Symbol"].astype(str).str.strip()
        .str.replace(".", "-", regex=False).tolist()
    )


def _fetch_nasdaq100_wikipedia() -> List[str]:
    tables = pd.read_html(NASDAQ100_URL, storage_options=HEADERS)
    df = None
    for t in tables:
        cols = [str(c).lower() for c in t.columns]
        if any(c in ("ticker", "symbol") for c in cols):
            df = t
            break
    if df is None:
        raise ValueError("Could not locate NASDAQ-100 components table")
    sym_col = "Ticker" if "Ticker" in df.columns else "Symbol"
    return (
        df[sym_col].astype(str).str.strip()
        .str.replace(".", "-", regex=False).tolist()
    )


def get_universe(limit: int | None = None) -> List[str]:
    """
    Returns combined S&P 500 + NASDAQ-100 tickers (deduped union).
    Tiered fallback. Disk-cached after first fetch.
    """
    cache_path = CACHE_DIR / "us_universe.csv"

    if cache_path.exists():
        try:
            df = pd.read_csv(cache_path)
            if "Ticker" in df.columns and len(df) > 100:
                symbols = df["Ticker"].astype(str).str.strip().tolist()
                return symbols[:limit] if limit else symbols
        except Exception as e:
            print(f"[universe] cached universe unreadable: {e}", file=sys.stderr)

    symbols: List[str] = []

    # Tier 1: Wikipedia S&P 500 + NASDAQ-100 union
    try:
        sp500 = _fetch_sp500_wikipedia()
        ndx = _fetch_nasdaq100_wikipedia()
        symbols = sorted(set(sp500) | set(ndx))
        print(f"[universe] loaded {len(symbols)} tickers from S&P 500 + NASDAQ-100 union", file=sys.stderr)
    except Exception as e:
        print(f"[universe] Wikipedia fetch failed: {e}", file=sys.stderr)

    # Tier 2: hardcoded fallback
    if not symbols:
        symbols = list(MINIMAL_FALLBACK)
        print(f"[universe] using minimal hardcoded fallback ({len(symbols)} tickers)", file=sys.stderr)

    try:
        pd.DataFrame({"Ticker": symbols}).to_csv(cache_path, index=False)
    except Exception as e:
        print(f"[universe] couldn't write cache: {e}", file=sys.stderr)

    return symbols[:limit] if limit else symbols
