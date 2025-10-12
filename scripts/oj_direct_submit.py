"""Utility for submitting code and custom test cases directly to the OJ service.

This script mirrors the request format used by USACOArena when evaluating
submissions. Provide a source file or inline code plus a path to test cases
and the script will invoke the online judge at the configured endpoint.
"""

import argparse
import json
import os
import shlex
from contextlib import contextmanager
from typing import Iterable, List, Mapping, Optional

import requests

from usacoarena.engine.judge import Judge
from usacoarena.models.models import Case, SubmissionStatus, TestResult, generate_id


def load_test_cases(path: str, stdin_root: Optional[str] = None) -> List[Case]:
    """Load test cases from a JSON file or directory of .in/.out pairs."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Test case path not found: {path}")

    if os.path.isdir(path):
        return _load_directory_cases(path, stdin_root)

    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        return _load_json_cases(path)

    raise ValueError("Unsupported test case file type. Use a JSON file or directory with .in/.out pairs.")


def _load_directory_cases(directory: str, stdin_root: Optional[str]) -> List[Case]:
    """Create Case objects from matching .in/.out files in a directory."""
    input_files = [f for f in os.listdir(directory) if f.endswith(".in") or f.startswith("I.")]
    input_files.sort()

    stdin_root_abs: Optional[str] = os.path.abspath(stdin_root) if stdin_root else None

    cases: List[Case] = []
    for input_file in input_files:
        if input_file.endswith(".in"):
            output_file = input_file[:-3] + ".out"
        else:
            output_file = "O." + input_file[2:]

        input_path = os.path.join(directory, input_file)
        output_path = os.path.join(directory, output_file)

        if not os.path.exists(output_path):
            continue

        with open(input_path, "r", encoding="utf-8") as f_in:
            input_data = f_in.read()
        with open(output_path, "r", encoding="utf-8") as f_out:
            expected_output = f_out.read()

        relative_input_path: Optional[str] = None
        if stdin_root_abs:
            input_abs = os.path.abspath(input_path)
            try:
                common = os.path.commonpath([input_abs, stdin_root_abs])
            except ValueError:
                common = None
            if common == stdin_root_abs:
                relative_input_path = os.path.relpath(input_abs, stdin_root_abs)
            else:
                relative_input_path = None

        cases.append(
            Case(
                id=generate_id(),
                input_data=input_data,
                expected_output=expected_output,
                input_path=relative_input_path,
            )
        )

    if not cases:
        raise ValueError(f"No matching .in/.out test cases found in {directory}")

    return cases


def _load_json_cases(path: str) -> List[Case]:
    """Create Case objects from a JSON file."""
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    if isinstance(data, Mapping):
        candidates = data.get("test_cases") or data.get("cases") or data.get("data")
        if candidates is None:
            raise ValueError("JSON file must contain a 'test_cases' list or be a list of cases.")
    elif isinstance(data, Iterable):
        candidates = data
    else:
        raise ValueError("Unsupported JSON structure for test cases.")

    cases: List[Case] = []
    for idx, item in enumerate(candidates, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Test case entry #{idx} is not an object: {item}")

        input_data = (
            item.get("input_data")
            or item.get("input")
            or item.get("stdin")
            or item.get("in")
        )
        expected_output = (
            item.get("expected_output")
            or item.get("output")
            or item.get("stdout")
            or item.get("out")
        )

        if input_data is None or expected_output is None:
            raise ValueError(f"Test case entry #{idx} must include input and expected output fields: {item}")

        cases.append(Case(id=generate_id(), input_data=str(input_data), expected_output=str(expected_output)))

    if not cases:
        raise ValueError(f"No test cases loaded from {path}")

    return cases


def build_curl_command(url: str, headers: Mapping[str, str], body: Optional[str]) -> str:
    """Return a curl command string that mirrors the outgoing HTTP request."""
    parts = ["curl", "-X", "POST", shlex.quote(url)]

    for name, value in headers.items():
        parts.extend(["-H", shlex.quote(f"{name}: {value}")])

    if body is not None:
        parts.extend(["-d", shlex.quote(body)])

    return " ".join(parts)


@contextmanager
def record_curl_commands(path: Optional[str]):
    """Patch requests.post to log curl commands when a path is provided."""
    if not path:
        yield
        return

    original_post = requests.post

    def logging_post(url, *args, **kwargs):  # type: ignore[override]
        headers = dict(kwargs.get("headers") or {})
        body: Optional[str] = None

        if "json" in kwargs and kwargs["json"] is not None:
            body = json.dumps(kwargs["json"], separators=(",", ":"))
            headers.setdefault("Content-Type", "application/json")
        elif "data" in kwargs and kwargs["data"] is not None:
            data_payload = kwargs["data"]
            if isinstance(data_payload, (bytes, bytearray)):
                body = data_payload.decode("utf-8", errors="replace")
            else:
                body = str(data_payload)

        command = build_curl_command(url, headers, body)
        with open(path, "a", encoding="utf-8") as log_fp:
            log_fp.write(command + "\n")

        return original_post(url, *args, **kwargs)

    requests.post = logging_post  # type: ignore[assignment]
    try:
        yield
    finally:
        requests.post = original_post  # type: ignore[assignment]


def run_tests(
    code: str,
    language: str,
    cases: List[Case],
    oj_endpoint: str,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> List[TestResult]:
    """Invoke the USACOArena judge to run code against custom cases."""
    judge = Judge(oj_endpoint=oj_endpoint)
    return judge.test_code_with_custom_cases(
        code=code,
        language=language,
        test_cases=cases,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )


def format_result(result: TestResult) -> str:
    """Format a single test result for display."""
    status = result.status.value if isinstance(result.status, SubmissionStatus) else str(result.status)
    parts = [f"status={status}"]

    if result.runtime_ms is not None:
        parts.append(f"runtime_ms={result.runtime_ms}")
    if result.memory_kb is not None:
        parts.append(f"memory_kb={result.memory_kb}")
    # if result.output not in (None, ""):
    #     parts.append(f"output={result.output!r}")
    if result.error_message:
        parts.append(f"error={result.error_message!r}")

    return ", ".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit code and test cases directly to the OJ service.")
    code_group = parser.add_mutually_exclusive_group(required=True)
    code_group.add_argument("--code", help="Inline source code string")
    code_group.add_argument("--code-file", help="Path to a file containing the source code")

    parser.add_argument("--testcases", required=True, help="Path to test case file (JSON) or directory")
    parser.add_argument("--language", default="cpp", help="Programming language (default: cpp)")
    parser.add_argument(
        "--oj-endpoint",
        default="http://localhost:10086/compile-and-execute",
        help="Online judge endpoint URL",
    )
    parser.add_argument("--time-limit-ms", type=int, default=5000, help="Time limit per test case in milliseconds")
    parser.add_argument("--memory-limit-mb", type=int, default=256, help="Memory limit in MB")
    parser.add_argument(
        "--curl-log",
        help="Write the exact curl command for each OJ request to this file",
    )
    parser.add_argument(
        "--stdin-root",
        help="Host directory whose contents are mounted into the OJ at /data/tests",
    )

    return parser.parse_args()


def load_code(args: argparse.Namespace) -> str:
    if args.code is not None:
        return args.code

    with open(args.code_file, "r", encoding="utf-8") as fp:
        return fp.read()


def main() -> None:
    args = parse_args()
    code = load_code(args)
    cases = load_test_cases(args.testcases, args.stdin_root)

    if args.curl_log:
        open(args.curl_log, "w", encoding="utf-8").close()

    with record_curl_commands(args.curl_log):
        results = run_tests(
            code=code,
            language=args.language,
            cases=cases,
            oj_endpoint=args.oj_endpoint,
            time_limit_ms=args.time_limit_ms,
            memory_limit_mb=args.memory_limit_mb,
        )

    successes = sum(1 for result in results if result.status == SubmissionStatus.ACCEPTED)
    for index, result in enumerate(results, start=1):
        print(f"Test case {index}: {format_result(result)}")

    print(f"Passed {successes} / {len(results)} test cases")


if __name__ == "__main__":
    main()
