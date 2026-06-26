"""
Universe screener — runs Stage + Trend + Momentum across the universe and ranks.

Cached aggressively because it's slow (yfinance bulk pull + per-ticker info).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import data, factors, stages


@st.cache_data(ttl=1800)
def screen_universe(tickers: list[str], bench: str = "SPY") -> pd.DataFrame:
    """
    For each ticker:
      * pull 2y price history
      * compute stage classification + factor scores (price-based ones)
    Returns a DataFrame of one row per ticker, sorted by composite descending.
    Quality + Value + Earnings scores require fundamentals so are NOT included
    in this fast screen — they're filled in on the Stock Deep Dive page.
    """
    if not tickers:
        return pd.DataFrame()

    bench_df = data.get_history(bench, period="2y")
    rows = []

    for tk in tickers:
        try:
            df = data.get_history(tk, period="2y")
            if df.empty or len(df) < 200:
                continue
            df = stages.classify(df)
            last = df.iloc[-1]

            tr_score, tr_comp = factors.trend_score(df)
            mo_score, mo_comp = factors.momentum_score(df, bench_df)

            rows.append({
                "ticker": tk,
                "price": float(last["close"]),
                "pct_from_52w_high": round(float(last["pct_from_52w_high"]), 1),
                "stage": str(last["stage"]),
                "ma30w_slope": round(float(last["ma30w_slope"]), 2),
                "atr_pct": round(float(last["atr_pct"]), 2),
                "vol_ratio": round(float(last["vol_ratio"]), 2),
                "trend_score":     round(tr_score, 3),
                "momentum_score":  round(mo_score, 3),
                "fast_composite":  round((tr_score + mo_score) / 2, 3),
                "12_1_mom":        mo_comp.get("12_1_mom"),
                "rs_vs_bench":     mo_comp.get("rs_vs_bench"),
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("fast_composite", ascending=False).reset_index(drop=True)


def filter_stage(df: pd.DataFrame, stage: str = "STAGE 2") -> pd.DataFrame:
    return df[df["stage"] == stage].reset_index(drop=True) if not df.empty else df
