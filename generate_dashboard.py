#!/usr/bin/env python3
"""CLI entry: generate the NSE institutional HTML dashboard.

The three original flags keep their exact behaviour, so the scheduled task and any
existing muscle memory still work. Added:

  --check   validate the environment and exit without fetching (fails fast on an
            hourly job instead of after a three-minute fetch)
  --out     also write the generated HTML to another path

The renderer is still chosen in one place, src/pipeline.py, so this CLI and the
Streamlit launcher can never disagree about which one is active. The summary
reports which renderer actually ran and whether the closing lists are still
disjoint, so both recent fixes are visible on every run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DELIVERABLE_LISTS = ("top_conviction", "top_swing", "top_long_term")


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2


def preflight() -> int:
    """Validate the repo without fetching anything. 0 when ready to run."""
    problems: list[str] = []
    print(f"repo root : {ROOT}")

    for rel in ("config/watchlists.yaml", "src/pipeline.py", "generate_dashboard.py"):
        if not (ROOT / rel).exists():
            problems.append(f"missing {rel} - run this from the repo root")

    pipeline = None
    try:
        import src.pipeline as pipeline  # noqa: PLC0415
    except Exception as exc:  # import-time failure is exactly what --check is for
        problems.append(f"cannot import src.pipeline: {exc}")

    renderer = "unknown"
    if pipeline is not None:
        render_fn = getattr(pipeline, "render_html", None)
        renderer = getattr(render_fn, "__module__", "unknown")
        code = getattr(render_fn, "__code__", None)
        if code is not None:
            module_dir = Path(code.co_filename).resolve().parent
            for side in ("styles.css", "app.js"):
                if not (module_dir / side).exists():
                    problems.append(f"{renderer} needs {side} next to {module_dir}")
    print(f"renderer  : {renderer}")

    for problem in problems:
        print(f"  problem : {problem}")
    if problems:
        print("preflight: NOT READY")
        return 2
    print("preflight: ready")
    return 0


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
    parser.add_argument("--out", type=Path, default=None,
                        help="Also write the generated HTML to this path")
    parser.add_argument("--check", action="store_true",
                        help="Validate the environment and exit without fetching")
    args = parser.parse_args()

    if args.check:
        return preflight()

    if not args.watchlists.exists():
        return _fail(f"watchlists file not found: {args.watchlists}")

    from src.pipeline import generate_dashboard, render_html

    print("Generating dashboard…")
    payload = generate_dashboard(
        project_root=ROOT,
        watchlists_path=args.watchlists,
        force_refresh=args.force_refresh,
        skip_news=args.skip_news,
    )

    html_path = Path(payload.get("html_path") or (ROOT / "output" / "dashboard.html"))
    print(f"Wrote: {html_path}")
    if args.out and args.out.resolve() != html_path.resolve():
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Also wrote: {args.out}")

    print(f"Renderer: {getattr(render_html, '__module__', 'unknown')}")
    print(f"Timestamp: {payload.get('generated_at')}")
    print(f"Warnings: {len(payload.get('warnings') or [])}")
    print(f"Opportunities: {len(payload.get('opportunities') or [])}")

    lists = payload.get("executive_lists") or {}
    rows = [c.get("symbol") for key in DELIVERABLE_LISTS for c in (lists.get(key) or [])]
    if rows:
        distinct = len(set(rows))
        counts = ", ".join(f"{key.replace('top_', '')} {len(lists.get(key) or [])}"
                           for key in DELIVERABLE_LISTS)
        flag = "" if distinct == len(rows) else f"  <-- {len(rows) - distinct} row(s) repeat"
        print(f"Closing lists: {counts} ({distinct} distinct of {len(rows)} rows){flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
