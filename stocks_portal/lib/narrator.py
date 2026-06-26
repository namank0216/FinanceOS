"""
Deterministic data narrator — generates plain-English summaries from
quantitative data. No LLM needed; just rules + templates.

Looks like AI commentary, runs in milliseconds, costs nothing.
For each domain (sectors, screen results, VIX, macro), takes the data and
produces a 2-3 paragraph 'what this is telling you' summary.
"""

from __future__ import annotations

import pandas as pd

# Sector classifications — matches lib/explainers.py
GROWTH_SECTORS = {"Technology", "Consumer Discretionary", "Communication Services"}
DEFENSIVE_SECTORS = {"Consumer Staples", "Utilities", "Health Care"}
CYCLICAL_SECTORS = {"Financials", "Industrials", "Materials", "Energy"}
RATE_SENSITIVE = {"Real Estate", "Utilities"}


# ============================================================
# SECTOR NARRATIVE — for Market Cockpit
# ============================================================
def sector_story(today_df: pd.DataFrame, month_df: pd.DataFrame) -> dict:
    """
    Generate a markdown narrative + headline regime classification from
    today's and 1-month sector returns.

    Inputs (both with columns ['Sector', 'Change %' or '1M %']):
      today_df: today's % change per sector
      month_df: 1-month % return per sector

    Returns: {'regime': str, 'badge_color': str, 'headline': str, 'narrative': str, 'actions': [str]}
    """
    if today_df.empty or month_df.empty:
        return {"regime": "—", "badge_color": "#8a93a6",
                "headline": "Sector data unavailable.",
                "narrative": "", "actions": []}

    today_col = "Change %" if "Change %" in today_df.columns else today_df.columns[-1]
    month_col = "1M %" if "1M %" in month_df.columns else month_df.columns[-1]

    today_df = today_df.copy().sort_values(today_col, ascending=False)
    month_df = month_df.copy().sort_values(month_col, ascending=False)

    # Today's leaders/laggards
    t_leader = today_df.iloc[0]
    t_laggard = today_df.iloc[-1]

    # Month leaders/laggards
    m_leader = month_df.iloc[0]
    m_laggard = month_df.iloc[-1]

    # Group averages over the past month
    def _avg(df, sectors):
        sub = df[df["Sector"].isin(sectors)]
        return float(sub[month_col].mean()) if not sub.empty else 0.0

    growth_1m = _avg(month_df, GROWTH_SECTORS)
    defensive_1m = _avg(month_df, DEFENSIVE_SECTORS)
    cyclical_1m = _avg(month_df, CYCLICAL_SECTORS)

    # Spread between growth and defensives — the cleanest risk-on/risk-off signal
    spread = growth_1m - defensive_1m

    # Regime classification
    if spread > 5 and growth_1m > 3:
        regime = "🟢 RISK-ON"
        badge = "#22C55E"
        headline = (f"Growth/cyclicals leading hard — investors are buying risk. "
                    f"Growth sectors averaged {growth_1m:+.1f}% over the past month "
                    f"vs defensives at {defensive_1m:+.1f}%.")
    elif spread < -3 and defensive_1m > growth_1m:
        regime = "🔴 DEFENSIVE / RISK-OFF"
        badge = "#EF4444"
        headline = (f"Money is hiding — defensives leading, growth sectors lagging. "
                    f"Defensives averaged {defensive_1m:+.1f}% vs growth at {growth_1m:+.1f}%.")
    elif abs(spread) <= 3 and growth_1m > 0 and defensive_1m > 0:
        regime = "🟡 BROAD ADVANCE"
        badge = "#FFD700"
        headline = (f"Most sectors green — broad participation rather than narrow leadership. "
                    f"Growth +{growth_1m:.1f}%, defensives +{defensive_1m:.1f}%.")
    elif growth_1m < 0 and defensive_1m < 0:
        regime = "⚫ BROAD DECLINE"
        badge = "#6B7280"
        headline = (f"Everything bleeding — broad selling pressure. "
                    f"Growth {growth_1m:+.1f}%, defensives {defensive_1m:+.1f}%.")
    else:
        regime = "🟡 MIXED / ROTATIONAL"
        badge = "#FFD700"
        headline = (f"Rotational tape — leadership is choppy. "
                    f"Growth {growth_1m:+.1f}%, defensives {defensive_1m:+.1f}%, cyclicals {cyclical_1m:+.1f}%.")

    # Special signature checks
    flags = []

    # Tech-only narrow leadership
    if growth_1m > 8 and (cyclical_1m < 2 and defensive_1m < 2):
        flags.append(
            f"⚠ **Narrow leadership** — Tech/growth ({growth_1m:+.1f}%) is doing all the work "
            f"while cyclicals ({cyclical_1m:+.1f}%) and defensives ({defensive_1m:+.1f}%) lag. "
            "Narrow markets historically precede corrections; be picky on individual names."
        )

    # Stagflation-ish: energy + defensives leading
    energy_1m = _avg(month_df, {"Energy"})
    if energy_1m > 5 and defensive_1m > 3 and growth_1m < 1:
        flags.append(
            "⚠ **Stagflation signature** — Energy AND defensives both leading while growth lags. "
            "Historically the worst regime for traditional 60/40 portfolios. "
            "Consider commodities + value over growth."
        )

    # Cyclical-led expansion
    if cyclical_1m > 3 and growth_1m > 3 and defensive_1m < 1:
        flags.append(
            "✅ **Cyclical-led expansion** — Cyclicals AND growth leading while defensives lag. "
            "Classic mid-cycle bull pattern. Add to leadership themes (semis, financials, industrials)."
        )

    # REITs/utilities crushed = rates rising
    rate_avg = _avg(month_df, RATE_SENSITIVE)
    if rate_avg < -3:
        flags.append(
            f"📉 **Rate-sensitive sectors getting hit** — REITs + Utilities averaged "
            f"{rate_avg:+.1f}% over the past month. The bond market is pricing in "
            "higher-for-longer rates. Watch the 10Y yield."
        )

    # Build narrative paragraph
    narrative_parts = [
        f"**Today's leader is {t_leader['Sector']}** at {t_leader[today_col]:+.2f}%, "
        f"laggard is **{t_laggard['Sector']}** at {t_laggard[today_col]:+.2f}%. ",
        f"Over the past month, **{m_leader['Sector']}** leads at "
        f"**{m_leader[month_col]:+.1f}%** while **{m_laggard['Sector']}** trails at "
        f"**{m_laggard[month_col]:+.1f}%** — a {abs(m_leader[month_col] - m_laggard[month_col]):.1f}-point spread. "
    ]

    if regime == "🟢 RISK-ON":
        actions = [
            "Bias longs toward growth/cyclical sectors that are leading the 1-month panel.",
            "Leveraged ETFs are eligible — confirm the leverage gate on the Macro Center.",
            "Add to the Stage 2 names from your Discovery scan.",
        ]
    elif regime == "🔴 DEFENSIVE / RISK-OFF":
        actions = [
            "Reduce growth/cyclical exposure. Rotate to defensives if you must stay invested.",
            "No new leveraged longs — gate is likely RED. Hedges (SQQQ, SOXS) usable with discipline.",
            "Tighten stops on existing longs.",
        ]
    elif regime == "🟡 BROAD ADVANCE":
        actions = [
            "Broad participation is healthy — solid environment for long positions.",
            "Pick from leaders in BOTH 1M and 3M timeframes (Sector Rotation page).",
        ]
    elif regime == "⚫ BROAD DECLINE":
        actions = [
            "Capital preservation mode. Avoid new longs.",
            "Wait for a leadership group to emerge before redeploying.",
        ]
    else:
        actions = [
            "Rotational tapes reward selectivity, not aggression.",
            "Look for sectors moving from LAGGING → IMPROVING on the RRG.",
        ]

    return {
        "regime": regime,
        "badge_color": badge,
        "headline": headline,
        "narrative": " ".join(narrative_parts),
        "flags": flags,
        "actions": actions,
        "metrics": {
            "growth_1m": growth_1m,
            "defensive_1m": defensive_1m,
            "cyclical_1m": cyclical_1m,
            "spread": spread,
        },
    }


# ============================================================
# DISCOVERY / SCREEN NARRATIVE
# ============================================================
def screen_story(scan_df: pd.DataFrame, filter_used: str) -> str:
    """Generate a narrative summary of what the scan found."""
    if scan_df.empty:
        return ""

    n_total = len(scan_df)
    n_stage2 = (scan_df["stage"] == "STAGE 2").sum() if "stage" in scan_df.columns else 0
    pct_stage2 = n_stage2 / n_total * 100 if n_total else 0

    parts = []

    # Universe health
    if pct_stage2 > 50:
        parts.append(
            f"**The market is broadly healthy** — {pct_stage2:.0f}% of the universe is in "
            f"Stage 2 (active uptrend). When most stocks are in confirmed uptrends, "
            "you can be aggressive with size and lean into momentum themes."
        )
    elif pct_stage2 > 30:
        parts.append(
            f"**Selective opportunity** — {pct_stage2:.0f}% of stocks in Stage 2. "
            "Not a 'rip everything' regime, but the leaders are real. "
            "Be picky — pick ONLY the highest-composite names from this screen."
        )
    elif pct_stage2 > 15:
        parts.append(
            f"**Narrow market** — only {pct_stage2:.0f}% of stocks in Stage 2. "
            "When breadth is weak, even great-looking names get dragged down with the market. "
            "Tighten stops, reduce size, and consider sitting on cash."
        )
    else:
        parts.append(
            f"**Bear/range market** — just {pct_stage2:.0f}% of stocks in Stage 2. "
            "Capital preservation regime. Most longs will fail in this environment. "
            "Wait for breadth to improve before deploying fresh capital."
        )

    # Top names
    if "composite" in scan_df.columns and scan_df["composite"].notna().any():
        top = scan_df.dropna(subset=["composite"]).head(3)
        if not top.empty:
            top_names = ", ".join([f"**{r['ticker']}** ({r['composite']:+.0f})"
                                    for _, r in top.iterrows()])
            parts.append(f"\n\n**Top 3 by composite:** {top_names}.")

    # Filter-specific commentary
    if "High-conviction" in filter_used:
        parts.append(" These are the names where Stage Analysis AND fundamentals agree — "
                     "the highest-conviction long candidates this screen produces.")

    return " ".join(parts)


# ============================================================
# VIX / DEPLOYMENT NARRATIVE
# ============================================================
def vix_story(current: float, percentile: float, bucket: str,
              deploy_pct: float | None, mean_fwd_ret: float | None,
              horizon_days: int) -> str:
    """Generate plain-English commentary on the current VIX deployment recommendation."""
    parts = []

    # Where are we
    if percentile < 20:
        parts.append(
            f"VIX at **{current:.1f}** sits in the bottom-{percentile:.0f}% of its "
            f"30-year history. Markets are unusually calm — historically a complacent setup. "
            "Forward returns from these levels have been below average."
        )
    elif percentile < 50:
        parts.append(
            f"VIX at **{current:.1f}** is below the long-run median (p{percentile:.0f}). "
            "The environment is constructive — neither panic nor euphoria."
        )
    elif percentile < 75:
        parts.append(
            f"VIX at **{current:.1f}** is above median (p{percentile:.0f}) — "
            "elevated nervousness but not panic. Forward returns from this zone "
            "tend to be average-to-good."
        )
    elif percentile < 90:
        parts.append(
            f"VIX at **{current:.1f}** sits in the top-25% of history (p{percentile:.0f}). "
            "Stress is meaningful. Historically these levels have offered above-average forward "
            "returns to patient buyers."
        )
    else:
        parts.append(
            f"VIX at **{current:.1f}** is in the top-10% of all history (p{percentile:.0f}) — "
            "extreme fear. Mean reversion in VIX has been remarkably reliable, and "
            "historical forward returns from this zone are exceptional. **This is when you deploy capital.**"
        )

    # Deployment recommendation interpretation
    if deploy_pct is not None and mean_fwd_ret is not None:
        parts.append(
            f"\n\nThe data-driven ladder suggests **deploying {deploy_pct:.0f}% of available cash** "
            f"at this VIX level. Historically, SPY's average {horizon_days}-trading-day forward "
            f"return from the **{bucket}** bucket was **{mean_fwd_ret:+.1f}%**."
        )

    return " ".join(parts)


# ============================================================
# MACRO STATE NARRATIVE
# ============================================================
def macro_story(state, vix_state: dict | None = None) -> dict:
    """Generate narrative for the Macro Center based on regime + components."""
    flags = state.components.get("flags", {})
    score = state.components.get("score", 0)
    vix_val = state.components.get("vix")
    curve = state.components.get("10y_2y_spread")
    hy = state.components.get("hy_oas")

    parts = []
    actions = []

    if state.regime == "RISK_ON":
        regime = "🟢 RISK-ON"
        badge = "#22C55E"
        headline = "Macro signals support adding risk. Leverage gate is GREEN."
        parts.append(
            f"All four components are constructive: VIX flag {flags.get('vix', 0):+d}, "
            f"yield curve {flags.get('curve', 0):+d}, credit {flags.get('credit', 0):+d}, "
            f"SPY trend {flags.get('trend', 0):+d}. Composite score {score:+d}."
        )
        actions = [
            "Initiate or add to long positions in Stage 2 names from your Discovery scan.",
            "Leveraged ETFs (TQQQ, SOXL, FNGU) are eligible at full size.",
            "Bias toward growth and cyclical sectors (Sector Rotation page).",
        ]
    elif state.regime == "NEUTRAL":
        regime = "🟡 NEUTRAL — proceed with caution"
        badge = "#FFD700"
        headline = "Macro is mixed. Reduce leverage, prefer quality."
        parts.append(
            f"Score {score:+d} with mixed component signals (VIX {flags.get('vix', 0):+d}, "
            f"curve {flags.get('curve', 0):+d}, credit {flags.get('credit', 0):+d}, "
            f"trend {flags.get('trend', 0):+d}). Don't lean hard either way."
        )
        actions = [
            "Reduce 3× ETF positions to half size or rotate to 1× (QQQ instead of TQQQ).",
            "Stick with high-quality Stage 2 names with composite ≥ +50.",
            "Tighten stops on existing positions in case the YELLOW flips RED.",
        ]
    else:  # RISK_OFF
        regime = "🔴 RISK-OFF — defensive posture"
        badge = "#EF4444"
        headline = "Macro signals are warning. Capital preservation > opportunism."
        parts.append(
            f"Composite score {score:+d}. The combination of "
            + (f"elevated VIX ({vix_val:.1f}), " if vix_val else "")
            + (f"curve at {curve:+.2f}%, " if curve is not None else "")
            + (f"and HY spreads at {hy:.2f}% " if hy else "")
            + "is signalling stress. History says these readings precede drawdowns."
        )
        actions = [
            "Avoid new long positions. Cash is a position.",
            "Exit leveraged ETF longs entirely. Inverse hedges (SQQQ, SOXS) usable with stops.",
            "If holding longs, rotate to defensives (XLP/XLU/XLV) or trim aggressively.",
            "Wait for VIX to peak then mean-revert before re-engaging risk.",
        ]

    # VIX-specific addendum
    if vix_state:
        cur = vix_state.get("current")
        pctile = vix_state.get("percentile")
        if cur is not None and pctile is not None:
            if pctile >= 90:
                parts.append(f"\n\n**VIX is at p{pctile:.0f}** ({cur:.1f}) — top decile of history. "
                             "Historically a buying opportunity for patient capital.")
            elif pctile <= 15:
                parts.append(f"\n\n**VIX is at p{pctile:.0f}** ({cur:.1f}) — bottom-decile complacency. "
                             "Forward returns from these levels have been below average. Don't FOMO.")

    return {
        "regime": regime,
        "badge_color": badge,
        "headline": headline,
        "narrative": " ".join(parts),
        "flags": [],
        "actions": actions,
    }


# ============================================================
# STOCK / VALUATION NARRATIVE
# ============================================================
def valuation_story(verdict: str, current: float, mid: float,
                    upside_pct: float, methods: dict) -> dict:
    """Generate narrative for the Valuation Engine fair-value verdict."""
    parts = []
    actions = []

    if verdict == "UNDERVALUED":
        regime = "🟢 UNDERVALUED"
        badge = "#22C55E"
        headline = (f"At ${current:,.2f} the stock trades **below** the fair-value range "
                    f"(median ${mid:,.2f}, {upside_pct:+.1f}% upside).")
        parts.append(
            f"All {len(methods)} valuation methods average to a price meaningfully above today's level. "
            "If technicals (Stage 2) and macro (RISK-ON) also agree, this is the alignment "
            "position traders look for: cheap stock + healthy chart + supportive environment."
        )
        actions = [
            "Verify Stage 2 + composite ≥ +50 on the Discovery page before initiating.",
            "Use 2.5× ATR stop. Position size by % equity risk, not by share count.",
            "Catalyst check: upcoming earnings? Recent insider buying? News flow?",
        ]
    elif verdict == "OVERVALUED":
        regime = "🔴 OVERVALUED"
        badge = "#EF4444"
        headline = (f"At ${current:,.2f} the stock trades **above** the fair-value range "
                    f"(median ${mid:,.2f}, {upside_pct:+.1f}% to mid).")
        parts.append(
            f"Methods average to a price below today's level. The market is paying a premium "
            "that requires above-average growth to justify. Any disappointment hits hard."
        )
        actions = [
            "Risky as a fresh long. If you hold it, consider trimming or tightening stops.",
            "Short candidate ONLY if technicals also break (Stage 3 → 4 transition).",
            "Wait for a pullback to the upper end of the fair-value range before considering longs.",
        ]
    else:  # FAIR
        regime = "🟡 FAIR VALUE"
        badge = "#FFD700"
        headline = (f"At ${current:,.2f} the stock sits in the fair-value range "
                    f"(median ${mid:,.2f}, {upside_pct:+.1f}% to mid).")
        parts.append(
            "The market is pricing this name correctly given consensus assumptions. "
            "Trades from here need a CATALYST — earnings beat, positive estimate revision, "
            "narrative shift — to justify size."
        )
        actions = [
            "Wait for a catalyst before adding. Stage Engine + earnings calendar are the next checks.",
            "If you hold, no urgency to exit unless thesis changes.",
        ]

    return {
        "regime": regime, "badge_color": badge, "headline": headline,
        "narrative": " ".join(parts), "actions": actions, "flags": [],
    }


# ============================================================
# Helper to render a narrator card
# ============================================================
def render_narrator_card(st_module, headline: str, narrative: str = "",
                          flags: list[str] | None = None,
                          actions: list[str] | None = None,
                          badge_color: str = "#FF8C00", regime: str = "📊 INSIGHT"):
    """Render a 'what this is telling you' card."""
    st_module.markdown(f"""
<div style="background:#11182A;padding:1.2rem;border-left:5px solid {badge_color};border-radius:6px;margin:0.8rem 0">
  <div style="color:#8a93a6;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.1rem">
    What the data is telling you
  </div>
  <div style="font-size:1.5rem;color:{badge_color};font-weight:bold;margin:0.4rem 0">{regime}</div>
  <div style="color:#E6E8EE;font-size:1rem;line-height:1.5;margin-top:0.3rem">{headline}</div>
  <div style="color:#bcc3d6;font-size:0.93rem;line-height:1.5;margin-top:0.6rem">{narrative}</div>
</div>
""", unsafe_allow_html=True)

    if flags:
        for f in flags:
            st_module.markdown(f)
    if actions:
        st_module.markdown("**🎯 What to do with this information:**")
        for a in actions:
            st_module.markdown(f"- {a}")
