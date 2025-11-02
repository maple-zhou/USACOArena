#!/usr/bin/env python3
"""Script that orchestrates an end-to-end run for a single-problem LLM agent."""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from usacoarena.engine.judge import Judge
from usacoarena.models.models import Submission, SubmissionStatus, generate_id
from usacoarena.solo import (
    AttemptLogEntry,
    LLMClient,
    LLMConfig,
    LLMUsage,
    SoloPromptBuilder,
    SoloRunLogger,
)
from usacoarena.utils.logger_config import get_logger, setup_logging

logger = get_logger("solo_runner")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single-problem LLM agent and log judging results"
    )
    parser.add_argument(
        "--problem-id",
        action="append",
        dest="problem_ids",
        required=True,
        help="USACO problem ID(s); provide multiple entries or comma-separated list",
    )
    parser.add_argument("--agent-config", required=True, help="Path to the LLM configuration file")
    parser.add_argument(
        "--competitor-name",
        help="Select a competitor when the config lists multiple entries",
    )
    parser.add_argument(
        "--prompt-file",
        default="prompts/solo_agent_prompt.txt",
        help="Path to the prompt template",
    )
    parser.add_argument(
        "--language",
        default="cpp",
        help="Submission language (e.g., cpp/python/java)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        dest="max_retries",
        help="Maximum retries after a failed LLM call; 0 means unlimited",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        dest="max_retries",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--token-limit",
        type=int,
        default=1000000,
        help="Cumulative token threshold; stop all problems once exceeded (default 1,000,000)",
    )
    parser.add_argument(
        "--oj-endpoint",
        default="http://localhost:10086/compile-and-execute",
        help="Online judge endpoint",
    )
    parser.add_argument(
        "--dataset-root",
        help="Optional dataset root",
    )
    parser.add_argument(
        "--log-dir",
        help="Optional log output directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate code only without contacting the judge",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="LLM request timeout (seconds)",
    )
    return parser.parse_args()


def default_log_dir(problem_ids: List[str], agent_config: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_agent_config = re.sub(r"[^A-Za-z0-9_-]", "_", agent_config)
    if len(problem_ids) == 1:
        safe_problem = re.sub(r"[^A-Za-z0-9_-]", "_", problem_ids[0])
        suffix = f"{safe_agent_config}_{safe_problem}"
    else:
        suffix = f"{safe_agent_config}_batch"
    return Path("logs/solo_runs") / f"{timestamp}_{suffix}"


def extract_code(content: str, language: str) -> str:
    """Extract a code block from the model response."""
    fence_pattern = re.compile(r"```(?:([\w+#-]+)\n)?(.*?)```", re.DOTALL)
    matches = fence_pattern.findall(content)
    if matches:
        target = None
        lang_lower = language.lower()
        for lang, code in matches:
            lang = (lang or "").strip().lower()
            if not lang:
                target = code
                break
            if lang in {lang_lower, _language_alias(lang_lower)}:
                target = code
                break
        if target is None:
            target = matches[0][1]
        return target.strip()
    return content.strip()


def _language_alias(language: str) -> str:
    if language == "cpp":
        return "c++"
    if language == "c++":
        return "cpp"
    if language == "py":
        return "python"
    return language


def _usage_total_tokens(usage: Optional[LLMUsage]) -> int:
    if not usage:
        return 0
    if usage.total_tokens is not None:
        return usage.total_tokens
    prompt = usage.prompt_tokens or 0
    completion = usage.completion_tokens or 0
    return prompt + completion


def _call_llm_with_retry(
    client: LLMClient,
    messages: List[Dict[str, str]],
    max_retries: int,
) -> Tuple[str, Optional[LLMUsage]]:
    attempts = 0
    while True:
        try:
            return client.infer(messages)
        except RuntimeError as exc:
            attempts += 1
            logger.warning("LLM call failed, retry %d: %s", attempts, exc)
            if max_retries and attempts >= max_retries:
                raise RuntimeError(
                    f"LLM call failed {attempts} times consecutively; aborting: {exc}"
                ) from exc


def build_feedback(submission: Submission, total_cases: Optional[int]) -> str:
    """Generate structured feedback text based on judging results."""
    total_available = total_cases or max(len(submission.test_results), 0)
    passed_count = sum(1 for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED)
    failed_cases = [(idx, tr) for idx, tr in enumerate(submission.test_results, start=1) if tr.status != SubmissionStatus.ACCEPTED]

    lines: List[str] = []
    if not failed_cases:
        lines.append(
            f"Your most recent submission passed {passed_count}/{total_available or passed_count} test cases. "
            "All tests passed."
        )
        return "\n".join(lines)

    failed_index, failed_case = failed_cases[0]
    failure_status = failed_case.status.value if hasattr(failed_case.status, "value") else failed_case.status
    lines.append(
        f"Your most recent submission passed {passed_count}/{total_available or len(submission.test_results)} test cases. "
        f"Test case {failed_index} failed with status {failure_status}."
    )

    if failed_case.test_case_id:
        lines.append(f"Failed test case ID: {failed_case.test_case_id}.")
    if failed_case.error_message:
        lines.append(f"Error message: {failed_case.error_message.strip()[:500]}")
    if failed_case.output and isinstance(failed_case.output, str) and failed_case.output.strip():
        lines.append(f"Program output:\n{failed_case.output.strip()[:500]}")

    lines.append("Please revise the solution and submit the complete code again.")
    return "\n".join(lines)


def summarise_attempt(submission: Submission, total_cases: Optional[int]) -> Dict[str, int]:
    passed = sum(1 for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED)
    if total_cases is None:
        total_cases = max(passed, len(submission.test_results))
    return {"passed": passed, "total": total_cases}


def main() -> int:
    args = parse_args()
    raw_problem_values = []
    for item in args.problem_ids:
        raw_problem_values.extend([p.strip() for p in item.split(",") if p.strip()])
    problem_ids = raw_problem_values
    if not problem_ids:
        raise ValueError("At least one problem-id is required")

    log_root = Path(args.log_dir) if args.log_dir else default_log_dir(problem_ids, args.agent_config)
    log_root.mkdir(parents=True, exist_ok=True)
    setup_logging(level="INFO", log_file=str(log_root / "runner.log"))

    builder = SoloPromptBuilder(args.prompt_file, dataset_root=args.dataset_root)
    config = LLMConfig.from_file(args.agent_config, competitor_name=args.competitor_name)
    client = LLMClient(config, timeout=args.timeout)
    judge = None if args.dry_run else Judge(oj_endpoint=args.oj_endpoint)

    logger.info(
        "Starting single-problem run: problems=%s, agent=%s, token-limit=%s",
        problem_ids,
        config.name,
        args.token_limit,
    )

    total_tokens_consumed = 0
    total_prompt_tokens_consumed = 0
    total_completion_tokens_consumed = 0
    solved_problems = 0
    token_limit_reached = False

    for index, problem_id in enumerate(problem_ids, start=1):
        safe_problem = re.sub(r"[^A-Za-z0-9_-]", "_", problem_id)
        problem_log_dir = (
            log_root
            if len(problem_ids) == 1 and args.log_dir
            else log_root / safe_problem
        )
        problem_log_dir.mkdir(parents=True, exist_ok=True)

        bundle = builder.build(problem_id, preferred_language=args.language)
        total_cases = len(builder.load_test_cases(problem_id)) or None

        run_logger = SoloRunLogger(problem_log_dir)
        run_logger.start_run(
            {
                "problem_id": problem_id,
                "agent_name": config.name,
                "language": args.language,
                "oj_endpoint": args.oj_endpoint,
                "max_retries": args.max_retries,
                "dry_run": args.dry_run,
                "token_limit": args.token_limit,
                "problem_index": index,
                "total_problems": len(problem_ids),
            }
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": bundle.system_prompt},
            {"role": "user", "content": bundle.user_prompt},
        ]

        problem_tokens = 0
        problem_prompt_tokens = 0
        problem_completion_tokens = 0
        problem_solved = False

        attempt = 0
        while True:
            attempt += 1
            logger.info("[%s] Attempt %d", problem_id, attempt)
            try:
                response_text, usage = _call_llm_with_retry(
                    client, messages, args.max_retries
                )
            except RuntimeError as exc:
                logger.error("LLM retries exhausted: %s", exc)
                entry = AttemptLogEntry(
                    attempt=attempt,
                    language=args.language,
                    code="",
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    judge_status="LLM_RETRY_EXHAUSTED",
                    passed_cases=None,
                    total_cases=total_cases,
                    error_message=str(exc),
                    prompt_tokens_cumulative_problem=problem_prompt_tokens,
                    completion_tokens_cumulative_problem=problem_completion_tokens,
                    total_tokens_cumulative_problem=problem_tokens,
                    prompt_tokens_cumulative_run=total_prompt_tokens_consumed,
                    completion_tokens_cumulative_run=total_completion_tokens_consumed,
                    total_tokens_cumulative_run=total_tokens_consumed,
                )
                run_logger.log_attempt(entry, messages=[dict(m) for m in messages])
                token_limit_reached = bool(
                    args.token_limit and total_tokens_consumed >= args.token_limit
                )
                break

            code = extract_code(response_text, args.language)
            prompt_tokens = (usage.prompt_tokens or 0) if usage else 0
            completion_tokens = (usage.completion_tokens or 0) if usage else 0
            attempt_tokens = _usage_total_tokens(usage)
            total_prompt_tokens_consumed += prompt_tokens
            total_completion_tokens_consumed += completion_tokens
            total_tokens_consumed += attempt_tokens
            problem_prompt_tokens += prompt_tokens
            problem_completion_tokens += completion_tokens
            problem_tokens += attempt_tokens

            if not code:
                logger.warning("[%s] No code extracted from model response (attempt %d)", problem_id, attempt)
                messages.append({"role": "assistant", "content": response_text})
                entry = AttemptLogEntry(
                    attempt=attempt,
                    language=args.language,
                    code=response_text,
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    total_tokens=usage.total_tokens if usage else None,
                    judge_status="NO_CODE",
                    passed_cases=None,
                    total_cases=total_cases,
                    error_message="No code block detected in model response",
                    prompt_tokens_cumulative_problem=problem_prompt_tokens,
                    completion_tokens_cumulative_problem=problem_completion_tokens,
                    total_tokens_cumulative_problem=problem_tokens,
                    prompt_tokens_cumulative_run=total_prompt_tokens_consumed,
                    completion_tokens_cumulative_run=total_completion_tokens_consumed,
                    total_tokens_cumulative_run=total_tokens_consumed,
                )
                run_logger.log_attempt(entry, messages=[dict(m) for m in messages])
                if args.token_limit and total_tokens_consumed >= args.token_limit:
                    token_limit_reached = True
                    break
                messages.append(
                    {
                        "role": "user",
                        "content": "Code was not detected. Please output the full solution inside a code block.",
                    }
                )
                continue

            if args.dry_run:
                messages.append({"role": "assistant", "content": response_text})
                entry = AttemptLogEntry(
                    attempt=attempt,
                    language=args.language,
                    code=code,
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    total_tokens=usage.total_tokens if usage else None,
                    judge_status="DRY_RUN",
                    passed_cases=None,
                    total_cases=total_cases,
                    error_message="Dry-run mode skipped judging",
                    prompt_tokens_cumulative_problem=problem_prompt_tokens,
                    completion_tokens_cumulative_problem=problem_completion_tokens,
                    total_tokens_cumulative_problem=problem_tokens,
                    prompt_tokens_cumulative_run=total_prompt_tokens_consumed,
                    completion_tokens_cumulative_run=total_completion_tokens_consumed,
                    total_tokens_cumulative_run=total_tokens_consumed,
                )
                run_logger.log_attempt(entry, messages=[dict(m) for m in messages])
                logger.info("[%s] Dry-run mode: code generated.", problem_id)
                problem_solved = True
                break

            submission = Submission(
                id=generate_id(),
                competition_id="solo",
                participant_id=config.name,
                problem_id=bundle.problem.id,
                code=code,
                language=args.language,
                submitted_at=datetime.now(),
            )

            try:
                submission = judge.evaluate_submission(submission, bundle.problem)
            except Exception as exc:
                logger.error("Judge service call failed: %s", exc)
                messages.append({"role": "assistant", "content": response_text})
                entry = AttemptLogEntry(
                    attempt=attempt,
                    language=args.language,
                    code=code,
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    total_tokens=usage.total_tokens if usage else None,
                    judge_status="JUDGE_ERROR",
                    passed_cases=None,
                    total_cases=total_cases,
                    error_message=str(exc),
                    prompt_tokens_cumulative_problem=problem_prompt_tokens,
                    completion_tokens_cumulative_problem=problem_completion_tokens,
                    total_tokens_cumulative_problem=problem_tokens,
                    prompt_tokens_cumulative_run=total_prompt_tokens_consumed,
                    completion_tokens_cumulative_run=total_completion_tokens_consumed,
                    total_tokens_cumulative_run=total_tokens_consumed,
                )
                run_logger.log_attempt(entry, messages=[dict(m) for m in messages])
                if args.token_limit and total_tokens_consumed >= args.token_limit:
                    token_limit_reached = True
                    break
                messages.append(
                    {
                        "role": "user",
                        "content": f"Judging failed: {exc}. Please output the code again.",
                    }
                )
                continue

            summary = summarise_attempt(submission, total_cases)
            status_value = submission.status.value if hasattr(submission.status, "value") else submission.status
            logger.info(
                "[%s] Judge result: %s, samples %s/%s",
                problem_id,
                status_value,
                summary["passed"],
                summary["total"],
            )

            messages.append({"role": "assistant", "content": response_text})
            entry = AttemptLogEntry(
                attempt=attempt,
                language=args.language,
                code=code,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                judge_status=status_value,
                passed_cases=summary["passed"],
                total_cases=summary["total"],
                error_message=None,
                prompt_tokens_cumulative_problem=problem_prompt_tokens,
                completion_tokens_cumulative_problem=problem_completion_tokens,
                total_tokens_cumulative_problem=problem_tokens,
                prompt_tokens_cumulative_run=total_prompt_tokens_consumed,
                completion_tokens_cumulative_run=total_completion_tokens_consumed,
                total_tokens_cumulative_run=total_tokens_consumed,
            )
            run_logger.log_attempt(entry, messages=[dict(m) for m in messages])

            if submission.status == SubmissionStatus.ACCEPTED:
                logger.info("[%s] All tests passed.", problem_id)
                problem_solved = True
                break

            feedback = build_feedback(submission, total_cases)
            messages.append({"role": "user", "content": feedback})

            if args.token_limit and total_tokens_consumed >= args.token_limit:
                token_limit_reached = True
                break
            # Continue to the next attempt

        if token_limit_reached:
            run_logger.finalize(
                "token_limit",
                {
                    "attempts": attempt,
                    "problem_tokens": problem_tokens,
                    "problem_prompt_tokens": problem_prompt_tokens,
                    "problem_completion_tokens": problem_completion_tokens,
                    "total_tokens": total_tokens_consumed,
                    "total_prompt_tokens": total_prompt_tokens_consumed,
                    "total_completion_tokens": total_completion_tokens_consumed,
                },
            )
            break

        run_logger.finalize(
            "success" if problem_solved else "failed",
            {
                "attempts": attempt,
                "problem_tokens": problem_tokens,
                "problem_prompt_tokens": problem_prompt_tokens,
                "problem_completion_tokens": problem_completion_tokens,
                "total_tokens": total_tokens_consumed,
                "total_prompt_tokens": total_prompt_tokens_consumed,
                "total_completion_tokens": total_completion_tokens_consumed,
            },
        )

        if problem_solved:
            solved_problems += 1
        if not problem_solved and args.dry_run:
            # Treat dry run as success
            solved_problems += 1

    if token_limit_reached:
        return 1
    return 0 if solved_problems == len(problem_ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
