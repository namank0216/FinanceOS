"""Valuation Engine — DCF + peer multiples + historical multiples → fair value range."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import ai_summary, data, explainers, narrator, universe, valuation

st.set_page_config(page_title="Valuation Engine", layout="wide")
st.title("💎 Valuation Engine")
st.caption("DCF · peer multiples · historical multiples → fair value with verdict.")

explainers.help_box(st, "What this page tells you (in plain English)", """
**Is this stock cheap, fair, or expensive?**

This is the question every value-conscious position trader asks before pulling the trigger. The page
runs 4-5 different valuation methods and combines them into a fair-value range:

1. **DCF (Discounted Cash Flow)** — projects 5 years of free cash flow + a terminal value, discounts
   back to today. The 'theoretical' fair price. Garbage-in/garbage-out though — the assumptions you
   feed it (growth rate, discount rate) drive the answer.
2. **Sector P/E** — what would the price be if this stock traded at the average P/E of its sector?
3. **Forward P/E** — what consensus earnings × forward P/E implies.
4. **Analyst consensus target** (if FMP key is set) — what the sell-side thinks.

The page averages these and gives you:
- 🟢 **UNDERVALUED** — current price is below the 25th percentile of estimates. **Long candidate** if
  technicals/macro agree.
- 🟡 **FAIR** — current price sits inside the 25-75% range of estimates. Need a catalyst to justify size.
- 🔴 **OVERVALUED** — current price is above the 75th percentile. Risky as a fresh long.

**The DCF sliders are YOUR judgment, not the system's.** Default 10% growth × 10% discount is a
"boring large-cap" baseline. Adjust based on what you know about the company.
""")

c1, c2 = st.columns([2, 4])
query = c1.text_input("Ticker or company name", value="AAPL",
                      placeholder="e.g. AAPL, Apple, Microsoft")
if not query:
    st.stop()

ticker, candidates = universe.resolve_ticker(query)
if not ticker:
    st.error(f"Could not resolve '{query}'.")
    st.stop()
if len(candidates) > 1 and candidates[0][1]:
    options = [f"{tk} — {name}" for tk, name in candidates]
    chosen = c2.selectbox("Multiple matches — pick one:", options, index=0)
    ticker = chosen.split(" — ")[0]
elif candidates and candidates[0][1]:
    c2.caption(f"→ Resolved to **{ticker}** ({candidates[0][1]})")

info = data.get_info(ticker)
quote = data.get_quote(ticker)
if not info or not quote.get("last"):
    st.error(f"No data for {ticker}.")
    st.stop()

price = quote["last"]
shares = info.get("sharesOutstanding") or quote.get("shares")
fcf = info.get("freeCashflow")
eps_ttm = info.get("trailingEps")
sales = info.get("totalRevenue")
pe = info.get("trailingPE")
sector = info.get("sector", "—")

st.subheader(f"{info.get('shortName', ticker)}  ·  {sector}")
st.caption(f"Current: ${price:,.2f}  ·  Market cap: ${quote.get('market_cap', 0)/1e9:,.1f}B  ·  Shares: {shares/1e6:,.0f}M" if shares else f"Current: ${price:,.2f}")

# ---------- Assumption sliders ----------
st.divider()
st.subheader("DCF assumptions")
a1, a2, a3 = st.columns(3)
growth = a1.slider("FCF growth (yrs 1-5, %/yr)", 0, 30, 10, 1) / 100
terminal = a2.slider("Terminal growth (%/yr)", 0.0, 5.0, 2.5, 0.25) / 100
discount = a3.slider("Discount rate / WACC (%)", 5, 20, 10, 1) / 100

# ---------- Calculate methods ----------
estimates = {}

# 1. DCF (yfinance FCF)
if fcf and shares:
    dcf = valuation.simple_dcf(fcf, growth, terminal, discount, shares)
    if dcf:
        estimates["DCF (yfinance FCF)"] = dcf["per_share"]

# 2. FMP DCF (if key)
if data.has_fmp():
    fmp_dcf = data.fmp_dcf(ticker)
    if fmp_dcf and fmp_dcf.get("dcf"):
        estimates["DCF (FMP model)"] = fmp_dcf["dcf"]

# 3. Historical P/E reversion
hist_pe = info.get("forwardPE") or info.get("trailingPE")
five_yr_avg_pe = info.get("trailingPE")  # yfinance doesn't expose 5y avg directly
# Approximate with current P/E ± 25% as a sanity band
if eps_ttm and pe:
    # Use sector average as historical reference
    sector_pe_assumption = {
        "Technology": 28, "Communication Services": 22, "Consumer Cyclical": 22,
        "Consumer Defensive": 22, "Financial Services": 14, "Healthcare": 22,
        "Industrials": 20, "Energy": 12, "Utilities": 18, "Real Estate": 30,
        "Basic Materials": 16,
    }.get(sector, 20)
    estimates[f"Sector-avg P/E ({sector_pe_assumption}×)"] = sector_pe_assumption * eps_ttm

# 4. Forward P/E
if info.get("forwardPE") and info.get("forwardEps"):
    estimates["Forward P/E (consensus)"] = info["forwardPE"] * info["forwardEps"]

# 5. Analyst target (FMP)
if data.has_fmp():
    pt = data.fmp_price_target(ticker)
    if pt and pt.get("targetConsensus"):
        estimates["Analyst consensus"] = pt["targetConsensus"]

# ---------- Fair value verdict ----------
fv = valuation.fair_value_consensus(estimates, price)

st.divider()
st.subheader("Fair value verdict")

verdict_color = valuation.verdict_color(fv.verdict)

vc1, vc2, vc3, vc4 = st.columns(4)
vc1.markdown(f"""
<div style="background:#11182A;padding:1rem;border-left:4px solid {verdict_color}">
  <div style="color:#8a93a6;font-size:0.75rem">VERDICT</div>
  <div style="font-size:1.5rem;font-weight:bold;color:{verdict_color}">{fv.verdict}</div>
</div>""", unsafe_allow_html=True)
vc2.metric("Current", f"${fv.current:.2f}")
vc3.metric("Median fair value", f"${fv.mid:.2f}", f"{fv.upside_pct:+.1f}% upside")
vc4.metric("25-75% range", f"${fv.low:.2f} – ${fv.high:.2f}")

# Narrator + AI elaboration
val_story = narrator.valuation_story(fv.verdict, fv.current, fv.mid, fv.upside_pct, estimates)
narrator.render_narrator_card(
    st,
    headline=val_story["headline"],
    narrative=val_story["narrative"],
    actions=val_story["actions"],
    badge_color=val_story["badge_color"],
    regime=val_story["regime"],
)

methods_summary = "; ".join([f"{k}: ${v:.2f}" for k, v in estimates.items()])
ai_ctx = (
    f"Valuation analysis for {ticker} ({info.get('shortName', ticker)}, {sector}):\n"
    f"Current price: ${fv.current:.2f}\n"
    f"Methods used: {methods_summary}\n"
    f"Fair-value range: ${fv.low:.2f} – ${fv.high:.2f}, median ${fv.mid:.2f}\n"
    f"Verdict: {fv.verdict} ({fv.upside_pct:+.1f}% upside to median)\n"
    f"Key fundamentals: P/E {info.get('trailingPE')}, Forward P/E {info.get('forwardPE')}, "
    f"P/S {info.get('priceToSalesTrailing12Months')}, "
    f"revenue growth {(info.get('revenueGrowth') or 0) * 100:.1f}%, "
    f"earnings growth {(info.get('earningsGrowth') or 0) * 100:.1f}%."
)
ai_summary.render_ai_button(st, ai_ctx, key=f"val_{ticker}")

# Visual
fig = go.Figure()
methods = list(estimates.keys())
values = list(estimates.values())
fig.add_trace(go.Bar(
    x=values, y=methods, orientation="h",
    marker_color="#FF8C00",
    text=[f"${v:.2f}" for v in values], textposition="outside",
    name="Method estimates",
))
fig.add_vline(x=price, line_color="#E6E8EE", line_width=3,
              annotation_text=f"Current ${price:.2f}", annotation_position="top")
fig.add_vline(x=fv.mid, line_color="#22C55E", line_dash="dot",
              annotation_text=f"Fair ${fv.mid:.2f}", annotation_position="bottom")
fig.add_vrect(x0=fv.low, x1=fv.high, fillcolor="rgba(34,197,94,0.07)", line_width=0)

fig.update_layout(
    template="plotly_dark", height=400,
    paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
    margin=dict(l=0, r=0, t=20, b=0),
    xaxis=dict(title="Per-share value ($)"),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------- Multiples comparison ----------
st.subheader("Current multiples")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("P/E (TTM)",    f"{info.get('trailingPE', 0):.1f}" if info.get('trailingPE') else "—")
m2.metric("P/E (Fwd)",    f"{info.get('forwardPE', 0):.1f}"  if info.get('forwardPE')  else "—")
m3.metric("P/S",          f"{info.get('priceToSalesTrailing12Months', 0):.2f}" if info.get('priceToSalesTrailing12Months') else "—")
m4.metric("P/B",          f"{info.get('priceToBook', 0):.2f}" if info.get('priceToBook') else "—")
m5.metric("EV/EBITDA",    f"{info.get('enterpriseToEbitda', 0):.1f}" if info.get('enterpriseToEbitda') else "—")

# Growth context
g1, g2, g3, g4 = st.columns(4)
g1.metric("Revenue growth (TTM)", f"{(info.get('revenueGrowth', 0) or 0)*100:.1f}%")
g2.metric("Earnings growth", f"{(info.get('earningsGrowth', 0) or 0)*100:.1f}%")
g3.metric("Profit margin", f"{(info.get('profitMargins', 0) or 0)*100:.1f}%")
g4.metric("ROE", f"{(info.get('returnOnEquity', 0) or 0)*100:.1f}%")

st.divider()

st.markdown("""
**How to read the verdict.**

- **UNDERVALUED** — current price is below the 25th percentile of method estimates. If the stage and momentum agree, this is a high-conviction long candidate. Position-trader sweet spot.
- **FAIR** — current price is inside the 25-75th percentile band. The market sees this name correctly. You'd want a strong catalyst (earnings beat, positive revision) to justify size.
- **OVERVALUED** — current price is above the 75th percentile. Risky as a fresh long. Consider trimming if you hold. Short candidate only if technicals also break (Stage 3 → 4 transition).

**Important caveats.**
- DCF is only as good as your growth and discount-rate assumptions. The default 10% growth × 10% discount is the textbook "boring large-cap." Adjust for the company you're evaluating.
- Sector-average P/E is a rough heuristic — it doesn't account for the company's quality differential within the sector. Use the **🧠 Stage Engine** Quality factor to refine.
- Analyst targets are biased upward (sell-side incentive structure). Treat them as a ceiling, not a target.
- This is one data point in a multi-layer decision. Don't trade off valuation alone — pair with the macro regime, sector rotation, stage, and catalyst layers.
""")
