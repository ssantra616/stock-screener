"""US ticker universe: Russell 3000 via iShares IWV ETF holdings.

Tiered fallback:
  1. iShares IWV holdings CSV (preferred — canonical Russell 3000)
  2. S&P 500 + NASDAQ-100 union from Wikipedia (~600 large caps)
  3. Hardcoded ~100-ticker minimal list
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import List

import pandas as pd
import requests

CACHE_DIR = Path(os.environ.get("CACHE_DIR", Path(__file__).parent / ".cache"))
CACHE_DIR.mkdir(exist_ok=True, parents=True)

RUSSELL3000_URL = (
    "https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund"
)
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Tier-3 fallback: ~100 large-cap US stocks
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
    "UAL", "AAL", "PLTR", "SOFI", "F", "RIVN", "LCID", "NIO", "PINS", "SNAP",
]


def _fetch_russell3000_from_ishares() -> List[str]:
    """iShares IWV CSV — header is buried below ~9 metadata rows."""
    resp = requests.get(RUSSELL3000_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    raw = resp.text

    lines = raw.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("ticker,"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not locate 'Ticker' header in IWV CSV")

    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))

    if "Asset Class" in df.columns:
        df = df[df["Asset Class"].astype(str).str.strip().str.lower() == "equity"]

    symbols = (
        df["Ticker"].astype(str).str.strip()
        .str.replace(".", "-", regex=False)
    )
    symbols = symbols[symbols.str.len() > 0]
    # Drop obvious non-equity rows (cash placeholders, dashes)
    symbols = symbols[~symbols.str.match(r"^-+$", na=False)]
    symbols = symbols.drop_duplicates().tolist()

    if len(symbols) < 1000:
        raise ValueError(f"iShares returned only {len(symbols)} symbols; suspicious")
    return symbols


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
    Returns US ticker symbols. Tiered fallback. Disk-cached after first fetch.
    `limit` truncates from the top (iShares orders by weight = largest first).
    """
    cache_path = CACHE_DIR / "us_universe.csv"

    # Try cache first
    if cache_path.exists():
        try:
            df = pd.read_csv(cache_path)
            if "Ticker" in df.columns and len(df) > 100:
                symbols = df["Ticker"].astype(str).str.strip().tolist()
                return symbols[:limit] if limit else symbols
        except Exception as e:
            print(f"[universe] cached universe unreadable: {e}", file=sys.stderr)

    # Tier 1: iShares
    symbols: List[str] = []
    try:
        symbols = _fetch_russell3000_from_ishares()
        print(f"[universe] loaded {len(symbols)} tickers from iShares Russell 3000", file=sys.stderr)
    except Exception as e:
        print(f"[universe] iShares fetch failed: {e}", file=sys.stderr)

    # Tier 2: Wikipedia union
    if not symbols:
        try:
            sp500 = _fetch_sp500_wikipedia()
            ndx = _fetch_nasdaq100_wikipedia()
            symbols = sorted(set(sp500) | set(ndx))
            print(f"[universe] loaded {len(symbols)} tickers from Wikipedia S&P+NDX union", file=sys.stderr)
        except Exception as e:
            print(f"[universe] wikipedia fetch failed: {e}", file=sys.stderr)

    # Tier 3: hardcoded
    if not symbols:
        symbols = list(MINIMAL_FALLBACK)
        print(f"[universe] using minimal hardcoded fallback ({len(symbols)} tickers)", file=sys.stderr)

    # Persist for next process
    try:
        pd.DataFrame({"Ticker": symbols}).to_csv(cache_path, index=False)
    except Exception as e:
        print(f"[universe] couldn't write cache: {e}", file=sys.stderr)

    return symbols[:limit] if limit else symbols
