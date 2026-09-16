"""Render a self-contained Apple-inspired HTML dashboard."""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Optional


def _e(val: Any) -> str:
    if val is None:
        return "-"
    return html.escape(str(val))


def _fmt_num(val: Any, digits: int = 2) -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):,.{digits}f}"
    except Exception:
        return _e(val)


def _fmt_conf(val: Any) -> Dict[str, Any]:
    """Format a confidence_pct value as a table cell dict for _table(),
    right-aligned server-side and suffixed with % to match the "Conf%" header."""
    if val is None:
        return {"html": "-", "num": True}
    try:
        return {"html": f"{float(val):.1f}%", "num": True}
    except Exception:
        return {"html": _e(val), "num": True}


def _fmt_pct(val: Any) -> str:
    if val is None:
        return "-"
    try:
        v = float(val)
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    except Exception:
        return _e(val)


def _fmt_inr(val: Any) -> str:
    if val is None:
        return "-"
    try:
        return f"₹{float(val):,.0f}"
    except Exception:
        return _e(val)


def _chg_class(val: Any) -> str:
    try:
        v = float(val)
        if v > 0:
            return "up"
        if v < 0:
            return "down"
    except Exception:
        pass
    return ""


def _score_badge(score: Any) -> str:
    if score is None:
        return '<span class="badge muted">n/a</span>'
    try:
        s = float(score)
    except Exception:
        return '<span class="badge muted">n/a</span>'
    cls = "good" if s >= 65 else "mid" if s >= 45 else "bad"
    return f'<span class="badge {cls}">{s:.0f}</span>'


def _rating_badge(rating: str) -> str:
    r = rating or "Hold"
    mapping = {
        "Strong Buy": "good",
        "Buy": "good",
        "Accumulate": "mid",
        "Hold": "mid",
        "Reduce": "bad",
        "Sell": "bad",
        "Strong Sell": "bad",
    }
    return f'<span class="badge {mapping.get(r, "mid")}">{_e(r)}</span>'


def _heat_cell(h: Dict[str, Any]) -> str:
    sym = _e(h.get("symbol"))
    pct = h.get("change_pct")
    try:
        v = float(pct)
    except (TypeError, ValueError):
        v = 0.0
    direction = "up" if v > 0 else "down" if v < 0 else ""
    intensity = round(min(abs(v) / 5.0, 1.0), 2)
    return (
        f"<div class='heat {direction}' style='--heat:{intensity:.2f}' "
        f"title='{sym}: {_fmt_pct(pct)}'>"
        f"<span>{sym}</span><strong>{_fmt_pct(pct)}</strong></div>"
    )


def _sparkline(values: Any, invert: bool = False) -> str:
    if not values:
        return ""
    try:
        vals = [float(v) for v in values if v is not None]
    except (TypeError, ValueError):
        return ""
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1.0
    n = len(vals)
    W, H, PAD = 100.0, 30.0, 2.0
    coords = []
    for i, v in enumerate(vals):
        x = (i / (n - 1)) * W
        y = H - PAD - ((v - mn) / rng) * (H - 2 * PAD)
        coords.append((x, y))
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
    area = f"{pts} {W:.1f},{H:.1f} 0,{H:.1f}"
    first, last = vals[0], vals[-1]
    up = (last >= first) != bool(invert)
    cls = "up" if up else "down"
    if first:
        delta = (last - first) / first * 100.0
    else:
        delta = 0.0
    title = f"{'▲' if up else '▼'} {delta:+.2f}% over {n} sessions"
    return (
        f"<svg class='spark {cls}' viewBox='0 0 {W} {H}' preserveAspectRatio='none' "
        f"role='img' aria-label='{_e(title)}'><title>{_e(title)}</title>"
        f"<polygon points='{area}' fill='currentColor' fill-opacity='0.12'/>"
        f"<polyline points='{pts}' fill='none' stroke='currentColor' stroke-width='1.7' "
        f"stroke-linejoin='round' stroke-linecap='round' vector-effect='non-scaling-stroke'/>"
        f"</svg>"
    )


def _interactive_chart(values: Any, elem_id: str, label: str = "", unit: str = "") -> str:
    """Dependency-free hover/tooltip line chart. Renders a placeholder <div>;
    the actual <svg> path is drawn client-side by the chart JS below (see
    `.chart-wrap` init), which also owns the crosshair/tooltip interaction."""
    if not values:
        return '<p class="muted">No chart data</p>'
    try:
        vals = [round(float(v), 4) for v in values if v is not None]
    except (TypeError, ValueError):
        return '<p class="muted">No chart data</p>'
    if len(vals) < 2:
        return '<p class="muted">No chart data</p>'
    up = vals[-1] >= vals[0]
    cls = "up" if up else "down"
    data_attr = _e(json.dumps(vals))
    return (
        f"<div class='chart-wrap {cls}' id='{_e(elem_id)}' data-values='{data_attr}' "
        f"data-label='{_e(label)}' data-unit='{_e(unit)}'>"
        f"<svg class='chart-svg' viewBox='0 0 600 220' preserveAspectRatio='none' role='img' "
        f"aria-label='{_e(label)} trend chart'></svg>"
        f"<div class='chart-tooltip'></div>"
        f"</div>"
    )


NUM_HEADERS = {"Conf%"}


def _table(headers: List[str], rows: List[List[Any]], table_id: str = "") -> str:
    tid = f' id="{_e(table_id)}"' if table_id else ""
    def _th(i: int, h: str) -> str:
        cls = " class='num'" if h in NUM_HEADERS else ""
        return f"<th data-sort-col='{i}'{cls}>{_e(h)}</th>"

    thead = "".join(_th(i, h) for i, h in enumerate(headers))
    body_rows = []
    for row in rows:
        tds = []
        for cell in row:
            if isinstance(cell, dict) and "html" in cell:
                cs = f" colspan='{cell['colspan']}'" if cell.get("colspan") else ""
                cls = " class='num'" if cell.get("num") else ""
                tds.append(f"<td{cs}{cls}>{cell['html']}</td>")
            else:
                tds.append(f"<td>{cell}</td>")
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    if not body_rows:
        body_rows.append(f"<tr><td colspan='{len(headers)}' class='muted'>No data</td></tr>")
    return f"""
    <div class="table-wrap">
      <table class="data-table sortable"{tid}>
        <thead><tr>{thead}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """


def _card(title: str, body: str, subtitle: str = "") -> str:
    sub = f'<p class="card-sub">{_e(subtitle)}</p>' if subtitle else ""
    return f'<article class="glass card"><h3>{_e(title)}</h3>{sub}{body}</article>'


def _kv(items: List[tuple]) -> str:
    lis = "".join(
        f"<li><span>{_e(k)}</span><strong class='{_chg_class(v) if isinstance(v, (int, float)) else ''}'>{_e(v)}</strong></li>"
        for k, v in items
    )
    return f'<ul class="kv">{lis}</ul>'


def _howto(title: str, items: List[str]) -> str:
    lis = "".join(f"<li>{_e(i)}</li>" for i in items)
    return f'<div class="howto"><h4>{_e(title)}</h4><ol>{lis}</ol></div>'


def render_html(payload: Dict[str, Any]) -> str:
    exec_s = payload.get("exec_summary") or {}
    regime = payload.get("regime") or {}
    globals_data = payload.get("globals") or {}
    indices = payload.get("indices") or {}
    nse = payload.get("nse_coverage") or {}
    breadth = payload.get("breadth") or {}
    sectors = payload.get("sector_rotation") or {}
    alpha_lb = payload.get("alpha_leaderboards") or {}
    watchlists = payload.get("watchlists") or {}
    options = payload.get("options") or {}
    opportunities = payload.get("opportunities") or []
    news = payload.get("news") or {}
    economy = payload.get("economy") or {}
    risk_dash = payload.get("risk_dashboard") or {}
    insights = payload.get("insights") or {}
    changes = payload.get("hourly_changes") or {}
    lists = payload.get("executive_lists") or {}
    spark = payload.get("sparklines") or {}
    warnings = payload.get("warnings") or []
    sources = payload.get("sources") or []
    generated_at = payload.get("generated_at") or ""

    # --- Section builders ---
    # 1 Executive
    drivers = "".join(f"<li>{_e(d)}</li>" for d in (exec_s.get("top_drivers") or [])[:8]) or "<li class='muted'>None</li>"
    tops_opp = "".join(f"<li>{_e(d)}</li>" for d in (exec_s.get("top_opportunities") or [])) or "<li class='muted'>None</li>"
    tops_risk = "".join(f"<li>{_e(d)}</li>" for d in (exec_s.get("top_risks") or [])) or "<li class='muted'>None</li>"
    exec_html = f"""
    <section id="executive" class="section">
      <h2>1. Executive Summary</h2>
      {_howto("How to use", [
        "Read the four stat tiles first — Sentiment, Bull/Bear, Market Risk, Regime — for the one-glance macro posture.",
        "Top Drivers / Opportunities / Risks are ranked by score; treat them as a daily checklist, not a forecast.",
        "The one-minute briefing is rule-based from the same feeds — confirm any call against the sections below.",
      ])}
      <div class="grid stats">
        <div class="glass stat"><span>Sentiment</span><strong>{_e(exec_s.get('market_sentiment'))}</strong>{_sparkline(spark.get('sentiment'))}</div>
        <div class="glass stat"><span>Bull / Bear</span><strong>{_fmt_num(exec_s.get('bull_bear',{}).get('bull'),1)} / {_fmt_num(exec_s.get('bull_bear',{}).get('bear'),1)}</strong>{_sparkline(spark.get('bull_bear'))}</div>
        <div class="glass stat"><span>Market Risk</span><strong>{_e(exec_s.get('market_risk_label'))} ({_fmt_num(exec_s.get('market_risk_score'),1)})</strong>{_sparkline(spark.get('risk'), invert=True)}</div>
        <div class="glass stat"><span>Regime</span><strong>{_e(regime.get('market_regime'))}</strong>{_sparkline(spark.get('regime'))}</div>
      </div>
      {_card(
          "Nifty 50 — last ~250 sessions",
          _interactive_chart(spark.get('regime'), 'nifty-trend-chart', label='Nifty 50', unit=''),
          "Hover to inspect any session's close. Daily closes via yfinance; no intraday ticks.",
      )}
      <div class="grid three">
        {_card("Top Drivers", f"<ul>{drivers}</ul>")}
        {_card("Top Opportunities", f"<ul>{tops_opp}</ul>")}
        {_card("Top Risks", f"<ul>{tops_risk}</ul>")}
      </div>
      {_card("One-minute AI Briefing", f"<p class='brief'>{_e(exec_s.get('one_minute_briefing'))}</p>")}
      {_card("Delivery %", f"<p class='muted'>{_e((breadth.get('delivery_percentage') or {}).get('reason') or (breadth.get('delivery_percentage') or {}).get('status'))}</p>")}
    </section>
    """

    # 2 Global
    g_rows = []
    for name, q in globals_data.items():
        if q.get("status") != "ok":
            g_rows.append([
                _e(name),
                _e(q.get("ticker")),
                {"html": f"<span class='muted'>Unavailable — {_e(q.get('reason'))}</span>", "colspan": 3},
            ])
        else:
            g_rows.append([
                _e(name),
                _e(q.get("ticker")),
                _fmt_num(q.get("last")),
                {"html": f"<span class='{_chg_class(q.get('change_pct'))}'>{_fmt_pct(q.get('change_pct'))}</span>"},
                _fmt_num(q.get("volume"), 0),
            ])
    global_html = f"""
    <section id="global" class="section">
      <h2>2. Global Markets</h2>
      {_howto("How to use", [
        "Scan Change% for overnight cues (USD/INR, US yields, crude, US VIX) that set the tone for the Indian cash open.",
        "Green = up, red = down; 'Unavailable — reason' rows are labeled, never inferred.",
        "Read the Impact note to link global moves to INR/domestic risk, then confirm with Breadth and Bank Nifty.",
      ])}
      {_table(["Market", "Ticker", "Last", "Change", "Volume"], g_rows, "global-table")}
      {_card("Impact on Indian Markets", f"<p>{_e(payload.get('global_impact'))}</p>")}
    </section>
    """

    # 3 NSE Coverage
    nse_rows = []
    for name, block in nse.items():
        q = block.get("quote") or {}
        t = block.get("technical") or {}
        nse_rows.append([
            _e(name),
            _fmt_num(q.get("last")),
            {"html": f"<span class='{_chg_class(q.get('change_pct'))}'>{_fmt_pct(q.get('change_pct'))}</span>"},
            _e(t.get("trend")),
            _e(t.get("momentum")),
            _fmt_num(t.get("support")),
            _fmt_num(t.get("resistance")),
            _fmt_num(t.get("relative_strength"), 1),
            _fmt_num(t.get("volume_ratio"), 2),
            {"html": _score_badge(t.get("technical_score"))},
            _e(
                (block.get("institutional_activity") or {}).get("summary")
                or (block.get("institutional_activity") or {}).get("status")
            ),
            _e(block.get("ai_summary")),
        ])
    nse_html = f"""
    <section id="nse" class="section">
      <h2>3. Complete NSE Coverage</h2>
      <p class="note">Index OHLC via yfinance. Institutional activity is market-level cash FII/DII from nselib/nsepython (not per-stock ownership).</p>
      {_howto("How to use", [
        "Trend / Momentum / Support / Resistance give the index-level technical picture at a glance.",
        "Inst. Activity is market-level FII/DII cash flow — read it as context, not per-stock ownership.",
        "Click Tech Score to rank index leadership; higher = stronger technicals.",
      ])}
      {_table(["Index","Last","Chg%","Trend","Momentum","Support","Resistance","RS","Vol Ratio","Tech Score","Inst. Activity","AI Summary"], nse_rows, "nse-table")}
    </section>
    """

    # 4 Breadth
    heat = breadth.get("heat_map") or []
    heat = [h for h in heat if h.get("change_pct", 0) > 1.0]
    heat = sorted(heat, key=lambda x: x.get("change_pct", 0), reverse=True)[:50]
    heat_cells = "".join(_heat_cell(h) for h in heat)
    heat_legend = (
        "<div class='heat-legend'><span>Move size</span>"
        "<div class='heat-legend-scale'>"
        + "".join(f"<i class='up' style='--heat:{v:.2f}'></i>" for v in (0.2, 0.4, 0.6, 0.8, 1.0))
        + "</div><span>1% &rarr; 5%+ gainers</span></div>"
    ) if heat_cells else ""
    vol_rows = [
        [_e(v.get("symbol")), _fmt_pct(v.get("change_pct")), _fmt_num(v.get("volume"), 0), _fmt_num(v.get("volume_ratio"), 2)]
        for v in (breadth.get("volume_leaders") or [])[:15]
    ]
    delivery = breadth.get("delivery_percentage") or {}
    breadth_html = f"""
    <section id="breadth" class="section">
      <h2>4. Market Breadth</h2>
      {_howto("How to use", [
        "Advances vs Declines plus New Highs/Lows gauge participation behind the index move.",
        "Breadth Score condenses it — high = broad participation, low = narrow/thin.",
        "Heat Map is filtered to the Top 50 biggest movers (>= 1% change) across the Nifty 500.",
        "Volume Leaders show where conviction and money are actually flowing.",
      ])}
      <div class="grid stats">
        <div class="glass stat"><span>Advances</span><strong class="up">{_e(breadth.get('advances'))}</strong></div>
        <div class="glass stat"><span>Declines</span><strong class="down">{_e(breadth.get('declines'))}</strong></div>
        <div class="glass stat"><span>Unchanged</span><strong>{_e(breadth.get('unchanged'))}</strong></div>
        <div class="glass stat"><span>New Highs / Lows</span><strong>{_e(breadth.get('new_highs'))} / {_e(breadth.get('new_lows'))}</strong></div>
        <div class="glass stat"><span>Breadth Score</span><strong>{_fmt_num(breadth.get('breadth_score'),1)}</strong></div>
      </div>
      <h3>Heat Map Summary</h3>
      {heat_legend}
      <div class="heat-map">{heat_cells or '<p class="muted">No heat map data</p>'}</div>
      <h3>Volume Leaders</h3>
      {_table(["Symbol","Chg%","Volume","Vol Ratio"], vol_rows)}
      <p>{_e(breadth.get('summary'))}</p>
    </section>
    """

    # 5 Sector rotation
    sec_rows = []
    for r in sectors.get("ranked") or []:
        sec_rows.append([
            _e(r.get("rank")),
            _e(r.get("sector")),
            _fmt_num(r.get("last")),
            {"html": f"<span class='{_chg_class(r.get('change_pct'))}'>{_fmt_pct(r.get('change_pct'))}</span>"},
            _fmt_num(r.get("relative_strength"), 1),
            _fmt_num(r.get("momentum_1m_pct"), 2),
            _fmt_num(r.get("rank_score"), 1),
            _e(r.get("trend")),
            _e(r.get("ai_summary")),
        ])
    unavail = "".join(f"<li>{_e(u.get('sector'))}: {_e(u.get('reason'))}</li>" for u in (sectors.get("unavailable") or []))
    sector_html = f"""
    <section id="sectors" class="section">
      <h2>5. Sector Rotation</h2>
      <p class="note">{_e(sectors.get('method_note'))}</p>
      {_howto("How to use", [
        "Rank 1 = strongest relative strength + 1m momentum; higher Rank Score = stronger trend.",
        "Rotate toward improving (rising) ranks and away from persistent laggards.",
        "Unavailable sectors are labeled — do not infer a reading.",
      ])}
      {_table(["Rank","Sector","Last","Chg%","RS","Mom 1M%","Rank Score","Trend","Summary"], sec_rows, "sector-table")}
      {f'<div class="glass card"><h3>Unavailable sectors</h3><ul>{unavail}</ul></div>' if unavail else ''}
    </section>
    """

    # 6 Technical engine — sample from Swing Trading
    tech_rows = []
    for c in (watchlists.get("Swing Trading") or [])[:15]:
        t = c.get("tech") or {}
        tech_rows.append([
            _e(c.get("symbol")),
            _e(t.get("trend")),
            _fmt_num(t.get("rsi"), 1),
            _fmt_num(t.get("macd_hist"), 4),
            _fmt_num(t.get("ema20")),
            _fmt_num(t.get("ema50")),
            _fmt_num(t.get("ema200")),
            _fmt_num(t.get("adx"), 1),
            _fmt_num(t.get("atr")),
            _fmt_num(t.get("supertrend")),
            {"html": _score_badge(c.get("technical_score"))},
        ])
    tech_howto = _howto("How to use", [
        "Trend first — Uptrend means price is above rising EMAs, Downtrend the opposite. Trade with the trend.",
        "RSI 14: above 70 is overbought (pullback risk), below 30 oversold (bounce potential); 45–65 is healthy.",
        "MACD Hist positive = bullish momentum, negative = bearish; watch for sign flips as trend shifts.",
        "EMA stack: Price > EMA20 > EMA50 > EMA200 signals strong bullish alignment.",
        "ADX: below 18 is weak/choppy, 18–25 moderate, 25+ a strong trend (only trust the trend above 25).",
        "ATR gauges volatility — use it to size stops; larger ATR means wider, safer stop distance.",
        "Supertrend: price above the level is bullish, below is bearish — a useful trailing stop.",
        "Tech Score 0–100: 65+ bullish, 45–64 neutral, under 45 bearish. Click the column header to rank.",
    ])
    tech_html = f"""
    <section id="technical" class="section">
      <h2>6. Technical Analysis Engine</h2>
      <p class="note">Indicators: RSI, MACD, EMA 20/50/100/200, VWAP (20d proxy), Supertrend, ADX, ATR, Bollinger, pivots, volume ratio. Technical Score 0–100.</p>
      {tech_howto}
      {_table(["Symbol","Trend","RSI","MACD Hist","EMA20","EMA50","EMA200","ADX","ATR","Supertrend","Tech Score"], tech_rows, "tech-table")}
    </section>
    """

    # 7 Fundamental
    fund_rows = []
    for c in (watchlists.get("Long Term Opportunities") or [])[:15]:
        f = c.get("fund") or {}
        m = (f.get("metrics") or {}) if f else {}
        rev = m.get("revenue_growth")
        rev_txt = _fmt_pct(rev * 100) if isinstance(rev, (int, float)) else "—"
        fund_rows.append([
            _e(c.get("symbol")),
            rev_txt,
            _fmt_num(m.get("roe_pct"), 1),
            _fmt_num(m.get("operating_margin_pct"), 1),
            _fmt_num(m.get("debt_to_equity_norm"), 2),
            _fmt_num(m.get("pe"), 1),
            _fmt_num(m.get("pb"), 2),
            _fmt_num(m.get("promoter_holding_pct"), 1),
            _fmt_num(m.get("institutional_holding_pct"), 1),
            {"html": _score_badge(c.get("fundamental_score"))},
            {"html": _score_badge(c.get("valuation_score"))},
            _e(
                (f.get("fii_dii") or {}).get("summary")
                or (f.get("fii_dii") or {}).get("status")
            ),
        ])
    fund_howto = _howto("How to use", [
        "Fund Score = quality & growth (revenue/EPS growth, ROE, margins, FCF, promoter conviction). 65+ is strong.",
        "Val Score = valuation (P/E, P/B). Higher means cheaper relative to earnings/book.",
        "Pair them — high Fund + high Val is quality at a reasonable price; low Fund + high Val can be a value trap.",
        "ROE 15%+ and Op Margin 10%+ point to a profitable, efficient business.",
        "D/E: below 0.5 is healthy, above 1.5 is leveraged (higher risk).",
        "Promoter 40%+ signals strong insider conviction.",
        "FII/DII column is market-level cash activity, not per-stock ownership — treat it as context, not a stock signal.",
    ])
    fund_html = f"""
    <section id="fundamental" class="section">
      <h2>7. Fundamental Analysis Engine</h2>
      <p class="note">Per-stock FII/DII ownership is unavailable; the FII/DII column shows market-level cash activity when NSE feeds succeed. Fundamentals/valuations still come from yfinance. ROCE approximated via operating quality metrics where ROCE is missing.</p>
      {fund_howto}
      {_table(["Symbol","Rev Gr","ROE%","Op Margin%","D/E","P/E","P/B","Promoter%","Inst%","Fund Score","Val Score","FII/DII"], fund_rows, "fund-table")}
    </section>
    """

    # 8 Options — weekly / monthly NSE chain + ~80% POP strategies
    def _expiry_block(block: Optional[Dict[str, Any]], title: str) -> str:
        if not block:
            return _card(title, "<p class='muted'>No data</p>")
        if block.get("status") != "ok":
            return _card(title, f"<p class='muted'>{_e(block.get('reason') or block.get('status'))}</p>")
        metrics = f"""
        <div class="grid stats">
          <div class="glass stat"><span>Expiry</span><strong>{_e(block.get('expiry'))}</strong></div>
          <div class="glass stat"><span>Spot</span><strong>{_fmt_num(block.get('spot'),2)}</strong></div>
          <div class="glass stat"><span>DTE</span><strong>{_e(block.get('dte'))}</strong></div>
          <div class="glass stat"><span>PCR (OI)</span><strong>{_fmt_num(block.get('pcr_oi'),3)}</strong></div>
          <div class="glass stat"><span>Max Pain</span><strong>{_fmt_num(block.get('max_pain'),0)}</strong></div>
          <div class="glass stat"><span>ATM IV</span><strong>{_fmt_num((block.get('atm') or {}).get('atm_iv'),2)}</strong></div>
          <div class="glass stat"><span>1SD Exp Move</span><strong>{_fmt_num(block.get('expected_move_1sd'),1)} ({_fmt_num(block.get('expected_move_pct'),2)}%)</strong></div>
        </div>
        <p><strong>Bias:</strong> {_e(block.get('bias'))}</p>
        <p class="muted">{_e((block.get('buildups') or {}).get('note'))}</p>
        """
        strat_rows = []
        for s in block.get("strategies") or []:
            meet = "Yes" if s.get("meets_80pct_target") else "No"
            strat_rows.append([
                _e(s.get("strategy")),
                _e(s.get("legs")),
                _fmt_pct((s.get("approx_pop") or 0) * 100),
                meet,
                _fmt_conf(s.get("confidence_pct")),
                _fmt_num(s.get("est_credit_pts"), 2),
                _fmt_inr(s.get("est_max_profit_inr")),
                _fmt_inr(s.get("est_max_loss_inr")),
                _e(s.get("why")),
            ])
        return f"""
        {_card(title, metrics)}
        <h4>Strategy recommendations (target ~80% model POP)</h4>
        {_table(["Strategy","Legs","Model POP","≥80%?","Conf%","Est Credit","Max Profit","Max Loss","Why"], strat_rows)}
        """

    rec_rows = []
    for s in options.get("recommendations") or []:
        rec_rows.append([
            _e(s.get("symbol")),
            _e(s.get("tenor")),
            _e(s.get("expiry")),
            _e(s.get("strategy")),
            _e(s.get("legs")),
            _fmt_pct((s.get("approx_pop") or 0) * 100),
            "Yes" if s.get("meets_80pct_target") else "No",
            _fmt_conf(s.get("confidence_pct")),
            _e(s.get("direction_bias")),
            _fmt_inr(s.get("est_max_profit_inr")),
            _fmt_inr(s.get("est_max_loss_inr")),
        ])

    opt_sym_blocks = []
    for s in options.get("symbols") or []:
        if s.get("status") != "ok":
            opt_sym_blocks.append(
                _card(_e(s.get("symbol")), f"<p class='muted'>{_e(s.get('reason'))}</p>")
            )
            continue
        opt_sym_blocks.append(f"<h3>{_e(s.get('symbol'))}</h3>")
        opt_sym_blocks.append(_expiry_block(s.get("weekly"), f"{s.get('symbol')} — Weekly"))
        opt_sym_blocks.append(_expiry_block(s.get("monthly"), f"{s.get('symbol')} — Monthly"))

    options_html = f"""
    <section id="options" class="section">
      <h2>8. Options Analytics (Weekly &amp; Monthly)</h2>
      <p class="note">{_e(options.get('note'))} Source: <a href="{_e(options.get('source_page') or 'https://www.nseindia.com/option-chain')}" target="_blank" rel="noopener">NSE Option Chain</a>.</p>
      {_card("Status", f"<p><strong>{_e(options.get('status'))}</strong> · Target model POP {_fmt_pct((options.get('target_pop') or 0.8)*100)}</p><p class='muted'>Model POP uses distance vs IV expected move. It is not a promised historical win rate.</p>")}
      {_howto("How to use", [
        "Check DTE, PCR(OI), Max Pain, ATM IV and the 1SD expected move before acting.",
        "Model POP is a distance-vs-IV estimate (~80% target), not a promised historical win rate.",
        "Max Profit / Max Loss are per-leg estimates; credit spreads are capped so max loss cannot exceed width.",
        "Sell premium only after confirming PCR / max pain vs spot.",
      ])}
      <h3>Top strategy board (≥80% model POP preferred)</h3>
      {_table(["Symbol","Tenor","Expiry","Strategy","Legs","Model POP","≥80%","Conf%","Bias","Max Profit","Max Loss"], rec_rows, "opt-rec-table")}
      {''.join(opt_sym_blocks)}
    </section>
    """

    # 9 Watchlists
    def wl_table(cards: List[Dict[str, Any]]) -> str:
        rows = []
        for c in cards:
            rows.append([
                _e(c.get("symbol")),
                _e(c.get("name")),
                {"html": _score_badge(c.get("technical_score"))},
                {"html": _score_badge(c.get("fundamental_score"))},
                {"html": _score_badge(c.get("momentum_score"))},
                {"html": _score_badge(c.get("sentiment_score"))},
                {"html": _score_badge(c.get("valuation_score"))},
                {"html": _score_badge(c.get("risk_score"))},
                {"html": _score_badge(c.get("overall_conviction"))},
                {"html": _rating_badge(c.get("rating") or "")},
                _fmt_conf(c.get("confidence_pct")),
            ])
        return _table(
            ["Symbol","Name","Tech","Fund","Mom","Sent","Val","Risk","Conviction","Rating","Conf%"],
            rows,
        )

    rebalance_map = {
        "Core Portfolio": [
            "Suggested cadence (not an automated rule): review quarterly or on conviction drift.",
            "Keep roughly equal weights; trim any name whose Rating drops to Reduce/Sell.",
            "Add only on Fund/Val confirmation — this is the anchor sleeve, not a trading book.",
        ],
        "Swing Candidates": [
            "Swing time frame: 2–8 weeks. Re-run the list weekly against fresh data.",
            "Exit on stop (Supertrend/ATR) or when the setup invalidates; rotate freed capital to the next swing.",
            "Size by volatility: wider ATR means smaller position to keep risk constant.",
        ],
        "AI Stocks": [
            "Theme sleeve — suggested monthly rebalance; trim laggards with falling momentum.",
            "Re-confirm catalysts and conviction each review; do not add into names that broke trend.",
        ],
        "Options Watchlist": [
            "Not an equity book — these symbols feed the Options Analytics chain; no rebalance applies.",
        ],
    }
    wl_blocks = []
    for name, cards in watchlists.items():
        detail_cards = []
        for c in cards[:8]:
            detail_cards.append(
                f"<div class='glass mini'><h4>{_e(c.get('symbol'))} {_rating_badge(c.get('rating') or '')}</h4>"
                f"<p><strong>Evidence:</strong> {_e('; '.join((c.get('evidence') or [])[:2]))}</p>"
                f"<p><strong>Risks:</strong> {_e('; '.join(c.get('risks') or []))}</p>"
                f"<p><strong>Catalysts:</strong> {_e('; '.join(c.get('catalysts') or []))}</p>"
                f"<p><strong>Horizon:</strong> {_e(c.get('time_horizon'))} · Conf {_fmt_num(c.get('confidence_pct'),1)}%</p></div>"
            )
        reb = _howto("Rebalance (suggested cadence)", rebalance_map[name]) if name in rebalance_map else ""
        wl_blocks.append(
            f"<h3>{_e(name)}</h3>{reb}{wl_table(cards)}<div class='grid two'>{''.join(detail_cards)}</div>"
        )
    watch_html = f"""
    <section id="watchlists" class="section">
      <h2>9. Watchlists</h2>
      <p class="note">Config-driven sample watchlists. Additional qualifying names discovered hourly via opportunity engine.</p>
      {_howto("How to use", [
        "Core Portfolio = long-term quality core; Swing Candidates = 2–8 week tactical; AI Stocks = IT/AI theme; Options Watchlist = option underlyings.",
        "Conviction = weighted multi-factor score; Rating = Strong Buy…Strong Sell bands; Conf% = data completeness.",
        "Swing time frame is 2–8 weeks; positional is 3–12 months (see each card's Horizon).",
        "See the per-list Rebalance notes below.",
      ])}
      {''.join(wl_blocks)}
    </section>
    """

    # 9.5 Alpha Leaderboards
    alpha_blocks = []
    nifty_alpha = alpha_lb.get("nifty") or {}
    
    alpha_blocks.append(f"<p class='brief'>Nifty 50 Baseline: 4W: <strong>{_fmt_pct(nifty_alpha.get('r4w'))}</strong> | 1W: <strong>{_fmt_pct(nifty_alpha.get('r1w'))}</strong></p>")
    
    selected_sectors = alpha_lb.get("sector_details") or []
    if selected_sectors:
        for sec in selected_sectors:
            alpha_blocks.append(f"<h3>{_e(sec.get('name'))}</h3>")
            alpha_blocks.append("<div class='grid four'>")
            for tier in sec.get("tiers", []):
                leaders_html = ""
                for l in tier.get("leaders", []):
                    leaders_html += f"<li><span class='muted'>{_e(l.get('ticker'))}</span> <strong class='{_chg_class(l.get('r4w'))}'>{_fmt_pct(l.get('r4w'))}</strong></li>"
                if not leaders_html:
                    leaders_html = "<li class='muted'>No strong momentum</li>"
                alpha_blocks.append(
                    f"<div class='glass mini'><h4>{_e(tier.get('label'))}</h4>"
                    f"<ul class='kv'>{leaders_html}</ul></div>"
                )
            alpha_blocks.append("</div>")
    else:
        alpha_blocks.append("<p class='muted'>No positive alpha sectors detected against Nifty 50.</p>")

    alpha_html = f"""
    <section id="alpha" class="section">
      <h2>10. Momentum &amp; Alpha Leaderboards</h2>
      {_howto("How to use", [
        "Identifies the top outperforming sectors against the Nifty 50 baseline over 4 weeks.",
        "For each sector, highlights the top 2 momentum leaders across Large, Mid, Small, and Micro cap tiers.",
        "Use this for tactical momentum allocation and relative strength trading.",
      ])}
      {''.join(alpha_blocks)}
    </section>
    """

    # 11 Opportunities
    opp_rows = [
        [
            _e(o.get("symbol")),
            _e(o.get("category")),
            _e(o.get("reason")),
            {"html": _score_badge(o.get("overall_conviction"))},
            {"html": _rating_badge(o.get("rating") or "")},
        ]
        for o in opportunities
    ]
    opp_html = f"""
    <section id="opportunities" class="section">
      <h2>11. AI Opportunity Engine — Top 10</h2>
      {_howto("How to use", [
        "Categories are rule-triggered: Breakout/Momentum, Value, Growth, Reversal, Quality, High RS.",
        "Ranked by Conviction with a Rating band; the top 10 unique symbols are shown.",
        "Rebalance (suggested cadence): refresh the shortlist each session; commit only on multi-factor confirmation.",
        "Treat it as a screening funnel — verify a pick in the Technical and Fundamental engines before acting.",
      ])}
      {_table(["Symbol","Category","Reason","Conviction","Rating"], opp_rows, "opp-table")}
    </section>
    """

    # 11 News
    news_blocks = []
    for item in news.get("items") or []:
        heads = "".join(f"<li>{_e(h)}</li>" for h in (item.get("headlines") or [])[:4]) or "<li class='muted'>No headlines</li>"
        news_blocks.append(
            f"<article class='glass card'><h3>{_e(item.get('category'))} "
            f"<span class='badge muted'>{_e(item.get('status'))}</span></h3>"
            f"<ul>{heads}</ul>"
            f"<p><strong>Likely impact:</strong> {_e(item.get('likely_impact'))}</p>"
            f"<p class='muted'>{_e(item.get('source') or item.get('reason'))}</p></article>"
        )
    news_html = f"""
    <section id="news" class="section">
      <h2>12. News Intelligence</h2>
      <p class="note">{_e(news.get('note'))}</p>
      {_howto("How to use", [
        "Headlines grouped by category with a likely-impact read.",
        "RSS headlines can lag and are optional — cross-check impact against the price and breadth sections.",
        "Use as a catalyst watchlist, not a primary signal.",
      ])}
      <div class="grid two">{''.join(news_blocks) or '<p class="muted">No news module output</p>'}</div>
    </section>
    """

    # 12 Economy
    def eco_box(title: str, obj: Any) -> str:
        if isinstance(obj, dict) and obj.get("status") == "unavailable":
            return _card(title, f"<p class='muted'>{_e(obj.get('reason'))}</p>")
        if isinstance(obj, dict) and "last" in obj:
            return _card(
                title,
                f"<p>Last: <strong>{_fmt_num(obj.get('last'))}</strong> "
                f"<span class='{_chg_class(obj.get('change_pct'))}'>{_fmt_pct(obj.get('change_pct'))}</span></p>"
                f"<p class='muted'>{_e(obj.get('status'))}</p>",
            )
        if isinstance(obj, list):
            rows = "".join(
                f"<li>{_e(x.get('name'))}: {_fmt_num(x.get('last'))} "
                f"<span class='{_chg_class(x.get('change_pct'))}'>{_fmt_pct(x.get('change_pct'))}</span> "
                f"({_e(x.get('status'))})</li>"
                for x in obj
            )
            return _card(title, f"<ul>{rows}</ul>")
        if isinstance(obj, dict) and "items" in obj:
            rows = "".join(
                f"<li>{_e(x.get('name'))}: {_fmt_num(x.get('last'))} ({_e(x.get('status'))})</li>"
                for x in obj.get("items") or []
            )
            return _card(title, f"<ul>{rows}</ul><p class='muted'>{_e(obj.get('note'))}</p>")
        return _card(title, f"<pre class='muted'>{_e(json.dumps(obj, default=str)[:400])}</pre>")

    eco_html = f"""
    <section id="economy" class="section">
      <h2>13. Macro &amp; Economy</h2>
      {_howto("How to use", [
        "Snapshot of macro prints: inflation, GDP, PMI, rates, currency, commodities, dollar index, central banks.",
        "'Unavailable' boxes are labeled — official prints beyond available feeds are never inferred.",
        "Use it to frame the regime; tie specific moves back to Global Markets.",
      ])}
      <div class="grid three">
        {eco_box("Inflation", economy.get("inflation"))}
        {eco_box("GDP", economy.get("gdp"))}
        {eco_box("PMI", economy.get("pmi"))}
        {eco_box("Interest Rates", economy.get("interest_rates"))}
        {eco_box("Currency", economy.get("currency"))}
        {eco_box("Commodities", economy.get("commodities"))}
        {eco_box("Dollar Index", economy.get("dollar_index"))}
        {eco_box("Global Central Banks", economy.get("global_central_banks"))}
      </div>
    </section>
    """

    # 13 Risk
    risk_rows = [
        [_e(i.get("name")), _fmt_num(i.get("score"), 1), _e(i.get("level")), _e(i.get("detail"))]
        for i in (risk_dash.get("items") or [])
    ]
    risk_html = f"""
    <section id="risk" class="section">
      <h2>14. Risk Dashboard</h2>
      {_howto("How to use", [
        "Higher score = more risk; Level is Low / Moderate / High / Critical.",
        "Valuation risk is intentionally 'Unavailable' (no CAPE/PE-band source) — not fabricated.",
        "Treat the highest-scoring rows as the near-term watch list.",
      ])}
      {_table(["Risk Type","Score","Level","Detail"], risk_rows)}
    </section>
    """

    # 14 Insights
    themes = "".join(f"<li>{_e(t)}</li>" for t in (insights.get("key_themes") or []))
    sec_out = "".join(f"<li>{_e(t)}</li>" for t in (insights.get("sector_outlook") or []))
    insights_html = f"""
    <section id="insights" class="section">
      <h2>15. AI Insights</h2>
      {_howto("How to use", [
        "Rule-based narratives: Market Summary, Weekly/Monthly Outlook, Sector Outlook, Key Themes, Opportunities.",
        "Treat them as organizing frames — verify each claim against the tables above.",
        "Weekly vs Monthly outlooks give the swing (2–8 wk) vs positional (3–12 mo) lens.",
      ])}
      <div class="grid two">
        {_card("Market Summary", f"<p>{_e(insights.get('market_summary'))}</p>")}
        {_card("Weekly Outlook", f"<p>{_e(insights.get('weekly_outlook'))}</p>")}
        {_card("Monthly Outlook", f"<p>{_e(insights.get('monthly_outlook'))}</p>")}
        {_card("Sector Outlook", f"<ul>{sec_out}</ul>")}
        {_card("Key Themes", f"<ul>{themes}</ul>")}
        {_card("Opportunities", f"<ul>{''.join(f'<li>{_e(x)}</li>' for x in (insights.get('opportunities') or []))}</ul>")}
      </div>
    </section>
    """

    # 15 Hourly changes
    ch_rows = [
        [_e(i.get("type")), _e(i.get("label")), _e(i.get("detail"))]
        for i in (changes.get("items") or [])
    ]
    changes_html = f"""
    <section id="changes" class="section">
      <h2>16. Hourly Change Detection</h2>
      {_howto("How to use", [
        "Diffs the current run against the previous snapshot (ratings, conviction, breadth, regime).",
        "Use it to see what moved since the last refresh — not as a signal on its own.",
        "Cross-check any change against the section it came from before acting.",
      ])}
      {_card("Summary", f"<p>{_e(changes.get('summary'))}</p><p class='muted'>Status: {_e(changes.get('status'))}</p>")}
      {_table(["Type","Label","Detail"], ch_rows)}
    </section>
    """

    # Final deliverables
    def top_list(cards: List[Dict[str, Any]]) -> str:
        rows = [
            [
                _e(c.get("symbol")),
                {"html": _rating_badge(c.get("rating") or "")},
                {"html": _score_badge(c.get("overall_conviction"))},
                _fmt_conf(c.get("confidence_pct")),
                _e(c.get("time_horizon")),
            ]
            for c in cards
        ]
        return _table(["Symbol","Rating","Conviction","Conf%","Horizon"], rows)

    fii = payload.get("fii_dii") or {}
    fii_bit = (
        f" Cash FII/DII: {fii.get('summary')} (as of {fii.get('as_of')})."
        if fii.get("status") == "ok" and fii.get("summary")
        else " Market-level FII/DII was unavailable this run."
    )
    conclusion = (
        f"As of {generated_at}, NSE conditions screen as {regime.get('market_sentiment')} "
        f"under a {regime.get('market_regime')} regime (bull {regime.get('bull_score')}, "
        f"risk {regime.get('market_risk_label')}). "
        f"Use Top Conviction for positional ideas and Swing list for tactical setups."
        f"{fii_bit} "
        f"Official macro prints beyond available feeds must not be inferred."
    )
    focus_next = [
        "Re-check India VIX and Nifty vs EMA50 for regime confirmation",
        "Monitor sector leadership persistence from rotation table",
        "Review weekly vs monthly option strategy board for ≥80% model-POP credit spreads",
        "Confirm NSE option PCR / max pain vs spot before selling premium",
    ]
    warn_html = "".join(f"<li>{_e(w)}</li>" for w in warnings[:30]) or "<li class='muted'>None</li>"
    src_html = "".join(f"<li>{_e(s)}</li>" for s in sources)

    final_html = f"""
    <section id="final" class="section">
      <h2>Final Deliverables</h2>
      {_howto("How to use", [
        "Top Conviction = positional (3–12 months); Swing Opportunities = swing (2–8 weeks); Long-term = fundamental-weighted.",
        "Rebalance (suggested cadence): swing weekly, conviction monthly, long-term quarterly.",
        "Use Top Risks and Focus Areas as the pre-action checklist.",
      ])}
      {_card("1. Executive Conclusion", f"<p>{_e(conclusion)}</p>")}
      <h3>2. Top 10 Conviction Stocks</h3>
      {top_list(lists.get('top_conviction') or [])}
      <h3>3. Top 10 Swing Opportunities</h3>
      {top_list(lists.get('top_swing') or [])}
      <h3>4. Top 10 Long-term Ideas</h3>
      {top_list(lists.get('top_long_term') or [])}
      <h3>5. Top Risks to Monitor</h3>
      <ul>{''.join(f'<li>{_e(x)}</li>' for x in (exec_s.get('top_risks') or []))}</ul>
      <h3>6. Focus Areas for the Next Hour</h3>
      <ul>{''.join(f'<li>{_e(x)}</li>' for x in focus_next)}</ul>
      <h3>7. Data Sources Used</h3>
      <ul>{src_html}</ul>
      <h3>8. Dashboard Generation Timestamp</h3>
      <p><strong>{_e(generated_at)}</strong></p>
      <h3>Fetch Warnings</h3>
      <ul>{warn_html}</ul>
    </section>
    """

    nav = """
    <nav class="topnav" aria-label="Sections">
      <div class="brand">
        <span class="brand-mark">N</span>
        <div class="brand-text"><strong>NSE Intelligence</strong><span>Institutional Dashboard</span></div>
      </div>
      <div class="nav-actions">
        <input id="global-search" type="search" placeholder="Search sections &amp; symbols…" aria-label="Search dashboard"/>
        <button id="theme-toggle" type="button" aria-label="Toggle theme">Dark mode</button>
      </div>
      <div class="nav-links">
        <span class="nav-group-label">Overview</span>
        <a href="#executive"><span class="n">01</span>Executive</a>
        <a href="#global"><span class="n">02</span>Global</a>

        <span class="nav-group-label">Market</span>
        <a href="#nse"><span class="n">03</span>NSE Coverage</a>
        <a href="#breadth"><span class="n">04</span>Breadth</a>
        <a href="#sectors"><span class="n">05</span>Sectors</a>

        <span class="nav-group-label">Stocks</span>
        <a href="#technical"><span class="n">06</span>Technical</a>
        <a href="#fundamental"><span class="n">07</span>Fundamental</a>
        <a href="#watchlists"><span class="n">09</span>Watchlists</a>
        <a href="#alpha"><span class="n">10</span>Alpha</a>
        <a href="#opportunities"><span class="n">11</span>Opportunities</a>

        <span class="nav-group-label">Options &amp; Risk</span>
        <a href="#options"><span class="n">08</span>Options</a>
        <a href="#risk"><span class="n">14</span>Risk</a>

        <span class="nav-group-label">Context</span>
        <a href="#news"><span class="n">12</span>News</a>
        <a href="#economy"><span class="n">13</span>Economy</a>

        <span class="nav-group-label">Wrap-up</span>
        <a href="#insights"><span class="n">15</span>Insights</a>
        <a href="#changes"><span class="n">16</span>Changes</a>
        <a href="#final" class="divider">Summary</a>
      </div>
    </nav>
    """

    css = """
/* ============================================================
   NSE Intelligence — design tokens (premium fintech)
   ============================================================ */
:root {
  --bg: #e9ecf6;
  --bg-grad-1: rgba(79, 70, 229, 0.15);
  --bg-grad-2: rgba(124, 58, 237, 0.12);
  --surface: #f7f8fd;
  --surface-2: #eef0f9;
  --surface-3: #e2e6f3;
  --fg: #0d1322;
  --fg-2: #3b455c;
  --muted: #66728a;
  --border: #dfe4f1;
  --border-soft: #e9edf6;

  --accent: #4f46e5;
  --accent-2: #7c3aed;
  --accent-soft: rgba(79, 70, 229, 0.10);
  --accent-on: #ffffff;
  --accent-hover: color-mix(in oklab, var(--accent), black 10%);
  --accent-active: color-mix(in oklab, var(--accent), black 16%);
  --grad-accent: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);

  --success: #0e9f6e;
  --success-soft: rgba(14, 159, 110, 0.12);
  --warn: #d97706;
  --warn-soft: rgba(217, 119, 6, 0.13);
  --danger: #dc2626;
  --danger-soft: rgba(220, 38, 38, 0.12);

  --font-display: "Inter", system-ui, -apple-system, sans-serif;
  --font-body: "Inter", system-ui, -apple-system, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --text-xs: 11px;
  --text-sm: 13px;
  --text-base: 15px;
  --text-lg: 17px;
  --text-xl: 20px;
  --text-2xl: 26px;
  --text-3xl: 34px;
  --text-4xl: 44px;
  --leading-body: 1.55;
  --leading-tight: 1.15;
  --tracking-display: -0.02em;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-pill: 999px;

  --shadow-1: 0 1px 2px rgba(13, 19, 34, 0.04), 0 1px 3px rgba(13, 19, 34, 0.03);
  --shadow-2: 0 2px 6px rgba(13, 19, 34, 0.05), 0 8px 24px rgba(13, 19, 34, 0.05);
  --shadow-3: 0 4px 12px rgba(13, 19, 34, 0.08), 0 16px 40px rgba(13, 19, 34, 0.08);

  --focus-ring: 0 0 0 3px rgba(99, 102, 241, 0.28);
  --motion-fast: 120ms;
  --motion-base: 200ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);

  --sidebar-w: 272px;
  --container-max: 1240px;
  --container-gutter: 40px;
}

:root[data-theme="dark"] {
  --bg: #0a0f1c;
  --bg-grad-1: rgba(99, 102, 241, 0.12);
  --bg-grad-2: rgba(139, 92, 246, 0.08);
  --surface: #111828;
  --surface-2: #182136;
  --surface-3: #1f2a44;
  --fg: #e8edf7;
  --fg-2: #b9c3d8;
  --muted: #8592ad;
  --border: #26314b;
  --border-soft: #1e2940;

  --accent: #818cf8;
  --accent-2: #a78bfa;
  --accent-soft: rgba(129, 140, 248, 0.14);
  --accent-on: #0b0f1a;
  --grad-accent: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);

  --success: #34d399;
  --success-soft: rgba(52, 211, 153, 0.14);
  --warn: #fbbf24;
  --warn-soft: rgba(251, 191, 36, 0.14);
  --danger: #f87171;
  --danger-soft: rgba(248, 113, 113, 0.14);

  --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.30);
  --shadow-2: 0 2px 6px rgba(0, 0, 0, 0.35), 0 8px 24px rgba(0, 0, 0, 0.35);
  --shadow-3: 0 4px 12px rgba(0, 0, 0, 0.45), 0 16px 40px rgba(0, 0, 0, 0.40);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  font-family: var(--font-body);
  color: var(--fg);
  background: var(--bg);
  line-height: var(--leading-body);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
  min-height: 100vh;
}
body::before {
  content: "";
  position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background:
    radial-gradient(1000px 520px at 0% -10%, var(--bg-grad-1), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, var(--bg-grad-2), transparent 55%);
}
a:focus-visible, button:focus-visible, input:focus-visible, [tabindex]:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
::selection { background: color-mix(in oklab, var(--accent) 22%, transparent); }

/* ---------- Sidebar ---------- */
.topnav {
  grid-column: 1;
  grid-row: 1;
  position: sticky; top: 0; height: 100vh; z-index: 50;
  display: flex; flex-direction: column;
  padding: 1.5rem 1rem 1.25rem;
  gap: 1rem;
  background: color-mix(in oklab, var(--surface) 88%, transparent);
  backdrop-filter: blur(14px) saturate(1.3);
  -webkit-backdrop-filter: blur(14px) saturate(1.3);
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.brand { display: flex; align-items: center; gap: .7rem; padding: .1rem .35rem; }
.brand-mark {
  width: 40px; height: 40px; border-radius: 12px; flex: none;
  background: var(--grad-accent);
  color: #ffffff;
  display: grid; place-items: center;
  font-family: var(--font-mono); font-weight: 700; font-size: 1.05rem;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
}
.brand-text { display: flex; flex-direction: column; line-height: 1.25; }
.brand-text strong { font-family: var(--font-display); font-weight: 700; font-size: var(--text-base); letter-spacing: -0.01em; color: var(--fg); }
.brand-text span { font-size: var(--text-xs); color: var(--muted); }

.nav-actions { display: flex; flex-direction: column; gap: .5rem; }
#global-search, #theme-toggle, select.filter {
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--fg);
  border-radius: var(--radius-md);
  padding: .55rem .8rem;
  font: inherit; font-size: var(--text-sm);
  transition: border-color var(--motion-fast) var(--ease-standard), box-shadow var(--motion-fast) var(--ease-standard), color var(--motion-fast) var(--ease-standard);
}
#global-search { width: 100%; }
#global-search:focus, #theme-toggle:focus, select.filter:focus { border-color: var(--accent); }
#theme-toggle { cursor: pointer; font-weight: 600; width: 100%; }
#theme-toggle:hover { border-color: var(--accent); color: var(--accent); }

.nav-links { display: flex; flex-direction: column; gap: 2px; }
.nav-group-label {
  font-family: var(--font-mono); font-size: 10px; font-weight: 700;
  letter-spacing: .08em; text-transform: uppercase; color: var(--muted);
  padding: .8rem .65rem .2rem; opacity: .8;
}
.nav-group-label:first-child { padding-top: .1rem; }
.nav-links a {
  display: flex; align-items: center; gap: .65rem;
  color: var(--muted); text-decoration: none;
  font-size: var(--text-sm); font-weight: 500; white-space: nowrap;
  padding: .5rem .65rem; border-radius: var(--radius-sm);
  border-left: 2px solid transparent;
  transition: color var(--motion-fast) var(--ease-standard), background var(--motion-fast) var(--ease-standard), border-color var(--motion-fast) var(--ease-standard);
}
.nav-links a .n {
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  color: var(--muted); width: 20px; flex: none;
}
.nav-links a:hover { color: var(--fg); background: color-mix(in oklab, var(--fg) 5%, transparent); }
.nav-links a.active {
  color: var(--fg); font-weight: 600;
  background: var(--accent-soft);
  border-left-color: var(--accent);
}
.nav-links a.active .n { color: var(--accent); }
.nav-links a.divider { margin-top: .6rem; padding-top: .75rem; border-top: 1px solid var(--border-soft); border-left-color: transparent; }

/* ---------- Content ---------- */
main {
  grid-column: 2;
  max-width: var(--container-max);
  width: 100%;
  margin: 0 auto;
  padding: 0 var(--container-gutter) 4rem;
}
.hero { position: relative; padding: 3.25rem 0 2rem; margin-bottom: .5rem; }
.hero::after {
  content: ""; display: block; height: 1px;
  background: linear-gradient(90deg, var(--accent), var(--accent-2), transparent);
  opacity: .4; margin-top: 1.75rem;
}
.hero-eyebrow {
  display: inline-flex; align-items: center; gap: .55rem;
  font-family: var(--font-mono); font-size: var(--text-xs);
  font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 1rem;
  padding: .3rem .7rem; border-radius: var(--radius-pill);
  background: var(--accent-soft);
  border: 1px solid color-mix(in oklab, var(--accent) 18%, transparent);
}
.hero-eyebrow::before {
  content: ""; width: 7px; height: 7px; border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 4px color-mix(in oklab, var(--success) 20%, transparent);
}
.hero h1 {
  font-family: var(--font-display);
  font-size: clamp(2rem, 4.6vw, 3rem);
  font-weight: 800; letter-spacing: var(--tracking-display);
  line-height: var(--leading-tight);
  margin: 0 0 .7rem; color: var(--fg); max-width: 26ch;
}
.hero p { color: var(--muted); margin: 0; font-size: var(--text-base); max-width: 68ch; }

.section { margin: 2.75rem 0; scroll-margin-top: 20px; }
.section h2 {
  font-family: var(--font-display);
  font-size: var(--text-2xl); font-weight: 700;
  letter-spacing: -0.015em; color: var(--fg);
  margin: 0 0 .6rem; padding-bottom: .7rem;
  border-bottom: 1px solid var(--border-soft);
  position: relative;
}
.section h2::after {
  content: ""; position: absolute; left: 0; bottom: -1px;
  width: 64px; height: 2px; border-radius: 2px;
  background: var(--grad-accent);
}
.section h3 { font-family: var(--font-display); font-size: var(--text-lg); font-weight: 600; letter-spacing: -0.01em; margin: 1.5rem 0 .55rem; }

/* ---------- Cards & panels ---------- */
.glass {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
}
.card { padding: 1.15rem 1.25rem; margin-bottom: 1rem; }
.card h3 { font-family: var(--font-display); font-size: var(--text-base); font-weight: 700; letter-spacing: -0.01em; margin: 0 0 .35rem; }
.card-sub { color: var(--muted); font-size: var(--text-sm); margin: -.25rem 0 .5rem; }
.grid { display: grid; gap: 1rem; }
.grid.two { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.grid.three { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.grid.four { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.grid.stats { grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); margin-bottom: 1.1rem; gap: .8rem; }
.stat { padding: 1rem 1.1rem; border-radius: var(--radius-md); }
.stat span {
  display: block; color: var(--muted);
  font-size: var(--text-xs); font-weight: 600;
  letter-spacing: .02em;
}
.stat strong {
  display: block; margin-top: .45rem;
  font-family: var(--font-display); font-weight: 700;
  font-size: 1.35rem; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums; color: var(--fg);
  line-height: 1.1;
}
.stat strong.up { color: var(--success); }
.stat strong.down { color: var(--danger); }
.spark {
  display: block; width: 100%; height: 36px; margin-top: .6rem;
  overflow: visible;
}
.spark.up { color: var(--success); }
.spark.down { color: var(--danger); }

/* ---------- Interactive chart ---------- */
.chart-wrap { position: relative; width: 100%; height: 240px; color: var(--accent); }
.chart-wrap.up { color: var(--success); }
.chart-wrap.down { color: var(--danger); }
.chart-svg { width: 100%; height: 100%; display: block; overflow: visible; cursor: crosshair; touch-action: pan-y; }
.chart-crosshair { stroke: var(--border); stroke-width: 1; vector-effect: non-scaling-stroke; }
.chart-dot { fill: var(--surface); stroke: currentColor; stroke-width: 2; }
.chart-tooltip {
  position: absolute; top: 4px; transform: translateX(-50%);
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: .35rem .6rem; font-size: var(--text-xs); box-shadow: var(--shadow-2);
  pointer-events: none; opacity: 0; transition: opacity var(--motion-fast) var(--ease-standard);
  white-space: nowrap; display: flex; flex-direction: column; gap: 1px; z-index: 5;
}
.chart-tooltip strong { font-family: var(--font-mono); color: var(--fg); font-variant-numeric: tabular-nums; font-size: var(--text-sm); }
.chart-tooltip span { color: var(--muted); }

/* ---------- Tables ---------- */
.table-wrap {
  overflow-x: auto; margin: .6rem 0 1.25rem;
  border-radius: var(--radius-md); border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow-1);
}
table.data-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
table.data-table th {
  position: sticky; top: 0; z-index: 2;
  background: var(--surface-2);
  color: var(--fg-2); font-size: var(--text-xs); font-weight: 600;
  letter-spacing: .03em;
  padding: .65rem .8rem; text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap; cursor: pointer; user-select: none;
}
table.data-table th::after { content: "↕"; margin-left: .35rem; opacity: .25; font-size: .7rem; }
table.data-table th[data-asc="true"]::after { content: "↑"; opacity: 1; color: var(--accent); }
table.data-table th[data-asc="false"]::after { content: "↓"; opacity: 1; color: var(--accent); }
table.data-table td {
  padding: .6rem .8rem;
  border-bottom: 1px solid var(--border-soft);
  vertical-align: middle; font-variant-numeric: tabular-nums;
}
table.data-table tbody tr:nth-child(even) td { background: color-mix(in oklab, var(--surface-2) 45%, var(--surface)); }
table.data-table tbody tr:last-child td { border-bottom: 0; }
table.data-table tbody tr { transition: background var(--motion-fast) var(--ease-standard); }
table.data-table tbody tr:hover td { background: var(--accent-soft); }
td.num, th.num { text-align: right; }
td.num { font-family: var(--font-mono); font-size: .95em; letter-spacing: -0.01em; white-space: nowrap; }

/* ---------- Text & badges ---------- */
.up { color: var(--success); }
.down { color: var(--danger); }
.muted { color: var(--muted); }
.note { color: var(--muted); font-size: var(--text-sm); }
.brief { font-size: var(--text-base); }
.badge {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: .15rem .6rem; border-radius: var(--radius-pill);
  font-size: var(--text-xs); font-weight: 600; line-height: 1.5; white-space: nowrap;
  border: 1px solid transparent;
}
.badge::before { content: ""; width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.badge.good { background: var(--success-soft); color: var(--success); }
.badge.mid { background: var(--warn-soft); color: var(--warn); }
.badge.bad { background: var(--danger-soft); color: var(--danger); }
.badge.muted { background: color-mix(in oklab, var(--muted) 12%, transparent); color: var(--muted); }
.badge.muted::before { display: none; }

/* ---------- How-to callout (collapsible) ---------- */
.howto {
  margin: .6rem 0 1.25rem;
  background: color-mix(in oklab, var(--surface-2) 60%, var(--surface));
  border: 1px solid var(--border); border-radius: var(--radius-md);
  overflow: hidden;
}
.howto h4 {
  margin: 0; padding: .7rem 1rem;
  font-family: var(--font-display);
  font-size: var(--text-xs); font-weight: 700;
  letter-spacing: .05em; color: var(--fg-2);
  cursor: pointer; user-select: none;
  display: flex; align-items: center; gap: .5rem;
  transition: color var(--motion-fast) var(--ease-standard);
}
.howto h4:hover { color: var(--accent); }
.howto h4::after {
  content: "▾"; margin-left: auto; font-size: .8rem;
  color: var(--muted); transition: transform var(--motion-fast) var(--ease-standard);
}
.howto.collapsed h4::after { transform: rotate(-90deg); }
.howto ol {
  margin: 0; padding: .35rem 1rem .85rem 2.2rem;
  display: grid; gap: .3rem; font-size: var(--text-sm); color: var(--fg-2);
  border-top: 1px solid var(--border-soft);
}
.howto.collapsed ol { display: none; }
.howto li::marker { color: var(--accent); font-weight: 600; }

/* ---------- Heat map ---------- */
.heat-map { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: .55rem; margin: .6rem 0 1.25rem; }
.heat {
  --heat: 0;
  border-radius: var(--radius-sm); padding: .65rem .75rem;
  border: 1px solid var(--border); background: var(--surface);
  display: flex; flex-direction: column; gap: .2rem;
  transition: transform var(--motion-fast) var(--ease-standard), box-shadow var(--motion-fast) var(--ease-standard);
}
.heat:hover { transform: translateY(-2px); box-shadow: var(--shadow-2); }
.heat span { font-size: var(--text-xs); color: var(--muted); font-weight: 600; }
.heat strong { font-family: var(--font-mono); font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
.heat.up { background: color-mix(in oklab, var(--success) calc(var(--heat) * 18%), var(--surface)); }
.heat.down { background: color-mix(in oklab, var(--danger) calc(var(--heat) * 18%), var(--surface)); }
.heat.up strong { color: var(--success); }
.heat.down strong { color: var(--danger); }
.heat-legend {
  display: flex; align-items: center; gap: .6rem;
  font-size: var(--text-xs); color: var(--muted); font-weight: 600;
  margin: .4rem 0 .75rem;
}
.heat-legend-scale { display: flex; gap: 3px; }
.heat-legend-scale i {
  --heat: 0; width: 20px; height: 10px; border-radius: 3px; display: block;
  border: 1px solid var(--border);
}
.heat-legend-scale i.up { background: color-mix(in oklab, var(--success) calc(var(--heat) * 18%), var(--surface)); }
.heat-legend-scale i.down { background: color-mix(in oklab, var(--danger) calc(var(--heat) * 18%), var(--surface)); }

/* ---------- Misc ---------- */
.mini { padding: 1rem; }
.mini h4 { margin: 0 0 .45rem; font-family: var(--font-display); font-size: var(--text-base); font-weight: 600; }
.kv { list-style: none; padding: 0; margin: 0; }
.kv li { display: flex; justify-content: space-between; gap: 1rem; padding: .4rem 0; border-bottom: 1px solid var(--border-soft); }
.kv li:last-child { border-bottom: 0; }
.toolbar { display: flex; gap: .6rem; flex-wrap: wrap; margin: .5rem 0 1rem; }
.card ul, .card ol { margin: .35rem 0 0; padding-left: 1.15rem; display: grid; gap: .3rem; }
footer {
  color: var(--muted); font-size: var(--text-sm);
  padding: 2.5rem 0 3rem; margin-top: 2.5rem;
  border-top: 1px solid var(--border);
}
footer p { margin: 0 0 .4rem; }
footer p:last-child { margin-bottom: 0; }
footer .credit { font-weight: 600; color: var(--fg-2); }
footer .disclaimer { font-size: var(--text-xs); }
footer .copyright { font-size: var(--text-xs); }

/* ---------- Responsive ---------- */
@media (max-width: 1100px) {
  body { grid-template-columns: 1fr; }
  .topnav {
    grid-column: 1; position: static; height: auto;
    flex-direction: column; border-right: 0; border-bottom: 1px solid var(--border);
    padding: 1rem;
  }
  .nav-actions { flex-direction: row; }
  .nav-actions #global-search { flex: 1; }
  #theme-toggle { width: auto; }
  .nav-links { flex-direction: row; overflow-x: auto; padding-bottom: .25rem; }
  .nav-links a { border-left: 0; border-bottom: 2px solid transparent; flex: none; }
  .nav-links a.active { border-bottom-color: var(--accent); background: transparent; }
  .nav-group-label { display: none; }
  main { grid-column: 1; padding: 0 24px 3rem; }
}
@media (max-width: 720px) {
  main { padding: 0 16px 2.5rem; }
  .hero { padding-top: 2rem; }
  .hero h1 { font-size: 1.85rem; }
  .grid.stats { grid-template-columns: repeat(2, 1fr); }
  .brand-text span { display: none; }
}

/* ---------- Print ---------- */
@media print {
  :root, :root[data-theme="dark"] {
    --bg: #ffffff; --surface: #ffffff; --surface-2: #f4f5f9; --surface-3: #eceef6;
    --fg: #0d1322; --fg-2: #3b455c; --muted: #55607a; --border: #d7dbe8; --border-soft: #e6e9f2;
    --shadow-1: none; --shadow-2: none; --shadow-3: none;
  }
  body { display: block; background: #fff; }
  body::before { display: none; }
  .topnav { display: none; }
  main { grid-column: 1; max-width: none; padding: 0 12px; margin: 0; }
  .hero { padding: .5rem 0 1rem; }
  .glass { box-shadow: none; border: 1px solid var(--border); backdrop-filter: none; }
  .howto.collapsed ol { display: grid; }
  .howto.collapsed h4::after { transform: none; }
  .section { margin: 1.25rem 0; page-break-inside: avoid; }
  .card, .table-wrap, .heat-map { page-break-inside: avoid; }
  table.data-table th { position: static; }
  a[href]::after { content: ""; }
  .toolbar, #theme-toggle { display: none; }
}
"""

    js = """
(function(){
  // Initial theme is already applied by the blocking <head> script (avoids
  // a flash of the wrong theme); this IIFE just wires up the toggle button.
  const root = document.documentElement;

  // Theme toggle
  const themeToggle = document.getElementById('theme-toggle');
  const syncThemeLabel = () => {
    if(!themeToggle) return;
    const dark = root.getAttribute('data-theme') === 'dark';
    themeToggle.textContent = dark ? 'Light mode' : 'Dark mode';
    themeToggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  };
  syncThemeLabel();
  themeToggle?.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('nse-theme', next);
    syncThemeLabel();
  });

  // Interactive line charts (dependency-free hover/tooltip)
  document.querySelectorAll(".chart-wrap").forEach(wrap => {
    let raw;
    try { raw = JSON.parse(wrap.dataset.values || "[]"); } catch (e) { raw = []; }
    const vals = raw.filter(v => typeof v === "number" && isFinite(v));
    if (vals.length < 2) return;
    const svg = wrap.querySelector(".chart-svg");
    const tip = wrap.querySelector(".chart-tooltip");
    const W = 600, H = 220, PAD = 8;
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const rng = (mx - mn) || 1;
    const n = vals.length;
    const xAt = i => (i / (n - 1)) * (W - PAD * 2) + PAD;
    const yAt = v => H - PAD - ((v - mn) / rng) * (H - PAD * 2);
    const pts = vals.map((v, i) => `${xAt(i).toFixed(2)},${yAt(v).toFixed(2)}`).join(" ");
    const areaPts = `${pts} ${xAt(n - 1).toFixed(2)},${H - PAD} ${xAt(0).toFixed(2)},${H - PAD}`;
    svg.innerHTML =
      `<polygon points="${areaPts}" fill="currentColor" fill-opacity="0.10"></polygon>` +
      `<polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" ` +
      `stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"></polyline>` +
      `<line class="chart-crosshair" x1="0" y1="0" x2="0" y2="${H}" style="display:none"></line>` +
      `<circle class="chart-dot" r="3.5" style="display:none"></circle>`;
    const crosshair = svg.querySelector(".chart-crosshair");
    const dot = svg.querySelector(".chart-dot");
    const unit = wrap.dataset.unit || "";
    const onMove = evt => {
      const rect = svg.getBoundingClientRect();
      if (!rect.width) return;
      const clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
      const xFrac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      const i = Math.round(xFrac * (n - 1));
      const v = vals[i];
      const x = xAt(i), y = yAt(v);
      crosshair.setAttribute("x1", x); crosshair.setAttribute("x2", x);
      crosshair.style.display = ""; dot.style.display = "";
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      const sessionsAgo = n - 1 - i;
      const when = sessionsAgo === 0 ? "Latest session" : `${sessionsAgo} session${sessionsAgo > 1 ? "s" : ""} ago`;
      tip.innerHTML = `<strong>${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit}</strong><span>${when}</span>`;
      tip.style.left = `${(x / W) * 100}%`;
      tip.style.opacity = "1";
    };
    const onLeave = () => {
      tip.style.opacity = "0";
      crosshair.style.display = "none";
      dot.style.display = "none";
    };
    wrap.addEventListener("mousemove", onMove);
    wrap.addEventListener("mouseleave", onLeave);
    wrap.addEventListener("touchmove", onMove, { passive: true });
    wrap.addEventListener("touchend", onLeave);
  });

  // Collapsible how-to callouts
  document.querySelectorAll('.howto').forEach(box => {
    const h = box.querySelector('h4');
    if(!h) return;
    box.classList.add('collapsed');
    h.setAttribute('role', 'button');
    h.setAttribute('tabindex', '0');
    h.setAttribute('aria-expanded', 'false');
    const toggle = () => {
      const closed = box.classList.toggle('collapsed');
      h.setAttribute('aria-expanded', String(!closed));
    };
    h.addEventListener('click', toggle);
    h.addEventListener('keydown', e => {
      if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); toggle(); }
    });
  });

  // Scrollspy — highlight the active section in the sidebar
  const links = Array.from(document.querySelectorAll('.nav-links a[href^="#"]'));
  const sections = links
    .map(a => document.querySelector(a.getAttribute('href')))
    .filter(Boolean);
  const onScroll = () => {
    const y = window.scrollY + 140;
    let current = null;
    for(const s of sections){ if(s.offsetTop <= y) current = s; }
    links.forEach(a => a.classList.toggle('active', !!current && a.getAttribute('href') === '#' + current.id));
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Right-align numeric table columns
  const SKIP = new Set(['-', '—', 'n/a', 'n.a.', '']);
  const isNum = t => {
    const s = t.replace(/[₹$,\s]/g, '');
    if(/^[+\-−]?\d+(\.\d+)?%?x?$/.test(s)) return true;
    if(/^[+\-−]?\d+(\.\d+)?\/[+\-−]?\d+(\.\d+)?$/.test(s)) return true;
    return false;
  };
  document.querySelectorAll('table.data-table').forEach(table => {
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    if(!rows.length) return;
    const heads = table.querySelectorAll('thead th');
    const nCols = heads.length;
    for(let c = 0; c < nCols; c++){
      let numeric = true, hasVal = false;
      for(const tr of rows){
        const td = tr.children[c];
        if(!td) continue;
        const t = td.innerText.trim();
        if(SKIP.has(t)) continue;
        if(td.querySelector('.badge')){ numeric = false; break; }
        hasVal = true;
        if(!isNum(t)){ numeric = false; break; }
      }
      if(numeric && hasVal){
        if(heads[c]) heads[c].classList.add('num');
        rows.forEach(tr => { if(tr.children[c]) tr.children[c].classList.add('num'); });
      }
    }
  });

  // Sortable tables
  document.querySelectorAll('table.sortable').forEach(table => {
    table.querySelectorAll('th').forEach((th, idx) => {
      th.addEventListener('click', () => {
        const tbody = table.tBodies[0];
        const rows = Array.from(tbody.rows);
        const asc = th.dataset.asc !== 'true';
        rows.sort((a,b) => {
          const av = a.cells[idx]?.innerText.trim() || '';
          const bv = b.cells[idx]?.innerText.trim() || '';
          const an = parseFloat(av.replace(/[%,+₹$]/g,''));
          const bn = parseFloat(bv.replace(/[%,+₹$]/g,''));
          let cmp;
          if(!isNaN(an) && !isNaN(bn)) cmp = an - bn;
          else cmp = av.localeCompare(bv);
          return asc ? cmp : -cmp;
        });
        th.dataset.asc = asc ? 'true' : 'false';
        rows.forEach(r => tbody.appendChild(r));
      });
    });
  });

  // Global search filter across tables and cards
  const search = document.getElementById('global-search');
  search?.addEventListener('input', () => {
    const q = search.value.toLowerCase().trim();
    document.querySelectorAll('table.data-table tbody tr').forEach(tr => {
      tr.style.display = !q || tr.innerText.toLowerCase().includes(q) ? '' : 'none';
    });
    document.querySelectorAll('.mini, .heat, .glass.card').forEach(el => {
      el.style.display = !q || el.innerText.toLowerCase().includes(q) ? '' : 'none';
    });
  });
})();
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>NSE Institutional Intelligence Dashboard</title>
<script>
(function(){{
  try {{
    var saved = localStorage.getItem('nse-theme');
    var theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
  }} catch (e) {{
    document.documentElement.setAttribute('data-theme', 'light');
  }}
}})();
</script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
{nav}
<main>
  <header class="hero">
    <span class="hero-eyebrow">NSE Market Intelligence - Evidence-scored</span>
    <h1>Institutional NSE Market Dashboard</h1>
    <p>Generated {_e(generated_at)} · Unavailable feeds explicitly labeled · Never invents market data</p>
  </header>
  {exec_html}
  {global_html}
  {nse_html}
  {breadth_html}
  {sector_html}
  {tech_html}
  {fund_html}
  {options_html}
  {watch_html}
  {alpha_html}
  {opp_html}
  {news_html}
  {eco_html}
  {risk_html}
  {insights_html}
  {changes_html}
  {final_html}
  <footer>
    <p>Cross-check critical decisions with primary exchange data. This dashboard never invents market prices or options metrics.</p>
    <p class="credit">Developed by Kamakshaiah Nelatur &middot; Hobby Investor</p>
    <p class="disclaimer">Personal project, not investment advice, not affiliated with any employer.</p>
    <p class="copyright">&copy; 2026 Kamakshaiah Nelatur</p>
  </footer>
</main>
<script>{js}</script>
</body>
</html>
"""
