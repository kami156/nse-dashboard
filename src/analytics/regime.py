"""Market regime, bull/bear and risk aggregation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


def _pct(item: Dict[str, Any]) -> Optional[float]:
    if not item or item.get("status") != "ok":
        return None
    return item.get("change_pct")


def detect_regime(
    indices: Dict[str, Dict[str, Any]],
    globals_data: Dict[str, Dict[str, Any]],
    breadth: Dict[str, Any],
    nifty_tech: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    nifty = indices.get("Nifty 50", {})
    bank = indices.get("Nifty Bank", {})
    vix = indices.get("India VIX", {})
    us_vix = globals_data.get("VIX (US)", {})

    signals: List[str] = []
    bull = 50.0

    n_chg = _pct(nifty)
    if n_chg is not None:
        bull += np.clip(n_chg * 3, -15, 15)
        signals.append(f"Nifty 50 day change {n_chg:+.2f}%")
    b_chg = _pct(bank)
    if b_chg is not None:
        bull += np.clip(b_chg * 2, -10, 10)

    if nifty_tech:
        if nifty_tech.get("trend") == "Uptrend":
            bull += 10
            signals.append("Nifty technical uptrend")
        elif nifty_tech.get("trend") == "Downtrend":
            bull -= 10
            signals.append("Nifty technical downtrend")
        ts = nifty_tech.get("technical_score")
        if ts is not None:
            bull += (ts - 50) * 0.25

    bs = breadth.get("breadth_score")
    if bs is not None:
        bull += (bs - 50) * 0.2
        signals.append(f"Breadth score {bs}")

    risk = 40.0
    vix_last = vix.get("last") if vix.get("status") == "ok" else None
    if vix_last is not None:
        if vix_last > 20:
            risk += min(25, (vix_last - 20) * 2)
            bull -= 5
            signals.append(f"India VIX elevated at {vix_last:.1f}")
        else:
            risk -= 5
            signals.append(f"India VIX contained at {vix_last:.1f}")
    us_vix_last = us_vix.get("last") if us_vix.get("status") == "ok" else None
    if us_vix_last and us_vix_last > 25:
        risk += 10
        signals.append(f"US VIX elevated ({us_vix_last:.1f})")

    dxy = _pct(globals_data.get("Dollar Index", {}))
    usdinr = _pct(globals_data.get("USD/INR", {}))
    if dxy is not None and dxy > 0.3:
        risk += 4
        signals.append("Dollar strength pressure")
    if usdinr is not None and usdinr > 0.2:
        risk += 4
        signals.append("INR weakening vs USD")

    bull = float(np.clip(bull, 0, 100))
    risk = float(np.clip(risk, 0, 100))
    bear = 100 - bull

    if bull >= 65:
        sentiment = "Bullish"
        regime = "Risk-on / Expansion"
    elif bull <= 35:
        sentiment = "Bearish"
        regime = "Risk-off / Contraction"
    else:
        sentiment = "Neutral / Mixed"
        regime = "Range / Transition"

    if risk >= 70:
        risk_label = "Critical"
    elif risk >= 55:
        risk_label = "High"
    elif risk >= 40:
        risk_label = "Moderate"
    else:
        risk_label = "Low"

    return {
        "market_sentiment": sentiment,
        "market_regime": regime,
        "bull_score": round(bull, 1),
        "bear_score": round(bear, 1),
        "market_risk_score": round(risk, 1),
        "market_risk_label": risk_label,
        "drivers": signals[:8],
        "nifty_last": nifty.get("last"),
        "nifty_change_pct": n_chg,
        "bank_change_pct": b_chg,
        "india_vix": vix_last,
    }
