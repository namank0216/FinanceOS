"""
VIX historical analysis + cash-deployment ladder.

Pulls 30+ years of daily VIX + SPY closes from yfinance, computes forward
SPY returns at each VIX level, and produces a data-backed deployment
heuristic: how much of your cash should be deployed at the current VIX
level, given history.

Disclaimer baked into the page that uses this:
  This is a HEURISTIC derived from past data. Future returns are not
  guaranteed to follow the same distribution. Use as one input, not as a
  signal generator on its own.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# (low, high, label) — closed on left, open on right
VIX_BUCKETS = [
    (0,   12, "🟦 Extreme calm"),
    (12,  15, "🟩 Calm"),
    (15,  20, "🟨 Normal"),
    (20,  25, "🟧 Elevated"),
    (25,  30, "🟥 Fear"),
    (30,  40, "🔴 Panic"),
    (40, 100, "⚫ Capitulation"),
]


def _try_yf(ticker: str, periods: list[str]) -> pd.Series:
    """Try a ticker with multiple period strings, return Close series or empty."""
    for p in periods:
        try:
            df = yf.Ticker(ticker).history(period=p, auto_adjust=True)
            if not df.empty and "Close" in df.columns:
                s = df["Close"].dropna()
                if s.index.tz is not None:
                    s.index = s.index.tz_localize(None)
                return s
        except Exception:
            continue
    return pd.Series(dtype=float)


def _vix_from_fred() -> pd.Series:
    """Pull VIX history from FRED (no API key needed) — works back to 1990."""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
        df = pd.read_csv(url)
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna()
        return pd.Series(df["value"].values, index=df["date"], name="vix")
    except Exception:
        return pd.Series(dtype=float)


def _spy_proxy_from_yf() -> pd.Series:
    """Last-resort SPY history — try multiple proxies."""
    for ticker, periods in [
        ("SPY",   ["max", "30y", "20y", "10y"]),
        ("^GSPC", ["max", "30y", "20y", "10y"]),
        ("VOO",   ["max", "20y", "10y"]),
    ]:
        s = _try_yf(ticker, periods)
        if not s.empty:
            return s.rename("spy")
    return pd.Series(dtype=float)


@st.cache_data(ttl=86400)  # 24h
def get_vix_spy_history() -> pd.DataFrame:
    """
    Daily VIX + SPY closes — full available history. Robust to yfinance flakiness.

    Source priority:
      VIX: yfinance ^VIX (max → 30y → 20y → 10y) → FRED VIXCLS
      SPY: yfinance SPY (max → 30y → 20y → 10y) → ^GSPC → VOO
    """
    # ---- VIX ----
    vix = _try_yf("^VIX", ["max", "30y", "20y", "10y"])
    if vix.empty:
        vix = _vix_from_fred()
    if vix.empty:
        return pd.DataFrame()
    vix = vix.rename("vix")

    # ---- SPY ----
    spy = _spy_proxy_from_yf()
    if spy.empty:
        return pd.DataFrame()

    # ---- Align ----
    # Both should be tz-naive at this point; ensure same timezone handling
    if vix.index.tz is not None:
        vix.index = vix.index.tz_localize(None)
    if spy.index.tz is not None:
        spy.index = spy.index.tz_localize(None)

    df = pd.concat([vix, spy], axis=1)
    df = df.dropna(how="any")
    return df


def _bucket_for(vix_value: float) -> str:
    for low, high, label in VIX_BUCKETS:
        if low <= vix_value < high:
            return label
    return VIX_BUCKETS[-1][2]


def current_state() -> dict:
    df = get_vix_spy_history()
    if df.empty:
        return {}
    cur = float(df["vix"].iloc[-1])
    series = df["vix"]
    return {
        "current":         cur,
        "bucket":          _bucket_for(cur),
        "percentile":      float((series <= cur).mean() * 100),
        "mean_historical": float(series.mean()),
        "median_historical": float(series.median()),
        "history_start":   df.index[0],
        "history_end":     df.index[-1],
        "n_observations":  len(df),
    }


def bucket_analysis(horizon_days: int = 252) -> pd.DataFrame:
    """
    For each VIX bucket, compute the historical SPY forward return over the
    given horizon. 252 trading days ≈ 1 year.
    """
    df = get_vix_spy_history()
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["fwd_return"] = df["spy"].shift(-horizon_days) / df["spy"] - 1
    df["max_drawdown"] = (
        df["spy"].rolling(horizon_days).apply(
            lambda w: ((w / w.cummax()) - 1).min() if len(w) > 1 else 0,
            raw=False,
        ).shift(-horizon_days)
    )

    bins = [b[0] for b in VIX_BUCKETS] + [VIX_BUCKETS[-1][1]]
    labels = [b[2] for b in VIX_BUCKETS]
    df["bucket"] = pd.cut(df["vix"], bins=bins, labels=labels, right=False)

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

    grouped["mean_fwd_ret"] = grouped["mean_fwd_ret"] * 100
    grouped["median_fwd_ret"] = grouped["median_fwd_ret"] * 100
    grouped["std_fwd_ret"] = grouped["std_fwd_ret"] * 100
    grouped["win_rate"] = grouped["win_rate"] * 100
    grouped["p10"] = grouped["p10"] * 100
    grouped["p90"] = grouped["p90"] * 100

    return grouped


def deployment_ladder(horizon_days: int = 252) -> pd.DataFrame:
    """
    Map each VIX bucket to a cash-deployment percentage based on its
    historical mean forward SPY return. Higher expected return → deploy more.

    Logic:
      * Sort buckets by mean forward return.
      * Lowest-return bucket → 10% deployment (still some exposure)
      * Highest-return bucket → 100% (full deployment)
      * Linear interpolation between.
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

    # Add a "VIX range" string column for display
    range_strs = []
    for label in analysis["bucket"]:
        for low, high, lab in VIX_BUCKETS:
            if lab == label:
                range_strs.append(f"{low}–{high}")
                break
        else:
            range_strs.append("")
    analysis["VIX range"] = range_strs

    return analysis[["bucket", "VIX range", "n", "mean_fwd_ret", "median_fwd_ret",
                     "win_rate", "p10", "p90", "deploy_pct"]]


def deploy_recommendation_for_current_vix(horizon_days: int = 252) -> dict:
    """Return the deployment recommendation for the current VIX reading."""
    state = current_state()
    ladder = deployment_ladder(horizon_days)
    if not state or ladder.empty:
        return {}
    cur_bucket = state["bucket"]
    row = ladder[ladder["bucket"] == cur_bucket]
    if row.empty:
        return state
    row_dict = row.iloc[0].to_dict()
    return {**state, **row_dict}


def vix_distribution_data() -> pd.DataFrame:
    """Return the raw VIX series for histograms."""
    df = get_vix_spy_history()
    return df[["vix"]] if not df.empty else pd.DataFrame()


# ============================================================
# Richer historical stats per bucket
# ============================================================
def bucket_history(horizon_days: int = 252) -> pd.DataFrame:
    """
    For each VIX bucket: total days observed, last occurrence date,
    most recent occurrences, longest consecutive streak, % of history.
    Returned as a DataFrame keyed by bucket label.
    """
    df = get_vix_spy_history()
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    bins = [b[0] for b in VIX_BUCKETS] + [VIX_BUCKETS[-1][1]]
    labels = [b[2] for b in VIX_BUCKETS]
    df["bucket"] = pd.cut(df["vix"], bins=bins, labels=labels, right=False)
    df = df.dropna(subset=["bucket"])
    total = len(df)

    rows = []
    for label in labels:
        sub = df[df["bucket"] == label].copy()
        if sub.empty:
            rows.append({
                "bucket": label, "n_days": 0, "pct_of_history": 0.0,
                "last_seen": None, "first_seen": None,
                "longest_streak": 0, "n_episodes": 0,
                "recent_5_entries": "—",
            })
            continue

        # Streak detection — group consecutive days in this bucket
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
# Sector-level forward returns by VIX bucket
# ============================================================
SPDR_SECTORS = {
    "XLK": "Tech",     "XLY": "Discr.",  "XLC": "Comm.",
    "XLF": "Fin.",     "XLV": "Health",  "XLI": "Indu.",
    "XLP": "Staples",  "XLE": "Energy",  "XLU": "Util.",
    "XLB": "Mater.",   "XLRE": "REIT",
}


@st.cache_data(ttl=86400)
def sector_returns_by_bucket(horizon_days: int = 252) -> pd.DataFrame:
    """
    For each VIX bucket × sector, compute mean sector ETF forward return.
    Returns wide DataFrame: rows = bucket, cols = sector name, vals = mean fwd %.
    Note: SPDR sector ETFs began ~1998 (XLRE 2015, XLC 2018) so smaller buckets
    will have fewer observations.
    """
    vix_spy = get_vix_spy_history()
    if vix_spy.empty:
        return pd.DataFrame()

    bins = [b[0] for b in VIX_BUCKETS] + [VIX_BUCKETS[-1][1]]
    labels = [b[2] for b in VIX_BUCKETS]

    result = {}
    for tk, name in SPDR_SECTORS.items():
        try:
            s = yf.Ticker(tk).history(period="max", auto_adjust=True)["Close"]
            if s.empty:
                continue
            if s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            joined = vix_spy[["vix"]].join(s.rename("price"), how="inner").dropna()
            if len(joined) < 252:
                continue
            joined["fwd"] = joined["price"].shift(-horizon_days) / joined["price"] - 1
            joined["bucket"] = pd.cut(joined["vix"], bins=bins, labels=labels, right=False)
            grp = joined.dropna(subset=["fwd", "bucket"]).groupby(
                "bucket", observed=True)["fwd"].mean() * 100
            result[name] = grp
        except Exception:
            continue

    if not result:
        return pd.DataFrame()

    out = pd.DataFrame(result)
    # Reorder rows by VIX bucket order, drop empty buckets
    out = out.reindex([l for l in labels if l in out.index])
    return out
