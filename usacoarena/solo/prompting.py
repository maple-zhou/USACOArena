"""构建用于单题运行的提示词。"""

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
    """封装题面与系统提示词。"""

    problem: Problem
    system_prompt: str
    user_prompt: str


class SoloPromptBuilder:
    """负责加载题目并与模板组合生成最终提示词。"""

    def __init__(self, prompt_path: str, dataset_root: Optional[str] = None) -> None:
        self._prompt_path = Path(prompt_path)
        if not self._prompt_path.exists():
            raise FileNotFoundError(f"找不到提示词文件: {self._prompt_path}")

        if dataset_root:
            loader = USACOProblemLoader(data_path=dataset_root)
        else:
            loader = USACOProblemLoader()
        self._loader = loader

    def build(self, problem_id: str, preferred_language: Optional[str] = None) -> PromptBundle:
        """读取题目信息并拼装提示词。"""
        problem = self._loader.load_problem(problem_id)
        if not problem:
            raise ValueError(f"题目 {problem_id} 不存在，请确认数据集已准备。")

        system_prompt = self._prompt_path.read_text(encoding="utf-8").strip()
        user_prompt = self._assemble_user_prompt(problem, preferred_language)
        return PromptBundle(problem=problem, system_prompt=system_prompt, user_prompt=user_prompt)

    def _assemble_user_prompt(self, problem: Problem, preferred_language: Optional[str]) -> str:
        """生成包含题面详情的用户提示词。"""
        header = [
            "# 题目信息",
            f"题号: {problem.id}",
            f"标题: {problem.title}",
            f"时间限制: {problem.time_limit_ms} ms",
            f"内存限制: {problem.memory_limit_mb} MB",
            "",
            "## 题目描述",
            problem.description.strip(),
        ]
        if preferred_language:
            header.insert(4, f"请使用 {preferred_language} 语言编写并返回完整代码。")
        parts = ["\n".join(header)]

        if problem.sample_cases:
            sample_lines = ["", "## 样例输入输出"]
            for idx, case in enumerate(problem.sample_cases, start=1):
                sample_lines.append(f"### 样例 {idx}")
                sample_lines.append("输入：")
                sample_lines.append(f"```\n{case.input_data.strip()}\n```")
                sample_lines.append("输出：")
                sample_lines.append(f"```\n{case.expected_output.strip()}\n```")
            parts.append("\n".join(sample_lines))

        parts.append("请直接返回最终代码，不要添加解释或额外文本。")
        return "\n\n".join(parts)

    def load_test_cases(self, problem_id: str):
        """提供触发器以便脚本获取完整测试数据。"""
        return self._loader.load_test_cases(problem_id)
