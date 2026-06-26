"""Sector Rotation — RRG-style chart of 11 SPDR sectors vs SPY."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, explainers, universe

st.set_page_config(page_title="Sector Rotation", layout="wide")
st.title("🌐 Sector Rotation")
st.caption("Relative Rotation Graph — find sector leadership shifts. Position trading is being in the right sectors.")

explainers.help_box(st, "How to read this page (in plain English)", """
**The single most important top-down decision for a position trader is which sectors to be in.**
50%+ of long-term alpha comes from sector selection — picking great stocks in weak sectors is
fighting the tape.

**The Relative Rotation Graph (RRG) below** plots all 11 SPDR sectors against the S&P 500 on two axes:
- **Horizontal**: Relative Strength — is the sector beating the S&P 500?
- **Vertical**: RS Momentum — is that strength accelerating or fading?

This creates 4 quadrants and the rotation tends to follow a clockwise cycle:

| Quadrant | What it means | What to do |
|---|---|---|
| 🟧 **IMPROVING** (top-left) | Sector starting to come back to life | Add gradually — could be the next leader |
| 🟢 **LEADING** (top-right) | Strong RS + accelerating | **The hunting ground** — best longs live here |
| 🟡 **WEAKENING** (bottom-right) | Lost momentum but still strong | Trim winners, don't add |
| 🔴 **LAGGING** (bottom-left) | Weak everything | Avoid longs; potential shorts |

**The dotted trail** behind each sector shows how it's been rotating over the past few weeks.
**Direction matters more than position** — a sector moving from LEADING toward WEAKENING is a
warning, while one moving from LAGGING toward IMPROVING is opportunity.
""")

with st.expander("📚 Risk-on vs Defensive — the foundational concept (read this if unsure)", expanded=False):
    explainers.render_risk_regime_explainer(st)

with st.expander("📋 Sector cheat sheet — what each sector is and how it behaves", expanded=False):
    st.markdown("**The 11 SPDR sectors, classified by behavior in different market regimes:**")
    explainers.render_sector_cheatsheet(st)
    st.markdown("""
    ---
    **Want full detail on any sector?** Use this rough mental model when looking at the RRG below
    or the sector heatmap on the Market Cockpit:

    - **All three GROWTH sectors (XLK + XLY + XLC) leading** → strong risk-on. Tech bull.
    - **All three DEFENSIVES (XLP + XLV + XLU) leading** → flight to safety. Recession fears.
    - **CYCLICALS (XLF + XLI + XLB) leading** → economic acceleration confirmed by the broad market.
    - **XLE energy leading alone with defensives** → stagflation worry (worst-case for 60/40).
    - **XLRE real estate diverging from XLU utilities** → rate-driven (when rates ease, REITs
      outperform; when rates spike, REITs get crushed harder than utilities).
    """)

period = st.selectbox("Lookback", ["3mo", "6mo", "1y"], index=1)

# Pull sector ETF + SPY history
spy = data.get_history("SPY", period=period)
if spy.empty:
    st.error("SPY data unavailable.")
    st.stop()

# Compute Relative Strength (RS) and RS-Momentum for each sector
def _rs_metrics(sec_df: pd.DataFrame, bench_df: pd.DataFrame, window: int = 14):
    """Returns (rs_ratio, rs_momentum) — JdK-style RRG axes."""
    if sec_df.empty or bench_df.empty:
        return None, None
    aligned = pd.concat([sec_df["close"].rename("sec"),
                         bench_df["close"].rename("bench")], axis=1).dropna()
    if len(aligned) < window * 2:
        return None, None
    rs = aligned["sec"] / aligned["bench"]
    rs_norm = rs / rs.rolling(window).mean() * 100
    rs_mom = rs_norm.diff(window) / rs_norm.shift(window) * 100 + 100
    return float(rs_norm.iloc[-1]), float(rs_mom.iloc[-1])


sec_data = []
for tk, name in universe.SECTOR_ETFS.items():
    df = data.get_history(tk, period=period)
    if df.empty:
        continue
    rs, mom = _rs_metrics(df, spy, window=10)
    if rs is None or mom is None:
        continue
    # Trail (last 5 weeks)
    trail = []
    for offset in [25, 20, 15, 10, 5, 0]:
        if len(df) > offset + 30:
            tr_df = df.iloc[:-offset] if offset else df
            tr_b = spy.iloc[:-offset] if offset else spy
            r, m = _rs_metrics(tr_df, tr_b, window=10)
            if r and m:
                trail.append((r, m))
    sec_data.append({"ticker": tk, "name": name, "rs": rs, "mom": mom, "trail": trail})

if not sec_data:
    st.error("Could not compute RS metrics.")
    st.stop()

# RRG chart
fig = go.Figure()

# Add quadrant backgrounds
fig.add_shape(type="rect", x0=80, y0=100, x1=100, y1=120,
              fillcolor="rgba(255,140,0,0.10)", line_width=0,
              layer="below")  # Improving (top-left)
fig.add_shape(type="rect", x0=100, y0=100, x1=120, y1=120,
              fillcolor="rgba(34,197,94,0.10)", line_width=0,
              layer="below")  # Leading (top-right)
fig.add_shape(type="rect", x0=100, y0=80, x1=120, y1=100,
              fillcolor="rgba(255,215,0,0.10)", line_width=0,
              layer="below")  # Weakening (bottom-right)
fig.add_shape(type="rect", x0=80, y0=80, x1=100, y1=100,
              fillcolor="rgba(239,68,68,0.10)", line_width=0,
              layer="below")  # Lagging (bottom-left)

# Quadrant labels
fig.add_annotation(x=85, y=118, text="<b>IMPROVING</b>", showarrow=False,
                   font=dict(color="#FF8C00", size=12))
fig.add_annotation(x=115, y=118, text="<b>LEADING</b>", showarrow=False,
                   font=dict(color="#22C55E", size=12))
fig.add_annotation(x=115, y=82, text="<b>WEAKENING</b>", showarrow=False,
                   font=dict(color="#FFD700", size=12))
fig.add_annotation(x=85, y=82, text="<b>LAGGING</b>", showarrow=False,
                   font=dict(color="#EF4444", size=12))

for s in sec_data:
    # Trail line
    if s["trail"]:
        xs = [t[0] for t in s["trail"]]
        ys = [t[1] for t in s["trail"]]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color="#8a93a6", width=1, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))
    # Current point
    quadrant_color = ("#22C55E" if s["rs"] >= 100 and s["mom"] >= 100 else
                      "#FF8C00" if s["rs"] < 100 and s["mom"] >= 100 else
                      "#FFD700" if s["rs"] >= 100 and s["mom"] < 100 else
                      "#EF4444")
    fig.add_trace(go.Scatter(
        x=[s["rs"]], y=[s["mom"]],
        mode="markers+text",
        marker=dict(size=14, color=quadrant_color, line=dict(color="white", width=1)),
        text=[s["ticker"]], textposition="top center",
        textfont=dict(color="white", size=11),
        name=s["ticker"], hovertext=f"{s['name']} ({s['ticker']})",
    ))

fig.add_hline(y=100, line_color="#374151")
fig.add_vline(x=100, line_color="#374151")
fig.update_layout(
    template="plotly_dark", height=600,
    paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
    xaxis=dict(title="Relative Strength (vs SPY) →", range=[80, 120]),
    yaxis=dict(title="RS Momentum →", range=[80, 120]),
    showlegend=False,
    margin=dict(l=0, r=0, t=20, b=0),
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("""
**How to read this chart.**
- **Top-right (LEADING — green)**: Strong RS + strong momentum. Best longs. Allocate here.
- **Top-left (IMPROVING — orange)**: Coming back to life. Add gradually.
- **Bottom-right (WEAKENING — yellow)**: Lost momentum. Trim. Don't add.
- **Bottom-left (LAGGING — red)**: Weak RS + weak momentum. Avoid longs. Short candidates.
- The dotted trail shows how each sector has rotated over the past few weeks. Direction matters more than position.
""")

st.divider()

# Ranked table
st.subheader("Ranking — by Relative Strength")
table_df = pd.DataFrame([{
    "Sector": s["name"], "ETF": s["ticker"],
    "RS (vs SPY)": s["rs"], "RS Momentum": s["mom"],
    "Quadrant": ("LEADING" if s["rs"] >= 100 and s["mom"] >= 100
                 else "IMPROVING" if s["rs"] < 100 and s["mom"] >= 100
                 else "WEAKENING" if s["rs"] >= 100 and s["mom"] < 100
                 else "LAGGING"),
} for s in sec_data]).sort_values("RS (vs SPY)", ascending=False)

table_df["RS (vs SPY)"] = table_df["RS (vs SPY)"].map(lambda x: f"{x:.1f}")
table_df["RS Momentum"] = table_df["RS Momentum"].map(lambda x: f"{x:.1f}")

st.dataframe(table_df, use_container_width=True, hide_index=True)
