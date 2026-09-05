"""
lib/crypto_agents.py — the "living framework" layer for the Crypto Cycle page.

Runs on page launch (cached, TTL 15 min) and optionally on a daily GitHub
Actions cron (scripts/refresh_crypto.py) so the app opens with fresh state
and builds a history of snapshots.

AGENTS (deterministic unless marked LLM):
  1. halving_agent     block height → projected next halving date (mempool.space / blockchain.info)
  2. sentiment_agent   Fear & Greed (alternative.me) + perp funding (Binance → OKX fallback)
  3. news_agent        crypto RSS via feedparser, tagged by catalyst type, deduped
  4. calendar_agent    FOMC (published schedule) + CPI (BLS page, best-effort) → next events
  5. etf_agent         US spot-ETF daily flows (Farside HTML, best-effort; fails quietly)
  6. recalibrate       adaptive euphoria threshold from the declining peak-MVRV series
  7. snapshot/diff     persist today's state; "what changed since last visit"
  8. analyst (LLM)     numbers + tagged headlines → structured read
  9. auditor (LLM)     second model pass: every claim must cite a number present in context;
                       unsupported claims are flagged. Generator + verifier pattern.

Every agent returns a dict with an 'ok' flag and 'source'. Nothing raises.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import numpy as np
import pandas as pd
import requests
import streamlit as st

from . import ai_summary, crypto_cycle as cc, model_panel as mp

STATE_DIR = Path(__file__).parent.parent / ".cache"
STATE_FILE = STATE_DIR / "crypto_state.json"
HIST_FILE = STATE_DIR / "crypto_state_history.jsonl"
UA = {"User-Agent": "Mozilla/5.0 (PulseFi research bot)"}

# Published FOMC meeting dates (second day = decision). Extend when the Fed
# publishes the next year's calendar (usually each summer).
FOMC = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
        "2026-09-16", "2026-10-28", "2026-12-09"]

CRYPTO_RSS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
]

CATALYST_TAGS = {
    "MACRO": ["fomc", "fed ", "federal reserve", "rate cut", "rate hike", "powell", "waller", "cpi", "inflation", "treasury", "yields", "tariff"],
    "ETF/FLOWS": ["etf", "inflow", "outflow", "blackrock", "ibit", "fidelity", "grayscale", "strategy buys", "microstrategy", "saylor", "treasury company"],
    "REGULATION": ["sec", "clarity act", "senate", "congress", "regulation", "cftc", "stablecoin bill", "genius act", "lawsuit"],
    "LIQUIDATION/LEVERAGE": ["liquidat", "leverage", "open interest", "funding rate", "short squeeze", "long squeeze"],
    "ON-CHAIN": ["mvrv", "realized", "whale", "exchange reserve", "miner", "hashrate", "halving"],
    "SECURITY/RISK": ["hack", "exploit", "bankrupt", "insolven", "ftx", "fraud"],
}


def _ok(**kw):
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat(), **kw}


def _fail(source, err=""):
    return {"ok": False, "source": source, "error": str(err)[:120]}


# ============================================================
# 1. Halving projection from block height
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def halving_agent() -> dict:
    height = None; src = None
    for url, key in (("https://mempool.space/api/blocks/tip/height", None),
                     ("https://blockchain.info/q/getblockcount", None)):
        try:
            r = requests.get(url, timeout=8, headers=UA); r.raise_for_status()
            height = int(r.text.strip()); src = url.split("/")[2]; break
        except Exception:
            continue
    if height is None:
        return _fail("block height", "all sources failed")
    next_h_block = ((height // 210_000) + 1) * 210_000
    remaining = next_h_block - height
    # observed block interval: last 2016 blocks (~2 weeks) via mempool difficulty-adjustment endpoint
    interval_min = 10.0
    try:
        r = requests.get("https://mempool.space/api/v1/difficulty-adjustment", timeout=8, headers=UA)
        j = r.json(); interval_min = float(j.get("timeAvg", 600_000)) / 60_000
    except Exception:
        pass
    eta = datetime.utcnow() + timedelta(minutes=remaining * interval_min)
    return _ok(source=src, height=height, next_halving_block=next_h_block, blocks_remaining=remaining,
               avg_block_min=round(interval_min, 2), projected_date=eta.date().isoformat(),
               drift_vs_static_days=(eta - cc.NEXT_HALVING_PROJECTED).days)


# ============================================================
# 2. Sentiment / positioning
# ============================================================
@st.cache_data(ttl=1800, show_spinner=False)
def sentiment_agent() -> dict:
    out = {}
    try:
        j = requests.get("https://api.alternative.me/fng/?limit=8", timeout=8, headers=UA).json()["data"]
        out["fear_greed"] = int(j[0]["value"]); out["fear_greed_label"] = j[0]["value_classification"]
        out["fear_greed_7d_ago"] = int(j[-1]["value"])
    except Exception as e:
        out["fear_greed_error"] = str(e)[:80]
    # funding: Binance perp → OKX fallback (Binance is geo-blocked in some regions incl. some US hosts)
    fund = None; fsrc = None
    try:
        j = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"}, timeout=8, headers=UA).json()
        fund = float(j["lastFundingRate"]) * 100; fsrc = "Binance"
    except Exception:
        try:
            j = requests.get("https://www.okx.com/api/v5/public/funding-rate", params={"instId": "BTC-USDT-SWAP"}, timeout=8, headers=UA).json()
            fund = float(j["data"][0]["fundingRate"]) * 100; fsrc = "OKX"
        except Exception:
            pass
    if fund is not None:
        out["funding_8h_pct"] = round(fund, 4); out["funding_annualized_pct"] = round(fund * 3 * 365, 1); out["funding_source"] = fsrc
        out["funding_read"] = ("crowded longs" if fund > 0.03 else "crowded shorts" if fund < -0.01 else "neutral")
    return _ok(source="alternative.me / " + (fsrc or "no funding"), **out)


# ============================================================
# 3. News, tagged by catalyst
# ============================================================
def _tag(title: str) -> list[str]:
    t = title.lower()
    return [k for k, words in CATALYST_TAGS.items() if any(w in t for w in words)]


@st.cache_data(ttl=900, show_spinner=False)
def news_agent(max_items: int = 40, hours: int = 48, asset_terms: tuple = ()) -> pd.DataFrame:
    """Crypto RSS (direct) + the app's macro/government feeds (indirect), tagged.
    asset_terms: coin name/symbol → rows mentioning them get the 'ASSET' tag."""
    rows = []; cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    terms = tuple(t.lower() for t in asset_terms if t and len(t) > 2)
    for src, url in CRYPTO_RSS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:25]:
                ts = None
                for k in ("published_parsed", "updated_parsed"):
                    if getattr(e, k, None):
                        ts = datetime(*getattr(e, k)[:6], tzinfo=timezone.utc); break
                if ts and ts < cutoff:
                    continue
                title = re.sub(r"\s+", " ", e.get("title", "")).strip()
                tags = _tag(title)
                if terms and any(t in title.lower() for t in terms):
                    tags = ["ASSET"] + tags
                rows.append({"time": ts, "source": src, "title": title, "link": e.get("link", ""), "tags": ", ".join(tags), "channel": "direct"})
        except Exception:
            continue
    # indirect: macro / government / SEC feeds already in lib.data — keep only high-impact or tagged items
    try:
        from . import data as _data
        mk = _data.get_market_news(max_per_feed=15)
        for r in mk.itertuples():
            title = str(getattr(r, "title", "")); tags = _tag(title)
            hi = bool(getattr(r, "high_impact", False)) if hasattr(r, "high_impact") else False
            if tags or hi:
                ts = getattr(r, "ts", None)
                rows.append({"time": ts, "source": getattr(r, "source", "macro"), "title": title, "link": getattr(r, "link", ""),
                             "tags": ", ".join(tags or ["MACRO"]), "channel": "indirect"})
    except Exception:
        pass
    if not rows:
        return pd.DataFrame(columns=["time", "source", "title", "link", "tags", "channel"])
    df = pd.DataFrame(rows).drop_duplicates("title").sort_values("time", ascending=False)
    # catalyst-tagged first
    df["has_tag"] = df["tags"].str.len() > 0
    return df.sort_values(["has_tag", "time"], ascending=[False, False]).drop(columns="has_tag").head(max_items).reset_index(drop=True)


# ============================================================
# 4. Macro calendar
# ============================================================
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def calendar_agent(days_ahead: int = 21) -> dict:
    today = datetime.utcnow().date()
    events = [{"date": d, "event": "FOMC decision", "kind": "MACRO"} for d in FOMC]
    # CPI: BLS schedule page, best effort
    try:
        html = requests.get("https://www.bls.gov/schedule/news_release/cpi.htm", timeout=10, headers=UA).text
        for m in re.finditer(r"([A-Z][a-z]+\.? \d{1,2}, \d{4})", html):
            try:
                d = datetime.strptime(m.group(1).replace(".", ""), "%B %d, %Y").date()
            except ValueError:
                try:
                    d = datetime.strptime(m.group(1).replace(".", ""), "%b %d, %Y").date()
                except ValueError:
                    continue
            if today <= d <= today + timedelta(days=120):
                events.append({"date": d.isoformat(), "event": "CPI release", "kind": "MACRO"})
        cpi_src = "bls.gov"
    except Exception:
        cpi_src = "unavailable"
    # quarterly futures/options expiry: last Friday of Mar/Jun/Sep/Dec
    for m in (3, 6, 9, 12):
        for y in (today.year, today.year + 1):
            d = datetime(y, m, 1) + pd.offsets.MonthEnd(0)
            d = d - pd.Timedelta(days=(d.weekday() - 4) % 7)
            events.append({"date": d.date().isoformat(), "event": "Quarterly expiry", "kind": "LEVERAGE"})
    ev = pd.DataFrame(events).drop_duplicates()
    ev["date"] = pd.to_datetime(ev["date"]).dt.date
    upcoming = ev[(ev["date"] >= today) & (ev["date"] <= today + timedelta(days=days_ahead))].sort_values("date")
    upcoming["days"] = [(d - today).days for d in upcoming["date"]]
    return _ok(source=f"FOMC static list / CPI {cpi_src}", upcoming=upcoming.reset_index(drop=True))


# ============================================================
# 5. ETF flows (best effort)
# ============================================================
@st.cache_data(ttl=3600, show_spinner=False)
def etf_agent() -> dict:
    try:
        html = requests.get("https://farside.co.uk/btc/", timeout=12, headers=UA).text
        tables = pd.read_html(html)
        t = max(tables, key=len)
        t.columns = [str(c).strip() for c in t.columns]
        total_col = next((c for c in t.columns if "total" in c.lower()), t.columns[-1])
        t = t[~t.iloc[:, 0].astype(str).str.contains("Total|Average|Maximum|Minimum", na=False)]
        vals = pd.to_numeric(t[total_col].astype(str).str.replace(r"[(),$]", "", regex=True).str.replace("−", "-"), errors="coerce").dropna()
        last5 = vals.tail(5)
        return _ok(source="farside.co.uk", last_day_musd=float(last5.iloc[-1]), last5_sum_musd=float(last5.sum()),
                   last5=[float(x) for x in last5], read=("inflows" if last5.sum() > 0 else "outflows"))
    except Exception as e:
        return _fail("farside.co.uk", e)


# ============================================================
# 6. Recalibration from data
# ============================================================
def recalibrate(df: pd.DataFrame) -> dict:
    """Adaptive parameters derived from the data, replacing fixed constants."""
    out = {}
    if df is None or df.empty or df["mvrv"].isna().all():
        return out
    m = df["mvrv"]
    peaks = [pk for pk in cc.CYCLE_PEAKS_BTC if pk in m.index and not np.isnan(m[pk])]
    if len(peaks) >= 2:
        pk_mvrv = [float(m[pk]) for pk in peaks]
        # each peak's MVRV as a ratio of the previous (5.06→4.25→2.72→2.22 ≈ 0.84, 0.64, 0.82)
        ratios = [pk_mvrv[i] / pk_mvrv[i - 1] for i in range(1, len(pk_mvrv))]
        nxt = pk_mvrv[-1] * float(np.mean(ratios))
        out["peak_mvrv_series"] = [round(v, 2) for v in pk_mvrv]
        out["expected_next_peak_mvrv"] = round(nxt, 2)
        # threshold: 85% of the LAST peak, floored at 2.0 so it can't fire mid-cycle.
        # Only meaningful INSIDE the post-halving peak window (compute_signals enforces this).
        out["euphoria_threshold_adaptive"] = round(max(2.0, 0.85 * pk_mvrv[-1]), 2)
        out["note"] = ("MVRV is losing discriminating power as peaks compress; the post-halving peak window is the primary "
                       "exit signal, MVRV above threshold inside it is confirmation.")
    # trough stats for the clock window
    return out


# ============================================================
# 7. Snapshot + diff
# ============================================================
def _state_from(sig: cc.Signals, extras: dict) -> dict:
    d = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in sig.__dict__.items() if k != "notes"}
    d["extras"] = extras
    d["saved"] = datetime.now(timezone.utc).isoformat()
    return d


def snapshot(sig: cc.Signals, extras: dict) -> dict:
    """Persist state, return diff vs previous snapshot."""
    new = _state_from(sig, extras)
    old = {}
    try:
        old = json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    changes = []
    watch = {"below_wma": "Price vs 200WMA", "in_bottom_window": "Post-peak window", "mvrv_state": "MVRV state",
             "structure": "Structure", "buy_count": "Buy signals", "sell_count": "Sell signals",
             "in_peak_window": "Peak window", "in_buy_date": "Halving buy date"}
    for k, lbl in watch.items():
        if old and old.get(k) != new.get(k):
            changes.append(f"{lbl}: {old.get(k)} → {new.get(k)}")
    if old and abs(new["price"] / max(old.get("price", new["price"]), 1) - 1) > 0.05:
        changes.append(f"Price moved {new['price']/old['price']-1:+.1%} since last snapshot ({old.get('saved','')[:10]})")
    if old and new.get("ath") and old.get("ath") and new["ath"] > old["ath"] * 1.001:
        changes.append("NEW ALL-TIME HIGH — post-peak clock reset")
    try:
        STATE_DIR.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(new, default=str))
        with HIST_FILE.open("a") as f:
            f.write(json.dumps({"saved": new["saved"], "price": new["price"], "ratio": new["ratio"], "mvrv": new["mvrv"],
                                "buy": new["buy_count"], "sell": new["sell_count"]}, default=str) + "\n")
    except Exception:
        pass
    return {"changes": changes, "previous_saved": old.get("saved"), "first_run": not bool(old)}


def history() -> pd.DataFrame:
    try:
        rows = [json.loads(l) for l in HIST_FILE.read_text().splitlines() if l.strip()]
        h = pd.DataFrame(rows); h["saved"] = pd.to_datetime(h["saved"]); return h
    except Exception:
        return pd.DataFrame()


# ============================================================
# 8-9. LLM analyst + auditor
# ============================================================
def _llm(prompt: str, max_tokens: int = 500) -> str:
    prov = ai_summary.detect_provider()
    if not prov:
        return ""
    try:
        return ai_summary.ask_specific(prov, prompt, max_tokens=max_tokens) or ""
    except Exception:
        return ""


def analyst_agent(context: str) -> str:
    prompt = ("You are a buy-side crypto strategist writing the morning note. Use ONLY the numbers and headlines below. "
              "Return exactly four short sections with these headers: CYCLE READ / CATALYSTS (next 14 days, dated) / "
              "RULE STATUS (which of the user's rules is closest to triggering and the exact trigger) / RISK (single biggest, with the number that would confirm it). "
              "Every sentence must contain at least one number from the context. No predictions without a base rate from the evidence lines.\n\n" + context)
    return _llm(prompt, 550)


def auditor_agent(analysis: str, context: str) -> str:
    if not analysis:
        return ""
    prompt = ("You are the risk auditor. Below is a CONTEXT (ground truth numbers) and an ANALYSIS written from it. "
              "List every numeric or factual claim in the ANALYSIS that is NOT supported by the CONTEXT, quoting the claim. "
              "If everything is supported, reply exactly: 'AUDIT PASS — all claims traceable to context.' Be strict and brief.\n\n"
              f"CONTEXT:\n{context}\n\nANALYSIS:\n{analysis}")
    return _llm(prompt, 300)


# ============================================================
# Orchestrator — runs on page launch
# ============================================================
@st.cache_data(ttl=900, show_spinner="Agents refreshing state…")
def run_pipeline(asset: str = "BTC", params: dict | None = None, use_llm: bool = True, use_panel: bool = True) -> dict:
    p = {**cc.DEFAULTS, **(params or {})}
    halv = halving_agent()
    if halv.get("ok"):
        p["next_halving"] = halv["projected_date"]
    df, meta = cc.merged_history(asset)
    recal = recalibrate(df) if not df.empty else {}
    if recal.get("euphoria_threshold_adaptive"):
        p["mvrv_high"] = recal["euphoria_threshold_adaptive"]
    live = cc.live_price(asset)
    sig = cc.compute_signals(df, asset, live, p) if not df.empty else None
    meta_a = cc.ASSETS.get(asset, {})
    sent = sentiment_agent(); cal = calendar_agent()
    news = news_agent(asset_terms=(meta_a.get("name", ""), asset))
    etf = etf_agent() if asset == "BTC" else _fail("etf", "BTC only")
    ev = cc.evidence(asset, p) if not df.empty else {}

    extras = {"halving": halv, "sentiment": sent, "etf": etf, "recal": recal,
              "calendar": cal.get("upcoming").to_dict("records") if cal.get("ok") else []}
    diff = snapshot(sig, {k: v for k, v in extras.items() if k != "calendar"}) if sig else {"changes": [], "first_run": True}

    context = ""
    analysis = audit = ""
    if sig:
        plan = {}
        try:
            plan = json.loads((STATE_DIR / "crypto_plan.json").read_text()).get(asset, {})
        except Exception:
            pass
        context = cc.context_for_ai(sig, ev, plan)
        if sent.get("ok"):
            context += f"\nSentiment: Fear&Greed {sent.get('fear_greed')} ({sent.get('fear_greed_label')}), 7d ago {sent.get('fear_greed_7d_ago')}; funding {sent.get('funding_8h_pct')}%/8h ({sent.get('funding_read')})."
        if etf.get("ok"):
            context += f"\nETF flows: last day {etf['last_day_musd']:+.0f}M USD, last 5 days {etf['last5_sum_musd']:+.0f}M ({etf['read']})."
        if halv.get("ok"):
            context += f"\nHalving projection from block {halv['height']}: {halv['projected_date']} ({halv['drift_vs_static_days']:+d}d vs static assumption)."
        if recal:
            context += f"\nAdaptive euphoria threshold {p['mvrv_high']} (peak MVRV series {recal.get('peak_mvrv_series')})."
        if cal.get("ok") and len(cal["upcoming"]):
            context += "\nCalendar: " + "; ".join(f"{r.event} {r.date} (+{r.days}d)" for r in cal["upcoming"].itertuples())
        if not news.empty:
            context += "\nTagged headlines (48h): " + " | ".join(f"[{t.tags or 'untagged'}] {t.title}" for t in news.head(12).itertuples())
        if diff["changes"]:
            context += "\nChanged since last snapshot: " + "; ".join(diff["changes"])
        if use_llm:
            analysis = analyst_agent(context)
            audit = auditor_agent(analysis, context)
    panel = mp.run_panel(context, asset, sig.price, do_audit=True) if (sig and use_llm and use_panel) else []

    return {"params": p, "sig": sig, "meta": meta, "evidence": ev, "halving": halv, "sentiment": sent, "etf": etf,
            "recal": recal, "calendar": cal, "news": news, "diff": diff, "context": context,
            "analysis": analysis, "audit": audit, "panel": panel, "df": df, "live": live}
