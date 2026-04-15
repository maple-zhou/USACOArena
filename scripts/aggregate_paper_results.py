#!/usr/bin/env python3
"""Aggregate repeated paper runs into publication-ready summary tables."""

from __future__ import annotations

import argparse
from pathlib import Path

from usacoarena.benchmark.paper_aggregation import aggregate_paper_runs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate runs/paper/... outputs into Table 2 / Table 8 / Table 9 style summaries."
    )
    parser.add_argument(
        "--runs-root",
        default="runs/paper",
        help="Root directory containing the paper reproduction run layout.",
    )
    parser.add_argument(
        "--output-dir",
        default="runs/paper/aggregated",
        help="Directory where aggregated JSON/CSV/Markdown artifacts are written.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    runs_root = Path(args.runs_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = aggregate_paper_runs(runs_root, output_dir)
    print(f"runs_root={runs_root}")
    print(f"output_dir={output_dir}")
    print(f"manifest={manifest['manifest']}")
    warnings = manifest.get("warnings", [])
    print(f"warnings={len(warnings)}")
    for key, artifacts in manifest.get("generated_sections", {}).items():
        print(f"{key}={artifacts.get('markdown', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
