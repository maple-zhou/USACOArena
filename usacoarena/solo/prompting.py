"""Construct prompts for single-problem LLM execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from usacoarena.models.models import Problem
from usacoarena.utils.problem_loader import USACOProblemLoader
from usacoarena.utils.logger_config import get_logger

logger = get_logger("solo_prompt")


@dataclass
class PromptBundle:
    """Bundle the problem statement with system and user prompts."""

    problem: Problem
    system_prompt: str
    user_prompt: str


class SoloPromptBuilder:
    """Load problems and compose the final templated prompts."""

    def __init__(self, prompt_path: str, dataset_root: Optional[str] = None) -> None:
        self._prompt_path = Path(prompt_path)
        if not self._prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {self._prompt_path}")

        if dataset_root:
            loader = USACOProblemLoader(data_path=dataset_root)
        else:
            loader = USACOProblemLoader()
        self._loader = loader

    def build(self, problem_id: str, preferred_language: Optional[str] = None) -> PromptBundle:
        """Load problem metadata and assemble prompts."""
        problem = self._loader.load_problem(problem_id)
        if not problem:
            raise ValueError(f"Problem {problem_id} is unavailable; ensure the dataset is prepared.")

        system_prompt = self._prompt_path.read_text(encoding="utf-8").strip()
        user_prompt = self._assemble_user_prompt(problem, preferred_language)
        return PromptBundle(problem=problem, system_prompt=system_prompt, user_prompt=user_prompt)

    def _assemble_user_prompt(self, problem: Problem, preferred_language: Optional[str]) -> str:
        """Construct the user-facing prompt with the full statement."""
        header = [
            "# Problem Details",
            f"ID: {problem.id}",
            f"Title: {problem.title}",
            f"Time Limit: {problem.time_limit_ms} ms",
            f"Memory Limit: {problem.memory_limit_mb} MB",
            "",
            "## Statement",
            problem.description.strip(),
        ]
        if preferred_language:
            header.insert(4, f"Please implement the solution in {preferred_language} and return only the complete code.")
        parts = ["\n".join(header)]

        if problem.sample_cases:
            sample_lines = ["", "## Sample Input / Output"]
            for idx, case in enumerate(problem.sample_cases, start=1):
                sample_lines.append(f"### Sample {idx}")
                sample_lines.append("Input:")
                sample_lines.append(f"```\n{case.input_data.strip()}\n```")
                sample_lines.append("Output:")
                sample_lines.append(f"```\n{case.expected_output.strip()}\n```")
            parts.append("\n".join(sample_lines))

        parts.append("Return only the final code without any additional commentary.")
        return "\n\n".join(parts)

    def load_test_cases(self, problem_id: str):
        """Expose a helper for scripts that need the full test set."""
        return self._loader.load_test_cases(problem_id)
