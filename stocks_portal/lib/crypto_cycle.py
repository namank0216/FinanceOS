"""
lib/crypto_cycle.py — BTC / ETH cycle engine (evidence computed in-app).

DATA (all free, no API key):
  * History + on-chain: Coin Metrics Community CSV on GitHub
      https://raw.githubusercontent.com/coinmetrics/data/master/csv/{btc,eth}.csv
    Daily since 2010 (BTC) / 2015 (ETH). Columns used: PriceUSD, CapMVRVCur,
    CapRealUSD, SplyCur. Updated daily by Coin Metrics. Cached 6h.
  * Live price: CoinGecko simple/price (free tier, ~30 req/min, no key)
    -> fallback Coinbase public spot -> fallback last Coin Metrics close.

SIGNALS (each one has an evidence() row computed from the same data):
  BUY side
    1. Price below 200-week MA (rolling 1400 calendar days) + depth bands
       0.85x / 0.66x (where prior cycle lows actually printed).
    2. Post-peak clock: days since ATH inside [330, 430] (prior troughs:
       410 / 363 / 364 days after the peaks of 2013, 2017, 2021).
    3. MVRV < 1.0 (capitulation). MVRV = market cap / realized cap.
  SELL side
    A. MVRV > 3.0 (euphoria).
    B. Post-halving peak window: 365-550 days after a halving (BTC only).
  TIME backstop (BTC only): buy ~500 days before a halving, sell ~500 after.
  STRUCTURE: last confirmed pivot high/low (10-bar pivots) + 20-day range.

EVIDENCE PHILOSOPHY
  Nothing in the UI is a remembered statistic. evidence() re-runs the
  backtests every session on the downloaded history, and reports the number
  of *independent episodes* next to every stat, because daily observations
  inside one bear market are not independent samples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import io

import numpy as np
import pandas as pd
import requests
import streamlit as st

CM_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/{asset}.csv"
CG_URL = "https://api.coingecko.com/api/v3/simple/price"
CB_URL = "https://api.coinbase.com/v2/prices/{pair}/spot"

ASSETS = {
    "BTC": {"cm": "btc", "cg": "bitcoin",  "cb": "BTC-USD", "name": "Bitcoin",  "halvings": True},
    "ETH": {"cm": "eth", "cg": "ethereum", "cb": "ETH-USD", "name": "Ethereum", "halvings": False},
    "SOL": {"cm": "sol", "cg": "solana",   "cb": "SOL-USD", "name": "Solana",   "halvings": False},
    "XRP": {"cm": "xrp", "cg": "ripple",   "cb": "XRP-USD", "name": "XRP",      "halvings": False},
    "HYPE": {"cm": "hype", "cg": "hyperliquid", "cb": "HYPE-USD", "name": "Hyperliquid", "halvings": False},
}


def register_asset(symbol: str, cg_id: str, name: str = "", cm_slug: str | None = None) -> str:
    """Add a coin to the registry at runtime (from the search bar). Returns the key."""
    key = symbol.upper()
    ASSETS[key] = {"cm": (cm_slug or symbol.lower()), "cg": cg_id, "cb": f"{key}-USD", "name": name or key, "halvings": False}
    return key


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def search_coins(query: str) -> list[dict]:
    """CoinGecko /search → [{symbol, id, name, rank}] best matches (free, no key)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        j = requests.get("https://api.coingecko.com/api/v3/search", params={"query": q}, timeout=10).json()
        coins = j.get("coins", [])[:8]
        return [{"symbol": c["symbol"].upper(), "id": c["id"], "name": c["name"], "rank": c.get("market_cap_rank")} for c in coins]
    except Exception:
        return []

# Confirmed halvings + projected next (block 1,050,000). Update the projection
# from a block-height countdown as it nears; it drifts by weeks with hashrate.
HALVINGS = [datetime(2012, 11, 28), datetime(2016, 7, 9),
            datetime(2020, 5, 11), datetime(2024, 4, 20)]
NEXT_HALVING_PROJECTED = datetime(2028, 3, 25)

# Cycle peaks used for the post-peak clock evidence (daily-close basis)
CYCLE_PEAKS_BTC = [datetime(2013, 11, 30), datetime(2017, 12, 17),
                   datetime(2021, 11, 10), datetime(2025, 10, 7)]

DEFAULTS = dict(
    wma_days=1400, band1=0.85, band2=0.66,
    win_start=330, win_end=430, proj_days=370,
    mvrv_low=1.0, mvrv_high=2.5,   # 2.5 not 3: peak MVRV fell 5.1→4.3→2.7→2.2 across cycles
    lead_days=500, lag_days=500, date_band=14,
    peak_start=365, peak_end=550, pivot=10,
)


# ============================================================
# Data
# ============================================================
@st.cache_data(ttl=6 * 3600, show_spinner="Loading Coin Metrics history…")
def load_history(asset: str = "BTC") -> pd.DataFrame:
    """Daily history with price, mvrv, realized_price. Empty DF on failure."""
    meta = ASSETS[asset]
    raw = pd.DataFrame()
    try:
        r = requests.get(CM_URL.format(asset=meta["cm"]), timeout=30)
        if r.status_code == 200 and "PriceUSD" in r.text[:5000]:
            raw = pd.read_csv(io.StringIO(r.text), low_memory=False)
    except Exception:
        raw = pd.DataFrame()
    if raw.empty or "PriceUSD" not in raw.columns:
        # CoinGecko full daily history (no on-chain metrics)
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/{meta['cg']}/market_chart",
                             params={"vs_currency": "usd", "days": "max", "interval": "daily"}, timeout=20)
            pts = r.json()["prices"]
            ser = pd.Series({pd.to_datetime(t, unit="ms").normalize(): float(px) for t, px in pts})
            ser = ser[~ser.index.duplicated(keep="last")].sort_index()
            df = pd.DataFrame({"price": ser, "mvrv": np.nan, "realized_price": np.nan})
            return df.asfreq("D").ffill()
        except Exception:
            return pd.DataFrame()

    cols = {"time": "time", "PriceUSD": "price"}
    for c in ("CapMVRVCur", "CapRealUSD", "SplyCur"):
        if c in raw.columns:
            cols[c] = c
    df = raw[list(cols)].rename(columns=cols)
    df["time"] = pd.to_datetime(df["time"])
    df = df.dropna(subset=["price"]).sort_values("time").set_index("time")
    df = df.asfreq("D").ffill()
    df["mvrv"] = df["CapMVRVCur"] if "CapMVRVCur" in df else np.nan
    if "CapRealUSD" in df and "SplyCur" in df:
        df["realized_price"] = df["CapRealUSD"] / df["SplyCur"]
    else:
        df["realized_price"] = np.nan
    return df[["price", "mvrv", "realized_price"]]


@st.cache_data(ttl=3600, show_spinner=False)
def recent_daily(asset: str = "BTC", days: int = 365) -> pd.Series:
    """Recent daily closes from CoinGecko market_chart (free). Used to extend
    the Coin Metrics file, which can lag by days/weeks. Empty on failure."""
    meta = ASSETS[asset]
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/{meta['cg']}/market_chart",
                         params={"vs_currency": "usd", "days": days, "interval": "daily"}, timeout=15)
        pts = r.json()["prices"]
        ser = pd.Series({pd.to_datetime(t, unit="ms").normalize(): float(px) for t, px in pts})
        return ser[~ser.index.duplicated(keep="last")].sort_index()
    except Exception:
        return pd.Series(dtype=float)


def merged_history(asset: str = "BTC") -> tuple[pd.DataFrame, dict]:
    """Coin Metrics history extended to today with CoinGecko closes.
    Returns (df, meta) where meta reports data ages so the UI can show them."""
    df = load_history(asset)
    meta = {"cm_end": None, "price_end": None, "mvrv_end": None}
    if df.empty:
        return df, meta
    meta["cm_end"] = df.index[-1].date()
    meta["mvrv_end"] = df["mvrv"].dropna().index[-1].date() if df["mvrv"].notna().any() else None
    rec = recent_daily(asset)
    if not rec.empty and rec.index[-1] > df.index[-1]:
        add = rec[rec.index > df.index[-1]]
        ext = pd.DataFrame({"price": add, "mvrv": np.nan, "realized_price": np.nan})
        df = pd.concat([df, ext]).asfreq("D").ffill(limit=3)
        df["price"] = df["price"].ffill()
    meta["price_end"] = df.index[-1].date()
    return df, meta


@st.cache_data(ttl=60, show_spinner=False)
def live_price(asset: str = "BTC") -> dict:
    """{'price', 'change_24h', 'source', 'ts'}; never raises."""
    meta = ASSETS[asset]
    try:
        r = requests.get(CG_URL, params={"ids": meta["cg"], "vs_currencies": "usd",
                                          "include_24hr_change": "true"}, timeout=8)
        j = r.json()[meta["cg"]]
        return {"price": float(j["usd"]), "change_24h": float(j.get("usd_24h_change", 0.0)),
                "source": "CoinGecko", "ts": datetime.now(timezone.utc)}
    except Exception:
        pass
    try:
        r = requests.get(CB_URL.format(pair=meta["cb"]), timeout=8)
        return {"price": float(r.json()["data"]["amount"]), "change_24h": np.nan,
                "source": "Coinbase", "ts": datetime.now(timezone.utc)}
    except Exception:
        pass
    df = load_history(asset)
    if not df.empty:
        return {"price": float(df["price"].iloc[-1]), "change_24h": np.nan,
                "source": f"Coin Metrics close {df.index[-1].date()}", "ts": df.index[-1]}
    return {"price": np.nan, "change_24h": np.nan, "source": "unavailable", "ts": None}


# ============================================================
# Signals
# ============================================================
@dataclass
class Signals:
    asset: str
    price: float
    price_source: str
    wma200: float
    ratio: float
    band1_lvl: float
    band2_lvl: float
    below_wma: bool
    ath: float
    ath_date: datetime
    days_since_ath: int
    in_bottom_window: bool
    projected_bottom: datetime
    mvrv: float
    mvrv_state: str            # CAPITULATION / NEUTRAL / EUPHORIA / n/a
    realized_price: float
    support: float
    resistance: float
    hi20: float
    lo20: float
    structure: str             # BULL / BEAR / RANGE
    buy_count: int
    sell_count: int
    # halving layer (BTC)
    last_halving: datetime | None = None
    next_halving: datetime | None = None
    days_since_halving: int | None = None
    days_to_buy_date: int | None = None
    buy_date: datetime | None = None
    sell_date: datetime | None = None
    in_peak_window: bool = False
    in_buy_date: bool = False
    in_sell_date: bool = False
    notes: list = field(default_factory=list)


def _pivots(high: pd.Series, low: pd.Series, n: int):
    """Last CONFIRMED pivot high/low (n bars each side) and its dates."""
    ph = high[(high == high.rolling(2 * n + 1, center=True).max())]
    pl = low[(low == low.rolling(2 * n + 1, center=True).min())]
    # only pivots with n bars after them are confirmed
    cutoff = high.index[-1] - timedelta(days=n)
    ph = ph[ph.index <= cutoff]
    pl = pl[pl.index <= cutoff]
    return ph, pl


def compute_signals(df: pd.DataFrame, asset: str = "BTC", live: dict | None = None,
                    p: dict | None = None) -> Signals | None:
    if df is None or df.empty or len(df) < 120:
        return None
    p = {**DEFAULTS, **(p or {})}
    live = live or {}
    price = float(live.get("price") or df["price"].iloc[-1])
    src = live.get("source", "history")

    s = df["price"]
    wma = s.rolling(p["wma_days"]).mean()
    wma200 = float(wma.iloc[-1]) if len(s) >= p["wma_days"] else np.nan
    ratio = price / wma200 if not np.isnan(wma200) else np.nan

    ath = float(s.max()); ath_date = s.idxmax().to_pydatetime()
    if price > ath:
        ath, ath_date = price, datetime.now(timezone.utc).replace(tzinfo=None)
    days_since_ath = (datetime.now(timezone.utc).replace(tzinfo=None) - ath_date).days
    in_window = p["win_start"] <= days_since_ath <= p["win_end"]

    mvrv_hist = df["mvrv"].dropna()
    mvrv = float(mvrv_hist.iloc[-1]) if not mvrv_hist.empty else np.nan
    rp = float(df["realized_price"].dropna().iloc[-1]) if df["realized_price"].notna().any() else np.nan
    if np.isnan(rp) and not mvrv_hist.empty and mvrv_hist.iloc[-1] > 0:
        # realized price = price / MVRV at the last on-chain observation
        rp = float(s[mvrv_hist.index[-1]] / mvrv_hist.iloc[-1])
    # scale MVRV to today's price (realized price moves slowly; on-chain file lags)
    if not np.isnan(mvrv) and not np.isnan(rp) and rp > 0:
        mvrv = price / rp
    # EUPHORIA label is reserved for the post-halving peak window (evidence: a
    # threshold alone was a bad exit); outside it the same reading is "ELEVATED".
    mvrv_state = ("n/a" if np.isnan(mvrv) else
                  "CAPITULATION" if mvrv < p["mvrv_low"] else
                  "ELEVATED" if mvrv > p["mvrv_high"] else "NEUTRAL")

    # structure on daily closes (Coin Metrics has no OHLC): use close as hi/lo proxy
    n = p["pivot"]
    ph, pl = _pivots(s, s, n)
    last_ph = float(ph.iloc[-1]) if len(ph) else np.nan
    last_pl = float(pl.iloc[-1]) if len(pl) else np.nan
    prev_ph = float(ph.iloc[-2]) if len(ph) > 1 else np.nan
    prev_pl = float(pl.iloc[-2]) if len(pl) > 1 else np.nan
    hi20 = float(s.iloc[-20:].max()); lo20 = float(s.iloc[-20:].min())
    resistance = max(last_ph, hi20) if not np.isnan(last_ph) else hi20
    support = min(last_pl, lo20) if not np.isnan(last_pl) else lo20
    if np.isnan(prev_ph) or np.isnan(prev_pl):
        structure = "RANGE"
    else:
        hh, hl = last_ph > prev_ph, last_pl > prev_pl
        structure = "BULL (HH+HL)" if hh and hl else "BEAR (LH+LL)" if not hh and not hl else "RANGE"

    below = (not np.isnan(wma200)) and price < wma200
    capit = mvrv_state == "CAPITULATION"
    euph = mvrv_state == "ELEVATED"

    sig = Signals(
        asset=asset, price=price, price_source=src, wma200=wma200, ratio=ratio,
        band1_lvl=wma200 * p["band1"], band2_lvl=wma200 * p["band2"], below_wma=below,
        ath=ath, ath_date=ath_date, days_since_ath=days_since_ath, in_bottom_window=in_window,
        projected_bottom=ath_date + timedelta(days=p["proj_days"]),
        mvrv=mvrv, mvrv_state=mvrv_state, realized_price=rp,
        support=support, resistance=resistance, hi20=hi20, lo20=lo20, structure=structure,
        buy_count=int(below) + int(in_window) + int(capit), sell_count=0,
    )

    # Halving clock applies to ETH too: ETH's 2017/2021 peaks landed inside
    # BTC's post-halving window. UI labels it "BTC cycle clock" for ETH.
    if True:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        nh = p.get("next_halving")
        if isinstance(nh, str):
            try:
                nh = datetime.fromisoformat(nh[:10])
            except Exception:
                nh = None
        hs = HALVINGS + [nh if isinstance(nh, datetime) else NEXT_HALVING_PROJECTED]
        past = [h for h in hs if h <= now]; fut = [h for h in hs if h > now]
        sig.last_halving = past[-1] if past else None
        sig.next_halving = fut[0] if fut else None
        if sig.last_halving:
            sig.days_since_halving = (now - sig.last_halving).days
            sig.sell_date = sig.last_halving + timedelta(days=p["lag_days"])
            sig.in_peak_window = p["peak_start"] <= sig.days_since_halving <= p["peak_end"]
            sig.in_sell_date = abs((sig.sell_date - now).days) <= p["date_band"]
        if sig.next_halving:
            sig.buy_date = sig.next_halving - timedelta(days=p["lead_days"])
            sig.days_to_buy_date = (sig.buy_date - now).days
            sig.in_buy_date = abs(sig.days_to_buy_date) <= p["date_band"]
        # Evidence: MVRV>3 alone was a BAD sell signal (67% of days were higher
        # 1y later). The peak window is the primary exit signal (1y fwd median
        # -48%, 19% positive); MVRV>2.5 INSIDE the window sharpens it (-58%).
        sig.sell_count = int(sig.in_peak_window) + int(euph and sig.in_peak_window)
        if euph and sig.in_peak_window:
            sig.mvrv_state = "EUPHORIA"

    if src.startswith("Coin Metrics"):
        sig.notes.append("Live price unavailable — using last daily close.")
    if np.isnan(wma200):
        sig.notes.append(f"Only {len(s)} days of history — 200-week MA needs {p['wma_days']}; signal 1 unavailable.")
    if np.isnan(mvrv):
        sig.notes.append("No on-chain MVRV for this asset (Coin Metrics community feed lacks it) — signal 3 unavailable.")
    return sig


# ============================================================
# Evidence — recomputed from the data every session
# ============================================================
def _fwd_stats(mask: pd.Series, s: pd.Series, hold: int) -> dict:
    fwd = (s.shift(-hold) / s - 1)
    m = pd.concat([mask, fwd], axis=1).dropna()
    m.columns = ["mask", "fwd"]
    sub = m[m["mask"]]
    if sub.empty:
        return {"n_days": 0, "episodes": 0, "pct_positive": np.nan, "median": np.nan}
    # independent episodes = separate runs of the condition being true
    runs = (m["mask"] != m["mask"].shift()).cumsum()
    episodes = int(runs[m["mask"]].nunique())
    return {"n_days": int(len(sub)), "episodes": episodes,
            "pct_positive": float((sub["fwd"] > 0).mean() * 100),
            "median": float(sub["fwd"].median() * 100)}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def evidence(asset: str = "BTC", p: dict | None = None) -> dict:
    """Backtests behind every signal, with episode counts. Keys -> DataFrame/rows."""
    df = load_history(asset)
    p = {**DEFAULTS, **(p or {})}
    if df.empty or len(df) < p["wma_days"] + 400:
        return {}
    s = df["price"]; mvrv = df["mvrv"]
    wma = s.rolling(p["wma_days"]).mean()

    rows = []
    for hold, lbl in ((365, "1y"), (730, "2y")):
        st1 = _fwd_stats(s < wma, s, hold)
        rows.append({"signal": "Price < 200-week MA", "hold": lbl, **st1})
        if mvrv.notna().any():
            st2 = _fwd_stats(mvrv < p["mvrv_low"], s, hold)
            rows.append({"signal": f"MVRV < {p['mvrv_low']}", "hold": lbl, **st2})
            st3 = _fwd_stats(mvrv > p["mvrv_high"], s, hold)
            rows.append({"signal": f"MVRV > {p['mvrv_high']} (sell side)", "hold": lbl, **st3})
        if asset == "BTC" or True:
            dsh = pd.Series(np.nan, index=s.index)
            for H in HALVINGS:
                mk = s.index >= H
                dsh[mk] = (s.index[mk] - H).days
            peakwin = (dsh >= p["peak_start"]) & (dsh <= p["peak_end"])
            rows.append({"signal": f"Post-halving peak window {p['peak_start']}-{p['peak_end']}d (sell side)", "hold": lbl, **_fwd_stats(peakwin, s, hold)})
            if mvrv.notna().any():
                rows.append({"signal": f"MVRV > {p['mvrv_high']} inside peak window (sell side)", "hold": lbl, **_fwd_stats(peakwin & (mvrv > p["mvrv_high"]), s, hold)})
        base = _fwd_stats(pd.Series(True, index=s.index), s, hold)
        rows.append({"signal": "ANY day (baseline)", "hold": lbl, **base})
    sig_tbl = pd.DataFrame(rows)

    # cycle-low position vs 200WMA and MVRV at each historical trough
    troughs = []
    if asset == "BTC":
        for i, pk in enumerate(CYCLE_PEAKS_BTC):
            end = CYCLE_PEAKS_BTC[i + 1] if i + 1 < len(CYCLE_PEAKS_BTC) else s.index[-1]
            seg = s[pk:end]
            if seg.empty:
                continue
            tr = seg.idxmin()
            troughs.append({
                "peak": pk.date(), "trough": tr.date(),
                "days_peak_to_trough": (tr - pk).days,
                "drawdown_%": round((seg.min() / s[pk] - 1) * 100, 1),
                "trough_price/200WMA": round(float(s[tr] / wma[tr]), 2) if not np.isnan(wma[tr]) else np.nan,
                "trough_MVRV": round(float(mvrv[tr]), 2) if not np.isnan(mvrv[tr]) else np.nan,
                "MVRV_at_peak": round(float(mvrv[pk]), 2) if not np.isnan(mvrv[pk]) else np.nan,
                "complete": bool(i + 1 < len(CYCLE_PEAKS_BTC)),
            })
    troughs_tbl = pd.DataFrame(troughs)

    # halving 500/500 rule vs all 1000-day windows (era-controlled)
    halv_rows = []
    if asset == "BTC":
        n = p["lead_days"] + p["lag_days"]
        all_r = (s.shift(-n) / s - 1).dropna()
        for h in HALVINGS:
            b = h - timedelta(days=p["lead_days"]); e = h + timedelta(days=p["lag_days"])
            if b in s.index and e in s.index:
                r = s[e] / s[b] - 1
                local = all_r[(all_r.index >= b - timedelta(days=365)) & (all_r.index <= b + timedelta(days=365))]
                halv_rows.append({"halving": h.date(), "buy": b.date(), "sell": e.date(),
                                  "return_%": round(r * 100), "local_median_%": round(local.median() * 100) if len(local) else np.nan,
                                  "percentile_vs_nearby_windows": round(float((local < r).mean() * 100)) if len(local) else np.nan})
        halv_rows.append({"halving": "ALL 1000d windows", "buy": "", "sell": "",
                          "return_%": round(all_r.median() * 100), "local_median_%": np.nan,
                          "percentile_vs_nearby_windows": round(float((all_r > 0).mean() * 100))})
    halv_tbl = pd.DataFrame(halv_rows)
    for c in ("halving", "buy", "sell"):
        if c in halv_tbl.columns:
            halv_tbl[c] = halv_tbl[c].astype(str)

    return {"signals": sig_tbl, "troughs": troughs_tbl, "halving": halv_tbl,
            "data_start": s.index[0].date(), "data_end": s.index[-1].date(), "n_days": int(len(s))}


# ============================================================
# Plan / verdict
# ============================================================
def verdict(sig: Signals, plan: dict) -> list[str]:
    """Turn signals + the user's written rules into plain-language actions."""
    out = []
    px = sig.price
    if plan.get("mode") == "cash":
        trg = plan.get("rebuy_close")
        if trg:
            out.append(f"REBUY RULE: daily close > {trg:,.0f} → buy next day (price is {px/trg-1:+.1%} vs trigger).")
        for i, rung in enumerate(plan.get("ladder", []), 1):
            out.append(f"LADDER {i}: buy at {rung:,.0f} ({px/rung-1:+.1%} above)." if px > rung else f"LADDER {i}: {rung:,.0f} — REACHED")
        if sig.buy_date:
            out.append(f"BACKSTOP: halving buy date {sig.buy_date.date()} ({sig.days_to_buy_date}d) — buy regardless if no rule fired.")
    else:
        if plan.get("stop"):
            out.append(f"STOP: {plan['stop']:,.0f} ({px/plan['stop']-1:+.1%} cushion).")
        out.append("EXIT MARKERS: MVRV > 3 or post-halving peak window → begin scale-out.")
    if not np.isnan(sig.wma200):
        out.append(f"200WMA {sig.wma200:,.0f} · band 0.85x {sig.band1_lvl:,.0f} · band 0.66x {sig.band2_lvl:,.0f}")
    else:
        out.append("200WMA unavailable (short history) — rely on clock + structure.")
    out.append(f"Structure: {sig.structure} · S {sig.support:,.0f} / R {sig.resistance:,.0f}")
    return out


def context_for_ai(sig: Signals, ev: dict, plan: dict) -> str:
    """Compact, numbers-first context for the AI briefing card."""
    lines = [f"{sig.asset} {sig.price:,.4g} ({sig.price_source}). " + (f"200WMA {sig.wma200:,.4g} → ratio {sig.ratio:.2f}x (below={sig.below_wma})." if not np.isnan(sig.wma200) else "200WMA n/a (short history)."),
             f"ATH {sig.ath:,.0f} on {sig.ath_date.date()}, {sig.days_since_ath}d ago; bottom window {DEFAULTS['win_start']}-{DEFAULTS['win_end']}d → in_window={sig.in_bottom_window}; projected trough date {sig.projected_bottom.date()}.",
             (f"MVRV {sig.mvrv:.2f} ({sig.mvrv_state}); realized price {sig.realized_price:,.4g}." if not np.isnan(sig.mvrv) else "MVRV n/a for this asset."),
             f"Structure {sig.structure}; support {sig.support:,.4g}, resistance {sig.resistance:,.4g}, 20d range {sig.lo20:,.4g}-{sig.hi20:,.4g}.",
             f"Buy signals {sig.buy_count}/3, sell signals {sig.sell_count}/2."]
    if sig.buy_date:
        lines.append(f"Halving: last {sig.last_halving.date()} ({sig.days_since_halving}d ago), next ~{sig.next_halving.date()}; 500d buy date {sig.buy_date.date()} in {sig.days_to_buy_date}d; peak window={sig.in_peak_window}.")
    if ev.get("signals") is not None and not ev["signals"].empty:
        t = ev["signals"]
        lines.append("Evidence (computed from data): " + "; ".join(
            f"{r.signal} {r.hold}: {r.pct_positive:.0f}% positive, median {r.median:+.0f}%, {r.episodes} episodes"
            for r in t.itertuples() if r.hold == "1y"))
    lines.append("User plan: " + "; ".join(verdict(sig, plan)))
    return "\n".join(lines)
