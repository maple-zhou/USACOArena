"""Hydro-backed judging adapter for USACOArena."""

from __future__ import annotations

from typing import Dict, List, Optional

from usacoarena.models.models import (
    Case,
    Competition,
    Problem,
    Submission,
    SubmissionStatus,
    TestResult,
)
from usacoarena.utils.hydro_client import HydroClient, HydroClientError
from usacoarena.utils.logger_config import get_logger

logger = get_logger("judge")


_FINISHED_STATUSES = {
    "ACCEPTED",
    "WRONG_ANSWER",
    "COMPILE_ERROR",
    "COMPILATION_ERROR",
    "RUNTIME_ERROR",
    "TIME_LIMIT_EXCEEDED",
    "MEMORY_LIMIT_EXCEEDED",
    "FORMAT_ERROR",
    "OUTPUT_LIMIT_EXCEEDED",
    "CANCELED",
    "SYSTEM_ERROR",
}


class Judge:
    """
    Judge adapter that delegates both submissions and pretests to Hydro.

    The constructor historically accepted an OJ endpoint. In the Hydro version,
    the same positional argument is treated as the Hydro base URL for backward
    compatibility with existing startup scripts.
    """

    def __init__(
        self,
        oj_endpoint: Optional[str] = None,
        *,
        hydro_client: Optional[HydroClient] = None,
    ) -> None:
        if hydro_client is not None:
            self.hydro_client = hydro_client
        elif oj_endpoint:
            self.hydro_client = HydroClient(base_url=oj_endpoint)
        else:
            env_client = HydroClient.from_env()
            if env_client is None:
                raise ValueError(
                    "Hydro judge requires USACOARENA_HYDRO_BASE_URL or an explicit HydroClient"
                )
            self.hydro_client = env_client

        self.oj_endpoint = self.hydro_client.base_url
        logger.debug("Initialized Hydro-backed Judge with base URL %s", self.oj_endpoint)

    def evaluate_submission(
        self,
        submission: Submission,
        problem: Problem,
        competition: Optional[Competition] = None,
        first_one: bool = False,
    ) -> Submission:
        """Submit code to Hydro, wait for the record, and map it back to arena models."""
        logger.debug(
            "Evaluating submission %s for problem %s via Hydro",
            submission.id,
            problem.id,
        )

        try:
            submit_payload = self.hydro_client.submit_solution(
                problem_id=problem.id,
                code=submission.code,
                language=self._get_language_code(submission.language),
            )
            record_id = str(
                submit_payload.get("record_id")
                or submit_payload.get("rid")
                or submit_payload.get("id")
                or ""
            ).strip()
            if not record_id:
                raise HydroClientError(f"Hydro submission response missing record_id: {submit_payload}")

            record = self.hydro_client.wait_for_record(record_id)
            submission.test_results = self._record_to_test_results(record)
            submission.status = self._record_to_submission_status(record)

            base_score = problem.get_problem_base_score(competition) if competition else 0
            submission.pass_score = base_score if submission.status == SubmissionStatus.ACCEPTED else 0

            first_ac_bonus = problem.get_problem_firstAC_bonus(competition) if competition else 0
            if submission.status == SubmissionStatus.ACCEPTED and first_one and first_ac_bonus > 0:
                submission.pass_score += first_ac_bonus

            submission.submission_tokens = submission.calculate_submission_tokens(competition)
            submission.penalty = submission.calculate_penalty(competition)
            return submission

        except Exception as exc:
            logger.error("Error evaluating Hydro submission: %s", exc, exc_info=True)
            submission.status = SubmissionStatus.COMPILATION_ERROR
            submission.test_results = [
                TestResult(
                    test_case_id="error",
                    status=SubmissionStatus.COMPILATION_ERROR,
                    error_message=str(exc),
                )
            ]
            submission.pass_score = 0
            submission.penalty = submission.calculate_penalty(competition)
            return submission

    def test_code_with_custom_cases(
        self,
        code: str,
        language: str,
        test_cases: List[Case],
        time_limit_ms: int = 5000,
        memory_limit_mb: int = 256,
    ) -> List[TestResult]:
        """
        Run ad-hoc code tests through Hydro pretest.

        Hydro pretest executes custom inputs on a specific problem. The caller is
        expected to supply `Case.input_path` or `Case.id` containing a valid
        problem id. When `expected_output` is present, USACOArena performs a
        lightweight post-hoc comparison to retain the old interface semantics.
        """
        if not test_cases:
            return []

        problem_id = self._infer_problem_id_from_cases(test_cases)
        if not problem_id:
            raise ValueError(
                "Hydro-backed test_code requires a problem_id. "
                "Provide it via each test case input_path or set test case id to the target problem id."
            )

        inputs = [case.input_data for case in test_cases]
        payload = self.hydro_client.pretest(
            problem_id=problem_id,
            code=code,
            language=self._get_language_code(language),
            inputs=inputs,
        )

        results_payload = payload.get("results")
        if not isinstance(results_payload, list):
            results_payload = []

        test_results: List[TestResult] = []
        for idx, case in enumerate(test_cases):
            record_case = results_payload[idx] if idx < len(results_payload) and isinstance(results_payload[idx], dict) else {}
            output = str(record_case.get("stdout", "") or "")
            stderr = str(record_case.get("stderr", "") or "")
            mapped_status = self._map_hydro_status(record_case.get("status"))

            if case.expected_output.strip():
                mapped_status = (
                    SubmissionStatus.ACCEPTED
                    if self._compare_outputs(output, case.expected_output)
                    else SubmissionStatus.WRONG_ANSWER
                )

            test_results.append(
                TestResult(
                    test_case_id=case.id or f"custom_case_{idx + 1}",
                    status=mapped_status,
                    runtime_ms=self._safe_int(record_case.get("time_ms")),
                    memory_kb=self._safe_int(record_case.get("memory_kb")),
                    output=output.strip(),
                    error_message=stderr.strip() or None,
                )
            )

        return test_results

    def test_oj_connection(self) -> bool:
        """Compatibility health check used by the server status endpoint."""
        try:
            payload = self.hydro_client.health()
            return bool(payload.get("connected", payload.get("ok", True)))
        except Exception:
            return False

    def _record_to_test_results(self, record: Dict) -> List[TestResult]:
        cases = record.get("test_cases")
        if not isinstance(cases, list):
            message = self._join_texts(record.get("judge_texts"), record.get("compiler_texts"))
            return [
                TestResult(
                    test_case_id="record",
                    status=self._record_to_submission_status(record),
                    runtime_ms=self._safe_int(record.get("time_ms")),
                    memory_kb=self._safe_int(record.get("memory_kb")),
                    error_message=message or None,
                )
            ]

        results: List[TestResult] = []
        for idx, item in enumerate(cases, start=1):
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            results.append(
                TestResult(
                    test_case_id=str(item.get("id") or idx),
                    status=self._map_hydro_status(item.get("status")),
                    runtime_ms=self._safe_int(item.get("time_ms") or item.get("time")),
                    memory_kb=self._safe_int(item.get("memory_kb") or item.get("memory")),
                    output=str(item.get("stdout", "") or "").strip() or None,
                    error_message=str(message).strip() if message else None,
                )
            )
        return results

    def _record_to_submission_status(self, record: Dict) -> SubmissionStatus:
        return self._map_hydro_status(record.get("status"))

    def _map_hydro_status(self, status: Optional[object]) -> SubmissionStatus:
        if isinstance(status, int):
            integer_map = {
                0: SubmissionStatus.ACCEPTED,
                1: SubmissionStatus.WRONG_ANSWER,
                2: SubmissionStatus.TIME_LIMIT_EXCEEDED,
                3: SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
                4: SubmissionStatus.RUNTIME_ERROR,
                5: SubmissionStatus.COMPILATION_ERROR,
                6: SubmissionStatus.RUNTIME_ERROR,
                7: SubmissionStatus.RUNTIME_ERROR,
                8: SubmissionStatus.RUNTIME_ERROR,
                9: SubmissionStatus.PENDING,
            }
            return integer_map.get(status, SubmissionStatus.RUNTIME_ERROR)

        normalized = str(status or "").strip().upper()
        mapping = {
            "AC": SubmissionStatus.ACCEPTED,
            "ACCEPTED": SubmissionStatus.ACCEPTED,
            "OK": SubmissionStatus.ACCEPTED,
            "WA": SubmissionStatus.WRONG_ANSWER,
            "WRONG_ANSWER": SubmissionStatus.WRONG_ANSWER,
            "PE": SubmissionStatus.WRONG_ANSWER,
            "FORMAT_ERROR": SubmissionStatus.WRONG_ANSWER,
            "CE": SubmissionStatus.COMPILATION_ERROR,
            "COMPILE_ERROR": SubmissionStatus.COMPILATION_ERROR,
            "COMPILATION_ERROR": SubmissionStatus.COMPILATION_ERROR,
            "RE": SubmissionStatus.RUNTIME_ERROR,
            "RUNTIME_ERROR": SubmissionStatus.RUNTIME_ERROR,
            "SYSTEM_ERROR": SubmissionStatus.RUNTIME_ERROR,
            "OLE": SubmissionStatus.RUNTIME_ERROR,
            "OUTPUT_LIMIT_EXCEEDED": SubmissionStatus.RUNTIME_ERROR,
            "TLE": SubmissionStatus.TIME_LIMIT_EXCEEDED,
            "TIME_LIMIT_EXCEEDED": SubmissionStatus.TIME_LIMIT_EXCEEDED,
            "MLE": SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
            "MEMORY_LIMIT_EXCEEDED": SubmissionStatus.MEMORY_LIMIT_EXCEEDED,
            "PENDING": SubmissionStatus.PENDING,
            "WAITING": SubmissionStatus.PENDING,
            "JUDGING": SubmissionStatus.PENDING,
            "COMPILING": SubmissionStatus.PENDING,
            "FETCHED": SubmissionStatus.PENDING,
        }
        if normalized in _FINISHED_STATUSES:
            return mapping.get(normalized, SubmissionStatus.RUNTIME_ERROR)
        return mapping.get(normalized, SubmissionStatus.PENDING)

    def _get_language_code(self, language: str) -> str:
        normalized = str(language or "").strip().lower()
        aliases = {
            "c++": "cc.cc17",
            "cpp": "cc.cc17",
            "cc": "cc.cc17",
            "c": "c",
            "java": "java",
            "python": "py.py3",
            "python3": "py.py3",
            "py": "py.py3",
            "pypy3": "py.pypy3",
            "rust": "rs",
            "go": "go",
            "javascript": "js",
            "node": "js",
            "nodejs": "js",
        }
        return aliases.get(normalized, normalized or "cc.cc17")

    def _compare_outputs(self, actual: str, expected: str) -> bool:
        actual = (actual or "").replace("\r\n", "\n").strip()
        expected = (expected or "").replace("\r\n", "\n").strip()

        if actual == expected:
            return True

        if " ".join(actual.split()) == " ".join(expected.split()):
            return True

        try:
            return abs(float(actual) - float(expected)) < 1e-6
        except (TypeError, ValueError):
            return False

    def _infer_problem_id_from_cases(self, test_cases: List[Case]) -> Optional[str]:
        for case in test_cases:
            candidate = str(case.input_path or "").strip()
            if candidate:
                return candidate
        for case in test_cases:
            candidate = str(case.id or "").strip()
            if candidate and not candidate.startswith("custom_"):
                return candidate
        return None

    def _join_texts(self, *sections: object) -> str:
        parts: List[str] = []
        for section in sections:
            if isinstance(section, list):
                for item in section:
                    text = str(item or "").strip()
                    if text:
                        parts.append(text)
            elif section:
                text = str(section).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts)

    def _safe_int(self, value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
