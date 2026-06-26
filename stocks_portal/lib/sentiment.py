"""Lightweight lexicon-based sentiment for finance headlines."""

from __future__ import annotations

import re

POSITIVE = {
    "beat","beats","tops","exceeds","upgrade","upgraded","raises","raised",
    "surge","soar","rally","rallies","gain","gains","jump","jumps","rise",
    "rises","climb","record","high","ath","strong","robust","outperform",
    "outperforms","buy","accumulate","upside","growth","expansion","launch",
    "approve","approved","approval","partnership","deal","acquire","acquisition",
    "guidance raised","guidance raise","initiate buy","positive","milestone",
    "breakthrough","authorize","dividend","buyback","repurchase",
}
NEGATIVE = {
    "miss","misses","missed","downgrade","downgraded","cut","cuts","slash",
    "plunge","tumble","fall","falls","drop","drops","decline","slip","slips",
    "underperform","underperforms","sell","reduce","downside","loss","losses",
    "warning","warns","caution","cautious","weak","disappoint","disappointing",
    "guidance cut","guidance lowered","guidance lower","probe","investigation",
    "lawsuit","sue","sued","fine","fined","sec investigation","fraud","recall",
    "halt","layoff","layoffs","bankruptcy","insolvency","default","downgrade",
    "negative","headwind","headwinds","slowdown","contracted","contraction",
}
INTENSIFIERS = {"massive","huge","major","record","extreme","unprecedented","sharp"}

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


def score_text(text: str) -> dict:
    if not text:
        return {"score": 0.0, "pos": 0, "neg": 0, "magnitude": 0.0}
    words = [w.lower() for w in WORD_RE.findall(text)]
    if not words:
        return {"score": 0.0, "pos": 0, "neg": 0, "magnitude": 0.0}
    pos = sum(1 for w in words if w in POSITIVE)
    neg = sum(1 for w in words if w in NEGATIVE)
    intens = sum(1 for w in words if w in INTENSIFIERS)
    if pos == 0 and neg == 0:
        return {"score": 0.0, "pos": 0, "neg": 0, "magnitude": 0.0}
    raw = (pos - neg) / max(pos + neg, 1)
    boost = 1 + 0.2 * intens
    score = max(-1.0, min(1.0, raw * boost))
    return {
        "score": round(score, 3), "pos": pos, "neg": neg,
        "magnitude": round((pos + neg) / max(len(words), 1), 3),
    }


def label(score: float) -> str:
    if score >= 0.5:   return "VERY BULLISH"
    if score >= 0.15:  return "BULLISH"
    if score <= -0.5:  return "VERY BEARISH"
    if score <= -0.15: return "BEARISH"
    return "NEUTRAL"
