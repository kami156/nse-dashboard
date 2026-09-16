"""News intelligence and economic dashboard — honest availability labeling."""
from __future__ import annotations

from typing import Any, Dict, List

import requests


def fetch_news_intelligence() -> Dict[str, Any]:
    """
    Best-effort: try Yahoo Finance RSS-like public endpoints via yfinance isn't news-complete.
    We attempt a lightweight Google News RSS query; on failure mark unavailable.
    """
    categories = [
        ("Earnings", "NSE earnings results"),
        ("Corporate actions", "NSE corporate action dividend bonus"),
        ("RBI", "Reserve Bank of India policy"),
        ("SEBI", "SEBI India market regulation"),
        ("Government policy", "India budget policy markets"),
        ("FII/DII flows", "FII DII India equity flows"),
        ("Block deals", "NSE block deal"),
        ("Bulk deals", "NSE bulk deal"),
        ("Insider transactions", "India insider trading disclosure"),
    ]
    items: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for label, query in categories:
        try:
            url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
            resp = requests.get(url, timeout=8, headers={"User-Agent": "NSE-Dashboard/1.0"})
            if resp.status_code != 200:
                items.append(
                    {
                        "category": label,
                        "status": "unavailable",
                        "reason": f"HTTP {resp.status_code}",
                        "headlines": [],
                        "likely_impact": "Unknown — source unavailable",
                    }
                )
                continue
            # Very light parse without requiring feedparser
            text = resp.text
            headlines = []
            parts = text.split("<title>")
            for p in parts[2:6]:  # skip channel title
                title = p.split("</title>")[0].strip()
                title = (
                    title.replace("<![CDATA[", "")
                    .replace("]]>", "")
                    .replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                )
                if title:
                    headlines.append(title)
            impact = "Monitor for stock-specific reaction"
            if label in ("RBI", "SEBI", "Government policy"):
                impact = "Potential market-wide / sector policy impact"
            elif label in ("FII/DII flows", "Block deals", "Bulk deals"):
                impact = "Flows/liquidity signal — confirm with exchange data"
            items.append(
                {
                    "category": label,
                    "status": "ok" if headlines else "partial",
                    "headlines": headlines,
                    "likely_impact": impact,
                    "source": "Google News RSS (headlines only; not verified exchange filings)",
                }
            )
        except Exception as exc:
            warnings.append(f"news {label}: {exc}")
            items.append(
                {
                    "category": label,
                    "status": "unavailable",
                    "reason": str(exc),
                    "headlines": [],
                    "likely_impact": "Unknown — source unavailable",
                }
            )

    return {
        "items": items,
        "warnings": warnings,
        "note": "Headlines are informational only; impact estimates are categorical, not price forecasts.",
    }


def economic_dashboard(globals_data: Dict[str, Any]) -> Dict[str, Any]:
    """Track what we can from free quotes; label official macro series unavailable."""
    def quote_row(name: str) -> Dict[str, Any]:
        q = globals_data.get(name) or {}
        if q.get("status") == "ok":
            return {
                "name": name,
                "status": "ok",
                "last": q.get("last"),
                "change_pct": q.get("change_pct"),
                "source": "Yahoo Finance",
            }
        return {
            "name": name,
            "status": "unavailable",
            "reason": q.get("reason") or "No quote",
        }

    return {
        "inflation": {
            "status": "unavailable",
            "reason": "CPI/WPI official series not fetched — use MOSPI/RBI releases",
        },
        "gdp": {
            "status": "unavailable",
            "reason": "GDP prints not fetched — use MOSPI / RBI publications",
        },
        "pmi": {
            "status": "unavailable",
            "reason": "PMI requires licensed data vendor or official release scrape with attribution",
        },
        "interest_rates": {
            "status": "partial",
            "items": [quote_row("US 10Y Yield")],
            "note": "India 10Y / policy repo rate not auto-fetched; confirm via RBI",
        },
        "currency": quote_row("USD/INR"),
        "commodities": [quote_row("Gold"), quote_row("Silver"), quote_row("Crude Oil")],
        "global_central_banks": {
            "status": "unavailable",
            "reason": "Central bank event calendar not integrated in this build",
        },
        "dollar_index": quote_row("Dollar Index"),
    }
