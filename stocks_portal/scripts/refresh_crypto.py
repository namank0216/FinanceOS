"""
Headless daily refresh: runs the agent pipeline for BTC and ETH, writes the
snapshot + history into .cache/ so the app opens with fresh state and a
growing history even when nobody has visited. Run by .github/workflows/crypto_refresh.yml.

Usage:  python scripts/refresh_crypto.py   (from stocks_portal/)
Set GROQ_API_KEY / GEMINI_API_KEY as repo secrets to include the LLM notes.
"""
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import crypto_agents as ag  # noqa: E402

out = {}
for asset in ("BTC", "ETH"):
    R = ag.run_pipeline(asset, use_llm=bool(os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")))
    s = R["sig"]
    out[asset] = {"price": s.price if s else None, "ratio": round(s.ratio, 3) if s else None,
                  "buy": s.buy_count if s else None, "sell": s.sell_count if s else None,
                  "changes": R["diff"].get("changes"), "halving": R["halving"].get("projected_date"),
                  "analysis": R["analysis"][:2000], "audit": R["audit"][:800]}
    print(asset, json.dumps(out[asset], default=str)[:400])
Path(".cache").mkdir(exist_ok=True)
Path(".cache/last_refresh.json").write_text(json.dumps(out, default=str, indent=1))
