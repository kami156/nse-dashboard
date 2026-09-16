"""Simple in-memory / disk TTL cache for market fetches."""
from __future__ import annotations

import json
import time
import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import pytz

def is_market_open(dt_ist: datetime.datetime) -> bool:
    """Check if NSE market is currently open (09:15 to 15:30 IST, Mon-Fri)."""
    if dt_ist.weekday() >= 5:
        return False
    return datetime.time(9, 15) <= dt_ist.time() <= datetime.time(15, 30)

def get_last_market_close(dt_ist: datetime.datetime) -> datetime.datetime:
    """Get the datetime of the most recent market close."""
    close_time = dt_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if dt_ist.weekday() >= 5:  # Weekend
        days_back = dt_ist.weekday() - 4  # Sat(5)->1 (Fri), Sun(6)->2 (Fri)
        return close_time - datetime.timedelta(days=days_back)
        
    if dt_ist < close_time:
        # Before today's close, so last close was yesterday (or Friday if Monday)
        days_back = 3 if dt_ist.weekday() == 0 else 1
        return close_time - datetime.timedelta(days=days_back)
        
    return close_time


class TTLCache:
    def __init__(self, cache_dir: Path, ttl_seconds: int = 300):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_seconds

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.cache_dir / f"{safe}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ts = payload.get("ts", 0)
            age = time.time() - ts
            
            # Base TTL (always valid if very fresh, handles active market hours)
            if age <= self.ttl:
                return payload.get("data")
                
            # Smart Cache: Check if data is still valid because market has been closed
            tz = pytz.timezone("Asia/Kolkata")
            now_ist = datetime.datetime.now(tz)
            
            if not is_market_open(now_ist):
                fetch_dt = datetime.datetime.fromtimestamp(ts, tz)
                last_close = get_last_market_close(now_ist)
                
                # If fetched at or after the last market close, no new data has been generated
                if fetch_dt >= last_close:
                    return payload.get("data")
                    
            return None
        except Exception:
            return None

    def set(self, key: str, data: Any) -> None:
        path = self._path(key)
        path.write_text(
            json.dumps({"ts": time.time(), "data": data}, default=str),
            encoding="utf-8",
        )

    def get_frame(self, key: str) -> Optional[pd.DataFrame]:
        data = self.get(key)
        if data is None:
            return None
        try:
            return pd.DataFrame(data["records"]).assign(
                **{data["index_name"]: pd.to_datetime(data["index"])}
            ).set_index(data["index_name"])
        except Exception:
            return None

    def set_frame(self, key: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            return
        payload = {
            "index_name": df.index.name or "Date",
            "index": [str(x) for x in df.index],
            "records": df.reset_index(drop=True).to_dict(orient="records"),
        }
        self.set(key, payload)

    def prune_stale(self, max_age_days: int = 30) -> int:
        """Delete cache files not written to in max_age_days.

        Universe composition changes over time (renames, delistings, index
        reshuffles), so cache files for symbols no longer fetched just sit
        there forever otherwise. Returns the number of files removed.
        """
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        try:
            for path in self.cache_dir.glob("*.json"):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except Exception:
                    continue
        except Exception:
            pass
        return removed
