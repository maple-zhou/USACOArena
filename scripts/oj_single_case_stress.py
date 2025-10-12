#!/usr/bin/env python3
"""
针对单个用例批量压测 /compile-and-execute 接口。
读取指定源码与输入输出文件，通过并发请求评估判题服务稳定性与延迟。
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
    """读取文件内容，保留原始换行。"""
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
    """构造与 README_OJ.md 匹配的请求体。"""
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
    """生成延迟统计摘要。"""
    average = statistics.mean(latencies)
    maximum = max(latencies)
    minimum = min(latencies)
    if len(latencies) >= 20:
        p95 = statistics.quantiles(latencies, n=100)[94]
    else:
        p95 = maximum
    return f"avg={average:.3f}s p95={p95:.3f}s max={maximum:.3f}s min={minimum:.3f}s"


def worker(endpoint: str, payload: Dict, http_timeout: float) -> Dict:
    """单次请求任务，返回判题结果与耗时。"""
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
    """并发执行请求并汇总结果。"""
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
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="针对单个数据点压测 OJ 判题接口。")
    parser.add_argument("--endpoint", default="http://localhost:10086/compile-and-execute", help="OJ 服务地址")
    parser.add_argument("--language", choices=list(LANGUAGE_CODES), default="cpp", help="源码语言")
    parser.add_argument("--source-file", required=True, help="源代码文件路径")
    parser.add_argument("--input-file", required=True, help="输入数据文件路径")
    parser.add_argument("--expected-file", required=True, help="期望输出文件路径")
    parser.add_argument("--total-requests", type=int, default=50, help="请求次数")
    parser.add_argument("--concurrency", type=int, default=8, help="并发线程数")
    parser.add_argument("--timeout-ms", type=int, default=4000, help="OJ 执行超时（毫秒）")
    parser.add_argument("--http-timeout", type=float, default=15.0, help="HTTP 请求超时（秒）")
    parser.add_argument("--file-io-name", help="可选 file_io_name，用于文件读写题目")
    parser.add_argument("--checker-type", default="strict_diff", help="判题方式")
    parser.add_argument("--save-failures", help="失败结果输出到 JSONL 文件")
    return parser.parse_args()


def main() -> None:
    """程序入口：加载文件、构造 payload、执行压测并输出统计。"""
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
    print("=== 单用例压测报告 ===")
    print(f"接口: {args.endpoint}")
    print(f"总请求: {args.total_requests}")
    print(f"并发度: {args.concurrency}")
    print(f"成功率: {summary['successes']} / {args.total_requests} ({success_rate:.2f}%)")
    print(f"延迟: {describe_latency(summary['latencies'])}")

    if summary["failures"]:
        print(f"失败样本（{len(summary['failures'])}）:")
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
        print(f"失败详情已写入 {output_path}")


if __name__ == "__main__":
    main()
