# US Stock Screener

A deployable, Finviz-inspired stock screener for **US-listed stocks** (Russell 3000). Built with FastAPI + Jinja2 + vanilla JS — no build step, no framework lock-in.

Filters by:

- **Price band** (default $5–$100)
- **P/E ratio** (default < 20)
- **Volume spike** (default > 2× the 20-day average)
- **RSI** (default 50–100)

All filters are adjustable from the UI. Results are ranked by a composite score and shown in a sortable table with sparklines and CSV export.

---

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**.

### Windows PowerShell

```powershell
cd C:\path\to\stock_screener
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If `uvicorn` is not found:

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Deploy anywhere

The app reads `PORT` and `HOST` from environment variables, so it works on any platform. Pick one:

### Render (easiest, free tier available)

1. Push this folder to a GitHub repo
2. Go to https://render.com → **New +** → **Web Service**
3. Connect your repo. Render auto-detects `render.yaml` and deploys.
4. First deploy takes ~5 min. Subsequent deploys take ~2 min.

Or even faster: click **New Blueprint Instance** and point at your repo.

### Railway / Fly.io / Heroku

`Procfile` is included. Push to the platform and it'll do the right thing.

```bash
# Heroku
heroku create
git push heroku main

# Railway
railway up
```

### Docker (any VPS, Kubernetes, AWS, GCP, Azure)

```bash
docker build -t stock-screener .
docker run -p 8000:8000 stock-screener
```

Open `http://localhost:8000`. To run on a different port:

```bash
docker run -e PORT=3000 -p 3000:3000 stock-screener
```

### Bare VPS (Ubuntu/Debian, no Docker)

```bash
# On the server
sudo apt update && sudo apt install -y python3-pip python3-venv
git clone <your-repo> && cd stock_screener
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run with nohup, or set up a systemd unit
nohup uvicorn main:app --host 0.0.0.0 --port 80 &
```

For production behind a reverse proxy (nginx, Caddy), bind to 127.0.0.1 and proxy to it.

---

## Expected runtime

The bottleneck is yfinance's per-ticker P/E lookup — there's no batch API for fundamentals.

| Universe size | First scan (cold) | Subsequent (warm cache) |
|---------------|-------------------|-------------------------|
| 100 tickers   | 30–60 sec         | 5–15 sec                |
| 500 tickers   | 3–5 min           | 30 sec                  |
| 1500 tickers  | 8–12 min          | 1–2 min                 |
| 3000 (full)   | 15–25 min         | 2–5 min                 |

**Start with 500.** That's the sweet spot for speed and meaningful coverage (top-500 by Russell 3000 weight = most large + mid caps).

---

## Rate limits

`yfinance` calls Yahoo Finance, which has no published rate limit but throttles aggressive callers (community-reported ~2000 requests/hour soft cap).

Mitigations baked in:

- **Batched OHLCV** (100 tickers per HTTP request)
- **In-memory TTL caching**: OHLCV cached 5 min, P/E cached 1 hour
- **Price-band prefilter** runs BEFORE P/E fetch (cuts ~25% of universe)
- **Sleep between requests** (0.3s OHLCV batches, 0.1s P/E)
- **Exponential backoff retry** on 429s and transient failures
- **Single asyncio lock**: only one scan at a time per process

If you hit 429s anyway, wait an hour or shrink the universe.

---

## Routes

- `GET  /`        — Main UI
- `POST /api/scan` — Run a scan (JSON body), returns `{results, stats, elapsed_s}`
- `GET  /healthz`  — Health check (for platforms)

---

## Files

| File              | Purpose                                                |
|-------------------|--------------------------------------------------------|
| `main.py`         | FastAPI app, routes, env-driven config, scan lock      |
| `screener.py`     | Filter logic + composite ranking                       |
| `data_fetcher.py` | yfinance wrapper with in-memory TTL caching            |
| `indicators.py`   | RSI (Wilder) + volume ratio                            |
| `universe.py`     | Russell 3000 fetcher with tiered fallback              |
| `templates/index.html` | Jinja2 template                                   |
| `static/styles.css`    | Finviz-inspired CSS                               |
| `static/app.js`        | Client-side fetch, sort, sparklines, CSV export   |
| `Dockerfile`      | Container build                                        |
| `Procfile`        | Heroku/Railway entry                                   |
| `render.yaml`     | Render Blueprint                                       |
| `requirements.txt`| Pinned deps                                            |
| `CLAUDE.md`       | Project memory for AI assistants                       |

---

## Disclaimer

Screening tool, not financial advice. Indicators are lagging by design. Always verify against your own research.
