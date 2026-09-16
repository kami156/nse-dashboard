from typing import Dict, Any, List

# NSE_Alpha_Radar Universe Definitions (for tiers and sectors)
from .universe import SECTOR_INDICES, TIER_ORDER, TIER_LABELS, UNIVERSE, BENCHMARK

MAX_ALPHA_SECTORS = 4
LEADERS_PER_TIER = 2

def compute_alpha_leaderboards(all_cards: List[Dict[str, Any]], nse_coverage: Dict[str, Any], histories: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes alpha leaderboards by identifying top sectors by 4w return against Nifty 50,
    then picking top momentum stocks (by r4w) per market cap tier.
    """
    # 1. Get Nifty 50 baseline 4w return
    # We can get it from histories
    nifty_df = histories.get(BENCHMARK)
    nifty_r4w = 0.0
    nifty_r1w = 0.0
    if nifty_df is not None and not nifty_df.empty:
        close = nifty_df["Close"]
        if len(close) > 21:
            nifty_r4w = float(close.iloc[-1] / close.iloc[-21] - 1) * 100
        if len(close) > 6:
            nifty_r1w = float(close.iloc[-1] / close.iloc[-6] - 1) * 100

    # 2. Compute Sector Alphas
    sectors = []
    for name, ticker, key in SECTOR_INDICES:
        df = histories.get(ticker)
        if df is None or df.empty:
            continue
        close = df["Close"]
        r4w = float(close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 21 else 0.0
        r1w = float(close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 6 else 0.0
        alpha = r4w - nifty_r4w
        sectors.append({
            "name": name,
            "ticker": ticker,
            "alpha": alpha,
            "r4w": r4w,
            "r1w": r1w,
            "key": key
        })
    
    sectors.sort(key=lambda s: s["alpha"], reverse=True)
    positive_sectors = [s for s in sectors if s["alpha"] > 0]
    
    if positive_sectors:
        selected_sectors = positive_sectors[:MAX_ALPHA_SECTORS]
    elif sectors:
        selected_sectors = sectors[:1]
    else:
        selected_sectors = []
        
    # 3. Create stock map from all_cards
    stock_map = {}
    for card in all_cards:
        sym = card["symbol"].replace(".NS", "")
        tech = card.get("tech") or {}
        r4w = tech.get("momentum_1m_pct")
        r1w = tech.get("momentum_1w_pct")
        if r4w is not None and r1w is not None:
            stock_map[sym] = {
                "ticker": sym,
                "r4w": r4w,
                "r1w": r1w,
                "last_close": tech.get("last")
            }

    # 4. Pick leaders per tier for top sectors
    sector_details = []
    for sector in selected_sectors:
        tiers = []
        for tier in TIER_ORDER:
            candidates = UNIVERSE[sector["key"]].get(tier, [])
            rows = []
            for ticker in candidates:
                if ticker in stock_map:
                    rows.append(stock_map[ticker])
            
            rows.sort(key=lambda r: r["r4w"], reverse=True)
            tiers.append({
                "label": TIER_LABELS[tier],
                "leaders": rows[:LEADERS_PER_TIER],
                "scanned": len(candidates)
            })
        
        sector_details.append({
            "name": sector["name"],
            "tiers": tiers
        })

    return {
        "nifty": {
            "r4w": nifty_r4w,
            "r1w": nifty_r1w,
        },
        "sectors": sectors,
        "selected_count": len(selected_sectors),
        "sector_details": sector_details
    }
