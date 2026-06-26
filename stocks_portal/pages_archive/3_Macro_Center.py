"""
Macro Center — unified macro & cross-asset terminal.

Tabs:
  🎯 Today           — current regime, leverage gate, component flags
  📊 VIX Deployment  — historical VIX analysis + cash-deployment ladder
  🌍 Asset Compare   — multi-select asset normalised performance + correlations
  💹 Rates & Curves  — assets vs interest rates + recession-signal markers
  🔥 Inflation       — assets vs CPI/PCE
  🥇 Commodities     — assets vs gold/silver/oil/havens
  🗺 Sector Heatmap  — multi-period sector performance grid
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import ai_summary, data, explainers, macro, narrator, universe, vix_analysis

st.set_page_config(page_title="Macro Center", layout="wide")
st.title("📈 Macro Center")
st.caption("Single source of truth for the top-down: regime, VIX deployment, cross-asset, rates, inflation, sectors.")

explainers.help_box(st, "What this page tells you (in plain English)", """
This is the **'what's the weather like out there?'** page. Position trading lives or dies on getting
the macro environment right.

The hero banner at the top tells you in one number whether the environment is **risk-on** (push the
gas) or **risk-off** (preserve capital). It also drives the **leverage gate** — a binary 🟢/🟡/🔴
indicator for whether 3× ETFs (TQQQ, SOXL, FNGU) are safe to hold today.

Then 7 tabs:
- **🎯 Today** — current state at a glance
- **📊 VIX & Deployment** — historical VIX analysis with a data-backed cash deployment ladder
  (deploy X% of your cash based on where VIX is, derived from 30+ years of SPY returns at each VIX level)
- **🌍 Asset Compare** — pick any assets, see how they've performed
- **💹 Rates & Curves** — yields, spreads, and the recession-signal markers
- **🔥 Inflation** — CPI/PCE trajectory vs your assets
- **🥇 Commodities** — gold, oil, bonds, dollar
- **🗺 Sectors** — leadership rotation across timeframes

**The simple decision rule:** check this page first thing every day. Confirm the gate is GREEN
before initiating new long positions. Reduce size when YELLOW. Stay in cash when RED.
""")

with st.expander("📚 Risk-on vs Defensive — the foundational concept (read this if you've ever been confused by these terms)", expanded=False):
    explainers.render_risk_regime_explainer(st)

# ============================================================
# Always-visible hero — regime + leverage gate
# ============================================================
state = macro.assess()
gate_color = {"GREEN": "#22C55E", "YELLOW": "#FF8C00", "RED": "#EF4444"}[state.leverage_gate]

st.markdown(f"""
<div style="background:#11182A;padding:1.2rem;border-left:6px solid {gate_color};border-radius:4px;margin-bottom:1rem">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <div style="color:#8a93a6;font-size:0.85rem;text-transform:uppercase">Current state</div>
      <div style="font-size:2rem;font-weight:bold;color:{gate_color}">{state.regime}</div>
      <div style="font-size:1.1rem;color:{gate_color};opacity:0.85">Leverage gate: {state.leverage_gate}</div>
    </div>
    <div style="font-size:0.9rem;color:#bcc3d6;max-width:60%;text-align:right">
      {state.summary}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# Asset / macro registry (used across tabs)
# ============================================================
ASSETS = {
    "S&P 500":          {"ticker": "SPY",     "color": "#22C55E"},
    "Nasdaq 100":       {"ticker": "QQQ",     "color": "#3B82F6"},
    "Nasdaq Composite": {"ticker": "^IXIC",   "color": "#60A5FA"},
    "Russell 2000":     {"ticker": "IWM",     "color": "#A855F7"},
    "Dow Jones":        {"ticker": "DIA",     "color": "#06B6D4"},
    "S&P MidCap 400":   {"ticker": "MDY",     "color": "#14B8A6"},
    "MSCI EAFE (Devel.)": {"ticker": "EFA",   "color": "#FFD700"},
    "MSCI Emerging":    {"ticker": "EEM",     "color": "#EC4899"},
    "REITs":            {"ticker": "VNQ",     "color": "#8B5CF6"},
    "Bitcoin":          {"ticker": "BTC-USD", "color": "#FF8C00"},
    "Ethereum":         {"ticker": "ETH-USD", "color": "#627EEA"},
    "Gold":             {"ticker": "GLD",     "color": "#FFD700"},
    "Silver":           {"ticker": "SLV",     "color": "#C0C0C0"},
    "Oil (USO)":        {"ticker": "USO",     "color": "#16A34A"},
    "Broad Commodities": {"ticker": "DBC",    "color": "#84CC16"},
    "20+ Yr Treasury":  {"ticker": "TLT",     "color": "#EF4444"},
    "USD Index (UUP)":  {"ticker": "UUP",     "color": "#0EA5E9"},
}

MACRO_SERIES = {
    "10Y Yield":       {"id": "DGS10",        "kind": "rate",  "color": "#EF4444",
        "tag": "⊖ rate-sensitive",         "rec_for": ["S&P 500", "Nasdaq 100", "Bitcoin", "REITs"],
        "note": "Rising 10Y compresses growth multiples. Strong inverse to QQQ, mild inverse to SPY."},
    "2Y Yield":        {"id": "DGS2",         "kind": "rate",  "color": "#FFD700",
        "tag": "Fed-policy proxy",         "rec_for": ["S&P 500", "Russell 2000", "Bitcoin"],
        "note": "Tracks expected Fed path. Inverse to risk assets when rising rapidly."},
    "30Y Yield":       {"id": "DGS30",        "kind": "rate",  "color": "#F472B6",
        "tag": "Long-duration",            "rec_for": ["20+ Yr Treasury", "REITs"]},
    "3M T-Bill":       {"id": "DGS3MO",       "kind": "rate",  "color": "#A78BFA",
        "tag": "Short-end",                "rec_for": []},
    "Fed Funds Rate":  {"id": "DFF",          "kind": "rate",  "color": "#A855F7",
        "tag": "Policy rate",              "rec_for": ["S&P 500", "Bitcoin"]},
    "10Y - 2Y Spread": {"id": "T10Y2Y",       "kind": "spread","color": "#22C55E",
        "tag": "⚠ RECESSION SIGNAL",       "rec_for": ["S&P 500", "Russell 2000"],
        "note": "Sustained inversion has preceded every US recession since 1955 (lead 6-18 months)."},
    "10Y - 3M Spread": {"id": "T10Y3M",       "kind": "spread","color": "#16A34A",
        "tag": "⚠ Estrella-Mishkin recession signal", "rec_for": ["S&P 500", "Russell 2000"],
        "note": "NY Fed considers this the most reliable recession lead indicator."},
    "CPI YoY":         {"id": "CPIAUCSL",     "kind": "yoy",   "color": "#EF4444",
        "tag": "Inflation (headline)",     "rec_for": ["S&P 500", "Gold", "Bitcoin"]},
    "Core CPI YoY":    {"id": "CPILFESL",     "kind": "yoy",   "color": "#FFD700",
        "tag": "Inflation (sticky)",       "rec_for": ["S&P 500"]},
    "PCE YoY":         {"id": "PCEPI",        "kind": "yoy",   "color": "#EC4899",
        "tag": "Fed-preferred",            "rec_for": ["S&P 500", "Bitcoin"]},
    "Core PCE YoY":    {"id": "PCEPILFE",     "kind": "yoy",   "color": "#A855F7",
        "tag": "★ Fed's actual target",    "rec_for": ["S&P 500", "Nasdaq 100"]},
    "HY Credit OAS":   {"id": "BAMLH0A0HYM2", "kind": "rate",  "color": "#EF4444",
        "tag": "Risk-on/off",              "rec_for": ["Russell 2000", "S&P 500", "Bitcoin"]},
    "IG Credit OAS":   {"id": "BAMLC0A0CM",   "kind": "rate",  "color": "#FFD700",
        "tag": "IG bond risk",             "rec_for": ["S&P 500"]},
    "Unemployment":    {"id": "UNRATE",       "kind": "rate",  "color": "#F97316",
        "tag": "Late-cycle",               "rec_for": ["S&P 500", "Russell 2000"]},
    "VIX":             {"id": "VIXCLS",       "kind": "vix",   "color": "#EF4444",
        "tag": "★ STRONG INVERSE for risk", "rec_for": ["S&P 500", "Nasdaq 100", "Bitcoin"]},
}

PERIOD_MAP = {
    "1D": ("5d", 1), "1W": ("1mo", 5), "1M": ("3mo", 21), "3M": ("6mo", 63),
    "YTD": ("ytd", None), "1Y": ("1y", 252), "2Y": ("2y", 504),
    "5Y": ("5y", 1260), "10Y": ("10y", 2520), "Max": ("max", None),
}

PERIOD_TO_DAYS = {"1D": 7, "1W": 30, "1M": 90, "3M": 180, "YTD": 365,
                  "1Y": 365, "2Y": 730, "5Y": 1825, "10Y": 3650, "Max": 18250}


# ============================================================
# Helpers
# ============================================================
def _slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    if df.empty:
        return df
    if period == "YTD":
        start = pd.Timestamp(year=pd.Timestamp.now().year, month=1, day=1)
        return df[df.index >= start]
    return df


def _normalize(s: pd.Series) -> pd.Series:
    s = s.dropna()
    return s / s.iloc[0] * 100 if not s.empty else s


def _pct_return(s: pd.Series) -> float | None:
    s = s.dropna()
    return float((s.iloc[-1] / s.iloc[0] - 1) * 100) if len(s) >= 2 else None


def _correlation(a: pd.Series, b: pd.Series) -> float | None:
    df = pd.concat([a.pct_change(), b.pct_change()], axis=1).dropna()
    return float(df.corr().iloc[0, 1]) if len(df) >= 5 else None


def _fred_with_yoy(spec: dict, days: int) -> pd.DataFrame:
    extra = 400 if spec["kind"] == "yoy" else 30
    raw = data.fred_series(spec["id"], days=days + extra)
    if raw.empty:
        return raw
    raw = raw.sort_values("date").reset_index(drop=True)
    if spec["kind"] == "yoy":
        raw["value"] = raw["value"].pct_change(12) * 100
        raw = raw.dropna(subset=["value"])
    return raw


def _fetch_assets(picks: list, period: str) -> dict:
    yf_period, _ = PERIOD_MAP[period]
    out = {}
    for label in picks:
        spec = ASSETS[label]
        df = data.get_history(spec["ticker"], period=yf_period)
        df = _slice_period(df, period)
        if df.empty:
            continue
        out[label] = df["close"]
    return out


def _add_event_lines(fig, events: list, color: str = "rgba(239,68,68,0.4)"):
    for date, label in events:
        try:
            x_val = pd.Timestamp(date).strftime("%Y-%m-%d")
        except Exception:
            x_val = str(date)
        try:
            fig.add_vline(x=x_val, line_dash="dot", line_color=color,
                          annotation_text=label, annotation_position="top",
                          annotation=dict(font=dict(size=10, color=color)))
        except Exception:
            try:
                fig.add_shape(type="line", x0=x_val, x1=x_val, y0=0, y1=1,
                              xref="x", yref="paper",
                              line=dict(dash="dot", color=color))
            except Exception:
                continue


def _detect_inversions(spread_df: pd.DataFrame) -> list:
    events = []
    inverted = False
    last_event_date = None
    for _, row in spread_df.iterrows():
        try:
            v = float(row["value"])
        except Exception:
            continue
        if v < 0 and not inverted:
            inverted = True
            if last_event_date is None or (row["date"] - last_event_date).days > 30:
                events.append((row["date"], "Curve inverted"))
                last_event_date = row["date"]
        elif v >= 0 and inverted:
            inverted = False
            if last_event_date is None or (row["date"] - last_event_date).days > 30:
                events.append((row["date"], "Un-inverted"))
                last_event_date = row["date"]
    return events


def _multiselect_with_tags(label: str, options: list, defaults: list, key: str,
                           focus_assets: list | None = None):
    valid_defaults = [d for d in defaults if d in options]
    def _fmt(option):
        spec = MACRO_SERIES.get(option, {})
        tag = spec.get("tag", "")
        rec_for = spec.get("rec_for", [])
        star = "★ " if focus_assets and any(fa in rec_for for fa in focus_assets) else ""
        return f"{star}{option}" + (f"  —  {tag}" if tag else "")
    return st.multiselect(label, options, default=valid_defaults, key=key, format_func=_fmt)


# ============================================================
# Tabs
# ============================================================
tab_today, tab_vix, tab_assets, tab_rates, tab_infl, tab_commod, tab_sectors = st.tabs([
    "🎯 Today", "📊 VIX & Deployment", "🌍 Asset Compare",
    "💹 Rates & Curves", "🔥 Inflation", "🥇 Commodities", "🗺 Sectors",
])

# ============================================================
# TAB 1 — TODAY
# ============================================================
with tab_today:
    st.subheader("Component flags")

    flags = state.components.get("flags", {})
    c1, c2, c3, c4 = st.columns(4)

    def _flag_card(col, name, val):
        color = "#22C55E" if val > 0 else "#EF4444" if val < 0 else "#FFD700"
        label = "🟢 Risk-on" if val > 0 else "🔴 Risk-off" if val < 0 else "🟡 Neutral"
        col.markdown(f"""
        <div style="background:#11182A;padding:1rem;border-left:4px solid {color}">
          <div style="color:#8a93a6;font-size:0.75rem;text-transform:uppercase">{name}</div>
          <div style="font-size:1.5rem;font-weight:bold;color:{color}">{label}</div>
          <div style="font-size:0.85rem;color:#bcc3d6">Score: {val:+d}</div>
        </div>""", unsafe_allow_html=True)

    _flag_card(c1, "VIX",         flags.get("vix", 0))
    _flag_card(c2, "Yield Curve", flags.get("curve", 0))
    _flag_card(c3, "HY Credit",   flags.get("credit", 0))
    _flag_card(c4, "SPY Trend",   flags.get("trend", 0))

    # Narrator card + optional AI elaboration
    try:
        vix_state_for_narrator = vix_analysis.current_state()
    except Exception:
        vix_state_for_narrator = None
    macro_narrative = narrator.macro_story(state, vix_state_for_narrator)
    narrator.render_narrator_card(
        st,
        headline=macro_narrative["headline"],
        narrative=macro_narrative["narrative"],
        actions=macro_narrative["actions"],
        badge_color=macro_narrative["badge_color"],
        regime=macro_narrative["regime"],
    )

    ai_ctx = (
        f"Macro regime classification: {state.regime}, leverage gate {state.leverage_gate}.\n"
        f"Component flags: VIX {flags.get('vix', 0):+d}, curve {flags.get('curve', 0):+d}, "
        f"credit {flags.get('credit', 0):+d}, SPY trend {flags.get('trend', 0):+d}.\n"
        f"VIX value: {state.components.get('vix')}, 10Y-2Y: {state.components.get('10y_2y_spread')}, "
        f"HY OAS: {state.components.get('hy_oas')}.\n"
        f"Pre-baked summary: {macro_narrative['headline']} {macro_narrative['narrative']}"
    )
    ai_summary.render_ai_button(st, ai_ctx, key="macro_today")

    st.divider()
    st.subheader("Playbook by regime")
    st.markdown("""
| Regime | Stock Selection | ETF Posture | Leverage |
|---|---|---|---|
| **🟢 RISK_ON / Gate GREEN** | Aggressive growth + cyclicals. Tech, semis, small caps | TQQQ, SOXL, FNGU at full size | 3× eligible at full risk-per-trade |
| **🟡 NEUTRAL / Gate YELLOW** | Quality leaders only. Reduce factor tilts | QQQ over TQQQ. Half size on 3× | Reduce 3× to half. Prefer 1× |
| **🔴 RISK_OFF / Gate RED** | Defensives only (XLP, XLV, XLU). Avoid high-beta | Cash + inverse hedges (SQQQ, SOXS) | No 3× longs. Inverse 3× as hedge with strict stops |
""")


# ============================================================
# TAB 2 — VIX & DEPLOYMENT
# ============================================================
with tab_vix:
    st.subheader("📊 VIX historical analysis + cash-deployment ladder")
    st.caption("Built from 30+ years of daily VIX + SPY closes. The deployment ladder is a heuristic from past data, not a forecast.")

    horizon_choice = st.radio("Forward horizon for the deployment math",
                              ["1 month (21d)", "3 months (63d)", "6 months (126d)",
                               "1 year (252d)", "2 years (504d)"],
                              horizontal=True, index=3)
    horizon_map = {"1 month (21d)": 21, "3 months (63d)": 63, "6 months (126d)": 126,
                   "1 year (252d)": 252, "2 years (504d)": 504}
    horizon = horizon_map[horizon_choice]

    with st.spinner("Pulling 30+ years of VIX and SPY history (cached for 24h)…"):
        state_vix = vix_analysis.current_state()
        rec = vix_analysis.deploy_recommendation_for_current_vix(horizon)
        ladder = vix_analysis.deployment_ladder(horizon)

    if not state_vix or ladder.empty:
        # Diagnostic to show which side failed
        raw = vix_analysis.get_vix_spy_history()
        if raw.empty:
            st.error("**Both VIX and SPY history failed to load.** "
                     "yfinance and FRED were both unreachable. Check your internet connection. "
                     "If you're on a corporate network, the SSL/proxy may be blocking outbound calls.")
        elif len(raw) < 252:
            st.error(f"Only {len(raw)} days of data loaded — need at least 252 (1 year) for the analysis. "
                     "yfinance may have rate-limited. Wait 60 seconds and refresh the page.")
        else:
            st.error("History loaded but bucketing failed unexpectedly. Try a different forward-horizon.")
        st.stop()
    else:
        # -------- Current snapshot --------
        cur = state_vix["current"]
        cur_pctile = state_vix["percentile"]
        bucket = state_vix["bucket"]
        deploy_pct = rec.get("deploy_pct", None)
        mean_fwd = rec.get("mean_fwd_ret", None)
        win_rate = rec.get("win_rate", None)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VIX now", f"{cur:.1f}",
                  f"p{cur_pctile:.0f} historically")
        c2.metric("Bucket", bucket if bucket else "—")
        c3.metric(f"Hist {horizon}d fwd SPY",
                  f"{mean_fwd:+.1f}%" if mean_fwd is not None else "—",
                  f"win rate {win_rate:.0f}%" if win_rate is not None else "")
        c4.metric("Recommended deployment",
                  f"{deploy_pct:.0f}%" if deploy_pct is not None else "—")

        # -------- VIX history with current marker --------
        st.markdown("**VIX historical distribution + current reading**")
        dist_df = vix_analysis.vix_distribution_data()
        if not dist_df.empty:
            colL, colR = st.columns([2, 1])
            with colL:
                fig = go.Figure()
                fig.add_trace(go.Histogram(
                    x=dist_df["vix"], nbinsx=60,
                    marker_color="#FF8C00", opacity=0.7,
                ))
                fig.add_vline(x=cur, line_color="#22C55E", line_width=3,
                              annotation_text=f"Now: {cur:.1f}",
                              annotation_position="top")
                fig.add_vline(x=15, line_dash="dot", line_color="#22C55E",
                              annotation_text="15")
                fig.add_vline(x=20, line_dash="dot", line_color="#FFD700",
                              annotation_text="20")
                fig.add_vline(x=30, line_dash="dot", line_color="#EF4444",
                              annotation_text="30")
                fig.update_layout(
                    template="plotly_dark", height=380,
                    paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                    xaxis=dict(title="VIX value"),
                    yaxis=dict(title="Days observed"),
                    margin=dict(l=0, r=0, t=20, b=0),
                )
                st.plotly_chart(fig, use_container_width=True)

            with colR:
                st.markdown(f"""
                **Historical context**

                Period: {state_vix['history_start'].strftime('%Y-%m-%d')} →
                {state_vix['history_end'].strftime('%Y-%m-%d')}
                ({state_vix['n_observations']:,} trading days)

                - **Mean VIX**: {state_vix['mean_historical']:.1f}
                - **Median VIX**: {state_vix['median_historical']:.1f}
                - **Current VIX**: {cur:.1f}
                - **Current percentile**: p{cur_pctile:.0f}
                  ({100-cur_pctile:.0f}% of history was higher)
                """)

        st.divider()

        # -------- Deployment ladder table --------
        st.markdown("**🎯 Cash-deployment ladder — derived from history**")
        st.caption(f"For each VIX bucket: forward SPY return over {horizon} trading days, "
                   "and the % of cash to deploy when VIX sits in that bucket.")

        display = ladder.copy()
        # Mark current bucket
        cur_marker = ["👉 NOW" if b == bucket else "" for b in display["bucket"]]
        display.insert(0, "", cur_marker)
        display.columns = ["", "Bucket", "VIX range", "n obs",
                           f"Mean {horizon}d fwd %", f"Median {horizon}d fwd %",
                           "Win rate %", "P10 %", "P90 %", "Deploy %"]

        # Format
        for c in [f"Mean {horizon}d fwd %", f"Median {horizon}d fwd %",
                  "Win rate %", "P10 %", "P90 %"]:
            display[c] = display[c].map(lambda x: f"{x:+.1f}" if pd.notna(x) else "—")
        display["Deploy %"] = display["Deploy %"].map(lambda x: f"{x:.0f}%")

        def _highlight_now(row):
            if str(row.iloc[0]).startswith("👉"):
                return ["background-color: rgba(255, 140, 0, 0.25); font-weight: bold"] * len(row)
            return [""] * len(row)

        st.dataframe(
            display.style.apply(_highlight_now, axis=1),
            use_container_width=True, hide_index=True,
        )

        # -------- Mean forward return chart --------
        fig = go.Figure(go.Bar(
            x=ladder["bucket"], y=ladder["mean_fwd_ret"],
            marker_color=["#22C55E" if v > 0 else "#EF4444" for v in ladder["mean_fwd_ret"]],
            text=[f"{v:+.1f}%" for v in ladder["mean_fwd_ret"]], textposition="outside",
        ))
        fig.update_layout(
            template="plotly_dark", height=380,
            title=f"Historical SPY {horizon}d-forward return by VIX bucket",
            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
            yaxis=dict(title="Mean forward return %", ticksuffix="%"),
            margin=dict(l=0, r=0, t=50, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # -------- Interpretation --------
        if deploy_pct is not None:
            equity = 100_000
            deploy_amt = equity * deploy_pct / 100
            cash_amt = equity - deploy_amt

            st.success(f"""
            **🎯 Recommendation given VIX = {cur:.1f}** (bucket: {bucket}):

            **Deploy ~{deploy_pct:.0f}% of cash to equities. Hold ~{100-deploy_pct:.0f}% in cash.**

            Why: historically, when VIX has been in this range, SPY's average {horizon}-trading-day
            forward return was **{mean_fwd:+.1f}%**, with a {win_rate:.0f}% win rate
            (across {int(rec.get('n', 0)):,} historical observations).

            **Worked example on $100,000:** deploy ~${deploy_amt:,.0f}, hold ~${cash_amt:,.0f} in cash.
            """)

        st.markdown("""
        ---
        ### How to read this

        The deployment % is **scaled linearly** between the bucket with the worst historical mean
        forward return (10% deployment) and the best (100% deployment). Higher VIX has historically
        been a buying opportunity because:

        1. **VIX is mean-reverting.** Spikes don't last. Each VIX > 30 reading in history was followed
           by a return to 15-25 within months.
        2. **High VIX correlates with depressed prices.** You're buying after the puke, not before it.
        3. **The risk premium expands.** Fearful investors demand a higher return to hold equities,
           and history shows that premium materialises.

        **What the data IS NOT:**
        - Not a market-timing tool for short horizons.
        - Not predictive of *which day* the rebound starts.
        - Not safe to use alone — pair with the regime gate at the top of this page and the
          stage analysis on individual names.
        - Not a guarantee. Past distributions are informative but not dispositive.

        **The simple rule that emerges from the data:**
        > 🟢 Buy fear (VIX > 30): the data has rewarded this consistently since 1990.
        > 🟡 Wait at calm (VIX < 15): forward returns are below average. Don't FOMO.
        > 🟧 Lean in at elevated (VIX 20-25): better forward returns than calm, with manageable risk.
        """)


# ============================================================
# TAB 3 — ASSET COMPARE
# ============================================================
with tab_assets:
    st.subheader("Asset comparison (multi-select)")

    s1_assets = st.multiselect(
        "Assets",
        list(ASSETS.keys()),
        default=["S&P 500", "Nasdaq 100", "Russell 2000", "Bitcoin", "Ethereum", "Gold"],
        key="s1_assets",
    )
    s1_period = st.radio("Period", list(PERIOD_MAP.keys()),
                         horizontal=True, index=6, key="s1_period")

    series_dict = _fetch_assets(s1_assets, s1_period)
    if not series_dict:
        st.warning("No assets selected.")
    else:
        fig = go.Figure()
        for label, s in series_dict.items():
            fig.add_trace(go.Scatter(
                x=s.index, y=_normalize(s).values, name=label,
                line=dict(color=ASSETS[label]["color"], width=2),
            ))
        fig.update_layout(
            template="plotly_dark", height=460,
            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
            yaxis=dict(title="Normalised (start=100)"),
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(orientation="h", y=1.05),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        rt = pd.DataFrame([{"Asset": k, "Return %": _pct_return(v)}
                           for k, v in series_dict.items()])
        rt = rt.sort_values("Return %", ascending=False).reset_index(drop=True)
        rt_fmt = rt.copy()
        rt_fmt["Return %"] = rt_fmt["Return %"].map(lambda x: f"{x:+.2f}%" if x is not None else "—")
        st.dataframe(rt_fmt, use_container_width=True, hide_index=True)

        if len(series_dict) >= 2:
            ret_df = pd.DataFrame({k: v.pct_change() for k, v in series_dict.items()}).dropna()
            if not ret_df.empty:
                corr = ret_df.corr()
                fig_c = px.imshow(corr.values, x=corr.columns, y=corr.index,
                                  text_auto=".2f", color_continuous_scale="RdBu_r",
                                  zmin=-1, zmax=1, aspect="auto")
                fig_c.update_layout(template="plotly_dark", height=320,
                                    paper_bgcolor="#0A0E1A",
                                    margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig_c, use_container_width=True)


# ============================================================
# TAB 4 — RATES
# ============================================================
with tab_rates:
    st.subheader("Assets vs interest rates / curves")

    c1, c2 = st.columns(2)
    with c1:
        s2_assets = st.multiselect("Assets", list(ASSETS.keys()),
                                   default=["S&P 500", "Bitcoin"], key="s2_assets")
    with c2:
        rate_options = [k for k, v in MACRO_SERIES.items() if v["kind"] in ("rate", "spread")]
        s2_rates = _multiselect_with_tags(
            "Rates / Spreads (★ = recommended for your asset)",
            rate_options,
            defaults=["10Y Yield", "10Y - 2Y Spread"],
            key="s2_rates",
            focus_assets=s2_assets,
        )
    s2_period = st.radio("Period", list(PERIOD_MAP.keys()),
                         horizontal=True, index=7, key="s2_period")
    days = PERIOD_TO_DAYS[s2_period]

    series_dict = _fetch_assets(s2_assets, s2_period)
    rate_data = {r: _fred_with_yoy(MACRO_SERIES[r], days) for r in s2_rates}

    if series_dict or any(not d.empty for d in rate_data.values()):
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for label, s in series_dict.items():
            fig.add_trace(go.Scatter(
                x=s.index, y=_normalize(s).values, name=label,
                line=dict(color=ASSETS[label]["color"], width=2.5),
            ), secondary_y=False)
        for label, df_r in rate_data.items():
            if df_r.empty:
                continue
            fig.add_trace(go.Scatter(
                x=df_r["date"], y=df_r["value"], name=label,
                line=dict(color=MACRO_SERIES[label]["color"], width=1.5, dash="dot"),
            ), secondary_y=True)
        for label in s2_rates:
            if MACRO_SERIES[label]["kind"] == "spread" and not rate_data[label].empty:
                _add_event_lines(fig, _detect_inversions(rate_data[label]),
                                 color="rgba(239,68,68,0.5)")
        fig.update_layout(
            template="plotly_dark", height=460,
            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
            yaxis=dict(title="Asset (start=100)"),
            yaxis2=dict(title="Yield / Spread (%)", ticksuffix="%"),
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(orientation="h", y=1.05),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Inversion warning
        for label in s2_rates:
            if MACRO_SERIES[label]["kind"] == "spread":
                df_s = rate_data.get(label)
                if df_s is not None and not df_s.empty:
                    if df_s.iloc[-1]["value"] < 0:
                        st.error(f"⚠ **{label}** currently INVERTED at "
                                 f"{df_s.iloc[-1]['value']:+.2f}%. Historic recession lead indicator.")


# ============================================================
# TAB 5 — INFLATION
# ============================================================
with tab_infl:
    st.subheader("Assets vs inflation")

    c1, c2 = st.columns(2)
    with c1:
        s3_assets = st.multiselect("Assets", list(ASSETS.keys()),
                                   default=["S&P 500", "Bitcoin", "Gold"], key="s3_assets")
    with c2:
        infl_options = [k for k, v in MACRO_SERIES.items() if v["kind"] == "yoy"]
        s3_infl = _multiselect_with_tags(
            "Inflation measures (★ = recommended for your asset)",
            infl_options,
            defaults=["CPI YoY", "Core CPI YoY"],
            key="s3_infl",
            focus_assets=s3_assets,
        )
    s3_period = st.radio("Period", list(PERIOD_MAP.keys()),
                         horizontal=True, index=7, key="s3_period")
    days = PERIOD_TO_DAYS[s3_period]

    series_dict = _fetch_assets(s3_assets, s3_period)
    infl_data = {label: _fred_with_yoy(MACRO_SERIES[label], days) for label in s3_infl}

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for label, s in series_dict.items():
        fig.add_trace(go.Scatter(
            x=s.index, y=_normalize(s).values, name=label,
            line=dict(color=ASSETS[label]["color"], width=2.5),
        ), secondary_y=False)
    for label, df_i in infl_data.items():
        if df_i.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df_i["date"], y=df_i["value"], name=label,
            line=dict(color=MACRO_SERIES[label]["color"], width=1.5),
        ), secondary_y=True)
    fig.add_hline(y=2.0, line_dash="dash", line_color="rgba(34,197,94,0.5)",
                  annotation_text="Fed 2% target", secondary_y=True)
    fig.add_hline(y=5.0, line_dash="dot", line_color="rgba(239,68,68,0.5)",
                  annotation_text="5% danger", secondary_y=True)
    fig.update_layout(
        template="plotly_dark", height=460,
        paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
        yaxis=dict(title="Asset (start=100)"),
        yaxis2=dict(title="YoY %", ticksuffix="%"),
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", y=1.05),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 6 — COMMODITIES
# ============================================================
with tab_commod:
    st.subheader("Risk assets vs commodities / havens")

    c1, c2 = st.columns(2)
    with c1:
        s4_assets = st.multiselect("Risk assets", list(ASSETS.keys()),
                                   default=["S&P 500", "Bitcoin"], key="s4_assets")
    with c2:
        s4_havens = st.multiselect("Commodities / havens", list(ASSETS.keys()),
                                   default=["Gold", "20+ Yr Treasury"], key="s4_havens")
    s4_period = st.radio("Period", list(PERIOD_MAP.keys()),
                         horizontal=True, index=6, key="s4_period")

    all_picks = list(set(s4_assets + s4_havens))
    series_dict = _fetch_assets(all_picks, s4_period)

    if series_dict:
        fig = go.Figure()
        for label, s in series_dict.items():
            fig.add_trace(go.Scatter(
                x=s.index, y=_normalize(s).values, name=label,
                line=dict(color=ASSETS[label]["color"], width=2.5,
                          dash="dot" if label in s4_havens else "solid"),
            ))
        fig.update_layout(
            template="plotly_dark", height=440,
            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
            yaxis=dict(title="Normalised (start=100)"),
            margin=dict(l=0, r=0, t=20, b=0),
            legend=dict(orientation="h", y=1.05),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# TAB 7 — SECTORS
# ============================================================
with tab_sectors:
    st.subheader("Sector heatmap — multi-period performance")

    heatmap_periods = st.multiselect(
        "Periods",
        ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y"],
        default=["1D", "1W", "1M", "3M", "YTD", "1Y"],
        key="s5_periods",
    )

    period_to_bars = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126,
                      "YTD": None, "1Y": 252, "2Y": 504, "5Y": 1260}

    if heatmap_periods:
        max_bars = max([b for b in (period_to_bars[p] for p in heatmap_periods)
                        if b is not None] + [252])
        period_pull = "5y" if max_bars > 504 else "2y"

        rows = []
        for tk, name in universe.SECTOR_ETFS.items():
            df = data.get_history(tk, period=period_pull)
            if df.empty:
                continue
            row = {"Sector": name, "ETF": tk}
            for p in heatmap_periods:
                bars = period_to_bars[p]
                if bars is None:
                    start = pd.Timestamp(year=pd.Timestamp.now().year, month=1, day=1)
                    sub = df[df.index >= start]
                    ret = ((sub["close"].iloc[-1] / sub["close"].iloc[0] - 1) * 100
                           if len(sub) > 1 else None)
                else:
                    if len(df) > bars:
                        ret = (df["close"].iloc[-1] / df["close"].iloc[-bars-1] - 1) * 100
                    else:
                        ret = None
                row[p] = ret
            rows.append(row)

        if rows:
            heat_df = pd.DataFrame(rows)
            matrix = heat_df.set_index("Sector")[heatmap_periods]
            fig = px.imshow(
                matrix.values, x=heatmap_periods, y=matrix.index,
                text_auto=".1f", color_continuous_scale="RdYlGn",
                zmin=-15, zmax=15, aspect="auto",
            )
            fig.update_layout(template="plotly_dark", height=540,
                              paper_bgcolor="#0A0E1A",
                              margin=dict(l=0, r=0, t=20, b=0))
            fig.update_traces(textfont=dict(size=12, color="white"))
            st.plotly_chart(fig, use_container_width=True)
