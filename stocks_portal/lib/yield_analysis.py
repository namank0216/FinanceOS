"""
10-Year Treasury yield historical analysis + deployment ladder.

Mirrors lib/vix_analysis.py structure:
  * Pull 60+ years of FRED DGS10 + SPY history
  * Bucket by yield level
  * Compute forward SPY returns per bucket
  * Generate cash-deployment recommendation

Why 10Y matters for equity allocation:
  * 10Y is the discount rate for long-duration assets (growth stocks, REITs)
  * Rising 10Y compresses P/E multiples; falling 10Y expands them
  * 10Y level vs SPY earnings yield signals relative attractiveness (Fed model)
  * Recent 12-month change matters more than absolute level
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import requests
import streamlit as st

# (low, high, label)
YIELD_BUCKETS = [
    (0.0, 1.5, "🟦 Ultra-low (<1.5%)"),
    (1.5, 2.5, "🟩 Low (1.5–2.5%)"),
    (2.5, 3.5, "🟨 Moderate (2.5–3.5%)"),
    (3.5, 4.5, "🟧 Elevated (3.5–4.5%)"),
    (4.5, 6.0, "🟥 High (4.5–6%)"),
    (6.0, 20.0, "⚫ Very high (>6%)"),
]


@st.cache_data(ttl=86400)
def get_10y_spy_history() -> pd.DataFrame:
    """Daily 10Y yield + SPY closes. Aligned, full history (back to ~1990 for SPY)."""
    # 10Y from FRED
    try:
        r = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
            timeout=15,
        )
        ten_df = pd.read_csv(pd.io.common.StringIO(r.text))
        ten_df.columns = ["date", "yield"]
        ten_df["date"] = pd.to_datetime(ten_df["date"], errors="coerce")
        ten_df["yield"] = pd.to_numeric(ten_df["yield"], errors="coerce")
        ten_df = ten_df.dropna()
    except Exception:
        return pd.DataFrame()

    # SPY from yfinance
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY").history(period="max", auto_adjust=True)["Close"]
        if spy.index.tz is not None:
            spy.index = spy.index.tz_localize(None)
        spy_df = pd.DataFrame({"spy": spy})
    except Exception:
        return pd.DataFrame()

    ten_df = ten_df.set_index("date").rename(columns={"yield": "y10"})
    df = ten_df.join(spy_df, how="inner").dropna()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def current_state() -> dict:
    df = get_10y_spy_history()
    if df.empty:
        return {}
    cur = float(df["y10"].iloc[-1])
    series = df["y10"]
    # 12-month change in yield
    chg_12m = None
    if len(df) > 252:
        chg_12m = cur - float(df["y10"].iloc[-252])
    return {
        "current": cur,
        "bucket": _bucket_for(cur),
        "percentile": float((series <= cur).mean() * 100),
        "mean_historical": float(series.mean()),
        "median_historical": float(series.median()),
        "change_12m": chg_12m,
        "history_start": df.index[0],
        "history_end": df.index[-1],
        "n_observations": len(df),
    }


def _bucket_for(y10_value: float) -> str:
    for low, high, label in YIELD_BUCKETS:
        if low <= y10_value < high:
            return label
    return YIELD_BUCKETS[-1][2]


def bucket_analysis(horizon_days: int = 252) -> pd.DataFrame:
    """For each yield bucket, compute SPY forward return over the horizon."""
    df = get_10y_spy_history()
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["fwd_return"] = df["spy"].shift(-horizon_days) / df["spy"] - 1

    bins = [b[0] for b in YIELD_BUCKETS] + [YIELD_BUCKETS[-1][1]]
    labels = [b[2] for b in YIELD_BUCKETS]
    df["bucket"] = pd.cut(df["y10"], bins=bins, labels=labels, right=False)

    valid = df.dropna(subset=["fwd_return", "bucket"])
    if valid.empty:
        return pd.DataFrame()

    grouped = valid.groupby("bucket", observed=True).agg(
        n=("fwd_return", "count"),
        mean_fwd_ret=("fwd_return", "mean"),
        median_fwd_ret=("fwd_return", "median"),
        std_fwd_ret=("fwd_return", "std"),
        win_rate=("fwd_return", lambda x: float((x > 0).mean())),
        p10=("fwd_return", lambda x: float(np.quantile(x, 0.10))),
        p90=("fwd_return", lambda x: float(np.quantile(x, 0.90))),
    ).reset_index()

    for c in ["mean_fwd_ret", "median_fwd_ret", "std_fwd_ret", "p10", "p90"]:
        grouped[c] = grouped[c] * 100
    grouped["win_rate"] = grouped["win_rate"] * 100

    return grouped


def deployment_ladder(horizon_days: int = 252) -> pd.DataFrame:
    """
    Cash deployment % per yield bucket based on historical mean forward SPY return.
    Higher historical forward return → higher recommended deployment.
    """
    analysis = bucket_analysis(horizon_days)
    if analysis.empty:
        return pd.DataFrame()

    min_ret = analysis["mean_fwd_ret"].min()
    max_ret = analysis["mean_fwd_ret"].max()

    if max_ret == min_ret:
        analysis["deploy_pct"] = 50.0
    else:
        analysis["deploy_pct"] = (
            10 + (analysis["mean_fwd_ret"] - min_ret) / (max_ret - min_ret) * 90
        ).round(0)

    range_strs = []
    for label in analysis["bucket"]:
        for low, high, lab in YIELD_BUCKETS:
            if lab == label:
                range_strs.append(f"{low:.1f}–{high:.1f}%")
                break
        else:
            range_strs.append("")
    analysis["yield_range"] = range_strs

    return analysis[["bucket", "yield_range", "n", "mean_fwd_ret",
                     "median_fwd_ret", "win_rate", "p10", "p90", "deploy_pct"]]


def deploy_recommendation_for_current() -> dict:
    state = current_state()
    ladder = deployment_ladder(252)
    if not state or ladder.empty:
        return state
    cur_bucket = state["bucket"]
    row = ladder[ladder["bucket"] == cur_bucket]
    if row.empty:
        return state
    return {**state, **row.iloc[0].to_dict()}


# ============================================================
# Richer historical stats per yield bucket
# ============================================================
def bucket_history() -> pd.DataFrame:
    df = get_10y_spy_history()
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    bins = [b[0] for b in YIELD_BUCKETS] + [YIELD_BUCKETS[-1][1]]
    labels = [b[2] for b in YIELD_BUCKETS]
    df["bucket"] = pd.cut(df["y10"], bins=bins, labels=labels, right=False)
    df = df.dropna(subset=["bucket"])
    total = len(df)

    rows = []
    for label in labels:
        sub = df[df["bucket"] == label].copy()
        if sub.empty:
            rows.append({
                "bucket": label, "n_days": 0, "pct_of_history": 0.0,
                "first_seen": None, "last_seen": None,
                "longest_streak": 0, "n_episodes": 0,
                "recent_5_entries": "—",
            })
            continue

        idx = sub.index
        idx_pos = pd.Series(range(len(df)), index=df.index).loc[idx]
        gap = idx_pos.diff().fillna(1)
        episode = (gap != 1).cumsum()
        eps = sub.assign(episode=episode.values).groupby("episode")
        streaks = eps.size()
        ep_starts = eps.apply(lambda g: g.index[0])

        rows.append({
            "bucket": label,
            "n_days": int(len(sub)),
            "pct_of_history": round(len(sub) / total * 100, 1),
            "first_seen": sub.index[0].strftime("%Y-%m-%d"),
            "last_seen":  sub.index[-1].strftime("%Y-%m-%d"),
            "longest_streak": int(streaks.max()) if not streaks.empty else 0,
            "n_episodes": int(len(streaks)),
            "recent_5_entries": ", ".join(
                ep_starts.sort_values(ascending=False).head(5).dt.strftime("%Y-%m-%d").tolist()
            ),
        })
    return pd.DataFrame(rows)



# ============================================================
# Sector-level forward returns by 10Y yield bucket
# ============================================================
SPDR_SECTORS = {
    "XLK": "Tech",     "XLY": "Discr.",  "XLC": "Comm.",
    "XLF": "Fin.",     "XLV": "Health",  "XLI": "Indu.",
    "XLP": "Staples",  "XLE": "Energy",  "XLU": "Util.",
    "XLB": "Mater.",   "XLRE": "REIT",
}


@st.cache_data(ttl=86400)
def sector_returns_by_bucket(horizon_days: int = 252) -> pd.DataFrame:
    """For each 10Y bucket × sector, mean sector ETF forward return."""
    base = get_10y_spy_history()
    if base.empty:
        return pd.DataFrame()

    bins = [b[0] for b in YIELD_BUCKETS] + [YIELD_BUCKETS[-1][1]]
    labels = [b[2] for b in YIELD_BUCKETS]

    try:
        import yfinance as yf
    except Exception:
        return pd.DataFrame()

    result = {}
    for tk, name in SPDR_SECTORS.items():
        try:
            s = yf.Ticker(tk).history(period="max", auto_adjust=True)["Close"]
            if s.empty:
                continue
            if s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            joined = base[["y10"]].join(s.rename("price"), how="inner").dropna()
            if len(joined) < 252:
                continue
            joined["fwd"] = joined["price"].shift(-horizon_days) / joined["price"] - 1
            joined["bucket"] = pd.cut(joined["y10"], bins=bins, labels=labels, right=False)
            grp = joined.dropna(subset=["fwd", "bucket"]).groupby(
                "bucket", observed=True)["fwd"].mean() * 100
            result[name] = grp
        except Exception:
            continue

    if not result:
        return pd.DataFrame()
    out = pd.DataFrame(result)
    out = out.reindex([l for l in labels if l in out.index])
    return out
