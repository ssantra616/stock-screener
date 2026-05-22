"""yfinance wrapper with TTL caching, batching, and rate-limit-friendly behavior.

This is the ONLY module that imports yfinance. Uses a simple in-memory TTL
cache keyed by frozenset of tickers + freshness window.
"""
from __future__ import annotations

import math
import sys
import time
from threading import RLock
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

BATCH_SIZE = 100
BATCH_DELAY_S = 0.3
PE_PER_TICKER_DELAY_S = 0.1
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 2.0

OHLCV_TTL_S = 300       # 5 min
PE_TTL_S = 3600         # 1 hour


# --- Simple thread-safe TTL cache ---
class _TTLCache:
    def __init__(self):
        self._store: Dict[str, Tuple[float, object]] = {}
        self._lock = RLock()

    def get(self, key: str, ttl_s: float):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > ttl_s:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value):
        with self._lock:
            self._store[key] = (time.time(), value)

    def clear(self):
        with self._lock:
            self._store.clear()


_ohlcv_cache = _TTLCache()
_pe_cache = _TTLCache()


def _chunk(lst: List[str], n: int) -> List[List[str]]:
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def _cache_key(symbols: List[str], extra: str = "") -> str:
    # Sorted tuple → stable key regardless of input order
    return f"{extra}:{','.join(sorted(symbols))}"


def fetch_ohlcv(
    yf_symbols: List[str],
    days: int = 60,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Bulk-download OHLCV. Cached 5 min. Calls `progress_cb(done, total)` per batch.
    Returns dict: symbol -> DataFrame with [Open, High, Low, Close, Volume].
    """
    if not yf_symbols:
        return {}

    key = _cache_key(yf_symbols, extra=f"ohlcv-{days}")
    if use_cache:
        cached = _ohlcv_cache.get(key, OHLCV_TTL_S)
        if cached is not None:
            if progress_cb:
                progress_cb(1, 1)
            return cached

    out: Dict[str, pd.DataFrame] = {}
    period = f"{max(days, 60)}d"
    batches = _chunk(yf_symbols, BATCH_SIZE)
    total = len(batches)

    for i, batch in enumerate(batches, start=1):
        df_batch = None
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                df_batch = yf.download(
                    tickers=batch,
                    period=period,
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,
                    progress=False,
                    threads=True,
                )
                break
            except Exception as e:
                last_err = e
                sleep_s = RETRY_BACKOFF_BASE ** attempt
                print(f"[fetcher] OHLCV batch {i}/{total} failed (attempt {attempt+1}), sleeping {sleep_s}s: {e}", file=sys.stderr)
                time.sleep(sleep_s)

        if df_batch is not None:
            if len(batch) == 1:
                sym = batch[0]
                if not df_batch.empty:
                    out[sym] = df_batch[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
            else:
                for sym in batch:
                    try:
                        sub = df_batch[sym]
                    except KeyError:
                        continue
                    if sub is None or sub.empty:
                        continue
                    sub = sub[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
                    if not sub.empty:
                        out[sym] = sub
        else:
            print(f"[fetcher] OHLCV batch {i}/{total} giving up: {last_err}", file=sys.stderr)

        if progress_cb:
            progress_cb(i, total)
        time.sleep(BATCH_DELAY_S)

    _ohlcv_cache.set(key, out)
    return out


def fetch_pe(
    yf_symbols: List[str],
    progress_cb: Optional[Callable[[int, int], None]] = None,
    use_cache: bool = True,
) -> Dict[str, float]:
    """
    Fetch trailing P/E per ticker. Cached 1 hour because fundamentals barely
    change intraday. This is the rate-limit bottleneck (one request per ticker).
    """
    if not yf_symbols:
        return {}

    out: Dict[str, float] = {}
    to_fetch: List[str] = []

    # Per-ticker cache lookup (so partial overlaps with previous scans reuse cache)
    if use_cache:
        for sym in yf_symbols:
            cached = _pe_cache.get(f"pe:{sym}", PE_TTL_S)
            if cached is not None:
                out[sym] = cached
            else:
                to_fetch.append(sym)
    else:
        to_fetch = list(yf_symbols)

    total = len(to_fetch)
    for i, sym in enumerate(to_fetch, start=1):
        pe = float("nan")
        for attempt in range(MAX_RETRIES + 1):
            try:
                t = yf.Ticker(sym)
                info = t.info or {}
                pe_val = info.get("trailingPE")
                if pe_val is None:
                    pe_val = info.get("forwardPE")
                if pe_val is not None and not (isinstance(pe_val, float) and math.isnan(pe_val)):
                    pe = float(pe_val)
                break
            except Exception as e:
                sleep_s = RETRY_BACKOFF_BASE ** attempt
                print(f"[fetcher] P/E {sym} failed (attempt {attempt+1}), sleeping {sleep_s}s: {e}", file=sys.stderr)
                time.sleep(sleep_s)

        out[sym] = pe
        _pe_cache.set(f"pe:{sym}", pe)

        if progress_cb and (i % 25 == 0 or i == total):
            progress_cb(i, total)
        time.sleep(PE_PER_TICKER_DELAY_S)

    return out


def clear_caches():
    """Useful for tests and manual cache invalidation."""
    _ohlcv_cache.clear()
    _pe_cache.clear()
