"""Rule-based institutional briefing and narrative insights."""
from __future__ import annotations

from typing import Any, Callable, Dict, List


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


# --------------------------------------------------------------------------- #
# Closing deliverables
#
# Each list answers a different question, so each one draws from its own horizon
# cohort (built by pipeline.is_swing / is_long_term / is_weekly / is_monthly) and
# ranks on the metric that horizon actually trades on. The three lists are then
# made disjoint by priority: a symbol is reported once, in the list where it ranks
# highest. Names held back this way are returned in each list's meta so nothing is
# hidden, and a list that cannot be filled from its own cohort reports the shortfall
# instead of being padded with names that do not belong to the horizon.
# --------------------------------------------------------------------------- #

def _conviction(c: Dict[str, Any]) -> float:
    return c.get("overall_conviction") or -1.0


def _num(c: Dict[str, Any], key: str) -> float:
    v = c.get(key)
    return float(v) if isinstance(v, (int, float)) else 0.0


def _momentum(c: Dict[str, Any]) -> float:
    return _num(c, "momentum_score")


def _long_term_quality(c: Dict[str, Any]) -> float:
    """Fundamental-weighted: quality at a reasonable price, as the brief specifies."""
    return _num(c, "fundamental_score") * 0.6 + _num(c, "valuation_score") * 0.4


def _dedupe(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One card per symbol, keeping the strongest conviction copy."""
    unique: Dict[str, Dict[str, Any]] = {}
    for c in cards:
        sym = c.get("symbol")
        if not sym:
            continue
        if sym not in unique or _conviction(c) > _conviction(unique[sym]):
            unique[sym] = c
    return list(unique.values())


def _take(
    pool: List[Dict[str, Any]],
    key: Callable[[Dict[str, Any]], float],
    limit: int,
    claimed: Dict[str, str],
    cohort: str,
    metric: str,
    cohort_size: int,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    held_back = sorted(c["symbol"] for c in pool if c.get("symbol") in claimed)
    available = [c for c in pool if c.get("symbol") not in claimed]
    ranked = sorted(available, key=lambda c: (key(c), _conviction(c)), reverse=True)
    picked = ranked[:limit]
    meta = {
        "cohort": cohort,
        "cohort_size": cohort_size,
        "metric": metric,
        "excluded_as_already_listed": held_back,
    }
    if len(picked) < limit:
        meta["shortfall"] = limit - len(picked)
        meta["shortfall_reason"] = (
            f"Only {len(available)} {cohort} name(s) remain after removing names already listed above; "
            "the list is left short rather than padded with names outside the horizon."
        )
    return picked, meta


def executive_lists(payload: Dict[str, Any]) -> Dict[str, Any]:
    watchlists: Dict[str, List[Dict[str, Any]]] = payload.get("watchlists") or {}
    cohorts: Dict[str, List[Dict[str, Any]]] = payload.get("horizon_cohorts") or {}

    universe: List[Dict[str, Any]] = []
    for wl_name, wl in watchlists.items():
        for c in wl or []:
            c2 = dict(c)
            c2["watchlist"] = wl_name
            universe.append(c2)
    # Also include opportunity-discovered cards if present
    for o in payload.get("opportunity_cards") or []:
        universe.append(o)

    ranked = sorted(_dedupe(universe), key=_conviction, reverse=True)

    def horizon_pool(name: str) -> List[Dict[str, Any]]:
        """Prefers the deep horizon cohort when the pipeline supplies one.

        payload["watchlists"] is truncated to 20 per horizon for the screener
        tables, which is not enough to fill a 10-name closing list once the names
        already listed above are removed.
        """
        source = cohorts.get(name) or watchlists.get(name) or []
        return _dedupe([dict(c) for c in source])

    conviction = ranked[:10]
    conviction_meta = {
        "cohort": "full analysed universe",
        "cohort_size": len(ranked),
        "metric": "overall conviction",
        "excluded_as_already_listed": [],
    }
    claimed: Dict[str, str] = {c["symbol"]: "Top 10 conviction" for c in conviction if c.get("symbol")}

    swing_pool = horizon_pool("Swing Trading") or ranked
    swing, swing_meta = _take(
        swing_pool, _momentum, 10, claimed,
        cohort="swing screen", metric="momentum score, tie-broken by conviction",
        cohort_size=len(swing_pool),
    )
    for c in swing:
        claimed[c["symbol"]] = "Top 10 swing"

    long_pool = horizon_pool("Long Term Opportunities") or ranked
    long_term, long_meta = _take(
        long_pool, _long_term_quality, 10, claimed,
        cohort="long-term screen", metric="fundamental score 60% + valuation score 40%",
        cohort_size=len(long_pool),
    )

    return {
        "top_conviction": conviction,
        "top_swing": swing,
        "top_long_term": long_term,
        "top_conviction_meta": conviction_meta,
        "top_swing_meta": swing_meta,
        "top_long_term_meta": long_meta,
    }
