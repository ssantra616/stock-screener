"""FastAPI server for the US stock screener.

Entry point for local dev:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Entry point for deployment (Render/Railway/Heroku/Docker):
    uvicorn main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from data_fetcher import fetch_ohlcv, fetch_pe
from screener import ScreenCriteria, prefilter_by_price, screen
from universe import get_universe

BASE_DIR = Path(__file__).parent

app = FastAPI(title="US Stock Screener", version="1.0.0")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Only one scan at a time per process (rate-limit hygiene).
# For higher concurrency, scale workers (uvicorn --workers N).
_scan_lock = asyncio.Lock()


class ScanRequest(BaseModel):
    universe_size: int = Field(500, ge=50, le=3000)
    price_min: float = Field(5.0, ge=0.5, le=10000.0)
    price_max: float = Field(100.0, ge=0.5, le=10000.0)
    pe_max: float = Field(20.0, ge=1.0, le=200.0)
    vol_ratio_min: float = Field(2.0, ge=1.0, le=20.0)
    rsi_min: float = Field(50.0, ge=0.0, le=100.0)
    rsi_max: float = Field(100.0, ge=0.0, le=100.0)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/healthz")
async def healthz():
    """Health check endpoint for deployment platforms."""
    return {"status": "ok"}


@app.post("/api/scan")
async def api_scan(req: ScanRequest) -> JSONResponse:
    if req.price_min >= req.price_max:
        raise HTTPException(400, "price_min must be < price_max")
    if req.rsi_min >= req.rsi_max:
        raise HTTPException(400, "rsi_min must be < rsi_max")

    # If a scan is already running, return 429 (frontend handles this gracefully).
    if _scan_lock.locked():
        raise HTTPException(429, "A scan is already running. Try again shortly.")

    async with _scan_lock:
        t0 = time.time()
        # All blocking work (yfinance calls) happens in a thread so the event
        # loop stays responsive for /healthz and other requests.
        result = await asyncio.to_thread(_run_scan_sync, req)
        result["elapsed_s"] = round(time.time() - t0, 1)
        return JSONResponse(result)


def _run_scan_sync(req: ScanRequest) -> Dict[str, Any]:
    """Synchronous scan pipeline. Called via asyncio.to_thread from the route."""
    criteria = ScreenCriteria(
        price_min=req.price_min,
        price_max=req.price_max,
        pe_max=req.pe_max,
        vol_ratio_min=req.vol_ratio_min,
        rsi_min=req.rsi_min,
        rsi_max=req.rsi_max,
    )

    yf_symbols = get_universe(limit=req.universe_size)
    universe_count = len(yf_symbols)

    # 1. OHLCV (batched, cached 5 min)
    ohlcv = fetch_ohlcv(yf_symbols, days=60)
    with_data = len(ohlcv)

    # 2. Price-band prefilter BEFORE expensive P/E fetch
    in_band = prefilter_by_price(yf_symbols, ohlcv, criteria.price_min, criteria.price_max)
    in_band_count = len(in_band)

    if not in_band:
        return {
            "results": [],
            "stats": {
                "universe": universe_count,
                "with_data": with_data,
                "in_price_band": 0,
                "passing": 0,
            },
            "criteria": req.model_dump(),
        }

    # 3. P/E (per-ticker, cached 1 hour)
    pe_map = fetch_pe(in_band)

    # 4. Apply remaining filters + rank
    df = screen(in_band, ohlcv, pe_map, criteria)

    results: List[Dict[str, Any]] = []
    for i, row in df.iterrows():
        results.append({
            "rank": i + 1,
            "ticker": row["ticker"],
            "price": round(float(row["price"]), 2),
            "change_pct": round(float(row["change_pct"]), 2),
            "pe_ratio": round(float(row["pe_ratio"]), 2),
            "volume_ratio": round(float(row["volume_ratio"]), 2),
            "rsi": round(float(row["rsi"]), 1),
            "score": round(float(row["score"]) * 100, 1),
            "sparkline": row["sparkline"],
        })

    return {
        "results": results,
        "stats": {
            "universe": universe_count,
            "with_data": with_data,
            "in_price_band": in_band_count,
            "passing": len(results),
        },
        "criteria": req.model_dump(),
    }


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
