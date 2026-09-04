"""
🎣 Funnel — Pond → Fish → Focus → Review.

Not the Weinstein "Stage 1-4" (that's price structure, see Discovery).
This is the selection funnel: mechanical screen → scored shortlist with a
correlation kill → written thesis + sizing → earnings-based review.
"""

import pandas as pd
import streamlit as st

from lib import ai_summary, canslim_minervini as cm, data, funnel, universe

st.title("🎣 Funnel: Pond → Fish → Focus → Review")
st.caption("Each step only eliminates. Nothing gets added back because you like it.")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["F1 Pond", "F2 Fish", "F3 Focus", "F4 Review", "📚 Evidence"])

# ------------------------------------------------------------ F1
with tab1:
    ok, msg = cm.market_direction_ok()
    st.markdown(f"**Regime gate:** {'🟢 ON' if ok else '🔴 OFF'} — {msg}")
    if not ok:
        st.warning("Regime OFF: breakouts fail far more often in index downtrends (Faber 2007). "
                   "The pond still runs, but treat everything below as watch-list only.")
    c1, c2, c3 = st.columns([2, 1, 1])
    uni = c1.selectbox("Universe", ["Nasdaq 100", "S&P 500", "Both (~600, slow)"])
    near = c2.slider("Within X% of 52-wk high", 5, 30, 20)
    maxf = c3.slider("Max fundamentals lookups", 20, 150, 80, 10,
                     help="yfinance statements are ~1s per ticker; survivors of the price gates only.")
    tickers = (universe.get_nasdaq100() if uni.startswith("Nasdaq") else
               universe.get_sp500() if uni.startswith("S&P") else universe.get_full_universe())
    if st.button("Run pond screen", type="primary"):
        st.session_state["pond"] = funnel.pond(tickers, near_high_pct=-near, max_fundamentals=maxf)
    p = st.session_state.get("pond")
    if p is not None and not p.empty:
        st.markdown(f"**{len(p)}** passed the price gates (Stage 2 + near high + RS). Gates passed of 5:")
        show = p[["ticker", "price", "gates_passed", "gate_trend", "gate_rs", "gate_accel", "gate_margin", "gate_rev",
                  "rev_g_now", "rev_g_prev", "accel_pp", "gm_delta_pp", "rev_up_pct", "surprise_avg", "rs_vs_bench", "pct_from_52w_high"]]
        st.dataframe(show, use_container_width=True, hide_index=True, height=420)
        st.caption("rev_g = YoY revenue growth this quarter vs prior quarter (accel_pp = the change, in points). "
                   "gm_delta = gross-margin change vs same quarter last year. rev_up = forward EPS estimate change (FMP) "
                   "or, without an FMP key, avg earnings surprise of the last 4 reports.")
    elif p is not None:
        st.info("Nothing passed the price gates — that itself is information about the regime.")

# ------------------------------------------------------------ F2
with tab2:
    p = st.session_state.get("pond")
    if p is None or p.empty:
        st.info("Run the pond first.")
    else:
        c1, c2, c3 = st.columns(3)
        min_g = c1.slider("Min gates passed", 3, 5, 4)
        top_n = c2.slider("Keep top N", 3, 10, 5)
        ccut = c3.slider("Correlation kill threshold", 0.5, 0.9, 0.7, 0.05)
        ranked, dropped = funnel.fish(p, min_gates=min_g, top_n=top_n, corr_cut=ccut)
        st.session_state["fish"] = ranked
        if ranked.empty:
            st.warning("No name passes that many gates. Lower the bar or accept that the pond is empty right now.")
        else:
            st.markdown("**Scored shortlist** (score = mean percentile of acceleration, margin delta, revisions/beats, RS):")
            st.dataframe(ranked[["ticker", "score", "gates_passed", "accel_pp", "gm_delta_pp", "rev_up_pct", "surprise_avg", "rs_vs_bench", "price"]],
                         use_container_width=True, hide_index=True)
            if not dropped.empty:
                st.markdown("**Dropped by the correlation kill** (same trade as a higher-scored survivor):")
                st.dataframe(dropped, use_container_width=True, hide_index=True)
            ctx = "Funnel F2 shortlist:\n" + ranked[["ticker", "score", "gates_passed", "accel_pp", "gm_delta_pp", "rev_up_pct", "surprise_avg"]].to_string(index=False)
            ai_summary.auto_summarize(
                st, "You are a buy-side PM. For each ticker below, in one line each: what the numbers say, and the single "
                    "question a Stage-3 analyst must answer before owning it. Then name which two are the SAME trade if any. "
                    "Numbers only, no hype.\n\n" + ctx, page_kind="funnel",
                fallback_text="Configure an AI key to get a shortlist briefing.")

# ------------------------------------------------------------ F3
with tab3:
    fish_df = st.session_state.get("fish")
    options = list(fish_df["ticker"]) if fish_df is not None and not fish_df.empty else []
    tk = st.selectbox("Ticker", options + ["(type)"]) if options else None
    if tk == "(type)" or not options:
        tk = st.text_input("Ticker", value="").upper().strip()
    if tk:
        saved = funnel.load_theses().get(tk, {})
        st.markdown("Answer in one sentence each. If you can't, that's the elimination.")
        q1 = st.text_area("1 · What is the wave, and why does THIS company toll it?", saved.get("wave", ""), height=70)
        q2 = st.text_area("2 · What number would prove me wrong? (invalidation — a metric, not a vibe)", saved.get("invalidation", ""), height=70)
        q3 = st.text_area("3 · Why might the market be wrong about it right now?", saved.get("edge", ""), height=70)
        st.markdown("**Sizing** — the stop decides the size, never the other way round.")
        c = st.columns(4)
        port = c[0].number_input("Portfolio $", 1000.0, 1e9, float(saved.get("portfolio", 100000)), 1000.0)
        mloss = c[1].number_input("Max loss if stopped (% of portfolio)", 0.25, 10.0, float(saved.get("max_loss_pct", 1.0)), 0.25)
        q = data.get_quote(tk) or {}
        entry_default = float(saved.get("entry") or q.get("price") or q.get("last") or 0)
        entry = c[2].number_input("Entry", 0.0, 1e6, entry_default, 0.01)
        stop = c[3].number_input("Stop", 0.0, 1e6, float(saved.get("stop") or entry * 0.92 if entry else 0), 0.01)
        sz = funnel.size_position(port, mloss, entry, stop)
        if sz:
            st.markdown(f"→ **{sz['shares']} shares** = ${sz['position_$']:,} ({sz['position_pct']}% of portfolio); "
                        f"risk ${sz['risk_$']:,} at a {sz['stop_dist_pct']}% stop.")
            if sz["position_pct"] > 15:
                st.warning("Position > 15% of portfolio. A −50% drawdown in this name would cost > 7.5% of everything.")
        if st.button("Save thesis"):
            funnel.save_thesis(tk, {"wave": q1, "invalidation": q2, "edge": q3, "portfolio": port,
                                    "max_loss_pct": mloss, "entry": entry, "stop": stop, "saved": str(pd.Timestamp.now().date())})
            st.success(f"Saved thesis for {tk}.")
        if not (q1.strip() and q2.strip() and q3.strip()):
            st.info("Three blanks = not eligible yet.")

# ------------------------------------------------------------ F4
with tab4:
    theses = funnel.load_theses()
    if not theses:
        st.info("No saved theses. Review runs on names saved in F3.")
    else:
        st.caption("Review on earnings, not on price. Exit on gate failure or your written invalidation — never on drawdown alone.")
        rows = []
        for tk, th in theses.items():
            r = funnel.review(tk)
            q = data.get_quote(tk) or {}
            px = q.get("price") or q.get("last")
            rows.append({"ticker": tk, "price": px, "entry": th.get("entry"), "stop": th.get("stop"),
                         "vs_stop_%": round((px / th["stop"] - 1) * 100, 1) if px and th.get("stop") else None,
                         "next_earnings": r.get("next_earnings"), "gates_ok/5": r.get("gates_ok"),
                         "trend": r.get("gate_trend"), "accel": r.get("accel_ok"), "margin": r.get("margin_ok"), "revisions": r.get("rev_ok"),
                         "invalidation": th.get("invalidation", "")[:80]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.markdown("**Rules:** gates_ok ≤ 2 → thesis broken, exit. Price below stop → exit, no negotiation. "
                    "Earnings within 7 days → decide *now* whether you hold through it.")

# ------------------------------------------------------------ Evidence
with tab5:
    st.markdown("Each gate's evidence source. These are literature citations, not statistics the app derived — "
                "the app's own contribution is applying them mechanically and showing you the raw numbers.")
    for k, g in funnel.GATES.items():
        st.markdown(f"**{g['label']}**  \n<span style='color:#8a93a6'>{g['evidence']}</span>", unsafe_allow_html=True)
    st.markdown("---\n**Honest limits:** yfinance statements can lag or mislabel line items; the revisions gate is weak "
                "without an FMP key (surprise history is a proxy); the acceleration gate needs 5–6 clean quarters. "
                "The funnel finds candidates that *resemble* past winners — survivorship bias is real (Bessembinder 2018), "
                "which is why F3 sizing and F4 exits do half the work.")
