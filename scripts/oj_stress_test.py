#!/usr/bin/env python3
"""
OJ stress-testing utility
-------------------------
Evaluate throughput, latency, and stability of the `/compile-and-execute` endpoint described in
README_OJ.md by issuing concurrent requests with configurable input sizes.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import string
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests


LANGUAGE_CODE = {
    "cpp": "cpp",
    "python": "py12",
    "java": "java21",
}


def load_source(args: argparse.Namespace) -> str:
    """Load source code from arguments or fall back to a default summation template."""
    if args.code_file:
        return Path(args.code_file).read_text(encoding="utf-8")

    if args.language == "cpp":
        return (
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n"
            "int main(){ios::sync_with_stdio(false);cin.tie(nullptr);"
            "long long x,sum=0;while(cin>>x)sum+=x;cout<<sum<<\"\\n\";return 0;}\n"
        )
    if args.language == "python":
        return (
            "import sys\n"
            "data = sys.stdin.read().strip().split()\n"
            "total = sum(int(x) for x in data) if data else 0\n"
            "print(total)\n"
        )
    if args.language == "java":
        return (
            "import java.io.*;\n"
            "import java.util.*;\n"
            "public class Main{public static void main(String[] args)throws Exception{"
            "var br=new BufferedInputStream(System.in);var sb=new StringBuilder();"
            "int c;while((c=br.read())!=-1){if(!Character.isWhitespace(c)){sb.append((char)c);}else{sb.append(' ');}}"
            "long sum=0;for(String token:sb.toString().trim().split(\" \")){if(!token.isEmpty()){sum+=Long.parseLong(token);}}"
            "System.out.println(sum);}}\n"
        )

    raise ValueError(f"Unsupported language: {args.language}")


def load_dataset(path: Optional[str]) -> List[List[int]]:
    """Load test data from JSON/text; return an empty list to trigger on-the-fly generation."""
    if not path:
        return []

    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file does not exist: {dataset_path}")

    if dataset_path.suffix.lower() in {".json", ".jsonl"}:
        cases: List[List[int]] = []
        for line in dataset_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and "numbers" in payload:
                cases.append([int(x) for x in payload["numbers"]])
            elif isinstance(payload, list):
                cases.append([int(x) for x in payload])
            else:
                raise ValueError(f"Unable to parse dataset line: {line}")
        return cases

    # Interpret plain-number text by line, splitting on whitespace or commas
    cases = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        tokens = [token.strip() for token in line.replace(",", " ").split() if token.strip()]
        if tokens:
            cases.append([int(token) for token in tokens])
    return cases


def generate_numbers(rng: random.Random, count: int, magnitude: int) -> List[int]:
    """Generate random integers to populate stdin."""
    limit = 10 ** magnitude
    return [rng.randrange(-limit, limit) for _ in range(count)]


def build_payloads(
    args: argparse.Namespace,
    source_code: str,
    dataset: Iterable[List[int]],
) -> Iterable[Dict]:
    """Yield request payloads driven by custom data or random generation."""
    rng = random.Random(args.seed)

    for idx in range(args.total_requests):
        if dataset:
            numbers = next(dataset)
        else:
            count = rng.randint(args.min_numbers, args.max_numbers)
            numbers = generate_numbers(rng, count, args.number_magnitude)

        stdin = " ".join(str(num) for num in numbers) + "\n"
        expected = f"{sum(numbers)}\n"

        compile_section = {
            "language": LANGUAGE_CODE[args.language],
            "source_code": source_code,
        }

        if args.language == "cpp":
            compile_section["compiler_options"] = ["-O2", "-std=c++17"]

        payload = {
            "compile": compile_section,
            "execute": {
                "stdin": stdin if not args.no_stdin else "",
                "timeout_ms": args.timeout_ms,
                "file_io_name": None,
            },
            "test_case": {
                "checker_type": "strict_diff",
                "expected_output": expected,
            },
        }

        yield idx, payload


def cycle_dataset(dataset: List[List[int]]) -> Iterable[List[int]]:
    """Cycle through a finite dataset to sustain long-running tests."""
    while True:
        for case in dataset:
            yield case


def describe_latency(latencies: List[float]) -> str:
    """Produce a human-readable latency summary."""
    p95 = statistics.quantiles(latencies, n=100)[94] if len(latencies) >= 2 else latencies[0]
    return (
        f"avg={statistics.mean(latencies):.3f}s "
        f"p95={p95:.3f}s "
        f"max={max(latencies):.3f}s "
        f"min={min(latencies):.3f}s"
    )


def worker(
    endpoint: str,
    payload: Dict,
    timeout: float,
) -> Dict:
    """Send a single request and record metrics."""
    sent_at = time.perf_counter()
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        latency = time.perf_counter() - sent_at
        status_code = response.status_code

        body = response.json()
        if isinstance(body, dict) and "body" in body and isinstance(body["body"], str):
            body = json.loads(body["body"])

        compile_result = body.get("compile", {})
        execute_result = body.get("execute", {})

        verdict = execute_result.get("verdict")
        compile_ok = compile_result.get("exit_code", 0) == 0

        success = (
            status_code == 200
            and compile_ok
            and verdict == "accepted"
        )

        return {
            "success": success,
            "latency": latency,
            "status_code": status_code,
            "verdict": verdict,
            "compile_exit": compile_result.get("exit_code"),
            "execute_exit": execute_result.get("exit_code"),
            "execute_wall": execute_result.get("wall_time"),
            "execute_mem": execute_result.get("memory_usage"),
            "stderr": execute_result.get("stderr") or compile_result.get("stderr"),
        }
    except Exception as exc:
        latency = time.perf_counter() - sent_at
        return {
            "success": False,
            "latency": latency,
            "status_code": None,
            "verdict": None,
            "compile_exit": None,
            "execute_exit": None,
            "execute_wall": None,
            "execute_mem": None,
            "stderr": str(exc),
        }


def stress(endpoint: str, payloads: Iterable[Dict], concurrency: int, timeout: float) -> Dict:
    """Execute the stress test with the configured concurrency and aggregate results."""
    latencies: List[float] = []
    successes = 0
    failures: List[Dict] = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(worker, endpoint, payload, timeout): idx
            for idx, payload in payloads
        }

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
    parser = argparse.ArgumentParser(
        description="Stress test the /compile-and-execute endpoint with concurrent requests to evaluate latency and success rate.",
    )
    parser.add_argument("--endpoint", default="http://localhost:10086/compile-and-execute", help="OJ endpoint")
    parser.add_argument("--language", choices=list(LANGUAGE_CODE), default="cpp", help="Programming language to test")
    parser.add_argument("--code-file", help="Path to a custom source file")
    parser.add_argument("--dataset", help="Load input cases from a JSON/text file (cycled)")
    parser.add_argument("--total-requests", type=int, default=100, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=8, help="Maximum concurrency")
    parser.add_argument("--timeout-ms", type=int, default=3000, help="OJ execution timeout in milliseconds")
    parser.add_argument("--http-timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--min-numbers", type=int, default=2, help="Minimum numbers when generating random input")
    parser.add_argument("--max-numbers", type=int, default=4096, help="Maximum numbers when generating random input")
    parser.add_argument("--number-magnitude", type=int, default=6, help="Magnitude for random integers (10^m)")
    parser.add_argument("--no-stdin", action="store_true", help="Disable stdin to isolate compilation throughput")
    parser.add_argument("--seed", type=int, default=2025, help="Random seed for reproducibility")
    parser.add_argument("--save-failures", help="Write failing cases to a JSONL file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_code = load_source(args)

    dataset = load_dataset(args.dataset)
    dataset_iter = cycle_dataset(dataset) if dataset else ()

    payload_iterable = build_payloads(args, source_code, dataset_iter)
    summary = stress(args.endpoint, payload_iterable, args.concurrency, args.http_timeout)

    success_rate = summary["successes"] / args.total_requests * 100
    latencies = summary["latencies"]

    print("=== OJ Stress Test Report ===")
    print(f"Endpoint: {args.endpoint}")
    print(f"Total requests: {args.total_requests}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Success rate: {summary['successes']} / {args.total_requests} ({success_rate:.2f}%)")
    print(f"Latency: {describe_latency(latencies)}")

    if summary["failures"]:
        print(f"Failure samples ({len(summary['failures'])}):")
        for failure in summary["failures"][:5]:
            print(
                f"- verdict={failure['verdict']} status={failure['status_code']} "
                f"stderr={failure['stderr']!r} latency={failure['latency']:.3f}s"
            )

        if args.save_failures:
            output_path = Path(args.save_failures)
            with output_path.open("w", encoding="utf-8") as fp:
                for failure in summary["failures"]:
                    fp.write(json.dumps(failure, ensure_ascii=False) + "\n")
            print(f"Failure details written to {output_path}")


if __name__ == "__main__":
    main()
