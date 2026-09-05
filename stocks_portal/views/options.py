"""
⚡ Options Flow — institutional / whale positioning proxy.

Layout:
  1. Top hero strip — universe + thresholds
  2. AI briefing slot (filled LAST with full flow context)
  3. Top whale flows table — sorted by premium $
  4. Per-ticker aggregate (net bullish vs bearish $)
  5. Filter buttons by classification
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import ai_summary, options_flow

st.title("⚡ Options Flow")
st.caption("Institutional / whale positioning — strikes where size is moving today.")

with st.expander("📌 What this page is and is NOT (read once)", expanded=False):
    st.markdown("""
**This is a free-data proxy for institutional options flow**, derived from yfinance options chains.
We rank contracts by:
- **Volume / Open Interest ratio** — high = NEW positions being opened today
- **Premium $** — total dollars flowing into the strike (institutional sizing)
- **Bid/Ask placement** — last price near ask = aggressive buyer; near bid = aggressive seller
- **Strike vs spot + days to expiration** — distinguishes directional bets from hedges

**What we CAN see:**
- 🟢 **BULLISH (call BTO)** — calls bought aggressively at the ask
- 🔴 **BEARISH (put BTO)** — puts bought aggressively at the ask
- 🛡 **HEDGE** — long-dated OTM puts (institutions protecting equity holdings)
- 💰 **SHORT VOL** — calls/puts sold (income, covered calls, willing-to-buy puts)
- 🚀 **BULLISH SPEC** — far-OTM long-dated calls (lottery tickets, often pre-catalyst)

**What we CANNOT see** (requires paid feeds — UnusualWhales/FlowAlgo at $40-200/mo):
- Real-time sweeps and block trades
- Multi-leg strategies (collars, straddles)
- Time-and-sales granularity (so bid/ask placement is approximate)

Use this alongside Macro and Stock Discovery — not as a standalone signal.
""")

# ============================================================
# Controls
# ============================================================
c1, c2, c3 = st.columns([3, 1, 1])
universe = c1.multiselect(
    "Tickers to scan",
    options_flow.WHALE_UNIVERSE,
    default=options_flow.WHALE_UNIVERSE[:18],
)
min_voi = c2.slider("Min V/OI", 1.0, 10.0, 2.0, 0.5,
                    help="Volume / Open Interest. Higher = more 'new' positioning.")
min_premium_k = c3.slider("Min premium ($K)", 50, 1000, 100, 50,
                          help="Minimum dollar size to flag a contract.")
min_premium = min_premium_k * 1000

# Reserve AI slot at top
ai_slot = st.empty()

# ============================================================
# Scan
# ============================================================
if not universe:
    st.warning("Pick at least one ticker.")
    st.stop()

with st.spinner(f"Scanning {len(universe)} tickers across the next 6 expirations… (~30-60s on first run, cached 10 min)"):
    flow = options_flow.scan_universe(universe, min_voi=min_voi, min_premium=min_premium)

if flow.empty:
    st.info("No unusual flow above thresholds. Try lowering Min V/OI or Min premium.")
    st.stop()

# ============================================================
# Per-ticker aggregate
# ============================================================
agg = options_flow.aggregate_by_ticker(flow)
if not agg.empty:
    st.subheader("Per-ticker net positioning today")
    show_cols = [c for c in ["ticker", "bullish", "bearish", "hedge", "short_vol",
                              "neutral", "net_directional_$"] if c in agg.columns]
    agg_disp = agg[show_cols].copy()
    for c in show_cols:
        if c != "ticker":
            agg_disp[c] = agg_disp[c].map(lambda x: f"${x/1e6:,.2f}M" if abs(x) >= 1e6
                                          else f"${x/1e3:,.0f}K" if abs(x) >= 1e3 else "—")

    def _color_net(val):
        if isinstance(val, str) and val.startswith("$") and "M" in val:
            try:
                num = float(val.replace("$", "").replace("M", "").replace(",", ""))
                if num > 1: return "background:rgba(34,197,94,0.25)"
                if num < -1: return "background:rgba(239,68,68,0.25)"
            except Exception: pass
        return ""
    st.dataframe(
        agg_disp.style.map(_color_net, subset=["net_directional_$"]) if "net_directional_$" in agg_disp.columns else agg_disp,
        use_container_width=True, hide_index=True,
    )

# ============================================================
# Filter buttons
# ============================================================
st.subheader("Top whale flows")
filter_choice = st.radio(
    "Filter by classification",
    ["All", "🟢 Bullish", "🔴 Bearish", "🛡 Hedges", "💰 Short Vol", "🚀 Speculative"],
    horizontal=True,
)

filt = flow.copy()
if "Bullish" in filter_choice:
    filt = filt[filt["classification"].str.contains("BULLISH")]
elif "Bearish" in filter_choice:
    filt = filt[filt["classification"].str.contains("BEARISH")]
elif "Hedges" in filter_choice:
    filt = filt[filt["classification"].str.contains("HEDGE")]
elif "Short Vol" in filter_choice:
    filt = filt[filt["classification"].str.contains("SHORT VOL")]
elif "Speculative" in filter_choice:
    filt = filt[filt["classification"].str.contains("SPEC")]

# ============================================================
# Top flows table
# ============================================================
disp = filt.head(40).copy()
if not disp.empty:
    disp["premium_$"] = disp["premium_$"].map(
        lambda x: f"${x/1e6:.2f}M" if x >= 1e6 else f"${x/1e3:.0f}K"
    )
    disp["strike"] = disp["strike"].map(lambda x: f"${x:,.2f}")
    disp["spot"] = disp["spot"].map(lambda x: f"${x:,.2f}")
    disp["last"] = disp["last"].map(lambda x: f"${x:.2f}")
    disp["IV %"] = disp["IV %"].map(lambda x: f"{x:.1f}%")
    disp["volume"] = disp["volume"].map(lambda x: f"{x:,}")
    disp["OI"] = disp["OI"].map(lambda x: f"{x:,}")
    disp["V/OI"] = disp["V/OI"].map(lambda x: f"{x:.1f}×")

    # Rename for display
    disp = disp.rename(columns={
        "ticker": "Ticker", "type": "Type", "strike": "Strike",
        "spot": "Spot", "moneyness": "Moneyness", "expiration": "Expiration",
        "DTE": "DTE", "volume": "Volume", "OI": "Open Int.",
        "V/OI": "V/OI", "IV %": "IV %", "last": "Last",
        "premium_$": "Premium $", "classification": "Read",
    })
    st.dataframe(disp, use_container_width=True, hide_index=True)

# ============================================================
# AI BRIEFING — populated last with full context
# ============================================================
total_bullish = flow[flow["classification"].str.contains("BULLISH")]["premium_$"].sum()
total_bearish = flow[flow["classification"].str.contains("BEARISH")]["premium_$"].sum()
total_hedge = flow[flow["classification"].str.contains("HEDGE")]["premium_$"].sum()
total_shortvol = flow[flow["classification"].str.contains("SHORT VOL")]["premium_$"].sum()

top5 = flow.head(5)
top_lines = "\n".join(
    f"  {r['ticker']} {r['type']} ${r['strike']:.0f} exp {r['expiration']} — "
    f"{r['volume']:,} contracts, ${r['premium_$']/1e6:.2f}M premium, V/OI {r['V/OI']}× — "
    f"{r['classification']}"
    for _, r in top5.iterrows()
)

ctx = f"""Top 5 institutional options flows today:
{top_lines}

Aggregate premium dollars:
  Bullish (call BTO + put STO):  ${total_bullish/1e6:.1f}M
  Bearish (put BTO + call STO):  ${total_bearish/1e6:.1f}M
  Hedges (OTM put BTO):          ${total_hedge/1e6:.1f}M
  Short Vol (premium selling):   ${total_shortvol/1e6:.1f}M
  Net directional (bullish - bearish): ${(total_bullish - total_bearish)/1e6:+.1f}M
"""

# Fallback if no AI configured
net = total_bullish - total_bearish
if net > 5e6:
    fb = (f"<b>Verdict:</b> 🟢 BULLISH FLOW<br>"
          f"<b>Why:</b> Net call buying + put selling totals ${net/1e6:.1f}M today. "
          f"Top: {top5.iloc[0]['ticker']} {top5.iloc[0]['type']} ${top5.iloc[0]['strike']:.0f} ({top5.iloc[0]['classification']}).<br>"
          f"<b>Action:</b> Lean with the flow — confirm with macro regime + sector leadership.<br>"
          f"<b>Watch for:</b> Bullish premium fading or hedge $ spiking.")
elif net < -5e6:
    fb = (f"<b>Verdict:</b> 🔴 BEARISH FLOW<br>"
          f"<b>Why:</b> Net put buying + call selling at ${-net/1e6:.1f}M. Top: "
          f"{top5.iloc[0]['ticker']} {top5.iloc[0]['type']} ${top5.iloc[0]['strike']:.0f}.<br>"
          f"<b>Action:</b> Reduce exposure, watch the names with concentrated bearish flow.<br>"
          f"<b>Watch for:</b> Hedges turning into outright shorts (capitulation often follows).")
else:
    fb = (f"<b>Verdict:</b> 🟡 MIXED FLOW<br>"
          f"<b>Why:</b> Bullish ${total_bullish/1e6:.1f}M vs bearish ${total_bearish/1e6:.1f}M — no decisive lean.<br>"
          f"<b>Action:</b> No conviction trade from options. Use other signals.<br>"
          f"<b>Watch for:</b> Imbalance building in single names — that's where the action is.")

with ai_slot.container():
    ai_summary.auto_summarize(st, ctx, page_kind="smart_money", fallback_text=fb)

st.caption("⚠ Options-flow proxy from free yfinance data, not a paid live tape. "
           "Educational, not financial advice.")
