"""
Carbon price data fetcher — EU ETS EUA prices.

Data source hierarchy:
  1. EEX (European Energy Exchange) — official EU ETS auction settlement prices.
     Public Excel files, no API key, updated daily during auction sessions.
     URL: https://public.eex-group.com/eex/eua-auction-report/
     Price unit: EUR/t CO2 (native, no conversion needed).

  2. CO2.L (SparkChange EUA ETC on LSE) via yfinance — fallback.
     Priced in GBp; divide by ~86 to get EUR/t approx.
     Less accurate but covers gaps when EEX files are unavailable.

  3. Synthetic data — local testing only.
"""

import io
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

EEX_BASE = "https://public.eex-group.com/eex/eua-auction-report/"
EEX_FILENAME = "emission-spot-primary-market-auction-report-{year}-data.xlsx"

# CO2.L is SparkChange Physical Carbon EUA ETC on LSE, priced in GBp.
# Dividing by ~86 converts GBp → EUR/t (using ~0.86 GBP/EUR fixed approx).
CO2L_DIVISOR = 86.0


def fetch_eua_prices(days: int = 500) -> pd.DataFrame:
    """
    Fetch EUA carbon price history. Returns DataFrame with columns:
    date, open, high, low, close, volume, source.
    All prices in EUR per tonne CO₂.
    """
    # Try EEX first (official source)
    df = _fetch_from_eex(days)
    if df is not None and len(df) >= 10:
        return df

    # Fallback: CO2.L via yfinance
    logger.warning("EEX fetch failed or insufficient data. Trying CO2.L via yfinance...")
    df = _fetch_co2l(days)
    if df is not None and len(df) >= 10:
        return df

    # Last resort: synthetic
    logger.warning("All live sources failed. Using synthetic data for local testing.")
    return _generate_synthetic_data(days)


def _fetch_from_eex(days: int) -> pd.DataFrame | None:
    """
    Download and parse EEX primary market auction reports.
    Fetches the current year + as many prior years as needed to cover `days`.
    Returns a cleaned DataFrame or None on failure.
    """
    current_year = datetime.today().year
    cutoff_date = (datetime.today() - timedelta(days=days)).date()

    all_dfs = []
    # Fetch years from current back until we have enough history
    for year in range(current_year, current_year - 4, -1):
        url = EEX_BASE + EEX_FILENAME.format(year=year)
        try:
            logger.info(f"Fetching EEX auction report: {url}")
            r = requests.get(url, timeout=20, headers={"User-Agent": "CarbonMarketTracker/1.0"})
            if r.status_code != 200:
                logger.warning(f"EEX {year}: HTTP {r.status_code}")
                continue

            df_raw = pd.read_excel(io.BytesIO(r.content), engine="openpyxl", header=None)
            df = _parse_eex_excel(df_raw, year)
            if df is not None and not df.empty:
                all_dfs.append(df)
                logger.info(f"EEX {year}: {len(df)} auction records.")
                # Stop fetching older years if we have enough
                if not df.empty and df["date"].min() <= cutoff_date:
                    break

        except Exception as e:
            logger.warning(f"EEX {year} failed: {e}")
            continue

    if not all_dfs:
        return None

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    combined = combined[combined["date"] >= cutoff_date]

    logger.info(f"EEX total: {len(combined)} records, {combined['date'].min()} → {combined['date'].max()}")
    return combined


def _parse_eex_excel(df_raw: pd.DataFrame, year: int) -> pd.DataFrame | None:
    """
    Parse the EEX auction Excel format.
    The file has a header section then rows like: Date | Volume | Price | ...
    We scan for the header row containing 'Date' and 'Price'.
    """
    try:
        # Find the header row — look for a row containing both 'Date' and 'Price'
        header_row = None
        for i, row in df_raw.iterrows():
            vals = [str(v).strip().lower() for v in row.values if pd.notna(v)]
            if any("date" in v for v in vals) and any("price" in v for v in vals):
                header_row = i
                break

        if header_row is None:
            # Try assuming row 0 or 1 is header
            header_row = 0

        df = pd.read_excel(
            io.BytesIO(b""),  # placeholder — we already have df_raw
            engine="openpyxl",
            header=header_row,
        ) if False else df_raw.iloc[header_row + 1:].copy()

        # Use the header row values as column names
        col_names = df_raw.iloc[header_row].values
        df.columns = range(len(df.columns))

        # Find date column and price column by scanning header values
        date_col = price_col = vol_col = None
        for idx, val in enumerate(col_names):
            val_str = str(val).strip().lower()
            if "date" in val_str and date_col is None:
                date_col = idx
            if "price" in val_str and price_col is None:
                price_col = idx
            if "volume" in val_str and vol_col is None:
                vol_col = idx

        if date_col is None or price_col is None:
            logger.warning(f"EEX {year}: Could not find Date/Price columns in header: {col_names}")
            return None

        result = pd.DataFrame()
        result["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
        result["close"] = pd.to_numeric(df[price_col], errors="coerce")
        if vol_col is not None:
            result["volume"] = pd.to_numeric(df[vol_col], errors="coerce")
        else:
            result["volume"] = None

        spread = result["close"] * 0.005
        result["open"] = result["close"].shift(1).fillna(result["close"])
        result["high"] = (result["close"] + spread).round(2)
        result["low"] = (result["close"] - spread).round(2)
        result["source"] = f"EEX Primary Auction (official EU ETS settlement, {year})"

        result = result.dropna(subset=["date", "close"])
        result = result[result["close"] > 0]

        # Sanity check
        median = result["close"].median()
        if not (10 < median < 300):
            logger.warning(f"EEX {year}: median price €{median:.2f} looks wrong.")
            return None

        return result[["date", "open", "high", "low", "close", "volume", "source"]]

    except Exception as e:
        logger.warning(f"EEX parse error for {year}: {e}")
        return None


def _fetch_co2l(days: int) -> pd.DataFrame | None:
    """
    Fallback: fetch CO2.L (SparkChange EUA ETC) from Yahoo Finance.
    CO2.L is priced in GBp — divide by ~86 to get approximate EUR/t.
    """
    end = datetime.today()
    start = end - timedelta(days=days)
    try:
        raw = yf.download(
            "CO2.L",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if raw.empty or len(raw) < 5:
            return None

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [col[0] for col in raw.columns]
        raw = raw.rename(columns=str.capitalize)

        df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "date"
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["date"]).dt.date

        for col in ["open", "high", "low", "close"]:
            df[col] = (df[col] / CO2L_DIVISOR).round(2)

        df["source"] = "Yahoo Finance (CO2.L), GBp÷86 → EUR/t approx"
        spread = df["close"] * 0.005  # 0.5% daily spread - realistic for EUA
        df["high"] = (df["close"] + spread).round(2)
        df["low"] = (df["close"] - spread).round(2)
        df["open"] = (df["close"].shift(1).fillna(df["close"])).round(2)
        df = df.dropna(subset=["close"])

        median = df["close"].median()
        if not (30 < median < 200):
            logger.warning(f"CO2.L median €{median:.2f} looks wrong.")
            return None

        logger.info(f"CO2.L: {len(df)} rows, median €{median:.2f}/t")
        return df

    except Exception as e:
        logger.warning(f"CO2.L fetch failed: {e}")
        return None


def _generate_synthetic_data(days: int = 365) -> pd.DataFrame:
    """
    Synthetic EUA data for local testing only.
    Based on actual EUA trajectory: ~€60/t in 2024, ~€70/t in 2026.
    """
    np.random.seed(42)
    dates = pd.bdate_range(end=datetime.today(), periods=days)
    price = 65.0
    prices = []
    for _ in range(len(dates)):
        price = max(40.0, price + np.random.normal(0.04, 1.1))
        prices.append(round(price, 2))

    df = pd.DataFrame({"date": dates.date, "close": prices})
    df["open"] = df["close"].shift(1).fillna(df["close"])
    df["high"] = df[["open", "close"]].max(axis=1) + abs(np.random.normal(0, 0.6, len(df)))
    df["low"]  = df[["open", "close"]].min(axis=1) - abs(np.random.normal(0, 0.6, len(df)))
    df["volume"] = np.random.randint(50_000, 250_000, len(df))
    df["source"] = "Synthetic (EEX/Yahoo unreachable — for local testing only)"
    return df[["date", "open", "high", "low", "close", "volume", "source"]]
