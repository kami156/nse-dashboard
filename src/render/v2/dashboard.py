"""NSE Market Intelligence — v2 renderer.

Drop-in replacement for ``src.render.dashboard.render_html``: same payload
shape, one self-contained HTML file out. The information architecture collapses
the old 16 flat sections into six workspaces, and the symbol data that used to
be printed five times (technical, fundamental, watchlists, opportunities, final)
is printed once in the Screener.

Direction: tech-utility. Palette, fonts and posture come from the direction
library verbatim (see v2/styles.css); market direction uses --up/--down state
tokens so the accent stays a UI colour, never a data reading.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
DASH = "\u2014"
ECO_LABEL = {
    "inflation": "Inflation",
    "gdp": "GDP",
    "pmi": "PMI",
    "interest_rates": "Interest rates",
    "currency": "Currency",
    "commodities": "Commodities",
    "dollar_index": "Dollar index",
    "global_central_banks": "Global central banks",
}

WS = [
    ("cockpit", "Cockpit", "Regime, index board, breadth and global cues"),
    ("sectors", "Sectors", "Rotation ranks and momentum leadership"),
    ("screener", "Screener", "Every analysed symbol, one row each"),
    ("ideas", "Ideas", "Ranked shortlists and final deliverables"),
    ("options", "Options", "Model-POP credit structures and chain state"),
    ("briefing", "Briefing", "Narrative, risk, news, macro and change log"),
]


# --------------------------------------------------------------------- format
def e(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def n(v: Any, d: int = 2) -> str:
    if v is None or v == "":
        return DASH
    try:
        f = float(v)
    except (TypeError, ValueError):
        return e(v)
    if d == 0:
        return f"{f:,.0f}"
    return f"{f:,.{d}f}"


def pct(v: Any, d: int = 2) -> str:
    if v is None or v == "":
        return DASH
    try:
        return f"{float(v):+.{d}f}%"
    except (TypeError, ValueError):
        return e(v)


def inr(v: Any) -> str:
    if v is None or v == "":
        return DASH
    try:
        return f"\u20b9{float(v):,.0f}"
    except (TypeError, ValueError):
        return e(v)


_LONG_DECIMAL = re.compile(r"\d+\.\d{4,}")


def txt(v: Any) -> str:
    """Escaped prose from the pipeline, with runaway float artefacts rounded.

    The scorers interpolate raw floats into sentences ("US VIX 15.319999694824219"),
    which is noise the reader should never see. Anything already at 2dp is left alone.
    """
    if v is None:
        return ""

    def shrink(m: "re.Match[str]") -> str:
        try:
            return f"{float(m.group(0)):.2f}"
        except ValueError:
            return m.group(0)

    return html.escape(_LONG_DECIMAL.sub(shrink, str(v)), quote=True)


def chip_pct(v: Any, d: int = 2) -> str:
    if v is None:
        return f'<span class="chip ghost">{DASH}</span>'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return f'<span class="chip ghost">{DASH}</span>'
    cls = "up" if f > 0 else ("down" if f < 0 else "")
    return f'<span class="chip {cls}">{pct(f, d)}</span>'


def score(v: Any) -> str:
    if v is None:
        return f'<span class="score">{DASH}</span>'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return f'<span class="score">{DASH}</span>'
    cls = "hi" if f >= 65 else ("mid" if f >= 45 else "lo")
    return f'<span class="score {cls}" data-sort="{f:.1f}">{f:.0f}</span>'


def rating(v: Any) -> str:
    r = (v or "").strip()
    low = r.lower()
    cls = "hold"
    if low in ("strong buy", "buy"):
        cls = "buy"
    elif low in ("accumulate",):
        cls = "acc"
    elif low in ("reduce", "sell", "strong sell"):
        cls = "red"
    return f'<span class="rating {cls}">{e(r) or DASH}</span>'


def meter(v: Any) -> str:
    if v is None:
        return f'<span class="muted">{DASH}</span>'
    try:
        f = max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return f'<span class="muted">{DASH}</span>'
    cls = "" if f >= 65 else ("mid" if f >= 45 else "lo")
    return (f'<span class="meter {cls}" role="img" aria-label="{f:.0f} of 100">'
            f'<i style="width:{f:.0f}%"></i></span>')


def level_chip(v: Any) -> str:
    s = (v or "").strip().lower()
    cls = "up" if s == "low" else ("warn" if s == "moderate" else ("down" if s else ""))
    return f'<span class="chip {cls}">{e(v) or DASH}</span>'


def spark(vals: Optional[Sequence[float]], w: int = 132, h: int = 30) -> str:
    if not vals or len(vals) < 2:
        return ""
    vals = [float(x) for x in vals]
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1.0
    pts = []
    for i, v in enumerate(vals):
        x = i / (len(vals) - 1) * w
        y = h - 2 - ((v - mn) / rng) * (h - 5)
        pts.append(f"{x:.1f},{y:.1f}")
    d = " ".join(pts)
    up = vals[-1] >= vals[0]
    lab = f"{'up' if up else 'down'} {abs((vals[-1] - vals[0]) / vals[0] * 100):.2f}% over {len(vals)} sessions"
    return (f'<svg class="sp {"up" if up else "dn"}" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{lab}" preserveAspectRatio="none">'
            f'<polygon points="{d} {w},{h} 0,{h}" fill="currentColor" opacity="0.13"/>'
            f'<polyline points="{d}" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>')


def panel(title: str, body: str, sub: str = "", tools: str = "", note: str = "",
          pid: str = "", tight: bool = False) -> str:
    head = f'<header><h2>{e(title)}</h2>'
    if sub:
        head += f'<span class="sub">{e(sub)}</span>'
    if tools:
        head += f'<div class="tbl-tools">{tools}</div>'
    head += "</header>"
    idattr = f' id="{e(pid)}"' if pid else ""
    out = f'<section class="panel"{idattr}>{head}'
    out += f'<div class="panel-body{" tight" if tight else ""}">{body}</div>'
    if note:
        out += f'<p class="note-row">{note}</p>'
    return out + "</section>"


def table(cols: Sequence[Tuple[str, str]], rows: Sequence[Sequence[str]], tid: str,
          empty: str = "No rows match the current filter.") -> str:
    head = "".join(
        f'<th scope="col"{f" class=\"{c}\"" if c else ""}>'
        f'<button type="button" class="sort">{e(label)}</button></th>'
        for label, c in cols
    )
    trs = []
    for r in rows:
        tds = []
        for i, cell in enumerate(r):
            cls = cols[i][1] if i < len(cols) else ""
            label = cols[i][0] if i < len(cols) else ""
            attr = f' class="{cls}"' if cls else ""
            tds.append(f'<td{attr} data-label="{e(label)}">{cell}</td>')
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<div class="tbl-wrap"><table class="tbl stack-rows" id="{e(tid)}" '
            f'data-count="{e(tid)}"><thead><tr>{head}</tr></thead><tbody>'
            + "".join(trs) + "</tbody></table></div>"
            + f'<p class="empty js-empty" hidden>{e(empty)}</p>')


def csv_btn(tid: str, label: str = "CSV") -> str:
    return f'<button type="button" class="btn js-csv" data-target="{e(tid)}">{e(label)}</button>'


def kv_list(items: Iterable[str], tight: bool = False) -> str:
    rows = "".join(f"<li>{txt(x)}</li>" for x in items if x)
    return f'<ul class="list{" tight" if tight else ""}">{rows}</ul>' if rows else f'<p class="muted">{DASH}</p>'


def fii_summary(payload: Dict[str, Any]) -> str:
    fii = payload.get("fii_dii") or {}
    if fii.get("summary"):
        return str(fii["summary"])
    for block in (payload.get("nse_coverage") or {}).values():
        s = ((block or {}).get("institutional_activity") or {}).get("summary")
        if s:
            return str(s)
    return ""


# ------------------------------------------------------------------ cockpit
def cockpit(p: Dict[str, Any]) -> str:
    ex = p.get("exec_summary") or {}
    reg = p.get("regime") or {}
    idx = p.get("indices") or {}
    br = p.get("breadth") or {}
    gl = p.get("globals") or {}
    cov = p.get("nse_coverage") or {}
    sparklines = p.get("sparklines") or {}
    closes = sparklines.get("nifty_closes") or []

    nifty = idx.get("Nifty 50") or {}
    vix = idx.get("India VIX") or {}
    fii = fii_summary(p)
    adv, dec = br.get("advances") or 0, br.get("declines") or 0
    tot = (adv + dec + (br.get("unchanged") or 0)) or 1
    bull = (ex.get("bull_bear") or {}).get("bull")
    bear = (ex.get("bull_bear") or {}).get("bear")

    verdict = f"""
<div class="verdict" data-od-id="verdict-ribbon">
  <div class="verdict-lead">
    <p class="k">Session verdict</p>
    <p class="v">{e(ex.get("market_sentiment") or reg.get("market_sentiment")) or DASH}</p>
    <p class="s">{e(reg.get("market_regime")) or DASH} regime ·
      risk {e(ex.get("market_risk_label")) or DASH} ({n(ex.get("market_risk_score"), 1)})</p>
  </div>
  <div class="vcell">
    <p class="k">Nifty 50</p>
    <p class="v">{n(nifty.get("last"), 2)}</p>
    {chip_pct(nifty.get("change_pct"))}
    {spark(sparklines.get("sentiment"))}
  </div>
  <div class="vcell">
    <p class="k">Breadth</p>
    <p class="v">{n(br.get("breadth_score"), 1)}</p>
    <p class="f">{n(adv, 0)} adv / {n(dec, 0)} dec</p>
    <p class="f">highs {n(br.get("new_highs"), 0)} · lows {n(br.get("new_lows"), 0)}</p>
  </div>
  <div class="vcell">
    <p class="k">India VIX</p>
    <p class="v">{n(vix.get("last"), 2)}</p>
    {chip_pct(vix.get("change_pct"))}
    <p class="f">fear gauge</p>
  </div>
  <div class="vcell">
    <p class="k">Bull / Bear</p>
    <p class="v">{n(bull, 1)} / {n(bear, 1)}</p>
    <p class="f">weighted regime score</p>
  </div>
</div>"""

    # chart
    chg = None
    if closes:
        chg = (closes[-1] - closes[0]) / closes[0] * 100
    chart_legend = ""
    if closes:
        chart_legend = (
            '<div class="chart-legend">'
            f'<span class="lg"><i style="background:var(--up)"></i>Close {n(closes[-1], 2)}</span>'
            f'<span class="lg">Period change <b class="{"up" if (chg or 0) >= 0 else "down"}">{pct(chg)}</b></span>'
            f'<span class="lg">High <b>{n(max(closes), 2)}</b></span>'
            f'<span class="lg">Low <b>{n(min(closes), 2)}</b></span>'
            f'<span class="lg">Sessions <b>{len(closes)}</b></span>'
            "</div>"
        )
    chart_panel = panel(
        "Nifty 50 — daily closes",
        f'<div class="chart {"dn" if (chg or 0) < 0 else ""}" data-values="{json.dumps(closes)}" '
        f'data-unit="" data-od-id="nifty-chart"><svg preserveAspectRatio="none" aria-label="Nifty 50 close over {len(closes)} sessions"></svg>'
        f'<div class="tip"></div></div>{chart_legend}',
        sub=f"{len(closes)} sessions · yfinance daily closes",
        pid="panel-nifty-chart",
    )

    # index board
    rows = []
    for name, blk in cov.items():
        t = blk.get("technical") or {}
        q = blk.get("quote") or {}
        if t.get("status") == "unavailable":
            tech_cells = [f'<span class="muted">{DASH}</span>'] * 6
        else:
            tech_cells = [
                e(t.get("trend")) or DASH,
                e(t.get("momentum")) or DASH,
                n(t.get("support"), 2),
                n(t.get("resistance"), 2),
                n(t.get("relative_strength"), 1),
                score(t.get("technical_score")),
            ]
        rows.append([
            e(name), n(q.get("last"), 2), chip_pct(q.get("change_pct")),
            tech_cells[0], tech_cells[1], tech_cells[2], tech_cells[3], tech_cells[4], tech_cells[5],
        ])
    index_panel = panel(
        "Index board",
        table(
            [("Index", ""), ("Last", "num"), ("Chg%", ""), ("Trend", ""), ("Momentum", ""),
             ("Support", "num"), ("Resistance", "num"), ("RS", "num"), ("Tech score", "num")],
            rows, "tbl-indices",
        ),
        sub=f"{len(cov)} NSE indices",
        tools=csv_btn("tbl-indices"),
        note=(f"FII/DII cash activity is market-level and identical for every index row, so it is "
              f"stated once here: {e(fii) or 'unavailable this run'}."
              + (f" Unavailable indices are labelled, never inferred: "
                 + ", ".join(k for k, v in cov.items() if (v.get("technical") or {}).get("status") == "unavailable")
                 + "." if any((v.get("technical") or {}).get("status") == "unavailable" for v in cov.values()) else "")),
        pid="panel-indices",
    )

    leaders = br.get("volume_leaders") or []
    vol_rows = [[e(v.get("symbol")), chip_pct(v.get("change_pct")), n(v.get("volume"), 0), n(v.get("volume_ratio"), 2)]
                for v in leaders]
    breadth_body = (
        '<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">'
        f'<div class="kpi"><p class="k">Advances</p><p class="v up">{n(adv, 0)}</p></div>'
        f'<div class="kpi"><p class="k">Declines</p><p class="v down">{n(dec, 0)}</p></div>'
        f'<div class="kpi"><p class="k">Unchanged</p><p class="v">{n(br.get("unchanged"), 0)}</p></div>'
        "</div>"
        f'<div class="divbar" role="img" aria-label="{adv} advances, {dec} declines, {br.get("unchanged")} unchanged" '
        'style="margin-top:14px">'
        f'<i class="adv" style="width:{adv / tot * 100:.1f}%"></i>'
        f'<i class="unch" style="width:{(br.get("unchanged") or 0) / tot * 100:.1f}%"></i>'
        f'<i class="dec" style="width:{dec / tot * 100:.1f}%"></i></div>'
        '<div class="legend-inline">'
        f'<span>Advances <b>{adv / tot * 100:.0f}%</b></span>'
        f'<span>Declines <b>{dec / tot * 100:.0f}%</b></span>'
        f'<span>New highs <b>{n(br.get("new_highs"), 0)}</b></span>'
        f'<span>New lows <b>{n(br.get("new_lows"), 0)}</b></span>'
        f'<span>Breadth score <b>{n(br.get("breadth_score"), 1)}</b></span>'
        "</div>"
        f'<h3 style="font-size:12px;margin:18px 0 8px">Volume leaders</h3>'
        + table([("Symbol", ""), ("Chg%", ""), ("Volume", "num"), ("Vol ratio", "num")], vol_rows, "tbl-volume")
    )
    breadth_panel = panel("Participation", breadth_body,
                          sub="Nifty 500 universe",
                          note=txt((br.get("delivery_percentage") or {}).get("reason")) or "")

    # global cues
    gl_rows = []
    for name, q in gl.items():
        gl_rows.append([
            e(name), f'<span class="mono muted">{e(q.get("ticker"))}</span>',
            n(q.get("last"), 2), chip_pct(q.get("change_pct")),
            n(q.get("volume"), 0) if q.get("volume") else f'<span class="muted">{DASH}</span>',
        ])
    global_panel = panel("Global cues", table(
        [("Market", ""), ("Ticker", ""), ("Last", "num"), ("Change", ""), ("Volume", "num")],
        gl_rows, "tbl-global"), sub=f"{len(gl)} instruments", tools=csv_btn("tbl-global"),
        note=txt(p.get("global_impact")), pid="panel-global")

    # heat map
    heat = [h for h in (br.get("heat_map") or []) if abs(h.get("change_pct") or 0) >= 1]
    heat = sorted(heat, key=lambda x: x.get("change_pct") or 0, reverse=True)
    cells = "".join(
        f'<div class="{"dn" if (h.get("change_pct") or 0) < 0 else ""}" '
        f'style="--h:{min(100, abs(h.get("change_pct") or 0) / 6 * 100):.0f}" '
        f'title="{e(h.get("symbol"))}: {pct(h.get("change_pct"))}">'
        f'<span>{e(h.get("symbol"))}</span><b>{pct(h.get("change_pct"), 1)}</b></div>'
        for h in heat
    )
    heat_panel = panel("Movers heat map", f'<div class="heat">{cells}</div>',
                       sub=f"{len(heat)} Nifty 500 names moving 1% or more",
                       note="Fill intensity scales with the size of the move, capped at 6%.")

    return f"""
<div class="ws-head">
  <div>
    <h1>Market Cockpit</h1>
    <p>Regime, index board, participation and overnight cues in one read. Every figure here is from the
      generated run; unavailable feeds stay labelled.</p>
  </div>
  <p class="stamp">generated {e(p.get("generated_at"))}</p>
</div>
{verdict}
<div class="grid g-2-1" style="margin-top:16px">{chart_panel}{breadth_panel}</div>
<div style="margin-top:16px">{index_panel}</div>
<div class="grid g-2" style="margin-top:16px">{global_panel}{heat_panel}</div>
"""


# ------------------------------------------------------------------- sectors
def sectors(p: Dict[str, Any]) -> str:
    sr = p.get("sector_rotation") or {}
    ranked = sr.get("ranked") or []
    alpha = p.get("alpha_leaderboards") or {}
    base = alpha.get("nifty") or {}

    rows = []
    for r in ranked:
        rs = r.get("rank_score")
        width = 0.0
        try:
            width = max(4.0, min(100.0, float(rs))) if rs is not None else 0.0
        except (TypeError, ValueError):
            width = 0.0
        mom = r.get("momentum_1m_pct")
        dn = (mom or 0) < 0
        rows.append(f"""
<div class="rank" data-od-id="sector-rank-{e(str(r.get("sector", "")).lower().replace(" ", "-"))}">
  <span class="pos">{n(r.get("rank"), 0)}</span>
  <span class="nm">{e(r.get("sector"))}
    <span class="chip ghost" style="margin-left:6px">{e(r.get("trend")) or "n/a"}</span>
    <span class="track{" dn" if dn else ""}"><i style="width:{width:.0f}%"></i></span>
  </span>
  <span class="num r3">{chip_pct(r.get("change_pct"))}</span>
  <span class="num">RS {n(r.get("relative_strength"), 1)}</span>
  <span class="num">1M {pct(r.get("momentum_1m_pct"), 2)}</span>
</div>""")
    notes = [f'<b>{e(r.get("sector"))}</b> — {txt(r.get("ai_summary"))}' for r in ranked if r.get("ai_summary")]
    rotation = panel("Rotation ranks", "".join(rows),
                     sub=f"{len(ranked)} sector proxies · bar = rank score",
                     note=e(sr.get("method_note")), pid="panel-rotation")

    tier_cards = []
    for sec in alpha.get("sector_details") or []:
        tiers = "".join(
            f'<div class="tier"><h4>{e(t.get("label"))}</h4><ul class="list tight">'
            + ("".join(
                f'<li><span class="muted">{e(l.get("ticker"))}</span> <b class="{"up" if (l.get("r4w") or 0) >= 0 else "down"}">{pct(l.get("r4w"))}</b></li>'
                for l in (t.get("leaders") or [])) or '<li class="muted">No strong momentum</li>')
            + "</ul></div>"
            for t in (sec.get("tiers") or [])
        )
        tier_cards.append(f'<div class="panel"><header><h2>{e(sec.get("name"))}</h2>'
                          f'<span class="sub">4-week return vs Nifty</span></header>'
                          f'<div class="panel-body"><div class="grid g-4">{tiers}</div></div></div>')
    alpha_panel = panel(
        "Momentum leadership",
        f'<div class="grid g-2" style="align-items:start">{"".join(tier_cards)}</div>'
        if tier_cards else f'<p class="muted">No sector leadership detail in this run.</p>',
        sub=f"Nifty 50 baseline 4W {pct(base.get('r4w'))} · 1W {pct(base.get('r1w'))}",
        pid="panel-alpha")

    return f"""
<div class="ws-head">
  <div>
    <h1>Sector rotation</h1>
    <p>Ranked on relative strength and one-month momentum from index proxies. Rank score drives the bar;
      institutions, valuation and earnings trend are marked unavailable rather than filled in.</p>
  </div>
  <p class="stamp">{len(ranked)} proxies</p>
</div>
{rotation}
<div style="margin-top:16px">{alpha_panel}</div>
<div style="margin-top:16px">{panel("Per-sector read", kv_list(notes), sub="Generated summaries per proxy")}</div>
"""


# ------------------------------------------------------------------ screener
SHORT = {
    "Long Term Opportunities": "LT",
    "Swing Trading": "Swing",
    "Weekly Opportunities": "Weekly",
    "Monthly Opportunities": "Monthly",
}


def screener(p: Dict[str, Any]) -> str:
    wl = p.get("watchlists") or {}
    opps = p.get("opportunities") or {}
    by_opp = {o.get("symbol"): o for o in (opps if isinstance(opps, list) else [])}

    merged: Dict[str, Dict[str, Any]] = {}
    for name, cards in wl.items():
        for c in cards or []:
            sym = c.get("symbol")
            if not sym:
                continue
            rec = merged.setdefault(sym, dict(c))
            rec.setdefault("lists", [])
            rec["lists"].append(SHORT.get(name, name))
            if not rec.get("name"):
                rec["name"] = c.get("name")

    rows = []
    for sym in sorted(merged, key=lambda s: -(merged[s].get("overall_conviction") or 0)):
        c = merged[sym]
        t = c.get("tech") or {}
        f = (c.get("fund") or {}).get("metrics") or {}
        lists = " ".join(f'<span class="chip ghost">{e(x)}</span>' for x in c.get("lists", []))
        detail = t.get("rsi") is not None or f.get("pe") is not None
        rows.append([
            f'<span data-sort="{e(sym)}">{e(sym)}</span>',
            f'<span title="{e(c.get("name"))}">{e(c.get("name"))}</span>',
            rating(c.get("rating")),
            f'{meter(c.get("overall_conviction"))} {score(c.get("overall_conviction"))}',
            n(c.get("confidence_pct"), 1) + "%",
            score(c.get("technical_score")),
            score(c.get("fundamental_score")),
            score(c.get("momentum_score")),
            score(c.get("valuation_score")),
            score(c.get("risk_score")),
            (e(t.get("trend")) or f'<span class="muted">{DASH}</span>') if detail else f'<span class="muted">{DASH}</span>',
            n(t.get("rsi"), 1),
            n(t.get("adx"), 1),
            n(f.get("pe"), 1),
            (pct(f.get("revenue_growth")) if f.get("revenue_growth") is not None else DASH),
            (n(f.get("operating_margin_pct"), 1) if f.get("operating_margin_pct") is not None else DASH),
            (n(f.get("debt_to_equity_norm"), 2) if f.get("debt_to_equity_norm") is not None else DASH),
            lists,
        ])
    with_detail = sum(1 for s in merged if (merged[s].get("tech") or {}).get("rsi") is not None)
    ratings = sorted({c.get("rating") for c in merged.values() if c.get("rating")})
    trends = sorted({((c.get("tech") or {}).get("trend")) for c in merged.values()
                     if (c.get("tech") or {}).get("trend")})

    def select(fid: str, label: str, col: int, values: List[str]) -> str:
        opts = "".join(f'<option value="{e(v)}">{e(v)}</option>' for v in values)
        return (f'<select id="{fid}" class="js-filter" data-table="tbl-screener" data-col="{col}" '
                f'aria-label="{e(label)}"><option value="">{e(label)}</option>{opts}</select>')

    tools = (
        select("f-rating", "All ratings", 2, ratings)
        + select("f-trend", "All trends", 10, trends)
        + csv_btn("tbl-screener", "Export CSV")
        + '<span class="count js-count" data-for="tbl-screener"></span>'
    )
    return f"""
<div class="ws-head">
  <div>
    <h1>Screener</h1>
    <p>One row per analysed symbol. This single table replaces the five overlapping symbol tables in the
      previous dashboard (technical, fundamental, watchlist, opportunity and final-deliverable).</p>
  </div>
  <p class="stamp">{len(merged)} symbols</p>
</div>
{panel("All analysed symbols",
       table([("Symbol", "sym"), ("Name", "name"), ("Rating", ""), ("Conviction", ""), ("Conf", "num"),
              ("Tech", "num"), ("Fund", "num"), ("Mom", "num"), ("Val", "num"), ("Risk", "num"),
              ("Trend", ""), ("RSI", "num"), ("ADX", "num"), ("P/E", "num"), ("Rev gr", "num"),
              ("Op mgn", "num"), ("D/E", "num"), ("On lists", "")],
             rows, "tbl-screener"),
       sub="sort any column · search filters the whole workspace",
       tools=tools,
       note=(f"Indicator and valuation detail is populated for {with_detail} of {len(merged)} symbols in this "
             f"run, because the previous renderer only printed detail for two of the four lists. The pipeline "
             f"already scores the full Nifty 500, so a regenerated run fills every row."),
       pid="panel-screener", tight=False)}
"""


# --------------------------------------------------------------------- ideas
def ideas(p: Dict[str, Any]) -> str:
    wl = p.get("watchlists") or {}
    opps = p.get("opportunities") or []
    lists = p.get("executive_lists") or {}
    fin = p.get("final") or {}
    base = {c.get("symbol"): c for c in (wl.get("Long Term Opportunities") or [])}

    def shortlist(name: str, cards: List[Dict[str, Any]], reason_key: str = "evidence",
                  show_reason: bool = True) -> str:
        rows = []
        for i, c in enumerate(cards or [], 1):
            reason = ""
            if show_reason:
                if reason_key == "opp":
                    reason = f'{e(c.get("category"))} — {txt(c.get("reason"))}'
                else:
                    ev = c.get("evidence") or []
                    reason = txt("; ".join(ev[:2])) if ev else f'<span class="muted">{DASH}</span>'
            rows.append([
                str(i), f'<span data-sort="{e(c.get("symbol"))}">{e(c.get("symbol"))}</span>',
                f'<span title="{e(c.get("name"))}">{e(c.get("name"))}</span>',
                rating(c.get("rating")),
                f'{meter(c.get("overall_conviction"))} {score(c.get("overall_conviction"))}',
                n(c.get("confidence_pct"), 1) + "%",
                e(c.get("time_horizon")) or f'<span class="muted">{DASH}</span>',
                reason,
            ])
        cols = [("#", "num"), ("Symbol", "sym"), ("Name", "name"), ("Rating", ""), ("Conviction", ""),
                ("Conf", "num"), ("Horizon", ""), ("Why it qualifies", "")]
        tid = "tbl-" + name.lower().replace(" ", "-")
        return table(cols, rows, tid) + (
            f'<div class="tbl-tools" style="margin-top:10px">{csv_btn(tid)}'
            f'<span class="count js-count" data-for="{tid}"></span></div>')

    def fin_table(key: str, tid: str) -> str:
        rows = [[f'<span data-sort="{e(c.get("symbol"))}">{e(c.get("symbol"))}</span>', rating(c.get("rating")),
                 f'{meter(c.get("overall_conviction"))} {score(c.get("overall_conviction"))}',
                 n(c.get("confidence_pct"), 1) + "%", e(c.get("time_horizon")) or DASH]
                for c in (lists.get(key) or [])]
        return table([("Symbol", "sym"), ("Rating", ""), ("Conviction", ""), ("Conf", "num"), ("Horizon", "")],
                     rows, tid)

    def symbols(key: str) -> List[str]:
        return [c.get("symbol") for c in (lists.get(key) or []) if c.get("symbol")]

    metas = {k: (lists.get(k + "_meta") or {}) for k in ("top_conviction", "top_swing", "top_long_term")}

    def fin_title(key: str, label: str) -> str:
        return f"Top {len(lists.get(key) or [])} {label}"

    def fin_note(key: str) -> str:
        m = metas[key]
        bits: List[str] = []
        if m.get("cohort"):
            bits.append(f"Source: {m['cohort']} ({m.get('cohort_size', '?')} names), "
                        f"ranked by {m.get('metric')}.")
        held = m.get("excluded_as_already_listed") or []
        if held:
            shown = ", ".join(x.replace(".NS", "") for x in held[:6])
            more = f" +{len(held) - 6} more" if len(held) > 6 else ""
            bits.append(f"{len(held)} name(s) already listed above are held back: {shown}{more}.")
        if m.get("shortfall"):
            bits.append(txt(m.get("shortfall_reason")))
        return txt(" ".join(bits))

    pairs = [("top_conviction", "top_swing"), ("top_conviction", "top_long_term"),
             ("top_swing", "top_long_term")]
    dupes = [f"{a.replace('top_', '').replace('_', ' ')} and {b.replace('top_', '').replace('_', ' ')}"
             for a, b in pairs if symbols(a) and symbols(a) == symbols(b)]
    total = sum(len(symbols(k)) for k in ("top_conviction", "top_swing", "top_long_term"))
    distinct = len(set(symbols("top_conviction")) | set(symbols("top_swing")) | set(symbols("top_long_term")))
    spread = (f"{distinct} distinct symbols across {total} rows — no symbol repeats across the three lists."
              if distinct == total else f"{distinct} distinct symbols across {total} rows.")
    if dupes:
        spread += " Identical lists still present: " + "; ".join(dupes) + "."

    subs = "".join(
        f'<button type="button" class="subtab" role="tab" data-group="ideas" data-sub="{key}" '
        f'aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        for i, (key, label) in enumerate([
            ("opps", "Opportunities"), ("lt", "Long term"), ("swing", "Swing"),
            ("weekly", "Weekly"), ("monthly", "Monthly"), ("deliverables", "Deliverables"),
        ])
    )
    panes = f"""
<div class="js-sub" data-group="ideas" data-sub="opps">
  {panel("Opportunity engine — top 10", shortlist("opportunities", opps, "opp", True),
         sub="rule-triggered categories, ranked by conviction", pid="panel-opps")}
</div>
<div class="js-sub" data-group="ideas" data-sub="lt" hidden>
  {panel("Long term opportunities", shortlist("longterm", wl.get("Long Term Opportunities")),
         sub="quality and valuation with a 200-day uptrend", pid="panel-lt")}
</div>
<div class="js-sub" data-group="ideas" data-sub="swing" hidden>
  {panel("Swing setups", shortlist("swing", wl.get("Swing Trading")),
         sub="oversold RSI bounce or positive MACD histogram", pid="panel-swing")}
</div>
<div class="js-sub" data-group="ideas" data-sub="weekly" hidden>
  {panel("Weekly opportunities", shortlist("weekly", wl.get("Weekly Opportunities")),
         sub="one-month momentum above 5% on above-average volume", pid="panel-weekly")}
</div>
<div class="js-sub" data-group="ideas" data-sub="monthly" hidden>
  {panel("Monthly opportunities", shortlist("monthly", wl.get("Monthly Opportunities")),
         sub="50/200 alignment with three-month momentum above 10%", pid="panel-monthly")}
</div>
<div class="js-sub" data-group="ideas" data-sub="deliverables" hidden>
  <div class="stack">
    {panel("Executive conclusion", f'<p class="prose">{txt(fin.get("conclusion"))}</p>',
           sub=e(p.get("generated_at")), pid="panel-conclusion")}
    <div class="grid g-3">
      {panel(fin_title("top_conviction", "conviction"), fin_table("top_conviction", "tbl-final-conviction"),
             sub="universe-wide, ranked on overall conviction",
             tools=csv_btn("tbl-final-conviction"), note=fin_note("top_conviction"))}
      {panel(fin_title("top_swing", "swing"), fin_table("top_swing", "tbl-final-swing"),
             sub=spread, tools=csv_btn("tbl-final-swing"), note=fin_note("top_swing"))}
      {panel(fin_title("top_long_term", "long term"), fin_table("top_long_term", "tbl-final-longterm"),
             sub="fundamental-weighted within the long-term screen",
             tools=csv_btn("tbl-final-longterm"), note=fin_note("top_long_term"))}
    </div>
    <div class="grid g-2">
      {panel("Top risks to monitor", kv_list(fin.get("top_risks") or []))}
      {panel("Focus areas for the next hour", kv_list(fin.get("focus_next_hour") or []))}
    </div>
  </div>
</div>"""
    return f"""
<div class="ws-head">
  <div>
    <h1>Ideas</h1>
    <p>Ranked shortlists per time horizon, then the report's closing deliverables. Every row carries the
      reason it qualified, so a name can be audited without leaving the page.</p>
  </div>
  <p class="stamp">{len(opps)} discovered opportunities</p>
</div>
<div class="subtabs" role="tablist" aria-label="Idea lists" style="margin-bottom:14px">{subs}</div>
{panes}
"""


# ------------------------------------------------------------------- options
def options(p: Dict[str, Any]) -> str:
    opt = p.get("options") or {}
    recs = opt.get("recommendations") or []
    symbols = opt.get("symbols") or []

    rec_rows = []
    for s in recs:
        pop = (s.get("approx_pop") or 0) * 100
        meet = s.get("meets_80pct_target")
        rec_rows.append([
            f'<span data-sort="{e(s.get("symbol"))}">{e(s.get("symbol"))}</span>',
            e(s.get("tenor")), f'<span class="mono">{e(s.get("expiry"))}</span>',
            f'{e(s.get("strategy"))}<br><span class="mono muted" style="font-size:11px">{e(s.get("legs"))}</span>',
            f'{meter(pop)} <span class="mono">{pop:.1f}%</span>',
            ('<span class="chip up">yes</span>' if meet else '<span class="chip down">no</span>'),
            n(s.get("confidence_pct"), 1) + "%",
            e(s.get("direction_bias")),
            inr(s.get("est_max_profit_inr")), inr(s.get("est_max_loss_inr")),
        ])
    board = panel(
        "Strategy board",
        table([("Symbol", "sym"), ("Tenor", ""), ("Expiry", ""), ("Strategy & legs", ""), ("Model POP", ""),
               ("\u226580%", ""), ("Conf", "num"), ("Bias", ""), ("Max profit", "num"), ("Max loss", "num")],
              rec_rows, "tbl-strategies"),
        sub=f"{len(recs)} structures · target {((opt.get('target_pop') or 0.8) * 100):.0f}% model POP",
        tools=csv_btn("tbl-strategies"),
        note="Model POP is a distance-versus-IV estimate, not a realised win rate. Max profit and loss are "
             "per-lot model values from the NSE chain.",
        pid="panel-strategies")

    tabs, panes = [], []
    for i, sym in enumerate(symbols):
        name = sym.get("symbol")
        blocks = []
        for tenor in ("weekly", "monthly"):
            b = sym.get(tenor)
            if not b or b.get("status") != "ok":
                blocks.append(panel(f"{name} — {tenor}", f'<p class="muted">{DASH} not available this run</p>'))
                continue
            stats = "".join(
                f'<div class="kpi"><p class="k">{e(k)}</p><p class="v">{v}</p></div>'
                for k, v in [
                    ("Expiry", e(b.get("expiry"))),
                    ("Spot", n(b.get("spot"), 2)),
                    ("DTE", n(b.get("dte"), 0)),
                    ("PCR (OI)", n(b.get("pcr_oi"), 3)),
                    ("Max pain", n(b.get("max_pain"), 0)),
                    ("ATM IV", n((b.get("atm") or {}).get("atm_iv"), 2)),
                    ("1SD move", f'{n(b.get("expected_move_1sd"), 1)} ({n(b.get("expected_move_pct"), 2)}%)'),
                ])
            srows = []
            for s in b.get("strategies") or []:
                pop = (s.get("approx_pop") or 0) * 100
                srows.append([
                    f'{e(s.get("strategy"))}<br><span class="mono muted" style="font-size:11px">{e(s.get("legs"))}</span>',
                    f'{meter(pop)} <span class="mono">{pop:.1f}%</span>',
                    ('<span class="chip up">yes</span>' if s.get("meets_80pct_target") else '<span class="chip down">no</span>'),
                    n(s.get("confidence_pct"), 1) + "%",
                    n(s.get("est_credit_pts"), 2),
                    inr(s.get("est_max_profit_inr")), inr(s.get("est_max_loss_inr")),
                ])
            why = [f'<b>{e(s.get("strategy"))}</b> — {txt(s.get("why"))}' for s in (b.get("strategies") or []) if s.get("why")]
            tid = f"tbl-{name.lower()}-{tenor}"
            blocks.append(panel(
                f"{name} — {tenor}",
                f'<div class="kpis">{stats}</div>'
                f'<p class="prose" style="margin-top:14px"><b>Bias:</b> {e(b.get("bias")) or DASH}</p>'
                + table([("Strategy & legs", ""), ("Model POP", ""), ("\u226580%", ""), ("Conf", "num"),
                         ("Est credit", "num"), ("Max profit", "num"), ("Max loss", "num")],
                        srows, tid)
                + kv_list(why, tight=True)
                + f'<div class="tbl-tools" style="margin-top:10px">{csv_btn(tid)}</div>',
                sub=f'expiry {e(b.get("expiry"))} · {n(b.get("dte"), 0)} DTE',
                note=txt((b.get("buildups") or {}).get("note"))))
        tabs.append(f'<button type="button" class="subtab" role="tab" data-group="optsym" data-sub="{e(name)}" '
                    f'aria-selected="{"true" if i == 0 else "false"}">{e(name)}</button>')
        panes.append(f'<div class="js-sub" data-group="optsym" data-sub="{e(name)}"{" hidden" if i else ""}>'
                     f'<div class="stack">{"".join(blocks)}</div></div>')

    return f"""
<div class="ws-head">
  <div>
    <h1>Options analytics</h1>
    <p>Credit structures screened for a model probability of profit near 80%, with the chain state behind each
      one. Chain source: <a href="{e(opt.get("source_page") or "https://www.nseindia.com/option-chain")}"
      target="_blank" rel="noopener" style="text-decoration:underline">NSE option chain</a>.</p>
  </div>
  <p class="stamp">status {e(opt.get("status")) or DASH}</p>
</div>
{board}
<div style="margin-top:16px">
  <div class="subtabs" role="tablist" aria-label="Options underlyings" style="margin-bottom:14px">{"".join(tabs)}</div>
  {"".join(panes)}
</div>
"""


# ------------------------------------------------------------------ briefing
def briefing(p: Dict[str, Any]) -> str:
    ex = p.get("exec_summary") or {}
    ins = p.get("insights") or {}
    risk = p.get("risk_dashboard") or {}
    news = p.get("news") or {}
    eco = p.get("economy") or {}
    ch = p.get("hourly_changes") or {}

    prose = "".join(
        panel(title, f'<p class="prose">{txt(ins.get(key))}</p>')
        for title, key in [("Market summary", "market_summary"), ("Weekly outlook", "weekly_outlook"),
                           ("Monthly outlook", "monthly_outlook")]
        if ins.get(key)
    )
    outlook = panel("Sector outlook & themes",
                    f'<h3 style="font-size:12px;margin-bottom:6px">Sector outlook</h3>'
                    + kv_list(ins.get("sector_outlook") or [])
                    + '<h3 style="font-size:12px;margin:16px 0 6px">Key themes</h3>'
                    + kv_list(ins.get("key_themes") or [])
                    + '<h3 style="font-size:12px;margin:16px 0 6px">Opportunities</h3>'
                    + kv_list((ins.get("opportunities") or [])[:10]))

    risk_rows = []
    for i in risk.get("items") or []:
        risk_rows.append([
            e(i.get("name")), f'{meter(i.get("score"))} <span class="mono">{n(i.get("score"), 1)}</span>',
            level_chip(i.get("level")), txt(i.get("detail")),
        ])
    risk_panel = panel("Risk matrix", table(
        [("Risk type", ""), ("Score", ""), ("Level", ""), ("Detail", "")], risk_rows, "tbl-risk"),
        sub="higher score = more risk", tools=csv_btn("tbl-risk"),
        note="Valuation risk is intentionally unavailable where no CAPE or PE-band source exists.")

    eco_cards = []
    for key, obj in eco.items():
        label = ECO_LABEL.get(key, key.replace("_", " ").title())
        if not isinstance(obj, dict):
            continue
        if obj.get("items"):
            body = "".join(
                f'<li><span class="muted">{e(x.get("name"))}</span> <b>{n(x.get("last"), 2)}</b> {chip_pct(x.get("change_pct"))}</li>'
                for x in obj["items"])
            inner = f'<ul class="kv">{body}</ul>'
        elif obj.get("status") == "ok" and obj.get("last") is not None:
            inner = (f'<p><span class="mono" style="font-size:17px">{n(obj.get("last"), 2)}</span> '
                     f'{chip_pct(obj.get("change_pct"))}</p>')
        else:
            inner = f'<p class="muted">{txt(obj.get("reason")) or "Unavailable"}</p>'
        note = txt(obj.get("note"))
        eco_cards.append(f'<div class="mini-card{" unavail" if not inner.startswith("<p><span") and not obj.get("items") else ""}">'
                         f'<h3>{e(label)}</h3><div class="body">{inner}</div>'
                         + (f'<p class="muted" style="font-size:11px;margin-top:6px">{note}</p>' if note else "")
                         + "</div>")
    eco_panel = panel("Macro & economy", f'<div class="grid g-3">{"".join(eco_cards)}</div>',
                      sub="labelled, never inferred")

    news_cards = []
    for item in news.get("items") or []:
        heads = "".join(f"<li>{txt(h)}</li>" for h in (item.get("headlines") or [])[:4])
        news_cards.append(
            f'<div class="mini-card js-filterable"><h3>{e(item.get("category"))} '
            f'<span class="chip ghost">{e(item.get("status"))}</span></h3>'
            f'<ul class="list tight" style="margin-top:8px">{heads}</ul>'
            f'<p class="muted" style="font-size:11.5px;margin-top:8px">'
            f'<b>Likely impact:</b> {txt(item.get("likely_impact"))}</p>'
            f'<p class="muted" style="font-size:11px">{txt(item.get("source"))}</p></div>')
    news_panel = panel("News intelligence", f'<div class="grid g-2">{"".join(news_cards)}</div>',
                       sub=f'{len(news_cards)} categories · headlines only, not filings',
                       note=txt(news.get("note")))

    items = ch.get("items") or []
    by_type: Dict[str, int] = {}
    for i in items:
        by_type[str(i.get("type"))] = by_type.get(str(i.get("type")), 0) + 1
    type_rows = [[f'<span class="chip ghost">{e(k)}</span>', f'<span class="mono">{v}</span>']
                 for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])]
    ch_rows = [[f'<span class="chip ghost">{e(i.get("type"))}</span>', e(i.get("label")), txt(i.get("detail"))]
               for i in items]
    ch_panel = panel(
        "Change detection",
        f'<p class="prose">{txt(ch.get("summary"))}</p>'
        + table([("Change type", ""), ("Count", "num")], type_rows, "tbl-changetypes")
        + f'<details style="margin-top:14px"><summary style="cursor:pointer;font-size:12.5px;color:var(--muted)">'
          f'Show all {len(items)} raw changes</summary>'
        + table([("Type", ""), ("Label", ""), ("Detail", "")], ch_rows, "tbl-changes")
        + "</details>",
        sub=f'{len(items)} changes vs prior snapshot', tools=csv_btn("tbl-changes"),
        pid="panel-changes")

    return f"""
<div class="ws-head">
  <div>
    <h1>Briefing</h1>
    <p>The narrative layer: what the evidence adds up to, what could go wrong, and what moved since the
      previous run.</p>
  </div>
  <p class="stamp">{e(p.get("generated_at"))}</p>
</div>
{panel("One-minute briefing", f'<p class="prose">{txt(ex.get("one_minute_briefing"))}</p>', pid="panel-brief")}
<div class="grid g-2-1" style="margin-top:16px">
  <div class="stack">{prose}{outlook}</div>
  {risk_panel}
</div>
<div style="margin-top:16px">{eco_panel}</div>
<div style="margin-top:16px">{news_panel}</div>
<div style="margin-top:16px">{ch_panel}</div>
"""


# ---------------------------------------------------------------------- shell
def render_html(payload: Dict[str, Any], *, standalone: bool = True) -> str:
    css = (HERE / "styles.css").read_text(encoding="utf-8")
    js = (HERE / "app.js").read_text(encoding="utf-8")
    reg = payload.get("regime") or {}
    warnings = payload.get("warnings") or []
    sources = payload.get("sources") or []
    fin = payload.get("final") or {}
    foot = payload.get("footer") or {}
    title = "NSE Market Intelligence"

    tabs = "".join(
        f'<button type="button" class="tab" role="tab" data-ws="{wid}" '
        f'aria-selected="{"true" if i == 0 else "false"}" tabindex="{"0" if i == 0 else "-1"}" '
        f'title="{e(desc)}">{e(label)}</button>'
        for i, (wid, label, desc) in enumerate(WS)
    )
    bodies = {
        "cockpit": cockpit(payload), "sectors": sectors(payload), "screener": screener(payload),
        "ideas": ideas(payload), "options": options(payload), "briefing": briefing(payload),
    }
    panes = "".join(
        f'<div class="ws" data-ws="{wid}"{" hidden" if i else ""} data-od-id="ws-{wid}">'
        f'<div class="shell">{bodies[wid]}</div></div>'
        for i, (wid, _, _) in enumerate(WS)
    )
    footer = f"""
<footer class="foot">
  <div class="foot-in">
    <div>
      <h4>Data sources</h4>
      <ul>{''.join(f"<li>{txt(s)}</li>" for s in sources) or f"<li>{DASH}</li>"}</ul>
    </div>
    <div>
      <h4>Data quality</h4>
      <ul>
        <li>Generated {e(payload.get("generated_at"))}</li>
        <li>{len(warnings)} fetch warning(s): {txt("; ".join(warnings[:3])) if warnings else "none"}</li>
        <li>Unavailable feeds are labelled in place and never estimated.</li>
        <li>Market prices via yfinance; FII/DII, constituents and option chain via nselib with nsepython fallback.</li>
      </ul>
      <h4 style="margin-top:14px">Provenance</h4>
      <ul>
        <li class="credit">{txt(foot.get("credit"))}</li>
        <li>{txt(foot.get("note"))}</li>
        <li>{txt(foot.get("disclaimer"))}</li>
        <li>{txt(foot.get("copyright"))}</li>
      </ul>
    </div>
  </div>
</footer>"""

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{e(title)} — Institutional Dashboard</title>
<meta name="description" content="Evidence-scored NSE market intelligence dashboard generated {e(payload.get("generated_at"))}."/>
<script>
(function(){{try{{var s=localStorage.getItem('nse-theme');var m=window.matchMedia('(prefers-color-scheme: dark)').matches;
document.documentElement.setAttribute('data-theme', s || (m ? 'dark' : 'light'));}}catch(e){{}}}})();
</script>
<style>
{css}
</style>
</head>
<body>
<header class="bar" data-od-id="topbar">
  <div class="bar-in">
    <div class="brand">
      <span class="brand-mark">N</span>
      <span class="brand-txt"><b>NSE Market Intelligence</b>
        <span>{e(reg.get("market_regime")) or DASH} · {e(payload.get("generated_at"))}</span></span>
    </div>
    <span class="bar-fill"></span>
    <div class="bar-tools">
      <label class="search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input id="global-search" type="search" placeholder="Filter symbols, sectors, sections&hellip;" aria-label="Filter the dashboard"/>
      </label>
      <button type="button" class="btn btn-icon" id="theme-toggle" aria-label="Switch theme">Dark</button>
    </div>
  </div>
  <nav class="tabs" role="tablist" aria-label="Workspaces">{tabs}</nav>
</header>
<main>{panes}</main>
{footer}
<script>
{js}
</script>
</body>
</html>
"""
