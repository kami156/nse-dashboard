"""NSE option-chain access via nselib/nsepython, with tertiary HTTP fallback."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

from .nse_reference import (
    INDEX_SYMBOLS,
    fetch_option_chain,
    fetch_option_expiries,
    from_yahoo_symbol,
)

# Re-export for analytics.imports
__all__ = [
    "INDEX_SYMBOLS",
    "fetch_contract_info",
    "fetch_option_chain_raw",
    "chain_to_frame",
    "classify_expiries",
    "_parse_expiry",
    "_session",
]

NSE_HOME = "https://www.nseindia.com"
OPTION_CHAIN_PAGE = "https://www.nseindia.com/option-chain"
CONTRACT_INFO = "https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}"
CHAIN_V3 = "https://www.nseindia.com/api/option-chain-v3?type={typ}&symbol={symbol}&expiry={expiry}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": OPTION_CHAIN_PAGE,
    "Connection": "keep-alive",
}


def _session() -> requests.Session:
    """Tertiary HTTP session (used only if nselib + nsepython fail)."""
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(OPTION_CHAIN_PAGE, timeout=20)
        time.sleep(0.35)
    except Exception:
        pass
    return s


def _get_json(sess: requests.Session, url: str) -> Dict[str, Any]:
    resp = sess.get(url, timeout=25)
    if resp.status_code in (401, 403):
        sess.get(OPTION_CHAIN_PAGE, timeout=20)
        time.sleep(0.5)
        resp = sess.get(url, timeout=25)
    if resp.status_code != 200:
        return {"status": "unavailable", "reason": f"NSE API HTTP {resp.status_code}", "source": url}
    try:
        data = resp.json()
    except Exception as exc:
        return {"status": "unavailable", "reason": f"Invalid JSON: {exc}", "source": url}
    if not data:
        return {"status": "unavailable", "reason": "Empty NSE response", "source": url}
    return data


def _http_contract_info(symbol: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    sym = from_yahoo_symbol(symbol)
    own = session is None
    sess = session or _session()
    try:
        url = CONTRACT_INFO.format(symbol=sym)
        data = _get_json(sess, url)
        if data.get("status") == "unavailable":
            data["symbol"] = sym
            return data
        return {
            "status": "ok",
            "symbol": sym,
            "expiryDates": data.get("expiryDates") or [],
            "strikePrice": data.get("strikePrice") or [],
            "source": url,
        }
    finally:
        if own:
            try:
                sess.close()
            except Exception:
                pass


def fetch_contract_info(symbol: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    sym = from_yahoo_symbol(symbol)
    info = fetch_option_expiries(sym)
    if info.get("status") == "ok" and info.get("expiryDates"):
        return {
            "status": "ok",
            "symbol": sym,
            "expiryDates": info.get("expiryDates") or [],
            "strikePrice": [],
            "source": info.get("source"),
        }
    # Tertiary HTTP
    return _http_contract_info(sym, session=session)


def _http_option_chain_raw(
    symbol: str,
    expiry: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    sym = from_yahoo_symbol(symbol)
    own_session = session is None
    sess = session or _session()
    typ = "Indices" if sym in INDEX_SYMBOLS else "Equity"
    try:
        info = _http_contract_info(sym, session=sess)
        if info.get("status") != "ok":
            return {
                "status": "unavailable",
                "symbol": sym,
                "reason": info.get("reason", "contract-info failed"),
                "source": info.get("source"),
            }
        expiries = info.get("expiryDates") or []
        if not expiry:
            if not expiries:
                return {
                    "status": "unavailable",
                    "symbol": sym,
                    "reason": "No expiry dates from NSE",
                    "source": info.get("source"),
                }
            expiry = expiries[0]
        url = CHAIN_V3.format(typ=typ, symbol=sym, expiry=expiry)
        data = _get_json(sess, url)
        if data.get("status") == "unavailable":
            data["symbol"] = sym
            return data
        records = data.setdefault("records", {})
        if not records.get("expiryDates"):
            records["expiryDates"] = expiries
        if not (records.get("data") or []):
            return {
                "status": "unavailable",
                "symbol": sym,
                "reason": f"Empty chain for expiry={expiry}",
                "source": url,
            }
        data["_meta"] = {
            "status": "ok",
            "symbol": sym,
            "expiry": expiry,
            "source": url,
            "source_page": OPTION_CHAIN_PAGE,
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        return data
    except Exception as exc:
        return {
            "status": "unavailable",
            "symbol": sym,
            "reason": str(exc),
            "source": CHAIN_V3.format(typ=typ, symbol=sym, expiry=expiry or ""),
        }
    finally:
        if own_session:
            try:
                sess.close()
            except Exception:
                pass


def fetch_option_chain_raw(
    symbol: str,
    expiry: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    Fetch option chain for a symbol/expiry.
    Primary: nselib → nsepython (via nse_reference). Tertiary: direct NSE HTTP.
    """
    sym = from_yahoo_symbol(symbol)
    lib = fetch_option_chain(sym, expiry=expiry)
    if lib.get("status") != "unavailable" and (lib.get("records") or {}).get("data"):
        return lib
    # Tertiary HTTP (session unused by libs but kept for API compatibility)
    http = _http_option_chain_raw(sym, expiry=expiry, session=session)
    if http.get("status") == "unavailable" and lib.get("reason"):
        http["reason"] = f"{lib.get('reason')}; tertiary: {http.get('reason')}"
    return http


def _parse_expiry(s: str) -> Optional[datetime]:
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def classify_expiries(expiry_list: List[str]) -> Dict[str, Any]:
    """Nearest = weekly; last expiry of a calendar month = monthly."""
    parsed: List[Tuple[str, datetime]] = []
    for e in expiry_list or []:
        dt = _parse_expiry(e)
        if dt:
            parsed.append((e, dt))
    parsed.sort(key=lambda x: x[1])
    if not parsed:
        return {"weekly": None, "monthly": None, "all": []}

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    future = [(e, d) for e, d in parsed if d >= today] or parsed
    weekly = future[0][0]

    by_month: Dict[Tuple[int, int], List[Tuple[str, datetime]]] = {}
    for e, d in future:
        by_month.setdefault((d.year, d.month), []).append((e, d))

    monthly = None
    for key in sorted(by_month.keys()):
        month_exps = sorted(by_month[key], key=lambda x: x[1])
        candidate = month_exps[-1][0]
        if candidate != weekly:
            monthly = candidate
            break
        monthly = candidate
    if monthly is None:
        monthly = future[-1][0] if len(future) > 1 else weekly

    return {
        "weekly": weekly,
        "monthly": monthly,
        "all": [e for e, _ in future],
        "parsed": [{"expiry": e, "date": d.strftime("%Y-%m-%d")} for e, d in future],
    }


def _leg_get(leg: Dict[str, Any], *keys, default=None):
    for k in keys:
        if k in leg and leg[k] is not None:
            return leg[k]
    return default


def chain_to_frame(raw: Dict[str, Any], expiry: Optional[str] = None) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    if not raw or raw.get("status") == "unavailable":
        return None, {"status": "unavailable", "reason": raw.get("reason") if raw else "empty"}

    records = raw.get("records") or {}
    underlying = records.get("underlyingValue")
    expiries = records.get("expiryDates") or []
    data = records.get("data") or []
    if not data:
        data = (raw.get("filtered") or {}).get("data") or []

    rows = []
    for row in data:
        exp = row.get("expiryDates") or row.get("expiryDate")
        if expiry and exp and exp != expiry:
            ce_exp = ((row.get("CE") or {}).get("expiryDate"))
            if ce_exp and expiry.replace("-", "") not in str(ce_exp).replace("-", ""):
                if len({(r.get("expiryDates") or r.get("expiryDate")) for r in data}) > 1:
                    continue

        strike = row.get("strikePrice")
        ce = row.get("CE") or {}
        pe = row.get("PE") or {}
        rows.append(
            {
                "expiry": exp or expiry,
                "strike": strike,
                "ce_oi": _leg_get(ce, "openInterest", default=0) or 0,
                "ce_chg_oi": _leg_get(ce, "changeinOpenInterest", default=0) or 0,
                "ce_volume": _leg_get(ce, "totalTradedVolume", default=0) or 0,
                "ce_iv": _leg_get(ce, "impliedVolatility"),
                "ce_ltp": _leg_get(ce, "lastPrice"),
                "ce_bid": _leg_get(ce, "buyPrice1", "bidprice"),
                "ce_ask": _leg_get(ce, "sellPrice1", "askPrice"),
                "ce_delta": _leg_get(ce, "delta"),
                "ce_theta": _leg_get(ce, "theta"),
                "ce_gamma": _leg_get(ce, "gamma"),
                "ce_vega": _leg_get(ce, "vega"),
                "pe_oi": _leg_get(pe, "openInterest", default=0) or 0,
                "pe_chg_oi": _leg_get(pe, "changeinOpenInterest", default=0) or 0,
                "pe_volume": _leg_get(pe, "totalTradedVolume", default=0) or 0,
                "pe_iv": _leg_get(pe, "impliedVolatility"),
                "pe_ltp": _leg_get(pe, "lastPrice"),
                "pe_bid": _leg_get(pe, "buyPrice1", "bidprice"),
                "pe_ask": _leg_get(pe, "sellPrice1", "askPrice"),
                "pe_delta": _leg_get(pe, "delta"),
                "pe_theta": _leg_get(pe, "theta"),
                "pe_gamma": _leg_get(pe, "gamma"),
                "pe_vega": _leg_get(pe, "vega"),
            }
        )

    if not rows:
        return None, {
            "status": "unavailable",
            "reason": f"No strikes for expiry={expiry}",
            "underlying": underlying,
            "expiries": expiries,
        }

    df = pd.DataFrame(rows).dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True)
    meta = {
        "status": "ok",
        "underlying": underlying,
        "expiry": expiry or (raw.get("_meta") or {}).get("expiry"),
        "expiries": expiries,
        "timestamp": records.get("timestamp"),
        "source": (raw.get("_meta") or {}).get("source"),
        "fetched_at": (raw.get("_meta") or {}).get("fetched_at"),
    }
    return df, meta
