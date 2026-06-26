"""
🌍 Macro — single-screen macro center with placeholder-pattern AI.

Pattern on every segment:
  1. Reserve placeholder slot at top
  2. Compute all data
  3. Render AI summary into placeholder (with full data context)
  4. Render visualizations below
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import ai_summary, data, macro, narrator, universe, vix_analysis, yield_analysis

st.title("🌍 Macro")

# ============================================================
# Hero — regime + leverage gate
# ============================================================
state = macro.assess()
gate_color = {"GREEN": "#22C55E", "YELLOW": "#FF8C00", "RED": "#EF4444"}[state.leverage_gate]

st.markdown(
    f"<div style='background:#11182A;padding:1.2rem;border-left:6px solid {gate_color};"
    f"border-radius:6px;margin-bottom:0.6rem'>"
    f"<div style='display:flex;justify-content:space-between;align-items:center'>"
    f"<div><div style='color:#8a93a6;font-size:0.8rem;text-transform:uppercase'>Macro regime</div>"
    f"<div style='font-size:1.7rem;font-weight:bold;color:{gate_color}'>"
    f"{state.regime} &middot; {state.leverage_gate}</div></div>"
    f"<div style='font-size:0.9rem;color:#bcc3d6;max-width:60%;text-align:right'>{state.summary}</div>"
    f"</div></div>",
    unsafe_allow_html=True,
)

# RESERVE the AI summary slot AT TOP (filled after data loads below)
top_ai_slot = st.empty()

# ============================================================
# Segment selector — radio (avoids tab/navigation glitches)
# ============================================================
st.markdown("### 🔬 Drill into a specific area")
segment = st.radio(
    "View",
    ["📊 VIX & Deployment", "💹 Rates & Curves", "🔥 Inflation",
     "🥇 Commodities", "🗺 Sectors"],
    horizontal=True,
    label_visibility="collapsed",
)

# Reserve a SECOND AI slot per-segment (filled after segment data loads)
segment_ai_slot = st.empty()

ASSETS = {
    "S&P 500":  ("SPY",     "#22C55E"),
    "Nasdaq":   ("QQQ",     "#3B82F6"),
    "Russell":  ("IWM",     "#A855F7"),
    "Bitcoin":  ("BTC-USD", "#FF8C00"),
    "Ethereum": ("ETH-USD", "#627EEA"),
    "Gold":     ("GLD",     "#FFD700"),
    "TLT 20Y":  ("TLT",     "#EF4444"),
    "Oil":      ("USO",     "#16A34A"),
}
PERIOD_MAP = {"1M": "3mo", "3M": "6mo", "YTD": "ytd",
              "1Y": "1y", "2Y": "2y", "5Y": "5y"}

# Recommendation tags + asset relevance for rates/spreads/inflation
MACRO_TAGS = {
    "10Y Yield":      {"tag": "⊖ rate-sensitive equities",
                       "rec_for": ["S&P 500", "Nasdaq", "Bitcoin"]},
    "2Y Yield":       {"tag": "Fed-policy proxy",
                       "rec_for": ["S&P 500", "Russell", "Bitcoin"]},
    "10Y-2Y Spread":  {"tag": "⚠ RECESSION SIGNAL",
                       "rec_for": ["S&P 500", "Russell"]},
    "Fed Funds":      {"tag": "Policy rate",
                       "rec_for": ["S&P 500", "Bitcoin"]},
    "HY Credit":      {"tag": "Risk-on/off",
                       "rec_for": ["Russell", "S&P 500", "Bitcoin"]},
    "CPI YoY":        {"tag": "Inflation (headline)",
                       "rec_for": ["S&P 500", "Gold", "Bitcoin"]},
    "Core CPI":       {"tag": "Inflation (sticky)",
                       "rec_for": ["S&P 500"]},
    "Core PCE":       {"tag": "★ Fed's actual target",
                       "rec_for": ["S&P 500", "Nasdaq"]},
}


def _label_with_tag(option: str, focus_assets: list | None = None) -> str:
    spec = MACRO_TAGS.get(option, {})
    tag = spec.get("tag", "")
    rec_for = spec.get("rec_for", [])
    star = "★ " if focus_assets and any(fa in rec_for for fa in focus_assets) else ""
    return f"{star}{option}" + (f"  —  {tag}" if tag else "")



def _slice_period(df, period):
    if df.empty:
        return df
    if period == "YTD":
        return df[df.index >= pd.Timestamp(year=pd.Timestamp.now().year, month=1, day=1)]
    return df


def _normalize(s):
    s = s.dropna()
    return s / s.iloc[0] * 100 if not s.empty else s


# ============================================================
# Segment 1: VIX & Deployment
# ============================================================
if segment == "📊 VIX & Deployment":
    horizon_choice = st.radio(
        "Forward horizon", ["1M", "3M", "6M", "1Y", "2Y"],
        horizontal=True, index=3, key="vix_horizon",
    )
    horizon = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252, "2Y": 504}[horizon_choice]

    with st.spinner("Pulling 30+ years of VIX/SPY history…"):
        state_vix = vix_analysis.current_state()
        rec = vix_analysis.deploy_recommendation_for_current_vix(horizon)
        ladder = vix_analysis.deployment_ladder(horizon)

    if not state_vix or ladder.empty:
        st.error("Could not fetch enough VIX/SPY history.")
    else:
        cur = state_vix["current"]
        cur_pctile = state_vix["percentile"]
        bucket = state_vix["bucket"]
        deploy_pct = rec.get("deploy_pct")
        mean_fwd = rec.get("mean_fwd_ret")
        win_rate = rec.get("win_rate")

        # Render visualization
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VIX today", f"{cur:.1f}",
                  f"Higher than {cur_pctile:.0f}% of all history",
                  help="Current VIX level + percentile rank vs 30+ years of history.")
        c2.metric("Current zone", bucket or "—",
                  help="Which fear/calm bucket VIX is currently sitting in.")
        horizon_lbl = {21: "1-month", 63: "3-month", 126: "6-month",
                       252: "1-year", 504: "2-year"}.get(horizon, f"{horizon}-day")
        c3.metric(f"Avg SPY return ({horizon_lbl} fwd)",
                  f"{mean_fwd:+.1f}%" if mean_fwd is not None else "—",
                  f"Positive {win_rate:.0f}% of the time" if win_rate is not None else "",
                  help=f"Average SPY return over the next {horizon_lbl} from this VIX zone, historically.")
        c4.metric("Suggested cash deploy",
                  f"{deploy_pct:.0f}%" if deploy_pct is not None else "—",
                  help="Data-driven cash deployment % for the current VIX zone.")

        fig = go.Figure(go.Bar(
            x=ladder["bucket"], y=ladder["mean_fwd_ret"],
            marker_color=["#22C55E" if v > 0 else "#EF4444" for v in ladder["mean_fwd_ret"]],
            text=[f"{v:+.1f}%" for v in ladder["mean_fwd_ret"]], textposition="outside",
        ))
        fig.update_layout(template="plotly_dark", height=350,
                          title=f"Historical SPY {horizon}d-fwd return by VIX bucket",
                          paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                          margin=dict(l=0, r=0, t=50, b=0))
        st.plotly_chart(fig, use_container_width=True)

        # Merge bucket_history for richer stats
        try:
            bh = vix_analysis.bucket_history()
        except Exception:
            bh = pd.DataFrame()

        with st.expander("📋 Full deployment ladder + occurrence history", expanded=True):
            d = ladder.copy()
            d.insert(0, "", ["👉" if b == bucket else "" for b in d["bucket"]])
            if not bh.empty:
                d = d.merge(bh, on="bucket", how="left")
            for c in ("mean_fwd_ret", "median_fwd_ret", "win_rate", "p10", "p90"):
                if c in d.columns:
                    d[c] = d[c].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")
            d["deploy_pct"] = d["deploy_pct"].map(lambda x: f"{x:.0f}%")
            if "pct_of_history" in d.columns:
                d["pct_of_history"] = d["pct_of_history"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            # Reorder columns to put history stats up front
            cols_order = [c for c in [
                "", "bucket", "VIX range",
                "n_days", "pct_of_history", "n_episodes", "longest_streak",
                "first_seen", "last_seen",
                "mean_fwd_ret", "median_fwd_ret", "win_rate",
                "p10", "p90", "deploy_pct",
            ] if c in d.columns]
            d_disp = d[cols_order].rename(columns={
                "bucket": "Zone", "VIX range": "VIX range", "n": "Forward-return obs.",
                "n_days": "Days observed", "pct_of_history": "% of history",
                "n_episodes": "# times entered", "longest_streak": "Longest run (days)",
                "first_seen": "First seen", "last_seen": "Last seen",
                "mean_fwd_ret": "Avg 1Y SPY %", "median_fwd_ret": "Median 1Y SPY %",
                "win_rate": "Win rate (% +)",
                "p10": "Worst 10% case", "p90": "Best 10% case",
                "deploy_pct": "Suggested deploy %",
            })
            st.dataframe(d_disp, use_container_width=True, hide_index=True)
            st.caption(
                "**Glossary:** "
                "**Days observed** = trading days the market spent in this zone. "
                "**% of history** = how rare/common this zone is. "
                "**# times entered** = distinct visits (entered + left + re-entered). "
                "**Longest run** = longest unbroken stretch in the zone. "
                "**Avg / Median 1Y SPY %** = average / typical SPY return over the next ~1 year from this zone. "
                "**Win rate (% +)** = how often SPY was positive 1 year later. "
                "**Worst 10% / Best 10% case** = bottom-decile and top-decile 1Y outcomes. "
                "**Suggested deploy %** = data-driven cash deployment for this zone."
            )

            if "recent_5_entries" in bh.columns:
                st.markdown("**📅 Most recent times each bucket was first hit:**")
                hist_show = bh[["bucket", "n_episodes", "longest_streak", "recent_5_entries"]].copy()
                hist_show.columns = ["Bucket", "# of episodes", "Longest run (days)", "5 most-recent entry dates"]
                st.dataframe(hist_show, use_container_width=True, hide_index=True)

        # ---- Sector recovery leadership by VIX bucket ----
        st.markdown("### 🏆 Which sectors led the recovery from each VIX level?")
        st.caption("Mean 1-year-forward sector ETF return by VIX bucket (since SPDR sectors began ~1998). "
                   "Hot = best recovery names to lean into when deploying capital.")
        try:
            sec_grid = vix_analysis.sector_returns_by_bucket(horizon)
        except Exception:
            sec_grid = pd.DataFrame()
        if not sec_grid.empty:
            fig_sec = px.imshow(
                sec_grid.values, x=sec_grid.columns, y=sec_grid.index,
                text_auto=".1f", color_continuous_scale="RdYlGn",
                zmin=-15, zmax=40, aspect="auto",
                labels=dict(x="Sector", y="VIX bucket", color="Mean fwd %"),
            )
            fig_sec.update_layout(template="plotly_dark", height=380,
                                  paper_bgcolor="#0A0E1A",
                                  margin=dict(l=0, r=0, t=10, b=0))
            fig_sec.update_traces(textfont=dict(size=11, color="white"))
            st.plotly_chart(fig_sec, use_container_width=True)

            # Highlight current bucket's leader
            if bucket in sec_grid.index:
                row = sec_grid.loc[bucket].sort_values(ascending=False)
                top3 = row.head(3)
                bot3 = row.tail(3)
                st.info(
                    f"**🎯 At current VIX level ({bucket}), historical winners over the next "
                    f"{horizon} trading days:** "
                    + ", ".join(f"**{s}** {v:+.1f}%" for s, v in top3.items())
                    + ".  Laggards: "
                    + ", ".join(f"{s} {v:+.1f}%" for s, v in bot3.items())
                    + ". Lean entries toward the leader sectors when deploying cash."
                )
        else:
            st.info("Sector breakdown unavailable (yfinance may be rate-limited; cached after first run).")

        # NOW fill the AI slot with full context
        ctx = (f"VIX = {cur:.1f}, percentile p{cur_pctile:.0f} of 30+ year history. "
               f"Bucket: {bucket}. Historical {horizon}-day forward SPY return from this bucket: "
               f"{mean_fwd:+.1f}% (win rate {win_rate:.0f}%). "
               f"Recommended cash deployment: {deploy_pct:.0f}%.")
        fb = narrator.vix_story(cur, cur_pctile, bucket, deploy_pct, mean_fwd, horizon)
        with segment_ai_slot.container():
            ai_summary.auto_summarize(st, ctx, page_kind="vix", fallback_text=fb)


# ============================================================
# Segment 2: Rates & Curves
# ============================================================
elif segment == "💹 Rates & Curves":
    c1, c2 = st.columns(2)
    sel_assets = c1.multiselect("Assets", list(ASSETS.keys()),
                                default=["S&P 500", "Bitcoin"], key="r_a")
    sel_rates = c2.multiselect(
        "Rates / Spreads  (★ = recommended for your asset)",
        ["10Y Yield", "2Y Yield", "10Y-2Y Spread", "Fed Funds", "HY Credit"],
        default=["10Y Yield", "10Y-2Y Spread"], key="r_r",
        format_func=lambda o: _label_with_tag(o, sel_assets),
    )
    period = st.radio("Period", list(PERIOD_MAP.keys()), index=4,
                      horizontal=True, key="r_p")
    days = {"1M": 90, "3M": 180, "YTD": 365, "1Y": 365, "2Y": 730, "5Y": 1825}[period]

    rate_id = {"10Y Yield": "DGS10", "2Y Yield": "DGS2",
               "10Y-2Y Spread": "T10Y2Y", "Fed Funds": "DFF",
               "HY Credit": "BAMLH0A0HYM2"}

    # Compute data
    asset_returns = {}
    rate_summary = {}
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for label in sel_assets:
        tk, color = ASSETS[label]
        df = data.get_history(tk, period=PERIOD_MAP[period])
        df = _slice_period(df, period)
        if df.empty:
            continue
        norm = _normalize(df["close"])
        fig.add_trace(go.Scatter(x=norm.index, y=norm.values, name=label,
                                  line=dict(color=color, width=2.5)),
                      secondary_y=False)
        asset_returns[label] = float(norm.iloc[-1] - 100) if not norm.empty else None
    for label in sel_rates:
        df = data.fred_series(rate_id[label], days=days)
        if df.empty:
            continue
        fig.add_trace(go.Scatter(x=df["date"], y=df["value"], name=label,
                                  line=dict(width=1.5, dash="dot")),
                      secondary_y=True)
        rate_summary[label] = float(df.iloc[-1]["value"])

    fig.update_layout(template="plotly_dark", height=440,
                      paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                      yaxis=dict(title="Asset (start=100)"),
                      yaxis2=dict(title="Yield (%)", ticksuffix="%"),
                      margin=dict(l=0, r=0, t=20, b=0),
                      legend=dict(orientation="h", y=1.05),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # ============================================================
    # 10Y YIELD DEPLOYMENT LADDER — historical SPY forward returns by yield bucket
    # ============================================================
    st.markdown("### 📊 10Y Yield Deployment Ladder")
    st.caption("Where is the 10Y now vs history? What did SPY do over the next 12 months "
               "from each yield level? Built from 30+ years of FRED + yfinance data.")

    with st.spinner("Pulling 10Y yield + SPY history…"):
        y10_state = yield_analysis.current_state()
        y10_rec = yield_analysis.deploy_recommendation_for_current()
        y10_ladder = yield_analysis.deployment_ladder(252)

    if y10_state and not y10_ladder.empty:
        cur_y = y10_state["current"]
        pctile = y10_state["percentile"]
        bucket = y10_state["bucket"]
        chg_12m = y10_state.get("change_12m")
        deploy_pct_y = y10_rec.get("deploy_pct")
        mean_fwd_y = y10_rec.get("mean_fwd_ret")
        win_rate_y = y10_rec.get("win_rate")

        yk1, yk2, yk3, yk4 = st.columns(4)
        yk1.metric("10Y yield today", f"{cur_y:.2f}%",
                   f"Higher than {pctile:.0f}% of all history",
                   help="Current 10-Year Treasury yield + percentile rank vs 60+ years.")
        yk2.metric("Current zone", bucket,
                   help="Which yield bucket the 10Y is in (Ultra-low / Low / Moderate / Elevated / High / Very high).")
        if chg_12m is not None:
            chg_lbl = ("Rates RISING" if chg_12m > 0.5
                       else "Rates FALLING" if chg_12m < -0.5
                       else "Roughly stable")
            yk3.metric("12-month change in 10Y",
                       f"{chg_12m:+.2f}%", chg_lbl,
                       help="How much the 10Y yield has moved over the past year. Big moves matter — direction often matters more than absolute level.")
        yk4.metric("Suggested cash deploy",
                   f"{deploy_pct_y:.0f}%" if deploy_pct_y is not None else "—",
                   f"Avg 1Y SPY return: {mean_fwd_y:+.1f}%" if mean_fwd_y is not None else "",
                   help="Data-driven cash deployment % for the current 10Y zone, based on historical 1Y SPY returns from this level.")

        # Bar chart
        fig_y = go.Figure(go.Bar(
            x=y10_ladder["bucket"], y=y10_ladder["mean_fwd_ret"],
            marker_color=["#22C55E" if v > 0 else "#EF4444" for v in y10_ladder["mean_fwd_ret"]],
            text=[f"{v:+.1f}%" for v in y10_ladder["mean_fwd_ret"]], textposition="outside",
        ))
        fig_y.update_layout(template="plotly_dark", height=320,
                            title="Historical SPY 1-year-forward return by 10Y yield bucket",
                            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                            margin=dict(l=0, r=0, t=50, b=0))
        st.plotly_chart(fig_y, use_container_width=True)

        try:
            bh_y = yield_analysis.bucket_history()
        except Exception:
            bh_y = pd.DataFrame()

        with st.expander("📋 Full 10Y deployment ladder + occurrence history", expanded=True):
            d = y10_ladder.copy()
            d.insert(0, "", ["👉" if b == bucket else "" for b in d["bucket"]])
            if not bh_y.empty:
                d = d.merge(bh_y, on="bucket", how="left")
            for c in ("mean_fwd_ret", "median_fwd_ret", "win_rate", "p10", "p90"):
                if c in d.columns:
                    d[c] = d[c].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")
            d["deploy_pct"] = d["deploy_pct"].map(lambda x: f"{x:.0f}%")
            if "pct_of_history" in d.columns:
                d["pct_of_history"] = d["pct_of_history"].map(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            cols_order = [c for c in [
                "", "bucket", "yield_range",
                "n_days", "pct_of_history", "n_episodes", "longest_streak",
                "first_seen", "last_seen",
                "mean_fwd_ret", "median_fwd_ret", "win_rate",
                "p10", "p90", "deploy_pct",
            ] if c in d.columns]
            d_disp = d[cols_order].rename(columns={
                "bucket": "Zone", "yield_range": "10Y range", "n": "Forward-return obs.",
                "n_days": "Days observed", "pct_of_history": "% of history",
                "n_episodes": "# times entered", "longest_streak": "Longest run (days)",
                "first_seen": "First seen", "last_seen": "Last seen",
                "mean_fwd_ret": "Avg 1Y SPY %", "median_fwd_ret": "Median 1Y SPY %",
                "win_rate": "Win rate (% +)",
                "p10": "Worst 10% case", "p90": "Best 10% case",
                "deploy_pct": "Suggested deploy %",
            })
            st.dataframe(d_disp, use_container_width=True, hide_index=True)
            st.caption(
                "**Glossary:** "
                "**Days observed** = trading days 10Y spent in this zone. "
                "**% of history** = how rare/common this zone is. "
                "**# times entered** = distinct visits to this yield range. "
                "**Avg / Median 1Y SPY %** = average / typical SPY return over the next year from this zone. "
                "**Win rate (% +)** = how often SPY was positive 1 year later. "
                "**Worst 10% / Best 10% case** = bottom-decile and top-decile outcomes. "
                "**Suggested deploy %** = data-driven cash deployment for this yield zone."
            )

            if "recent_5_entries" in bh_y.columns:
                st.markdown("**📅 Most recent times each yield bucket was first hit:**")
                hist_show = bh_y[["bucket", "n_episodes", "longest_streak", "recent_5_entries"]].copy()
                hist_show.columns = ["Bucket", "# of episodes", "Longest run (days)", "5 most-recent entry dates"]
                st.dataframe(hist_show, use_container_width=True, hide_index=True)

        # ---- Sector forward returns by 10Y yield bucket ----
        st.markdown("### 🏆 Which sectors performed best at each 10Y level?")
        st.caption("Mean 1-year-forward sector ETF return when the 10Y was in each bucket.")
        try:
            sec_grid_y = yield_analysis.sector_returns_by_bucket(252)
        except Exception:
            sec_grid_y = pd.DataFrame()
        if not sec_grid_y.empty:
            fig_secy = px.imshow(
                sec_grid_y.values, x=sec_grid_y.columns, y=sec_grid_y.index,
                text_auto=".1f", color_continuous_scale="RdYlGn",
                zmin=-15, zmax=30, aspect="auto",
                labels=dict(x="Sector", y="10Y bucket", color="Mean fwd %"),
            )
            fig_secy.update_layout(template="plotly_dark", height=360,
                                   paper_bgcolor="#0A0E1A",
                                   margin=dict(l=0, r=0, t=10, b=0))
            fig_secy.update_traces(textfont=dict(size=11, color="white"))
            st.plotly_chart(fig_secy, use_container_width=True)

            if bucket in sec_grid_y.index:
                row = sec_grid_y.loc[bucket].sort_values(ascending=False)
                top3 = row.head(3)
                st.info(
                    f"**🎯 At current 10Y level ({bucket}), historical winners over the next year:** "
                    + ", ".join(f"**{s}** {v:+.1f}%" for s, v in top3.items())
                    + "."
                )

    # NOW fill AI slot with full context — including the 10Y deployment data
    ctx_parts = [
        f"Period: {period}.",
        "Asset returns over period: " +
        ", ".join(f"{k} {v:+.1f}%" for k, v in asset_returns.items() if v is not None),
        "Current rates: " +
        ", ".join(f"{k} {v:+.2f}%" for k, v in rate_summary.items()),
    ]
    if y10_state:
        ctx_parts.append(
            f"10Y yield: {y10_state['current']:.2f}% (p{y10_state['percentile']:.0f} of "
            f"{y10_state['n_observations']:,} observations). Bucket: {y10_state['bucket']}."
        )
        if y10_state.get("change_12m") is not None:
            ctx_parts.append(f"10Y 12-month change: {y10_state['change_12m']:+.2f}%.")
        if y10_rec.get("mean_fwd_ret") is not None:
            ctx_parts.append(
                f"Historical 1-year SPY forward return from current 10Y bucket: "
                f"{y10_rec['mean_fwd_ret']:+.1f}% (win rate {y10_rec['win_rate']:.0f}%). "
                f"Recommended cash deployment: {y10_rec['deploy_pct']:.0f}%."
            )
    ctx = "\n".join(ctx_parts)

    spread = rate_summary.get("10Y-2Y Spread")
    if spread is not None and spread < 0:
        fb = (f"<b>Verdict:</b> 🔴 RISK-OFF<br>"
              f"<b>Why:</b> 10Y-2Y curve INVERTED at {spread:+.2f}%. Historic recession lead.<br>"
              f"<b>Action:</b> Reduce equity exposure. 10Y deployment ladder suggests "
              f"{y10_rec.get('deploy_pct', 50):.0f}% cash deployment.<br>"
              f"<b>Watch for:</b> Curve un-inverting (often precedes recession itself).")
    elif y10_state and y10_rec.get("deploy_pct") is not None:
        fb = (f"<b>Why:</b> 10Y at {y10_state['current']:.2f}% (p{y10_state['percentile']:.0f}), "
              f"history says {y10_rec['mean_fwd_ret']:+.1f}% avg 1Y SPY return from this bucket.<br>"
              f"<b>Action:</b> Suggested cash deployment {y10_rec['deploy_pct']:.0f}%.<br>"
              f"<b>Watch for:</b> 10Y crossing above/below the next bucket boundary.")
    else:
        fb = "<b>Why:</b> Rates data loaded — see charts and ladder above."
    with segment_ai_slot.container():
        ai_summary.auto_summarize(st, ctx, page_kind="macro", fallback_text=fb)


# ============================================================
# Segment 3: Inflation
# ============================================================
elif segment == "🔥 Inflation":
    sel_assets = st.multiselect("Assets", list(ASSETS.keys()),
                                default=["S&P 500", "Bitcoin", "Gold"], key="i_a")
    period = st.radio("Period", list(PERIOD_MAP.keys()), index=4,
                      horizontal=True, key="i_p")
    days = {"1M": 90, "3M": 180, "YTD": 365, "1Y": 365, "2Y": 730, "5Y": 1825}[period]

    def _yoy(series_id, days):
        df = data.fred_series(series_id, days=days + 400)
        if df.empty:
            return df
        df = df.sort_values("date").reset_index(drop=True)
        df["value"] = df["value"].pct_change(12) * 100
        return df.dropna(subset=["value"])

    cpi = _yoy("CPIAUCSL", days)
    core_cpi = _yoy("CPILFESL", days)
    pce = _yoy("PCEPILFE", days)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for label in sel_assets:
        tk, color = ASSETS[label]
        df = data.get_history(tk, period=PERIOD_MAP[period])
        df = _slice_period(df, period)
        if df.empty:
            continue
        fig.add_trace(go.Scatter(x=df.index, y=_normalize(df["close"]).values,
                                  name=label, line=dict(color=color, width=2.5)),
                      secondary_y=False)
    for df_inf, lab, c in [(cpi, "CPI YoY", "#EF4444"),
                            (core_cpi, "Core CPI", "#FFD700"),
                            (pce, "Core PCE", "#A855F7")]:
        if not df_inf.empty:
            fig.add_trace(go.Scatter(x=df_inf["date"], y=df_inf["value"],
                                      name=lab, line=dict(color=c, width=1.5)),
                          secondary_y=True)
    fig.add_hline(y=2.0, line_dash="dash", line_color="rgba(34,197,94,0.5)",
                  secondary_y=True)
    fig.update_layout(template="plotly_dark", height=440,
                      paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                      yaxis=dict(title="Asset (start=100)"),
                      yaxis2=dict(title="YoY %", ticksuffix="%"),
                      margin=dict(l=0, r=0, t=20, b=0),
                      legend=dict(orientation="h", y=1.05),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    cur_pce = float(pce.iloc[-1]["value"]) if not pce.empty else None
    cur_cpi = float(cpi.iloc[-1]["value"]) if not cpi.empty else None
    ctx = (f"Period: {period}. Latest inflation prints: "
           f"CPI YoY {cur_cpi:.2f}%, " if cur_cpi is not None else ""
           ) + (f"Core PCE YoY {cur_pce:.2f}% (Fed targets 2%)." if cur_pce is not None else "")
    if cur_pce is not None:
        if cur_pce > 3:
            fb = (f"<b>Verdict:</b> 🔴 INFLATION HOT<br>"
                  f"<b>Why:</b> Core PCE {cur_pce:.2f}% — well above Fed 2% target.<br>"
                  f"<b>Action:</b> Expect Fed-hawkish stance. Long-duration assets (growth, REITs) face headwind.")
        elif cur_pce > 2.5:
            fb = (f"<b>Verdict:</b> 🟡 SLIGHTLY HOT<br>"
                  f"<b>Why:</b> Core PCE {cur_pce:.2f}% — modestly above target.")
        else:
            fb = (f"<b>Verdict:</b> 🟢 NEAR TARGET<br>"
                  f"<b>Why:</b> Core PCE {cur_pce:.2f}% — supportive of risk assets.")
    else:
        fb = "Inflation data unavailable."
    with segment_ai_slot.container():
        ai_summary.auto_summarize(st, ctx, page_kind="macro", fallback_text=fb)


# ============================================================
# Segment 4: Commodities
# ============================================================
elif segment == "🥇 Commodities":
    sel_assets = st.multiselect("Risk assets", list(ASSETS.keys()),
                                default=["S&P 500", "Bitcoin"], key="c_a")
    sel_havens = st.multiselect("Commodities / havens", list(ASSETS.keys()),
                                default=["Gold", "TLT 20Y"], key="c_h")
    period = st.radio("Period", list(PERIOD_MAP.keys()), index=3,
                      horizontal=True, key="c_p")

    fig = go.Figure()
    perfs = {}
    for label in list(set(sel_assets + sel_havens)):
        tk, color = ASSETS[label]
        df = data.get_history(tk, period=PERIOD_MAP[period])
        df = _slice_period(df, period)
        if df.empty:
            continue
        norm = _normalize(df["close"])
        fig.add_trace(go.Scatter(x=norm.index, y=norm.values, name=label,
                                  line=dict(color=color, width=2.5,
                                            dash="dot" if label in sel_havens else "solid")))
        perfs[label] = float(norm.iloc[-1] - 100) if not norm.empty else None
    fig.update_layout(template="plotly_dark", height=420,
                      paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                      yaxis=dict(title="Normalised (start=100)"),
                      margin=dict(l=0, r=0, t=20, b=0),
                      legend=dict(orientation="h", y=1.05),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    ctx = (f"Period: {period}. Performance: " +
           ", ".join(f"{k} {v:+.1f}%" for k, v in perfs.items() if v is not None))
    risk_avg = sum(v for k, v in perfs.items() if k in sel_assets and v is not None) / max(len(sel_assets), 1)
    haven_avg = sum(v for k, v in perfs.items() if k in sel_havens and v is not None) / max(len(sel_havens), 1)
    fb = (f"<b>Why:</b> Risk avg {risk_avg:+.1f}%, havens avg {haven_avg:+.1f}%.<br>"
          f"<b>Action:</b> {'Risk-on rotation in progress.' if risk_avg > haven_avg + 3 else 'Defensives outperforming — caution warranted.' if haven_avg > risk_avg + 3 else 'Mixed — neither leadership nor flight to safety dominant.'}")
    with segment_ai_slot.container():
        ai_summary.auto_summarize(st, ctx, page_kind="macro", fallback_text=fb)


# ============================================================
# ============================================================
# Segment 5: Sectors heatmap
# ============================================================
else:
    periods = st.multiselect(
        "Periods", ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y"],
        default=["1W", "1M", "3M", "YTD", "1Y"], key="s_p",
    )
    period_to_bars = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126,
                      "YTD": None, "1Y": 252}

    rows = []
    for tk, name in universe.SECTOR_ETFS.items():
        df = data.get_history(tk, period="2y")
        if df.empty:
            continue
        row = {"Sector": name}
        for p in periods:
            bars = period_to_bars[p]
            if bars is None:
                start = pd.Timestamp(year=pd.Timestamp.now().year, month=1, day=1)
                sub = df[df.index >= start]
                ret = (sub["close"].iloc[-1] / sub["close"].iloc[0] - 1) * 100 if len(sub) > 1 else None
            else:
                ret = (df["close"].iloc[-1] / df["close"].iloc[-bars - 1] - 1) * 100 if len(df) > bars else None
            row[p] = ret
        rows.append(row)

    if rows and periods:
        heat_df = pd.DataFrame(rows)
        matrix = heat_df.set_index("Sector")[periods]
        fig = px.imshow(matrix.values, x=periods, y=matrix.index,
                        text_auto=".1f", color_continuous_scale="RdYlGn",
                        zmin=-15, zmax=15, aspect="auto")
        fig.update_layout(template="plotly_dark", height=500,
                          paper_bgcolor="#0A0E1A",
                          margin=dict(l=0, r=0, t=20, b=0))
        fig.update_traces(textfont=dict(size=12, color="white"))
        st.plotly_chart(fig, use_container_width=True)

        if "1M" in matrix.columns and matrix["1M"].notna().any():
            leader_1m = matrix["1M"].idxmax()
            laggard_1m = matrix["1M"].idxmin()
            leader_3m = matrix["3M"].idxmax() if "3M" in matrix.columns and matrix["3M"].notna().any() else None
            ctx = (f"Sector heatmap. 1M leader: {leader_1m} ({matrix.loc[leader_1m, '1M']:+.1f}%). "
                   f"1M laggard: {laggard_1m} ({matrix.loc[laggard_1m, '1M']:+.1f}%). "
                   f"3M leader: {leader_3m or 'n/a'}. "
                   f"Durable: {'YES' if leader_1m == leader_3m else 'NO'}.")
            durable = leader_1m == leader_3m
            fb = (f"<b>Verdict:</b> {'DURABLE LEADERSHIP' if durable else 'ROTATIONAL'}<br>"
                  f"<b>Why:</b> {leader_1m} leads 1M ({matrix.loc[leader_1m, '1M']:+.1f}%), "
                  f"{'same name leads 3M' if durable else f'3M leader is {leader_3m}'}.<br>"
                  f"<b>Action:</b> Hunt stocks in {leader_1m if durable else 'sectors leading BOTH 1M and 3M'}.")
            with segment_ai_slot.container():
                ai_summary.auto_summarize(st, ctx, page_kind="macro", fallback_text=fb)


# ============================================================
# Fill the TOP AI slot (after all segments rendered)
# ============================================================
flags = state.components.get("flags", {})
try:
    vix_state = vix_analysis.current_state() or {}
except Exception:
    vix_state = {}

ctx_top = (
    f"Macro regime: {state.regime}, leverage gate: {state.leverage_gate}.\n"
    f"Component flags: VIX {flags.get('vix', 0):+d}, curve {flags.get('curve', 0):+d}, "
    f"credit {flags.get('credit', 0):+d}, SPY trend {flags.get('trend', 0):+d}.\n"
    f"VIX: {state.components.get('vix')}, percentile p{vix_state.get('percentile', 0):.0f}.\n"
    f"10Y-2Y: {state.components.get('10y_2y_spread')}, "
    f"HY OAS: {state.components.get('hy_oas')}."
)
mn = narrator.macro_story(state, vix_state)
fb_top = (f"<b>Verdict:</b> {mn['regime']}<br>"
          f"<b>Why:</b> {mn['headline']}<br>"
          f"<b>Action:</b> {mn['actions'][0] if mn['actions'] else 'Monitor.'}<br>"
          f"<b>Watch for:</b> Component flag flipping negative.")

with top_ai_slot.container():
    ai_summary.auto_summarize(st, ctx_top, page_kind="macro", fallback_text=fb_top)

st.caption("Research and decision-support tool. Not financial advice.")
