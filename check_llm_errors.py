#!/usr/bin/env python3
"""Utility to inspect competition logs and report the last error count for each LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Dict, Iterable, List, Set

NAME_REGEX = re.compile(r"NAME:\s*(?P<llm>[^,\n]+)")
ERROR_REGEX = re.compile(
    r"Try\s+(?P<count>\d+)\s+Error generating response with\s+(?P<llm>\S+)"
)

# Update these lists when you prefer to hardcode defaults instead of supplying CLI flags.
PRESET_FOLDERS: List[str] = [
    # Example: "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_163853",
    # "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_121702",
    # "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_163853",
    # "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_163919",
    # "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_163953",
    # "run_5000_8llm_problems_contest3_credits_limit_40M_20251119_164020",
    # "run_5000_p11_problems_contest3_competition_main_20251119_121709",
    # "run_5000_p12_problems_contest3_competition_main_20251119_121711",
    # "run_5000_p21_problems_contest3_competition_main_20251119_121733",
    # "run_5000_p22_problems_contest3_competition_main_20251119_121735"
    "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_185309",
    "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_190208",
    "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_190210",
    "run_5000_8llm_problems_contest3_credits_limit_10M_20251119_190212",
    "run_5000_8llm_problems_contest3_credits_limit_40M_20251119_190214",
    "run_5000_p11_problems_contest3_competition_main_20251119_190159",
    "run_5000_p12_problems_contest3_competition_main_20251119_190203",
    "run_5000_p21_problems_contest3_competition_main_20251119_190205",
    "run_5000_p22_problems_contest3_competition_main_20251119_190206"

]
PRESET_LLMS: List[str] = [
    # Example: "claude-sonnet-4-20250514",
     "claude-sonnet-4-20250514",
     "deepseek-v3",
     "deepseek-v3.1",
     "gemini-2.5-pro",
     "glm-4.5",
     "gpt-5-codex",
     "kimi-k2-0905",
     "qwen3-235b"
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reverse-search competition logs and report the last observed error count "
            "for each requested LLM."
        )
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("logs/run_logs"),
        help="Base directory containing competition run folders (default: logs/run_logs)",
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        help=(
            "Relative folder names (inside base-dir) that should be scanned. "
            "If omitted, the PRESET_FOLDERS list at the top of the script is used."
        ),
    )
    parser.add_argument(
        "--llms",
        nargs="+",
        help=(
            "LLM names to search for (exact match). "
            "If omitted, the PRESET_LLMS list at the top of the script is used."
        ),
    )
    return parser.parse_args()


def discover_log_files(folder: Path) -> List[Path]:
    """Return candidate log files inside the folder sorted by mtime descending."""
    direct_logs = sorted(folder.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if direct_logs:
        return direct_logs
    # Fall back to a recursive search if the shallow scan comes up empty.
    deep_logs = sorted(folder.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return deep_logs


def scan_log_for_llms(log_path: Path, pending_llms: Iterable[str]) -> Dict[str, int]:
    """Scan a single log file from bottom to top for the provided LLMs."""
    pending: Set[str] = set(pending_llms)
    if not pending:
        return {}

    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return {}

    found: Dict[str, int] = {}
    for line in reversed(lines):
        if not pending:
            break

        if "Error generating response with" in line:
            error_match = ERROR_REGEX.search(line)
            if error_match:
                llm = error_match.group("llm")
                if llm in pending:
                    found[llm] = int(error_match.group("count"))
                    pending.remove(llm)
                    continue

        if "NAME:" in line:
            name_match = NAME_REGEX.search(line)
            if name_match:
                llm_name = name_match.group("llm").strip()
                if llm_name in pending:
                    found[llm_name] = 0
                    pending.remove(llm_name)

    return found


def summarize_folder(folder: Path, llms: List[str]) -> Dict[str, int | None]:
    """Return the last observed error count per LLM for a single folder."""
    log_files = discover_log_files(folder)
    results: Dict[str, int | None] = {llm: None for llm in llms}

    if not log_files:
        return results

    for log_path in log_files:
        remaining = [llm for llm, value in results.items() if value is None]
        if not remaining:
            break
        latest_hits = scan_log_for_llms(log_path, remaining)
        for llm, count in latest_hits.items():
            results[llm] = count

    return results


def format_result(value: int | None) -> str:
    if value is None:
        return "not found"
    if value == 0:
        return "0 error (latest record is NAME)"
    return f"{value} error(s)"


def main() -> None:
    args = parse_args()
    base_dir: Path = args.base_dir
    folders = args.folders if args.folders else PRESET_FOLDERS
    llms = args.llms if args.llms else PRESET_LLMS
    if not folders:
        raise SystemExit("No folders supplied (CLI flag or PRESET_FOLDERS).")
    if not llms:
        raise SystemExit("No LLMs supplied (CLI flag or PRESET_LLMS).")

    for folder_name in folders:
        folder_path = base_dir / folder_name
        print(f"\n=== {folder_name} ===")
        if not folder_path.exists():
            print("  Folder missing, skip.")
            continue

        llm_status = summarize_folder(folder_path, llms)
        for llm in llms:
            print(f"  {llm}: {format_result(llm_status[llm])}")


if __name__ == "__main__":
    main()
