"""
Smart Money — Dataroma superinvestors + Congressional trades + insider activity.

Data sources (all free, no API key):
  * Dataroma.com  — quarterly 13F-derived superinvestor portfolios
                    (Buffett, Pabrai, Greenblatt, Klarman, Burry, Ackman, etc.)
  * House Stock Watcher — Congressional STOCK Act disclosures (Pelosi, Crenshaw, etc.)
  * Finnhub (with key) — corporate insider Form 4 transactions

Dataroma uses static HTML pages — pandas.read_html parses them cleanly.
House Stock Watcher publishes a public JSON dataset.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from io import StringIO

DATAROMA = "https://dataroma.com"
HSW_API = "https://housestockwatcher.com/api/transactions"

# Curated list of high-signal superinvestors on Dataroma
SUPERINVESTORS = {
    "BRK":  "Berkshire Hathaway (Buffett)",
    "MOH":  "Mohnish Pabrai",
    "GFP":  "Joel Greenblatt (Gotham)",
    "BAU":  "Seth Klarman (Baupost)",
    "SAM":  "Michael Burry (Scion)",
    "PSC":  "Bill Ackman (Pershing Square)",
    "DAA":  "David Abrams",
    "DT":   "David Tepper (Appaloosa)",
    "VA":   "Howard Marks (Oaktree)",
    "TWE":  "Terry Smith (Fundsmith)",
    "DM":   "Daniel Loeb (Third Point)",
    "GS":   "Glenn Greenberg (Brave Warrior)",
    "L":    "Lee Ainslie (Maverick)",
    "RTC":  "Bill Miller (Miller Value)",
    "PB":   "Prem Watsa (Fairfax)",
    "WSC":  "Walter Schloss",
    "STC":  "Stanley Druckenmiller (Duquesne)",
    "JG":   "John Griffin (Blue Ridge)",
}


# ============================================================
# DATAROMA
# ============================================================
def _clean_dataroma_df(df: pd.DataFrame) -> pd.DataFrame:
    """Clean &nbsp; and other HTML artifacts that pd.read_html leaves behind."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    # Decode HTML entities that pandas missed
    for c in out.columns:
        if out[c].dtype == "object":
            out[c] = (out[c].astype(str)
                      .str.replace("\xa0", " ", regex=False)
                      .str.replace("&nbsp;", " ", regex=False)
                      .str.replace("&amp;", "&", regex=False)
                      .str.strip())
    # Drop rows that are entirely whitespace / "nan" / "None"
    out = out.replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
    out = out.dropna(how="all")
    # Drop columns that are entirely empty
    out = out.dropna(axis=1, how="all")
    # Drop columns that are clearly junk (column name contains "Unnamed")
    junk_cols = [c for c in out.columns if "Unnamed" in str(c)]
    out = out.drop(columns=junk_cols, errors="ignore")
    return out.reset_index(drop=True)


@st.cache_data(ttl=43200)  # 12 hours
def get_holdings(manager_code: str) -> pd.DataFrame:
    """Pull a superinvestor's current holdings from Dataroma."""
    url = f"{DATAROMA}/m/holdings.php?m={manager_code}"
    try:
        r = requests.get(url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 EquityTerm/1.0"})
        if r.status_code != 200:
            return pd.DataFrame()
        tables = pd.read_html(StringIO(r.text))
        if not tables:
            return pd.DataFrame()
        # The holdings table is usually the largest with a 'Stock' column
        best = None
        best_len = 0
        for t in tables:
            cols = [str(c) for c in t.columns]
            if any("Stock" in c or "Ticker" in c for c in cols) and len(t) > best_len:
                best = t
                best_len = len(t)
        if best is None:
            best = max(tables, key=lambda t: len(t))
        return _clean_dataroma_df(best)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=43200)
def get_recent_activity(manager_code: str) -> pd.DataFrame:
    """
    Pull recent buys/sells for a superinvestor — using the holdings table's
    RecentActivity column, which is cleaner than scraping the activity page.
    """
    holdings = get_holdings(manager_code)
    if holdings.empty:
        return pd.DataFrame()
    # Find the activity column
    activity_col = None
    stock_col = None
    for c in holdings.columns:
        cs = str(c)
        if "Activity" in cs or "Recent" in cs:
            activity_col = c
        elif "Stock" in cs or "Ticker" in cs:
            stock_col = c
    if not activity_col or not stock_col:
        return pd.DataFrame()
    # Filter to rows with actual activity (not "None" / "—" / blank)
    df = holdings[[stock_col, activity_col]].copy()
    df.columns = ["Stock", "Recent Activity"]
    df = df[df["Recent Activity"].notna()]
    df = df[~df["Recent Activity"].astype(str).str.strip().isin(["None", "—", "", "nan"])]
    return df.reset_index(drop=True)


@st.cache_data(ttl=43200)
def get_top_holdings_aggregate(top_n_managers: int = 10, top_n_holdings: int = 25) -> pd.DataFrame:
    """
    Aggregate the top holdings across all tracked superinvestors.
    Reveals 'consensus picks' — stocks held by the most legendary managers.
    """
    counts = {}
    for code in list(SUPERINVESTORS.keys())[:top_n_managers]:
        df = get_holdings(code)
        if df.empty:
            continue
        # Try to identify the ticker column
        ticker_col = None
        for c in df.columns:
            if any(k in str(c) for k in ("Stock", "Ticker", "Symbol")):
                ticker_col = c
                break
        if not ticker_col:
            continue
        for val in df[ticker_col].dropna().astype(str):
            # values are usually "TICKER - Company Name"
            tk = val.split("-")[0].strip().split()[0].upper()
            if tk and tk.isalnum() and len(tk) <= 6:
                counts[tk] = counts.get(tk, 0) + 1

    if not counts:
        return pd.DataFrame()
    df = pd.DataFrame([{"ticker": k, "n_managers": v} for k, v in counts.items()])
    return df.sort_values("n_managers", ascending=False).head(top_n_holdings).reset_index(drop=True)


@st.cache_data(ttl=43200)
def get_grand_portfolio() -> pd.DataFrame:
    """
    Pull Dataroma's official 'Grand Portfolio' — aggregated holdings across ALL
    tracked superinvestors, ranked by the number of managers holding.
    URL: https://dataroma.com/m/g/portfolio.php?pct=0&o=c
    """
    url = f"{DATAROMA}/m/g/portfolio.php?pct=0&o=c"
    try:
        r = requests.get(url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 EquityTerm/1.0"})
        if r.status_code != 200:
            return pd.DataFrame()
        tables = pd.read_html(StringIO(r.text))
        if not tables:
            return pd.DataFrame()
        best = max(tables, key=lambda t: len(t))
        return _clean_dataroma_df(best)
    except Exception:
        return pd.DataFrame()


# ============================================================
# CONGRESSIONAL TRADES (House Stock Watcher)
# ============================================================
@st.cache_data(ttl=21600)  # 6 hours
def get_congress_trades(days: int = 30) -> pd.DataFrame:
    """Pull recent House STOCK Act disclosures."""
    try:
        # House Stock Watcher serves a JSON endpoint
        urls = [
            "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json",
            "https://housestockwatcher.com/api/transactions",
        ]
        for url in urls:
            try:
                r = requests.get(url, timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0 EquityTerm/1.0"})
                if r.status_code == 200:
                    j = r.json()
                    if isinstance(j, list) and j:
                        df = pd.DataFrame(j)
                        # Normalize columns
                        if "transaction_date" in df.columns:
                            df["transaction_date"] = pd.to_datetime(
                                df["transaction_date"], errors="coerce")
                            cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
                            df = df[df["transaction_date"] >= cutoff]
                        return df
            except Exception:
                continue
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame()


def aggregate_congress_by_ticker(df: pd.DataFrame, days: int = 60) -> pd.DataFrame:
    """Roll up by ticker: # trades, # politicians, buy/sell ratio."""
    if df.empty:
        return pd.DataFrame()
    if "ticker" not in df.columns:
        return pd.DataFrame()
    if "transaction_date" in df.columns:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df["transaction_date"] >= cutoff]
    if df.empty:
        return pd.DataFrame()
    rows = []
    for tk, grp in df.groupby("ticker"):
        if not tk or pd.isna(tk) or str(tk).strip() == "--":
            continue
        n_trades = len(grp)
        n_politicians = grp["representative"].nunique() if "representative" in grp.columns else 0
        buys = grp[grp.get("type", pd.Series(["unknown"]*len(grp))).str.lower().str.contains("purchase", na=False)] \
            if "type" in grp.columns else pd.DataFrame()
        sells = grp[grp.get("type", pd.Series(["unknown"]*len(grp))).str.lower().str.contains("sale", na=False)] \
            if "type" in grp.columns else pd.DataFrame()
        rows.append({
            "ticker": tk,
            "n_trades": n_trades,
            "n_politicians": n_politicians,
            "buys": len(buys),
            "sells": len(sells),
            "net": len(buys) - len(sells),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["n_politicians", "n_trades"],
                                          ascending=False).reset_index(drop=True)
