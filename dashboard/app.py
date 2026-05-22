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
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .big-price {
        font-size: 2.8rem;
        font-weight: 700;
        color: #e2e8f0;
    }
    .price-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
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
</style>
""", unsafe_allow_html=True)


# ── Data loading ───────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_data(days: int):
    init_db()
    # Auto-run pipeline if DB is empty
    existing = get_prices_df(days=1)
    if existing.empty or "Synthetic" in str(existing.get("source", [""])[0] if not existing.empty else ""):
        import os
        db_path = Path(__file__).parent.parent / "data" / "carbon_tracker.db"
        if db_path.exists():
            os.remove(db_path)
        init_db()
        from pipeline.runner import run_pipeline
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
    
    **Data source:** SparkChange EUA ETC (CO2.L) via Yahoo Finance.
    """)

    st.markdown("---")
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

def fmt_change(val, suffix="%"):
    arrow = "▲" if val >= 0 else "▼"
    colour = "change-positive" if val >= 0 else "change-negative"
    return f'<span class="{colour}">{arrow} {abs(val):.2f}{suffix}</span>'

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

st.markdown(f"*As of {summary.price_date} · {summary.market} · {summary.unit}*")
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

# Candlestick or line chart depending on data quality
has_ohlc = (df["high"] - df["low"]).mean() > 0.01

if has_ohlc:
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="EUA Price",
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
        increasing_fillcolor="rgba(34,197,94,0.3)",
        decreasing_fillcolor="rgba(239,68,68,0.3)",
    ), row=1, col=1)
else:
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close"],
        name="EUA Price",
        line=dict(color="#22c55e", width=2),
        fill="tozeroy",
        fillcolor="rgba(34,197,94,0.05)",
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
    colours = ["#22c55e" if c >= o else "#ef4444"
               for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"],
        name="Volume",
        marker_color=colours,
        opacity=0.6,
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
fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True,
                 title_text="EUR/t CO₂", row=1, col=1)

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
    # Daily returns distribution
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
    "Data: ICE EUA Futures via Yahoo Finance · "
    "Built with Python, FastAPI, SQLite, Streamlit · "
    "[GitHub →](https://github.com/Umrii/carbon-market-tracker)"
)
