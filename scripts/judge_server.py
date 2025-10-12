"""Flask 服务，为 Judge 提供 HTTP 接口，便于外部 Agent 远程判题。"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, request

from usacoarena.engine.judge import Judge
from usacoarena.models.models import (
    Competition,
    Submission,
    SubmissionStatus,
    generate_id,
)
from usacoarena.utils.logger_config import get_logger
from usacoarena.utils.problem_loader import USACOProblemLoader

LOGGER = get_logger("judge_server")


def _build_feedback(submission: Submission, total_cases: Optional[int]) -> str:
    """生成结构化反馈信息。"""
    total_available = total_cases or max(len(submission.test_results), 0)
    passed_count = sum(1 for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED)
    failed_cases = [
        (idx, tr)
        for idx, tr in enumerate(submission.test_results, start=1)
        if tr.status != SubmissionStatus.ACCEPTED
    ]

    if not failed_cases:
        return (
            f"你最近的一次提交测评结果为：通过了 {passed_count}/{total_available or passed_count} 个测试用例，"
            f"全部测试均已通过。"
        )

    failed_index, failed_case = failed_cases[0]
    failure_status = failed_case.status.value if hasattr(failed_case.status, "value") else str(failed_case.status)
    parts = [
        f"你最近的一次提交测评结果为：通过了 {passed_count}/{total_available or len(submission.test_results)} 个测试用例，"
        f"第 {failed_index} 个测试用例失败，判定为 {failure_status}。",
    ]
    if failed_case.test_case_id:
        parts.append(f"失败的测试用例编号：{failed_case.test_case_id}。")
    if failed_case.error_message:
        parts.append(f"错误信息：{failed_case.error_message.strip()[:500]}")
    if failed_case.output and isinstance(failed_case.output, str) and failed_case.output.strip():
        parts.append(f"程序输出：\n{failed_case.output.strip()[:500]}")
    parts.append("请修改代码并再次给出完整的源代码。")
    return "\n".join(parts)


def _summarise_submission(submission: Submission, total_cases: Optional[int]) -> Dict[str, Any]:
    """构造基础统计数据。"""
    passed = sum(1 for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED)
    total = total_cases or max(passed, len(submission.test_results))
    return {
        "passed": passed,
        "total": total,
        "status": submission.status.value if hasattr(submission.status, "value") else str(submission.status),
    }


@dataclass
class JudgeServerConfig:
    """Judge Server 配置，支持通过 CLI/环境变量覆盖。"""

    host: str = "0.0.0.0"
    port: int = 8081
    oj_endpoint: str = "http://localhost:10086/compile-and-execute"
    dataset_path: Optional[str] = None


class JudgeService:
    """封装 Judge 与题库加载逻辑，提供提交评测能力。"""

    def __init__(self, config: JudgeServerConfig):
        self.config = config
        self.loader = USACOProblemLoader(data_path=config.dataset_path)
        self.judge = Judge(oj_endpoint=config.oj_endpoint)
        LOGGER.info(
            "Judge service initialized (oj=%s, dataset=%s)",
            self.judge.oj_endpoint,
            self.loader.data_path,
        )

    def evaluate(self, payload: Dict[str, Any]) -> Tuple[Submission, Optional[int]]:
        """根据请求 payload 评测一次提交，返回 Submission 与总测试数。"""
        problem_id = (payload.get("problem_id") or "").strip()
        code = payload.get("code")
        language = (payload.get("language") or "python").strip()
        if not problem_id:
            raise ValueError("problem_id 不能为空")
        if not code:
            raise ValueError("code 不能为空")

        problem = self.loader.load_problem(problem_id)
        if not problem:
            raise ValueError(f"未找到题目 {problem_id}")

        competition = None
        competition_data = payload.get("competition")
        if competition_data:
            competition = Competition(
                id=competition_data.get("id", "offline"),
                title=competition_data.get("title", competition_data.get("name", "ad-hoc")),
                description=competition_data.get("description", ""),
                start_time=datetime.now(timezone.utc),
                end_time=None,
                max_tokens_per_participant=competition_data.get("max_tokens", 100000),
                rules=competition_data.get("rules"),
                is_active=True,
                participant_count=competition_data.get("participant_count", 0),
                problem_count=competition_data.get("problem_count", 0),
            )

        submission = Submission(
            id=payload.get("submission_id", generate_id()),
            competition_id=payload.get("competition_id", competition.id if competition else "offline"),
            participant_id=payload.get("participant_id", "judge-server"),
            problem_id=problem_id,
            code=code,
            language=language,
            submitted_at=datetime.now(timezone.utc),
        )

        judge = self.judge
        if payload.get("oj_endpoint"):
            judge = Judge(oj_endpoint=payload["oj_endpoint"])

        result = judge.evaluate_submission(
            submission,
            problem=problem,
            competition=competition,
            first_one=bool(payload.get("first_one", False)),
        )
        total_cases = payload.get("total_cases")
        if total_cases is None:
            total_cases = len(self.loader.load_test_cases(problem_id))
        return result, total_cases


def create_app(config: JudgeServerConfig) -> Flask:
    """创建 Flask 应用。"""
    service = JudgeService(config)
    app = Flask(__name__)

    @app.route("/healthz", methods=["GET"])
    def health() -> Any:
        return jsonify({"ok": True, "oj_endpoint": service.judge.oj_endpoint})

    @app.route("/api/judge/evaluate", methods=["POST"])
    def evaluate() -> Any:
        data = request.get_json(silent=True) or {}
        try:
            submission, total_cases = service.evaluate(data)
            feedback = _build_feedback(submission, total_cases)
            summary = _summarise_submission(submission, total_cases)
            response = {
                "ok": True,
                "submission": submission.to_dict(include_code=False),
                "test_results": [tr.to_dict() for tr in submission.test_results],
                "feedback": feedback,
                "summary": summary,
            }
            return jsonify(response)
        except ValueError as exc:
            LOGGER.warning("Invalid request data: %s", exc)
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover - 避免暴露堆栈
            LOGGER.error("Failed to evaluate submission", exc_info=True)
            return jsonify({"ok": False, "error": str(exc)}), 500

    return app


def _parse_args() -> JudgeServerConfig:
    parser = argparse.ArgumentParser(description="启动 Judge HTTP 服务")
    parser.add_argument("--host", default=os.getenv("JUDGE_SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("JUDGE_SERVER_PORT", "8081")))
    parser.add_argument(
        "--oj-endpoint",
        default=os.getenv("JUDGE_SERVER_OJ_ENDPOINT", "http://localhost:10086/compile-and-execute"),
    )
    parser.add_argument("--dataset-path", default=os.getenv("JUDGE_SERVER_DATASET_PATH"))
    args = parser.parse_args()
    return JudgeServerConfig(
        host=args.host,
        port=args.port,
        oj_endpoint=args.oj_endpoint,
        dataset_path=args.dataset_path,
    )


def main() -> None:
    config = _parse_args()
    app = create_app(config)
    LOGGER.info("Starting Judge server on %s:%s", config.host, config.port)
    app.run(host=config.host, port=config.port)


if __name__ == "__main__":
    main()
