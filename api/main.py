"""
Carbon Market Tracker — FastAPI Backend
Serves EUA price data, analytics, and alerts via REST API.

Run with: uvicorn api.main:app --reload
Docs at:  http://localhost:8000/docs
"""

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.analytics import enrich, get_market_summary
from pipeline.database import get_alerts_df, get_prices_df, init_db

# ── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Carbon Market Tracker API",
    description=(
        "Real-time EU ETS (EUA) carbon price data, analytics, and alerts. "
        "Built as part of a portfolio project for CFP Energy internship application."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ── Response models ────────────────────────────────────────────────────────

class PriceRecord(BaseModel):
    date: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[int]
    ma_7: Optional[float]
    ma_30: Optional[float]
    daily_return: Optional[float]
    volatility_20d: Optional[float]


class SummaryResponse(BaseModel):
    latest_price: float
    prev_price: float
    daily_change: float
    daily_change_pct: float
    week_change_pct: float
    month_change_pct: float
    ma_7: Optional[float]
    ma_30: Optional[float]
    volatility_20d: Optional[float]
    ytd_change_pct: float
    price_date: str
    market: str = "EU ETS — European Carbon Allowances (EUA)"
    unit: str = "EUR per tonne CO₂"


class AlertRecord(BaseModel):
    date: str
    type: str
    message: str
    price: float
    change_pct: float


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/", tags=["Info"])
def root():
    return {
        "name": "Carbon Market Tracker API",
        "description": "EU ETS EUA carbon price data and analytics",
        "docs": "/docs",
        "endpoints": ["/summary", "/prices", "/alerts", "/health"],
    }


@app.get("/health", tags=["Info"])
def health():
    """Simple health check."""
    df = get_prices_df(days=1)
    return {
        "status": "ok",
        "has_data": not df.empty,
        "latest_date": str(df.iloc[-1]["date"]) if not df.empty else None,
    }


@app.get("/summary", response_model=SummaryResponse, tags=["Analytics"])
def get_summary():
    """
    Latest market snapshot: current price, daily/weekly/monthly change,
    moving averages, and annualised volatility.
    """
    df = get_prices_df()
    if df.empty:
        raise HTTPException(status_code=503, detail="No price data available. Run the pipeline first.")

    summary = get_market_summary(df)
    if not summary:
        raise HTTPException(status_code=503, detail="Insufficient data for summary.")

    return SummaryResponse(**summary.__dict__)


@app.get("/prices", response_model=list[PriceRecord], tags=["Data"])
def get_prices(
    days: int = Query(default=90, ge=1, le=500, description="Number of trading days to return"),
):
    """
    Historical EUA price data with computed analytics columns.
    Use ?days=N to control how much history is returned (default 90, max 500).
    """
    df = get_prices_df(days=days)
    if df.empty:
        raise HTTPException(status_code=503, detail="No price data available.")

    df = enrich(df)

    records = []
    for _, row in df.iterrows():
        records.append(PriceRecord(
            date=str(row["date"]),
            open=_safe_float(row.get("open")),
            high=_safe_float(row.get("high")),
            low=_safe_float(row.get("low")),
            close=round(float(row["close"]), 2),
            volume=int(row["volume"]) if row.get("volume") else None,
            ma_7=_safe_float(row.get("ma_7")),
            ma_30=_safe_float(row.get("ma_30")),
            daily_return=_safe_float(row.get("daily_return")),
            volatility_20d=_safe_float(row.get("volatility_20d")),
        ))
    return records


@app.get("/alerts", response_model=list[AlertRecord], tags=["Alerts"])
def get_alerts(
    days: int = Query(default=30, ge=1, le=500, description="Number of recent alert records"),
):
    """
    Recent price alerts triggered by significant daily moves (>±3%).
    Useful for monitoring market turbulence relevant to carbon compliance costs.
    """
    df = get_alerts_df(days=days)
    if df.empty:
        return []

    return [
        AlertRecord(
            date=str(row["date"]),
            type=row["type"],
            message=row["message"],
            price=round(float(row["price"]), 2),
            change_pct=round(float(row["change_pct"]), 2),
        )
        for _, row in df.iterrows()
    ]


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    try:
        import math
        f = float(val)
        return None if math.isnan(f) else round(f, 2)
    except (TypeError, ValueError):
        return None
