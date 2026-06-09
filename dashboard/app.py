"""
Carbon Market Tracker — Streamlit Dashboard
EU ETS Carbon Price Analytics & Monitoring

Run with: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pipeline.analytics import enrich, get_market_summary
from pipeline.database import get_alerts_df, get_prices_df, init_db
from llm_insight import get_market_insight

# ── Page config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Carbon Market Tracker",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .change-positive { color: #22c55e; font-weight: 600; }
    .change-negative { color: #ef4444; font-weight: 600; }
    .alert-drop {
        background: rgba(239, 68, 68, 0.1);
        border-left: 4px solid #ef4444;
        padding: 10px 16px;
        border-radius: 4px;
        margin: 6px 0;
        font-size: 0.9rem;
    }
    .alert-spike {
        background: rgba(34, 197, 94, 0.1);
        border-left: 4px solid #22c55e;
        padding: 10px 16px;
        border-radius: 4px;
        margin: 6px 0;
        font-size: 0.9rem;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin: 24px 0 12px 0;
        border-bottom: 1px solid #1e293b;
        padding-bottom: 8px;
    }
    /* Insight button — dark theme */
    div[data-testid="stButton"].insight-btn > button {
        background: rgba(96, 165, 250, 0.06);
        border: 1px solid #334155;
        color: #94a3b8;
        border-radius: 8px;
        font-size: 0.82rem;
        letter-spacing: 0.3px;
        padding: 0.35rem 0.9rem;
        transition: border-color 0.2s, color 0.2s, background 0.2s;
    }
    div[data-testid="stButton"].insight-btn > button:hover {
        border-color: #60a5fa;
        color: #e2e8f0;
        background: rgba(96, 165, 250, 0.14);
    }
</style>
""", unsafe_allow_html=True)


# ── Data loading ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data(days: int):
    init_db()
    from pipeline.database import (
        delete_synthetic_records, purge_invalid_prices, is_price_data_valid,
    )
    from pipeline.runner import run_pipeline

    delete_synthetic_records()
    purge_invalid_prices()

    if not is_price_data_valid():
        # Data is missing, stale, or corrupt (e.g. row-indices stored as prices).
        # Wipe everything first — upsert skips existing dates, so corrupt records
        # for valid dates would never be overwritten without a full wipe.
        from pipeline.database import delete_all_prices
        delete_all_prices()
        run_pipeline()

    df = get_prices_df(days=days)
    if df is None or df.empty:
        return pd.DataFrame(), None, pd.DataFrame()
    df_enriched = enrich(df)
    summary = get_market_summary(df)
    alerts_df = get_alerts_df(days=60)
    if alerts_df is None:
        alerts_df = pd.DataFrame()
    return df_enriched, summary, alerts_df


# ── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Settings")
    days = st.slider("History (trading days)", min_value=30, max_value=500, value=180, step=10)
    show_ma7 = st.checkbox("Show 7-day MA", value=True)
    show_ma30 = st.checkbox("Show 30-day MA", value=True)
    show_volume = st.checkbox("Show Volume", value=True)

    st.markdown("---")
    st.markdown("### 📚 About")
    st.markdown("""
    **EU ETS** — the world's first and largest carbon market, 
    covering ~40% of EU greenhouse gas emissions.
    
    **EUA** (EU Allowance) = right to emit 1 tonne of CO₂.
    Companies must surrender one EUA per tonne emitted annually.
    
    **Data source:** EEX Primary Market Auction Reports (official EU ETS settlement prices).
    """)

    st.markdown("---")
    if st.button("🔄 Force Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Built by Muhammad Atiq · [GitHub](https://github.com/Umrii)")


# ── Load data ──────────────────────────────────────────────────────────────

df, summary, alerts_df = load_data(days)

# ── Header ─────────────────────────────────────────────────────────────────

st.markdown("# 🌍 Carbon Market Tracker")
st.markdown("**EU Emissions Trading System (EU ETS) · EUA Price Analytics**")

if df.empty or summary is None:
    st.error("⚠️ No data available. Please run the pipeline first: `python -m pipeline.runner`")
    st.stop()

# ── Top KPI strip ──────────────────────────────────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("EUA Price", f"€{summary.latest_price:.2f}", f"{summary.daily_change:+.2f} today")
with col2:
    st.metric("Day Change", f"{summary.daily_change_pct:+.2f}%")
with col3:
    st.metric("Week Change", f"{summary.week_change_pct:+.2f}%")
with col4:
    st.metric("Month Change", f"{summary.month_change_pct:+.2f}%")
with col5:
    st.metric("YTD Change", f"{summary.ytd_change_pct:+.2f}%")

# ── Metadata row + insight button (right-aligned) ──────────────────────────

col_meta, col_btn = st.columns([4, 1])
with col_meta:
    st.markdown(f"*As of {summary.price_date} · {summary.market} · {summary.unit}*")
with col_btn:
    st.markdown('<div class="insight-btn">', unsafe_allow_html=True)
    if st.button("🤖 Generate Insight", use_container_width=True, key="insight_btn"):
        with st.spinner("Generating insight…"):
            st.session_state["market_insight"] = get_market_insight(
                latest_price=summary.latest_price,
                change_pct=summary.daily_change_pct,
                ma_7=summary.ma_7 or summary.latest_price,
                ma_30=summary.ma_30 or summary.latest_price,
                volatility=summary.volatility_20d or 0.0,
            )
    st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.get("market_insight"):
    st.info(st.session_state["market_insight"])

st.markdown("---")

# ── Main chart ─────────────────────────────────────────────────────────────

st.markdown('<div class="section-header">Price History</div>', unsafe_allow_html=True)

rows = 2 if show_volume else 1
row_heights = [0.75, 0.25] if show_volume else [1.0]

fig = make_subplots(
    rows=rows, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=row_heights,
)

# Price line chart (EEX auction settlement prices — one price per day)
fig.add_trace(go.Scatter(
    x=df["date"],
    y=df["close"],
    name="EUA Price",
    line=dict(color="#22c55e", width=2),
), row=1, col=1)

# Moving averages
if show_ma7:
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["ma_7"],
        name="7-day MA",
        line=dict(color="#f59e0b", width=1.5, dash="dot"),
    ), row=1, col=1)

if show_ma30:
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["ma_30"],
        name="30-day MA",
        line=dict(color="#60a5fa", width=2),
    ), row=1, col=1)

# Volume bars
if show_volume:
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"],
        name="Volume",
        marker_color="#60a5fa",
        opacity=0.4,
    ), row=2, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)

fig.update_layout(
    height=520,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8"),
    xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=10, b=0),
)
fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True)

# Compute price axis range explicitly from data so it is never contaminated
# by the volume subplot's scale — required for correct rendering across all
# Streamlit + Plotly version combinations.
price_vals = df["close"].dropna()
if not price_vals.empty:
    pad = (price_vals.max() - price_vals.min()) * 0.1 or price_vals.mean() * 0.05
    price_range = [float(price_vals.min() - pad), float(price_vals.max() + pad)]
else:
    price_range = None

fig.update_yaxes(
    gridcolor="rgba(255,255,255,0.05)", showgrid=True,
    title_text="EUR/t CO₂", row=1, col=1,
    range=price_range,
)

st.plotly_chart(fig, use_container_width=True)

# ── Analytics row ──────────────────────────────────────────────────────────

st.markdown('<div class="section-header">Analytics</div>', unsafe_allow_html=True)

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Moving Averages & Volatility**")
    ma_data = {
        "Metric": ["7-day MA", "30-day MA", "20-day Ann. Volatility", "Price vs 30d MA"],
        "Value": [
            f"€{summary.ma_7:.2f}/t" if summary.ma_7 else "—",
            f"€{summary.ma_30:.2f}/t" if summary.ma_30 else "—",
            f"{summary.volatility_20d:.1f}%" if summary.volatility_20d else "—",
            f"{((summary.latest_price - summary.ma_30) / summary.ma_30 * 100):+.1f}%" if summary.ma_30 else "—",
        ]
    }
    st.dataframe(pd.DataFrame(ma_data), hide_index=True, use_container_width=True)

with col_b:
    returns = df["daily_return"].dropna()
    fig2 = go.Figure(go.Histogram(
        x=returns,
        nbinsx=40,
        marker_color="#60a5fa",
        opacity=0.75,
        name="Daily Return %",
    ))
    fig2.add_vline(x=0, line_color="#94a3b8", line_dash="dash")
    fig2.add_vline(x=returns.mean(), line_color="#f59e0b", line_dash="dot",
                   annotation_text=f"μ={returns.mean():.2f}%")
    fig2.update_layout(
        title="Daily Return Distribution",
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8"),
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis=dict(title="Daily Return (%)", gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(title="Frequency", gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Alerts ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-header">Price Alerts (±3% Daily Moves)</div>', unsafe_allow_html=True)

if alerts_df.empty:
    st.info("No significant price movements detected in the selected period.")
else:
    recent_alerts = alerts_df.head(10)
    for _, alert in recent_alerts.iterrows():
        css_class = "alert-drop" if alert["type"] == "PRICE_DROP" else "alert-spike"
        icon = "🔴" if alert["type"] == "PRICE_DROP" else "🟢"
        st.markdown(
            f'<div class="{css_class}">{icon} <strong>{alert["date"]}</strong> — {alert["message"]}</div>',
            unsafe_allow_html=True,
        )

# ── Footer ─────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption(
    "Carbon Market Tracker · EU ETS EUA Price Pipeline · "
    "Data: EEX Primary Market Auction Reports · "
    "Built with Python, FastAPI, SQLite, Streamlit · "
    "[GitHub →](https://github.com/Umrii/carbon-market-tracker)"
)