"""
🎣 Discovery — the selection funnel: Pond → Fish → Focus (AI) → Review.

Replaces the old Discovery + CAN SLIM pages. Weinstein stage analysis still
powers the trend gate under the hood (lib/stages.py), but the page is organised
around eliminations, not indicators. Focus is written by agents from fetched
facts; you review and approve, you don't type what an API already knows.
"""

import json

import pandas as pd
import streamlit as st

from lib import canslim_minervini as cm, data, funnel, universe

st.title("🎣 Discovery")
st.caption("Pond → Fish → Focus → Review. Each step only eliminates.")

GREEN, RED, AMBER, GREY = "#22C55E", "#EF4444", "#FF8C00", "#8a93a6"
GATE_COLS = ["gate_trend", "gate_rs", "gate_accel", "gate_margin", "gate_rev", "gate_quality", "gate_dilution", "gate_incremental"]

tab1, tab2, tab3, tab4, tab5 = st.tabs(["F1 Pond", "F2 Fish", "F3 Focus (AI)", "F4 Review", "📚 Evidence"])

# ------------------------------------------------------------ F1
with tab1:
    ok, msg = cm.market_direction_ok()
    st.markdown(f"**Regime gate:** {'🟢 ON' if ok else '🔴 OFF'} — {msg}")
    if not ok:
        st.warning("Regime OFF: breakouts fail far more often in index downtrends (Faber 2007). Treat survivors as watch-list only.")
    c1, c2, c3 = st.columns([2, 1, 1])
    uni = c1.selectbox("Universe", ["Nasdaq 100", "S&P 500", "Both (~600, slow)"])
    near = c2.slider("Within X% of 52-wk high", 5, 30, 20)
    maxf = c3.slider("Max fundamentals lookups", 20, 150, 80, 10)
    tickers = (universe.get_nasdaq100() if uni.startswith("Nasdaq") else
               universe.get_sp500() if uni.startswith("S&P") else universe.get_full_universe())
    if st.button("Run pond screen", type="primary"):
        st.session_state["pond"] = funnel.pond(tickers, near_high_pct=-near, max_fundamentals=maxf)
    p = st.session_state.get("pond")
    if p is not None and not p.empty:
        st.markdown(f"**{len(p)}** passed the price gates. Gates passed of 8 "
                    "(trend · RS · acceleration · margin · revisions · quality · dilution · incremental):")
        show = p[["ticker", "price", "gates_passed"] + GATE_COLS +
                 ["rev_g_now", "accel_pp", "gm_delta_pp", "rev_up_pct", "surprise_avg", "gp_assets", "roic_pct",
                  "share_growth_pct", "rev_ps_growth_pct", "incr_margin_pct", "rs_vs_bench", "pct_from_52w_high"]]
        st.dataframe(show, use_container_width=True, hide_index=True, height=440)
        st.caption("accel_pp = change in YoY revenue growth vs prior quarter · gm_delta = gross-margin change YoY · "
                   "gp_assets = gross profit / total assets (Novy-Marx) · share_growth = diluted share count YoY · "
                   "incr_margin = Δ operating income / Δ revenue (operating leverage).")
    elif p is not None:
        st.info("Nothing passed the price gates — that is information about the regime.")

# ------------------------------------------------------------ F2
with tab2:
    p = st.session_state.get("pond")
    if p is None or p.empty:
        st.info("Run the pond first.")
    else:
        c1, c2, c3 = st.columns(3)
        min_g = c1.slider("Min gates passed (of 8)", 4, 8, 5)
        top_n = c2.slider("Keep top N", 3, 10, 5)
        ccut = c3.slider("Correlation kill threshold", 0.5, 0.9, 0.7, 0.05)
        ranked, dropped = funnel.fish(p, min_gates=min_g, top_n=top_n, corr_cut=ccut)
        st.session_state["fish"] = ranked
        if ranked.empty:
            st.warning("No name passes that many gates. Lower the bar or accept the pond is empty right now.")
        else:
            st.markdown("**Scored shortlist** — score = mean percentile of acceleration, margin delta, revisions, RS, "
                        "gross profitability, incremental margin, minus dilution:")
            st.dataframe(ranked[["ticker", "score", "gates_passed", "accel_pp", "gm_delta_pp", "rev_up_pct", "gp_assets",
                                 "incr_margin_pct", "share_growth_pct", "rs_vs_bench", "price"]],
                         use_container_width=True, hide_index=True)
            if not dropped.empty:
                st.markdown("**Dropped by the correlation kill** (same trade as a higher-scored survivor):")
                st.dataframe(dropped, use_container_width=True, hide_index=True)

# ------------------------------------------------------------ F3 (AI)
with tab3:
    fish_df = st.session_state.get("fish")
    opts = list(fish_df["ticker"]) if fish_df is not None and not fish_df.empty else []
    c1, c2 = st.columns([2, 1])
    tk = c1.selectbox("Ticker from the shortlist", opts) if opts else None
    typed = c2.text_input("…or any ticker", "").upper().strip()
    tk = typed or tk
    if tk:
        if st.button(f"Run agents on {tk}", type="primary") or st.session_state.get("thesis_tk") == tk:
            if st.session_state.get("thesis_tk") != tk:
                with st.spinner("Fetching facts → writing thesis → auditing…"):
                    fp = funnel.fact_pack(tk)
                    th = funnel.ai_thesis(tk, fp)
                st.session_state.update(thesis_tk=tk, thesis_fp=fp, thesis=th)
            fp, th = st.session_state["thesis_fp"], st.session_state["thesis"]
            if not th:
                st.error("No LLM key found (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY). Facts below are still fetched.")
            elif th.get("_error"):
                st.error(f"Agent error: {th['_error']}")
            else:
                ok = th.get("_audit_pass"); col = GREEN if ok else RED if ok is False else GREY
                st.markdown(f"<div style='border-left:4px solid {col};padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:6px'>"
                            f"<b>{tk} — thesis card</b> <span style='color:#8a93a6'>({th.get('_model')}, {th.get('_latency_s')}s, audit: {'PASS' if ok else 'FLAGGED' if ok is False else 'n/a'})</span><br><br>"
                            f"<b>Wave:</b> {th.get('wave')}<br><b>Invalidation:</b> {th.get('invalidation')}<br><b>Edge:</b> {th.get('edge')}<br>"
                            f"<b>Same trade as:</b> {th.get('same_trade_as')}<br><b>Stop:</b> {th.get('stop_rationale')}<br>"
                            f"<b>Gate flags:</b> {', '.join(th.get('gate_flags') or []) or 'none'}</div>", unsafe_allow_html=True)
                if th.get("_audit") and ok is False:
                    with st.expander("Auditor findings"):
                        st.write(th["_audit"])
                # scenarios
                info = fp.get("info", {}); mcap = info.get("marketCap"); fund = fp.get("fund", {})
                rev_ttm = None
                try:
                    qi = data.get_financials(tk).get("income_q")
                    rev_ttm = float(qi.loc["Total Revenue"].dropna().iloc[:4].sum())
                except Exception:
                    pass
                if mcap and rev_ttm:
                    yrs = st.slider("Horizon (years)", 3, 10, 5)
                    rows = []
                    for k in ("bear", "base", "bull"):
                        sc = th.get(k) or {}
                        r = funnel.scenario_returns(mcap, rev_ttm, yrs, sc)
                        rows.append({"scenario": k, **sc, **r})
                    st.markdown("**Scenario returns** (agent assumptions — edit in the JSON below if you disagree):")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                    bear = next((r for r in rows if r["scenario"] == "bear"), {})
                    if bear.get("multiple_of_today") is not None and bear["multiple_of_today"] < 0.6:
                        st.warning("Bear case loses >40% — only survivable at small size.")
            # sizing (prefilled from facts)
            st.markdown("**Sizing** — the stop decides the size.")
            saved = funnel.load_theses().get(tk, {})
            price = fp.get("price") or (fp.get("quote") or {}).get("price") or 0.0
            atr = fp.get("atr14") or 0.0
            c = st.columns(4)
            port = c[0].number_input("Portfolio $", 1000.0, 1e9, float(saved.get("portfolio", 100000)), 1000.0)
            mloss = c[1].number_input("Max loss if stopped (% of portfolio)", 0.25, 10.0, float(saved.get("max_loss_pct", 1.0)), 0.25)
            entry = c[2].number_input("Entry", 0.0, 1e6, float(saved.get("entry") or price), 0.01)
            stop = c[3].number_input("Stop (default 2.5×ATR)", 0.0, 1e6, float(saved.get("stop") or max(entry - 2.5 * atr, 0)), 0.01)
            sz = funnel.size_position(port, mloss, entry, stop)
            if sz:
                st.markdown(f"→ **{sz['shares']} shares** = ${sz['position_$']:,} ({sz['position_pct']}% of portfolio); risk ${sz['risk_$']:,} at a {sz['stop_dist_pct']}% stop.")
            with st.expander("Facts the agents used / edit thesis JSON before saving"):
                st.json(fp)
                edited = st.text_area("Thesis JSON", json.dumps({k: v for k, v in (th or {}).items() if not k.startswith("_")}, indent=1), height=220)
            if st.button("Approve & save thesis"):
                try:
                    tj = json.loads(edited)
                except Exception:
                    tj = th or {}
                funnel.save_thesis(tk, {**{k: v for k, v in tj.items()}, "portfolio": port, "max_loss_pct": mloss, "entry": entry, "stop": stop,
                                        "saved": str(pd.Timestamp.now().date()), "next_earnings": fp.get("next_earnings")})
                st.success(f"Saved {tk}. It now appears in F4 Review.")

# ------------------------------------------------------------ F4
with tab4:
    theses = funnel.load_theses()
    if not theses:
        st.info("No saved theses yet — approve one in F3.")
    else:
        st.caption("Review on earnings, not on price. Exit on gate failure or the written invalidation — never on drawdown alone.")
        rows = []
        for tk, th in theses.items():
            r = funnel.review(tk); q = data.get_quote(tk) or {}
            px = q.get("price") or q.get("last")
            rows.append({"ticker": tk, "price": px, "entry": th.get("entry"), "stop": th.get("stop"),
                         "vs_stop_%": round((px / th["stop"] - 1) * 100, 1) if px and th.get("stop") else None,
                         "next_earnings": r.get("next_earnings"), "gates_ok/8": r.get("gates_ok"),
                         "invalidation": (th.get("invalidation") or "")[:90]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.markdown("**Rules:** gates_ok ≤ 3 → thesis broken, exit. Price below stop → exit, no negotiation. "
                    "Earnings within 7 days → decide now whether you hold through it.")
        if st.button("Re-run agents on all held names"):
            for tk in theses:
                th = funnel.ai_thesis(tk)
                if th and not th.get("_error"):
                    st.markdown(f"**{tk}** — invalidation now: {th.get('invalidation')} · flags: {', '.join(th.get('gate_flags') or []) or 'none'}")

# ------------------------------------------------------------ Evidence
with tab5:
    st.markdown("Each gate's evidence source. Literature citations, not statistics the app derived; the app applies them mechanically and shows raw numbers.")
    for k, g in funnel.GATES.items():
        st.markdown(f"**{g['label']}**  \n<span style='color:#8a93a6'>{g['evidence']}</span>", unsafe_allow_html=True)
    st.markdown("---\n**Honest limits:** yfinance statements can lag or mislabel line items; the revisions gate is a proxy without an FMP key; "
                "quality/dilution use annual statements (one year stale at worst). The funnel finds names that resemble past winners — "
                "survivorship bias is real (Bessembinder 2018), which is why F3 sizing and F4 exits do half the work.")
