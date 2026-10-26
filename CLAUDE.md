# US Stock Screener — CLAUDE.md

Project memory for AI assistants. Read this first when working on this codebase.

## What this project is

A deployable, Finviz-inspired stock screener for **US-listed stocks** (Russell 3000). Filters by:

- **Price band** (default $5–$100, adjustable)
- **P/E ratio** below threshold (default 20, adjustable)
- **Volume spike** above N× the 20-day average (default 2.0×, adjustable)
- **RSI** within a range (default 50–100, adjustable)

Server is **FastAPI** (ASGI). Frontend is **Jinja2 + vanilla JS** (no React, no build step). Data source is `yfinance`.

## How to run locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`.

## How to deploy

Reads `PORT` and `HOST` from env vars so it works on any platform:

- **Render**: `render.yaml` included → push to Git, "New Web Service"
- **Railway / Fly.io / Heroku**: `Procfile` included
- **Docker / VPS / Kubernetes**: `Dockerfile` included → `docker build -t screener . && docker run -p 8000:8000 screener`

The entry point everywhere is `uvicorn main:app --host 0.0.0.0 --port $PORT`.

## Architecture

```
stock_screener/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── Dockerfile
├── Procfile
├── render.yaml
├── .dockerignore
├── main.py                # FastAPI app, routes, env config
├── screener.py            # filter logic + composite ranking
├── data_fetcher.py        # yfinance wrappers + in-memory caching
├── indicators.py          # RSI (Wilder) + volume ratio
├── universe.py            # Russell 3000 fetcher with fallback
├── templates/
│   └── index.html         # Jinja2 template (Apple-inspired UI)
└── static/
    ├── styles.css         # Apple-inspired styling, dark/light via prefers-color-scheme
    └── app.js             # fetch + render, presets, validation, saved filters, auto-refresh
```

## Routes

- `GET  /`           → renders the screener page
- `POST /api/scan`   → runs the screen with criteria from request body, returns JSON `{results, stats}`
- `GET  /healthz`    → returns `{"status":"ok"}` for platform health checks

## Rate limiting strategy

`yfinance` hits Yahoo Finance, which throttles aggressive callers (community-reported ~2000 requests/hour soft cap, with 429s on bursty patterns).

Strategy:

1. **Batched OHLCV downloads**: 100 tickers per HTTP request via `yf.download(tickers=[...])`. 3000 tickers = ~30 requests.
2. **In-memory cache** (since Streamlit's `@st.cache_data` is gone): a TTL-keyed dict module-level cache in `data_fetcher.py`. OHLCV cached 5 min, P/E cached 1 hour.
3. **Price-band prefilter** runs BEFORE P/E fetch. Cuts ~25% of universe before the rate-limit-expensive call.
4. **Sleep between batches**: 0.3s for OHLCV, 0.1s per P/E ticker.
5. **Exponential backoff retry** on failures.
6. **Scan-in-progress lock**: a single `asyncio.Lock` prevents concurrent scans from clobbering each other and burning rate limits.

Expected runtime for full Russell 3000:
- First scan (cold): 15–25 min
- Within 1 hour (warm P/E cache): 2–5 min

## Key implementation notes

- `data_fetcher.py` is the ONLY module that imports `yfinance`. Everything else uses pandas DataFrames.
- The price prefilter is the single biggest optimization — apply it BEFORE P/E lookup.
- Cache is in-memory only. Process restart = cold cache. For multi-replica deploys you'd swap for Redis (not in scope).
- The single asyncio Lock means **one scan at a time per process**. Multiple users can hit the page, but their scans queue. For higher concurrency, run multiple workers (`--workers 4`).
- Don't add per-ticker `.info` calls in the hot path. P/E is unavoidable but TTL-cached.

## Out of scope

- Sector/market-cap filters (would need per-ticker `.info` calls — rate-limit hostile)
- Backtesting
- Intraday/tick data (we use daily bars; "near real-time" here means last-close prices refreshed every 5 min)
- Authentication, multi-user state
- Persistent storage (Redis, DB) — pure in-memory caching only

## When editing

- New filter? Edit `screener.py` (logic), `templates/index.html` (input), `static/app.js` (send in POST body), and the `ScanRequest` pydantic model in `main.py`.
- Universe broken? `universe.py` has a tiered fallback (iShares → Wikipedia → hardcoded). Don't add 4th tier without good reason.
- Style change? `static/styles.css` only. No inline styles, no Tailwind, no preprocessor.
