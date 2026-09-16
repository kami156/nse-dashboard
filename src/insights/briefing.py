"""Rule-based institutional briefing and narrative insights."""
from __future__ import annotations

from typing import Any, Dict, List


def one_minute_briefing(payload: Dict[str, Any]) -> str:
    regime = payload.get("regime") or {}
    breadth = payload.get("breadth") or {}
    sectors = (payload.get("sector_rotation") or {}).get("ranked") or []
    top_sec = sectors[0]["sector"] if sectors else "n/a"
    weak_sec = sectors[-1]["sector"] if sectors else "n/a"
    nifty = regime.get("nifty_change_pct")
    nifty_txt = f"{nifty:+.2f}%" if nifty is not None else "unavailable"
    fii = payload.get("fii_dii") or {}
    if fii.get("status") == "ok" and fii.get("summary"):
        fii_txt = f"FII/DII ({fii.get('as_of') or 'latest'}): {fii.get('summary')}."
    else:
        fii_txt = "FII/DII market activity unavailable from NSE feeds."
    return (
        f"Market sentiment is {regime.get('market_sentiment', 'n/a')} "
        f"({regime.get('market_regime', 'n/a')}) with bull score "
        f"{regime.get('bull_score', 'n/a')} and risk "
        f"{regime.get('market_risk_label', 'n/a')} ({regime.get('market_risk_score', 'n/a')}). "
        f"Nifty day move {nifty_txt}. Breadth: {breadth.get('summary', 'n/a')} "
        f"Sector leadership: {top_sec} strongest / {weak_sec} weakest among available sector proxies. "
        f"{fii_txt} "
        f"Recommendations below are evidence-scored. Options use NSE chain weekly/monthly "
        f"with ~80% model-POP credit strategies where data allows."
    )


def build_insights(payload: Dict[str, Any]) -> Dict[str, Any]:
    regime = payload.get("regime") or {}
    opportunities = payload.get("opportunities") or []
    risks_dash = payload.get("risk_dashboard") or {}
    sectors = (payload.get("sector_rotation") or {}).get("ranked") or []

    weekly = (
        f"Weekly outlook leans {regime.get('market_sentiment', 'mixed').lower()} while regime is "
        f"{regime.get('market_regime', 'transition')}. Watch breadth score "
        f"{(payload.get('breadth') or {}).get('breadth_score')} and India VIX "
        f"{regime.get('india_vix')} for confirmation of trend continuation vs mean reversion."
    )
    monthly = (
        "Monthly outlook depends on global risk (USD, US yields, crude) and domestic earnings delivery. "
        "Positional bias should stay aligned with Nifty trend vs 50/200 EMA structure and sector leadership persistence."
    )
    sector_outlook = []
    for s in sectors[:5]:
        sector_outlook.append(
            f"{s['sector']}: rank #{s.get('rank')} (score {s.get('rank_score')}) — {s.get('trend') or 'n/a'}"
        )

    themes = []
    if regime.get("bull_score", 50) >= 60:
        themes.append("Risk-on participation favoring high relative-strength sectors")
    elif regime.get("bull_score", 50) <= 40:
        themes.append("Defensive posture; prefer quality balance sheets and lower beta")
    else:
        themes.append("Selective stock-picking over index beta")
    if opportunities:
        themes.append(f"Opportunity engine highlighting {opportunities[0].get('category')} names")

    return {
        "market_summary": one_minute_briefing(payload),
        "weekly_outlook": weekly,
        "monthly_outlook": monthly,
        "sector_outlook": sector_outlook,
        "risks": [r.get("detail") for r in (risks_dash.get("items") or [])][:8],
        "opportunities": [f"{o['symbol']}: {o.get('category')} — {o.get('reason')}" for o in opportunities[:8]],
        "key_themes": themes,
    }


def executive_lists(payload: Dict[str, Any]) -> Dict[str, Any]:
    cards: List[Dict[str, Any]] = []
    for wl_name, wl in (payload.get("watchlists") or {}).items():
        for c in wl:
            c2 = dict(c)
            c2["watchlist"] = wl_name
            cards.append(c2)
    # Also include opportunity-discovered cards if present
    for o in payload.get("opportunity_cards") or []:
        cards.append(o)

    def sort_key(c):
        return c.get("overall_conviction") or -1

    unique = {}
    for c in cards:
        sym = c["symbol"]
        if sym not in unique or sort_key(c) > sort_key(unique[sym]):
            unique[sym] = c
    ranked = sorted(unique.values(), key=sort_key, reverse=True)

    conviction = ranked[:10]
    swing = [c for c in ranked if (c.get("momentum_score") or 0) >= 55][:10]
    if len(swing) < 10:
        swing = ranked[:10]
    long_term = sorted(
        ranked,
        key=lambda c: ((c.get("fundamental_score") or 0) * 0.6 + (c.get("overall_conviction") or 0) * 0.4),
        reverse=True,
    )[:10]

    return {
        "top_conviction": conviction,
        "top_swing": swing,
        "top_long_term": long_term,
    }
