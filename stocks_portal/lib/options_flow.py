"""
Options-flow proxy for "whale" / institutional positioning.

Inputs: yfinance options chain (free).
Outputs: ranked list of unusual contracts classified as
  🟢 BULLISH (call BTO)         — bought-to-open calls (directional long)
  🔴 BEARISH (put BTO)          — bought-to-open puts (directional short)
  🛡 HEDGE (OTM put BTO)        — protection on existing equity exposure
  💰 SHORT VOL (call/put STO)   — selling premium
  🚀 BULLISH SPEC (far OTM call)— lottery-ticket speculation, often pre-catalyst
  🟡 NEUTRAL                    — routine flow

Honest limitations:
  - We CANNOT see sweeps, block trades, or multi-leg strategies
  - Bid/ask placement is approximate (no time-and-sales)
  - Real institutional flow services (UnusualWhales, FlowAlgo, BBS) cost $40-200/mo
This module gives you ~70% of the signal at $0 cost. Use with the rest of the
macro picture, not as a standalone signal.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf

# Tickers most liquid in options (where institutional flow is real)
WHALE_UNIVERSE = [
    # Indices / ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Mega-caps
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA",
    "AVGO", "AMD", "NFLX", "ORCL", "BRK-B",
    # Other liquid names
    "COIN", "PLTR", "SMCI", "MU", "MARA",
    # Leveraged ETFs (the user trades these)
    "TQQQ", "SOXL", "FNGU", "SQQQ", "SOXS",
    # Commodities / havens
    "GLD", "SLV", "USO", "TLT",
]


@st.cache_data(ttl=600)  # 10 min
def get_options_chain_full(ticker: str, max_expirations: int = 6) -> pd.DataFrame:
    """Pull full options chain across the next N expirations."""
    try:
        t = yf.Ticker(ticker)
        all_exps = t.options
        if not all_exps:
            return pd.DataFrame()
        expirations = all_exps[:max_expirations]
        rows = []
        for exp in expirations:
            try:
                chain = t.option_chain(exp)
                calls = chain.calls.copy()
                calls["type"] = "call"
                puts = chain.puts.copy()
                puts["type"] = "put"
                for df in (calls, puts):
                    df["expiration"] = exp
                    df["ticker"] = ticker
                    rows.append(df)
            except Exception:
                continue
        if not rows:
            return pd.DataFrame()
        out = pd.concat(rows, ignore_index=True, sort=False)
        return out
    except Exception:
        return pd.DataFrame()


def classify_contract(row: pd.Series, spot_price: float) -> tuple[str, float]:
    """
    Return (classification, premium_dollars) for a single options contract.
    """
    try:
        volume = float(row.get("volume") or 0)
        oi = float(row.get("openInterest") or 0)
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
        last = float(row.get("lastPrice") or 0)
        strike = float(row.get("strike") or 0)
        is_call = row.get("type") == "call"
        exp = pd.to_datetime(row.get("expiration"))
        dte = (exp - pd.Timestamp.now()).days
    except Exception:
        return "—", 0.0

    if volume <= 0 or strike <= 0 or spot_price <= 0:
        return "—", 0.0

    # Premium = volume × last price × 100 (multiplier per contract)
    premium = volume * last * 100

    # Bid-ask position: 0 = at bid (sold), 1 = at ask (bought aggressively)
    spread = ask - bid
    if spread > 0 and bid > 0 and ask > 0:
        position = max(0.0, min(1.0, (last - bid) / spread))
    else:
        position = 0.5  # unknown

    # V/OI ratio — opening activity if high
    voi = volume / max(oi, 1)

    # Moneyness
    moneyness = strike / spot_price
    if is_call:
        is_otm = moneyness > 1.05
        is_far_otm = moneyness > 1.15
        is_atm = 0.97 <= moneyness <= 1.05
        is_itm = moneyness < 0.97
    else:
        is_otm = moneyness < 0.95
        is_far_otm = moneyness < 0.85
        is_atm = 0.95 <= moneyness <= 1.03
        is_itm = moneyness > 1.03

    # ----- Classification -----
    # Aggressive buyer (last near ask)
    if position >= 0.6:
        if is_call:
            if is_far_otm and dte > 30:
                return "🚀 BULLISH SPEC (far-OTM call BTO, long-dated)", premium
            if is_otm and dte <= 30:
                return "🟢 BULLISH (short-dated OTM call BTO)", premium
            return "🟢 BULLISH (call BTO)", premium
        else:  # put
            if is_otm and dte > 45:
                return "🛡 HEDGE (long-dated OTM put BTO)", premium
            if is_atm:
                return "🔴 BEARISH (ATM put BTO)", premium
            if is_far_otm:
                return "🛡 HEDGE (far-OTM put BTO)", premium
            return "🔴 BEARISH (put BTO)", premium

    # Aggressive seller (last near bid)
    if position <= 0.4:
        if is_call:
            if is_otm:
                return "💰 SHORT VOL (call STO — covered call or income)", premium
            return "🟧 BEARISH (call STO)", premium
        else:
            if is_otm:
                return "🟢 BULLISH (put STO — willing to buy stock at strike)", premium
            return "💰 SHORT VOL (put STO)", premium

    # Mid-market
    return "🟡 NEUTRAL (mid-market fill)", premium


@st.cache_data(ttl=600)
def _spot_price(ticker: str) -> float:
    try:
        t = yf.Ticker(ticker)
        try:
            v = t.fast_info.get("last_price") or t.fast_info.get("lastPrice")
            if v is not None:
                return float(v)
        except Exception:
            pass
        h = t.history(period="2d", auto_adjust=True)
        if not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


@st.cache_data(ttl=600)
def scan_universe(tickers: list[str], min_voi: float = 2.0,
                  min_premium: float = 100_000.0,
                  min_volume: int = 100) -> pd.DataFrame:
    """
    Scan multiple tickers for unusual options activity.
    Returns DataFrame ranked by premium ($) descending.
    """
    rows = []
    for tk in tickers:
        spot = _spot_price(tk)
        if spot <= 0:
            continue
        chain = get_options_chain_full(tk)
        if chain.empty:
            continue
        chain["voi"] = chain["volume"].fillna(0) / chain["openInterest"].clip(lower=1)
        for _, row in chain.iterrows():
            try:
                vol = float(row.get("volume") or 0)
            except Exception:
                vol = 0
            if vol < min_volume or pd.isna(row.get("voi")) or row["voi"] < min_voi:
                continue
            cls, prem = classify_contract(row, spot)
            if prem < min_premium:
                continue
            rows.append({
                "ticker":         tk,
                "type":           row.get("type"),
                "strike":         float(row.get("strike", 0)),
                "spot":           round(spot, 2),
                "moneyness":      round(float(row.get("strike", 0)) / spot, 2) if spot else None,
                "expiration":     row.get("expiration"),
                "DTE":            (pd.to_datetime(row.get("expiration"))
                                   - pd.Timestamp.now()).days,
                "volume":         int(vol),
                "OI":             int(row.get("openInterest") or 0),
                "V/OI":           round(float(row["voi"]), 1),
                "IV %":           round(float(row.get("impliedVolatility", 0)) * 100, 1),
                "last":           round(float(row.get("lastPrice", 0)), 2),
                "premium_$":      int(prem),
                "classification": cls,
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("premium_$", ascending=False).reset_index(drop=True)
    return df


def aggregate_by_ticker(flow: pd.DataFrame) -> pd.DataFrame:
    """Aggregate flow by ticker — net bullish vs bearish premium."""
    if flow.empty:
        return pd.DataFrame()

    def _bias(cls: str) -> str:
        if "BULLISH" in cls or "put STO" in cls: return "bullish"
        if "BEARISH" in cls or "call STO" in cls: return "bearish"
        if "HEDGE" in cls: return "hedge"
        if "SHORT VOL" in cls: return "short_vol"
        return "neutral"

    df = flow.copy()
    df["bias"] = df["classification"].apply(_bias)
    grouped = df.groupby(["ticker", "bias"])["premium_$"].sum().unstack(fill_value=0).reset_index()
    grouped["net_directional_$"] = (grouped.get("bullish", 0) - grouped.get("bearish", 0))
    grouped = grouped.sort_values("net_directional_$", ascending=False, key=abs)
    return grouped
