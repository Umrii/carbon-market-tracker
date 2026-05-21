# 🌍 Carbon Market Tracker

**EU ETS EUA Price Pipeline · Analytics · Dashboard**

A Python data engineering project that tracks EU Emissions Trading System (EU ETS) carbon allowance (EUA) prices — the same market at the core of CFP Energy's business. Built as a portfolio project to demonstrate real-world pipeline, API, and data engineering skills.

---

## What It Does

The EU ETS is the world's largest carbon market. Companies that emit CO₂ must surrender one EUA (European Allowance) per tonne of emissions per year. EUA prices — currently around €70–90/t — directly affect compliance costs for thousands of European businesses.

This project:

1. **Fetches** daily EUA prices from ICE EUA Futures (`^ICEEUA`) via Yahoo Finance
2. **Stores** them in a SQLite database with upsert logic (no duplicate runs)
3. **Computes** rolling analytics: 7-day MA, 30-day MA, 20-day annualised volatility, daily returns
4. **Alerts** when the price moves more than ±3% in a single day
5. **Serves** all of this via a REST API (FastAPI)
6. **Visualises** it in an interactive dashboard (Streamlit + Plotly)

---

## Architecture

```
carbon-market-tracker/
├── pipeline/
│   ├── fetcher.py      # yfinance data ingestion
│   ├── database.py     # SQLAlchemy ORM + SQLite storage
│   ├── analytics.py    # Rolling metrics + alert detection
│   └── runner.py       # One-shot or scheduled pipeline runner
├── api/
│   └── main.py         # FastAPI REST API (4 endpoints)
├── dashboard/
│   └── app.py          # Streamlit dashboard
├── data/
│   └── carbon_tracker.db  # SQLite database (auto-created)
└── requirements.txt
```

**Tech stack:** Python · pandas · SQLAlchemy · SQLite · FastAPI · Streamlit · Plotly · APScheduler · yfinance

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the data pipeline (fetches + stores EUA data)

```bash
python -m pipeline.runner
```

To keep it running with daily auto-refresh (runs at 18:00 UTC after EU market close):

```bash
python -m pipeline.runner --schedule
```

### 3. Start the API server

```bash
uvicorn api.main:app --reload
```

API docs available at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check + latest data date |
| GET | `/summary` | Current price snapshot + all metrics |
| GET | `/prices?days=90` | Historical OHLCV + computed analytics |
| GET | `/alerts?days=30` | Recent ±3% price movement alerts |

Example response from `/summary`:

```json
{
  "latest_price": 88.76,
  "daily_change": -1.48,
  "daily_change_pct": -1.64,
  "week_change_pct": -3.31,
  "ma_7": 91.20,
  "ma_30": 87.45,
  "volatility_20d": 18.3,
  "ytd_change_pct": 4.2,
  "market": "EU ETS — European Carbon Allowances (EUA)",
  "unit": "EUR per tonne CO₂"
}
```

---

## Design Decisions

**SQLite:** Sufficient for single-machine daily ingestion of one time-series. Easy to swap for PostgreSQL by changing `DB_URL` in `database.py`.

**yfinance:** Free, no API key, covers ICE EUA Futures (`^ICEEUA`) with 2+ years of history. Backup ticker `CO2.L` (SparkChange EUA ETC) included.

**APScheduler over cron?** Python-native, cross-platform, easier for a portfolio demo. In production, this would be an Airflow DAG or a cloud scheduler (AWS EventBridge / Azure Logic Apps).

**Alert threshold of ±3%:** Based on EUA's historical average daily volatility (~1–1.5%). A ±3% move is roughly a 2σ event, worth flagging for compliance teams.

---


## About

Built by **Muhammad Atiq** — MSc Data Science student at Northumbria University with 2 years of Python backend engineering experience.

[GitHub](https://github.com/Umrii) · [LinkedIn](https://linkedin.com/in/anas-atiq) · [Portfolio](https://anasatiq.com)
