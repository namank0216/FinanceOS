"""
lib/model_panel.py — run several LLMs on the SAME context, side by side, and
keep score over time. "Which model is better" becomes a measured question.

Providers (all OpenAI-compatible chat endpoints except Gemini), all with free tiers:
  groq        GROQ_API_KEY         Meta Llama 3.3 70B, OpenAI gpt-oss-120b, Qwen3
  gemini      GEMINI_API_KEY       Gemini 2.5 Flash (frontier closed model, free)
  openrouter  OPENROUTER_API_KEY   NVIDIA Nemotron, DeepSeek, Llama 4 (":free" slots rotate; 50 req/day)
  nvidia      NVIDIA_API_KEY       NVIDIA NIM (build.nvidia.com) — Nemotron / Llama-Nemotron
  cerebras    CEREBRAS_API_KEY     fast Llama / gpt-oss (card required for the grant)
  anthropic   ANTHROPIC_API_KEY    Claude Haiku (paid, pennies) — optional reference model

Roster is editable in the UI and persisted to .cache/model_roster.json; free model
IDs rotate, so a broken ID just shows an error in its card instead of breaking the page.

SCORING (the point of the exercise):
  * audit_pass    — a fixed auditor model checks each note's claims against the context
  * bias_7d       — every note ends with a JSON line {"bias_7d": up|down|flat, "conviction": 1-5,
                    "key_level": number}; the ledger stores it with the price at the time
  * realized      — when a note is ≥7 days old, the cron/page scores it against the actual
                    7-day return (flat = |ret| < 2%). Leaderboard = accuracy, audit rate, latency.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

try:
    import streamlit as st
except Exception:  # headless cron
    st = None

CACHE = Path(__file__).parent.parent / ".cache"
ROSTER_FILE = CACHE / "model_roster.json"
LEDGER_FILE = CACHE / "agent_notes.jsonl"

PROVIDERS = {
    "groq":       {"base": "https://api.groq.com/openai/v1", "key": "GROQ_API_KEY"},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "key": "OPENROUTER_API_KEY"},
    "nvidia":     {"base": "https://integrate.api.nvidia.com/v1", "key": "NVIDIA_API_KEY"},
    "cerebras":   {"base": "https://api.cerebras.ai/v1", "key": "CEREBRAS_API_KEY"},
    "gemini":     {"base": "https://generativelanguage.googleapis.com/v1beta", "key": "GEMINI_API_KEY"},
    "anthropic":  {"base": "https://api.anthropic.com/v1", "key": "ANTHROPIC_API_KEY"},
}

DEFAULT_ROSTER = [
    {"label": "Meta Llama 3.3 70B",   "provider": "groq",       "model": "llama-3.3-70b-versatile", "on": True},
    {"label": "OpenAI gpt-oss-120B",  "provider": "groq",       "model": "openai/gpt-oss-120b",     "on": True},
    {"label": "Gemini 2.5 Flash",     "provider": "gemini",     "model": "gemini-2.5-flash",        "on": True},
    {"label": "NVIDIA Nemotron (OR)", "provider": "openrouter", "model": "nvidia/nemotron-3-ultra-550b-a55b:free", "on": True},
    {"label": "DeepSeek V3 (OR)",     "provider": "openrouter", "model": "deepseek/deepseek-chat-v3-0324:free", "on": False},
    {"label": "NVIDIA Nemotron (NIM)","provider": "nvidia",     "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "on": False},
    {"label": "Claude Haiku (paid)",  "provider": "anthropic",  "model": "claude-haiku-4-5-20251001", "on": False},
]
AUDITOR = {"provider": "gemini", "model": "gemini-2.5-flash"}   # fixed grader; change in roster UI if no Gemini key

NOTE_PROMPT = (
    "You are a buy-side crypto strategist writing the morning note. Use ONLY the numbers and headlines in CONTEXT. "
    "Write four short sections with these exact headers: CYCLE READ / CATALYSTS (next 14 days, dated) / "
    "RULE STATUS (which of the user's rules is closest to triggering and the exact trigger) / RISK (single biggest, with the number that would confirm it). "
    "Every sentence must contain at least one number from CONTEXT. No predictions without a base rate from the evidence lines. "
    "Finish with ONE line of JSON and nothing after it: "
    '{"bias_7d": "up"|"down"|"flat", "conviction": 1-5, "key_level": <number>}\n\nCONTEXT:\n'
)
AUDIT_PROMPT = (
    "You are the risk auditor. CONTEXT is ground truth. List every numeric or factual claim in NOTE that is NOT "
    "supported by CONTEXT, quoting each. If all claims are supported reply exactly: AUDIT PASS. Then on a new line "
    'write JSON: {"unsupported": <count>}\n\nCONTEXT:\n{ctx}\n\nNOTE:\n{note}'
)


# ------------------------------------------------------------------ keys / roster
def _key(name: str) -> str | None:
    v = os.getenv(name)
    if not v and st is not None:
        try:
            v = st.secrets.get(name)
        except Exception:
            v = None
    return v


def load_roster() -> list[dict]:
    try:
        return json.loads(ROSTER_FILE.read_text())
    except Exception:
        return [dict(r) for r in DEFAULT_ROSTER]


def save_roster(roster: list[dict]):
    CACHE.mkdir(exist_ok=True)
    ROSTER_FILE.write_text(json.dumps(roster, indent=1))


def available(roster: list[dict]) -> list[dict]:
    return [r for r in roster if r.get("on") and _key(PROVIDERS[r["provider"]]["key"])]


# ------------------------------------------------------------------ calls
def _chat(provider: str, model: str, prompt: str, max_tokens: int = 700, timeout: int = 45) -> tuple[str, float]:
    key = _key(PROVIDERS[provider]["key"])
    if not key:
        return "", 0.0
    t0 = time.time()
    base = PROVIDERS[provider]["base"]
    if provider == "gemini":
        url = f"{base}/models/{model}:generateContent?key={key}"
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2}}
        r = requests.post(url, json=body, timeout=timeout); r.raise_for_status()
        j = r.json()
        text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    elif provider == "anthropic":
        r = requests.post(f"{base}/messages", timeout=timeout,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": model, "max_tokens": max_tokens, "temperature": 0.2,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status(); text = "".join(b.get("text", "") for b in r.json()["content"])
    else:  # OpenAI-compatible
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://pulsefi.streamlit.app"; headers["X-Title"] = "PulseFi"
        r = requests.post(f"{base}/chat/completions", headers=headers, timeout=timeout,
                          json={"model": model, "temperature": 0.2, "max_tokens": max_tokens,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status(); text = r.json()["choices"][0]["message"]["content"]
    return text.strip(), round(time.time() - t0, 1)


def _parse_json_tail(text: str) -> dict:
    m = re.findall(r"\{[^{}]*\}", text)
    for cand in reversed(m):
        try:
            j = json.loads(cand)
            if "bias_7d" in j or "unsupported" in j:
                return j
        except Exception:
            continue
    return {}


def _run_one(entry: dict, context: str, asset: str, price: float) -> dict:
    out = {"ts": datetime.now(timezone.utc).isoformat(), "asset": asset, "price": price,
           "label": entry["label"], "provider": entry["provider"], "model": entry["model"],
           "note": "", "latency_s": None, "error": "", "bias_7d": None, "conviction": None, "key_level": None}
    try:
        text, lat = _chat(entry["provider"], entry["model"], NOTE_PROMPT + context)
        j = _parse_json_tail(text)
        out.update(note=text, latency_s=lat, bias_7d=j.get("bias_7d"), conviction=j.get("conviction"), key_level=j.get("key_level"))
    except Exception as e:
        out["error"] = str(e)[:160]
    return out


def audit(note: str, context: str) -> dict:
    if not note:
        return {"audit": "", "unsupported": None, "audit_pass": None}
    try:
        text, _ = _chat(AUDITOR["provider"], AUDITOR["model"], AUDIT_PROMPT.format(ctx=context, note=note), max_tokens=350)
        j = _parse_json_tail(text)
        return {"audit": text, "unsupported": j.get("unsupported"), "audit_pass": text.strip().startswith("AUDIT PASS") or j.get("unsupported") == 0}
    except Exception as e:
        return {"audit": f"(auditor error: {str(e)[:80]})", "unsupported": None, "audit_pass": None}


def run_panel(context: str, asset: str, price: float, roster: list[dict] | None = None, do_audit: bool = True) -> list[dict]:
    roster = available(roster or load_roster())
    if not roster or not context:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=min(6, len(roster))) as ex:
        futs = {ex.submit(_run_one, r, context, asset, price): r for r in roster}
        for f in as_completed(futs):
            results.append(f.result())
    if do_audit:
        for r in results:
            r.update(audit(r["note"], context))
    results.sort(key=lambda r: r["label"])
    _append_ledger(results)
    return results


# ------------------------------------------------------------------ ledger + scoring
def _append_ledger(rows: list[dict]):
    try:
        CACHE.mkdir(exist_ok=True)
        with LEDGER_FILE.open("a") as f:
            for r in rows:
                slim = {k: r.get(k) for k in ("ts", "asset", "price", "label", "provider", "model", "latency_s", "error",
                                              "bias_7d", "conviction", "key_level", "unsupported", "audit_pass")}
                slim["note"] = (r.get("note") or "")[:1500]
                f.write(json.dumps(slim, default=str) + "\n")
    except Exception:
        pass


def ledger() -> pd.DataFrame:
    try:
        rows = [json.loads(l) for l in LEDGER_FILE.read_text().splitlines() if l.strip()]
        d = pd.DataFrame(rows); d["ts"] = pd.to_datetime(d["ts"], utc=True); return d
    except Exception:
        return pd.DataFrame()


def score(price_series: pd.Series, asset: str, horizon_days: int = 7, flat_band: float = 0.02) -> pd.DataFrame:
    """Leaderboard: per model — notes, audit pass %, unsupported claims/note, realized 7d directional accuracy."""
    d = ledger()
    if d.empty:
        return pd.DataFrame()
    d = d[d["asset"] == asset].copy()
    ps = price_series.copy(); ps.index = pd.to_datetime(ps.index).tz_localize("UTC") if ps.index.tz is None else ps.index
    realized = []
    for r in d.itertuples():
        t_end = r.ts + pd.Timedelta(days=horizon_days)
        if t_end > ps.index[-1] or r.bias_7d not in ("up", "down", "flat") or not r.price:
            realized.append(None); continue
        p_end = float(ps[ps.index <= t_end].iloc[-1]); ret = p_end / float(r.price) - 1
        actual = "flat" if abs(ret) < flat_band else "up" if ret > 0 else "down"
        realized.append(actual == r.bias_7d)
    d["correct_7d"] = realized
    g = d.groupby("label").agg(
        notes=("ts", "count"), errors=("error", lambda s: int((s.fillna("") != "").sum())),
        audit_pass_pct=("audit_pass", lambda s: round(100 * s.dropna().astype(bool).mean(), 0) if s.dropna().size else None),
        unsupported_per_note=("unsupported", lambda s: round(s.dropna().astype(float).mean(), 2) if s.dropna().size else None),
        scored_7d=("correct_7d", lambda s: int(s.dropna().size)),
        accuracy_7d_pct=("correct_7d", lambda s: round(100 * s.dropna().astype(bool).mean(), 0) if s.dropna().size else None),
        avg_latency_s=("latency_s", "mean"),
    ).reset_index()
    g["avg_latency_s"] = g["avg_latency_s"].round(1)
    return g.sort_values(["accuracy_7d_pct", "audit_pass_pct"], ascending=False, na_position="last")


def openrouter_free_models() -> list[str]:
    """Helper for the roster UI: current ':free' model IDs (they rotate)."""
    try:
        j = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json()
        return sorted(m["id"] for m in j.get("data", []) if m.get("id", "").endswith(":free"))
    except Exception:
        return []
