"""
Plain-English explainers for technical metrics and indicators.

Every function here either:
  * Takes a number, returns (verdict_label, plain_english_explanation)
  * Or generates a narrative summary for a whole page section

Used across pages so non-technical users get a friendly read of the data
alongside the raw numbers. The technical detail stays — we just translate.
"""

from __future__ import annotations

# ============================================================
# Glossary — short + long for tooltips
# ============================================================
GLOSSARY = {
    "P/E Ratio": {
        "short": "How expensive the stock is vs. its earnings.",
        "long": "Price-to-Earnings ratio. P/E of 20 means you pay $20 for every $1 of annual earnings. "
                "Lower = cheaper. S&P 500 historical average is ~18-22.",
    },
    "Forward P/E": {
        "short": "P/E based on next year's expected earnings.",
        "long": "Same as P/E but using analyst forecasts of next year's profit. If forward P/E is "
                "lower than trailing P/E, the market expects earnings to grow.",
    },
    "P/S Ratio": {
        "short": "Price relative to revenue. Useful when earnings are negative.",
        "long": "Price-to-Sales. Lower = cheaper. Best for fast-growing companies that aren't yet profitable.",
    },
    "P/B Ratio": {
        "short": "Price relative to book value (assets minus liabilities).",
        "long": "Price-to-Book. Below 1 = trading below liquidation value. Useful for asset-heavy "
                "businesses (banks, insurers) but less meaningful for asset-light (software).",
    },
    "PEG": {
        "short": "P/E adjusted for growth. Below 1 = bargain.",
        "long": "Price/Earnings to Growth. PEG = P/E ÷ growth rate. <1 = cheap relative to growth, "
                ">2 = expensive relative to growth. Lynch's favorite metric.",
    },
    "EV/EBITDA": {
        "short": "Enterprise value vs. earnings before interest/tax/depreciation.",
        "long": "Captures debt + market cap, divided by operating earnings. Useful across capital "
                "structures. <10 generally cheap, >15 expensive (sector-dependent).",
    },
    "ROE": {
        "short": "Return on Equity — how efficiently the company earns from shareholder money.",
        "long": "Net income ÷ shareholder equity. >15% = strong. >20% = excellent. <10% = below avg.",
    },
    "ROIC": {
        "short": "Return on Invested Capital — true profitability of the business.",
        "long": "How much profit is generated per dollar of total capital (debt + equity). "
                ">15% sustained = wide moat. <10% means the company isn't beating its cost of capital.",
    },
    "FCF Yield": {
        "short": "Free cash flow as a % of market cap. The 'real' earnings yield.",
        "long": "Free cash flow ÷ market cap. >5% = generous, >8% = potential value play. "
                "Negative = the business is consuming cash (red flag in mature firms).",
    },
    "Debt/Equity": {
        "short": "How leveraged the company is.",
        "long": "Total debt divided by shareholder equity. <0.5 = lightly levered, "
                "0.5-1.0 = moderate, >1.5 = heavily levered (more risk in downturns).",
    },
    "Gross Margin": {
        "short": "Profit after direct costs, before overhead.",
        "long": "Revenue minus cost of goods, divided by revenue. >50% = high-quality business, "
                "<20% = thin margins (commodity-like).",
    },
    "Operating Margin": {
        "short": "Profit after all operating expenses but before tax/interest.",
        "long": "Operating income ÷ revenue. >20% = excellent operations, <10% = thin.",
    },
    "RSI": {
        "short": "Momentum gauge from 0-100. Above 70 = over-bought, below 30 = over-sold.",
        "long": "Relative Strength Index over 14 periods. Doesn't predict reversals but flags extremes.",
    },
    "ADX": {
        "short": "Trend strength. Above 25 = strong trend, below 20 = sideways.",
        "long": "Average Directional Index. Tells you HOW strong a trend is (regardless of direction). "
                ">25 = trend-following strategies work. <20 = chop, mean-reversion or stay out.",
    },
    "MACD": {
        "short": "Momentum signal. Crossing above zero = bullish, below = bearish.",
        "long": "Moving Average Convergence Divergence. Hist > 0 + rising = bullish momentum. "
                "Hist < 0 + falling = bearish momentum.",
    },
    "ATR": {
        "short": "Average True Range — typical daily price movement size.",
        "long": "ATR(14) = average daily price range. Used for setting stop-losses (typically 2-3× ATR).",
    },
    "VIX": {
        "short": "Fear gauge. Below 15 = calm, above 30 = panic.",
        "long": "Implied 30-day volatility on S&P 500 options. <15 = complacency, 15-22 = normal, "
                "22-30 = elevated fear, >30 = panic. Mean-reverts. Inverse of SPY (~ -0.80 corr).",
    },
    "Yield Curve (10Y-2Y)": {
        "short": "Difference between 10-year and 2-year Treasury yields.",
        "long": "Healthy curve = positive (long rates higher than short). Inverted (negative) = "
                "recession signal — has preceded every US recession since 1955 with 6-18 month lead.",
    },
    "Beta": {
        "short": "How much the stock moves vs. the market. 1 = same as market.",
        "long": "Beta of 1.5 = stock moves 1.5× the S&P 500. Beta of 0.5 = stock moves half as much. "
                "Negative beta (rare) = inverse correlation.",
    },
    "Stage 1": {
        "short": "Basing — sideways action. Wait, don't buy yet.",
        "long": "After a downtrend or as accumulation begins. Volatility contracts. "
                "Watch for breakout above 30-week MA on volume.",
    },
    "Stage 2": {
        "short": "Advancing — uptrend. The only stage to buy.",
        "long": "Price above rising 30-week MA. Higher highs, higher lows. Volume on rallies. "
                "Position-trader sweet spot. Pullbacks to 10-week MA are entries.",
    },
    "Stage 3": {
        "short": "Topping — uptrend exhausting. Tighten stops, don't add.",
        "long": "Sideways above flattening 30-week MA. Distribution: volume on declines exceeds rallies. "
                "Reduce size. Don't initiate new longs.",
    },
    "Stage 4": {
        "short": "Declining — downtrend. Don't touch (or short with discipline).",
        "long": "Price below falling 30-week MA. Lower lows. The 'no touch' zone for longs.",
    },
    "Composite Score": {
        "short": "Single -100 to +100 number combining trend, momentum, quality, value, earnings.",
        "long": "Above +50 = strong buy candidate. +25 to +50 = buy. -25 to +25 = neutral. "
                "Below -25 = avoid or short. Best when paired with stage analysis.",
    },
    "Leverage Gate": {
        "short": "Whether 3× ETFs are safe to hold today (🟢/🟡/🔴).",
        "long": "Composite of VIX, yield curve, credit spreads, broad trend. GREEN = full size on 3× OK. "
                "YELLOW = half size or 1× preferred. RED = no leverage; cash or hedges only.",
    },
    "Decay (Leveraged ETFs)": {
        "short": "Loss from daily rebalancing — eats returns in choppy markets.",
        "long": "3× ETFs reset daily. In a flat-but-volatile year, the 3× version can lose value "
                "while the underlying breaks even. Worse in choppy markets, less in directional ones.",
    },
}


# ============================================================
# Per-metric interpreters: (verdict_label, plain_english_text)
# ============================================================
def interpret_pe(pe: float | None) -> tuple[str, str]:
    if pe is None or pe <= 0:
        return ("⚠ Unprofitable",
                "The company isn't making money on a trailing basis. Common in early-growth firms; "
                "red flag in mature ones.")
    if pe < 12:   return ("🟢 Cheap",
                          f"At P/E {pe:.1f}, expectations are low. Could be a value play — or a value "
                          "trap if earnings are about to fall. Check if the business is structurally healthy.")
    if pe < 18:   return ("🟢 Fair",
                          f"P/E {pe:.1f} is roughly average for a mature business. Reasonable price.")
    if pe < 25:   return ("🟡 Slight premium",
                          f"P/E {pe:.1f} sits modestly above average. Justified only if growth is solid.")
    if pe < 40:   return ("🟧 Expensive",
                          f"P/E {pe:.1f} requires above-average growth to make sense. Any disappointment hurts.")
    return ("🔴 Priced for perfection",
            f"P/E {pe:.1f} prices in extreme growth. The bar to clear is very high — "
            "small misses can lead to outsized declines.")


def interpret_peg(peg: float | None) -> tuple[str, str]:
    if peg is None or peg <= 0:
        return ("—", "Not enough growth data to compute PEG.")
    if peg < 1.0:  return ("🟢 Cheap relative to growth",
                           f"PEG {peg:.2f}. Lynch would call this a bargain — earnings growth is "
                           "outpacing the multiple investors are willing to pay.")
    if peg < 1.5:  return ("🟩 Reasonable",
                           f"PEG {peg:.2f}. Growth roughly justifies the price.")
    if peg < 2.5:  return ("🟧 Premium",
                           f"PEG {peg:.2f}. You're paying up for growth. Need conviction it persists.")
    return ("🔴 Expensive vs growth",
            f"PEG {peg:.2f}. The price is running ahead of even optimistic growth assumptions.")


def interpret_roe(roe: float | None) -> tuple[str, str]:
    if roe is None: return ("—", "")
    pct = roe * 100 if abs(roe) < 1 else roe
    if pct < 0:    return ("🔴 Negative",  f"ROE {pct:.1f}%. Company is destroying shareholder value.")
    if pct < 8:    return ("🟧 Below avg",  f"ROE {pct:.1f}%. Below typical S&P 500 norms (~14%).")
    if pct < 15:   return ("🟡 Average",    f"ROE {pct:.1f}%. In line with the market average.")
    if pct < 25:   return ("🟢 Strong",     f"ROE {pct:.1f}%. Solid capital efficiency.")
    return ("🟢🟢 Exceptional", f"ROE {pct:.1f}%. Top-tier — usually associated with wide-moat businesses.")


def interpret_fcf_yield(fcfy: float | None) -> tuple[str, str]:
    if fcfy is None: return ("—", "")
    pct = fcfy * 100 if abs(fcfy) < 1 else fcfy
    if pct < 0:    return ("🔴 Negative",   f"FCF yield {pct:.1f}%. Company is burning cash.")
    if pct < 2:    return ("🟧 Tight",      f"FCF yield {pct:.1f}%. Generates little free cash relative to price.")
    if pct < 5:    return ("🟡 Decent",     f"FCF yield {pct:.1f}%. Reasonable cash generation.")
    if pct < 8:    return ("🟢 Generous",   f"FCF yield {pct:.1f}%. Strong cash production.")
    return ("🟢🟢 Cheap on cash", f"FCF yield {pct:.1f}%. Deep-value cash machine.")


def interpret_debt_equity(de: float | None) -> tuple[str, str]:
    if de is None: return ("—", "")
    d = de if de < 10 else de / 100
    if d < 0.3:    return ("🟢 Lightly leveraged", f"D/E {d:.2f}. Conservative balance sheet.")
    if d < 0.7:    return ("🟢 Moderate",          f"D/E {d:.2f}. Healthy use of debt.")
    if d < 1.5:    return ("🟡 Leveraged",         f"D/E {d:.2f}. Above average — watch interest coverage.")
    return ("🔴 Highly leveraged",
            f"D/E {d:.2f}. Vulnerable in a downturn or rising-rate environment.")


def interpret_rsi(rsi: float | None) -> tuple[str, str]:
    if rsi is None: return ("—", "")
    if rsi > 80:   return ("🔴 Extreme over-bought", f"RSI {rsi:.0f}. Risk of pullback elevated. Don't chase.")
    if rsi > 70:   return ("🟧 Over-bought",         f"RSI {rsi:.0f}. Strong momentum but stretched.")
    if rsi > 50:   return ("🟢 Bullish momentum",    f"RSI {rsi:.0f}. Buyers in control.")
    if rsi > 30:   return ("🟡 Bearish momentum",    f"RSI {rsi:.0f}. Sellers in control.")
    if rsi > 20:   return ("🟧 Over-sold",           f"RSI {rsi:.0f}. Bounce possible — but trends can stay over-sold.")
    return ("🔴 Extreme over-sold", f"RSI {rsi:.0f}. Heavy selling — wait for stabilization before catching the knife.")


def interpret_adx(adx: float | None) -> tuple[str, str]:
    if adx is None: return ("—", "")
    if adx < 20:   return ("🟡 Sideways",        f"ADX {adx:.0f}. No real trend — chop. Trend systems will fail here.")
    if adx < 25:   return ("🟧 Weak trend",      f"ADX {adx:.0f}. Trend forming but not yet strong.")
    if adx < 40:   return ("🟢 Strong trend",    f"ADX {adx:.0f}. Trend systems will work — ride it.")
    return ("🟢🟢 Very strong trend", f"ADX {adx:.0f}. Powerful trend in motion.")


def interpret_vix(vix: float | None) -> tuple[str, str]:
    if vix is None: return ("—", "")
    if vix < 12:   return ("🔵 Extreme calm",   f"VIX {vix:.1f}. Complacency. Forward returns historically below average — "
                                                "don't FOMO. Hold dry powder.")
    if vix < 15:   return ("🟢 Calm",          f"VIX {vix:.1f}. Below historical median — markets are relaxed.")
    if vix < 22:   return ("🟡 Normal",        f"VIX {vix:.1f}. Average volatility regime.")
    if vix < 30:   return ("🟧 Elevated fear", f"VIX {vix:.1f}. Caution mode — but also where forward returns improve.")
    if vix < 40:   return ("🔴 Panic",         f"VIX {vix:.1f}. Historically a buying opportunity for patient capital.")
    return ("⚫ Capitulation",
            f"VIX {vix:.1f}. Extreme. Historically the BEST time to deploy fresh cash if your time horizon is 6+ months.")


def interpret_yield_curve(spread: float | None) -> tuple[str, str]:
    if spread is None: return ("—", "")
    if spread < -0.5:  return ("🔴 Deeply inverted",
                                f"10Y-2Y at {spread:+.2f}%. Strongest recession warning. Defensive posture warranted.")
    if spread < 0:     return ("🟧 Inverted",
                                f"10Y-2Y at {spread:+.2f}%. Historic recession lead. Lead time 6-18 months.")
    if spread < 0.5:   return ("🟡 Flat",
                                f"10Y-2Y at {spread:+.2f}%. Late-cycle territory.")
    if spread < 1.5:   return ("🟢 Healthy",
                                f"10Y-2Y at {spread:+.2f}%. Normal yield curve.")
    return ("🟢🟢 Steep",
            f"10Y-2Y at {spread:+.2f}%. Classic early-cycle / re-acceleration shape.")


# ============================================================
# Composite narrative — used on Stage Engine and Stock Deep Dive
# ============================================================
def stock_narrative(name: str, sector: str, stage: str, composite: float,
                    factor_scores: dict, info: dict | None = None) -> str:
    """Return a 2-3 sentence plain-English summary of the stock."""
    parts = [f"**{name}** is a {sector or 'company'}."]

    stage_lookup = {
        "STAGE 1": "currently **basing** — sideways action with no real trend yet. The classic "
                   "Weinstein rule says wait for a breakout above the 30-week moving average on volume "
                   "before initiating longs.",
        "STAGE 2": "in a **confirmed uptrend** — Stage 2, the only stage where you should be considering "
                   "fresh long positions. The trend is your friend until it breaks.",
        "STAGE 3": "in a **topping phase** — the uptrend is exhausting. Tighten stops on existing "
                   "positions and don't initiate new longs here.",
        "STAGE 4": "in a **downtrend** — Stage 4, the 'no touch' zone for longs. Either avoid entirely "
                   "or short with strict risk management.",
    }
    parts.append(f"It is {stage_lookup.get(stage, 'in an unclear stage')}")

    if composite >= 50:
        parts.append("The 5-factor composite score is **strongly positive** — trend, momentum, "
                     "quality, value, and earnings are all aligned bullishly. High-conviction setup "
                     "if other layers (macro, sector, valuation) agree.")
    elif composite >= 25:
        parts.append("The 5-factor composite is **moderately positive** — most factors lean bullish "
                     "but conviction is mixed. Wait for stronger alignment or tighter entry.")
    elif composite > -25:
        parts.append("The composite is **neutral** — factors are mixed. Better setups exist; pass.")
    elif composite > -50:
        parts.append("The composite is **moderately negative** — avoid as a long. Better candidates exist.")
    else:
        parts.append("The composite is **strongly negative** — avoid longs. Short candidate only "
                     "with strict discipline and a confirmed Stage 4 setup.")

    return " ".join(parts)


# ============================================================
# Verdict card renderer (used by pages)
# ============================================================
def verdict_color(verdict: str) -> str:
    v = verdict.upper()
    if any(x in v for x in ("STRONG BUY", "BUY", "UNDERVALUED", "GREEN", "RISK_ON", "STAGE 2")):
        return "#22C55E"
    if any(x in v for x in ("AVOID", "SELL", "REDUCE", "STRONG SHORT", "OVERVALUED",
                            "RED", "RISK_OFF", "STAGE 4", "PANIC")):
        return "#EF4444"
    if any(x in v for x in ("YELLOW", "NEUTRAL", "FAIR", "STAGE 3", "STAGE 1", "WAIT", "HOLD")):
        return "#FFD700"
    return "#8a93a6"


def render_decision_card(st_module, verdict: str, plain_english: str,
                         actions: list[str] | None = None):
    """Render a top-of-page decision card."""
    color = verdict_color(verdict)
    st_module.markdown(f"""
    <div style="background:#11182A;padding:1.2rem;border-left:5px solid {color};border-radius:4px;margin-bottom:0.8rem">
      <div style="color:#8a93a6;font-size:0.8rem;text-transform:uppercase;letter-spacing:0.1rem">System verdict</div>
      <div style="font-size:1.8rem;color:{color};font-weight:bold">{verdict}</div>
      <div style="color:#bcc3d6;margin-top:0.4rem;line-height:1.5">{plain_english}</div>
    </div>
    """, unsafe_allow_html=True)
    if actions:
        bullets = "\n".join(f"- {a}" for a in actions)
        st_module.markdown(f"**Suggested next steps:**\n{bullets}")


def help_box(st_module, title: str, body: str):
    """Collapsible plain-English explainer at top of a page."""
    with st_module.expander(f"💡 {title}", expanded=False):
        st_module.markdown(body)


# ============================================================
# Risk-on / Defensive — the conceptual foundation
# ============================================================
RISK_REGIMES = {
    "risk_on": {
        "label": "🟢 RISK-ON",
        "tagline": "Investors are confident. Money chases growth.",
        "what_it_means": (
            "Investors believe the future is better than the past. They're willing to accept volatility "
            "and uncertainty in exchange for higher expected returns. Money flows OUT of safe assets "
            "(bonds, cash, defensives) and INTO higher-octane stuff (growth tech, small caps, emerging "
            "markets, crypto, leveraged ETFs)."
        ),
        "tells": [
            "VIX is low (<18)",
            "Tech, semis, small caps are leading",
            "Defensives (staples, utilities, healthcare) lag the market",
            "High-yield credit spreads are tight (<3.5%)",
            "10Y yield rising on growth (not inflation panic)",
            "Bitcoin / Ethereum / crypto rallying alongside equities",
        ],
        "what_to_do": [
            "Increase exposure to growth and cyclical sectors",
            "Leveraged ETFs (TQQQ, SOXL) are eligible at full size",
            "Loosen stops slightly — trends tend to extend",
            "Add to small caps and emerging markets",
        ],
    },
    "defensive": {
        "label": "🔴 DEFENSIVE / RISK-OFF",
        "tagline": "Investors are nervous. Money seeks safety.",
        "what_it_means": (
            "Investors are pricing in uncertainty — recession risk, geopolitical tension, policy "
            "concerns, overvaluation. Capital rotates OUT of risk assets and INTO things people need "
            "regardless of the economy: utilities (everyone needs power), consumer staples (food, "
            "soap, cigarettes), healthcare (medication, hospitals), and Treasury bonds. The 'flight to "
            "safety' trade."
        ),
        "tells": [
            "VIX is elevated (>22, especially >30)",
            "Defensives (XLP, XLU, XLV) are leading the market",
            "Cyclicals and tech are lagging",
            "High-yield credit spreads widening",
            "Yield curve flat or inverted",
            "Dollar (DXY) and gold both bid simultaneously",
            "Bitcoin diverging negatively from equities",
        ],
        "what_to_do": [
            "Reduce equity exposure — raise cash",
            "Avoid leveraged ETFs entirely (gate is RED)",
            "Tighten stops on existing longs",
            "If holding longs, rotate from cyclicals to defensives",
            "Inverse hedges (SQQQ, SOXS) usable with discipline",
            "Wait for VIX to peak then mean-revert before re-engaging",
        ],
    },
}


# ============================================================
# Sector cheat sheet — what each SPDR sector represents and why
# ============================================================
SECTORS_DETAILED = {
    "XLK": {
        "name": "Technology",
        "type": "🟢 Risk-on / Growth",
        "examples": "Apple, Microsoft, Nvidia, Broadcom, Salesforce",
        "what_it_does": "Software, semiconductors, hardware, IT services.",
        "behavior": (
            "**Long-duration**: most of the cash flow is years in the future, so prices are highly "
            "sensitive to interest rates (rising rates compress valuations). Leads bull markets when "
            "rates are falling and risk appetite is healthy. Gets crushed in 'risk-off' rotations."
        ),
        "leads_when": "Rates falling/stable, growth confidence high, animal spirits",
        "lags_when": "Rates rising rapidly, recession fears, tech-specific stress",
    },
    "XLY": {
        "name": "Consumer Discretionary",
        "type": "🟢 Risk-on / Cyclical",
        "examples": "Amazon, Tesla, Home Depot, McDonald's, Nike",
        "what_it_does": "Things people buy when they have disposable income — cars, vacations, fashion, restaurants, online shopping.",
        "behavior": (
            "**Cyclical**: tracks the consumer's confidence and wallet. Leads when the economy is "
            "expanding and unemployment is low. Suffers fast in slowdowns because these are the first "
            "purchases consumers cut."
        ),
        "leads_when": "Consumer confidence high, wages rising, employment strong",
        "lags_when": "Recession fears, inflation squeezing real incomes, layoffs",
    },
    "XLC": {
        "name": "Communication Services",
        "type": "🟢 Risk-on / Mixed",
        "examples": "Meta, Google (Alphabet), Netflix, Disney, Verizon, AT&T",
        "what_it_does": "Internet platforms, social media, streaming, telecom. Bifurcated sector.",
        "behavior": (
            "**Mixed**: dominated by mega-cap tech (Meta, Google) so behaves more like tech. "
            "Old-telecom names (Verizon, AT&T) inside are more defensive but small weight."
        ),
        "leads_when": "Same as XLK — risk-on, growth confidence",
        "lags_when": "Same as XLK — rates rising, recession fears",
    },
    "XLF": {
        "name": "Financials",
        "type": "🟡 Cyclical / Rate-sensitive",
        "examples": "JPMorgan, Bank of America, Berkshire, BlackRock, Visa",
        "what_it_does": "Banks, insurers, asset managers, payment networks, exchanges.",
        "behavior": (
            "**Cyclical AND rate-sensitive**: banks make money on the spread between deposits and "
            "loans. Higher rates can be GOOD (wider net interest margin) UNTIL recession risk hits "
            "credit quality. The classic late-cycle dilemma."
        ),
        "leads_when": "Rates rising on growth, steepening yield curve, credit healthy",
        "lags_when": "Recession fears, inverted yield curve, credit stress, bank failures",
    },
    "XLV": {
        "name": "Health Care",
        "type": "🔴 Defensive",
        "examples": "Eli Lilly, J&J, UnitedHealth, Pfizer, Merck, Abbott",
        "what_it_does": "Pharma, biotech, medical devices, hospitals, insurers, lab services.",
        "behavior": (
            "**Defensive**: people need healthcare in good times and bad. Demand is largely inelastic. "
            "Less affected by economic cycles. Often outperforms in bear markets and risk-off periods."
        ),
        "leads_when": "Risk-off, recession fears, late cycle",
        "lags_when": "Risk-on rallies, growth-favoring environments",
    },
    "XLI": {
        "name": "Industrials",
        "type": "🟡 Cyclical",
        "examples": "Boeing, Caterpillar, Honeywell, GE, Lockheed Martin, UPS",
        "what_it_does": "Manufacturing, aerospace, construction equipment, transportation, defense.",
        "behavior": (
            "**Cyclical**: tied directly to economic activity. Construction, factory orders, freight "
            "volumes — all rise with GDP and contract in slowdowns. Defense names provide some "
            "stability via government contracts."
        ),
        "leads_when": "Economic expansion, manufacturing PMI rising, capex cycles, infrastructure spending",
        "lags_when": "Manufacturing recession, weak global demand, freight slowdowns",
    },
    "XLP": {
        "name": "Consumer Staples",
        "type": "🔴 Defensive",
        "examples": "Costco, Walmart, P&G, Coca-Cola, PepsiCo, Philip Morris",
        "what_it_does": "Things people buy regardless of the economy — food, drinks, cleaning products, basic toiletries, tobacco.",
        "behavior": (
            "**Classic defensive**: demand is inelastic. People still buy soap and pasta in a recession. "
            "Steady cash flows, often pay dividends. Outperforms in bear markets, lags in bull markets."
        ),
        "leads_when": "Risk-off, late cycle, recession, inflation hedging (some pricing power)",
        "lags_when": "Risk-on rallies, growth phases, low-volatility environments",
    },
    "XLE": {
        "name": "Energy",
        "type": "🟡 Commodity / Cyclical",
        "examples": "ExxonMobil, Chevron, ConocoPhillips, Schlumberger",
        "what_it_does": "Oil & gas — exploration, production, refining, services, pipelines.",
        "behavior": (
            "**Commodity-driven**: tracks oil and natural gas prices, which tie to global demand "
            "(growth-cyclical) AND geopolitical events (uncertainty premium). Inflation hedge but "
            "volatile."
        ),
        "leads_when": "Energy prices rising, supply tight, geopolitical risk, inflation",
        "lags_when": "Oil prices falling, demand destruction, energy transition narrative",
    },
    "XLU": {
        "name": "Utilities",
        "type": "🔴 Defensive / Bond-proxy",
        "examples": "NextEra Energy, Duke Energy, Southern Company, Dominion Energy",
        "what_it_does": "Electric, gas, water utilities. Regulated monopolies.",
        "behavior": (
            "**Bond-proxy defensive**: regulated returns, predictable cash flows, high dividends. "
            "Rate-sensitive — when bond yields rise, utility yields look less attractive. Outperforms "
            "in flight-to-safety AND when rates fall."
        ),
        "leads_when": "Risk-off, falling rates, recession fears",
        "lags_when": "Rates rising, growth-favoring environments",
    },
    "XLB": {
        "name": "Materials",
        "type": "🟡 Cyclical / Commodity",
        "examples": "Linde, Sherwin-Williams, Freeport-McMoRan, Newmont (gold mining), Dow",
        "what_it_does": "Chemicals, mining, metals, paper, packaging.",
        "behavior": (
            "**Cyclical with commodity exposure**: tied to construction, manufacturing, and global "
            "demand. Gold miners (within materials) can act as inflation hedge / defensive — splits "
            "the sector's behavior."
        ),
        "leads_when": "Global growth, infrastructure spending, weaker dollar, commodities rallying",
        "lags_when": "Slowdowns, strong dollar, falling commodity prices",
    },
    "XLRE": {
        "name": "Real Estate",
        "type": "🔴 Defensive / Rate-sensitive",
        "examples": "American Tower, Prologis, Welltower, Equinix",
        "what_it_does": "REITs — commercial real estate, towers, data centers, healthcare facilities, industrial.",
        "behavior": (
            "**Defensive AND rate-sensitive**: real estate provides steady rental income (defensive) "
            "but is highly sensitive to interest rates (mortgage costs, cap rates). Crushed when rates "
            "spike, leads when rates fall."
        ),
        "leads_when": "Rates falling/stable, defensive rotations, search for yield",
        "lags_when": "Rates rising rapidly, recession threatening rents",
    },
}


def render_sector_cheatsheet(st_module):
    """Render a Risk-On / Defensive / Cyclical sector cheatsheet table."""
    rows = []
    for tk, info in SECTORS_DETAILED.items():
        rows.append({
            "Sector":     f"{tk}",
            "Name":       info["name"],
            "Risk type":  info["type"],
            "Examples":   info["examples"],
            "Leads when": info["leads_when"],
        })
    import pandas as pd
    df = pd.DataFrame(rows)
    st_module.dataframe(df, use_container_width=True, hide_index=True)


def render_risk_regime_explainer(st_module):
    """Render a side-by-side risk-on vs defensive explainer."""
    col1, col2 = st_module.columns(2)
    for col, regime_key in zip([col1, col2], ["risk_on", "defensive"]):
        regime = RISK_REGIMES[regime_key]
        color = "#22C55E" if regime_key == "risk_on" else "#EF4444"
        with col:
            st_module.markdown(f"""
<div style="background:#11182A;padding:1rem;border-left:4px solid {color};border-radius:4px">
  <div style="font-size:1.3rem;font-weight:bold;color:{color}">{regime['label']}</div>
  <div style="color:#bcc3d6;font-size:0.95rem;font-style:italic;margin:0.4rem 0">{regime['tagline']}</div>
  <div style="color:#E6E8EE;margin-top:0.5rem;line-height:1.5">{regime['what_it_means']}</div>
</div>""", unsafe_allow_html=True)
            st_module.markdown(f"**🔍 How to spot it ({regime['label'].split()[1] if len(regime['label'].split()) > 1 else 'It'})**")
            for tell in regime["tells"]:
                st_module.markdown(f"- {tell}")
            st_module.markdown("**🎯 What to do**")
            for action in regime["what_to_do"]:
                st_module.markdown(f"- {action}")
