"""End-to-end dashboard generation pipeline."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analytics.breadth import compute_breadth
from src.analytics.fundamental import analyze_fundamental
from src.analytics.opportunities import build_risk_dashboard, discover_opportunities
from src.analytics.options import analyze_options
from src.analytics.regime import detect_regime
from src.analytics.scoring import build_stock_scorecard
from src.analytics.alpha import compute_alpha_leaderboards
from src.analytics.sectors import rank_sectors
from src.analytics.technical import analyze_technical
from src.data.cache import TTLCache
from src.data.fetchers import INDEX_MAP, MarketFetcher
from src.data.news_macro import economic_dashboard, fetch_news_intelligence
from src.data.nse_reference import fetch_fii_dii_activity, resolve_universe, to_yahoo_symbol
from src.insights.briefing import build_insights, executive_lists, one_minute_briefing
from src.render.v2.dashboard import render_html
from src.storage.snapshots import SnapshotStore, detect_changes


def load_watchlists(path: Path) -> Dict[str, List[str]]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _unique(seq: List[str]) -> List[str]:
    seen: Set[str] = set()
    out = []
    for s in seq:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _spark_series(hist, n: int = 60) -> List[float]:
    if hist is None or hist.empty or "Close" not in hist.columns:
        return []
    s = hist["Close"].dropna()
    if s.empty:
        return []
    return [round(float(x), 2) for x in s.tail(n).tolist()]


def _analyze_symbol(
    fetcher: MarketFetcher,
    symbol: str,
    hist,
    market_fii_dii: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    tech = analyze_technical(hist)
    info = fetcher.stock_info(symbol)
    fund = analyze_fundamental(info, market_fii_dii=market_fii_dii)
    return build_stock_scorecard(symbol, tech, fund, info)


def generate_dashboard(
    project_root: Optional[Path] = None,
    watchlists_path: Optional[Path] = None,
    force_refresh: bool = False,
    skip_news: bool = False,
) -> Dict[str, Any]:
    root = Path(project_root) if project_root else ROOT
    wl_path = Path(watchlists_path) if watchlists_path else root / "config" / "watchlists.yaml"
    out_dir = root / "output"
    snap_dir = out_dir / "snapshots"
    cache_dir = root / "output" / ".cache"
    out_dir.mkdir(parents=True, exist_ok=True)

    watchlists = load_watchlists(wl_path)
    cache = TTLCache(cache_dir, ttl_seconds=300)
    cache.prune_stale(max_age_days=30)  # drop cache entries for symbols no longer fetched
    fetcher = MarketFetcher(cache=cache, force_refresh=force_refresh)
    nse_warnings: List[str] = []
    nse_sources: List[str] = []

    # Fetch Nifty 500 constituents
    universe = resolve_universe(
        cache=cache,
        force_refresh=force_refresh,
    )
    nifty50 = universe["nifty50"]
    next50 = universe["next50"]
    midcap150 = universe["midcap150"]
    smallcap250 = universe["smallcap250"]
    nse_warnings.extend(universe.get("warnings") or [])
    nse_sources.extend(universe.get("sources") or [])
    
    fii_dii = fetch_fii_dii_activity(cache=cache, force_refresh=force_refresh)
    if fii_dii.get("status") == "ok":
        nse_sources.append(fii_dii.get("source") or "nselib/nsepython FII/DII")
    else:
        nse_warnings.append(f"FII/DII: {fii_dii.get('reason')}")

    equity_symbols = _unique(
        [s for s in nifty50 + next50 + midcap150 + smallcap250 if s.endswith(".NS") or ".NS" in s]
    )
    equity_symbols = [
        to_yahoo_symbol(s)
        for s in equity_symbols
        if s.upper() not in ("NIFTY", "BANKNIFTY")
    ]

    # Fetch market blocks (yfinance OHLC / fundamentals)
    indices = fetcher.fetch_indices()
    globals_data = fetcher.fetch_globals()

    # Histories for indices + equities (batch)
    index_tickers = [INDEX_MAP[k] for k in INDEX_MAP]
    all_tickers = _unique(index_tickers + equity_symbols)
    histories = fetcher.fetch_histories(all_tickers, period="1y")

    # Index technicals for NSE coverage section
    inst_block: Dict[str, Any]
    if fii_dii.get("status") == "ok":
        inst_block = {
            "status": "ok",
            "summary": fii_dii.get("summary"),
            "as_of": fii_dii.get("as_of"),
            "fii": fii_dii.get("fii"),
            "dii": fii_dii.get("dii"),
            "source": fii_dii.get("source"),
            "note": fii_dii.get("note"),
        }
    else:
        inst_block = {
            "status": "unavailable",
            "reason": fii_dii.get("reason") or "FII/DII unavailable",
        }

    nse_coverage = {}
    for name, ticker in INDEX_MAP.items():
        quote = indices.get(name, {})
        tech = analyze_technical(histories.get(ticker)) if ticker in histories else {
            "status": "unavailable",
            "reason": f"No history for {ticker}",
        }
        nse_coverage[name] = {
            "ticker": ticker,
            "quote": quote,
            "technical": tech,
            "institutional_activity": dict(inst_block),
            "ai_summary": tech.get("ai_summary")
            if tech.get("status") == "ok"
            else f"{name}: data unavailable ({tech.get('reason') or quote.get('reason')})",
        }

    # Breadth on nifty500
    breadth_universe = {
        s: histories[s]
        for s in _unique(nifty50 + next50 + midcap150 + smallcap250)
        if s in histories
    }
    breadth = compute_breadth(breadth_universe)

    sector_hist = {INDEX_MAP[k]: histories[INDEX_MAP[k]] for k in INDEX_MAP if INDEX_MAP[k] in histories}

    # Watchlist scorecards
    def score_list(symbols: List[str]) -> List[Dict[str, Any]]:
        cards = []
        for s in symbols:
            sym = to_yahoo_symbol(s)
            if sym.upper() in ("NIFTY", "BANKNIFTY") or not sym.endswith(".NS"):
                continue
            hist = histories.get(sym)
            cards.append(_analyze_symbol(fetcher, sym, hist, market_fii_dii=fii_dii))
        return cards

    # Evaluate all Nifty 500 stocks
    # Warm the .info cache in parallel first: turns ~N sequential Yahoo round
    # trips into N/8, score_list() below then reads from cache sequentially.
    fetcher.prefetch_infos(equity_symbols)
    all_cards = score_list(equity_symbols)
    
    # Now that we have all_cards, calculate sector rotation
    sector_rotation = rank_sectors(indices, sector_hist, INDEX_MAP, all_cards)

    # Compute Alpha & Momentum Leaderboards
    alpha_leaderboards = compute_alpha_leaderboards(all_cards, nse_coverage, histories)

    def is_long_term(c: Dict[str, Any]) -> bool:
        t = c.get("tech") or {}
        f = c.get("fund") or {}
        # Long Term: Value > 60 or Quality > 60, Long term uptrend (Price > 200 SMA)
        return (f.get("valuation_score", 0) > 60 or f.get("fundamental_score", 0) > 60) and t.get("trend") == "Uptrend"

    def is_swing(c: Dict[str, Any]) -> bool:
        t = c.get("tech") or {}
        # Swing Trading: Oversold RSI bounce or positive MACD histogram
        rsi = t.get("rsi", 50)
        macd_hist = t.get("macd_hist", 0)
        return (rsi < 45) or (macd_hist > 0 and rsi < 65)

    def is_weekly(c: Dict[str, Any]) -> bool:
        t = c.get("tech") or {}
        # Weekly: High 1-month momentum with strong volume
        return t.get("momentum_1m_pct", 0) > 5 and t.get("volume_ratio", 0) > 1.2

    def is_monthly(c: Dict[str, Any]) -> bool:
        t = c.get("tech") or {}
        # Monthly: Golden cross (50 > 200 SMA) and solid 3-month momentum
        sma50 = t.get("ema50", 0) or 0
        sma200 = t.get("ema200", 999999) or 999999
        return (sma50 > sma200) and (t.get("momentum_3m_pct", 0) > 10)

    # Watchlist scorecards replaced with Time Horizon Screeners
    horizon_screens = {
        "Long Term Opportunities": [c for c in all_cards if is_long_term(c)],
        "Swing Trading": [c for c in all_cards if is_swing(c)],
        "Weekly Opportunities": [c for c in all_cards if is_weekly(c)],
        "Monthly Opportunities": [c for c in all_cards if is_monthly(c)],
    }
    wl_cards = {
        name: sorted(cards, key=lambda x: x.get("overall_conviction", 0), reverse=True)[:20]
        for name, cards in horizon_screens.items()
    }

    # Deep horizon cohorts for the closing deliverables. The 20-row screener tables
    # above are too shallow to fill a 10-name list once names already listed are
    # removed, which is what made Top 10 Swing collapse into Top 10 Conviction.
    _COHORT_FIELDS = (
        "symbol", "name", "rating", "overall_conviction", "confidence_pct",
        "momentum_score", "fundamental_score", "valuation_score", "time_horizon",
    )
    horizon_cohorts = {
        name: [
            {k: c.get(k) for k in _COHORT_FIELDS}
            for c in sorted(cards, key=lambda x: x.get("overall_conviction", 0), reverse=True)[:60]
        ]
        for name, cards in horizon_screens.items()
    }

    # Opportunity discovery across the entire universe
    discovery_pool = all_cards
    opportunities = discover_opportunities(discovery_pool)
    opportunity_cards = discovery_pool

    nifty_tech = (nse_coverage.get("Nifty 50") or {}).get("technical")
    regime = detect_regime(indices, globals_data, breadth, nifty_tech)

    # We don't have custom options watchlist anymore, use Nifty/BankNifty as default
    options = analyze_options(["NIFTY", "BANKNIFTY"])
    if options.get("warnings"):
        nse_warnings.extend(options["warnings"])
    if options.get("status") == "ok":
        nse_sources.append(
            "nselib (primary) / nsepython (fallback) / NSE HTTP tertiary for option chain"
        )

    news = {"items": [], "note": "Skipped"} if skip_news else fetch_news_intelligence()
    economy = economic_dashboard(globals_data)
    risk_dashboard = build_risk_dashboard(regime, breadth, globals_data, sector_rotation, all_cards)

    # Global impact narrative
    impact_bits = []
    for k in ["S&P 500", "Nasdaq", "Dollar Index", "USD/INR", "Crude Oil", "VIX (US)", "Gift Nifty"]:
        q = globals_data.get(k) or {}
        if q.get("status") == "ok" and q.get("change_pct") is not None:
            impact_bits.append(f"{k} {q['change_pct']:+.2f}%")
    global_impact = (
        "Global cue summary: " + "; ".join(impact_bits) + ". "
        "Strong USD / rising yields / crude spikes typically pressure INR and domestic risk assets; "
        "confirm via next cash-session breadth and Bank Nifty leadership."
        if impact_bits
        else "Insufficient global quotes to assess impact on Indian markets."
    )

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    payload: Dict[str, Any] = {
        "generated_at": generated_at,
        "indices": indices,
        "globals": globals_data,
        "global_impact": global_impact,
        "nse_coverage": nse_coverage,
        "fii_dii": fii_dii,
        "universe": {
            "nifty50_count": len(nifty50),
            "midcap_count": len(midcap150),
            "sources": universe.get("sources") or [],
        },
        "breadth": breadth,
        "sector_rotation": sector_rotation,
        "watchlists": wl_cards,
        "horizon_cohorts": horizon_cohorts,
        "options": options,
        "opportunities": opportunities,
        "opportunity_cards": [
            {k: v for k, v in c.items() if k not in ("tech", "fund")} for c in opportunity_cards
        ],
        "news": news,
        "economy": economy,
        "risk_dashboard": risk_dashboard,
        "regime": regime,
        "alpha_leaderboards": alpha_leaderboards,
        "sparklines": {
            "sentiment": _spark_series(histories.get("^NSEI"), n=60),
            "bull_bear": _spark_series(histories.get("^NSEI"), n=120),
            "risk": _spark_series(histories.get("^INDIAVIX"), n=60),
            "regime": _spark_series(histories.get("^NSEI"), n=250),
        },
        "warnings": list(fetcher.warnings) + nse_warnings,
        "sources": list(
            dict.fromkeys(
                fetcher.sources
                + [
                    "Yahoo Finance via yfinance (prices, fundamentals)",
                    "nselib (primary) / nsepython (fallback) for FII/DII, constituents, option chain",
                    "Google News RSS (headline intelligence; optional)",
                    "Computed indicators (RSI/MACD/EMA/ADX/ATR/Bollinger/Supertrend/pivots)",
                ]
                + nse_sources
            )
        ),
    }

    # Slim snapshot for change detection (avoid huge hist)
    snap_store = SnapshotStore(snap_dir)
    previous = snap_store.load_previous()
    slim_snap = {
        "generated_at": generated_at,
        "indices": {
            k: {kk: vv for kk, vv in v.items() if kk in ("ticker", "status", "last", "change_pct")}
            for k, v in indices.items()
        },
        "sector_rotation": {
            "ranked": [
                {"sector": r.get("sector"), "rank": r.get("rank"), "rank_score": r.get("rank_score")}
                for r in (sector_rotation.get("ranked") or [])
            ]
        },
        "watchlists": {
            name: [
                {
                    "symbol": c["symbol"],
                    "rating": c.get("rating"),
                    "overall_conviction": c.get("overall_conviction"),
                }
                for c in cards
            ]
            for name, cards in wl_cards.items()
        },
        "opportunities": opportunities,
        "breadth": {
            "breadth_score": breadth.get("breadth_score"),
            "volume_leaders": (breadth.get("volume_leaders") or [])[:10],
        },
        "regime": {
            "market_regime": regime.get("market_regime"),
            "bull_score": regime.get("bull_score"),
            "market_risk_score": regime.get("market_risk_score"),
        },
    }
    changes = detect_changes(slim_snap, previous)
    snap_store.save(slim_snap)

    payload["hourly_changes"] = changes
    payload["briefing"] = one_minute_briefing(payload)
    payload["insights"] = build_insights(payload)
    payload["executive_lists"] = executive_lists(payload)

    # Top drivers / opportunities / risks for exec summary
    payload["exec_summary"] = {
        "market_sentiment": regime.get("market_sentiment"),
        "bull_bear": {"bull": regime.get("bull_score"), "bear": regime.get("bear_score")},
        "market_risk_score": regime.get("market_risk_score"),
        "market_risk_label": regime.get("market_risk_label"),
        "top_drivers": regime.get("drivers") or [],
        "top_opportunities": [
            f"{o['symbol'].replace('.NS','')}: {o.get('category')}" for o in opportunities[:5]
        ],
        "top_risks": [i.get("detail") for i in (risk_dashboard.get("items") or []) if i.get("level") in ("High", "Critical", "Moderate")][:5],
        "one_minute_briefing": payload["briefing"],
    }

    html = render_html(payload)
    html_path = out_dir / "dashboard.html"
    html_path.write_text(html, encoding="utf-8")
    payload["html_path"] = str(html_path)
    return payload
