"""NSE options analytics: weekly/monthly chain metrics + ~80% POP strategy ideas."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.data.nse_option_chain import (
    INDEX_SYMBOLS,
    chain_to_frame,
    classify_expiries,
    fetch_option_chain_raw,
)

# Approximate index lot sizes (verify on NSE; used only for notional illustration)
LOT_SIZE = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
    "FINNIFTY": 60,
    "MIDCPNIFTY": 120,
}

# Target theoretical probability of profit for short-premium structures
TARGET_POP = 0.80


def _safe_div(a: float, b: float) -> Optional[float]:
    if b is None or b == 0:
        return None
    return a / b


def compute_pcr(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    pe_oi = float(df["pe_oi"].sum())
    ce_oi = float(df["ce_oi"].sum())
    pe_vol = float(df["pe_volume"].sum())
    ce_vol = float(df["ce_volume"].sum())
    return {
        "pcr_oi": round(pe_oi / ce_oi, 3) if ce_oi else None,
        "pcr_volume": round(pe_vol / ce_vol, 3) if ce_vol else None,
        "total_pe_oi": pe_oi,
        "total_ce_oi": ce_oi,
    }


def compute_max_pain(df: pd.DataFrame) -> Optional[float]:
    strikes = df["strike"].astype(float).values
    if len(strikes) == 0:
        return None
    best_strike = None
    best_pain = None
    for s in strikes:
        # Call writers pain if spot settles above strike; put writers if below
        call_pain = ((df["strike"] < s).astype(float) * (s - df["strike"]) * df["ce_oi"]).sum()
        put_pain = ((df["strike"] > s).astype(float) * (df["strike"] - s) * df["pe_oi"]).sum()
        pain = float(call_pain + put_pain)
        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = float(s)
    return best_strike


def atm_iv(df: pd.DataFrame, spot: float) -> Dict[str, Any]:
    if df.empty or spot is None:
        return {"atm_iv": None, "ce_iv": None, "pe_iv": None, "atm_strike": None}
    idx = (df["strike"] - spot).abs().idxmin()
    row = df.loc[idx]
    ce_iv = row.get("ce_iv")
    pe_iv = row.get("pe_iv")
    vals = [v for v in (ce_iv, pe_iv) if v is not None and v > 0]
    return {
        "atm_strike": float(row["strike"]),
        "ce_iv": float(ce_iv) if ce_iv else None,
        "pe_iv": float(pe_iv) if pe_iv else None,
        "atm_iv": float(np.mean(vals)) if vals else None,
    }


def expected_move(spot: float, atm_iv_pct: Optional[float], dte: int) -> Optional[float]:
    """1 SD expected move ≈ spot * IV * sqrt(T). IV from NSE is in percent."""
    if not spot or not atm_iv_pct or atm_iv_pct <= 0 or dte is None or dte < 0:
        return None
    t = max(dte, 1) / 365.0
    return float(spot * (atm_iv_pct / 100.0) * math.sqrt(t))


def dte_days(expiry_str: str) -> Optional[int]:
    from src.data.nse_option_chain import _parse_expiry
    from datetime import datetime

    dt = _parse_expiry(expiry_str)
    if not dt:
        return None
    return max(0, (dt.date() - datetime.now().date()).days)


def strike_step(df: pd.DataFrame) -> int:
    strikes = sorted(df["strike"].astype(float).unique())
    if len(strikes) < 2:
        return 50
    diffs = np.diff(strikes)
    diffs = diffs[diffs > 0]
    return int(np.median(diffs)) if len(diffs) else 50


def approx_delta_from_distance(distance: float, em: float) -> Optional[float]:
    """
    Rough normal approx: z = distance / EM (1 SD).
    Call delta ≈ N(z) for ITM convention is messy; for OTM short call use 1-N(z).
    For OTM put (strike < spot): delta ≈ -N(-z) ≈ -(1-N(z)) magnitude.
    Returns absolute delta estimate in (0, 0.5] for OTM options.
    """
    if em is None or em <= 0:
        return None
    z = abs(distance) / em
    # survival function approx via erf
    # P(|X| > z*sd) one-tail
    from math import erf, sqrt

    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    otm_prob = 1 - cdf  # approx chance of finishing beyond strike for 1-sided
    # Absolute delta ~ probability of finishing ITM ≈ otm side for OTM shorts is 1-cdf for calls above spot
    abs_delta = max(0.01, min(0.49, 1 - cdf))
    return abs_delta


def find_short_strike_for_pop(
    df: pd.DataFrame,
    spot: float,
    em: float,
    side: str,
    target_pop: float = TARGET_POP,
) -> Optional[Dict[str, Any]]:
    """
    Pick OTM short strike whose approx POP >= target_pop.
    POP for short put ≈ 1 - P(spot < strike) ≈ using distance/EM.
    For short put: want strike so far below that P(touch) <= 1-target_pop.
    """
    step = strike_step(df)
    target_delta = 1 - target_pop  # ~0.20 for 80% POP
    if side == "put":
        candidates = df[df["strike"] < spot].sort_values("strike", ascending=False)
    else:
        candidates = df[df["strike"] > spot].sort_values("strike", ascending=True)

    best = None
    for _, row in candidates.iterrows():
        strike = float(row["strike"])
        distance = abs(strike - spot)
        abs_delta = approx_delta_from_distance(distance, em)
        if abs_delta is None:
            continue
        pop = 1 - abs_delta
        ltp = row.get("pe_ltp") if side == "put" else row.get("ce_ltp")
        oi = row.get("pe_oi") if side == "put" else row.get("ce_oi")
        iv = row.get("pe_iv") if side == "put" else row.get("ce_iv")
        # Prefer first strike that meets POP (closest to money among qualifiers)
        if pop + 1e-6 >= target_pop:
            best = {
                "side": side,
                "strike": strike,
                "approx_delta": round(abs_delta, 3),
                "approx_pop": round(pop, 3),
                "ltp": float(ltp) if ltp is not None else None,
                "oi": int(oi) if oi is not None else None,
                "iv": float(iv) if iv else None,
                "distance": round(distance, 2),
                "distance_pct": round(distance / spot * 100, 2),
            }
            break
    # If none met, take furthest OTM available and label actual POP
    if best is None and not candidates.empty:
        row = candidates.iloc[-1] if side == "put" else candidates.iloc[-1]
        strike = float(row["strike"])
        distance = abs(strike - spot)
        abs_delta = approx_delta_from_distance(distance, em) or 0.25
        pop = 1 - abs_delta
        ltp = row.get("pe_ltp") if side == "put" else row.get("ce_ltp")
        best = {
            "side": side,
            "strike": strike,
            "approx_delta": round(abs_delta, 3),
            "approx_pop": round(pop, 3),
            "ltp": float(ltp) if ltp is not None else None,
            "oi": int(row.get("pe_oi") if side == "put" else row.get("ce_oi") or 0),
            "iv": float(row.get("pe_iv") if side == "put" else row.get("ce_iv") or 0) or None,
            "distance": round(distance, 2),
            "distance_pct": round(distance / spot * 100, 2),
            "note": "Chain edge — POP may be below target",
        }
    if best:
        best["wing_width"] = step * 2  # default 2 strikes for credit spread
        best["long_strike"] = best["strike"] - best["wing_width"] if side == "put" else best["strike"] + best["wing_width"]
    return best


def detect_buildups(df: pd.DataFrame, spot: float) -> Dict[str, Any]:
    """Classify CE/PE OI change near ATM as long/short buildup proxies."""
    band = df[(df["strike"] >= spot * 0.97) & (df["strike"] <= spot * 1.03)].copy()
    if band.empty:
        band = df.copy()

    def classify(chg_oi: float, price_up: bool) -> str:
        # Without reliable underlying day direction per strike LTP change,
        # use OI change sign + IV/LTP as weak proxy — label as tentative.
        if chg_oi > 0:
            return "OI increase (build-up) — confirm with price direction"
        if chg_oi < 0:
            return "OI decrease (unwinding/covering) — confirm with price direction"
        return "Flat OI"

    ce_chg = float(band["ce_chg_oi"].sum())
    pe_chg = float(band["pe_chg_oi"].sum())
    top_ce = df.nlargest(5, "ce_oi")[["strike", "ce_oi", "ce_chg_oi", "ce_iv", "ce_ltp"]].to_dict("records")
    top_pe = df.nlargest(5, "pe_oi")[["strike", "pe_oi", "pe_chg_oi", "pe_iv", "pe_ltp"]].to_dict("records")
    return {
        "near_atm_ce_chg_oi": ce_chg,
        "near_atm_pe_chg_oi": pe_chg,
        "ce_signal": classify(ce_chg, True),
        "pe_signal": classify(pe_chg, False),
        "top_ce_oi_strikes": top_ce,
        "top_pe_oi_strikes": top_pe,
        "note": (
            "NSE chain does not always expose clean per-strike price direction vs OI; "
            "build-up labels are OI-change based and must be confirmed on the live chart."
        ),
    }


def bias_from_pcr_maxpain(pcr_oi: Optional[float], max_pain: Optional[float], spot: float) -> str:
    bits = []
    if pcr_oi is not None:
        if pcr_oi >= 1.2:
            bits.append("elevated PCR (put-heavy / cautious-to-bullish hedge tone)")
        elif pcr_oi <= 0.7:
            bits.append("low PCR (call-heavy / complacent-to-bearish risk)")
        else:
            bits.append("balanced PCR")
    if max_pain and spot:
        if spot > max_pain * 1.003:
            bits.append("spot above max pain")
        elif spot < max_pain * 0.997:
            bits.append("spot below max pain")
        else:
            bits.append("spot near max pain")
    return "; ".join(bits) if bits else "insufficient bias inputs"


def recommend_strategies(
    symbol: str,
    tenor: str,
    spot: float,
    em: Optional[float],
    pcr: Dict[str, Any],
    max_pain: Optional[float],
    df: pd.DataFrame,
    atm: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Recommend defined-risk premium strategies targeting ~80% theoretical POP.
    POP is model-based (distance vs expected move), NOT a guaranteed win rate.
    """
    recs: List[Dict[str, Any]] = []
    if not spot or em is None or em <= 0 or df is None or df.empty:
        return [
            {
                "strategy": "Unavailable",
                "tenor": tenor,
                "target_pop": TARGET_POP,
                "status": "unavailable",
                "reason": "Need spot, expected move, and chain rows",
            }
        ]

    lot = LOT_SIZE.get(symbol.upper(), 1)
    put_leg = find_short_strike_for_pop(df, spot, em, "put", TARGET_POP)
    call_leg = find_short_strike_for_pop(df, spot, em, "call", TARGET_POP)
    bias = bias_from_pcr_maxpain(pcr.get("pcr_oi"), max_pain, spot)
    pcr_oi = pcr.get("pcr_oi")

    def credit_est(short_ltp, long_row_ltp) -> Optional[float]:
        if short_ltp is None:
            return None
        if long_row_ltp is None:
            return float(short_ltp) * 0.35  # rough if long missing
        return max(0.05, float(short_ltp) - float(long_row_ltp))

    # Bull put credit spread — favored when PCR elevated / not call-heavy crash setup
    if put_leg:
        long_strike = put_leg["long_strike"]
        long_row = df.loc[(df["strike"] - long_strike).abs().idxmin()]
        credit = credit_est(put_leg.get("ltp"), long_row.get("pe_ltp"))
        width = abs(put_leg["strike"] - float(long_row["strike"]))
        if credit is not None:
            credit = max(0.0, min(credit, width))
        max_loss = (width - credit) * lot if credit is not None else None
        max_profit = credit * lot if credit is not None else None
        conf = min(95, 55 + (put_leg["approx_pop"] - 0.7) * 100)
        if pcr_oi and pcr_oi >= 1.0:
            conf += 5
        recs.append(
            {
                "strategy": "Bull Put Credit Spread",
                "tenor": tenor,
                "direction_bias": "Mildly bullish / neutral-bullish",
                "legs": (
                    f"SELL PE {put_leg['strike']} / BUY PE {float(long_row['strike']):.0f}"
                ),
                "approx_pop": put_leg["approx_pop"],
                "target_pop": TARGET_POP,
                "meets_80pct_target": put_leg["approx_pop"] >= TARGET_POP,
                "approx_delta_short": put_leg["approx_delta"],
                "est_credit_pts": round(credit, 2) if credit is not None else None,
                "est_max_profit_inr": round(max_profit, 0) if max_profit is not None else None,
                "est_max_loss_inr": round(max_loss, 0) if max_loss is not None else None,
                "lot_size": lot,
                "confidence_pct": round(min(95, conf), 1),
                "why": (
                    f"Short put ~{put_leg['distance_pct']}% below spot (~{put_leg['approx_delta']:.2f} abs-delta). "
                    f"Model POP {put_leg['approx_pop']*100:.0f}% vs {TARGET_POP*100:.0f}% target. Bias: {bias}."
                ),
                "risks": [
                    "Gap risk through short strike",
                    "IV crush helps shorts but IV expansion hurts",
                    "Model POP ≠ realized win rate",
                ],
                "management": "Take profit ~50–60% of credit; exit if spot closes below short strike.",
            }
        )

    # Bear call credit spread — favored when PCR low / call walls
    if call_leg:
        long_strike = call_leg["long_strike"]
        long_row = df.loc[(df["strike"] - long_strike).abs().idxmin()]
        credit = credit_est(call_leg.get("ltp"), long_row.get("ce_ltp"))
        width = abs(float(long_row["strike"]) - call_leg["strike"])
        if credit is not None:
            credit = max(0.0, min(credit, width))
        max_loss = (width - credit) * lot if credit is not None else None
        max_profit = credit * lot if credit is not None else None
        conf = min(95, 55 + (call_leg["approx_pop"] - 0.7) * 100)
        if pcr_oi and pcr_oi <= 0.85:
            conf += 5
        recs.append(
            {
                "strategy": "Bear Call Credit Spread",
                "tenor": tenor,
                "direction_bias": "Mildly bearish / neutral-bearish",
                "legs": (
                    f"SELL CE {call_leg['strike']} / BUY CE {float(long_row['strike']):.0f}"
                ),
                "approx_pop": call_leg["approx_pop"],
                "target_pop": TARGET_POP,
                "meets_80pct_target": call_leg["approx_pop"] >= TARGET_POP,
                "approx_delta_short": call_leg["approx_delta"],
                "est_credit_pts": round(credit, 2) if credit is not None else None,
                "est_max_profit_inr": round(max_profit, 0) if max_profit is not None else None,
                "est_max_loss_inr": round(max_loss, 0) if max_loss is not None else None,
                "lot_size": lot,
                "confidence_pct": round(min(95, conf), 1),
                "why": (
                    f"Short call ~{call_leg['distance_pct']}% above spot. "
                    f"Model POP {call_leg['approx_pop']*100:.0f}%. Bias: {bias}."
                ),
                "risks": [
                    "Short-covering squeeze through call wall",
                    "Event/gap risk",
                    "Model POP ≠ realized win rate",
                ],
                "management": "Take profit ~50–60% of credit; exit if spot closes above short strike.",
            }
        )

    # Iron condor — both wings ~80% each side ⇒ joint POP lower; disclose clearly
    if put_leg and call_leg:
        joint = put_leg["approx_pop"] * call_leg["approx_pop"]
        # For "80% overall" iron condor, widen to higher single-side POP (~0.90) if possible
        wide_put = find_short_strike_for_pop(df, spot, em, "put", 0.90)
        wide_call = find_short_strike_for_pop(df, spot, em, "call", 0.90)
        if wide_put and wide_call:
            joint90 = wide_put["approx_pop"] * wide_call["approx_pop"]
            # Iron condor P&L: total credit = put credit + call credit;
            # max loss = the wider net-risk wing (only one side is ITM at expiry).
            lp_row = df.loc[(df["strike"] - wide_put["long_strike"]).abs().idxmin()]
            lc_row = df.loc[(df["strike"] - wide_call["long_strike"]).abs().idxmin()]
            put_credit = credit_est(wide_put.get("ltp"), lp_row.get("pe_ltp"))
            call_credit = credit_est(wide_call.get("ltp"), lc_row.get("ce_ltp"))
            put_width = abs(float(lp_row["strike"]) - wide_put["strike"])
            call_width = abs(float(lc_row["strike"]) - wide_call["strike"])
            if put_credit is not None:
                put_credit = max(0.0, min(put_credit, put_width))
            if call_credit is not None:
                call_credit = max(0.0, min(call_credit, call_width))
            total_credit = (
                (put_credit + call_credit)
                if put_credit is not None and call_credit is not None
                else None
            )
            if total_credit is not None:
                max_profit = total_credit * lot
                put_risk = max(0.0, put_width - put_credit)
                call_risk = max(0.0, call_width - call_credit)
                max_loss = max(put_risk, call_risk) * lot
            else:
                max_profit = None
                max_loss = None
            recs.append(
                {
                    "strategy": "Iron Condor (wide, ~80% joint POP target)",
                    "tenor": tenor,
                    "direction_bias": "Neutral / range-bound",
                    "legs": (
                        f"SELL PE {wide_put['strike']} / BUY PE {wide_put['long_strike']} + "
                        f"SELL CE {wide_call['strike']} / BUY CE {wide_call['long_strike']}"
                    ),
                    "approx_pop": round(joint90, 3),
                    "target_pop": TARGET_POP,
                    "meets_80pct_target": joint90 >= TARGET_POP,
                    "approx_delta_short": {
                        "put": wide_put["approx_delta"],
                        "call": wide_call["approx_delta"],
                    },
                    "est_credit_pts": round(total_credit, 2) if total_credit is not None else None,
                    "est_max_profit_inr": round(max_profit, 0) if max_profit is not None else None,
                    "est_max_loss_inr": round(max_loss, 0) if max_loss is not None else None,
                    "lot_size": lot,
                    "confidence_pct": round(min(92, 50 + joint90 * 40), 1),
                    "why": (
                        f"Both wings placed for ~90% single-side POP so joint model POP "
                        f"≈ {joint90*100:.0f}% (product of independent tails — approximate). "
                        f"1SD expected move {em:.0f} pts. Bias: {bias}."
                    ),
                    "risks": [
                        "Correlated tail moves invalidate independence assumption",
                        "Lower credit than tighter condor",
                        "Pin risk / gamma near expiry",
                    ],
                    "management": "Exit at 40–50% of total credit or if one wing is tested.",
                    "note": (
                        f"Tighter 80%-per-wing condor would only have joint POP ≈ {joint*100:.0f}%, "
                        "so wide wings are used when targeting ~80% overall."
                    ),
                }
            )

    # Rank: prefer those meeting 80% target, then confidence
    recs.sort(
        key=lambda r: (
            1 if r.get("meets_80pct_target") else 0,
            r.get("approx_pop") or 0,
            r.get("confidence_pct") or 0,
        ),
        reverse=True,
    )
    # Add disclaimer block on each
    for r in recs:
        r["disclaimer"] = (
            "approx_pop is a theoretical probability of profit from distance vs IV-implied "
            "expected move (normal approx). It is NOT a historical backtested win rate and "
            "does not guarantee 80% wins."
        )
    return recs


def analyze_expiry_chain(
    symbol: str,
    tenor: str,
    expiry: str,
    raw: Dict[str, Any],
) -> Dict[str, Any]:
    df, meta = chain_to_frame(raw, expiry=expiry)
    if df is None or meta.get("status") != "ok":
        return {
            "symbol": symbol,
            "tenor": tenor,
            "expiry": expiry,
            "status": "unavailable",
            "reason": meta.get("reason", "chain parse failed"),
        }

    spot = meta.get("underlying")
    if spot is None:
        return {
            "symbol": symbol,
            "tenor": tenor,
            "expiry": expiry,
            "status": "unavailable",
            "reason": "Underlying spot missing from option-chain payload",
            "source": meta.get("source"),
        }
    spot = float(spot)
    pcr = compute_pcr(df)
    mp = compute_max_pain(df)
    atm = atm_iv(df, spot)
    dte = dte_days(expiry)
    em = expected_move(spot, atm.get("atm_iv"), dte if dte is not None else 7)
    buildups = detect_buildups(df, spot)
    strategies = recommend_strategies(
        symbol, tenor, spot, em, pcr, mp, df, atm
    )

    # Compact strike table around ATM (±10 strikes)
    step = strike_step(df)
    band = df[(df["strike"] >= spot - 10 * step) & (df["strike"] <= spot + 10 * step)]
    table = band[
        [
            "strike",
            "ce_oi",
            "ce_chg_oi",
            "ce_iv",
            "ce_ltp",
            "pe_ltp",
            "pe_iv",
            "pe_chg_oi",
            "pe_oi",
        ]
    ].to_dict("records")

    return {
        "symbol": symbol,
        "tenor": tenor,
        "expiry": expiry,
        "status": "ok",
        "spot": spot,
        "dte": dte,
        "pcr_oi": pcr.get("pcr_oi"),
        "pcr_volume": pcr.get("pcr_volume"),
        "max_pain": mp,
        "atm": atm,
        "expected_move_1sd": round(em, 2) if em else None,
        "expected_move_pct": round(em / spot * 100, 2) if em and spot else None,
        "buildups": buildups,
        "bias": bias_from_pcr_maxpain(pcr.get("pcr_oi"), mp, spot),
        "strategies": strategies,
        "chain_slice": table,
        "timestamp": meta.get("timestamp"),
        "source": meta.get("source"),
        "fetched_at": meta.get("fetched_at"),
    }


def analyze_symbol_options(symbol: str, session=None) -> Dict[str, Any]:
    sym = symbol.replace(".NS", "").upper().strip()
    from src.data.nse_option_chain import fetch_contract_info

    info = fetch_contract_info(sym, session=session)
    if info.get("status") != "ok":
        return {
            "symbol": sym,
            "status": "unavailable",
            "reason": info.get("reason"),
            "source": info.get("source"),
            "weekly": None,
            "monthly": None,
        }

    classes = classify_expiries(info.get("expiryDates") or [])
    weekly_exp = classes.get("weekly")
    monthly_exp = classes.get("monthly")

    weekly = None
    monthly = None
    if weekly_exp:
        raw_w = fetch_option_chain_raw(sym, expiry=weekly_exp, session=session)
        weekly = analyze_expiry_chain(sym, "weekly", weekly_exp, raw_w)
    if monthly_exp and monthly_exp == weekly_exp:
        monthly = dict(weekly or {})
        if monthly:
            monthly["tenor"] = "monthly"
            monthly["note"] = "Nearest expiry is also the monthly expiry"
    elif monthly_exp:
        import time

        time.sleep(0.6)
        raw_m = fetch_option_chain_raw(sym, expiry=monthly_exp, session=session)
        monthly = analyze_expiry_chain(sym, "monthly", monthly_exp, raw_m)

    top = []
    for block in (weekly, monthly):
        if not block or block.get("status") != "ok":
            continue
        for s in block.get("strategies") or []:
            if s.get("strategy") == "Unavailable":
                continue
            item = dict(s)
            item["symbol"] = sym
            item["expiry"] = block.get("expiry")
            top.append(item)
    top.sort(
        key=lambda r: (
            1 if r.get("meets_80pct_target") else 0,
            r.get("approx_pop") or 0,
            r.get("confidence_pct") or 0,
        ),
        reverse=True,
    )

    return {
        "symbol": sym,
        "status": "ok",
        "is_index": sym in INDEX_SYMBOLS,
        "expiry_classes": classes,
        "weekly": weekly,
        "monthly": monthly,
        "top_strategies": top[:6],
        "source_page": "https://www.nseindia.com/option-chain",
        "disclaimer": (
            "Data from nselib/nsepython (NSE option chain). Strategy POP is theoretical "
            f"(target {int(TARGET_POP*100)}%), not a promised win rate."
        ),
    }


def analyze_options(watchlist: List[str]) -> Dict[str, Any]:
    """Analyze index underlyings for weekly + monthly; equities best-effort."""
    # Always ensure NIFTY + BANKNIFTY for weekly/monthly core; skip equities by default
    # (equity option-chain-v3 type differs and rate-limits easily)
    symbols = []
    for must in ("NIFTY", "BANKNIFTY"):
        symbols.append(must)
    for s in watchlist or []:
        u = s.replace(".NS", "").upper()
        if u in INDEX_SYMBOLS and u not in symbols:
            symbols.append(u)
    # optional FINNIFTY if listed
    symbols = symbols[:3]

    from src.data.nse_option_chain import _session
    import time

    sess = _session()
    per_symbol = []
    warnings = []
    try:
        for i, sym in enumerate(symbols):
            if i:
                time.sleep(0.8)  # be polite to NSE
            result = analyze_symbol_options(sym, session=sess)
            per_symbol.append(result)
            if result.get("status") != "ok":
                warnings.append(f"{sym}: {result.get('reason')}")
    finally:
        try:
            sess.close()
        except Exception:
            pass

    ok = [s for s in per_symbol if s.get("status") == "ok"]
    # Flatten top strategies meeting 80%
    recommendations = []
    for s in ok:
        for strat in s.get("top_strategies") or []:
            recommendations.append(strat)
    recommendations.sort(
        key=lambda r: (
            1 if r.get("meets_80pct_target") else 0,
            r.get("approx_pop") or 0,
            r.get("confidence_pct") or 0,
        ),
        reverse=True,
    )

    return {
        "status": "ok" if ok else "unavailable",
        "reason": None if ok else (warnings[0] if warnings else "NSE option chain unavailable"),
        "symbols": per_symbol,
        "recommendations": recommendations[:12],
        "target_pop": TARGET_POP,
        "source_page": "https://www.nseindia.com/option-chain",
        "note": (
            "Weekly = nearest expiry; Monthly = last listed expiry of the month. "
            f"Strategies aim for ~{int(TARGET_POP*100)}% theoretical POP via OTM credit structures. "
            "This is model probability, not a guaranteed historical win rate."
        ),
        "warnings": warnings,
        "long_short_buildup": {"see": "per-symbol buildups"},
        "short_covering": {"status": "partial", "note": "Inferred weakly from OI change; confirm on chart"},
        "long_unwinding": {"status": "partial", "note": "Inferred weakly from OI change; confirm on chart"},
    }
