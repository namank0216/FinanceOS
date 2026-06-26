"""
Stock Discovery — combined screener + Stage Engine on one page.

Default workflow:
  1. Universe = Nasdaq 100
  2. Filter = "High-conviction longs (Stage 2 + composite ≥ +50)"
  3. Click Run scan → ranked candidates
  4. Pick from list (or type ticker) → full Stage Engine detail below
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import ai_summary, data, explainers, factors, narrator, screener, stages, universe

st.title("🔍 Stock Discovery & Analysis")
st.caption("Screen the universe → pick a candidate → analyze it. Everything on one page.")
# ============================================================
# 1. Universe + filter UI
# ============================================================
st.subheader("1️⃣ Universe & filter")

c1, c2, c3 = st.columns([2, 3, 1])

universe_choice = c1.selectbox(
    "Universe",
    ["Nasdaq 100 (default)", "S&P 500", "Both combined (~600 stocks)"],
    index=0,
    help="Nasdaq 100 = ~100 large-cap, growth-tilted. S&P 500 = 500 large-caps. "
         "Both = combined (~600 unique tickers — slower scan).",
)

filter_choice = c2.selectbox(
    "Filter preset",
    [
        "🟢 High-conviction longs  (Stage 2 + composite ≥ +50)",
        "🟢 Buy candidates  (Stage 2 + composite ≥ +25)",
        "🟢 Stage 2 only  (any composite)",
        "🟡 Stage 1 basing  (watch list)",
        "🔴 Avoid list  (Stage 4 or composite ≤ -25)",
        "Show all (no filter)",
    ],
    index=0,
)

top_n = c3.slider("Top N", 10, 100, 30, 10)

# Resolve universe
if universe_choice.startswith("Nasdaq 100"):
    tickers = universe.get_nasdaq100()
    universe_label = "Nasdaq 100"
elif universe_choice.startswith("S&P 500"):
    tickers = universe.get_sp500()
    universe_label = "S&P 500"
else:
    tickers = universe.get_full_universe()
    universe_label = "S&P 500 + Nasdaq 100"


def _matches_filter(row, choice: str) -> bool:
    stage = str(row.get("stage", ""))
    comp = row.get("composite")
    if comp is None or pd.isna(comp):
        comp = (row.get("fast_composite", 0.5) - 0.5) * 200  # rough proxy

    if "High-conviction" in choice:
        return stage == "STAGE 2" and comp >= 50
    if "Buy candidates" in choice:
        return stage == "STAGE 2" and comp >= 25
    if "Stage 2 only" in choice:
        return stage == "STAGE 2"
    if "Stage 1" in choice:
        return stage == "STAGE 1"
    if "Avoid" in choice:
        return stage == "STAGE 4" or comp <= -25
    return True


def _compute_full_composite(ticker: str, bench_df: pd.DataFrame) -> dict | None:
    """Compute full 5-factor composite for one ticker. Slower than fast screen."""
    try:
        df = data.get_history(ticker, period="2y")
        if df.empty or len(df) < 200:
            return None
        df = stages.classify(df)
        info = data.get_info(ticker)
        fmp_m = data.fmp_key_metrics(ticker) if data.has_fmp() else {}
        earn = data.get_earnings_dates(ticker)

        tr, _ = factors.trend_score(df)
        mo, _ = factors.momentum_score(df, bench_df)
        q,  _ = factors.quality_score(info, fmp_m)
        v,  _ = factors.value_score(info, fmp_m)
        e,  _ = factors.earnings_score(earn, info)
        composite = factors.composite_score(tr, mo, q, v, e)
        return {
            "ticker": ticker,
            "composite": composite,
            "trend_full": round(tr, 2),
            "momentum_full": round(mo, 2),
            "quality": round(q, 2),
            "value": round(v, 2),
            "earnings": round(e, 2),
        }
    except Exception:
        return None


# ============================================================
# 2. Run scan
# ============================================================
run_btn = st.button(
    f"▶ Run scan on {len(tickers)} {universe_label} stocks",
    type="primary", use_container_width=True,
)

if run_btn:
    # Step 1 — fast screen
    with st.spinner(f"Step 1/2 — fast stage + trend × momentum scan across {len(tickers)} stocks…"):
        fast = screener.screen_universe(tickers)

    if fast.empty:
        st.error("Scan returned no results. Try refreshing in 30 seconds — yfinance may be rate-limited.")
        st.stop()

    # Step 2 — for filters that depend on full composite, run the slower per-stock fundamentals
    needs_full = any(s in filter_choice for s in ("High-conviction", "Buy candidates", "Avoid"))
    if needs_full:
        # Compute full composite only for Stage 2 (longs) or Stage 4 (avoid) — bounded
        target_stages = ["STAGE 2"] if "Avoid" not in filter_choice else ["STAGE 2", "STAGE 4"]
        target = fast[fast["stage"].isin(target_stages)]
        bench_df = data.get_history("SPY", period="2y")

        full_rows = []
        if not target.empty:
            progress = st.progress(0.0, "Step 2/2 — computing full 5-factor composite (quality × value × earnings)…")
            for i, (_, row) in enumerate(target.iterrows()):
                progress.progress((i + 1) / len(target), f"{row['ticker']}…")
                full = _compute_full_composite(row["ticker"], bench_df)
                if full:
                    full_rows.append(full)
            progress.empty()

        if full_rows:
            full_df = pd.DataFrame(full_rows)
            fast = fast.merge(full_df, on="ticker", how="left")

    st.session_state["scan_full"] = fast
    st.session_state["scan_filter_used"] = filter_choice

# ============================================================
# 3. Show results table
# ============================================================
if "scan_full" in st.session_state:
    fast = st.session_state["scan_full"]
    filter_used = st.session_state.get("scan_filter_used", filter_choice)

    filtered = fast[fast.apply(lambda r: _matches_filter(r, filter_used), axis=1)]

    # Sort: by composite desc if available, else fast_composite
    if "composite" in filtered.columns and filtered["composite"].notna().any():
        filtered = filtered.sort_values("composite", ascending=False)
    else:
        filtered = filtered.sort_values("fast_composite", ascending=False)

    filtered = filtered.head(top_n).reset_index(drop=True)

    if filtered.empty:
        st.warning(f"No stocks matched the filter '{filter_used}'. Try a less restrictive filter, "
                   "or expand the universe.")
    else:
        st.subheader(f"📊 {len(filtered)} matching stocks  (filter: {filter_used})")

        # Format display
        cols_show = ["ticker", "price", "stage", "composite", "fast_composite",
                     "trend_score", "momentum_score", "quality", "value", "earnings",
                     "12_1_mom", "rs_vs_bench", "pct_from_52w_high", "atr_pct"]
        cols_show = [c for c in cols_show if c in filtered.columns]
        disp = filtered[cols_show].copy()

        if "price" in disp.columns:
            disp["price"] = disp["price"].map(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")
        for c in ("composite",):
            if c in disp.columns:
                disp[c] = disp[c].map(lambda x: f"{x:+.0f}" if pd.notna(x) else "—")
        for c in ("fast_composite", "trend_score", "momentum_score",
                  "quality", "value", "earnings"):
            if c in disp.columns:
                disp[c] = disp[c].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
        for c in ("12_1_mom", "rs_vs_bench", "pct_from_52w_high"):
            if c in disp.columns:
                disp[c] = disp[c].map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "—")
        if "atr_pct" in disp.columns:
            disp["atr_pct"] = disp["atr_pct"].map(lambda x: f"{x:.2f}%" if pd.notna(x) else "—")

        # Stage colour highlight
        def _stage_style(val):
            return {"STAGE 1": "background:#FFD700;color:#0A0E1A",
                    "STAGE 2": "background:#22C55E;color:white",
                    "STAGE 3": "background:#FF8C00;color:white",
                    "STAGE 4": "background:#EF4444;color:white"}.get(val, "")

        st.dataframe(
            disp.style.applymap(_stage_style, subset=["stage"]),
            use_container_width=True, hide_index=True,
        )

        # Distribution stats
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Stage 1 (basing)",      f"{(fast['stage']=='STAGE 1').sum()}")
        s2.metric("Stage 2 (advancing)",   f"{(fast['stage']=='STAGE 2').sum()}")
        s3.metric("Stage 3 (topping)",     f"{(fast['stage']=='STAGE 3').sum()}")
        s4.metric("Stage 4 (declining)",   f"{(fast['stage']=='STAGE 4').sum()}")

        pct_stage2 = (fast["stage"] == "STAGE 2").sum() / len(fast) * 100
        if pct_stage2 > 50:
            st.success(f"✅ {pct_stage2:.0f}% of universe in Stage 2 — broad strength. Aggressive posture justified.")
        elif pct_stage2 > 30:
            st.info(f"ℹ {pct_stage2:.0f}% in Stage 2 — selective opportunity. Pick leaders only.")
        elif pct_stage2 > 15:
            st.warning(f"⚠ {pct_stage2:.0f}% in Stage 2 — narrow market. Tighter stops; be picky.")
        else:
            st.error(f"⛔ Only {pct_stage2:.0f}% in Stage 2 — bear/range market. Cash + defensive sectors.")

        # Narrator commentary
        screen_narrative = narrator.screen_story(filtered, filter_used)
        if screen_narrative:
            narrator.render_narrator_card(
                st,
                headline="📊 What this screen is telling you",
                narrative=screen_narrative,
                badge_color="#FF8C00",
                regime="📊 SCAN INSIGHT",
            )
            ai_ctx = (
                f"Stock screener results: {len(filtered)} stocks passed filter '{filter_used}' "
                f"out of {len(fast)} in the universe. {pct_stage2:.0f}% of the universe is in Stage 2.\n"
                f"Top 5 by composite: " +
                ", ".join([f"{r['ticker']} ({r.get('composite', 'n/a')})"
                          for _, r in filtered.head(5).iterrows()]) + ".\n"
                f"Stage distribution: Stage 1 {(fast['stage'] == 'STAGE 1').sum()}, "
                f"Stage 2 {(fast['stage'] == 'STAGE 2').sum()}, "
                f"Stage 3 {(fast['stage'] == 'STAGE 3').sum()}, "
                f"Stage 4 {(fast['stage'] == 'STAGE 4').sum()}."
            )
            ai_summary.auto_summarize(st, ai_ctx, page_kind='screen')

else:
    st.info("👆 Click **Run scan** to start. First scan takes 30-90 seconds; results cache for 30 minutes.")


# ============================================================
# 4. Drill into a stock — Stage Engine detail
# ============================================================
st.divider()
st.subheader("2️⃣ Drill into a stock")

# Build options: scanned tickers first, then "(manual entry)"
options: list[str] = ["(manual entry — type any ticker / company name)"]
if "scan_full" in st.session_state:
    fast = st.session_state["scan_full"]
    filter_used = st.session_state.get("scan_filter_used", filter_choice)
    filtered = fast[fast.apply(lambda r: _matches_filter(r, filter_used), axis=1)]
    if "composite" in filtered.columns and filtered["composite"].notna().any():
        filtered = filtered.sort_values("composite", ascending=False)
    else:
        filtered = filtered.sort_values("fast_composite", ascending=False)
    options += filtered["ticker"].head(top_n).tolist()

dc1, dc2 = st.columns([2, 3])
choice = dc1.selectbox("Pick from scan results, or choose manual entry below:",
                       options, index=1 if len(options) > 1 else 0)

ticker = None
if choice.startswith("(manual"):
    query = dc2.text_input("Ticker or company name", value="NVDA",
                           placeholder="e.g. NVDA, Nvidia, Apple, Tesla")
    if query:
        resolved, candidates = universe.resolve_ticker(query)
        if not resolved:
            st.error(f"Could not resolve '{query}' to a ticker.")
            st.stop()
        if len(candidates) > 1 and candidates[0][1]:
            opts = [f"{tk} — {nm}" for tk, nm in candidates]
            picked = st.selectbox("Multiple matches:", opts, index=0)
            ticker = picked.split(" — ")[0]
        else:
            ticker = resolved
            if candidates and candidates[0][1]:
                st.caption(f"→ Resolved to **{ticker}** ({candidates[0][1]})")
else:
    ticker = choice
    dc2.caption(f"Showing detail for **{ticker}**.")

if not ticker:
    st.stop()

# ---------- Stage Engine detail view ----------
period = st.selectbox("Chart period", ["6mo", "1y", "2y", "3y"], index=2, key="detail_period")

df = data.get_history(ticker, period=period)
if df.empty or len(df) < 200:
    st.error(f"Not enough data for {ticker} (need 200+ daily bars).")
    st.stop()

bench_df = data.get_history("SPY", period=period)
df = stages.classify(df)
last = df.iloc[-1]
stage_str = str(last["stage"])

info = data.get_info(ticker)
fmp_metrics = data.fmp_key_metrics(ticker) if data.has_fmp() else {}
earnings = data.get_earnings_dates(ticker)

tr_score, tr_comp = factors.trend_score(df)
mo_score, mo_comp = factors.momentum_score(df, bench_df)
q_score,  q_comp  = factors.quality_score(info, fmp_metrics)
v_score,  v_comp  = factors.value_score(info, fmp_metrics)
e_score,  e_comp  = factors.earnings_score(earnings, info)
composite = factors.composite_score(tr_score, mo_score, q_score, v_score, e_score)

stage_color = stages.stage_color(stage_str)
sig_color = factors.label_color(composite)
sig_label = factors.label_composite(composite)

# Decision card
narrative = explainers.stock_narrative(
    name=info.get("shortName", ticker) if info else ticker,
    sector=info.get("sector", "") if info else "",
    stage=stage_str, composite=composite,
    factor_scores={"trend": tr_score, "momentum": mo_score,
                   "quality": q_score, "value": v_score, "earnings": e_score},
    info=info,
)

actions = []
if stage_str == "STAGE 2" and composite >= 50:
    actions.append("🟢 **High-conviction long candidate.** Pair with macro regime check (Macro Center) "
                   "and valuation verdict (Valuation Engine) before entry.")
    actions.append("Use 2.5× ATR stop below 10-week MA; size by % equity risk, not by share count.")
elif stage_str == "STAGE 2" and composite >= 25:
    actions.append("🟢 **Eligible long.** Wait for a pullback to the 10-week MA for a tighter entry.")
elif stage_str == "STAGE 1":
    actions.append("🟡 **Watch list, not a buy.** Add an alert for a breakout above 30-week MA on heavy volume.")
elif stage_str == "STAGE 3":
    actions.append("🟧 **Don't add. Tighten stops on existing positions.** Distribution is in progress.")
elif stage_str == "STAGE 4":
    actions.append("🔴 **Skip entirely.** Stage 4 is not a long. Wait for a Stage 1 base to form.")
else:
    actions.append("Composite is mixed. Better setups exist — pass on this one.")

if stage_str == "STAGE 2" and composite >= 50:
    verdict = "STRONG BUY CANDIDATE"
elif stage_str == "STAGE 2" and composite >= 25:
    verdict = "BUY CANDIDATE"
elif stage_str == "STAGE 1":
    verdict = "WAIT — base forming"
elif stage_str == "STAGE 3":
    verdict = "REDUCE — uptrend exhausting"
elif stage_str == "STAGE 4":
    verdict = "AVOID — downtrend"
elif composite < -25:
    verdict = "AVOID"
else:
    verdict = "NEUTRAL"

explainers.render_decision_card(st, verdict, narrative, actions)

# Per-stock AI elaboration
ai_ctx = (
    f"Stock analysis: {info.get('shortName', ticker) if info else ticker} ({ticker}) — "
    f"{info.get('sector', '') if info else ''}\n"
    f"Stage: {stage_str}, Composite: {composite:+.1f}, Verdict: {verdict}\n"
    f"Factor scores (0-1, higher better): trend {tr_score:.2f}, momentum {mo_score:.2f}, "
    f"quality {q_score:.2f}, value {v_score:.2f}, earnings {e_score:.2f}\n"
    f"Last price ${last['close']:,.2f}, % from 52w high {last['pct_from_52w_high']:.1f}%, "
    f"30wk MA slope {last.get('ma30w_slope', 0):.2f}%/20d\n"
    f"P/E {info.get('trailingPE') if info else 'n/a'}, "
    f"revenue growth {((info.get('revenueGrowth') or 0) * 100):.1f}%, "
    f"earnings growth {((info.get('earningsGrowth') or 0) * 100):.1f}%."
)
ai_summary.auto_summarize(st, ai_ctx, page_kind='stock')

# Headline metrics
m1, m2, m3, m4 = st.columns(4)
m1.markdown(f"""
<div style="background:#11182A;padding:1rem;border-left:4px solid {stage_color}">
  <div style="color:#8a93a6;font-size:0.75rem">STAGE (Weinstein)</div>
  <div style="font-size:1.5rem;font-weight:bold;color:{stage_color}">{stages.stage_label(stage_str)}</div>
  <div style="color:#bcc3d6;font-size:0.78rem;margin-top:0.3rem">
    {explainers.GLOSSARY.get('Stage 2' if stage_str=='STAGE 2' else 'Stage 1' if stage_str=='STAGE 1' else 'Stage 3' if stage_str=='STAGE 3' else 'Stage 4', {}).get('short', '')}
  </div>
</div>""", unsafe_allow_html=True)

m2.markdown(f"""
<div style="background:#11182A;padding:1rem;border-left:4px solid {sig_color}">
  <div style="color:#8a93a6;font-size:0.75rem">COMPOSITE  (-100 to +100)</div>
  <div style="font-size:1.5rem;font-weight:bold;color:{sig_color}">{composite:+.0f}</div>
  <div style="color:{sig_color};font-size:0.85rem">{sig_label}</div>
  <div style="color:#bcc3d6;font-size:0.78rem;margin-top:0.3rem">{explainers.GLOSSARY['Composite Score']['short']}</div>
</div>""", unsafe_allow_html=True)

today_chg = (last["close"] / df["close"].iloc[-2] - 1) * 100
m3.metric("Last price", f"${last['close']:,.2f}", f"{today_chg:+.2f}% today")
m4.metric("% from 52-week high", f"{last['pct_from_52w_high']:.1f}%",
          help="Within ~15% of high = healthy. Below 25% off = meaningful correction.")

# Factor breakdown
st.subheader("Factor breakdown — what's driving the score?")
st.caption("Each factor 0-1 (higher = better). Composite is a weighted blend.")

fig = go.Figure(go.Bar(
    x=[tr_score, mo_score, q_score, v_score, e_score],
    y=["Trend", "Momentum", "Quality", "Value", "Earnings"],
    orientation="h",
    marker_color=["#22C55E" if s > 0.6 else "#FF8C00" if s > 0.4 else "#EF4444"
                  for s in [tr_score, mo_score, q_score, v_score, e_score]],
    text=[f"{s:.2f}" for s in [tr_score, mo_score, q_score, v_score, e_score]],
    textposition="outside",
))
fig.update_layout(template="plotly_dark", height=300,
                  paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                  xaxis=dict(range=[0, 1.1]), margin=dict(l=0, r=0, t=20, b=0))
st.plotly_chart(fig, use_container_width=True)

# Plain-English factor cards
def _factor_verdict(score: float, factor: str):
    if score >= 0.7:  return ("🟢 Strong",  f"Top-tier on **{factor}**.")
    if score >= 0.55: return ("🟢 Good",    f"Healthy on **{factor}**.")
    if score >= 0.4:  return ("🟡 Mixed",   f"**{factor}** is mixed — neither great nor terrible.")
    if score >= 0.25: return ("🟧 Weak",    f"**{factor}** below average. A drag on the thesis.")
    return ("🔴 Poor", f"**{factor}** is in poor shape. Significant red flag.")


f_explanations = {
    "Trend":     "Above 30-week MA and rising? The non-negotiable starting point.",
    "Momentum":  "12-month return excluding most recent month + relative strength vs SPY.",
    "Quality":   "ROIC, FCF margin, gross margin, manageable debt. Best long-term predictor.",
    "Value":     "Cheap vs earnings/sales/growth (PEG matters more than raw P/E).",
    "Earnings":  "Beating expectations and growing? Earnings momentum draws institutional buying.",
}

fcols = st.columns(5)
for col, (name, score) in zip(fcols,
                              [("Trend", tr_score), ("Momentum", mo_score),
                               ("Quality", q_score), ("Value", v_score), ("Earnings", e_score)]):
    label, _ = _factor_verdict(score, name)
    color = "#22C55E" if score >= 0.55 else "#FF8C00" if score >= 0.4 else "#EF4444"
    col.markdown(f"""
    <div style="background:#11182A;padding:0.7rem;border-left:3px solid {color};margin-bottom:0.5rem;height:140px">
      <div style="color:#8a93a6;font-size:0.7rem;text-transform:uppercase">{name}</div>
      <div style="font-size:1.1rem;font-weight:bold;color:{color}">{label}</div>
      <div style="color:#bcc3d6;font-size:0.75rem;margin-top:0.3rem;line-height:1.3">{f_explanations[name]}</div>
    </div>
    """, unsafe_allow_html=True)

# Price + stages chart
st.subheader("Price chart with stage overlay")
fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
    increasing_line_color="#22C55E", decreasing_line_color="#EF4444", name=ticker,
))
fig.add_trace(go.Scatter(x=df.index, y=df["ma30w"], name="30wk MA (Weinstein line)",
                         line=dict(color="#FF8C00", width=2)))
fig.add_trace(go.Scatter(x=df.index, y=df["ma10w"], name="10wk MA (entry pullback level)",
                         line=dict(color="#FFD700", width=1)))
fig.add_trace(go.Scatter(x=df.index, y=df["ma40w"], name="40wk MA (long-term)",
                         line=dict(color="#E6E8EE", width=1, dash="dot")))

# Stage backgrounds
prev_stage, band_start = None, None
for ts, st_val in df["stage"].items():
    if st_val != prev_stage:
        if prev_stage and band_start:
            color = {"STAGE 1": "rgba(255,215,0,0.05)",
                     "STAGE 2": "rgba(34,197,94,0.07)",
                     "STAGE 3": "rgba(255,140,0,0.07)",
                     "STAGE 4": "rgba(239,68,68,0.07)"}.get(prev_stage)
            if color:
                fig.add_vrect(x0=band_start, x1=ts, line_width=0, fillcolor=color)
        band_start, prev_stage = ts, st_val

fig.update_layout(template="plotly_dark", height=560,
                  paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                  xaxis_rangeslider_visible=False,
                  margin=dict(l=0, r=0, t=20, b=0),
                  legend=dict(orientation="h", y=1.05))
st.plotly_chart(fig, use_container_width=True)
