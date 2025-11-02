#!/usr/bin/env python3
"""
Stress-test the /compile-and-execute endpoint with a single fixed test case.
Load the specified source code and IO files, then issue concurrent requests to measure stability and latency.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional

import requests


LANGUAGE_CODES = {
    "cpp": "cpp",
    "python": "py12",
    "java": "java21",
}


def load_text(path: str) -> str:
    """Load file content while preserving line breaks."""
    return Path(path).read_text(encoding="utf-8")


def build_payload(
    language: str,
    source_code: str,
    stdin_data: str,
    expected_output: str,
    timeout_ms: int,
    file_io_name: Optional[str],
    checker_type: str,
) -> Dict:
    """Construct the request payload that matches README_OJ.md."""
    compile_section = {
        "language": LANGUAGE_CODES[language],
        "source_code": source_code,
    }
    if language == "cpp":
        compile_section["compiler_options"] = ["-O2", "-std=c++17"]

    execute_section = {
        "stdin": stdin_data,
        "timeout_ms": timeout_ms,
        "file_io_name": file_io_name,
    }

    test_case_section = {
        "checker_type": checker_type,
        "expected_output": expected_output,
    }

    return {
        "compile": compile_section,
        "execute": execute_section,
        "test_case": test_case_section,
    }


def describe_latency(latencies: list[float]) -> str:
    """Generate a latency summary."""
    average = statistics.mean(latencies)
    maximum = max(latencies)
    minimum = min(latencies)
    if len(latencies) >= 20:
        p95 = statistics.quantiles(latencies, n=100)[94]
    else:
        p95 = maximum
    return f"avg={average:.3f}s p95={p95:.3f}s max={maximum:.3f}s min={minimum:.3f}s"


def worker(endpoint: str, payload: Dict, http_timeout: float) -> Dict:
    """Execute a single request and return the result with latency."""
    started = time.perf_counter()
    try:
        response = requests.post(endpoint, json=payload, timeout=http_timeout)
        latency = time.perf_counter() - started
        status_code = response.status_code

        try:
            body = response.json()
        except ValueError:
            return {
                "success": False,
                "latency": latency,
                "status_code": status_code,
                "verdict": None,
                "compile_exit": None,
                "execute_exit": None,
                "stderr": response.text.strip()[:200],
            }

        if isinstance(body, dict) and isinstance(body.get("body"), str):
            body = json.loads(body["body"])

        compile_result = body.get("compile", {}) or {}
        execute_result = body.get("execute") or {}

        compile_exit = compile_result.get("exit_code")
        verdict = execute_result.get("verdict")

        success = (
            status_code == 200
            and compile_exit == 0
            and verdict == "accepted"
        )

        return {
            "success": success,
            "latency": latency,
            "status_code": status_code,
            "verdict": verdict,
            "compile_exit": compile_exit,
            "execute_exit": execute_result.get("exit_code"),
            "stderr": execute_result.get("stderr") or compile_result.get("stderr"),
        }
    except Exception as exc:
        latency = time.perf_counter() - started
        return {
            "success": False,
            "latency": latency,
            "status_code": None,
            "verdict": None,
            "compile_exit": None,
            "execute_exit": None,
            "stderr": str(exc),
        }


def run_benchmark(
    endpoint: str,
    payload: Dict,
    total_requests: int,
    concurrency: int,
    http_timeout: float,
) -> Dict:
    """Execute requests concurrently and aggregate the results."""
    latencies: list[float] = []
    successes = 0
    failures: list[Dict] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(worker, endpoint, payload, http_timeout)
            for _ in range(total_requests)
        ]

        for future in as_completed(futures):
            result = future.result()
            latencies.append(result["latency"])
            if result["success"]:
                successes += 1
            else:
                failures.append(result)

    return {
        "latencies": latencies,
        "successes": successes,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Stress-test the OJ endpoint with a single data point.")
    parser.add_argument("--endpoint", default="http://localhost:10086/compile-and-execute", help="OJ service endpoint")
    parser.add_argument("--language", choices=list(LANGUAGE_CODES), default="cpp", help="Source language")
    parser.add_argument("--source-file", required=True, help="Path to the source code file")
    parser.add_argument("--input-file", required=True, help="Path to the input data file")
    parser.add_argument("--expected-file", required=True, help="Path to the expected output file")
    parser.add_argument("--total-requests", type=int, default=50, help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=8, help="Number of concurrent threads")
    parser.add_argument("--timeout-ms", type=int, default=4000, help="OJ execution timeout (ms)")
    parser.add_argument("--http-timeout", type=float, default=15.0, help="HTTP request timeout (seconds)")
    parser.add_argument("--file-io-name", help="Optional file_io_name for file-IO style problems")
    parser.add_argument("--checker-type", default="strict_diff", help="Checker type")
    parser.add_argument("--save-failures", help="Write failing results to a JSONL file")
    return parser.parse_args()


def main() -> None:
    """Entry point: load files, build the payload, execute the benchmark, and print statistics."""
    args = parse_args()

    source_code = load_text(args.source_file)
    stdin_data = load_text(args.input_file)
    expected_output = load_text(args.expected_file)

    payload = build_payload(
        language=args.language,
        source_code=source_code,
        stdin_data=stdin_data,
        expected_output=expected_output,
        timeout_ms=args.timeout_ms,
        file_io_name=args.file_io_name,
        checker_type=args.checker_type,
    )

    summary = run_benchmark(
        endpoint=args.endpoint,
        payload=payload,
        total_requests=args.total_requests,
        concurrency=args.concurrency,
        http_timeout=args.http_timeout,
    )

    success_rate = summary["successes"] / args.total_requests * 100
    print("=== Single-Case Stress Test Report ===")
    print(f"Endpoint: {args.endpoint}")
    print(f"Total requests: {args.total_requests}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Success rate: {summary['successes']} / {args.total_requests} ({success_rate:.2f}%)")
    print(f"Latency: {describe_latency(summary['latencies'])}")

    if summary["failures"]:
        print(f"Failure samples ({len(summary['failures'])}):")
        for failure in summary["failures"][:5]:
            print(
                f"- status={failure['status_code']} verdict={failure['verdict']} "
                f"stderr={failure['stderr']!r} latency={failure['latency']:.3f}s"
            )

    if summary["failures"] and args.save_failures:
        output_path = Path(args.save_failures)
        with output_path.open("w", encoding="utf-8") as fp:
            for failure in summary["failures"]:
                fp.write(json.dumps(failure, ensure_ascii=False) + "\n")
        print(f"Failure details written to {output_path}")


if __name__ == "__main__":
    main()
