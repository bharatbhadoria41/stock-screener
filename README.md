# Momentum Value Screener

Live screener for NSE Nifty 500 or NYSE stocks: P/E < 20, volume > 2× 20-day average,
RSI > 50. Ranked results in a Streamlit dashboard, auto-refreshing every 60 seconds.

See **CLAUDE.md** for architecture, design rationale, and known limitations.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py --server.port 8501
```

Open **http://localhost:8501** in your browser.

## Using the dashboard

- Pick **NSE (Nifty 500)** or **NYSE (US)** in the sidebar.
- For NYSE, choose **Quick scan** (~100 liquid large-caps, fast) or **Full scan**
  (all NYSE-listed tickers — slower and more likely to hit Yahoo Finance rate limits).
- Adjust P/E, volume-spike, and RSI thresholds live.
- Auto-refresh is on by default (every 60s). Use **Refresh Now** to force an
  immediate re-fetch, bypassing the cache.

## Notes

- First load can take 10-30+ seconds while it fetches P/E data for every ticker
  in the universe (this is then cached for 30 minutes).
- If you see a rate-limit error, wait a minute and click Refresh Now, or switch
  to Quick scan mode.
