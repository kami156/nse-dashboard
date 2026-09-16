"""Market breadth analytics from a stock universe."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import datetime

import pandas as pd

def get_market_delivery_percentage() -> Optional[float]:
    try:
        import nselib
        from nselib import capital_market
    except ImportError:
        return None
    
    for i in range(7):
        d = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime('%d-%m-%Y')
        try:
            df = capital_market.bhav_copy_with_delivery(d)
            if df is not None and not df.empty:
                df['DELIV_PER'] = df['DELIV_PER'].astype(str).str.strip().replace('-', '0').astype(float)
                eq_df = df[df['SERIES'] == 'EQ']
                return float(eq_df['DELIV_PER'].mean())
        except Exception:
            continue
    return None


def compute_breadth(histories: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    if not histories:
        return {
            "status": "unavailable",
            "reason": "No universe histories available for breadth",
            "breadth_score": None,
        }

    advances = declines = unchanged = 0
    new_highs = new_lows = 0
    volume_leaders: List[Dict[str, Any]] = []
    heat: List[Dict[str, Any]] = []

    for symbol, df in histories.items():
        if df is None or len(df) < 2:
            continue
        last = float(df["Close"].iloc[-1])
        prev = float(df["Close"].iloc[-2])
        chg_pct = (last / prev - 1) * 100 if prev else 0
        if chg_pct > 0.05:
            advances += 1
        elif chg_pct < -0.05:
            declines += 1
        else:
            unchanged += 1

        lookback = df.tail(252) if len(df) >= 60 else df
        hi = float(lookback["High"].max())
        lo = float(lookback["Low"].min())
        if last >= hi * 0.995:
            new_highs += 1
        if last <= lo * 1.005:
            new_lows += 1

        vol = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
        avg_vol = float(df["Volume"].iloc[-20:].mean()) if "Volume" in df.columns else 0
        volume_leaders.append(
            {
                "symbol": symbol,
                "change_pct": round(chg_pct, 2),
                "volume": vol,
                "volume_ratio": round(vol / avg_vol, 2) if avg_vol else None,
            }
        )
        heat.append({"symbol": symbol.replace(".NS", ""), "change_pct": round(chg_pct, 2)})

    volume_leaders.sort(key=lambda x: (x.get("volume_ratio") or 0), reverse=True)
    heat.sort(key=lambda x: x["change_pct"], reverse=True)

    thin_count = sum(1 for v in volume_leaders if (v.get("volume_ratio") or 1) < 0.7)

    total = advances + declines + unchanged
    adv_ratio = advances / total if total else 0.5
    breadth_score = round(adv_ratio * 100, 1)

    avg_del = get_market_delivery_percentage()
    if avg_del is not None:
        delivery_data = {
            "status": "ok",
            "reason": f"Nifty Universe Average Delivery: {avg_del:.2f}%",
        }
    else:
        delivery_data = {
            "status": "unavailable",
            "reason": "Delivery % requires NSE bhavcopy / exchange data (nselib fetch failed)",
        }

    return {
        "status": "ok",
        "universe_size": total,
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "new_highs": new_highs,
        "new_lows": new_lows,
        "delivery_percentage": delivery_data,
        "volume_leaders": volume_leaders[:15],
        "thin_count": thin_count,
        "heat_map": heat,
        "breadth_score": breadth_score,
        "summary": (
            f"Advances {advances} / Declines {declines} / Unchanged {unchanged}. "
            f"New highs {new_highs}, new lows {new_lows}. Breadth score {breadth_score}."
        ),
    }
