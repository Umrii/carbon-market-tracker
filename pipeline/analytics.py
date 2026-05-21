"""
Analytics engine for EU ETS carbon price data.
Computes rolling metrics, detects anomalies, and generates alerts.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Alert thresholds
DAILY_DROP_THRESHOLD = -3.0   # % drop in one day → alert
DAILY_SPIKE_THRESHOLD = 3.0   # % spike in one day → alert
VOLATILITY_WINDOW = 20        # days for rolling volatility calc


@dataclass
class MarketSummary:
    latest_price: float
    prev_price: float
    daily_change: float
    daily_change_pct: float
    week_change_pct: float
    month_change_pct: float
    ma_7: float
    ma_30: float
    volatility_20d: float
    ytd_change_pct: float
    price_date: str
    market: str = "EU ETS — European Carbon Allowances (EUA)"
    unit: str = "EUR per tonne CO₂"

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add computed columns to the price DataFrame:
    - daily_return, ma_7, ma_30, volatility_20d, pct_from_ma30
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    df["daily_return"] = df["close"].pct_change() * 100
    df["ma_7"] = df["close"].rolling(7).mean().round(2)
    df["ma_30"] = df["close"].rolling(30).mean().round(2)
    # Annualised vol: std of daily returns * sqrt(252)
    df["volatility_20d"] = (
        df["close"].pct_change().rolling(VOLATILITY_WINDOW).std() * (252 ** 0.5) * 100
    ).round(2)
    df["pct_from_ma30"] = ((df["close"] - df["ma_30"]) / df["ma_30"] * 100).round(2)
    return df


def get_market_summary(df: pd.DataFrame) -> Optional[MarketSummary]:
    """Compute a snapshot summary from the latest data."""
    if df is None or len(df) < 2:
        return None

    df = enrich(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    daily_change = latest["close"] - prev["close"]
    daily_change_pct = (daily_change / prev["close"]) * 100

    week_row = df.iloc[-6] if len(df) >= 6 else df.iloc[0]
    month_row = df.iloc[-22] if len(df) >= 22 else df.iloc[0]

    # YTD: find first trading day of the current year
    current_year = pd.to_datetime(latest["date"]).year
    ytd_rows = df[pd.to_datetime(df["date"]).dt.year == current_year]
    ytd_start_price = ytd_rows.iloc[0]["close"] if not ytd_rows.empty else latest["close"]

    return MarketSummary(
        latest_price=round(latest["close"], 2),
        prev_price=round(prev["close"], 2),
        daily_change=round(daily_change, 2),
        daily_change_pct=round(daily_change_pct, 2),
        week_change_pct=round((latest["close"] - week_row["close"]) / week_row["close"] * 100, 2),
        month_change_pct=round((latest["close"] - month_row["close"]) / month_row["close"] * 100, 2),
        ma_7=round(latest["ma_7"], 2) if pd.notna(latest["ma_7"]) else None,
        ma_30=round(latest["ma_30"], 2) if pd.notna(latest["ma_30"]) else None,
        volatility_20d=round(latest["volatility_20d"], 2) if pd.notna(latest["volatility_20d"]) else None,
        ytd_change_pct=round((latest["close"] - ytd_start_price) / ytd_start_price * 100, 2),
        price_date=str(latest["date"]),
    )


def detect_alerts(df: pd.DataFrame) -> list[dict]:
    """
    Scan enriched price data for alert conditions.
    Returns a list of alert dicts for any triggered thresholds.
    """
    df = enrich(df)
    alerts = []

    for _, row in df.iterrows():
        if pd.isna(row["daily_return"]):
            continue

        if row["daily_return"] <= DAILY_DROP_THRESHOLD:
            alerts.append({
                "date": row["date"],
                "type": "PRICE_DROP",
                "message": (
                    f"EUA price dropped {row['daily_return']:.2f}% to "
                    f"€{row['close']:.2f}/t on {row['date']}"
                ),
                "price": row["close"],
                "change_pct": row["daily_return"],
            })

        elif row["daily_return"] >= DAILY_SPIKE_THRESHOLD:
            alerts.append({
                "date": row["date"],
                "type": "PRICE_SPIKE",
                "message": (
                    f"EUA price spiked {row['daily_return']:.2f}% to "
                    f"€{row['close']:.2f}/t on {row['date']}"
                ),
                "price": row["close"],
                "change_pct": row["daily_return"],
            })

    return alerts
