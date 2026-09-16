# NSE Institutional Dashboard

Python pipeline that fetches market data, scores NSE watchlists, and writes a self-contained Apple-inspired HTML dashboard. Streamlit launches generation and previews the HTML.

## Quick start

```bash
cd C:\NSE_Dashboard
python -m pip install -r requirements.txt
python generate_dashboard.py
streamlit run app.py
```

Output: `output/dashboard.html`

## Configuration

No API keys are required. Data is fetched keylessly via **yfinance**, **nselib**, and **nsepython**; `.env` is only reserved for future integrations.

## Data sources

| Need | Library |
|------|---------|
| Historical OHLC + fundamentals | **yfinance** |
| NSE reference (FII/DII, index constituents, option chain) | **nselib** (primary), **nsepython** (fallback) |

YAML watchlists in `config/watchlists.yaml` remain the offline safety net when NSE constituent fetches fail.

## Notes

- Watchlists live in `config/watchlists.yaml` (sample lists only).
- Re-run hourly to populate change detection against `output/snapshots/latest.json`.
