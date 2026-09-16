"""AI opportunity discovery from technical/fundamental scorecards."""
from __future__ import annotations

from typing import Any, Dict, List


def discover_opportunities(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    for c in cards:
        tech = c.get("tech") or {}
        fund = c.get("fund") or {}
        if c.get("overall_conviction") is None:
            continue
        symbol = c["symbol"]
        categories = []

        if tech.get("trend") == "Uptrend" and (tech.get("momentum_1m_pct") or 0) > 3 and (tech.get("volume_ratio") or 0) >= 1.2:
            categories.append(("Breakout / Momentum", "Uptrend with positive 1m momentum and volume confirmation"))
        if (c.get("momentum_score") or 0) >= 68:
            categories.append(("Momentum stock", f"Momentum score {c.get('momentum_score')}"))
        if (c.get("valuation_score") or 0) >= 65 and (c.get("fundamental_score") or 0) >= 55:
            categories.append(("Value opportunity", "Attractive valuation with acceptable fundamentals"))
        if (fund.get("metrics") or {}).get("revenue_growth") and fund["metrics"]["revenue_growth"] > 0.12:
            categories.append(("Growth stock", f"Revenue growth {fund['metrics']['revenue_growth']*100:.1f}%"))
        if tech.get("rsi") is not None and tech["rsi"] < 35 and tech.get("trend") != "Uptrend":
            categories.append(("Reversal candidate", f"RSI oversold at {tech['rsi']:.0f}"))
        if (c.get("fundamental_score") or 0) >= 70 and (c.get("risk_score") or 100) <= 55:
            categories.append(("Quality compounder", "High fundamental score with controlled risk"))
        if (tech.get("relative_strength") or 0) >= 65:
            categories.append(("High relative strength", f"RS {tech.get('relative_strength')}"))

        for cat, reason in categories:
            ops.append(
                {
                    "symbol": symbol,
                    "name": c.get("name"),
                    "category": cat,
                    "reason": reason,
                    "overall_conviction": c.get("overall_conviction"),
                    "rating": c.get("rating"),
                    "technical_score": c.get("technical_score"),
                    "fundamental_score": c.get("fundamental_score"),
                    "confidence_pct": c.get("confidence_pct"),
                }
            )

    # Deduplicate by symbol keeping highest conviction category row grouped
    ops.sort(key=lambda x: x.get("overall_conviction") or 0, reverse=True)
    seen = set()
    top: List[Dict[str, Any]] = []
    for o in ops:
        key = (o["symbol"], o["category"])
        if key in seen:
            continue
        seen.add(key)
        top.append(o)
        if len(top) >= 25:
            break

    # Top 10 unique symbols
    top10_symbols = []
    seen_sym = set()
    for o in ops:
        if o["symbol"] in seen_sym:
            continue
        seen_sym.add(o["symbol"])
        top10_symbols.append(o)
        if len(top10_symbols) >= 10:
            break

    return top10_symbols


def build_risk_dashboard(
    regime: Dict[str, Any],
    breadth: Dict[str, Any],
    globals_data: Dict[str, Any],
    sectors: Dict[str, Any],
    all_cards: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    def level(score: float) -> str:
        if score >= 70:
            return "Critical"
        if score >= 55:
            return "High"
        if score >= 40:
            return "Moderate"
        return "Low"

    market = regime.get("market_risk_score") or 50
    items = [
        {
            "name": "Market risk",
            "score": market,
            "level": regime.get("market_risk_label") or level(market),
            "detail": f"Bull {regime.get('bull_score')} / Bear {regime.get('bear_score')}; VIX {regime.get('india_vix')}",
        }
    ]

    # Sector risk: dispersion of sector performance
    ranked = sectors.get("ranked") or []
    if len(ranked) >= 3:
        chgs = [r.get("change_pct") for r in ranked if r.get("change_pct") is not None]
        if chgs:
            dispersion = max(chgs) - min(chgs)
            sec_score = min(90, 30 + dispersion * 8)
            items.append(
                {
                    "name": "Sector risk",
                    "score": round(sec_score, 1),
                    "level": level(sec_score),
                    "detail": f"Sector day-change dispersion {dispersion:.2f}pp",
                }
            )
    else:
        items.append(
            {
                "name": "Sector risk",
                "score": None,
                "level": "Unavailable",
                "detail": "Insufficient sector data",
            }
        )

    # Liquidity: from breadth volume — proxy only (thin = low-volume count in universe)
    thin = (breadth or {}).get("thin_count")
    if thin is not None:
        liq = min(85, 30 + thin * 5)
        items.append(
            {
                "name": "Liquidity risk",
                "score": liq,
                "level": level(liq),
                "detail": "Proxy from universe volume ratios (not exchange liquidity metrics)",
            }
        )
    else:
        items.append(
            {
                "name": "Liquidity risk",
                "score": None,
                "level": "Unavailable",
                "detail": "Volume data insufficient",
            }
        )

    pes = []
    if all_cards:
        for c in all_cards:
            pe = (c.get("fund") or {}).get("metrics", {}).get("pe")
            if isinstance(pe, (int, float)) and pe > 0:
                pes.append(pe)
                
    if pes:
        avg_pe = sum(pes) / len(pes)
        if avg_pe > 25:
            pe_score = min(90, 50 + (avg_pe - 25) * 2)
        else:
            pe_score = max(10, 50 - (25 - avg_pe) * 2)
        items.append(
            {
                "name": "Valuation risk",
                "score": round(pe_score, 1),
                "level": level(pe_score),
                "detail": f"Nifty Universe Aggregate P/E is {avg_pe:.1f}",
            }
        )
    else:
        items.append(
            {
                "name": "Valuation risk",
                "score": None,
                "level": "Unavailable",
                "detail": "Aggregate market valuation (CAPE/PE bands) not sourced — avoid fabrication",
            }
        )

    # Macro risk from USD/INR, yields, crude
    macro = 40.0
    details = []
    for name, weight in [("USD/INR", 8), ("US 10Y Yield", 6), ("Crude Oil", 5), ("Dollar Index", 5)]:
        q = globals_data.get(name) or {}
        if q.get("status") == "ok" and q.get("change_pct") is not None:
            macro += abs(q["change_pct"]) * weight / 3
            details.append(f"{name} {q['change_pct']:+.2f}%")
    items.append(
        {
            "name": "Macro risk",
            "score": round(min(95, macro), 1),
            "level": level(macro),
            "detail": "; ".join(details) if details else "Limited macro quotes",
        }
    )

    us_vix = (globals_data.get("VIX (US)") or {}).get("last")
    global_score = 35.0
    if us_vix:
        global_score = min(95, 20 + us_vix * 1.5)
    items.append(
        {
            "name": "Global risk",
            "score": round(global_score, 1),
            "level": level(global_score),
            "detail": f"US VIX {us_vix}" if us_vix else "US VIX unavailable",
        }
    )

    return {"items": items, "overall_label": regime.get("market_risk_label")}
