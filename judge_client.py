#!/usr/bin/env python3
"""Simple client for the USACO Arena judge server."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit code to the judge server and print per-test results."
    )
    parser.add_argument(
        "code_path",
        help="Path to the source file to submit.",
    )
    parser.add_argument(
        "--problem-id",
        required=True,
        help="Problem identifier, e.g. 1524_platinum_forklift_certified.",
    )
    parser.add_argument(
        "--language",
        default="cpp",
        help="Language string expected by the judge (default: cpp).",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8081/api/judge/evaluate",
        help="Judge server endpoint (default: http://127.0.0.1:8081/api/judge/evaluate).",
    )
    parser.add_argument(
        "--participant-id",
        help="Optional participant identifier passed through to the judge.",
    )
    parser.add_argument(
        "--submission-id",
        help="Optional submission identifier passed through to the judge.",
    )
    return parser.parse_args()


def load_code(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as source:
            return source.read()
    except OSError as exc:  # pragma: no cover - CLI convenience
        print(f"Failed to read code from {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def build_payload(args: argparse.Namespace, code: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "problem_id": args.problem_id,
        "language": args.language,
        "code": code,
    }
    if args.participant_id:
        payload["participant_id"] = args.participant_id
    if args.submission_id:
        payload["submission_id"] = args.submission_id
    return payload


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Judge request failed with HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Unable to reach judge server at {url}: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(raw.decode(encoding))
    except json.JSONDecodeError as exc:
        print(f"Failed to decode response as JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def iter_test_results(response: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if isinstance(response.get("test_results"), list):
        return response["test_results"]
    submission = response.get("submission")
    if isinstance(submission, dict) and isinstance(submission.get("test_results"), list):
        return submission["test_results"]
    return ()


def print_results(results: Iterable[Dict[str, Any]]) -> None:
    found = False
    for index, result in enumerate(results, start=1):
        found = True
        case_id = result.get("test_case_id") or f"case_{index}"
        status = result.get("status") or "UNKNOWN"
        details = []
        runtime = result.get("runtime_ms")
        if runtime is not None:
            details.append(f"time={runtime}ms")
        memory = result.get("memory_kb")
        if memory is not None:
            details.append(f"mem={memory}KB")
        message = result.get("error_message")
        suffix = ""
        if details:
            suffix += " (" + ", ".join(str(d) for d in details) + ")"
        if message:
            suffix += f" | error: {message.strip()}"
        print(f"{case_id}: {status}{suffix}")
    if not found:
        print("No test results returned by judge.", file=sys.stderr)


def main() -> None:
    args = parse_args()
    code = load_code(args.code_path)
    payload = build_payload(args, code)
    response = post_json(args.url, payload)
    if not response.get("ok", False):
        error_message = response.get("error", "Unknown error")
        print(f"Judge returned error: {error_message}", file=sys.stderr)
        sys.exit(1)
    print_results(iter_test_results(response))
    summary = response.get("summary")
    if isinstance(summary, dict):
        passed = summary.get("passed")
        total = summary.get("total")
        status = summary.get("status")
        if passed is not None and total is not None and status:
            print(f"Summary: {passed}/{total} {status}")


if __name__ == "__main__":
    main()
