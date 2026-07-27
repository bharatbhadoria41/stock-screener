# CLAUDE.md — Momentum Value Screener

This file gives Claude (or any future contributor) the context needed to work on this
project without re-deriving decisions from scratch.

## Purpose

A live stock screener that scans either the **NSE Nifty 500** (India) or **NYSE**
(US) universe and surfaces stocks that are simultaneously:

1. **Cheap** — Trailing P/E ratio < 20
2. **Breaking out on volume** — Today's volume > 2x the 20-day average volume
3. **In an uptrend** — RSI(14) > 50

Results are ranked by a composite score and shown in a Streamlit dashboard that
auto-refreshes every 60 seconds.

## Architecture

```
stock-screener/
├── CLAUDE.md              # this file
├── README.md              # human-facing setup/run instructions
├── requirements.txt
├── app.py                 # Streamlit UI entry point
└── src/
    ├── universe.py         # ticker universe fetching (Nifty 500 / NYSE) + fallback lists
    ├── indicators.py       # RSI, volume-ratio math
    └── screener.py         # data fetching, caching, filtering, ranking
```

### Key design decisions (and why)

- **Streamlit**, chosen over Flask/React for speed of delivery and because
  `st.cache_data(ttl=...)` gives us free, simple time-based caching, and
  `streamlit-autorefresh` gives us a periodic rerun without hand-rolled JS/WebSockets.

- **Two-tier caching.** Fundamentals (P/E) come from `yfinance`'s `.info`, which is
  slow (one HTTP call per ticker) and doesn't change minute-to-minute, so it's cached
  for **30 minutes**. Price/volume history is fetched in one batched
  `yf.download(tickers=[...])` call (much faster) and is cached for **60 seconds** to
  match the "near real-time" refresh requirement. This split is what makes a 1-minute
  refresh cadence practical against hundreds of tickers without immediately hitting
  Yahoo Finance rate limits.

- **Universe lists.** `yfinance` has no official index-constituents endpoint.
  - Nifty 500: we attempt a live fetch from NSE's public archive CSV
    (`archives.nseindia.com/content/indices/ind_nifty500list.csv`). NSE frequently
    blocks non-browser requests, so there is a bundled static fallback list
    (`src/universe.py::NIFTY_FALLBACK`) covering the large/mid-cap names. Replace/extend
    this list with an up-to-date official CSV for full 500-stock coverage.
  - NYSE: there is no free "all NYSE tickers" endpoint that isn't either huge (7000+
    symbols incl. small/illiquid names) or paywalled. We offer:
    - **Quick scan** — a curated ~100-ticker list of liquid large-cap NYSE names
      (`src/universe.py::NYSE_FALLBACK`), fast enough for 1-minute refresh.
    - **Full scan** — dynamically fetched from Nasdaq Trader's `otherlisted.txt`
      (all NYSE-listed symbols). This is slow and more likely to hit rate limits;
      it's opt-in in the sidebar, not the default.

- **Composite ranking score** (see `screener.py::compute_score`):
  `score = 0.4 * min(vol_ratio / 5, 1) + 0.3 * ((rsi - 50) / 50) + 0.3 * ((20 - pe) / 20)`
  All three components are normalized to roughly [0, 1] before weighting so that no
  single metric (e.g. a huge volume spike) dominates the ranking by scale alone. This
  is a reasonable default, not a proven trading signal — tune the weights in one place.

## Known limitations (be upfront about these with the user)

- `yfinance` is an **unofficial** wrapper around Yahoo Finance endpoints. It has no
  SLA, can silently rate-limit or return partial data, and is not suitable for
  production trading decisions.
- "Near real-time" here means **1-minute polling**, not streaming tick data. True
  real-time would require a paid market-data feed/websocket.
- P/E ratio from `.info` is Yahoo's trailing P/E, which can be `None` for
  loss-making companies — these are filtered out (can't evaluate P/E < 20 without a
  P/E).
- Scanning the full Nifty 500 or full NYSE list every single minute may still get
  throttled by Yahoo depending on network conditions; if you see empty results or
  errors, widen the refresh interval or use "Quick scan" mode.

## Running

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

Then open `http://localhost:8501`.

## Conventions for future changes

- Keep all tunable thresholds (PE cutoff, volume multiple, RSI cutoff, refresh
  interval, score weights) as constants/sidebar inputs — never hardcode them deep
  inside a function.
- Any new data source call should go through `screener.py`'s cached wrapper
  functions, not be called ad hoc from `app.py`, so caching/rate-limit behavior
  stays centralized.
- If adding a new market/universe, follow the existing pattern in `universe.py`:
  a live-fetch function + a static fallback list + a single public
  `get_<market>_symbols()` entry point.
