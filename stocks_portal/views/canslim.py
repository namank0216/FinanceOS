"""
CAN SLIM + Minervini Trend Template scanner.

Two of the most battle-tested growth-investing systems, combined.
Both originated from traders who turned <$100K into eight-figure portfolios.
Both demand the SAME thing: high-quality stock in a strong uptrend, during a
confirmed market uptrend.

This page runs the full pipeline and ranks every stock in your chosen universe.
"""

import pandas as pd
import streamlit as st

from lib import ai_summary, canslim_minervini as cm, universe

st.title("🏆 CAN SLIM + Minervini Scanner")
st.caption("O'Neil's CAN SLIM (fundamentals + market) × Minervini's Trend Template "
           "(8 price/MA criteria) — combined growth screener.")

# ============================================================
# Top section — market gate
# ============================================================
market_ok, market_msg = cm.market_direction_ok()
gate_color = "#15803D" if market_ok else "#7F1D1D"
gate_emoji = "🟢" if market_ok else "🔴"
st.markdown(
    f"<div style='background:{gate_color};padding:0.9rem 1.1rem;border-radius:6px;"
    f"margin-bottom:0.8rem'>"
    f"<div style='color:white;font-size:0.75rem;text-transform:uppercase;"
    f"letter-spacing:0.1rem'>CAN SLIM 'M' — Market Direction Gate</div>"
    f"<div style='color:white;font-size:1.05rem;margin-top:0.2rem'>"
    f"{gate_emoji} {market_msg}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

if not market_ok:
    st.warning(
        "⚠️ Per CAN SLIM rules, you should be ~75-100% in cash during "
        "market downtrends. Picks below are flagged WATCH until SPY confirms "
        "a follow-through day."
    )

# AI briefing slot (filled at end)
ai_slot = st.empty()

st.divider()

# ============================================================
# Universe + filter controls
# ============================================================
c1, c2, c3 = st.columns([2, 2, 1])

universe_choice = c1.selectbox(
    "Universe to scan",
    ["Nasdaq 100 (recommended — ~100 growth-tilted names)",
     "S&P 500 (~500 large-caps, slower)",
     "Both combined (~600 unique)"],
    index=0,
    help="CAN SLIM was built for growth stocks. Nasdaq 100 is the natural "
         "starting point. S&P 500 adds large-cap value/cyclicals which rarely "
         "pass the 25% earnings growth bar.",
)

verdict_filter = c2.selectbox(
    "Show",
    ["All verdicts",
     "🟢 STRONG BUY only",
     "🟢 BUY + STRONG BUY",
     "🟡 WATCH (basing setups)",
     "Top 20 by combined score"],
    index=2,
)

run_btn = c3.button("🔍 Run scan", type="primary", use_container_width=True)

# Resolve universe
if "nasdaq" in universe_choice.lower():
    tickers = universe.get_nasdaq100()
elif "s&p" in universe_choice.lower():
    tickers = universe.get_sp500()
else:
    tickers = sorted(set(universe.get_nasdaq100() + universe.get_sp500()))

st.caption(f"📊 Universe: **{len(tickers)} tickers** ready. Scan typically takes "
           f"{int(len(tickers) * 0.8)}-{int(len(tickers) * 1.5)} seconds first run "
           f"(cached after).")

# ============================================================
# Run scan
# ============================================================
df = None
if run_btn or st.session_state.get("canslim_df") is not None:
    if run_btn:
        with st.spinner(f"Scanning {len(tickers)} tickers — Minervini + CAN SLIM…"):
            df = cm.scan(tickers, max_tickers=len(tickers), require_market=True)
            st.session_state["canslim_df"] = df
    else:
        df = st.session_state["canslim_df"]

# ============================================================
# Results
# ============================================================
if df is None or df.empty:
    st.info("Click **Run scan** to begin. Results stay cached during this session.")
else:
    # Apply verdict filter
    view = df.copy()
    if verdict_filter == "🟢 STRONG BUY only":
        view = view[view["Verdict"].str.contains("STRONG BUY")]
    elif verdict_filter == "🟢 BUY + STRONG BUY":
        view = view[view["Verdict"].str.contains("BUY")]
    elif verdict_filter == "🟡 WATCH (basing setups)":
        view = view[view["Verdict"].str.contains("WATCH")]
    elif verdict_filter == "Top 20 by combined score":
        view = view.head(20)

    # Summary tiles
    n_strong = int((df["Verdict"].str.contains("STRONG BUY")).sum())
    n_buy = int((df["Verdict"].str.contains("BUY") & ~df["Verdict"].str.contains("STRONG")).sum())
    n_watch = int((df["Verdict"].str.contains("WATCH")).sum())
    n_avoid = int((df["Verdict"].str.contains("AVOID")).sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🟢 STRONG BUY", n_strong, help="Trend 8/8 + Fund ≥3/4 + market green")
    m2.metric("🟢 BUY", n_buy, help="Trend ≥7/8 + Fund ≥2/4 + market green")
    m3.metric("🟡 WATCH", n_watch, help="Trend ≥6/8 — basing or near-pass")
    m4.metric("🔴 AVOID", n_avoid, help="Trend <6/8 — no setup")

    st.divider()

    # ============================================================
    # Compact results table (most actionable columns)
    # ============================================================
    st.subheader(f"Results ({len(view)} shown)")
    show_cols = [
        "Ticker", "Verdict", "Total /12", "Trend /8", "Fund /4",
        "RS Rank", "Price", "% from 52w high", "% above 52w low",
        "Quarterly EPS %", "Annual EPS %", "Inst Own %",
    ]
    st.dataframe(
        view[show_cols],
        use_container_width=True,
        height=min(600, 40 + 35 * len(view)),
        hide_index=True,
        column_config={
            "Total /12":     st.column_config.NumberColumn(format="%d /12"),
            "Trend /8":      st.column_config.NumberColumn(format="%d /8"),
            "Fund /4":       st.column_config.NumberColumn(format="%d /4"),
            "RS Rank":       st.column_config.ProgressColumn(
                min_value=1, max_value=99, format="%d"),
            "Price":         st.column_config.NumberColumn(format="$%.2f"),
            "% from 52w high": st.column_config.NumberColumn(format="%+.1f%%"),
            "% above 52w low":  st.column_config.NumberColumn(format="%+.1f%%"),
            "Quarterly EPS %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Annual EPS %":    st.column_config.NumberColumn(format="%+.1f%%"),
            "Inst Own %":      st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    # ============================================================
    # Drill-down: full criteria breakdown for one ticker
    # ============================================================
    st.divider()
    st.subheader("🔬 Criteria breakdown")

    pick = st.selectbox(
        "Pick a ticker to see exactly which criteria it passes/fails",
        options=view["Ticker"].tolist() if not view.empty else [],
    )
    if pick:
        row = df[df["Ticker"] == pick].iloc[0]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Minervini Trend Template (8 checks)**")
            checks = [
                ("T1. Price > 150d AND > 200d MA",  row["T1"]),
                ("T2. 150d MA > 200d MA",            row["T2"]),
                ("T3. 200d MA trending up (1mo)",    row["T3"]),
                ("T4. 50d > 150d AND > 200d MA",     row["T4"]),
                ("T5. Price > 50d MA",               row["T5"]),
                ("T6. Price ≥ 30% above 52w low",    row["T6"]),
                ("T7. Within 25% of 52w high",       row["T7"]),
                ("T8. RS Rank ≥ 70",                 row["T8 (RS≥70)"]),
            ]
            for label, ok in checks:
                icon = "✅" if ok else "❌"
                st.markdown(f"{icon} &nbsp; {label}", unsafe_allow_html=True)

        with col2:
            st.markdown("**CAN SLIM Fundamental + Macro**")
            fund = [
                (f"C. Quarterly EPS ≥ 25% YoY  (actual: {row['Quarterly EPS %']}%)",
                 row["C (Q EPS≥25%)"]),
                (f"A. Annual EPS ≥ 25%  (actual: {row['Annual EPS %']}%)",
                 row["A (Yr EPS≥25%)"]),
                (f"L. Leader — RS ≥ 80  (actual: {row['RS Rank']})",
                 row["L (RS≥80)"]),
                (f"I. Institutional ≥ 30%  (actual: {row['Inst Own %']}%)",
                 row["I (Inst≥30%)"]),
                ("S. Volume expanding (50d > avg)", row["Vol expanding"]),
                (f"M. Market in uptrend  ({'YES' if market_ok else 'NO'})",
                 market_ok),
            ]
            for label, ok in fund:
                icon = "✅" if ok else "❌"
                st.markdown(f"{icon} &nbsp; {label}", unsafe_allow_html=True)

        # Verdict + summary
        st.markdown(
            f"<div style='background:#11182A;padding:1rem;border-left:4px solid #FF8C00;"
            f"border-radius:6px;margin-top:0.8rem'>"
            f"<div style='font-size:1.1rem;color:#E6E8EE'>"
            f"<b>{row['Ticker']}</b> &middot; {row['Verdict']} "
            f"&middot; Total {int(row['Total /12'])}/12 "
            f"&middot; Price ${row['Price']:.2f} "
            f"&middot; RS {int(row['RS Rank'])}"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    # ============================================================
    # AI briefing (filled at the end with full results context)
    # ============================================================
    if df is not None and not df.empty:
        ctx = cm.summarize_for_ai(df, market_msg)
        fallback = (
            f"<b>Scan results:</b> {n_strong} STRONG BUY, {n_buy} BUY, "
            f"{n_watch} WATCH out of {len(df)} scanned.  "
            f"Market direction: {'✅ confirmed uptrend' if market_ok else '❌ no follow-through yet'}.  "
            f"Focus on the top of the table — these are the names with the "
            f"highest combined Trend + Fundamental scores."
        )
        with ai_slot.container():
            ai_summary.auto_summarize(st, ctx, page_kind="screen",
                                       fallback_text=fallback)

# ============================================================
# Footer — methodology citation
# ============================================================
with st.expander("📚 What is CAN SLIM + Minervini?"):
    st.markdown("""
**CAN SLIM** is the growth-investing methodology developed by **William J. O'Neil**,
founder of *Investor's Business Daily*. Documented in his 1988 book *How to Make
Money in Stocks*. Backtested by AAII to outperform the S&P 500 by ~30% annualized
during favorable markets.

| Letter | Meaning | This scanner |
|--------|---------|--------------|
| **C** | Current quarterly earnings ≥ 25% YoY | ✅ checked |
| **A** | Annual earnings growth ≥ 25% over 3 years | ✅ checked (1yr proxy) |
| **N** | New highs, new products, new management | ✅ via T7 (within 25% of 52w high) |
| **S** | Supply & Demand — low float + volume confirmation | ✅ via volume expansion |
| **L** | Leader vs Laggard — top RS rank | ✅ RS ≥ 80 |
| **I** | Institutional sponsorship growing | ✅ Held % institutions ≥ 30% |
| **M** | Market direction confirmed uptrend | ✅ macro gate at top |

**Minervini's Trend Template** is the 8-point price-action filter developed by
**Mark Minervini**, 1997 U.S. Investing Champion (155% return). It's the
strictest "is this stock in a Stage 2 uptrend?" definition in growth investing.

This page runs **both systems on every stock** and ranks by combined score.
A perfect score is 12/12 + market gate green — historically rare (maybe 3-8
names in the entire Nasdaq 100). Most actionable names will score 9-11.

**How to use:**
1. Check the market gate at the top — if red, sit on your hands
2. Run the scan
3. Focus on STRONG BUY names (8/8 trend + 3+/4 fundamentals)
4. Click into each to see exactly which criteria it passes
5. Cross-reference with the Stock Discovery page for Stage Engine confirmation
""")
