"""Multi-factor scoring and recommendation ratings."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


RATINGS = [
    (85, "Strong Buy"),
    (70, "Buy"),
    (60, "Accumulate"),
    (45, "Hold"),
    (35, "Reduce"),
    (20, "Sell"),
    (0, "Strong Sell"),
]


def rating_from_score(score: float) -> str:
    for threshold, label in RATINGS:
        if score >= threshold:
            return label
    return "Strong Sell"


def momentum_score(tech: Dict[str, Any]) -> Optional[float]:
    if not tech or tech.get("status") == "unavailable":
        return None
    base = 50.0
    m1 = tech.get("momentum_1m_pct") or 0
    m3 = tech.get("momentum_3m_pct") or 0
    base += np.clip(m1 * 1.2, -20, 25)
    base += np.clip(m3 * 0.5, -15, 15)
    rsi = tech.get("rsi") or 50
    if 50 <= rsi <= 65:
        base += 5
    elif rsi > 75:
        base -= 8
    elif rsi < 30:
        base += 3
    return float(np.clip(base, 0, 100))


def sentiment_score(tech: Dict[str, Any], fund: Dict[str, Any], info: Dict[str, Any]) -> Optional[float]:
    """Proxy sentiment from price action + analyst key; not social scrapes."""
    if not tech or tech.get("technical_score") is None:
        return None
    s = 50.0
    s += (tech.get("technical_score", 50) - 50) * 0.4
    if fund and fund.get("fundamental_score") is not None:
        s += (fund["fundamental_score"] - 50) * 0.2
    rec = (info or {}).get("recommendationKey")
    if rec in ("buy", "strong_buy"):
        s += 10
    elif rec in ("sell", "strong_sell"):
        s -= 10
    elif rec == "hold":
        s += 0
    # Volume confirmation
    vr = tech.get("volume_ratio")
    if vr and vr > 1.5 and (tech.get("momentum_1m_pct") or 0) > 0:
        s += 5
    return float(np.clip(s, 0, 100))


def risk_score(tech: Dict[str, Any], fund: Dict[str, Any], info: Dict[str, Any]) -> Optional[float]:
    """Higher = more risk."""
    if not tech or tech.get("status") == "unavailable":
        return None
    r = 40.0
    atr = tech.get("atr")
    last = tech.get("last")
    if atr and last:
        vol = atr / last * 100
        r += np.clip(vol * 3, 0, 25)
    beta = (info or {}).get("beta")
    if beta is not None:
        r += np.clip((beta - 1) * 15, -10, 20)
    de = (fund or {}).get("metrics", {}).get("debt_to_equity_norm")
    if de is not None and de > 1.5:
        r += 10
    if tech.get("trend") == "Downtrend":
        r += 8
    return float(np.clip(r, 0, 100))


def overall_conviction(
    technical: Optional[float],
    fundamental: Optional[float],
    momentum: Optional[float],
    valuation: Optional[float],
    sentiment: Optional[float],
    risk: Optional[float],
) -> Optional[float]:
    parts = []
    weights = []
    for val, w in [
        (technical, 0.25),
        (fundamental, 0.20),
        (momentum, 0.20),
        (valuation, 0.15),
        (sentiment, 0.10),
        # invert risk: low risk boosts conviction
        ((100 - risk) if risk is not None else None, 0.10),
    ]:
        if val is not None:
            parts.append(val * w)
            weights.append(w)
    if not parts:
        return None
    return float(np.clip(sum(parts) / sum(weights), 0, 100))


def build_stock_scorecard(
    symbol: str,
    tech: Dict[str, Any],
    fund: Dict[str, Any],
    info: Dict[str, Any],
) -> Dict[str, Any]:
    t_score = tech.get("technical_score") if tech else None
    f_score = fund.get("fundamental_score") if fund else None
    v_score = fund.get("valuation_score") if fund else None
    m_score = momentum_score(tech)
    s_score = sentiment_score(tech, fund, info)
    r_score = risk_score(tech, fund, info)
    overall = overall_conviction(t_score, f_score, m_score, v_score, s_score, r_score)

    rating = rating_from_score(overall) if overall is not None else "Hold"
    confidence = None
    if overall is not None:
        available = sum(
            1
            for x in [t_score, f_score, m_score, v_score, s_score, r_score]
            if x is not None
        )
        confidence = round(min(95, 40 + available * 8 + abs(overall - 50) * 0.3), 1)

    evidence: List[str] = []
    if tech and tech.get("ai_summary"):
        evidence.append(tech["ai_summary"])
    if fund and fund.get("evidence"):
        evidence.extend(fund["evidence"][:3])

    risks = []
    if r_score is not None and r_score >= 60:
        risks.append("Elevated volatility / beta risk")
    if tech and tech.get("trend") == "Downtrend":
        risks.append("Price below key moving averages")
    if fund and fund.get("metrics", {}).get("debt_to_equity_norm", 0) and fund["metrics"].get("debt_to_equity_norm", 0) > 1.5:
        risks.append("High leverage")
    if not risks:
        risks.append("Standard equity market risk")

    catalysts = []
    if m_score and m_score >= 65:
        catalysts.append("Positive price momentum")
    if f_score and f_score >= 65:
        catalysts.append("Supportive fundamental metrics")
    if tech and tech.get("volume_ratio") and tech["volume_ratio"] > 1.3:
        catalysts.append("Above-average volume participation")
    if not catalysts:
        catalysts.append("Await clearer catalyst confirmation")

    horizon = "Swing (2–8 weeks)"
    if overall is not None and overall >= 70 and (f_score or 0) >= 60:
        horizon = "Positional (3–12 months)"
    elif overall is not None and overall < 40:
        horizon = "Tactical (days–weeks) / risk management"

    return {
        "symbol": symbol,
        "name": (info or {}).get("shortName") or symbol.replace(".NS", ""),
        "sector": (info or {}).get("sector"),
        "technical_score": round(t_score, 1) if t_score is not None else None,
        "fundamental_score": round(f_score, 1) if f_score is not None else None,
        "momentum_score": round(m_score, 1) if m_score is not None else None,
        "valuation_score": round(v_score, 1) if v_score is not None else None,
        "sentiment_score": round(s_score, 1) if s_score is not None else None,
        "risk_score": round(r_score, 1) if r_score is not None else None,
        "overall_conviction": round(overall, 1) if overall is not None else None,
        "rating": rating,
        "confidence_pct": confidence,
        "evidence": evidence,
        "risks": risks,
        "catalysts": catalysts,
        "time_horizon": horizon,
        "tech": tech,
        "fund": fund,
    }
