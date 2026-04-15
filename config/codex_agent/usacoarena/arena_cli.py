#!/usr/bin/env python3
"""Small CLI helper for USACOArena participant HTTP actions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error as url_error
from urllib import request as url_request


class CLIError(RuntimeError):
    """Raised for CLI/runtime errors."""


class ArenaHTTP:
    """Minimal JSON API client built on Python standard library only."""

    def __init__(self, base_url: str, timeout: float) -> None:
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            raise CLIError("USACOARENA_BASE_URL is required")
        self.base_url = base
        self.timeout = float(timeout)

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        body: Optional[bytes] = None
        headers: Dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = url_request.Request(url=url, data=body, headers=headers, method=method.upper())

        response_status = 0
        response_text = ""
        try:
            with url_request.urlopen(req, timeout=self.timeout) as resp:
                response_status = int(resp.getcode() or 0)
                response_text = resp.read().decode("utf-8", errors="replace")
        except url_error.HTTPError as exc:
            response_status = int(exc.code or 0)
            try:
                response_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                response_text = str(exc)
        except url_error.URLError as exc:
            raise CLIError(f"network error for {method} {path}: {exc}") from exc

        try:
            data = json.loads(response_text)
        except Exception as exc:
            preview = response_text.strip()[:500]
            raise CLIError(
                f"invalid json response for {method} {path}: HTTP {response_status}, body={preview}"
            ) from exc

        if not isinstance(data, dict):
            raise CLIError(f"invalid response shape for {method} {path}: {type(data)!r}")

        if response_status >= 400:
            message = data.get("message") or data.get("error") or str(data)
            raise CLIError(f"HTTP {response_status} for {method} {path}: {message}")

        if data.get("status") != "success":
            message = data.get("message") or "unknown api error"
            raise CLIError(f"API error for {method} {path}: {message}")

        return data


def env_value(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    text = str(raw).strip()
    if text:
        return text
    return default


def require_value(value: str, *, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise CLIError(f"{name} is required")
    return text


def resolve_problem_id(cli_value: str) -> str:
    candidate = str(cli_value or "").strip()
    if candidate:
        return candidate
    from_env = env_value("USACOARENA_PROBLEM_ID")
    if from_env:
        return from_env
    raise CLIError("problem_id is required (pass --problem-id or set USACOARENA_PROBLEM_ID)")


def print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def enrich_with_timing_state(
    client: ArenaHTTP,
    payload: Dict[str, Any],
    *,
    competition_id: str,
    participant_id: str,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    existing = payload.get("data")
    if isinstance(existing, dict) and "elapsed_time_seconds" in existing:
        return payload

    try:
        status_payload = client.request(
            "GET",
            f"/api/participants/status/{competition_id}/{participant_id}",
        )
    except CLIError:
        return payload

    timing_data = status_payload.get("data")
    if not isinstance(timing_data, dict):
        return payload

    timing_state = {
        "elapsed_time_seconds": timing_data.get("elapsed_time_seconds", 0),
        "delivery_time_seconds": timing_data.get("delivery_time_seconds", 0),
        "delivery_time_multiplier": timing_data.get("delivery_time_multiplier", 1.0),
        "delivery_time_credit": timing_data.get("delivery_time_credit", 0.0),
        "delivery_time_settled": bool(timing_data.get("delivery_time_settled", False)),
        "consumed_credit": timing_data.get("consumed_credit"),
    }
    merged = dict(payload)
    merged["participant_timing_state"] = timing_state
    return merged


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USACOArena participant HTTP helper")
    parser.add_argument(
        "--api-base",
        default=env_value("USACOARENA_BASE_URL", "http://127.0.0.1:5000"),
        help="USACOArena base URL",
    )
    parser.add_argument(
        "--competition-id",
        default=env_value("USACOARENA_COMPETITION_ID", ""),
        help="Competition ID",
    )
    parser.add_argument(
        "--participant-id",
        default=env_value("USACOARENA_PARTICIPANT_ID", ""),
        help="Participant ID",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(env_value("USACOARENA_REQUEST_TIMEOUT", "30")),
        help="HTTP timeout seconds",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Get participant running status")
    subparsers.add_parser("state", help="Get participant full solved/submission state")
    subparsers.add_parser("list-problems", help="List problems in this competition")
    subparsers.add_parser("rankings", help="Get current competition rankings")
    subparsers.add_parser("gateway", help="Get participant-scoped gateway credentials")

    show_problem = subparsers.add_parser("show-problem", help="Get one problem statement")
    show_problem.add_argument("--problem-id", default="", help="Problem ID")

    submit = subparsers.add_parser("submit", help="Submit source code")
    submit.add_argument("--problem-id", default="", help="Problem ID")
    submit.add_argument("--code-file", required=True, help="Path to code file")
    submit.add_argument("--language", default=env_value("USACOARENA_LANGUAGE", "cpp"), help="Language")

    submission = subparsers.add_parser("submission", help="Get submission detail by id")
    submission.add_argument("--submission-id", required=True, help="Submission ID")

    quit_comp = subparsers.add_parser("quit", help="Terminate this participant")
    quit_comp.add_argument(
        "--reason",
        default="Voluntarily Quit Competition",
        help="Termination reason",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    api_base = require_value(args.api_base, name="api_base")
    competition_id = require_value(args.competition_id, name="competition_id")
    participant_id = require_value(args.participant_id, name="participant_id")

    client = ArenaHTTP(api_base, timeout=float(args.timeout))

    try:
        if args.command == "status":
            data = client.request(
                "GET",
                f"/api/participants/status/{competition_id}/{participant_id}",
            )
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "state":
            data = client.request(
                "GET",
                f"/api/participants/get_solved_problems/{competition_id}/{participant_id}",
            )
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "list-problems":
            data = client.request("GET", f"/api/problems/list/{competition_id}")
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "show-problem":
            problem_id = resolve_problem_id(args.problem_id)
            data = client.request("GET", f"/api/problems/get/{competition_id}/{problem_id}")
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "submit":
            problem_id = resolve_problem_id(args.problem_id)
            code_path = Path(args.code_file).expanduser()
            if not code_path.exists() or not code_path.is_file():
                raise CLIError(f"code file not found: {code_path}")
            code = code_path.read_text(encoding="utf-8")
            payload = {"code": code, "language": str(args.language or "cpp").strip() or "cpp"}
            data = client.request(
                "POST",
                f"/api/submissions/create/{competition_id}/{participant_id}/{problem_id}",
                payload=payload,
            )
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "submission":
            submission_id = require_value(args.submission_id, name="submission_id")
            data = client.request("GET", f"/api/submissions/get/{submission_id}")
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "rankings":
            data = client.request("GET", f"/api/rankings/get/{competition_id}")
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "gateway":
            data = client.request(
                "GET",
                f"/api/participants/gateway_credentials/{competition_id}/{participant_id}",
            )
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        if args.command == "quit":
            reason = str(args.reason or "Voluntarily Quit Competition").strip() or "Voluntarily Quit Competition"
            data = client.request(
                "POST",
                f"/api/participants/terminate/{competition_id}/{participant_id}",
                payload={"reason": reason},
            )
            print_json(
                enrich_with_timing_state(
                    client,
                    data,
                    competition_id=competition_id,
                    participant_id=participant_id,
                )
            )
            return 0

        raise CLIError(f"unknown command: {args.command}")
    except CLIError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
