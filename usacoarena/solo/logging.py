"""记录单题运行过程的日志工具。"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from usacoarena.utils.logger_config import get_logger

logger = get_logger("solo_logger")


_LANGUAGE_EXT = {
    "cpp": ".cpp",
    "c++": ".cpp",
    "python": ".py",
    "py": ".py",
    "java": ".java",
    "rust": ".rs",
    "go": ".go",
}


@dataclass
class AttemptLogEntry:
    """描述一次提交尝试。"""

    attempt: int
    language: str
    code: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    judge_status: str
    passed_cases: Optional[int]
    total_cases: Optional[int]
    error_message: Optional[str]
    prompt_tokens_cumulative_problem: int
    completion_tokens_cumulative_problem: int
    total_tokens_cumulative_problem: int
    prompt_tokens_cumulative_run: int
    completion_tokens_cumulative_run: int
    total_tokens_cumulative_run: int
    usage_details: Optional[Dict[str, Any]] = None

    def to_dict(self, code_path: str) -> Dict[str, Any]:
        payload = asdict(self)
        payload["code_path"] = code_path
        return payload


class SoloRunLogger:
    """管理本地日志输出。"""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.code_dir = self.base_dir / "code"
        self.code_dir.mkdir(exist_ok=True)
        self._jsonl_path = self.base_dir / "attempts.jsonl"
        self._markdown_path = self.base_dir / "attempts.md"
        self._run_meta_path = self.base_dir / "run.json"
        self._conversation_dir = self.base_dir / "conversations"
        self._conversation_dir.mkdir(exist_ok=True)
        self._init_markdown()

    def _init_markdown(self) -> None:
        if not self._markdown_path.exists():
            header = [
                "# LLM 单题尝试记录",
                f"创建时间：{datetime.now().isoformat(timespec='seconds')}",
                "",
            ]
            self._markdown_path.write_text("\n".join(header), encoding="utf-8")

    def start_run(self, metadata: Dict[str, Any]) -> None:
        """写入运行元数据。"""
        payload = {
            "status": "running",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            **metadata,
        }
        self._run_meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _code_extension(self, language: str) -> str:
        return _LANGUAGE_EXT.get(language.lower(), ".txt")

    def log_attempt(
        self,
        entry: AttemptLogEntry,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> Path:
        """记录一次提交并返回代码文件路径。"""
        code_path = self.code_dir / f"attempt_{entry.attempt}{self._code_extension(entry.language)}"
        code_path.write_text(entry.code, encoding="utf-8")

        record = entry.to_dict(code_path=str(code_path.relative_to(self.base_dir)))
        record["timestamp"] = datetime.now().isoformat(timespec="seconds")

        conversation_path: Optional[Path] = None
        if messages is not None:
            conversation_path = self._conversation_dir / f"attempt_{entry.attempt}.json"
            conversation_path.write_text(
                json.dumps(messages, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            record["conversation_path"] = str(conversation_path.relative_to(self.base_dir))

        with self._jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        md_lines = [
            f"## 尝试 {entry.attempt}",
            f"- 语言：{entry.language}",
            f"- 判题结果：{entry.judge_status}",
            f"- 样例通过：{entry.passed_cases}/{entry.total_cases if entry.total_cases is not None else '?'}",
            f"- Token：prompt={entry.prompt_tokens or 0}, completion={entry.completion_tokens or 0}, total={entry.total_tokens or 0}",
            (
                "- 累计 Token（题目）："
                f"prompt={entry.prompt_tokens_cumulative_problem}, "
                f"completion={entry.completion_tokens_cumulative_problem}, "
                f"total={entry.total_tokens_cumulative_problem}"
            ),
            (
                "- 累计 Token（整体）："
                f"prompt={entry.prompt_tokens_cumulative_run}, "
                f"completion={entry.completion_tokens_cumulative_run}, "
                f"total={entry.total_tokens_cumulative_run}"
            ),
        ]
        if entry.error_message:
            md_lines.append(f"- 错误信息：{entry.error_message}")
        if conversation_path is not None:
            md_lines.append(
                f"- 对话记录：{conversation_path.relative_to(self.base_dir)}"
            )
        md_lines.append("")
        md_lines.append("```")
        md_lines.append(entry.code.strip())
        md_lines.append("```")
        md_lines.append("")
        with self._markdown_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")

        return code_path

    def finalize(self, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """收尾运行并更新元数据文件。"""
        final_payload = {
            "status": status,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        if self._run_meta_path.exists():
            current = json.loads(self._run_meta_path.read_text(encoding="utf-8"))
            final_payload = {**current, **final_payload}
        if extra:
            final_payload.update(extra)
        self._run_meta_path.write_text(json.dumps(final_payload, indent=2, ensure_ascii=False), encoding="utf-8")
