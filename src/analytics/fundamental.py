"""Fundamental analysis engine and Fundamental Score (0-100)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np


def _clip_score(x: float) -> float:
    return float(np.clip(x, 0, 100))


def analyze_fundamental(
    info: Dict[str, Any],
    market_fii_dii: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not info or info.get("status") == "unavailable":
        return {
            "status": "unavailable",
            "reason": info.get("reason", "Fundamental data unavailable"),
            "fundamental_score": None,
            "valuation_score": None,
        }

    missing = []
    fields = {
        "revenue_growth": info.get("revenueGrowth"),
        "eps_growth": info.get("earningsGrowth"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "profit_margin": info.get("profitMargins"),
        "operating_margin": info.get("operatingMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "free_cash_flow": info.get("freeCashflow"),
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "promoter_holding": info.get("heldPercentInsiders"),
        "institutional_holding": info.get("heldPercentInstitutions"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "name": info.get("shortName"),
    }
    for k, v in fields.items():
        if v is None and k not in ("sector", "industry", "name", "dividend_yield", "forward_pe", "roa"):
            missing.append(k)

    score = 50.0
    evidence = []

    rg = fields["revenue_growth"]
    if rg is not None:
        score += np.clip(rg * 40, -12, 15)
        evidence.append(f"Revenue growth {rg*100:.1f}%")
    eg = fields["eps_growth"]
    if eg is not None:
        score += np.clip(eg * 35, -12, 15)
        evidence.append(f"EPS growth {eg*100:.1f}%")
    roe = fields["roe"]
    if roe is not None:
        # yfinance ROE often as fraction
        roe_pct = roe * 100 if abs(roe) < 5 else roe
        score += np.clip((roe_pct - 12) / 2, -10, 12)
        evidence.append(f"ROE {roe_pct:.1f}%")
        fields["roe_pct"] = round(roe_pct, 2)
    # ROCE proxy via ROA + margin quality
    if fields["operating_margin"] is not None:
        om = fields["operating_margin"] * 100 if abs(fields["operating_margin"]) < 5 else fields["operating_margin"]
        score += np.clip((om - 10) / 3, -8, 10)
        fields["operating_margin_pct"] = round(om, 2)
    de = fields["debt_to_equity"]
    if de is not None:
        # debtToEquity from yfinance often as percent-like (e.g. 50 = 0.5)
        de_val = de / 100 if de > 10 else de
        if de_val < 0.5:
            score += 6
        elif de_val > 1.5:
            score -= 8
        evidence.append(f"D/E {de_val:.2f}")
        fields["debt_to_equity_norm"] = round(de_val, 2)
    if fields["free_cash_flow"] is not None:
        if fields["free_cash_flow"] > 0:
            score += 6
            evidence.append("Positive FCF")
        else:
            score -= 6
            evidence.append("Negative FCF")

    # Valuation score separate
    val = 50.0
    pe = fields["pe"]
    if pe is not None and pe > 0:
        if pe < 15:
            val += 15
        elif pe < 25:
            val += 5
        elif pe > 40:
            val -= 15
        else:
            val -= 5
        evidence.append(f"P/E {pe:.1f}")
    pb = fields["pb"]
    if pb is not None and pb > 0:
        if pb < 2:
            val += 8
        elif pb > 6:
            val -= 10
    if fields["promoter_holding"] is not None:
        ph = fields["promoter_holding"] * 100 if fields["promoter_holding"] <= 1 else fields["promoter_holding"]
        fields["promoter_holding_pct"] = round(ph, 2)
        if ph >= 40:
            score += 4
    if fields["institutional_holding"] is not None:
        ih = fields["institutional_holding"] * 100 if fields["institutional_holding"] <= 1 else fields["institutional_holding"]
        fields["institutional_holding_pct"] = round(ih, 2)

    # Per-stock FII/DII ownership split is not in free feeds.
    # Attach market-level cash FII/DII when provided by nselib/nsepython.
    if market_fii_dii and market_fii_dii.get("status") == "ok":
        fii_dii = {
            "status": "market_level",
            "summary": market_fii_dii.get("summary"),
            "as_of": market_fii_dii.get("as_of"),
            "source": market_fii_dii.get("source"),
            "reason": "Market-level cash FII/DII (not per-stock ownership split)",
        }
    else:
        fii_dii = {
            "status": "unavailable",
            "reason": (
                "Per-stock FII/DII ownership split unavailable; "
                "market-level activity also unavailable"
            ),
        }

    fund_score = _clip_score(score)
    val_score = _clip_score(val)

    return {
        "status": "ok" if len(missing) < 8 else "partial",
        "missing_fields": missing,
        "fundamental_score": round(fund_score, 1),
        "valuation_score": round(val_score, 1),
        "metrics": fields,
        "fii_dii": fii_dii,
        "evidence": evidence,
        "ai_summary": (
            f"{fields.get('name') or 'Stock'}: fund score {fund_score:.0f}/100, "
            f"valuation {val_score:.0f}/100. " + ("; ".join(evidence[:4]) if evidence else "Limited fundamentals.")
        ),
    }
