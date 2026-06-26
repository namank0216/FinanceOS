"""
Multi-factor composite scoring for position trading equities.

Five factor pillars (weights are starting points — tunable in optimizer):
  1. TREND      (0..1)  — price vs 30wk MA, MA slope, 52w-high proximity
  2. MOMENTUM   (0..1)  — 12-1 month, RS rating vs SPY, recent vol-adjusted return
  3. QUALITY    (0..1)  — ROIC, FCF margin, debt/equity, gross margin (from FMP if key, else yfinance basics)
  4. VALUE      (0..1)  — P/E vs sector, FCF yield, P/S vs growth, EV/EBITDA
  5. EARNINGS   (0..1)  — surprise streak, revision trend, drift quality

Final composite is a weighted sum on -100..+100. > +50 = strong long, < -50 = strong avoid/short.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ============================================================
# TREND
# ============================================================
def trend_score(price_df: pd.DataFrame) -> tuple[float, dict]:
    if price_df.empty or len(price_df) < 200:
        return 0.0, {}
    last = price_df.iloc[-1]

    components = {}
    # Above rising 30wk MA → +1, below falling → -1
    above_ma = 1 if last["close"] > last["ma30w"] else -1
    rising_ma = 1 if last.get("ma30w_slope", 0) > 0.5 \
        else -1 if last.get("ma30w_slope", 0) < -0.5 else 0
    components["above_30w_ma"] = above_ma
    components["ma_slope"] = rising_ma

    # 52-week high proximity (-15% means at high, -100% means at low)
    pct_high = last.get("pct_from_52w_high", -100)
    proximity = max(-1.0, min(1.0, (pct_high + 30) / 30))  # at -30%: 0, at 0%: 1, at -60%: -1
    components["52w_proximity"] = round(proximity, 2)

    # 50d above 200d?
    ma_stack = 1 if last.get("ma10w", 0) > last.get("ma40w", 0) else -1
    components["ma_stack"] = ma_stack

    raw = (above_ma * 0.30 + rising_ma * 0.30 + proximity * 0.25 + ma_stack * 0.15)
    score = (raw + 1) / 2  # to 0..1
    return float(np.clip(score, 0, 1)), components


# ============================================================
# MOMENTUM
# ============================================================
def momentum_score(price_df: pd.DataFrame, bench_df: pd.DataFrame) -> tuple[float, dict]:
    """12-1 momentum + RS vs benchmark + Sharpe-like vol-adj return."""
    if price_df.empty or len(price_df) < 252:
        return 0.0, {}
    c = price_df["close"]

    # 12-1 momentum: 12-month return excluding most-recent month (Jegadeesh-Titman classic)
    if len(c) >= 252:
        mom_12_1 = c.iloc[-21] / c.iloc[-252] - 1
    else:
        mom_12_1 = 0
    # Recent 6-month
    mom_6 = c.iloc[-1] / c.iloc[-126] - 1 if len(c) >= 126 else 0
    # 3-month
    mom_3 = c.iloc[-1] / c.iloc[-63] - 1 if len(c) >= 63 else 0

    # Vol-adjusted (return / stdev of returns)
    rets = c.pct_change().dropna()
    sharpe_ish = (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0

    # Relative strength vs benchmark (e.g. SPY)
    rs = 0
    if not bench_df.empty and len(bench_df) >= 252:
        b = bench_df["close"]
        stock_ret = c.iloc[-1] / c.iloc[-252] - 1
        bench_ret = b.iloc[-1] / b.iloc[-252] - 1
        rs = stock_ret - bench_ret

    components = {
        "12_1_mom":   round(float(mom_12_1) * 100, 1),
        "6m_mom":     round(float(mom_6) * 100, 1),
        "3m_mom":     round(float(mom_3) * 100, 1),
        "vol_adj":    round(float(sharpe_ish), 2),
        "rs_vs_bench": round(float(rs) * 100, 1),
    }

    # Normalise each into 0..1 with sensible scaling
    n_12 = _sigmoid(mom_12_1, 0.20)      # 20% return = 0.5 contribution centerpoint
    n_6 = _sigmoid(mom_6, 0.10)
    n_3 = _sigmoid(mom_3, 0.05)
    n_vol = _sigmoid(sharpe_ish, 1.0)    # Sharpe of 1
    n_rs = _sigmoid(rs, 0.10)

    score = n_12 * 0.35 + n_6 * 0.20 + n_3 * 0.10 + n_vol * 0.15 + n_rs * 0.20
    return float(np.clip(score, 0, 1)), components


# ============================================================
# QUALITY
# ============================================================
def quality_score(info: dict, fmp_metrics: dict | None = None) -> tuple[float, dict]:
    """Quality from ratios. Higher ROIC, FCF margin, lower debt = better."""
    components = {}
    parts = []

    # Prefer FMP TTM data if available
    src = fmp_metrics or {}
    yf_info = info or {}

    roic = _pick(src, ["roicTTM", "returnOnInvestedCapitalTTM"]) \
        or _pick(yf_info, ["returnOnEquity"])  # fallback to ROE
    if roic is not None:
        components["roic"] = round(roic * 100, 2)
        parts.append((_sigmoid(roic, 0.15), 0.30))

    fcf_yield = _pick(src, ["freeCashFlowYieldTTM", "freeCashFlowPerShareTTM"])
    if fcf_yield is None:
        fcf = yf_info.get("freeCashflow")
        mc = yf_info.get("marketCap")
        if fcf and mc:
            fcf_yield = fcf / mc
    if fcf_yield is not None:
        components["fcf_yield"] = round(fcf_yield * 100, 2) if fcf_yield < 1 else round(fcf_yield, 2)
        parts.append((_sigmoid(fcf_yield, 0.05), 0.25))

    gross_margin = _pick(src, ["grossProfitMarginTTM"]) or yf_info.get("grossMargins")
    if gross_margin is not None:
        components["gross_margin"] = round(gross_margin * 100, 2)
        parts.append((_sigmoid(gross_margin, 0.40), 0.15))

    debt_to_eq = _pick(src, ["debtToEquityTTM"]) or yf_info.get("debtToEquity")
    if debt_to_eq is not None:
        d = debt_to_eq if debt_to_eq < 10 else debt_to_eq / 100  # yfinance returns %, FMP returns ratio
        components["debt_to_equity"] = round(d, 2)
        # Lower is better — invert
        parts.append((1 - _sigmoid(d, 1.0), 0.15))

    op_margin = yf_info.get("operatingMargins")
    if op_margin is not None:
        components["operating_margin"] = round(op_margin * 100, 2)
        parts.append((_sigmoid(op_margin, 0.20), 0.15))

    if not parts:
        return 0.5, components

    total_w = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / total_w
    return float(np.clip(score, 0, 1)), components


# ============================================================
# VALUE
# ============================================================
def value_score(info: dict, fmp_metrics: dict | None = None) -> tuple[float, dict]:
    """
    Value vs growth. Cheap-and-growing → high. Expensive-and-stagnant → low.
    Uses PEG concept: P/E adjusted by growth rate.
    """
    components = {}
    parts = []

    yf_info = info or {}
    src = fmp_metrics or {}

    pe = _pick(src, ["peRatioTTM"]) or yf_info.get("trailingPE")
    fwd_pe = yf_info.get("forwardPE")
    growth = yf_info.get("earningsGrowth") or yf_info.get("revenueGrowth") or 0
    ps = _pick(src, ["priceToSalesRatioTTM"]) or yf_info.get("priceToSalesTrailing12Months")
    pb = yf_info.get("priceToBook")
    ev_ebitda = _pick(src, ["enterpriseValueOverEBITDATTM"]) or yf_info.get("enterpriseToEbitda")

    if pe and pe > 0:
        components["pe"] = round(pe, 1)
        # PEG-style: lower P/E vs growth rate is cheaper
        if growth and growth > 0:
            peg = pe / (growth * 100)
            components["peg"] = round(peg, 2)
            # PEG < 1 = cheap, PEG > 2 = expensive
            parts.append((1 - _sigmoid(peg, 1.5), 0.30))
        else:
            # Without growth, use raw P/E with a wider band
            parts.append((1 - _sigmoid(pe, 25), 0.30))

    if fwd_pe and fwd_pe > 0:
        components["fwd_pe"] = round(fwd_pe, 1)
        # Forward P/E discount to trailing P/E is a positive
        if pe and pe > 0:
            fwd_discount = (pe - fwd_pe) / pe
            components["fwd_pe_discount"] = round(fwd_discount * 100, 1)
            parts.append((_sigmoid(fwd_discount, 0.10), 0.15))

    if ps:
        components["ps"] = round(ps, 1)
        parts.append((1 - _sigmoid(ps, 5), 0.15))

    if pb:
        components["pb"] = round(pb, 1)
        parts.append((1 - _sigmoid(pb, 4), 0.10))

    if ev_ebitda and ev_ebitda > 0:
        components["ev_ebitda"] = round(ev_ebitda, 1)
        parts.append((1 - _sigmoid(ev_ebitda, 15), 0.15))

    div_yield = yf_info.get("dividendYield")
    if div_yield:
        components["div_yield"] = round(div_yield * 100 if div_yield < 1 else div_yield, 2)
        parts.append((_sigmoid(div_yield, 0.03), 0.10))

    if not parts:
        return 0.5, components

    total_w = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / total_w
    return float(np.clip(score, 0, 1)), components


# ============================================================
# EARNINGS
# ============================================================
def earnings_score(earnings_df: pd.DataFrame, info: dict) -> tuple[float, dict]:
    """Recent surprise rate + EPS growth + revision trend (if available)."""
    components = {}
    parts = []

    if earnings_df is not None and not earnings_df.empty:
        # earnings_df from yfinance has 'Surprise(%)' column for past quarters
        surprise_col = next((c for c in earnings_df.columns
                            if "surprise" in c.lower()), None)
        if surprise_col:
            past = earnings_df[earnings_df[surprise_col].notna()].head(8)
            if not past.empty:
                avg_surprise = past[surprise_col].mean()
                beat_rate = (past[surprise_col] > 0).mean()
                components["avg_surprise_pct"] = round(float(avg_surprise), 2)
                components["beat_rate"] = round(float(beat_rate) * 100, 1)
                parts.append((_sigmoid(avg_surprise / 100, 0.05), 0.40))
                parts.append((beat_rate, 0.30))

    eps_growth = info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth")
    if eps_growth is not None:
        components["eps_growth"] = round(eps_growth * 100, 1)
        parts.append((_sigmoid(eps_growth, 0.20), 0.30))

    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        components["rev_growth"] = round(rev_growth * 100, 1)
        parts.append((_sigmoid(rev_growth, 0.15), 0.20))

    if not parts:
        return 0.5, components

    total_w = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / total_w
    return float(np.clip(score, 0, 1)), components


# ============================================================
# COMPOSITE
# ============================================================
def composite_score(trend: float, momentum: float, quality: float,
                    value: float, earnings: float,
                    weights: dict | None = None) -> float:
    """Weighted composite on a -100..+100 scale.
    Default weights: trend=0.25, mom=0.20, quality=0.20, value=0.20, earn=0.15.
    """
    w = weights or {"trend": 0.25, "momentum": 0.20, "quality": 0.20,
                    "value": 0.20, "earnings": 0.15}
    raw = (trend * w["trend"] + momentum * w["momentum"]
           + quality * w["quality"] + value * w["value"]
           + earnings * w["earnings"])  # 0..1
    return float((raw - 0.5) * 200)  # to -100..+100


def label_composite(score: float) -> str:
    if score >= 50:  return "STRONG BUY"
    if score >= 25:  return "BUY"
    if score <= -50: return "AVOID / SHORT"
    if score <= -25: return "REDUCE"
    return "NEUTRAL"


def label_color(score: float) -> str:
    if score >= 50:  return "#22C55E"
    if score >= 25:  return "#16A34A"
    if score <= -50: return "#EF4444"
    if score <= -25: return "#DC2626"
    return "#8a93a6"


# ----- Helpers -----
def _sigmoid(x, midpoint, k: float = 1.0):
    """Logistic squash. Maps x to 0..1 with 0.5 at midpoint."""
    if x is None:
        return 0.5
    try:
        return 1 / (1 + np.exp(-k * (x - midpoint) / max(abs(midpoint) * 0.5, 0.01)))
    except Exception:
        return 0.5


def _pick(d: dict, keys: list[str]):
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except Exception:
                continue
    return None
