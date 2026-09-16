"""Snapshot storage and hourly change detection."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SnapshotStore:
    # Retention: keep the most recent MAX_ARCHIVES snapshot files, and drop
    # anything older than MAX_AGE_DAYS regardless of count. Without this,
    # an hourly cron accumulates one file per run forever (output/snapshots/
    # already had 40+ archives from a few days of testing).
    MAX_ARCHIVES = 200
    MAX_AGE_DAYS = 14

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.directory / "latest.json"

    def load_previous(self) -> Optional[Dict[str, Any]]:
        if not self.latest_path.exists():
            return None
        try:
            return json.loads(self.latest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, snapshot: Dict[str, Any]) -> Path:
        snapshot = dict(snapshot)
        snapshot["saved_at"] = _utcnow()
        # Archive
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive = self.directory / f"snap_{stamp}.json"
        text = json.dumps(snapshot, indent=2, default=str)
        archive.write_text(text, encoding="utf-8")
        self.latest_path.write_text(text, encoding="utf-8")
        self._prune()
        return archive

    def _prune(self) -> None:
        """Delete old archive snapshots beyond the retention window."""
        try:
            archives = sorted(
                self.directory.glob("snap_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            return

        now = datetime.now(timezone.utc).timestamp()
        max_age_secs = self.MAX_AGE_DAYS * 86400
        for i, path in enumerate(archives):
            too_old = (now - path.stat().st_mtime) > max_age_secs
            over_count = i >= self.MAX_ARCHIVES
            if too_old or over_count:
                try:
                    path.unlink()
                except Exception:
                    pass


def detect_changes(current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not previous:
        return {
            "status": "first_run",
            "summary": "No previous hourly snapshot — change detection starts on next run.",
            "items": [],
        }

    items: List[Dict[str, Any]] = []

    # Index trend / leadership changes
    cur_idx = current.get("indices", {})
    prev_idx = previous.get("indices", {})
    for name, cur in cur_idx.items():
        prev = prev_idx.get(name, {})
        if cur.get("status") != "ok" or prev.get("status") != "ok":
            continue
        c, p = cur.get("change_pct"), prev.get("change_pct")
        if c is None or p is None:
            continue
        if abs(c - p) >= 0.5:
            items.append(
                {
                    "type": "index_move",
                    "label": name,
                    "detail": f"Day change moved from {p:+.2f}% to {c:+.2f}%",
                    "meaningful": abs(c - p) >= 1.0,
                }
            )

    # Sector leadership
    cur_sec = (current.get("sector_rotation") or {}).get("ranked") or []
    prev_sec = (previous.get("sector_rotation") or {}).get("ranked") or []
    if cur_sec and prev_sec:
        cur_leader = cur_sec[0].get("sector")
        prev_leader = prev_sec[0].get("sector")
        if cur_leader and prev_leader and cur_leader != prev_leader:
            items.append(
                {
                    "type": "sector_leadership",
                    "label": "Sector leadership change",
                    "detail": f"Leader changed from {prev_leader} to {cur_leader}",
                    "meaningful": True,
                }
            )

    # Watchlist conviction / rating changes
    def _cards(snap: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out = {}
        for wl in (snap.get("watchlists") or {}).values():
            for card in wl:
                out[card["symbol"]] = card
        return out

    cur_cards = _cards(current)
    prev_cards = _cards(previous)
    for sym, card in cur_cards.items():
        prev = prev_cards.get(sym)
        if not prev:
            items.append(
                {
                    "type": "new_watchlist_name",
                    "label": sym,
                    "detail": "Newly appearing on analyzed watchlists",
                    "meaningful": True,
                }
            )
            continue
        if card.get("rating") != prev.get("rating"):
            items.append(
                {
                    "type": "rating_change",
                    "label": sym,
                    "detail": f"Rating {prev.get('rating')} → {card.get('rating')}",
                    "meaningful": True,
                }
            )
        co, po = card.get("overall_conviction"), prev.get("overall_conviction")
        if co is not None and po is not None and abs(co - po) >= 8:
            items.append(
                {
                    "type": "conviction_change",
                    "label": sym,
                    "detail": f"Conviction {po:.0f} → {co:.0f}",
                    "meaningful": abs(co - po) >= 12,
                }
            )

    # Opportunities: new breakouts
    cur_ops = {o["symbol"]: o for o in current.get("opportunities", [])}
    prev_ops = {o["symbol"]: o for o in previous.get("opportunities", [])}
    for sym, op in cur_ops.items():
        if sym not in prev_ops:
            items.append(
                {
                    "type": "new_breakout_or_opportunity",
                    "label": sym,
                    "detail": f"New opportunity: {op.get('category')} — {op.get('reason')}",
                    "meaningful": True,
                }
            )

    # Volume spikes from breadth leaders
    for v in (current.get("breadth") or {}).get("volume_leaders", [])[:5]:
        if (v.get("volume_ratio") or 0) >= 2.0:
            items.append(
                {
                    "type": "volume_spike",
                    "label": v["symbol"],
                    "detail": f"Volume ratio {v['volume_ratio']}x with {v['change_pct']:+.2f}%",
                    "meaningful": True,
                }
            )

    # Regime change
    cur_reg = (current.get("regime") or {}).get("market_regime")
    prev_reg = (previous.get("regime") or {}).get("market_regime")
    if cur_reg and prev_reg and cur_reg != prev_reg:
        items.append(
            {
                "type": "trend_regime",
                "label": "Market regime",
                "detail": f"{prev_reg} → {cur_reg}",
                "meaningful": True,
            }
        )

    meaningful = [i for i in items if i.get("meaningful")]
    return {
        "status": "ok",
        "previous_saved_at": previous.get("saved_at") or previous.get("generated_at"),
        "summary": (
            f"{len(meaningful)} meaningful changes vs prior snapshot "
            f"({previous.get('saved_at') or previous.get('generated_at') or 'unknown'})."
            if meaningful
            else "No material changes vs prior hourly snapshot."
        ),
        "items": meaningful[:40] if meaningful else items[:20],
        "all_count": len(items),
    }
