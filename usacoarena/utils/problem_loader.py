"""Hydro-backed problem loading utilities for USACOArena."""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from usacoarena.models.models import Case, Level, Problem, generate_id
from usacoarena.utils.hydro_client import HydroClient, HydroClientError
from usacoarena.utils.logger_config import get_logger

logger = get_logger("usaco_problem_loader")

_SECTION_PATTERN = re.compile(
    r"(?P<header>INPUT FORMAT|OUTPUT FORMAT|SAMPLE INPUT|SAMPLE OUTPUT|INPUT|OUTPUT)\s*:\s*",
    flags=re.IGNORECASE,
)


class USACOProblemLoader:
    """
    Backward-compatible problem loader that reads metadata from Hydro.

    The historical class name is kept intentionally so the rest of the
    USACOArena codebase can migrate with minimal churn.
    """

    def __init__(
        self,
        data_path: Optional[str] = None,
        *,
        hydro_client: Optional[HydroClient] = None,
    ) -> None:
        self.data_path = data_path
        self.hydro_client = hydro_client or HydroClient.from_env()
        if self.hydro_client is None:
            raise ValueError(
                "Hydro problem loader requires USACOARENA_HYDRO_BASE_URL "
                "or an explicit HydroClient instance"
            )

        self.problems_dict: Dict[str, Dict] = {}
        self._detail_cache: Dict[str, Dict] = {}
        self._load_problem_dict()

    def _load_problem_dict(self) -> None:
        try:
            problems = self.hydro_client.list_problems(detail=True)
        except HydroClientError as exc:
            logger.error("Failed to load Hydro problem library: %s", exc)
            self.problems_dict = {}
            return

        self.problems_dict = {
            str(problem.get("id")): problem
            for problem in problems
            if isinstance(problem, dict) and problem.get("id") is not None
        }
        self._detail_cache.update(self.problems_dict)

    def refresh(self) -> None:
        """Reload the problem index from Hydro."""
        self._load_problem_dict()

    def get_problem_ids(self, level: Optional[str] = None) -> List[str]:
        if not level:
            return list(self.problems_dict.keys())

        level_lower = str(level).strip().lower()
        return [
            pid
            for pid, problem in self.problems_dict.items()
            if str(problem.get("level", "")).strip().lower() == level_lower
        ]

    def load_solution(self, problem_id: str) -> Optional[str]:
        try:
            return self.hydro_client.get_problem_solution(problem_id)
        except HydroClientError as exc:
            logger.warning("Failed to load Hydro solution for %s: %s", problem_id, exc)
            return None

    def load_problem(self, problem_id: str) -> Optional[Problem]:
        detail = self._get_problem_detail(problem_id)
        if not detail:
            return None

        sample_cases = self._parse_sample_cases(detail)
        level = self._parse_level(detail.get("level"))

        return Problem(
            id=str(detail.get("id", problem_id)),
            title=str(detail.get("title", "")),
            description=str(detail.get("description", detail.get("statement", ""))),
            level=level,
            sample_cases=sample_cases,
            time_limit_ms=int(detail.get("time_limit_ms", 1000) or 1000),
            memory_limit_mb=int(detail.get("memory_limit_mb", 256) or 256),
        )

    def load_test_cases(self, problem_id: str) -> List[Case]:
        """
        Hidden test data is no longer available to USACOArena directly.

        This method remains for compatibility, but only returns public sample
        cases, which is sufficient for prompt construction and lightweight
        debugging flows.
        """
        problem = self.load_problem(problem_id)
        if not problem:
            return []
        return list(problem.sample_cases)

    def get_problem_with_test_cases(self, problem_id: str) -> Optional[Dict]:
        problem = self.load_problem(problem_id)
        if not problem:
            return None
        test_cases = self.load_test_cases(problem_id) or list(problem.sample_cases)
        return {
            "problem": problem,
            "test_cases": test_cases,
        }

    def import_problems_to_competition(self, competition, problem_ids: List[str]) -> int:
        count = 0
        for pid in problem_ids:
            if self.load_problem(pid):
                count += 1
        return count

    def get_problem_info(self, problem_id: str) -> Optional[Dict]:
        detail = self._get_problem_detail(problem_id)
        if not detail:
            return None
        samples = self._parse_sample_cases(detail)
        return {
            "id": str(detail.get("id", problem_id)),
            "title": str(detail.get("title", "")),
            "description": str(detail.get("description", detail.get("statement", ""))),
            "level": str(detail.get("level", "bronze")),
            "runtime_limit": int(detail.get("time_limit_ms", 1000) or 1000) // 1000,
            "memory_limit": int(detail.get("memory_limit_mb", 256) or 256),
            "sample_count": len(samples),
            "has_test_files": bool(detail.get("test_case_count", 0)),
        }

    def _get_problem_detail(self, problem_id: str) -> Optional[Dict]:
        problem_id = str(problem_id).strip()
        if not problem_id:
            return None

        if problem_id in self._detail_cache:
            return self._detail_cache[problem_id]

        try:
            detail = self.hydro_client.get_problem(problem_id)
        except HydroClientError as exc:
            logger.warning("Problem %s not found in Hydro: %s", problem_id, exc)
            return None

        self._detail_cache[problem_id] = detail
        self.problems_dict.setdefault(problem_id, detail)
        return detail

    def _parse_sample_cases(self, detail: Dict) -> List[Case]:
        raw_samples = detail.get("sample_cases")
        if isinstance(raw_samples, list):
            cases = []
            for item in raw_samples:
                if not isinstance(item, dict):
                    continue
                cases.append(
                    Case(
                        id=str(item.get("id") or generate_id()),
                        input_data=str(
                            item.get("input_data", item.get("input", "")) or ""
                        ),
                        expected_output=str(
                            item.get("expected_output", item.get("output", "")) or ""
                        ),
                        input_path=item.get("input_path"),
                    )
                )
            if cases:
                return cases

        statement = str(detail.get("statement", detail.get("description", "")) or "")
        return self._extract_samples_from_statement(statement)

    def _extract_samples_from_statement(self, statement: str) -> List[Case]:
        if not statement.strip():
            return []

        markers = list(_SECTION_PATTERN.finditer(statement))
        if not markers:
            return []

        sections: Dict[str, str] = {}
        for idx, match in enumerate(markers):
            start = match.end()
            end = markers[idx + 1].start() if idx + 1 < len(markers) else len(statement)
            header = match.group("header").strip().upper()
            sections[header] = statement[start:end].strip()

        input_text = sections.get("SAMPLE INPUT") or sections.get("INPUT")
        output_text = sections.get("SAMPLE OUTPUT") or sections.get("OUTPUT")
        if not input_text or not output_text:
            return []

        return [
            Case(
                id=generate_id(),
                input_data=input_text.strip(),
                expected_output=output_text.strip(),
            )
        ]

    def _parse_level(self, raw_level: Optional[str]) -> Level:
        normalized = str(raw_level or "").strip().lower()
        mapping = {
            "bronze": Level.BRONZE,
            "silver": Level.SILVER,
            "gold": Level.GOLD,
            "platinum": Level.PLATINUM,
        }
        return mapping.get(normalized, Level.BRONZE)
