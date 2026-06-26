# EquityTerm — Bloomberg-style Position-Trading Terminal for Stocks

A free, local, institutional-grade decision system for position trading US equities.

**Methodology:** Hybrid **Quality at a Reasonable Price (QARP)** + **Stage Analysis** + **Macro Regime gating** + **Catalyst timing**. The William O'Neil × Mark Minervini × AQR factor stack, layered with Stan Weinstein's stage framework and a top-down macro overlay. Battle-tested across 50+ years of market regimes.

The point isn't to call tops or bottoms. The point is: **be in the strongest stocks in the strongest sectors when the macro regime supports risk-on, sized by your edge, with rules that make emotion irrelevant.**

---

## How decisions get made

```
        MACRO REGIME (Risk On / Off / Neutral)
                    ↓
              SECTOR ROTATION
                    ↓
            STAGE ANALYSIS per stock
              (only Stage 2 candidates)
                    ↓
         MULTI-FACTOR COMPOSITE SCORE
       Trend × Momentum × Quality × Value × Earnings
                    ↓
            VALUATION VERDICT
       (Undervalued / Fair / Overvalued)
                    ↓
             CATALYST CHECK
       (Earnings beat? Drift active? News?)
                    ↓
         POSITION SIZING (vol-targeted)
                    ↓
                ENTRY → EXIT rules
```

Each layer is a gate. A trade that fails any gate doesn't happen. This is what removes the emotion — you don't decide, the layers decide.

---

## Modules (v1)

| Module | What it does |
|---|---|
| 📊 Market Cockpit | S&P 500 / Nasdaq / sectors / VIX / breadth — daily glance |
| ⚡ Leveraged ETF Hub | TQQQ, FNGU, SOXL, UPRO, TECL, TNA + inverses. Decay analysis, leverage-gate-aware sizing, underlying tracking |
| 📈 Macro Regime + Leverage Gate | VIX, yield curve, credit spreads, breadth → risk-on/off classification AND a binary 🟢🟡🔴 gate that says whether 3× products are safe to hold |
| 🌐 Sector Rotation | Relative Rotation Graph (RRG) of 11 SPDR sectors vs SPY |
| 🧠 Stage Engine | Weinstein stage classifier + multi-factor composite for any ticker |
| 🔍 Stock Screener | Universe scan, Stage 2 candidates ranked by trend × momentum |
| 🔬 Stock Deep Dive | One-ticker research: chart, fundamentals, holders, recommendations, news |
| 💰 Smart Money Tracker | Dataroma superinvestors + Congressional trades + corporate insider Form 4 |
| 💎 Valuation Engine | DCF, peer multiples, sector multiples, analyst consensus → fair value range |
| 📰 News Flow | Yahoo + MarketWatch + Seeking Alpha + CNBC RSS with sentiment scoring |

**Coming in v2 (next build):** Earnings Engine (PEAD analysis), Portfolio + Risk, Backtest Lab, Decision Journal, Alert Center, Strategy Optimizer.

### Leveraged ETF philosophy

You trade TQQQ / FNGU / SOXL. Treat them as macro vehicles, not stock substitutes:

- **They are NOT buy-and-hold.** Volatility drag means a flat year on the underlying can be a losing year on the 3× version. Hold periods of weeks-to-months only, with rules.
- **The Macro Regime gate is non-negotiable.** When the gate is 🔴, you don't hold 3× products. Period. The hub will visually show this.
- **Sizing scales inverse to leverage.** A 1% account-risk position in QQQ is a ~0.33% position in TQQQ. The Leveraged ETF Hub does this math for you.
- **Underlying drives signals, ETF drives execution.** Stage analysis runs on QQQ for TQQQ signals, on SOXX for SOXL, on the FANG+ index basket for FNGU. The ETF chart is a confirmation lens, not the source of signal.

---

## Universe

Default: **S&P 500 + Nasdaq 100** (~600 unique tickers). Pulled live from Wikipedia at first run, cached locally.

---

## Install

You need Python 3.10+.

```bash
cd stocks_portal
pip install -r requirements.txt
streamlit run app.py
```

Or just **double-click `run.bat`** (Windows). First run installs deps, ~60 seconds.

---

## Optional API keys (free, no credit card)

The system works fully without keys but unlocks significantly better data when you provide them:

| Provider | What it adds | Free tier | Signup |
|---|---|---|---|
| Finnhub | Real-time news per ticker, earnings calendar with surprises, analyst recs, insider transactions | 60 calls/min | https://finnhub.io |
| Financial Modeling Prep (FMP) | Detailed financial statements, ratios (ROIC/FCF yield), analyst targets, DCF inputs | 250 calls/day | https://financialmodelingprep.com |

Add them to a `.env` file in the `stocks_portal` folder:

```
FINNHUB_API_KEY=your_key_here
FMP_API_KEY=your_key_here
```

The data layer auto-detects these and routes appropriately.

---

## Data sources (all free)

| Source | Used for |
|---|---|
| yfinance (Yahoo Finance) | OHLCV, fundamentals, earnings dates, holders, options, recommendations |
| FRED (St. Louis Fed) | VIX, yield curve, credit spreads, all macro |
| Wikipedia | S&P 500 + Nasdaq 100 universe lists |
| RSS (Yahoo Finance, MarketWatch, Seeking Alpha) | News headlines |
| SEC EDGAR | 13F filings, Form 4 insider transactions (v2) |
| Finnhub (optional key) | News, earnings, recs, insiders |
| Financial Modeling Prep (optional key) | Statements, ratios, DCF |

If any source is down, the affected panel shows "data unavailable" and the rest keeps working.

---

## Disclaimer

Research and decision-support tool. Not financial advice. The capital is yours, the calls are yours, the risk is yours.
