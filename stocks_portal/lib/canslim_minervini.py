"""
CAN SLIM (O'Neil) + Minervini Trend Template — combined growth screener.

Two systems, both built by guys who turned <$100K into eight figures.
Both demand the SAME thing: a high-quality stock in a strong uptrend
during a confirmed market uptrend.

═══════════════════════════════════════════════════════════════════════
MINERVINI TREND TEMPLATE — 8 price/MA criteria (binary)
═══════════════════════════════════════════════════════════════════════
  T1. Price > 150d SMA AND > 200d SMA
  T2. 150d SMA > 200d SMA
  T3. 200d SMA trending up (≥ 1 month)
  T4. 50d SMA > 150d SMA AND > 200d SMA
  T5. Price > 50d SMA
  T6. Price ≥ 30% above 52-week low
  T7. Price within 25% of 52-week high
  T8. Relative Strength rank ≥ 70

═══════════════════════════════════════════════════════════════════════
CAN SLIM — fundamentals + macro overlay
═══════════════════════════════════════════════════════════════════════
  C. Current quarter EPS growth ≥ 25% YoY
  A. Annual EPS growth ≥ 25% (last full year vs prior)
  N. New high (within 25% of 52w high — captured by T7)
  S. Supply/Demand — volume confirmation (50d vol > avg)
  L. Leader — RS ≥ 80 (stricter than Minervini's 70)
  I. Institutional sponsorship ≥ 30%
  M. Market direction — confirmed uptrend (macro gate, external)

═══════════════════════════════════════════════════════════════════════
SCORING
═══════════════════════════════════════════════════════════════════════
  Trend score:    0-8  (Minervini)
  Fundamental:    0-4  (C, A, L, I)
  Market gate:    Pass/Fail (M)
  TOTAL:          0-12 + market gate

  Verdict tiers:
    🟢 STRONG BUY  →  Trend 8/8 + Fund ≥3/4 + Market green
    🟢 BUY         →  Trend ≥7/8 + Fund ≥2/4 + Market green
    🟡 WATCH       →  Trend ≥6/8 (basing or near-pass)
    🔴 AVOID       →  Trend <6/8 (no setup)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ============================================================
# 1) Universe-level RS rank (IBD-style)
# ============================================================
@st.cache_data(ttl=3600)  # 1 hour
def compute_rs_ranks(tickers: list[str], lookback_days: int = 252) -> pd.DataFrame:
    """
    IBD-style Relative Strength Rank (1-99).
    Formula: weighted blend of 3m/6m/9m/12m returns, percentile-ranked.
    Weighting: 0.4 * Q1 + 0.2 * (Q2 + Q3 + Q4)
    """
    try:
        df = yf.download(
            " ".join(tickers), period="1y", interval="1d",
            auto_adjust=True, progress=False, threads=True,
            group_by="ticker",
        )
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    rows = []
    for tk in tickers:
        try:
            # Handle both single-ticker (DataFrame) and multi-ticker (multiindex)
            if len(tickers) == 1:
                close = df["Close"] if "Close" in df.columns else None
            else:
                if tk not in df.columns.get_level_values(0):
                    continue
                close = df[tk]["Close"]
            close = close.dropna()
            if len(close) < 200:
                continue
            now = float(close.iloc[-1])
            # 3m=63d, 6m=126d, 9m=189d, 12m=252d  (trading days)
            q1 = (now / float(close.iloc[-63]))  - 1.0 if len(close) > 63  else np.nan
            q2 = (now / float(close.iloc[-126])) - 1.0 if len(close) > 126 else np.nan
            q3 = (now / float(close.iloc[-189])) - 1.0 if len(close) > 189 else np.nan
            q4 = (now / float(close.iloc[-min(len(close)-1, 252)])) - 1.0
            score = 0.4 * q1 + 0.2 * (q2 + q3 + q4)
            rows.append({"ticker": tk, "rs_raw": score})
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).dropna()
    if out.empty:
        return out
    # Percentile rank 1-99
    out["rs_rank"] = out["rs_raw"].rank(pct=True) * 98 + 1
    out["rs_rank"] = out["rs_rank"].round().astype(int)
    return out[["ticker", "rs_rank", "rs_raw"]]


# ============================================================
# 2) Per-ticker price-action analysis (Minervini)
# ============================================================
@st.cache_data(ttl=3600)
def minervini_check(ticker: str) -> dict:
    """Run 8 Minervini Trend Template checks on a single ticker."""
    try:
        h = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=True)
    except Exception:
        return {"ok": False, "ticker": ticker}

    if h is None or h.empty or len(h) < 200:
        return {"ok": False, "ticker": ticker}

    close = h["Close"]
    vol = h["Volume"]
    price = float(close.iloc[-1])

    sma50  = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()

    sma50_now  = float(sma50.iloc[-1])
    sma150_now = float(sma150.iloc[-1])
    sma200_now = float(sma200.iloc[-1])
    sma200_1mo = float(sma200.iloc[-21])  # 1 month ago

    wk52_high = float(close.max())
    wk52_low  = float(close.min())

    # 8 Trend Template checks
    t1 = price > sma150_now and price > sma200_now
    t2 = sma150_now > sma200_now
    t3 = sma200_now > sma200_1mo
    t4 = sma50_now > sma150_now and sma50_now > sma200_now
    t5 = price > sma50_now
    t6 = price >= wk52_low * 1.30        # 30% above 52w low
    t7 = price >= wk52_high * 0.75       # within 25% of 52w high
    # t8 (RS) is set externally from compute_rs_ranks

    # Volume signature (CAN SLIM "S")
    vol50_avg = float(vol.tail(50).mean())
    vol50_recent = float(vol.tail(10).mean())
    vol_expanding = vol50_recent > vol50_avg

    trend_score = sum([t1, t2, t3, t4, t5, t6, t7])  # /7 (t8 added later)

    return {
        "ok": True,
        "ticker": ticker,
        "price": round(price, 2),
        "sma50": round(sma50_now, 2),
        "sma150": round(sma150_now, 2),
        "sma200": round(sma200_now, 2),
        "wk52_high": round(wk52_high, 2),
        "wk52_low": round(wk52_low, 2),
        "pct_from_high": round((price / wk52_high - 1) * 100, 1),
        "pct_from_low":  round((price / wk52_low - 1) * 100, 1),
        "T1_above_150_200": bool(t1),
        "T2_150_above_200": bool(t2),
        "T3_200_uptrend": bool(t3),
        "T4_50_above_150_200": bool(t4),
        "T5_above_50": bool(t5),
        "T6_30pct_above_low": bool(t6),
        "T7_within_25pct_high": bool(t7),
        "trend_score_pre_rs": int(trend_score),
        "vol_expanding": bool(vol_expanding),
    }


# ============================================================
# 3) Per-ticker fundamentals (CAN SLIM C, A, I)
# ============================================================
@st.cache_data(ttl=86400)  # 1 day
def fundamentals_check(ticker: str) -> dict:
    """
    Pull EPS growth + institutional ownership from yfinance.
    Returns:
      eps_q_growth   — current quarter YoY EPS growth (%)
      eps_a_growth   — annual EPS growth (%)
      inst_own_pct   — institutional ownership (%)
      C, A, I        — bool flags
    """
    out = {
        "ticker": ticker,
        "eps_q_growth": None,
        "eps_a_growth": None,
        "inst_own_pct": None,
        "C_quarterly_25": False,
        "A_annual_25":    False,
        "I_inst_30":      False,
    }
    try:
        t = yf.Ticker(ticker)

        # Quarterly EPS via quarterly_income_stmt → "Diluted EPS" or "Basic EPS"
        try:
            qi = t.quarterly_income_stmt
            row_keys = [k for k in ("Diluted EPS", "Basic EPS", "Net Income")
                        if qi is not None and k in qi.index]
            if row_keys and len(qi.columns) >= 5:
                key = row_keys[0]
                series = qi.loc[key].dropna()
                if len(series) >= 5:
                    # Current quarter vs same quarter prior year (idx 0 vs idx 4)
                    curr = float(series.iloc[0])
                    prior = float(series.iloc[4])
                    if prior != 0:
                        growth = (curr - prior) / abs(prior) * 100
                        out["eps_q_growth"] = round(growth, 1)
                        out["C_quarterly_25"] = growth >= 25
        except Exception:
            pass

        # Annual EPS — same logic on income_stmt
        try:
            ai = t.income_stmt
            row_keys = [k for k in ("Diluted EPS", "Basic EPS", "Net Income")
                        if ai is not None and k in ai.index]
            if row_keys and len(ai.columns) >= 2:
                key = row_keys[0]
                series = ai.loc[key].dropna()
                if len(series) >= 2:
                    curr = float(series.iloc[0])
                    prior = float(series.iloc[1])
                    if prior != 0:
                        growth = (curr - prior) / abs(prior) * 100
                        out["eps_a_growth"] = round(growth, 1)
                        out["A_annual_25"] = growth >= 25
        except Exception:
            pass

        # Institutional ownership
        try:
            info = t.info
            inst = info.get("heldPercentInstitutions")
            if inst is not None:
                inst_pct = float(inst) * 100
                out["inst_own_pct"] = round(inst_pct, 1)
                out["I_inst_30"] = inst_pct >= 30
        except Exception:
            pass

    except Exception:
        pass

    return out


# ============================================================
# 4) Market direction check (CAN SLIM "M")
# ============================================================
@st.cache_data(ttl=600)  # 10 min
def market_direction_ok() -> tuple[bool, str]:
    """
    Confirmed uptrend criteria (O'Neil):
      - SPY price > 50d SMA AND > 200d SMA
      - 50d SMA > 200d SMA
    Returns (ok, description)
    """
    try:
        h = yf.Ticker("SPY").history(period="1y", interval="1d", auto_adjust=True)
        if h is None or h.empty:
            return False, "SPY data unavailable"
        close = h["Close"]
        price = float(close.iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        cond1 = price > sma50 and price > sma200
        cond2 = sma50 > sma200
        if cond1 and cond2:
            return True, (f"SPY {price:.2f} > 50d {sma50:.2f} > 200d {sma200:.2f} — "
                          f"confirmed uptrend. CAN SLIM 'M' = ✅")
        return False, (f"SPY {price:.2f} / 50d {sma50:.2f} / 200d {sma200:.2f} — "
                       f"market not in confirmed uptrend. CAN SLIM 'M' = ❌")
    except Exception as e:
        return False, f"Market check failed: {e}"


# ============================================================
# 5) Combined scanner
# ============================================================
def scan(tickers: list[str], max_tickers: int = 100,
         require_market: bool = True) -> pd.DataFrame:
    """
    Full pipeline: RS ranks → Minervini → CAN SLIM fundamentals → score.

    Returns DataFrame ranked by combined_score descending.
    """
    # 1) Trim universe (yfinance gets flaky beyond ~150 tickers per call)
    tickers = list(dict.fromkeys(tickers))[:max_tickers]
    if not tickers:
        return pd.DataFrame()

    # 2) RS ranks across the whole batch
    rs_df = compute_rs_ranks(tickers)
    rs_map = dict(zip(rs_df["ticker"], rs_df["rs_rank"])) if not rs_df.empty else {}

    # 3) Per-ticker Minervini + fundamentals
    market_ok, _ = market_direction_ok()

    rows = []
    progress = st.progress(0.0, text="Scanning…")
    for i, tk in enumerate(tickers, start=1):
        progress.progress(i / len(tickers), text=f"Scanning {tk} ({i}/{len(tickers)})")

        m = minervini_check(tk)
        if not m.get("ok"):
            continue
        rs = rs_map.get(tk, 0)
        f = fundamentals_check(tk)

        t8 = rs >= 70  # Minervini's 8th criterion
        L = rs >= 80   # CAN SLIM "L" (Leader)

        trend_score = m["trend_score_pre_rs"] + int(t8)  # /8
        fund_score = (int(f["C_quarterly_25"]) + int(f["A_annual_25"]) +
                      int(L) + int(f["I_inst_30"]))  # /4
        combined = trend_score + fund_score  # /12

        # Verdict
        if trend_score == 8 and fund_score >= 3 and market_ok:
            verdict = "🟢 STRONG BUY"
        elif trend_score >= 7 and fund_score >= 2 and market_ok:
            verdict = "🟢 BUY"
        elif trend_score >= 6:
            verdict = "🟡 WATCH"
        else:
            verdict = "🔴 AVOID"

        # If market is down, override BUY → WATCH (CAN SLIM M-rule)
        if require_market and not market_ok and "BUY" in verdict:
            verdict = "🟡 WATCH (market down — wait for follow-through)"

        rows.append({
            "Ticker":          tk,
            "Verdict":         verdict,
            "Trend /8":        trend_score,
            "Fund /4":         fund_score,
            "Total /12":       combined,
            "RS Rank":         int(rs),
            "Price":           m["price"],
            "% from 52w high": m["pct_from_high"],
            "% above 52w low": m["pct_from_low"],
            "Quarterly EPS %": f["eps_q_growth"],
            "Annual EPS %":    f["eps_a_growth"],
            "Inst Own %":      f["inst_own_pct"],
            "T1": m["T1_above_150_200"], "T2": m["T2_150_above_200"],
            "T3": m["T3_200_uptrend"],   "T4": m["T4_50_above_150_200"],
            "T5": m["T5_above_50"],      "T6": m["T6_30pct_above_low"],
            "T7": m["T7_within_25pct_high"],  "T8 (RS≥70)": t8,
            "C (Q EPS≥25%)":  f["C_quarterly_25"],
            "A (Yr EPS≥25%)": f["A_annual_25"],
            "L (RS≥80)":      L,
            "I (Inst≥30%)":   f["I_inst_30"],
            "Vol expanding":  m["vol_expanding"],
        })
    progress.empty()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values(
        ["Total /12", "RS Rank"], ascending=[False, False]
    ).reset_index(drop=True)
    return df


def summarize_for_ai(df: pd.DataFrame, market_msg: str) -> str:
    """Build a context string for the AI briefing."""
    if df is None or df.empty:
        return f"{market_msg}\n\nNo candidates returned by the scan."
    n_total = len(df)
    n_strong = int((df["Verdict"].str.contains("STRONG BUY")).sum())
    n_buy = int((df["Verdict"].str.contains("BUY") & ~df["Verdict"].str.contains("STRONG")).sum())
    n_watch = int((df["Verdict"].str.contains("WATCH")).sum())

    top5 = df.head(5)
    top_lines = "\n".join(
        f"- {r['Ticker']}: {r['Verdict']} (Trend {int(r['Trend /8'])}/8, "
        f"Fund {int(r['Fund /4'])}/4, RS {int(r['RS Rank'])}, "
        f"{r['% from 52w high']:+.1f}% from 52w high, "
        f"EPS Q {r['Quarterly EPS %']}%, EPS Yr {r['Annual EPS %']}%)"
        for _, r in top5.iterrows()
    )
    return (
        f"CAN SLIM + Minervini scan results.\n"
        f"{market_msg}\n\n"
        f"Universe scanned: {n_total} tickers.\n"
        f"🟢 STRONG BUY: {n_strong} | 🟢 BUY: {n_buy} | 🟡 WATCH: {n_watch}\n\n"
        f"Top 5 candidates by combined score:\n{top_lines}"
    )
