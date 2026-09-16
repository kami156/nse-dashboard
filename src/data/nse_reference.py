"""NSE reference data: nselib primary, nsepython fallback (not for OHLC history)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .cache import TTLCache

INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}


def to_yahoo_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return s
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    if s in INDEX_SYMBOLS or s in ("NIFTY", "BANKNIFTY"):
        return s
    return f"{s}.NS"


def from_yahoo_symbol(symbol: str) -> str:
    return (symbol or "").replace(".NS", "").replace(".BO", "").upper().strip()


def _empty(reason: str, source: str = "nselib/nsepython") -> Dict[str, Any]:
    return {"status": "unavailable", "reason": reason, "source": source}


def _df_empty(df: Any) -> bool:
    return df is None or (isinstance(df, pd.DataFrame) and df.empty) or (
        isinstance(df, (list, dict)) and len(df) == 0
    )


def _normalize_fii_dii_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    cols = {c.lower().replace(" ", ""): c for c in df.columns}

    def col(*names: str) -> Optional[str]:
        for n in names:
            key = n.lower().replace(" ", "")
            if key in cols:
                return cols[key]
        # fuzzy
        for k, orig in cols.items():
            for n in names:
                if n.lower().replace(" ", "") in k:
                    return orig
        return None

    cat_c = col("category", "categoryname")
    buy_c = col("buyValue", "buyvalue", "buy")
    sell_c = col("sellValue", "sellvalue", "sell")
    net_c = col("netValue", "netvalue", "net")
    date_c = col("date")

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        cat = str(r[cat_c]).strip() if cat_c else ""
        buy = _to_float(r[buy_c]) if buy_c else None
        sell = _to_float(r[sell_c]) if sell_c else None
        net = _to_float(r[net_c]) if net_c else None
        if net is None and buy is not None and sell is not None:
            net = buy - sell
        rows.append(
            {
                "category": cat,
                "buy_value": buy,
                "sell_value": sell,
                "net_value": net,
                "date": str(r[date_c]) if date_c else None,
            }
        )
    return rows


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def _summarize_fii_dii(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fii = next((r for r in rows if "FII" in (r.get("category") or "").upper()), None)
    dii = next((r for r in rows if "DII" in (r.get("category") or "").upper()), None)
    parts = []
    if fii and fii.get("net_value") is not None:
        parts.append(f"FII/FPI net {fii['net_value']:+.2f} Cr")
    if dii and dii.get("net_value") is not None:
        parts.append(f"DII net {dii['net_value']:+.2f} Cr")
    date = (fii or dii or {}).get("date") if (fii or dii) else None
    return {
        "fii": fii,
        "dii": dii,
        "summary": "; ".join(parts) if parts else None,
        "as_of": date,
    }


def fetch_fii_dii_activity(
    cache: Optional[TTLCache] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Market-level cash FII/DII buy/sell/net for the latest available session."""
    key = "nse:fii_dii"
    if cache and not force_refresh:
        cached = cache.get(key)
        if cached and cached.get("status") == "ok":
            return cached

    errors: List[str] = []

    # --- nselib (function exists but not always re-exported) ---
    try:
        from nselib.capital_market.capital_market_data import fii_dii_trading_activity

        df = fii_dii_trading_activity()
        if not _df_empty(df):
            rows = _normalize_fii_dii_rows(pd.DataFrame(df))
            summary = _summarize_fii_dii(rows)
            out = {
                "status": "ok",
                "source": "nselib.capital_market.fii_dii_trading_activity",
                "rows": rows,
                **summary,
                "note": "Market-level cash segment activity (Rs Cr). Not per-stock ownership.",
            }
            if cache:
                cache.set(key, out)
            return out
        errors.append("nselib returned empty FII/DII frame")
    except Exception as exc:
        errors.append(f"nselib: {exc}")

    # --- nsepython fallback ---
    try:
        from nsepython import nse_fiidii

        df = nse_fiidii()
        if not _df_empty(df):
            rows = _normalize_fii_dii_rows(pd.DataFrame(df))
            summary = _summarize_fii_dii(rows)
            out = {
                "status": "ok",
                "source": "nsepython.nse_fiidii",
                "rows": rows,
                **summary,
                "note": "Market-level cash segment activity (Rs Cr). Not per-stock ownership.",
            }
            if cache:
                cache.set(key, out)
            return out
        errors.append("nsepython returned empty FII/DII frame")
    except Exception as exc:
        errors.append(f"nsepython: {exc}")

    return _empty("; ".join(errors) or "FII/DII unavailable")


def _symbols_from_constituent_df(df: pd.DataFrame) -> List[str]:
    cols = {c.lower(): c for c in df.columns}
    sym_col = cols.get("symbol") or cols.get("symbol name") or cols.get("trading_symbol")
    if not sym_col:
        for c in df.columns:
            if "symbol" in str(c).lower():
                sym_col = c
                break
    if not sym_col:
        return []
    out = []
    for v in df[sym_col].tolist():
        s = from_yahoo_symbol(str(v))
        if s:
            out.append(to_yahoo_symbol(s))
    return out


def fetch_index_constituents(
    index: str = "nifty50",
    cache: Optional[TTLCache] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    index keys: nifty50 | midcap150 | next50 | smallcap250 | equity_master
    Returns Yahoo-style .NS symbols.
    """
    index_key = (index or "nifty50").lower().strip()
    cache_key = f"nse:constituents:{index_key}"
    if cache and not force_refresh:
        cached = cache.get(cache_key)
        if cached and cached.get("status") == "ok":
            return cached

    nselib_map = {
        "nifty50": ("nifty50_equity_list", "Nifty 50"),
        "midcap150": ("niftymidcap150_equity_list", "Nifty Midcap 150"),
        "next50": ("niftynext50_equity_list", "Nifty Next 50"),
        "smallcap250": ("niftysmallcap250_equity_list", "Nifty Smallcap 250"),
        "equity_master": ("equity_list", "NSE equity list"),
    }

    errors: List[str] = []

    if index_key in nselib_map:
        fn_name, label = nselib_map[index_key]
        try:
            from nselib import capital_market

            fn = getattr(capital_market, fn_name)
            df = fn()
            if not _df_empty(df):
                symbols = _symbols_from_constituent_df(pd.DataFrame(df))
                if symbols:
                    out = {
                        "status": "ok",
                        "index": label,
                        "index_key": index_key,
                        "symbols": symbols,
                        "count": len(symbols),
                        "source": f"nselib.capital_market.{fn_name}",
                    }
                    if cache:
                        # write with longer logical life: store then rely on TTLCache default;
                        # for constituents we still use same cache file with its TTL.
                        cache.set(cache_key, out)
                    return out
            errors.append(f"nselib.{fn_name} empty")
        except Exception as exc:
            errors.append(f"nselib.{fn_name}: {exc}")

    # nsepython fallbacks (limited coverage)
    try:
        if index_key == "equity_master":
            from nsepython import nse_eq_symbols

            syms = nse_eq_symbols()
            if isinstance(syms, (list, tuple)) and syms:
                symbols = [to_yahoo_symbol(str(s)) for s in syms if s]
                out = {
                    "status": "ok",
                    "index": "NSE equity list",
                    "index_key": index_key,
                    "symbols": symbols,
                    "count": len(symbols),
                    "source": "nsepython.nse_eq_symbols",
                }
                if cache:
                    cache.set(cache_key, out)
                return out
            errors.append("nsepython.nse_eq_symbols empty")
        elif index_key == "nifty50":
            # Best-effort: some builds expose index constituents via quote helpers
            from nsepython import fnolist

            fl = fnolist()
            if isinstance(fl, (list, tuple)) and fl:
                # Not true Nifty 50 — skip inventing; record attempt only
                errors.append("nsepython has no dedicated Nifty 50 constituent list")
    except Exception as exc:
        errors.append(f"nsepython: {exc}")

    return _empty("; ".join(errors) or f"Constituents unavailable for {index_key}")


def fetch_equity_master(
    cache: Optional[TTLCache] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    return fetch_index_constituents("equity_master", cache=cache, force_refresh=force_refresh)


def _expiry_to_nselib(expiry: str) -> str:
    """Convert common expiry strings to dd-mm-YYYY for nselib.nse_live_option_chain."""
    s = (expiry or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except Exception:
            continue
    return s


def _expiry_to_display(expiry: str) -> str:
    s = (expiry or "").strip()
    for fmt in ("%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d-%b-%Y")
        except Exception:
            continue
    return s


def fetch_option_expiries(symbol: str) -> Dict[str, Any]:
    sym = from_yahoo_symbol(symbol)
    errors: List[str] = []

    try:
        from nselib import derivatives

        mapping = derivatives.expiry_dates_option_index()
        if isinstance(mapping, dict) and sym in mapping and mapping[sym]:
            return {
                "status": "ok",
                "symbol": sym,
                "expiryDates": list(mapping[sym]),
                "source": "nselib.derivatives.expiry_dates_option_index",
            }
        # equity / missing — try contract via live chain path below
        errors.append(f"nselib expiry map missing {sym}")
    except Exception as exc:
        errors.append(f"nselib expiries: {exc}")

    try:
        from nsepython import nse_expirydetails_by_symbol

        details = nse_expirydetails_by_symbol(sym)
        expiries = []
        if isinstance(details, dict):
            expiries = details.get("expiryDates") or details.get("ExpiryList") or []
        elif isinstance(details, (list, tuple)):
            expiries = list(details)
        if expiries:
            return {
                "status": "ok",
                "symbol": sym,
                "expiryDates": [str(e) for e in expiries],
                "source": "nsepython.nse_expirydetails_by_symbol",
            }
        errors.append("nsepython expiries empty")
    except Exception as exc:
        errors.append(f"nsepython expiries: {exc}")

    return _empty("; ".join(errors) or "No expiries", source="nselib/nsepython")


def _dataframe_chain_to_records(
    df: pd.DataFrame,
    symbol: str,
    expiry: Optional[str],
    underlying: Optional[float] = None,
    expiries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convert nselib option-chain DataFrame into NSE records.data CE/PE shape."""
    data = []
    display_exp = _expiry_to_display(expiry) if expiry else None
    for _, r in df.iterrows():
        strike = _to_float(r.get("Strike_Price"))
        if strike is None:
            continue
        exp = r.get("Expiry_Date") or display_exp
        ce = {
            "strikePrice": strike,
            "expiryDate": exp,
            "openInterest": _to_float(r.get("CALLS_OI")) or 0,
            "changeinOpenInterest": _to_float(r.get("CALLS_Chng_in_OI")) or 0,
            "totalTradedVolume": _to_float(r.get("CALLS_Volume")) or 0,
            "impliedVolatility": _to_float(r.get("CALLS_IV")),
            "lastPrice": _to_float(r.get("CALLS_LTP")),
            "buyPrice1": _to_float(r.get("CALLS_Bid_Price")),
            "sellPrice1": _to_float(r.get("CALLS_Ask_Price")),
        }
        pe = {
            "strikePrice": strike,
            "expiryDate": exp,
            "openInterest": _to_float(r.get("PUTS_OI")) or 0,
            "changeinOpenInterest": _to_float(r.get("PUTS_Chng_in_OI")) or 0,
            "totalTradedVolume": _to_float(r.get("PUTS_Volume")) or 0,
            "impliedVolatility": _to_float(r.get("PUTS_IV")),
            "lastPrice": _to_float(r.get("PUTS_LTP")),
            "buyPrice1": _to_float(r.get("PUTS_Bid_Price")),
            "sellPrice1": _to_float(r.get("PUTS_Ask_Price")),
        }
        data.append(
            {
                "strikePrice": strike,
                "expiryDates": exp,
                "expiryDate": exp,
                "CE": ce,
                "PE": pe,
            }
        )

    return {
        "records": {
            "data": data,
            "underlyingValue": underlying,
            "expiryDates": expiries or ([display_exp] if display_exp else []),
            "timestamp": str(df["Fetch_Time"].iloc[0]) if "Fetch_Time" in df.columns and len(df) else None,
        },
        "_meta": {
            "status": "ok",
            "symbol": symbol,
            "expiry": display_exp,
            "source": "nselib.derivatives.nse_live_option_chain",
            "source_page": "https://www.nseindia.com/option-chain",
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    }


def fetch_option_chain(
    symbol: str,
    expiry: Optional[str] = None,
    cache: Optional[TTLCache] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Return NSE-like option-chain JSON (records.data with CE/PE).
    Tries nselib, then nsepython, then returns unavailable (tertiary HTTP lives in nse_option_chain).
    """
    sym = from_yahoo_symbol(symbol)
    cache_key = f"nse:oc:{sym}:{expiry or 'nearest'}"
    if cache and not force_refresh:
        cached = cache.get(cache_key)
        if cached and cached.get("status") != "unavailable" and (cached.get("records") or {}).get("data"):
            return cached

    errors: List[str] = []
    exp_info = fetch_option_expiries(sym)
    expiries = (exp_info.get("expiryDates") or []) if exp_info.get("status") == "ok" else []
    chosen = expiry or (expiries[0] if expiries else None)
    display_exp = _expiry_to_display(chosen) if chosen else None

    # --- nselib: prefer raw JSON (keeps underlyingValue) ---
    if display_exp:
        try:
            from nselib.derivatives.get_func import get_nse_option_chain

            resp = get_nse_option_chain(sym, display_exp)
            payload = resp.json() if hasattr(resp, "json") else resp
            if isinstance(payload, dict) and (payload.get("records") or {}).get("data"):
                records = payload.setdefault("records", {})
                if expiries and not records.get("expiryDates"):
                    records["expiryDates"] = expiries
                payload["_meta"] = {
                    "status": "ok",
                    "symbol": sym,
                    "expiry": display_exp,
                    "source": "nselib.derivatives.get_nse_option_chain",
                    "source_page": "https://www.nseindia.com/option-chain",
                    "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
                if cache:
                    cache.set(cache_key, payload)
                return payload
            errors.append("nselib raw option chain empty")
        except Exception as exc:
            errors.append(f"nselib raw option chain: {exc}")

        # DataFrame fallback if raw path fails
        try:
            from nselib import derivatives

            df = derivatives.nse_live_option_chain(
                symbol=sym,
                expiry_date=_expiry_to_nselib(chosen),
                oi_mode="full",
            )
            if not _df_empty(df):
                out = _dataframe_chain_to_records(
                    pd.DataFrame(df),
                    symbol=sym,
                    expiry=chosen,
                    expiries=expiries,
                )
                if cache:
                    cache.set(cache_key, out)
                return out
            errors.append("nselib option chain DataFrame empty")
        except Exception as exc:
            errors.append(f"nselib option chain df: {exc}")

    # --- nsepython ---
    try:
        from nsepython import nse_optionchain_scrapper, option_chain

        raw = None
        try:
            raw = nse_optionchain_scrapper(sym)
        except Exception:
            raw = None
        if _df_empty(raw) or not (isinstance(raw, dict) and (raw.get("records") or {}).get("data")):
            try:
                raw = option_chain(sym)
            except Exception as exc:
                errors.append(f"nsepython.option_chain: {exc}")
                raw = None
        if isinstance(raw, dict) and (raw.get("records") or {}).get("data"):
            records = raw.setdefault("records", {})
            if expiries and not records.get("expiryDates"):
                records["expiryDates"] = expiries
            if chosen and records.get("data"):
                filtered = []
                for row in records["data"]:
                    exp = row.get("expiryDates") or row.get("expiryDate")
                    ce_exp = ((row.get("CE") or {}).get("expiryDate"))
                    if exp == chosen or ce_exp == chosen or not exp:
                        filtered.append(row)
                if filtered:
                    records["data"] = filtered
            raw["_meta"] = {
                "status": "ok",
                "symbol": sym,
                "expiry": display_exp,
                "source": "nsepython",
                "source_page": "https://www.nseindia.com/option-chain",
                "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            if cache:
                cache.set(cache_key, raw)
            return raw
        errors.append("nsepython option chain empty")
    except Exception as exc:
        errors.append(f"nsepython: {exc}")

    out = _empty("; ".join(errors) or "Option chain unavailable")
    out["symbol"] = sym
    out["expiry"] = chosen
    out["expiryDates"] = expiries
    return out


def resolve_universe(
    cache: Optional[TTLCache] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Prefer live NSE lists for Nifty 500 (Nifty 50 + Next 50 + Midcap 150 + Smallcap 250)."""
    warnings: List[str] = []
    sources: List[str] = []

    def _fetch_list(key: str) -> List[str]:
        res = fetch_index_constituents(key, cache=cache, force_refresh=force_refresh)
        if res.get("status") == "ok" and res.get("symbols"):
            src = res.get("source") or f"nselib {key}"
            if src not in sources:
                sources.append(src)
            return list(res["symbols"])
        else:
            warnings.append(f"{key} live list failed: {res.get('reason')}")
            return []

    nifty50 = _fetch_list("nifty50")
    next50 = _fetch_list("next50")
    midcap150 = _fetch_list("midcap150")
    smallcap250 = _fetch_list("smallcap250")

    return {
        "nifty50": nifty50,
        "next50": next50,
        "midcap150": midcap150,
        "smallcap250": smallcap250,
        "warnings": warnings,
        "sources": sources,
    }
