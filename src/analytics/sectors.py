"""Sector rotation ranking from sector index quotes + technicals."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .technical import analyze_technical


SECTOR_KEYS = [
    "Nifty IT",
    "Nifty Pharma",
    "Nifty Auto",
    "Nifty Metal",
    "Nifty FMCG",
    "Nifty Energy",
    "Nifty Realty",
    "Nifty PSU Bank",
    "Nifty Media",
    "Nifty Bank",
]

# yfinance/Yahoo Finance reports a broad GICS-like "sector" (Technology,
# Healthcare, Financial Services, ...) and a finer "industry" per stock.
# A naive substring check of the bare index name (e.g. "it" in "Nifty IT")
# almost never matches that taxonomy — "it" is not a substring of
# "Technology" or "Information Technology Services" at all. Match on the
# actual vocabulary Yahoo uses instead.
SECTOR_MATCH_KEYWORDS: Dict[str, List[str]] = {
    "Nifty IT": ["technology", "information technology", "software", "it services"],
    "Nifty Pharma": ["healthcare", "pharma", "drug manufacturer", "biotechnology", "medical"],
    "Nifty Auto": ["auto", "vehicle", "automobile"],
    "Nifty Metal": ["steel", "metal", "aluminum", "mining", "copper", "basic materials"],
    "Nifty FMCG": [
        "consumer defensive", "household", "packaged foods", "beverages",
        "personal products", "tobacco", "food",
    ],
    "Nifty Energy": ["energy", "oil", "gas", "refin", "coal"],
    "Nifty Realty": ["real estate", "realty"],
    "Nifty PSU Bank": ["bank"],
    "Nifty Media": ["media", "broadcasting", "entertainment", "publish"],
    "Nifty Bank": ["bank"],
}


def rank_sectors(
    indices: Dict[str, Dict[str, Any]],
    histories: Dict[str, pd.DataFrame],
    ticker_by_name: Dict[str, str],
    all_cards: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for name in SECTOR_KEYS:
        quote = indices.get(name, {})
        ticker = ticker_by_name.get(name) or quote.get("ticker")
        tech = analyze_technical(histories.get(ticker)) if ticker and ticker in histories else {"status": "unavailable"}
        if quote.get("status") != "ok" and tech.get("status") != "ok":
            rows.append(
                {
                    "sector": name,
                    "status": "unavailable",
                    "reason": quote.get("reason") or tech.get("reason") or "No sector data",
                    "rank_score": None,
                }
            )
            continue

        rs = tech.get("relative_strength") if tech.get("status") == "ok" else 50
        mom = tech.get("momentum_1m_pct") if tech.get("status") == "ok" else quote.get("change_pct") or 0
        inst = 50.0

        # Calculate dynamic sector valuation and earnings from all_cards
        valuation = 50.0
        earnings = 50.0
        val_note = "Sector valuation aggregates unavailable"
        earn_note = "Sector earnings trend unavailable"

        if all_cards:
            sec_pes = []
            sec_earn = []
            keywords = SECTOR_MATCH_KEYWORDS.get(name) or [name.replace("Nifty ", "").lower()]
            for c in all_cards:
                c_sec = ((c.get("fund") or {}).get("metrics") or {}).get("sector") or ""
                c_sec = c_sec.lower()
                c_ind = ((c.get("fund") or {}).get("metrics") or {}).get("industry") or ""
                c_ind = c_ind.lower()

                if any(kw in c_sec or kw in c_ind for kw in keywords):
                    pe = (c.get("fund") or {}).get("metrics", {}).get("pe")
                    eg = (c.get("fund") or {}).get("metrics", {}).get("earnings_growth")
                    if isinstance(pe, (int, float)) and pe > 0: sec_pes.append(pe)
                    if isinstance(eg, (int, float)): sec_earn.append(eg)

            if sec_pes:
                avg_pe = sum(sec_pes) / len(sec_pes)
                valuation = max(10, min(90, 50 + (25 - avg_pe) * 1.5))
                val_note = f"Sector Aggregate P/E: {avg_pe:.1f}"
            if sec_earn:
                avg_eg = sum(sec_earn) / len(sec_earn)
                earnings = max(10, min(90, 50 + avg_eg * 100))
                earn_note = f"Sector Aggregate Earnings Growth: {avg_eg*100:.1f}%"

        rank = (
            0.35 * (rs or 50)
            + 0.35 * (50 + np.clip((mom or 0) * 2, -25, 25))
            + 0.10 * inst
            + 0.10 * valuation
            + 0.10 * earnings
        )
        rows.append(
            {
                "sector": name,
                "status": "ok",
                "last": quote.get("last"),
                "change_pct": quote.get("change_pct"),
                "relative_strength": rs,
                "momentum_1m_pct": mom,
                "institutional_participation": {
                    "value": inst,
                    "note": "Sector-level FII/DII flows unavailable; market-level cash FII/DII is shown in NSE coverage",
                },
                "valuation": {"value": valuation, "note": val_note},
                "earnings_trend": {"value": earnings, "note": earn_note},
                "trend": tech.get("trend"),
                "technical_score": tech.get("technical_score"),
                "rank_score": round(float(rank), 1),
                "ai_summary": tech.get("ai_summary") or f"{name} ranked on relative strength and momentum only.",
            }
        )

    available = [r for r in rows if r.get("rank_score") is not None]
    available.sort(key=lambda x: x["rank_score"], reverse=True)
    for i, r in enumerate(available, 1):
        r["rank"] = i
    unavailable = [r for r in rows if r.get("rank_score") is None]
    return {
        "status": "ok" if available else "unavailable",
        "ranked": available,
        "unavailable": unavailable,
        "method_note": (
            "Ranking uses relative strength + momentum from sector index proxies. "
            "Institutional participation, valuation, and earnings trend are marked neutral/unavailable "
            "without fabricating values."
        ),
    }
