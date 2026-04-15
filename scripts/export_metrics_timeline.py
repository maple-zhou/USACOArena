#!/usr/bin/env python3
"""Poll USACOArena APIs and export competition metric snapshots over time."""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests


def _request_json(base_url: str, path: str, timeout: float) -> Dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected JSON payload for {path}: not an object")
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _flatten_participant_metrics(
    snapshot_at: str,
    competition_id: str,
    ranking_rows: Iterable[Dict[str, Any]],
    submissions_by_participant: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for entry in ranking_rows:
        participant_id = str(entry.get("participant_id") or entry.get("id") or "").strip()
        rows.append(
            {
                "snapshot_at": snapshot_at,
                "competition_id": competition_id,
                "participant_id": participant_id,
                "name": entry.get("name"),
                "rank": entry.get("rank"),
                "score": entry.get("score"),
                "problem_pass_score": entry.get("problem_pass_score"),
                "remaining_tokens": entry.get("remaining_tokens"),
                "consumed_tokens": entry.get("consumed_tokens"),
                "consumed_credit": entry.get("consumed_credit"),
                "submission_penalty": entry.get("submission_penalty"),
                "LLM_tokens": entry.get("LLM_tokens"),
                "hint_tokens": entry.get("hint_tokens"),
                "test_tokens": entry.get("test_tokens"),
                "submission_tokens": entry.get("submission_tokens"),
                "llm_inference_count": entry.get("llm_inference_count"),
                "submission_count": entry.get("submission_count"),
                "accepted_count": entry.get("accepted_count"),
                "elapsed_time_seconds": entry.get("elapsed_time_seconds"),
                "delivery_time_seconds": entry.get("delivery_time_seconds"),
                "delivery_time_credit": entry.get("delivery_time_credit"),
                "delivery_time_multiplier": entry.get("delivery_time_multiplier"),
                "is_running": entry.get("is_running"),
                "termination_reason": entry.get("termination_reason"),
                "solved_problem_count": len(entry.get("solved_problems") or []),
                "submission_event_count": len(submissions_by_participant.get(participant_id, [])),
            }
        )
    return rows


def _write_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _rewrite_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "snapshot_at",
        "competition_id",
        "participant_id",
        "name",
        "rank",
        "score",
        "problem_pass_score",
        "remaining_tokens",
        "consumed_tokens",
        "consumed_credit",
        "submission_penalty",
        "LLM_tokens",
        "hint_tokens",
        "test_tokens",
        "submission_tokens",
        "llm_inference_count",
        "submission_count",
        "accepted_count",
        "elapsed_time_seconds",
        "delivery_time_seconds",
        "delivery_time_credit",
        "delivery_time_multiplier",
        "is_running",
        "termination_reason",
        "solved_problem_count",
        "submission_event_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll USACOArena metrics endpoints and export a timeline."
    )
    parser.add_argument("--api-base", required=True, help="USACOArena API base URL")
    parser.add_argument("--competition-id", required=True, help="Competition ID")
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Stop after this many seconds; 0 means run until all participants terminate",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/timeline",
        help="Directory for JSONL/CSV snapshots",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve() / args.competition_id
    output_dir.mkdir(parents=True, exist_ok=True)

    timeline_jsonl = output_dir / "participant_metrics_timeline.jsonl"
    timeline_csv = output_dir / "participant_metrics_timeline.csv"
    rankings_jsonl = output_dir / "rankings_raw.jsonl"
    submissions_jsonl = output_dir / "submissions_raw.jsonl"
    intelligence_jsonl = output_dir / "intelligence_report_raw.jsonl"

    all_rows: List[Dict[str, Any]] = []
    started_at = time.time()

    while True:
        snapshot_at = _utc_now()
        rankings_payload = _request_json(
            args.api_base,
            f"/api/rankings/get/{args.competition_id}",
            args.timeout,
        )
        submissions_payload = _request_json(
            args.api_base,
            f"/api/submissions/list/{args.competition_id}",
            args.timeout,
        )
        intelligence_payload = _request_json(
            args.api_base,
            f"/api/metrics/intelligence/{args.competition_id}?format=json",
            args.timeout,
        )

        ranking_rows = rankings_payload.get("data") or []
        submission_rows = submissions_payload.get("data") or []
        intelligence_data = intelligence_payload.get("data") or {}

        submissions_by_participant: Dict[str, List[Dict[str, Any]]] = {}
        for entry in submission_rows:
            participant_id = str(entry.get("participant_id") or "").strip()
            submissions_by_participant.setdefault(participant_id, []).append(entry)

        flat_rows = _flatten_participant_metrics(
            snapshot_at=snapshot_at,
            competition_id=args.competition_id,
            ranking_rows=ranking_rows,
            submissions_by_participant=submissions_by_participant,
        )
        all_rows.extend(flat_rows)

        _write_jsonl(timeline_jsonl, flat_rows)
        _write_jsonl(
            rankings_jsonl,
            [{"snapshot_at": snapshot_at, "competition_id": args.competition_id, "rankings": ranking_rows}],
        )
        _write_jsonl(
            submissions_jsonl,
            [{"snapshot_at": snapshot_at, "competition_id": args.competition_id, "submissions": submission_rows}],
        )
        _write_jsonl(
            intelligence_jsonl,
            [{"snapshot_at": snapshot_at, "competition_id": args.competition_id, "report": intelligence_data}],
        )
        _rewrite_csv(timeline_csv, all_rows)

        all_terminated = bool(flat_rows) and all(not bool(row.get("is_running")) for row in flat_rows)
        if args.duration > 0 and (time.time() - started_at) >= args.duration:
            break
        if all_terminated:
            break
        time.sleep(max(args.interval, 1.0))

    print(f"timeline_jsonl={timeline_jsonl}")
    print(f"timeline_csv={timeline_csv}")
    print(f"rankings_jsonl={rankings_jsonl}")
    print(f"submissions_jsonl={submissions_jsonl}")
    print(f"intelligence_jsonl={intelligence_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
