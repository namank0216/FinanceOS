"""
Universe: S&P 500 + Nasdaq 100 + leveraged-ETF watchlist + sector ETFs.
Pulled live from Wikipedia at first run, cached to JSON locally.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

CACHE = Path(__file__).parent.parent / ".cache" / "universe.json"

# 11 SPDR sector ETFs
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLY": "Consumer Discretionary",
    "XLC": "Communication Services",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
}

# Major broad-market ETFs
INDEX_ETFS = ["SPY", "QQQ", "IWM", "DIA", "MDY"]

# Leveraged ETFs the user trades + companions, with their underlyings
# (underlying is what we run signals on; the lev ETF is the execution vehicle)
LEVERAGED_ETFS = {
    # 3x long
    "TQQQ": {"name": "ProShares UltraPro QQQ",        "leverage": 3,  "underlying": "QQQ",  "sector": "Tech"},
    "FNGU": {"name": "MicroSectors FANG+ 3X",         "leverage": 3,  "underlying": "QQQ",  "sector": "Mega Tech"},
    "SOXL": {"name": "Direxion Semi 3X Bull",         "leverage": 3,  "underlying": "SOXX", "sector": "Semiconductors"},
    "UPRO": {"name": "ProShares UltraPro S&P 500",    "leverage": 3,  "underlying": "SPY",  "sector": "Broad"},
    "SPXL": {"name": "Direxion S&P 500 3X Bull",      "leverage": 3,  "underlying": "SPY",  "sector": "Broad"},
    "TECL": {"name": "Direxion Tech 3X Bull",         "leverage": 3,  "underlying": "XLK",  "sector": "Tech"},
    "TNA":  {"name": "Direxion Small Cap 3X Bull",    "leverage": 3,  "underlying": "IWM",  "sector": "Small Cap"},
    "LABU": {"name": "Direxion Biotech 3X Bull",      "leverage": 3,  "underlying": "XBI",  "sector": "Biotech"},
    "WEBL": {"name": "Direxion Internet 3X Bull",     "leverage": 3,  "underlying": "FDN",  "sector": "Internet"},
    "DPST": {"name": "Direxion Regional Banks 3X",    "leverage": 3,  "underlying": "KRE",  "sector": "Regional Banks"},
    # 3x inverse (for hedging / regime-off plays)
    "SQQQ": {"name": "ProShares UltraPro Short QQQ",  "leverage": -3, "underlying": "QQQ",  "sector": "Tech (Inverse)"},
    "SOXS": {"name": "Direxion Semi 3X Bear",         "leverage": -3, "underlying": "SOXX", "sector": "Semis (Inverse)"},
    "FNGD": {"name": "MicroSectors FANG+ -3X",        "leverage": -3, "underlying": "QQQ",  "sector": "Mega Tech (Inverse)"},
    "SPXS": {"name": "Direxion S&P 500 3X Bear",      "leverage": -3, "underlying": "SPY",  "sector": "Broad (Inverse)"},
    "SPXU": {"name": "ProShares UltraPro Short S&P",  "leverage": -3, "underlying": "SPY",  "sector": "Broad (Inverse)"},
}


# Hardcoded fallback for the most-liquid 100 names if Wikipedia is down
FALLBACK_TICKERS = [
    "AAPL","MSFT","NVDA","GOOGL","GOOG","AMZN","META","TSLA","AVGO","BRK-B",
    "LLY","JPM","V","UNH","XOM","MA","JNJ","PG","HD","COST",
    "ABBV","WMT","MRK","NFLX","BAC","ADBE","CRM","KO","PEP","TMO",
    "AMD","ORCL","ACN","CSCO","LIN","DIS","WFC","ABT","MCD","CVX",
    "DHR","INTC","CMCSA","IBM","TXN","VZ","NKE","INTU","QCOM","NEE",
    "PM","NOW","CAT","RTX","UNP","UPS","BMY","LOW","COP","HON",
    "AMGN","SPGI","GS","ELV","BA","SBUX","T","BLK","DE","AMAT",
    "PFE","SCHW","MDT","LMT","C","BKNG","GILD","ADP","PLD","TJX",
    "MDLZ","SYK","REGN","ETN","MU","ISRG","VRTX","PANW","ZTS","CB",
    "ADI","KLAC","SNPS","CDNS","BSX","FI","SO","DUK","EQIX","CI",
    # Common Nasdaq 100 mega-caps already mostly above; add a few not in S&P
    "MELI","PDD","ASML","AZN","ARM","MAR","ABNB","CRWD","CTAS","ADSK",
]


def _from_wikipedia_sp500() -> tuple[list[str], dict[str, str]] | tuple[None, None]:
    """Returns (tickers list, ticker→name dict)."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        for t in tables:
            if "Symbol" in t.columns:
                # Find the company-name column
                name_col = None
                for c in t.columns:
                    sc = str(c)
                    if "Security" in sc or "Company" in sc:
                        name_col = c
                        break
                syms_raw = t["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
                syms = [s.strip() for s in syms_raw if s and len(s) <= 6]
                names_dict = {}
                if name_col:
                    names_raw = t[name_col].astype(str).tolist()
                    for s, n in zip(syms_raw, names_raw):
                        s = s.strip()
                        if s and len(s) <= 6:
                            names_dict[s] = str(n).strip()
                return syms, names_dict
    except Exception:
        pass
    return None, None


def _from_wikipedia_nasdaq100() -> tuple[list[str], dict[str, str]] | tuple[None, None]:
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(url)
        for t in tables:
            cols = [str(c) for c in t.columns]
            ticker_col = next((c for c in t.columns if str(c) in ("Ticker", "Symbol")), None)
            if not ticker_col:
                continue
            name_col = next((c for c in t.columns
                             if "Compan" in str(c) or "Security" in str(c)), None)
            syms_raw = t[ticker_col].astype(str).str.replace(".", "-", regex=False).tolist()
            syms = [s.strip() for s in syms_raw if s and len(s) <= 6 and s.replace("-", "").isalpha()]
            if not (90 <= len(syms) <= 110):
                continue
            names_dict = {}
            if name_col:
                names_raw = t[name_col].astype(str).tolist()
                for s, n in zip(syms_raw, names_raw):
                    s = s.strip()
                    if s and len(s) <= 6:
                        names_dict[s] = str(n).strip()
            return syms, names_dict
    except Exception:
        pass
    return None, None


@st.cache_data(ttl=86400)  # 24h
def get_sp500() -> list[str]:
    if CACHE.exists():
        try:
            d = json.loads(CACHE.read_text())
            if d.get("sp500") and d.get("sp500_names"):
                return d["sp500"]
        except Exception:
            pass
    syms, names = _from_wikipedia_sp500()
    if not syms:
        return FALLBACK_TICKERS
    _save_cache({"sp500": syms, "sp500_names": names or {}})
    return syms


@st.cache_data(ttl=86400)
def get_nasdaq100() -> list[str]:
    if CACHE.exists():
        try:
            d = json.loads(CACHE.read_text())
            if d.get("nasdaq100") and d.get("nasdaq100_names"):
                return d["nasdaq100"]
        except Exception:
            pass
    syms, names = _from_wikipedia_nasdaq100()
    if not syms:
        return FALLBACK_TICKERS[:100]
    _save_cache({"nasdaq100": syms, "nasdaq100_names": names or {}})
    return syms


@st.cache_data(ttl=86400)
def get_full_universe() -> list[str]:
    sp = set(get_sp500())
    nq = set(get_nasdaq100())
    return sorted(sp | nq)


@st.cache_data(ttl=86400)
def get_name_lookup() -> dict[str, str]:
    """Combined ticker → company-name dictionary (S&P 500 + Nasdaq 100)."""
    get_sp500(); get_nasdaq100()  # ensure cache populated
    if CACHE.exists():
        try:
            d = json.loads(CACHE.read_text())
            sp_names = d.get("sp500_names", {}) or {}
            nq_names = d.get("nasdaq100_names", {}) or {}
            return {**sp_names, **nq_names}
        except Exception:
            pass
    return {}


def resolve_ticker(query: str) -> tuple[str | None, list[tuple[str, str]]]:
    """
    Accept either a ticker or a company name. Returns (best_ticker, candidates).
    candidates is a list of (ticker, name) tuples for ambiguous matches.

    Strategy:
      1. Exact ticker match in S&P 500 / Nasdaq 100 → that ticker.
      2. Substring match on company name → all matches, best first.
      3. Looks like a ticker (1-6 alpha chars) outside our universe → trust it,
         yfinance accepts many tickers we don't track (ETFs, ADRs, etc.)
      4. Otherwise → None.
    """
    if not query or not query.strip():
        return None, []
    q = query.strip()
    q_upper = q.upper()
    q_lower = q.lower()
    lookup = get_name_lookup()

    # 1. Exact ticker hit
    if q_upper in lookup:
        return q_upper, [(q_upper, lookup.get(q_upper, ""))]

    # 2. Company-name substring search
    candidates = [(tk, name) for tk, name in lookup.items()
                  if q_lower in name.lower()]
    # Prefer prefix matches; tie-break by shorter name (more specific)
    candidates.sort(key=lambda x: (not x[1].lower().startswith(q_lower), len(x[1])))
    if candidates:
        return candidates[0][0], candidates[:10]

    # 3. Looks like a ticker outside our universe (ETFs, ADRs, etc.)
    cleaned = q_upper.replace("-", "").replace(".", "")
    if 1 <= len(q_upper) <= 6 and cleaned.isalpha():
        return q_upper, [(q_upper, "")]

    return None, []


def _save_cache(updates: dict):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if CACHE.exists():
        try:
            existing = json.loads(CACHE.read_text())
        except Exception:
            existing = {}
    existing.update(updates)
    CACHE.write_text(json.dumps(existing, indent=2))


def is_leveraged(ticker: str) -> bool:
    return ticker.upper() in LEVERAGED_ETFS


def underlying_of(ticker: str) -> str:
    """For a leveraged ETF, return its underlying ticker. Else return self."""
    info = LEVERAGED_ETFS.get(ticker.upper())
    return info["underlying"] if info else ticker
