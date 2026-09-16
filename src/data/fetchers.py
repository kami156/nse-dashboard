"""Market data fetchers via yfinance (and best-effort public endpoints)."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from .cache import TTLCache

# Max concurrent network fetches. yfinance/Yahoo tolerates modest parallelism;
# keep this conservative to avoid tripping rate limits across ~1500-2000 symbols.
MAX_FETCH_WORKERS = 8


INDEX_MAP = {
    "Nifty 50": "^NSEI",
    "Nifty Bank": "^NSEBANK",
    "Nifty IT": "^CNXIT",
    "Nifty Pharma": "^CNXPHARMA",
    "Nifty Auto": "^CNXAUTO",
    "Nifty Metal": "^CNXMETAL",
    "Nifty FMCG": "^CNXFMCG",
    "Nifty Energy": "^CNXENERGY",
    "Nifty Realty": "^CNXREALTY",
    "Nifty PSU Bank": "^CNXPSUBANK",
    "Nifty Media": "^CNXMEDIA",
    "India VIX": "^INDIAVIX",
    # Proxies / alternatives when direct NSE sector tickers fail
    "Nifty Midcap 100": "^NSMIDCP",  # NIFTY MIDCAP 100
    "Nifty Midcap": "^NSEMDCP50",
    "Nifty Smallcap": "NIFTYSMLCAP250.NS",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
}

GLOBAL_MAP = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow Jones": "^DJI",
    "FTSE 100": "^FTSE",
    "DAX": "^GDAXI",
    "CAC 40": "^FCHI",
    "Nikkei 225": "^N225",
    "Hang Seng": "^HSI",
    "Shanghai Comp": "000001.SS",
    "Dollar Index": "DX-Y.NYB",
    "USD/INR": "INR=X",
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Crude Oil": "CL=F",
    "US 10Y Yield": "^TNX",
    "VIX (US)": "^VIX",
}

# Special fetcher for Gift Nifty (not on Yahoo Finance)
def _fetch_gift_nifty() -> Dict[str, Any]:
    import urllib.request
    import re
    
    try:
        req = urllib.request.Request(
            'https://www.moneycontrol.com/indian-indices/gift-nifty-9.html',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        
        price_match = re.search(r'id="sp_val">([^<]+)</span>', html)
        ch_prch_match = re.search(r'id="sp_ch_prch"[^>]*>.*?</span>\s*([0-9.\-]+)\s*\(\s*([0-9.\-]+)%\)', html, re.DOTALL)
        
        if not price_match:
            return {"ticker": "GIFT NIFTY", "status": "unavailable", "reason": "Failed to parse price"}
            
        price = float(price_match.group(1).replace(',', ''))
        chg = float(ch_prch_match.group(1).replace(',', '')) if ch_prch_match else None
        pct = float(ch_prch_match.group(2).replace(',', '')) if ch_prch_match else None
        
        # If it has a reddownarow or similar, Moneycontrol includes the sign in the text, so the regex captures it.
        return {
            "ticker": "GIFT NIFTY",
            "status": "ok",
            "last": price,
            "change": chg,
            "change_pct": pct,
            "volume": None,
            "high": None,
            "low": None
        }
    except Exception as exc:
        return {"ticker": "GIFT NIFTY", "status": "unavailable", "reason": str(exc)}



@dataclass
class FetchResult:
    data: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)


def _fallback_history_nselib(ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    from nselib import capital_market
    
    period_map = {
        "1mo": "1M",
        "3mo": "3M",
        "6mo": "6M",
        "1y": "1Y",
        "1d": "1W",
        "5d": "1W",
    }
    nselib_period = period_map.get(period, "6M")
    symbol = ticker.replace(".NS", "").strip()
    
    try:
        df = capital_market.price_volume_and_deliverable_position_data(symbol, period=nselib_period)
        if df is None or df.empty:
            return None
        
        df['Date'] = pd.to_datetime(df['Date'], format='%d-%b-%Y', errors='coerce')
        df = df.dropna(subset=['Date']).sort_values('Date')
        df.set_index('Date', inplace=True)
        
        for col in ['OpenPrice', 'HighPrice', 'LowPrice', 'ClosePrice', 'TotalTradedQuantity']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '').astype(float)
        
        df = df.rename(columns={
            'OpenPrice': 'Open',
            'HighPrice': 'High',
            'LowPrice': 'Low',
            'ClosePrice': 'Close',
            'TotalTradedQuantity': 'Volume'
        })
        
        req_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df[[c for c in req_cols if c in df.columns]]
        
        if not df.empty:
            df.index = df.index.tz_localize('Asia/Kolkata')
            
        return df
    except Exception:
        return None


def _safe_history(ticker: str, period: str = "6mo", interval: str = "1d") -> Tuple[Optional[pd.DataFrame], Optional[str], str]:
    import logging
    import os
    from contextlib import redirect_stderr
    from io import StringIO

    # yfinance prints HTTP 404 / "possibly delisted" to stderr for missing symbols
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    
    df = None
    err = None
    source = "Yahoo Finance (yfinance)"
    
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull, redirect_stderr(devnull):
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=True)
        
        if df is not None and not df.empty:
            df = df.rename(columns=str.title)
            
            # Check for bad yfinance data (NaN close or zero volume for equities)
            is_bad_data = pd.isna(df["Close"].iloc[-1])
            if is_bad_data and ticker.endswith(".NS"):
                df = None  # Force fallback
    except Exception as exc:
        err = f"{ticker}: {exc}"
        df = None

    # Fallback for Indian Equities
    if (df is None or df.empty) and ticker.endswith(".NS"):
        fallback_df = _fallback_history_nselib(ticker, period)
        if fallback_df is not None and not fallback_df.empty:
            df = fallback_df
            err = None
            source = "NSE Official (nselib)"

    if df is None or df.empty:
        if not err:
            err = f"No history for {ticker}"
        return None, err, source

    return df, None, source


def _last_change(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or len(df) < 2:
        last = float(df["Close"].iloc[-1]) if df is not None and not df.empty else None
        return {
            "last": last,
            "prev": None,
            "change": None,
            "change_pct": None,
            "volume": float(df["Volume"].iloc[-1]) if df is not None and "Volume" in df.columns and not df.empty else None,
            "high": float(df["High"].iloc[-1]) if df is not None and not df.empty else None,
            "low": float(df["Low"].iloc[-1]) if df is not None and not df.empty else None,
        }
    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])
    chg = last - prev
    return {
        "last": last,
        "prev": prev,
        "change": chg,
        "change_pct": (chg / prev * 100.0) if prev else None,
        "volume": float(df["Volume"].iloc[-1]) if "Volume" in df.columns else None,
        "high": float(df["High"].iloc[-1]),
        "low": float(df["Low"].iloc[-1]),
    }


class MarketFetcher:
    def __init__(self, cache: Optional[TTLCache] = None, force_refresh: bool = False):
        self.cache = cache
        self.force_refresh = force_refresh
        self.warnings: List[str] = []
        self.sources: List[str] = ["Yahoo Finance (yfinance)"]
        self._lock = threading.Lock()

    def _add_warning(self, msg: str) -> None:
        with self._lock:
            self.warnings.append(msg)

    def _add_source(self, src: str) -> None:
        with self._lock:
            if src not in self.sources:
                self.sources.append(src)

    def history(self, ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
        key = f"hist:{ticker}:{period}"
        if self.cache and not self.force_refresh:
            cached = self.cache.get_frame(key)
            if cached is not None and not cached.empty:
                return cached
        df, err, source = _safe_history(ticker, period=period)
        if err:
            self._add_warning(err)
            return None

        self._add_source(source)

        if self.cache and df is not None:
            self.cache.set_frame(key, df)
        return df

    def quote_map(self, mapping: Dict[str, str], period: str = "5d") -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for name, ticker in mapping.items():
            df = self.history(ticker, period=period)
            if df is None or df.empty:
                out[name] = {
                    "ticker": ticker,
                    "status": "unavailable",
                    "reason": f"No data for {ticker}",
                }
                continue
            meta = _last_change(df)
            out[name] = {
                "ticker": ticker,
                "status": "ok",
                **meta,
            }
        return out

    def stock_info(self, ticker: str) -> Dict[str, Any]:
        key = f"info:{ticker}"
        if self.cache and not self.force_refresh:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        try:
            info = yf.Ticker(ticker).info or {}
            slim = {
                "symbol": ticker,
                "shortName": info.get("shortName") or info.get("longName") or ticker,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "marketCap": info.get("marketCap"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "priceToBook": info.get("priceToBook"),
                "returnOnEquity": info.get("returnOnEquity"),
                "returnOnAssets": info.get("returnOnAssets"),
                "profitMargins": info.get("profitMargins"),
                "operatingMargins": info.get("operatingMargins"),
                "revenueGrowth": info.get("revenueGrowth"),
                "earningsGrowth": info.get("earningsGrowth"),
                "debtToEquity": info.get("debtToEquity"),
                "freeCashflow": info.get("freeCashflow"),
                "heldPercentInsiders": info.get("heldPercentInsiders"),
                "heldPercentInstitutions": info.get("heldPercentInstitutions"),
                "dividendYield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
                "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
                "recommendationKey": info.get("recommendationKey"),
            }
            if self.cache:
                self.cache.set(key, slim)
            return slim
        except Exception as exc:
            self._add_warning(f"info {ticker}: {exc}")
            return {"symbol": ticker, "status": "unavailable", "reason": str(exc)}

    def prefetch_infos(self, tickers: List[str], max_workers: int = MAX_FETCH_WORKERS) -> None:
        """Warm the .info cache for many tickers in parallel.

        stock_info() itself stays single-threaded/cache-first, so calling this
        before a sequential scoring loop turns ~N sequential network round
        trips into N/max_workers, with no change to per-symbol logic.
        """
        uniq = list(dict.fromkeys(t for t in tickers if t))
        if not uniq:
            return
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(self.stock_info, uniq))

    def fetch_indices(self) -> Dict[str, Dict[str, Any]]:
        return self.quote_map(INDEX_MAP, period="6mo")

    def fetch_globals(self) -> Dict[str, Dict[str, Any]]:
        out = self.quote_map(GLOBAL_MAP, period="5d")
        
        # Fetch Gift Nifty specially
        gift_nifty = _fetch_gift_nifty()
        out["Gift Nifty"] = gift_nifty
        if gift_nifty["status"] == "ok":
            if "Moneycontrol" not in self.sources:
                self.sources.append("Moneycontrol")
        
        return out

    def fetch_histories(
        self, tickers: List[str], period: str = "6mo", max_workers: int = MAX_FETCH_WORKERS
    ) -> Dict[str, pd.DataFrame]:
        uniq = list(dict.fromkeys(t for t in tickers if t))
        result: Dict[str, pd.DataFrame] = {}
        result_lock = threading.Lock()

        def _one(t: str) -> None:
            df = self.history(t, period=period)
            if df is not None and not df.empty:
                with result_lock:
                    result[t] = df

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(_one, uniq))
        return result
