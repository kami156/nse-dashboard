#!/usr/bin/env python3
"""CLI entry: generate the NSE institutional HTML dashboard."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import generate_dashboard


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate NSE Institutional Dashboard HTML")
    parser.add_argument(
        "--watchlists",
        type=Path,
        default=ROOT / "config" / "watchlists.yaml",
        help="Path to watchlists YAML",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Bypass fetch cache")
    parser.add_argument("--skip-news", action="store_true", help="Skip Google News RSS fetch")
    args = parser.parse_args()

    print("Generating dashboard…")
    payload = generate_dashboard(
        project_root=ROOT,
        watchlists_path=args.watchlists,
        force_refresh=args.force_refresh,
        skip_news=args.skip_news,
    )
    print(f"Wrote: {payload.get('html_path')}")
    print(f"Timestamp: {payload.get('generated_at')}")
    print(f"Warnings: {len(payload.get('warnings') or [])}")
    print(f"Opportunities: {len(payload.get('opportunities') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
