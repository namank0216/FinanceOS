"""
Unified data layer — yfinance (default), Finnhub, FMP, FRED, RSS.
All wrapped in try/except with Streamlit caching.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# Load env files. Priority: .env wins, but .env.example is also accepted as
# a fallback (users often paste keys there instead of copying to .env).
try:
    from dotenv import load_dotenv
    base_dir = Path(__file__).parent.parent
    # Load .env.example FIRST so .env can override if both exist
    example_env = base_dir / ".env.example"
    main_env = base_dir / ".env"
    if example_env.exists():
        load_dotenv(example_env)
    if main_env.exists():
        load_dotenv(main_env, override=True)
except Exception:
    pass


def _clean_key(raw: str) -> str:
    """
    Strip whitespace, surrounding quotes, and stray 'api_key=' prefixes that
    sometimes get pasted in by mistake.
    """
    s = (raw or "").strip().strip('"').strip("'")
    # Common mistake: value pasted as "api_key=XYZ" instead of just "XYZ"
    if s.lower().startswith("api_key="):
        s = s.split("=", 1)[1].strip()
    return s


FINNHUB_KEY = _clean_key(os.getenv("FINNHUB_API_KEY", ""))
FMP_KEY = _clean_key(os.getenv("FMP_API_KEY", ""))
FRED_KEY = _clean_key(os.getenv("FRED_API_KEY", ""))

# RSS feeds for ticker-agnostic news
# Categorized RSS feeds — markets, government, international, economic
NEWS_RSS = [
    # ───── 📈 MARKETS ─────
    ("📈 Markets", "Yahoo Finance",   "https://finance.yahoo.com/news/rssindex"),
    ("📈 Markets", "MarketWatch",     "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("📈 Markets", "Seeking Alpha",   "https://seekingalpha.com/market_currents.xml"),
    ("📈 Markets", "CNBC Markets",    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
    ("📈 Markets", "WSJ Markets",     "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("📈 Markets", "Reuters Markets", "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"),
    # ───── 🏛 GOVERNMENT / FED / TREASURY ─────
    ("🏛 Government", "Federal Reserve",   "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("🏛 Government", "US Treasury",       "https://home.treasury.gov/news/press-releases/feed"),
    ("🏛 Government", "SEC Press",         "https://www.sec.gov/news/pressreleases.rss"),
    ("🏛 Government", "WSJ Politics",      "https://feeds.a.dj.com/rss/RSSPolitics.xml"),
    # ───── 🌍 INTERNATIONAL ─────
    ("🌍 International", "Reuters World",  "https://www.reutersagency.com/feed/?best-topics=world&post_type=best"),
    ("🌍 International", "BBC Business",   "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("🌍 International", "AP News Top",    "https://feeds.apnews.com/rss/apf-topnews"),
    ("🌍 International", "FT World",       "https://www.ft.com/world?format=rss"),
    ("🌍 International", "CNBC World",     "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"),
    # ───── 📊 ECONOMIC / DATA ─────
    ("📊 Economic", "Reuters Econ",       "https://www.reutersagency.com/feed/?best-topics=economy&post_type=best"),
    ("📊 Economic", "Trading Economics",  "https://tradingeconomics.com/rss/news.aspx?i=united+states"),
    ("📊 Economic", "BLS Releases",       "https://www.bls.gov/feed/news_release.rss"),
]

# Keywords that flag a story as high-impact for markets
HIGH_IMPACT_KEYWORDS = [
    "fed", "fomc", "powell", "rate cut", "rate hike", "rate decision",
    "tariff", "trade war", "sanction", "tax bill", "shutdown",
    "cpi", "ppi", "inflation", "jobs report", "non-farm", "unemployment",
    "war", "invasion", "ceasefire", "missile", "attack",
    "china", "taiwan", "russia", "israel", "iran", "saudi",
    "ecb", "boe", "boj", "central bank",
    "recession", "gdp", "earnings beat", "guidance",
    "default", "bankruptcy", "downgrade", "fitch", "moody",
    "sec investigation", "antitrust",
]


def has_finnhub() -> bool: return bool(FINNHUB_KEY)
def has_fmp() -> bool:     return bool(FMP_KEY)
def has_fred() -> bool:    return bool(FRED_KEY)


def _safe_get(url: str, params: dict | None = None, timeout: int = 10):
    try:
        r = requests.get(url, params=params, timeout=timeout,
                         headers={"User-Agent": "EquityTerm/1.0"})
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


# ============================================================
# yfinance — primary
# ============================================================
@st.cache_data(ttl=300)
def get_history(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        return df
    except Exception:
        return pd.DataFrame()


def _fi_get(fi, *keys):
    """Try multiple key variants on yfinance FastInfo (camelCase/snake_case)."""
    for k in keys:
        try:
            v = fi[k] if k in fi else None
        except Exception:
            v = None
        if v is None:
            v = getattr(fi, k, None)
        if v is not None:
            return _f(v)
    return None


@st.cache_data(ttl=120)
def get_quote(ticker: str) -> dict:
    out = {}
    try:
        t = yf.Ticker(ticker)
        # 1. Try fast_info — fast but key names vary by yfinance version
        try:
            fi = t.fast_info
            out["last"]       = _fi_get(fi, "last_price", "lastPrice")
            out["prev_close"] = _fi_get(fi, "previous_close", "previousClose", "regular_market_previous_close")
            out["open"]       = _fi_get(fi, "open")
            out["day_high"]   = _fi_get(fi, "day_high", "dayHigh")
            out["day_low"]    = _fi_get(fi, "day_low", "dayLow")
            out["year_high"]  = _fi_get(fi, "year_high", "yearHigh")
            out["year_low"]   = _fi_get(fi, "year_low", "yearLow")
            out["volume"]     = _fi_get(fi, "last_volume", "lastVolume", "regular_market_volume")
            out["market_cap"] = _fi_get(fi, "market_cap", "marketCap")
            out["shares"]     = _fi_get(fi, "shares")
            out["currency"]   = getattr(fi, "currency", "USD")
        except Exception:
            pass

        # 2. Fallback — pull from recent history if fast_info missed the price
        if not out.get("last"):
            try:
                hist = t.history(period="5d", auto_adjust=True)
                if not hist.empty:
                    out["last"]       = _f(hist["Close"].iloc[-1])
                    if len(hist) > 1:
                        out["prev_close"] = _f(hist["Close"].iloc[-2])
                    out["open"]       = _f(hist["Open"].iloc[-1])
                    out["day_high"]   = _f(hist["High"].iloc[-1])
                    out["day_low"]    = _f(hist["Low"].iloc[-1])
                    out["volume"]     = _f(hist["Volume"].iloc[-1])
                    if "year_high" not in out or out["year_high"] is None:
                        h_year = t.history(period="1y", auto_adjust=True)
                        if not h_year.empty:
                            out["year_high"] = _f(h_year["High"].max())
                            out["year_low"]  = _f(h_year["Low"].min())
            except Exception:
                pass

        # 3. Final safety net — pull market cap from .info if still missing
        if not out.get("market_cap"):
            try:
                info = t.info or {}
                out["market_cap"] = _f(info.get("marketCap"))
                if not out.get("shares"):
                    out["shares"] = _f(info.get("sharesOutstanding"))
            except Exception:
                pass

        return out
    except Exception:
        return out


@st.cache_data(ttl=600)
def get_info(ticker: str) -> dict:
    """Slow but rich. Use for deep-dive page only."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        return info
    except Exception:
        return {}


@st.cache_data(ttl=900)
def get_financials(ticker: str) -> dict:
    """Income statement + balance sheet + cashflow (annual + quarterly)."""
    try:
        t = yf.Ticker(ticker)
        return {
            "income":   t.income_stmt,
            "income_q": t.quarterly_income_stmt,
            "balance":  t.balance_sheet,
            "balance_q": t.quarterly_balance_sheet,
            "cashflow": t.cashflow,
            "cashflow_q": t.quarterly_cashflow,
        }
    except Exception:
        return {}


@st.cache_data(ttl=900)
def get_earnings_dates(ticker: str) -> pd.DataFrame:
    try:
        t = yf.Ticker(ticker)
        df = t.earnings_dates
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900)
def get_recommendations(ticker: str) -> pd.DataFrame:
    try:
        t = yf.Ticker(ticker)
        df = t.recommendations_summary
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_holders(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        return {
            "institutional": t.institutional_holders,
            "major": t.major_holders,
        }
    except Exception:
        return {}


# ============================================================
# Bulk price fetch — for screener
# ============================================================
@st.cache_data(ttl=600)
def bulk_history(tickers: list[str], period: str = "1y",
                 interval: str = "1d") -> pd.DataFrame:
    """Returns a DataFrame with multi-index columns (ticker, ohlcv-field)."""
    if not tickers:
        return pd.DataFrame()
    try:
        df = yf.download(
            tickers=" ".join(tickers), period=period, interval=interval,
            auto_adjust=True, group_by="ticker", threads=True, progress=False,
        )
        return df
    except Exception:
        return pd.DataFrame()


# ============================================================
# Finnhub (optional key)
# ============================================================
@st.cache_data(ttl=300)
def fh_news(ticker: str, days: int = 14) -> pd.DataFrame:
    if not FINNHUB_KEY:
        return pd.DataFrame()
    end = datetime.now(timezone.utc).date()
    start = pd.Timestamp(end) - pd.Timedelta(days=days)
    j = _safe_get("https://finnhub.io/api/v1/company-news",
                  {"symbol": ticker, "from": str(start.date()), "to": str(end),
                   "token": FINNHUB_KEY})
    if not j:
        return pd.DataFrame()
    df = pd.DataFrame(j)
    if df.empty:
        return df
    df["datetime"] = pd.to_datetime(df["datetime"], unit="s", utc=True)
    return df.sort_values("datetime", ascending=False)


@st.cache_data(ttl=900)
def fh_earnings_calendar(days_ahead: int = 14) -> pd.DataFrame:
    if not FINNHUB_KEY:
        return pd.DataFrame()
    today = datetime.now().date()
    end = today + pd.Timedelta(days=days_ahead).to_pytimedelta()
    j = _safe_get("https://finnhub.io/api/v1/calendar/earnings",
                  {"from": str(today), "to": str(end), "token": FINNHUB_KEY})
    if not j or "earningsCalendar" not in j:
        return pd.DataFrame()
    return pd.DataFrame(j["earningsCalendar"])


@st.cache_data(ttl=900)
def fh_recommendation(ticker: str) -> pd.DataFrame:
    if not FINNHUB_KEY:
        return pd.DataFrame()
    j = _safe_get("https://finnhub.io/api/v1/stock/recommendation",
                  {"symbol": ticker, "token": FINNHUB_KEY})
    return pd.DataFrame(j) if j else pd.DataFrame()


@st.cache_data(ttl=3600)
def fh_insider(ticker: str) -> pd.DataFrame:
    if not FINNHUB_KEY:
        return pd.DataFrame()
    j = _safe_get("https://finnhub.io/api/v1/stock/insider-transactions",
                  {"symbol": ticker, "token": FINNHUB_KEY})
    if not j or "data" not in j:
        return pd.DataFrame()
    df = pd.DataFrame(j["data"])
    if not df.empty and "transactionDate" in df.columns:
        df["transactionDate"] = pd.to_datetime(df["transactionDate"])
    return df


# ============================================================
# Financial Modeling Prep (optional key)
# ============================================================
@st.cache_data(ttl=3600)
def fmp_ratios(ticker: str) -> dict:
    if not FMP_KEY:
        return {}
    j = _safe_get(f"https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}",
                  {"apikey": FMP_KEY})
    return j[0] if j and isinstance(j, list) and j else {}


@st.cache_data(ttl=3600)
def fmp_key_metrics(ticker: str) -> dict:
    if not FMP_KEY:
        return {}
    j = _safe_get(f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}",
                  {"apikey": FMP_KEY})
    return j[0] if j and isinstance(j, list) and j else {}


@st.cache_data(ttl=3600)
def fmp_dcf(ticker: str) -> dict:
    """FMP's DCF estimate."""
    if not FMP_KEY:
        return {}
    j = _safe_get(f"https://financialmodelingprep.com/api/v3/discounted-cash-flow/{ticker}",
                  {"apikey": FMP_KEY})
    return j[0] if j and isinstance(j, list) and j else {}


@st.cache_data(ttl=3600)
def fmp_analyst_estimates(ticker: str) -> pd.DataFrame:
    if not FMP_KEY:
        return pd.DataFrame()
    j = _safe_get(f"https://financialmodelingprep.com/api/v3/analyst-estimates/{ticker}",
                  {"apikey": FMP_KEY})
    return pd.DataFrame(j) if j else pd.DataFrame()


@st.cache_data(ttl=3600)
def fmp_price_target(ticker: str) -> dict:
    if not FMP_KEY:
        return {}
    j = _safe_get("https://financialmodelingprep.com/api/v4/price-target-consensus",
                  {"symbol": ticker, "apikey": FMP_KEY})
    return j[0] if j and isinstance(j, list) and j else {}


# ============================================================
# FRED — macro (no key required for occasional use)
# ============================================================
FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@st.cache_data(ttl=3600)
def fred_series(series_id: str, days: int = 730) -> pd.DataFrame:
    """Pull a FRED series via the graph CSV endpoint (no key needed)."""
    try:
        url = f"{FRED_BASE}?id={series_id}"
        df = pd.read_csv(url)
        if df.empty:
            return pd.DataFrame()
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna()
        return df.tail(days).reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


# Common FRED series IDs
FRED_IDS = {
    "VIX":            "VIXCLS",
    "10Y Yield":      "DGS10",
    "2Y Yield":       "DGS2",
    "10Y-2Y Spread":  "T10Y2Y",
    "10Y-3M Spread":  "T10Y3M",
    "HY Credit":      "BAMLH0A0HYM2",  # ICE BofA HY OAS
    "IG Credit":      "BAMLC0A0CM",    # ICE BofA IG OAS
    "Fed Funds":      "DFF",
    "Unemployment":   "UNRATE",
    "Core PCE":       "PCEPILFE",
    "Dollar Index":   "DTWEXBGS",
}


# ============================================================
# News (RSS, free, no key)
# ============================================================
@st.cache_data(ttl=600)
def get_market_news(max_per_feed: int = 20) -> pd.DataFrame:
    """Fetch all categorized news with category tag + high-impact flag."""
    rows = []
    for entry in NEWS_RSS:
        # Each entry is (category, source, url)
        if len(entry) == 3:
            category, source, url = entry
        else:
            category, source, url = "📈 Markets", entry[0], entry[1]
        try:
            f = feedparser.parse(url)
            for e in f.entries[:max_per_feed]:
                ts = None
                if hasattr(e, "published_parsed") and e.published_parsed:
                    ts = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                title = getattr(e, "title", "")
                summary = getattr(e, "summary", "")[:500]
                # High-impact flag — flag if any keyword appears in title or summary
                text_lower = (title + " " + summary).lower()
                is_high_impact = any(kw in text_lower for kw in HIGH_IMPACT_KEYWORDS)
                rows.append({
                    "category": category,
                    "source":   source,
                    "title":    title,
                    "summary":  summary,
                    "link":     getattr(e, "link", ""),
                    "ts":       ts,
                    "high_impact": is_high_impact,
                })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).dropna(subset=["ts"])
    return df.sort_values("ts", ascending=False).reset_index(drop=True)


# ----- Helpers -----
def _f(x):
    try:
        return float(x) if x is not None else None
    except Exception:
        return None
