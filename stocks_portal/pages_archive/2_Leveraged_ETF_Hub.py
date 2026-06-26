"""Leveraged ETF Hub — TQQQ, FNGU, SOXL + inverses, with leverage gate."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import data, explainers, macro, stages, universe

st.set_page_config(page_title="Leveraged ETF Hub", layout="wide")
st.title("⚡ Leveraged ETF Hub")
st.caption("3× ETFs treated as macro vehicles. Sized inverse to leverage. Gated by macro regime.")

explainers.help_box(st, "What you need to know about leveraged ETFs (in plain English)", """
**Why leveraged ETFs are different from regular ETFs.** A 3× ETF like TQQQ aims to deliver 3× the
**daily** move of the underlying QQQ. That sounds great when QQQ is going up. But because the leverage
resets every day, **a flat year on QQQ can turn into a big loss on TQQQ**. This is called "volatility
decay" or "leverage drag."

Think of it this way: if QQQ goes -10% one day and +11.1% the next (back to flat), a 3× version goes
-30% then +33.3% — and ends up at -6.7%, not zero. That's drag. The choppier the underlying, the
worse the drag.

**Three rules I bake into this page:**

1. **The Leverage Gate at the top is non-negotiable.** When it's 🟢 GREEN, full-size 3× positions
   are eligible. When 🟡 YELLOW, cut to half size. When 🔴 RED, **don't hold leveraged longs at all.**
2. **Size positions inverse to the leverage.** A 1% account-risk position in QQQ is a ~0.33%
   position in TQQQ. The position-sizing calculator below does this math for you so you can't make
   the classic retail mistake of sizing TQQQ like it's QQQ.
3. **Stage analysis runs on the underlying, not the ETF.** When deciding whether to buy TQQQ, look
   at QQQ's stage. The ETF chart is execution context, not signal source.

**Bottom line:** these are macro vehicles, not buy-and-hold instruments. Hold periods of weeks
to months max, with strict stops, gated by macro regime. Used right, they amplify good calls.
Used wrong, they delete accounts.
""")

# ---------- Leverage gate (mandatory top of page) ----------
state = macro.assess()
gate_color = {"GREEN": "#22C55E", "YELLOW": "#FF8C00", "RED": "#EF4444"}[state.leverage_gate]

st.markdown(f"""
<div style="background:#11182A; padding:1.2rem; border-left:6px solid {gate_color}; border-radius:4px;">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      <div style="color:#8a93a6;font-size:0.85rem;text-transform:uppercase;">Leverage Gate</div>
      <div style="font-size:2rem;font-weight:bold;color:{gate_color};">{state.leverage_gate}</div>
      <div style="color:#bcc3d6;font-size:0.95rem;">{state.regime}</div>
    </div>
    <div style="font-size:0.9rem;color:#bcc3d6;max-width:65%;text-align:right;">
      {state.summary}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------- ETF grid ----------
st.subheader("Leveraged ETFs — current state")

bull_etfs = {k: v for k, v in universe.LEVERAGED_ETFS.items() if v["leverage"] > 0}
bear_etfs = {k: v for k, v in universe.LEVERAGED_ETFS.items() if v["leverage"] < 0}

def _build_grid(etf_dict, label):
    st.markdown(f"**{label}**")
    rows = []
    for etf_tk, info in etf_dict.items():
        q = data.get_quote(etf_tk)
        u = data.get_quote(info["underlying"])
        if not q.get("last") or not u.get("last"):
            continue
        etf_chg = (q["last"] - q["prev_close"]) / q["prev_close"] * 100 if q.get("prev_close") else 0
        und_chg = (u["last"] - u["prev_close"]) / u["prev_close"] * 100 if u.get("prev_close") else 0
        # Decay proxy: if ETF moved much less than 3x underlying recently, that's drag
        rows.append({
            "ETF": etf_tk,
            "Name": info["name"],
            "Lev": info["leverage"],
            "Underlying": info["underlying"],
            "ETF Last": q["last"],
            "ETF %": etf_chg,
            "Und. %": und_chg,
            "Implied %": und_chg * info["leverage"],
            "Slip vs theo": etf_chg - (und_chg * info["leverage"]),
            "Sector": info["sector"],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No quote data.")
        return

    fmt = df.copy()
    fmt["ETF Last"] = fmt["ETF Last"].map(lambda x: f"${x:,.2f}")
    fmt["ETF %"] = fmt["ETF %"].map(lambda x: f"{x:+.2f}%")
    fmt["Und. %"] = fmt["Und. %"].map(lambda x: f"{x:+.2f}%")
    fmt["Implied %"] = fmt["Implied %"].map(lambda x: f"{x:+.2f}%")
    fmt["Slip vs theo"] = fmt["Slip vs theo"].map(lambda x: f"{x:+.2f}%")

    def _color(val):
        if isinstance(val, str):
            if val.startswith("+"): return "color:#22C55E"
            if val.startswith("-"): return "color:#EF4444"
        return ""
    st.dataframe(
        fmt.style.applymap(_color, subset=["ETF %", "Und. %", "Slip vs theo"]),
        use_container_width=True, hide_index=True,
    )

_build_grid(bull_etfs, "Bull (long)")
st.markdown("<br>", unsafe_allow_html=True)
_build_grid(bear_etfs, "Bear (inverse)")

st.divider()

# ---------- Per-ETF deep dive with decay analysis ----------
st.subheader("ETF + underlying chart")

c1, c2 = st.columns([1, 1])
sel_etf = c1.selectbox("ETF", list(universe.LEVERAGED_ETFS.keys()), index=0)
period = c2.selectbox("Period", ["3mo", "6mo", "1y", "2y"], index=2)

info = universe.LEVERAGED_ETFS[sel_etf]
underlying = info["underlying"]

etf_df = data.get_history(sel_etf, period=period)
und_df = data.get_history(underlying, period=period)

if etf_df.empty or und_df.empty:
    st.warning("Data unavailable.")
    st.stop()

# Stage analysis on underlying (the real signal source)
und_df = stages.classify(und_df)
last_und = und_df.iloc[-1]
stage = str(last_und["stage"])
stage_label = stages.stage_label(stage)
stage_action = stages.stage_action(stage)

s1, s2, s3, s4 = st.columns(4)
s1.metric(f"{underlying} Stage", stage_label)
s2.metric(f"{underlying} 30wk MA slope",
          f"{last_und['ma30w_slope']:.2f}%/20d")
s3.metric(f"{underlying} % from 52w high",
          f"{last_und['pct_from_52w_high']:.1f}%")
s4.metric("Leverage gate", state.leverage_gate)

st.info(f"**Action per Stage rule:** {stage_action}")

# Combined chart: normalize both to start=100 to show decay visually
norm_etf = etf_df["close"] / etf_df["close"].iloc[0] * 100
norm_und = und_df["close"] / und_df["close"].iloc[0] * 100
theoretical = (1 + (und_df["close"].pct_change() * info["leverage"]).fillna(0)).cumprod() * 100

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                    vertical_spacing=0.05,
                    subplot_titles=(
                        f"{sel_etf} (actual) vs {underlying} (×{info['leverage']} theoretical)",
                        "Decay = actual − theoretical (%)"))

fig.add_trace(go.Scatter(x=norm_etf.index, y=norm_etf, name=f"{sel_etf} actual",
                         line=dict(color="#FF8C00", width=2)), row=1, col=1)
fig.add_trace(go.Scatter(x=theoretical.index, y=theoretical, name=f"{info['leverage']}× theoretical",
                         line=dict(color="#22C55E", width=1, dash="dot")), row=1, col=1)
fig.add_trace(go.Scatter(x=norm_und.index, y=norm_und, name=f"{underlying} (1×)",
                         line=dict(color="#8a93a6", width=1)), row=1, col=1)

decay = norm_etf.values - theoretical.values
fig.add_trace(go.Scatter(x=norm_etf.index, y=decay, name="Decay",
                         fill="tozeroy", line=dict(color="#EF4444")), row=2, col=1)

fig.update_layout(
    template="plotly_dark", height=620,
    paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
    margin=dict(l=0, r=0, t=40, b=0),
    legend=dict(orientation="h", y=1.05),
)
st.plotly_chart(fig, use_container_width=True)

# Decay summary
total_decay = decay[-1] - decay[0] if len(decay) else 0
days = len(etf_df)
st.markdown(f"""
**Decay over {period}:** the {sel_etf} delivered **{total_decay:+.1f}%** less than the
theoretical {info['leverage']}× of {underlying}. That's the cost of daily rebalancing in
volatile conditions. {'Significant drag — typical in choppy markets.' if total_decay < -5
else 'Mild drag — markets have been directional.' if total_decay < 0
else 'No drag — the trend has been smooth.'}
""")

st.divider()

# ---------- Position sizing helper for leveraged ETFs ----------
st.subheader("Leverage-aware position sizing")
st.caption("3× ETFs need ~1/leverage smaller positions to keep portfolio risk constant.")

ps1, ps2, ps3 = st.columns(3)
equity = ps1.number_input("Equity ($)", min_value=1000.0, value=100_000.0, step=1000.0)
risk_pct = ps2.slider("Risk per trade % (target)", 0.1, 5.0, 1.0, 0.1)
stop_pct_under = ps3.slider("Stop distance (% of underlying)", 1.0, 15.0, 7.0, 0.5)

leverage = abs(info["leverage"])
# A 7% drop in underlying = 7% × leverage drop in ETF
etf_stop_pct = stop_pct_under * leverage
risk_capital = equity * risk_pct / 100
etf_price = float(etf_df["close"].iloc[-1])
shares = risk_capital / (etf_price * etf_stop_pct / 100)
notional = shares * etf_price
exposure_pct = notional / equity * 100

st.markdown(f"""
- **Underlying stop**: {stop_pct_under}% on {underlying}
- **Implied ETF stop**: ~{etf_stop_pct:.1f}% on {sel_etf} (×{leverage} amplification)
- **Risk capital**: ${risk_capital:,.2f} ({risk_pct}% of ${equity:,.0f})
- **Suggested {sel_etf} position size**: **{shares:.0f} shares** at ${etf_price:.2f} = **${notional:,.0f} notional** ({exposure_pct:.1f}% of equity)
""")

if state.leverage_gate == "RED":
    st.error("⛔ Leverage gate is RED. Skip this trade. Hold cash or use 1× ETF instead.")
elif state.leverage_gate == "YELLOW":
    st.warning(f"⚠ Leverage gate is YELLOW. Consider half size: **{shares/2:.0f} shares**.")
else:
    st.success("✅ Leverage gate is GREEN. Full size eligible.")
