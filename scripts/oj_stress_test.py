#!/usr/bin/env python3
"""
OJ 压力测试工具
----------------
针对 README_OJ.md 描述的 /compile-and-execute 接口，通过并发请求与可调输入规模评估服务吞吐、延迟与稳定性。
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
    """根据参数加载源代码；若未指定则提供默认求和模板。"""
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

    raise ValueError(f"暂不支持的语言：{args.language}")


def load_dataset(path: Optional[str]) -> List[List[int]]:
    """从 JSON/文本中加载测试数据；若为空则返回空列表代表需在线生成。"""
    if not path:
        return []

    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"数据文件不存在：{dataset_path}")

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
                raise ValueError(f"无法解析数据行：{line}")
        return cases

    # 默认按纯数字文本解析，每行一组，用空格或逗号分隔
    cases = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        tokens = [token.strip() for token in line.replace(",", " ").split() if token.strip()]
        if tokens:
            cases.append([int(token) for token in tokens])
    return cases


def generate_numbers(rng: random.Random, count: int, magnitude: int) -> List[int]:
    """生成指定数量与数量级的随机整数用于构造 stdin。"""
    limit = 10 ** magnitude
    return [rng.randrange(-limit, limit) for _ in range(count)]


def build_payloads(
    args: argparse.Namespace,
    source_code: str,
    dataset: Iterable[List[int]],
) -> Iterable[Dict]:
    """持续生成请求 payload，结合自定义数据或在线随机生成。"""
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
    """将有限数据集循环使用，以便支撑长时间压力测试。"""
    while True:
        for case in dataset:
            yield case


def describe_latency(latencies: List[float]) -> str:
    """生成延迟统计描述。"""
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
    """发送单次请求并记录指标。"""
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
    """按照设定的并发度执行压力测试，并汇总结果。"""
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
        description="对 /compile-and-execute 进行并发压力测试，评估延迟与成功率。",
    )
    parser.add_argument("--endpoint", default="http://localhost:10086/compile-and-execute", help="OJ 接口地址")
    parser.add_argument("--language", choices=list(LANGUAGE_CODE), default="cpp", help="测试语言")
    parser.add_argument("--code-file", help="自定义源代码文件路径")
    parser.add_argument("--dataset", help="从文件加载输入集合（JSON/文本），支持循环使用")
    parser.add_argument("--total-requests", type=int, default=100, help="总请求数")
    parser.add_argument("--concurrency", type=int, default=8, help="最大并发度")
    parser.add_argument("--timeout-ms", type=int, default=3000, help="OJ 执行超时（毫秒）")
    parser.add_argument("--http-timeout", type=float, default=10.0, help="HTTP 请求超时时间（秒）")
    parser.add_argument("--min-numbers", type=int, default=2, help="随机生成输入时的最小数字个数")
    parser.add_argument("--max-numbers", type=int, default=4096, help="随机生成输入时的最大数字个数")
    parser.add_argument("--number-magnitude", type=int, default=6, help="随机整数的数量级（10^m）")
    parser.add_argument("--no-stdin", action="store_true", help="禁用 stdin 以测试编译阶段吞吐")
    parser.add_argument("--seed", type=int, default=2025, help="随机数种子，便于复现压测场景")
    parser.add_argument("--save-failures", help="将失败案例写入 JSONL 文件")
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

    print("=== OJ 压力测试报告 ===")
    print(f"接口: {args.endpoint}")
    print(f"总请求: {args.total_requests}")
    print(f"并发度: {args.concurrency}")
    print(f"成功率: {summary['successes']} / {args.total_requests} ({success_rate:.2f}%)")
    print(f"延迟: {describe_latency(latencies)}")

    if summary["failures"]:
        print(f"失败样本（{len(summary['failures'])}）：")
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
            print(f"失败详情已写入 {output_path}")


if __name__ == "__main__":
    main()
