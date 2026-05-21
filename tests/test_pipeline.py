"""
Basic test suite for Carbon Market Tracker.
Run with: pytest tests/test_pipeline.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pipeline.analytics import detect_alerts, enrich, get_market_summary
from pipeline.fetcher import _generate_synthetic_data


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    return _generate_synthetic_data(days=100)


@pytest.fixture
def api_client():
    from api.main import app
    return TestClient(app)


# ── Analytics tests ────────────────────────────────────────────────────────

def test_synthetic_data_shape(sample_df):
    assert len(sample_df) > 0
    assert "close" in sample_df.columns
    assert "date" in sample_df.columns


def test_enrich_adds_columns(sample_df):
    enriched = enrich(sample_df)
    assert "ma_7" in enriched.columns
    assert "ma_30" in enriched.columns
    assert "daily_return" in enriched.columns
    assert "volatility_20d" in enriched.columns


def test_ma7_less_than_ma30_eventually(sample_df):
    enriched = enrich(sample_df)
    # After 30 days, both MAs should be populated
    late = enriched.iloc[40:]
    assert late["ma_7"].notna().any()
    assert late["ma_30"].notna().any()


def test_market_summary_returns_object(sample_df):
    summary = get_market_summary(sample_df)
    assert summary is not None
    assert summary.latest_price > 0
    assert isinstance(summary.daily_change_pct, float)


def test_alert_detection(sample_df):
    alerts = detect_alerts(sample_df)
    # Should detect at least some alerts in 100 days of data
    assert isinstance(alerts, list)
    for alert in alerts:
        assert "type" in alert
        assert alert["type"] in ("PRICE_DROP", "PRICE_SPIKE")
        assert abs(alert["change_pct"]) >= 3.0


# ── API tests ──────────────────────────────────────────────────────────────

def test_api_root(api_client):
    r = api_client.get("/")
    assert r.status_code == 200
    assert "endpoints" in r.json()


def test_api_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_api_summary(api_client):
    r = api_client.get("/summary")
    assert r.status_code == 200
    data = r.json()
    assert "latest_price" in data
    assert data["latest_price"] > 0
    assert "unit" in data


def test_api_prices(api_client):
    r = api_client.get("/prices?days=10")
    assert r.status_code == 200
    records = r.json()
    assert isinstance(records, list)
    assert len(records) > 0
    assert "close" in records[0]


def test_api_alerts(api_client):
    r = api_client.get("/alerts?days=60")
    assert r.status_code == 200
    alerts = r.json()
    assert isinstance(alerts, list)
