#!/usr/bin/env python3
"""AI Research Team — TradingAgents-style analyst debate.

Pipeline mirrors TradingAgents (analysts -> bull/bear debate -> risk team ->
portfolio manager), but the analysts are RULE-BASED on the user's SMC
Market-Mechanics playbook (free, backtested) instead of paid LLM calls.
Swap `analyst_verdicts` for LLM-backed analysts (Ollama/Groq) when desired —
see README.

Each analyst returns {stance: bull|bear|neutral, confidence: 0-1, reasons[]}.
Portfolio Manager combines them into BUY / SELL / HOLD.
"""
import math


def _ema(vals, n):
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _swings(closes, lookback=20):
    """Recent swing high/low."""
    seg = closes[-lookback:]
    return max(seg), min(seg)


def trend_analyst(candles):
    """4H-style bias: EMA50 vs EMA200 + BOS detection on closes."""
    closes = [c["c"] for c in candles]
    if len(closes) < 210:
        return {"analyst": "Trend", "stance": "neutral", "confidence": 0.3,
                "reasons": ["not enough history for 4H bias"]}
    e50 = _ema(closes[-60:], 50)
    e200 = _ema(closes, 200)
    last = closes[-1]
    hi, lo = _swings(closes, 30)
    reasons, score = [], 0.0
    if last > e50 > e200:
        score += 0.5
        reasons.append("price above EMA50 above EMA200 — uptrend structure")
    elif last < e50 < e200:
        score -= 0.5
        reasons.append("price below EMA50 below EMA200 — downtrend structure")
    # BOS: close beyond prior 30-bar swing
    if last > hi * 1.001:
        score += 0.3
        reasons.append("bullish BOS — closed above prior swing high")
    elif last < lo * 0.999:
        score -= 0.3
        reasons.append("bearish BOS — closed below prior swing low")
    # premium/discount of recent range
    pos = (last - lo) / (hi - lo + 1e-9)
    if pos > 0.7:
        score -= 0.15
        reasons.append("premium zone — long entries less attractive")
    elif pos < 0.3:
        score += 0.15
        reasons.append("discount zone — long entries attractive")
    stance = "bull" if score > 0.15 else "bear" if score < -0.15 else "neutral"
    return {"analyst": "Trend", "stance": stance,
            "confidence": round(min(0.9, abs(score) + 0.3), 2), "reasons": reasons}


def liquidity_analyst(candles):
    """Sweep + displacement: wick beyond swing extreme then reclaim."""
    if len(candles) < 40:
        return {"analyst": "Liquidity", "stance": "neutral", "confidence": 0.3,
                "reasons": ["not enough history"]}
    closes = [c["c"] for c in candles]
    hi, lo = _swings(closes[:-5], 25)
    last5 = candles[-5:]
    reasons, score = [], 0.0
    for c in last5:
        swept_high = c["h"] > hi * 1.001 and c["c"] < hi
        swept_low = c["l"] < lo * 0.999 and c["c"] > lo
        if swept_high:
            score -= 0.35
            reasons.append("sell-side sweep: wicked above highs, closed back — bearish")
            break
        if swept_low:
            score += 0.35
            reasons.append("buy-side sweep: wicked below lows, closed back — bullish")
            break
    # displacement: last 3-bar range vs average
    ranges = [c["h"] - c["l"] for c in candles[-20:]]
    avg = sum(ranges) / len(ranges)
    if ranges[-1] > avg * 1.8:
        reasons.append("displacement candle — institutional footprint")
        score += 0.1 if closes[-1] > closes[-2] else -0.1
    if not reasons:
        reasons.append("no fresh sweep — waiting for liquidity raid")
    stance = "bull" if score > 0.15 else "bear" if score < -0.15 else "neutral"
    return {"analyst": "Liquidity", "stance": stance,
            "confidence": round(min(0.85, abs(score) + 0.35), 2), "reasons": reasons}


def kronos_analyst(forecast):
    """Kronos foundation-model verdict from sampled forecast paths."""
    if not forecast or forecast.get("status") != "ready":
        return {"analyst": "Kronos AI", "stance": "neutral", "confidence": 0.3,
                "reasons": ["forecast still computing"]}
    r = forecast["result"]
    p_up, mv = r["p_up"], r["exp_move_pct"]
    if p_up >= 0.65:
        stance, conf = "bull", p_up
        reasons = [f"Kronos: {int(p_up*100)}% of paths end higher"]
    elif p_up <= 0.35:
        stance, conf = "bear", 1 - p_up
        reasons = [f"Kronos: {int((1-p_up)*100)}% of paths end lower"]
    else:
        stance, conf = "neutral", 0.5
        reasons = ["Kronos: paths split — no edge"]
    reasons.append(f"expected 24h move {mv:+.2f}% (median path)")
    return {"analyst": "Kronos AI", "stance": stance,
            "confidence": round(conf, 2), "reasons": reasons}


def risk_manager(candles, stance_votes):
    """1% risk guardrails from the playbook."""
    closes = [c["c"] for c in candles]
    atr = sum(c["h"] - c["l"] for c in candles[-14:]) / 14
    last = closes[-1]
    bulls = sum(1 for s in stance_votes if s == "bull")
    bears = sum(1 for s in stance_votes if s == "bear")
    if bulls >= 2:
        sl = last - atr * 1.5
        tp = last + atr * 3.0
        bias = "long"
    elif bears >= 2:
        sl = last + atr * 1.5
        tp = last - atr * 3.0
        bias = "short"
    else:
        return {"analyst": "Risk", "stance": "neutral", "confidence": 0.5,
                "reasons": ["no analyst consensus — stand aside"],
                "risk_pct": 1.0, "sl": None, "tp": None}
    rr = abs(tp - last) / (abs(sl - last) + 1e-9)
    return {"analyst": "Risk", "stance": "bull" if bias == "long" else "bear",
            "confidence": 0.7,
            "reasons": [f"1% risk plan — SL {sl:,.2f}, TP {tp:,.2f}, R:R 1:{rr:.1f}"],
            "risk_pct": 1.0, "sl": round(sl, 2), "tp": round(tp, 2)}


def debate(symbol, candles, forecast):
    """Full analyst debate -> portfolio verdict."""
    t = trend_analyst(candles)
    l = liquidity_analyst(candles)
    k = kronos_analyst(forecast)
    votes = [t["stance"], l["stance"], k["stance"]]
    r = risk_manager(candles, votes)
    bulls = sum(1 for s in votes if s == "bull")
    bears = sum(1 for s in votes if s == "bear")
    conf = round((t["confidence"] + l["confidence"] + k["confidence"]) / 3, 2)
    if bulls >= 2:
        verdict, note = "BUY", f"{bulls}/3 analysts bullish"
    elif bears >= 2:
        verdict, note = "SELL", f"{bears}/3 analysts bearish"
    else:
        verdict, note = "HOLD", "analysts split — no trade"
    return {
        "symbol": symbol.upper(),
        "verdict": verdict,
        "confidence": conf,
        "note": note,
        "analysts": [t, l, k, r],
    }
