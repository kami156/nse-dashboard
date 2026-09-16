"""Technical analysis engine and Technical Score (0-100)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _macd(series: pd.Series) -> Dict[str, pd.Series]:
    ema12 = _ema(series, 12)
    ema26 = _ema(series, 26)
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    hist = line - signal
    return {"macd": line, "signal": signal, "hist": hist}


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low = df["High"], df["Low"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr = _atr(df, period)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.rolling(period).mean()


def _bollinger(series: pd.Series, period: int = 20) -> Dict[str, pd.Series]:
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    return {"mid": mid, "upper": mid + 2 * std, "lower": mid - 2 * std}


def _supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    atr = _atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    st = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(True, index=df.index)
    for i in range(len(df)):
        if i == 0:
            st.iloc[i] = upper.iloc[i]
            continue
        if df["Close"].iloc[i] > st.iloc[i - 1]:
            direction.iloc[i] = True
        elif df["Close"].iloc[i] < st.iloc[i - 1]:
            direction.iloc[i] = False
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        st.iloc[i] = lower.iloc[i] if direction.iloc[i] else upper.iloc[i]
    return st


def _pivots(df: pd.DataFrame) -> Dict[str, float]:
    prev = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
    h, l, c = float(prev["High"]), float(prev["Low"]), float(prev["Close"])
    pp = (h + l + c) / 3
    return {
        "pivot": pp,
        "r1": 2 * pp - l,
        "s1": 2 * pp - h,
        "r2": pp + (h - l),
        "s2": pp - (h - l),
    }


def analyze_technical(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty or len(df) < 30:
        return {
            "status": "unavailable",
            "reason": "Insufficient price history for technical analysis",
            "technical_score": None,
        }

    close = df["Close"]
    rsi = _rsi(close)
    macd = _macd(close)
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    ema100 = _ema(close, 100)
    ema200 = _ema(close, 200) if len(df) >= 200 else pd.Series(np.nan, index=df.index)
    atr = _atr(df)
    adx = _adx(df)
    bb = _bollinger(close)
    try:
        st = _supertrend(df)
        st_val = float(st.iloc[-1]) if not np.isnan(st.iloc[-1]) else None
    except Exception:
        st_val = None
    piv = _pivots(df)

    last = float(close.iloc[-1])
    rsi_v = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    macd_hist = float(macd["hist"].iloc[-1]) if not np.isnan(macd["hist"].iloc[-1]) else 0.0
    adx_v = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 20.0
    atr_v = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else None

    # Volume profile proxy: recent vs 20d avg
    vol_ratio = None
    if "Volume" in df.columns and df["Volume"].iloc[-20:].mean() > 0:
        vol_ratio = float(df["Volume"].iloc[-1] / df["Volume"].iloc[-20:].mean())

    # VWAP proxy: 20-session rolling volume-weighted typical price (no intraday session data)
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    _vol = df.get("Volume", pd.Series(1, index=df.index)).replace(0, np.nan)
    vwap = (typical * _vol).rolling(20).sum() / _vol.rolling(20).sum()
    vwap_v = float(vwap.iloc[-1]) if not np.isnan(vwap.iloc[-1]) else None

    # Momentum: 1w / 1m / 3m returns
    ret_5 = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) > 6 else 0.0
    ret_20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else ret_5
    ret_60 = float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) > 61 else ret_20

    # Trend structure
    trend = "Sideways"
    if last > float(ema50.iloc[-1]) > float(ema100.iloc[-1] if not np.isnan(ema100.iloc[-1]) else ema50.iloc[-1]):
        trend = "Uptrend"
    elif last < float(ema50.iloc[-1]) < float(ema100.iloc[-1] if not np.isnan(ema100.iloc[-1]) else ema50.iloc[-1]):
        trend = "Downtrend"

    # Support / resistance from recent swings + pivots
    look = df.tail(60)
    support = float(min(look["Low"].min(), piv["s1"]))
    resistance = float(max(look["High"].max(), piv["r1"]))

    # Relative strength vs own 50dma slope
    rs = 50 + ret_20 * 100
    rs = float(np.clip(rs, 0, 100))

    # Technical score 0-100
    score = 50.0
    score += 10 if last > float(ema20.iloc[-1]) else -8
    score += 10 if last > float(ema50.iloc[-1]) else -8
    if not np.isnan(ema200.iloc[-1]):
        score += 8 if last > float(ema200.iloc[-1]) else -8
    score += 8 if macd_hist > 0 else -8
    if 45 <= rsi_v <= 65:
        score += 6
    elif rsi_v > 70:
        score -= 4
    elif rsi_v < 30:
        score += 4  # oversold bounce potential
    score += min(10, max(-5, (adx_v - 20) / 2))
    score += min(8, max(-8, ret_20 * 40))
    if vol_ratio and vol_ratio > 1.3 and ret_20 > 0:
        score += 4
    score = float(np.clip(score, 0, 100))

    momentum_label = "Strong" if ret_20 > 0.05 else "Positive" if ret_20 > 0 else "Weak" if ret_20 > -0.05 else "Negative"

    return {
        "status": "ok",
        "last": last,
        "trend": trend,
        "momentum": momentum_label,
        "momentum_1w_pct": round(ret_5 * 100, 2),
        "momentum_1m_pct": round(ret_20 * 100, 2),
        "momentum_3m_pct": round(ret_60 * 100, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "relative_strength": round(rs, 1),
        "volume_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
        "rsi": round(rsi_v, 2),
        "macd_hist": round(macd_hist, 4),
        "ema20": round(float(ema20.iloc[-1]), 2),
        "ema50": round(float(ema50.iloc[-1]), 2),
        "ema100": round(float(ema100.iloc[-1]), 2) if not np.isnan(ema100.iloc[-1]) else None,
        "ema200": round(float(ema200.iloc[-1]), 2) if not np.isnan(ema200.iloc[-1]) else None,
        "vwap": round(vwap_v, 2) if vwap_v is not None else None,
        "supertrend": round(st_val, 2) if st_val is not None else None,
        "adx": round(adx_v, 2),
        "atr": round(atr_v, 2) if atr_v is not None else None,
        "bollinger_upper": round(float(bb["upper"].iloc[-1]), 2) if not np.isnan(bb["upper"].iloc[-1]) else None,
        "bollinger_lower": round(float(bb["lower"].iloc[-1]), 2) if not np.isnan(bb["lower"].iloc[-1]) else None,
        "pivots": {k: round(v, 2) for k, v in piv.items()},
        "trend_strength": "Strong" if adx_v >= 25 else "Moderate" if adx_v >= 18 else "Weak",
        "technical_score": round(score, 1),
        "ai_summary": (
            f"{trend} with {momentum_label.lower()} momentum; RSI {rsi_v:.0f}, ADX {adx_v:.0f}. "
            f"Support near {support:.0f}, resistance near {resistance:.0f}."
        ),
    }


def technical_score_only(df: Optional[pd.DataFrame]) -> Optional[float]:
    result = analyze_technical(df) if df is not None else {"technical_score": None}
    return result.get("technical_score")
