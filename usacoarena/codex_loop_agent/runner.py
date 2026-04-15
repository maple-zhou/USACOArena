"""Standalone Codex loop runner for USACOArena competitions."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from .api_client import ArenaAPIError, ArenaClient, GatewayCredentials, ParticipantStatus
from .sandbox import RunnerSandbox, SandboxError


_SESSION_ID_REGEX = re.compile(r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b")
_DEFAULT_LOCAL_EVAL_OVERHEAD_CREDIT = 100.0

_STRATEGY_PROFILE_TEXTS: Dict[str, str] = {
    "swarm_fast_7": (
        "The Speedy Spendthrift (极速爆破流): Optimize for extreme speed. "
        "Maximize parallel exploration and spawn multiple coder agents simultaneously. "
        "Do not worry about token costs. If an evaluation fails, immediately pivot "
        "to a new parallel approach rather than sequential debugging."
    ),
    "swarm_balanced_4": (
        "The Cost-Aware Strategist (动态平衡流): Dynamically decide whether to debug "
        "or rewrite based on remaining budget and wall-clock pressure. Keep a measured "
        "parallel frontier and continuously trade off speed vs. cost."
    ),
    "swarm_lean_2": (
        "The Frugal Perfectionist (省吃俭用流): Think carefully, minimize parallel branches, "
        "and minimize local sandbox evaluations. Accept longer delivery time for much lower token cost."
    ),
    "usacoarena": (
        "The Cost-Aware Strategist (动态平衡流): Dynamically decide whether to debug "
        "or rewrite based on remaining budget and wall-clock pressure."
    ),
}


@dataclass(slots=True)
class RunnerConfig:
    """Configuration for standalone Codex loop runner."""

    api_base: str
    competition_id: str
    participant_id: str
    workspace: Path
    template_dir: Path

    codex_binary: str = "codex"
    model: str = "gpt-5.3-codex"
    language: str = "cpp"

    request_timeout: float = 30.0
    poll_interval_seconds: float = 5.0
    retry_min_backoff_seconds: float = 2.0
    retry_max_backoff_seconds: float = 60.0

    llm_isolate: bool = False
    sync_templates: bool = True
    force_template_overwrite: bool = False

    explicit_problem_id: Optional[str] = None
    resume_session_id: Optional[str] = None

    extra_codex_configs: List[str] = field(default_factory=list)


@dataclass(slots=True)
class RunnerState:
    """Persistent runner state for auto-resume."""

    session_id: Optional[str] = None
    run_count: int = 0
    consecutive_failures: int = 0
    last_exit_code: Optional[int] = None
    last_started_at: Optional[str] = None
    last_finished_at: Optional[str] = None
    last_stdout_log: Optional[str] = None
    last_stderr_log: Optional[str] = None
    last_error: Optional[str] = None
    selected_problem_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "RunnerState":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            session_id=_optional_str(payload.get("session_id")),
            run_count=_to_int(payload.get("run_count"), 0),
            consecutive_failures=_to_int(payload.get("consecutive_failures"), 0),
            last_exit_code=(
                None
                if payload.get("last_exit_code") is None
                else _to_int(payload.get("last_exit_code"), 0)
            ),
            last_started_at=_optional_str(payload.get("last_started_at")),
            last_finished_at=_optional_str(payload.get("last_finished_at")),
            last_stdout_log=_optional_str(payload.get("last_stdout_log")),
            last_stderr_log=_optional_str(payload.get("last_stderr_log")),
            last_error=_optional_str(payload.get("last_error")),
            selected_problem_id=_optional_str(payload.get("selected_problem_id")),
        )

    def to_payload(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_count": self.run_count,
            "consecutive_failures": self.consecutive_failures,
            "last_exit_code": self.last_exit_code,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_stdout_log": self.last_stdout_log,
            "last_stderr_log": self.last_stderr_log,
            "last_error": self.last_error,
            "selected_problem_id": self.selected_problem_id,
        }


@dataclass(frozen=True, slots=True)
class RunTrace:
    """Per-run trace file layout."""

    run_index: int
    run_tag: str
    run_dir: Path
    events_path: Path
    budget_log_path: Path
    agents_path: Path
    evaluation_trace_path: Path
    manifest_path: Path
    summary_path: Path
    agent_exec_path: Path
    tool_stats_path: Path
    session_meta_path: Path
    codex_events_path: Path
    codex_stderr_path: Path
    prompt_path: Path
    command_path: Path
    started_at: str


class CodexLoopRunner:
    """Long-running Codex agent loop with participant-scoped gateway routing."""

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config

        self.client = ArenaClient(config.api_base, timeout=config.request_timeout)
        self.sandbox = RunnerSandbox(
            workspace=config.workspace,
            codex_binary=config.codex_binary,
            enable_landlock=config.llm_isolate,
        )

        self.workspace = self.sandbox.layout.workspace
        self.logs_dir = self.sandbox.layout.logs_dir
        self.runs_dir = self.workspace / "runs"
        self.runner_runs_dir = self.workspace / "runner_runs"
        self.state_path = self.workspace / "runner_state.json"
        self.runtime_path = self.workspace / "runtime_status.json"
        self.agent_exec_log_path = self.workspace / "agent_exec.log"
        self.agent_exec_summary_path = self.workspace / "agent_exec_summary.jsonl"
        self.final_metrics_path = self.workspace / "final_metrics.json"
        self.final_metrics_markdown_path = self.workspace / "final_metrics.md"
        self.final_participant_state_path = self.workspace / "final_participant_state.json"
        self.final_rankings_path = self.workspace / "final_rankings.json"

        self._state_lock = threading.Lock()
        self._state = self._load_state()
        if config.resume_session_id:
            self._state.session_id = config.resume_session_id.strip()

        self._gateway_credentials: Optional[GatewayCredentials] = None
        self._trace_lock = threading.Lock()
        self._active_trace: Optional[RunTrace] = None
        self._trace_agents: Dict[str, Dict[str, Any]] = {}
        self._trace_runtime: Dict[str, Any] = {}

    def run(self) -> int:
        """Run forever until participant stops running."""

        self._prepare_workspace()
        self._persist_state()

        backoff = max(0.1, float(self.config.retry_min_backoff_seconds))
        while True:
            try:
                status = self._safe_get_status()
            except ArenaAPIError as exc:
                self._state.last_error = f"status check failed: {exc}"
                self._persist_state()
                print(f"[codex-loop] status check failed: {exc}")
                time.sleep(backoff)
                backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)
                continue
            self._write_runtime_status(status=status, message="pre-run status check")
            if self._should_stop(status):
                reason = status.termination_reason or "participant_not_running"
                print(f"[codex-loop] participant stopped: {reason}")
                self._write_final_metrics_snapshot(
                    status=status,
                    stop_stage="pre_run_status_check",
                    stop_reason=reason,
                )
                return 0

            try:
                self._gateway_credentials = self.client.get_gateway_credentials(
                    self.config.competition_id,
                    self.config.participant_id,
                )
            except ArenaAPIError as exc:
                self._state.last_error = str(exc)
                self._persist_state()
                print(f"[codex-loop] failed to fetch gateway credentials: {exc}")
                time.sleep(backoff)
                backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)
                continue

            try:
                participant_state = self.client.get_participant_state(
                    self.config.competition_id,
                    self.config.participant_id,
                )
                selected_problem = self._resolve_problem_id(participant_state=participant_state)
            except ArenaAPIError as exc:
                self._state.last_error = str(exc)
                self._persist_state()
                print(f"[codex-loop] failed to resolve problem id: {exc}")
                time.sleep(backoff)
                backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)
                continue

            now = _utc_now()
            run_index = self._state.run_count + 1
            max_credit = self._derive_max_credit(status=status, participant_state=participant_state)
            budget_remaining = self._derive_budget_remaining(
                status=status,
                participant_state=participant_state,
                max_credit=max_credit,
            )
            strategy_profile = self._resolve_swarm_strategy_profile()
            use_resume = bool(self._state.session_id)
            command = self._build_codex_command(
                session_id=self._state.session_id if use_resume else None,
                gateway=self._gateway_credentials,
            )
            prompt = self._build_prompt(
                use_resume=use_resume,
                swarm_strategy_profile=strategy_profile,
                max_credit=max_credit,
            )

            env = self._build_runner_env(
                gateway=self._gateway_credentials,
                problem_id=selected_problem,
            )

            trace = self._start_run_trace(
                run_index=run_index,
                use_resume=use_resume,
                selected_problem=selected_problem,
                command=command,
                prompt=prompt,
                strategy_profile=strategy_profile,
                max_credit=max_credit,
                budget_remaining=budget_remaining,
            )
            stdout_path = trace.codex_events_path
            stderr_path = trace.codex_stderr_path

            self._state.last_started_at = now
            self._state.last_stdout_log = _safe_relative(stdout_path, self.workspace)
            self._state.last_stderr_log = _safe_relative(stderr_path, self.workspace)
            self._persist_state()

            print(
                "[codex-loop] launch",
                json.dumps(
                    {
                        "run": run_index,
                        "resume": use_resume,
                        "session_id": self._state.session_id,
                        "problem_id": selected_problem,
                    },
                    ensure_ascii=False,
                ),
            )
            self._append_trace_event(
                action="codex.launch",
                status="running",
                input_data={
                    "run_index": run_index,
                    "use_resume": use_resume,
                    "selected_problem_id": selected_problem,
                    "command": command,
                    "prompt_path": _safe_relative(trace.prompt_path, self.workspace),
                },
                output_data={"run_dir": _safe_relative(trace.run_dir, self.workspace)},
            )

            try:
                exit_code = self.sandbox.run_subprocess(
                    command=command,
                    cwd=self.workspace,
                    env=env,
                    stdin=prompt,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    on_stdout_line=self._capture_stdout_line,
                    on_stderr_line=self._capture_stderr_line,
                )
            except SandboxError as exc:
                self._state.last_error = f"sandbox error: {exc}"
                self._state.consecutive_failures += 1
                self._state.last_exit_code = 1
                self._state.last_finished_at = _utc_now()
                self._persist_state()
                print(f"[codex-loop] sandbox error: {exc}")
                self._append_trace_event(
                    action="codex.exec",
                    status="failed",
                    output_data={"error": str(exc), "category": "sandbox"},
                )
                self._finalize_active_trace(
                    exit_code=1,
                    use_resume=use_resume,
                    selected_problem=selected_problem,
                    command=command,
                    pre_status=status,
                    post_status=None,
                    error=self._state.last_error,
                )
                time.sleep(backoff)
                backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)
                continue
            except Exception as exc:  # pragma: no cover - defensive
                self._state.last_error = f"subprocess error: {exc}"
                self._state.consecutive_failures += 1
                self._state.last_exit_code = 1
                self._state.last_finished_at = _utc_now()
                self._persist_state()
                print(f"[codex-loop] subprocess error: {exc}")
                self._append_trace_event(
                    action="codex.exec",
                    status="failed",
                    output_data={"error": str(exc), "category": "subprocess"},
                )
                self._finalize_active_trace(
                    exit_code=1,
                    use_resume=use_resume,
                    selected_problem=selected_problem,
                    command=command,
                    pre_status=status,
                    post_status=None,
                    error=self._state.last_error,
                )
                time.sleep(backoff)
                backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)
                continue

            self._append_trace_event(
                action="codex.exec",
                status="completed" if int(exit_code) == 0 else "failed",
                output_data={"exit_code": int(exit_code)},
            )
            self._state.run_count += 1
            self._state.last_exit_code = int(exit_code)
            self._state.last_finished_at = _utc_now()

            if exit_code == 0:
                self._state.consecutive_failures = 0
                self._state.last_error = None
            else:
                self._state.consecutive_failures += 1
                self._state.last_error = f"codex exited with code {exit_code}"

            if (
                exit_code != 0
                and self._state.session_id
                and self._resume_session_missing(stderr_path)
            ):
                print(
                    "[codex-loop] resume session appears missing; clearing saved session id and restarting fresh"
                )
                self._append_trace_event(
                    action="session.resume",
                    status="failed",
                    output_data={"reason": "session_missing"},
                )
                self._state.session_id = None

            self._persist_state()

            try:
                post_status = self._safe_get_status()
            except ArenaAPIError as exc:
                self._state.last_error = f"post-run status check failed: {exc}"
                self._persist_state()
                print(f"[codex-loop] post-run status check failed: {exc}")
                self._append_trace_event(
                    action="status.check.post",
                    status="error",
                    output_data={"error": str(exc)},
                )
                self._finalize_active_trace(
                    exit_code=int(exit_code),
                    use_resume=use_resume,
                    selected_problem=selected_problem,
                    command=command,
                    pre_status=status,
                    post_status=None,
                    error=self._state.last_error,
                )
                time.sleep(backoff)
                backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)
                continue

            self._append_trace_event(
                action="status.check.post",
                status="ok",
                output_data=self._status_to_payload(post_status),
            )
            self._write_runtime_status(status=post_status, message="post-run status check")
            self._finalize_active_trace(
                exit_code=int(exit_code),
                use_resume=use_resume,
                selected_problem=selected_problem,
                command=command,
                pre_status=status,
                post_status=post_status,
                error=(self._state.last_error if int(exit_code) != 0 else None),
            )
            if self._should_stop(post_status):
                reason = post_status.termination_reason or "participant_not_running"
                print(f"[codex-loop] participant stopped after run: {reason}")
                self._write_final_metrics_snapshot(
                    status=post_status,
                    stop_stage="post_run_status_check",
                    stop_reason=reason,
                )
                return 0

            if exit_code == 0:
                backoff = max(0.1, float(self.config.retry_min_backoff_seconds))
                sleep_s = max(0.0, float(self.config.poll_interval_seconds))
                if sleep_s > 0:
                    time.sleep(sleep_s)
                continue

            time.sleep(backoff)
            backoff = min(self.config.retry_max_backoff_seconds, backoff * 2)

    def _prepare_workspace(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.runner_runs_dir.mkdir(parents=True, exist_ok=True)
        self.sandbox.seed_codex_home()

        if self.config.sync_templates:
            selected_template = Path(self.config.template_dir).expanduser().resolve()
            base_template = self._default_template_dir()
            if selected_template != base_template and base_template.exists():
                self._sync_templates(
                    template_dir=base_template,
                    overwrite=False,
                )
                # Overlay strategy folder content (e.g., AGENTS.md) onto the base template.
                self._sync_templates(
                    template_dir=selected_template,
                    overwrite=True,
                )
            else:
                self._sync_templates(
                    template_dir=selected_template,
                    overwrite=self.config.force_template_overwrite,
                )

        context_md = self._build_context_markdown()
        (self.workspace / "competition_context.md").write_text(context_md, encoding="utf-8")

    @staticmethod
    def _default_template_dir() -> Path:
        return Path(__file__).resolve().parents[2] / "config" / "codex_agent" / "usacoarena"

    def _sync_templates(self, *, template_dir: Path, overwrite: bool) -> None:
        source_root = Path(template_dir).expanduser().resolve()
        if not source_root.exists() or not source_root.is_dir():
            raise RuntimeError(f"template_dir not found: {source_root}")

        for root, dirnames, filenames in os.walk(source_root):
            rel_root = Path(root).resolve().relative_to(source_root)
            if "__pycache__" in dirnames:
                dirnames.remove("__pycache__")

            target_root = (self.workspace / rel_root).resolve()
            target_root.mkdir(parents=True, exist_ok=True)

            for filename in filenames:
                src = Path(root) / filename
                dst = target_root / filename
                if dst.exists() and not overwrite:
                    continue
                shutil.copy2(src, dst)

    def _resolve_problem_id(self, *, participant_state: Optional[Dict[str, Any]] = None) -> str:
        if self.config.explicit_problem_id:
            value = self.config.explicit_problem_id.strip()
            if value:
                self._state.selected_problem_id = value
                self._persist_state()
                return value

        if participant_state is None:
            participant_state = self.client.get_participant_state(
                self.config.competition_id,
                self.config.participant_id,
            )
        solved_ids = _extract_solved_problem_ids(participant_state.get("solved_problems"))

        rows = self.client.list_problems(self.config.competition_id)
        for item in rows:
            problem_id = str(item.get("id") or "").strip()
            if problem_id and problem_id not in solved_ids:
                self._state.selected_problem_id = problem_id
                self._persist_state()
                return problem_id

        if rows:
            fallback = str(rows[0].get("id") or "").strip()
            if fallback:
                self._state.selected_problem_id = fallback
                self._persist_state()
                return fallback

        if self._state.selected_problem_id:
            return self._state.selected_problem_id

        raise ArenaAPIError("unable to resolve any problem id for this participant")

    def _derive_max_credit(self, *, status: ParticipantStatus, participant_state: Dict[str, Any]) -> float:
        candidates: List[float] = []
        raw_limit = participant_state.get("limit_tokens")
        if raw_limit is not None:
            try:
                candidates.append(float(raw_limit))
            except (TypeError, ValueError):
                pass
        raw_consumed = participant_state.get("consumed_credit")
        if raw_consumed is not None:
            try:
                consumed_credit = max(0.0, float(raw_consumed))
                candidates.append(consumed_credit + max(0.0, float(status.remaining_tokens)))
            except (TypeError, ValueError):
                pass
        candidates.append(max(0.0, float(status.remaining_tokens)))
        positive = [value for value in candidates if value > 0]
        if positive:
            return max(positive)
        return max(1.0, float(status.remaining_tokens or 1))

    def _derive_budget_remaining(
        self,
        *,
        status: ParticipantStatus,
        participant_state: Dict[str, Any],
        max_credit: float,
    ) -> float:
        consumed_credit = 0.0
        raw_consumed = participant_state.get("consumed_credit")
        if raw_consumed is not None:
            try:
                consumed_credit = max(0.0, float(raw_consumed))
            except (TypeError, ValueError):
                consumed_credit = 0.0
        via_consumed = max(0.0, max_credit - consumed_credit)
        via_status = max(0.0, float(status.remaining_tokens))
        if via_status > 0:
            return min(via_status, via_consumed) if via_consumed > 0 else via_status
        return via_consumed

    def _resolve_swarm_strategy_profile(self) -> str:
        from_agents = self._read_swarm_strategy_profile_from_agents()
        if from_agents:
            return from_agents

        template_key = Path(self.config.template_dir).expanduser().name.strip().lower()
        if template_key in _STRATEGY_PROFILE_TEXTS:
            return _STRATEGY_PROFILE_TEXTS[template_key]
        for key, value in _STRATEGY_PROFILE_TEXTS.items():
            if key in template_key:
                return value
        return _STRATEGY_PROFILE_TEXTS["usacoarena"]

    def _read_swarm_strategy_profile_from_agents(self) -> Optional[str]:
        candidates: List[Path] = [
            self.workspace / "AGENTS.md",
            Path(self.config.template_dir).expanduser() / "AGENTS.md",
        ]
        seen: set[str] = set()
        for path in candidates:
            try:
                resolved = str(path.resolve())
            except Exception:
                resolved = str(path)
            if resolved in seen:
                continue
            seen.add(resolved)

            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            profile = self._extract_swarm_strategy_profile(content)
            if profile:
                return profile
        return None

    @staticmethod
    def _extract_swarm_strategy_profile(content: str) -> Optional[str]:
        alias_to_key = {
            "speedy spendthrift": "swarm_fast_7",
            "极速爆破流": "swarm_fast_7",
            "cost-aware strategist": "swarm_balanced_4",
            "动态平衡流": "swarm_balanced_4",
            "frugal perfectionist": "swarm_lean_2",
            "省吃俭用流": "swarm_lean_2",
        }
        for raw in str(content or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            lower = line.lower()
            if line.startswith("SWARM_STRATEGY_PROFILE:"):
                value = line.split(":", 1)[1].strip()
                if value:
                    return value
            if lower.startswith("# swarm strategy profile:"):
                label = line.split(":", 1)[1].strip()
                if label:
                    lowered_label = label.lower()
                    for alias, key in alias_to_key.items():
                        if alias in lowered_label:
                            return _STRATEGY_PROFILE_TEXTS[key]
                    return label
        return None

    def _build_runner_env(self, *, gateway: GatewayCredentials, problem_id: str) -> Dict[str, str]:
        env = self.sandbox.build_env(os.environ)

        env["USACOARENA_BASE_URL"] = self.config.api_base.rstrip("/")
        env["USACOARENA_COMPETITION_ID"] = self.config.competition_id
        env["USACOARENA_PARTICIPANT_ID"] = self.config.participant_id
        env["USACOARENA_PROBLEM_ID"] = problem_id
        env["USACOARENA_LANGUAGE"] = self.config.language

        env["OPENAI_API_BASE"] = gateway.openai_api_base
        env["OPENAI_BASE_URL"] = gateway.openai_api_base
        env["OPENAI_API_KEY"] = gateway.openai_api_key

        return env

    def _build_codex_command(self, *, session_id: Optional[str], gateway: GatewayCredentials) -> List[str]:
        gateway_base = gateway.openai_api_base
        provider_name = "usacoarena_gateway"

        command: List[str]
        if session_id:
            command = [self.config.codex_binary, "exec", "resume"]
        else:
            command = [self.config.codex_binary, "exec"]

        command.extend(
            [
                "-c",
                f"model_provider={_toml_string(provider_name)}",
                "-c",
                f"model_providers.{provider_name}.name={_toml_string('USACOArena Gateway')}",
                "-c",
                f"model_providers.{provider_name}.base_url={_toml_string(gateway_base)}",
                "-c",
                f"model_providers.{provider_name}.env_key={_toml_string('OPENAI_API_KEY')}",
                "-c",
                f"model_providers.{provider_name}.requires_openai_auth=false",
                "-c",
                "preferred_auth_method=\"apikey\"",
                "-c",
                "mcp_servers={}",
            ]
        )

        for item in self.config.extra_codex_configs:
            token = str(item or "").strip()
            if token:
                command.extend(["-c", token])

        if self.config.model:
            command.extend(["-m", self.config.model])

        command.extend(["--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--json"])

        if session_id:
            command.extend([session_id, "-"])
        else:
            command.extend(["-C", str(self.workspace), "-"])

        return command

    def _build_prompt(
        self,
        *,
        use_resume: bool,
        swarm_strategy_profile: str,
        max_credit: float,
    ) -> str:
        selected_problem = self._state.selected_problem_id or "(auto)"
        mode_line = "Continue the existing Codex session." if use_resume else "Start a new Codex session."
        max_credit_text = str(int(round(max(0.0, float(max_credit)))))
        strategy_text = swarm_strategy_profile.strip() or _STRATEGY_PROFILE_TEXTS["usacoarena"]

        return "\n".join(
            [
                mode_line,
                "",
                "[System Configuration]",
                "You are a highly capable, autonomous agent swarm participating in an ICPC-style coding competition (USACOArena).",
                "Your ultimate goal is to solve the competitive programming task, but you are strictly governed by economic realities: Absolute Delivery Time, Token Expenditure, and Evaluation Overhead.",
                "",
                "Your current swarm strategy profile is:",
                f">>> {strategy_text} <<<",
                "",
                "[Swarm Roles & Workflow]",
                "Organize your swarm using the following roles:",
                "1. Lead_Manager: Decomposes the task, assigns sub-tasks, and explicitly monitors the global credit budget and wall-clock time.",
                "2. Algo_Thinker: Drafts mathematical and algorithmic approaches.",
                "3. Swarm_Coder: Implements the algorithm in code. (Multiple can be spawned in parallel).",
                "4. Local_Evaluator: Writes local edge-case tests and runs the evaluation sandbox.",
                "",
                "[Economic Feedback & Constraints]",
                f"You are constrained by a unified \"Credit Budget\" of {max_credit_text}.",
                "- Every generated token (thinking, coding, or communication) costs credit.",
                "- Every Local_Evaluator sandbox run incurs an explicit test overhead cost.",
                "- The Lead_Manager MUST evaluate the remaining budget before spawning new agents or ordering re-evaluations.",
                "",
                "[Trace and Profiling Directives]",
                "Execute this task using the agent swarm, and keep a granular trace of the entire economic and execution process under `runs/<timestamp>/`. We strictly require the following files for post-run profiling:",
                "IMPORTANT: `runner_runs/` is reserved for system-level runner traces. Do not write swarm artifacts there.",
                "",
                "- `events.jsonl`: Every state transition. Must include: `timestamp`, `agent_id`, `role`, `action`, `status`, `input`, `output`, and critically, a breakdown of tokens used: `tokens_thinking`, `tokens_coding`, and `tokens_communication` (overhead).",
                "- `budget_log.csv`: A ledger recording `timestamp`, `event_type` (e.g., LLM_Call, Local_Test), `credit_deducted`, `budget_remaining`, and `wall_clock_elapsed_ms`.",
                "- `agents.csv`: Each agent’s `agent_id`, `role`, `spawn_time`, `end_time`, and `total_token_cost`.",
                "- `evaluation_trace.json`: Logs of local test executions, pass/fail results, latency, and the specific cost incurred per test.",
                "- `artifacts_manifest.json`: File paths and hashes for all generated code and test files.",
                "- `run_summary.md`: A final executive summary. MUST calculate and report: Total Absolute Time (ms), Total Token Cost, Communication Overhead Ratio (communication tokens / total tokens), Total Evaluation Runs, and the final USACOArena submission decision.",
                "",
                "[Execution Protocol]",
                "1. First, output the task decomposition plan and the initial agent roster.",
                "2. Execute the task according to your strategy profile, allowing parallel agent execution.",
                "3. During execution, the Lead_Manager must continuously report budget status and agent lifecycle events.",
                "4. Finish by writing all required trace files and the unified summary.",
                "",
                "[Operational Context]",
                f"Competition ID: {self.config.competition_id}",
                f"Participant ID: {self.config.participant_id}",
                f"Target problem (if fixed): {selected_problem}",
                "",
                "Before acting, read these local files:",
                "1. AGENTS.md",
                "2. problem.md",
                "3. competition_context.md",
                "",
                "Use local HTTP helper script for all competition interactions:",
                "- `python arena_cli.py status`",
                "- `python arena_cli.py state`",
                "- `python arena_cli.py list-problems`",
                "- `python arena_cli.py show-problem --problem-id <id>`",
                "- `python arena_cli.py submit --problem-id <id> --code-file main.cpp --language cpp`",
                "- `python arena_cli.py rankings`",
                "- `python arena_cli.py quit --reason \"Voluntarily Quit Competition\"`",
                "",
                "Stop only if participant is terminated/out_of_tokens or if you intentionally quit via API.",
                "",
            ]
        )

    def _capture_stdout_line(self, line: str) -> None:
        text = str(line or "")
        session_id = self._extract_session_id_from_stdout(text)
        if session_id:
            self._record_session_id(session_id)

        payload = self._parse_json_line(text)
        if payload is None:
            stripped = text.strip()
            if stripped:
                self._append_trace_event(
                    action="codex.stdout.text",
                    status="stream",
                    output_data={"line": stripped[:4000]},
                    agent_id="codex",
                )
            return

        action = str(payload.get("type") or "codex.event").strip() or "codex.event"
        agent_id = self._extract_agent_id(payload) or "codex"
        role = self._extract_agent_role(payload)
        self._touch_trace_agent(agent_id=agent_id, role=role or "worker", status="running")
        event_status = "error" if self._payload_is_error(payload) else "ok"
        self._append_trace_event(
            action=action,
            status=event_status,
            output_data=payload,
            agent_id=agent_id,
        )

    def _capture_stderr_line(self, line: str) -> None:
        text = str(line or "")
        lowered = text.lower()
        if "session id" in lowered:
            matched = _SESSION_ID_REGEX.search(text)
            if matched:
                self._record_session_id(matched.group(1))

        status = "error" if any(token in lowered for token in ("error", "exception", "failed")) else "stream"
        stripped = text.strip()
        if stripped:
            self._append_trace_event(
                action="codex.stderr",
                status=status,
                output_data={"line": stripped[:4000]},
                agent_id="codex",
            )

    def _extract_session_id_from_stdout(self, line: str) -> Optional[str]:
        text = str(line or "").strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        event_type = str(payload.get("type") or "")
        if event_type == "thread.started":
            candidate = payload.get("thread_id")
            if isinstance(candidate, str):
                return self._normalize_session_id(candidate)

        if event_type == "session_meta":
            inner = payload.get("payload")
            if isinstance(inner, dict):
                candidate = inner.get("id")
                if isinstance(candidate, str):
                    return self._normalize_session_id(candidate)

        return None

    def _normalize_session_id(self, value: str) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        matched = _SESSION_ID_REGEX.search(text)
        if matched:
            return matched.group(1)
        return None

    def _record_session_id(self, session_id: str) -> None:
        normalized = self._normalize_session_id(session_id)
        if not normalized:
            return
        with self._state_lock:
            if self._state.session_id == normalized:
                return
            self._state.session_id = normalized
            self._persist_state_unlocked()
        self._touch_trace_agent(
            agent_id=normalized,
            role="primary_solver",
            status="running",
        )
        print(f"[codex-loop] captured session_id={normalized}")

    @staticmethod
    def _parse_json_line(line: str) -> Optional[Dict[str, Any]]:
        text = str(line or "").strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except Exception:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _extract_agent_id(payload: Dict[str, Any]) -> Optional[str]:
        direct = payload.get("agent_id")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        if str(payload.get("type") or "") == "thread.started":
            thread_id = payload.get("thread_id")
            if isinstance(thread_id, str) and thread_id.strip():
                return thread_id.strip()
        nested = payload.get("agent")
        if isinstance(nested, dict):
            nested_id = nested.get("id")
            if isinstance(nested_id, str) and nested_id.strip():
                return nested_id.strip()
        inner = payload.get("payload")
        if isinstance(inner, dict):
            nested = inner.get("agent_id")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return None

    @staticmethod
    def _extract_agent_role(payload: Dict[str, Any]) -> Optional[str]:
        direct = payload.get("role")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        nested = payload.get("agent")
        if isinstance(nested, dict):
            nested_role = nested.get("role")
            if isinstance(nested_role, str) and nested_role.strip():
                return nested_role.strip()
        return None

    @staticmethod
    def _payload_is_error(payload: Dict[str, Any]) -> bool:
        event_type = str(payload.get("type") or "").lower()
        if "error" in event_type or "failed" in event_type:
            return True
        for key in ("error", "exception"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, dict) and value:
                return True
        return False

    def _touch_trace_agent(
        self,
        *,
        agent_id: str,
        role: str = "worker",
        status: str = "running",
        timestamp: Optional[str] = None,
    ) -> None:
        normalized_id = str(agent_id or "").strip()
        if not normalized_id:
            return
        ts = timestamp or _utc_now()
        with self._trace_lock:
            if self._active_trace is None:
                return
            row = self._trace_agents.get(normalized_id)
            if row is None:
                row = {
                    "agent_id": normalized_id,
                    "role": role or "worker",
                    "spawn_time": ts,
                    "last_seen": ts,
                    "end_time": "",
                    "status": status or "running",
                    "event_count": 0,
                    "error_count": 0,
                    "total_token_cost": 0.0,
                }
                self._trace_agents[normalized_id] = row
                return
            if role and (not row.get("role") or row.get("role") in ("worker", "unknown")):
                row["role"] = role
            row["last_seen"] = ts
            if status:
                row["status"] = status
            if status in {"completed", "failed", "terminated"}:
                row["end_time"] = ts

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None:
            return None
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except Exception:
            return str(value)

    def _append_trace_event(
        self,
        *,
        action: str,
        status: str,
        agent_id: str = "runner",
        input_data: Any = None,
        output_data: Any = None,
    ) -> None:
        ts = _utc_now()
        normalized_agent_id = str(agent_id or "runner").strip() or "runner"
        normalized_action = str(action or "event").strip() or "event"
        normalized_status = str(status or "unknown").strip() or "unknown"
        tokens_total = self._extract_total_tokens(output_data)
        tokens_thinking, tokens_coding, tokens_communication = self._split_tokens_by_category(
            action=normalized_action,
            payload=output_data,
            total=tokens_total,
        )
        budget_entries: List[Dict[str, Any]] = []
        local_eval_entry: Optional[Dict[str, Any]] = None

        with self._trace_lock:
            trace = self._active_trace
            if trace is None:
                return
            runtime = self._trace_runtime if isinstance(self._trace_runtime, dict) else {}
            row = self._trace_agents.get(normalized_agent_id)
            if row is None:
                row = {
                    "agent_id": normalized_agent_id,
                    "role": "worker",
                    "spawn_time": ts,
                    "last_seen": ts,
                    "end_time": "",
                    "status": "running",
                    "event_count": 0,
                    "error_count": 0,
                    "total_token_cost": 0.0,
                }
                self._trace_agents[normalized_agent_id] = row
            row["last_seen"] = ts
            row["event_count"] = int(row.get("event_count", 0)) + 1
            row["total_token_cost"] = float(row.get("total_token_cost") or 0.0) + float(tokens_total)
            if normalized_status in {"error", "failed"}:
                row["error_count"] = int(row.get("error_count", 0)) + 1
                row["status"] = "failed"
                row["end_time"] = ts
            elif normalized_status in {"completed", "done", "terminated"}:
                row["status"] = "completed"
                row["end_time"] = ts
            elif row.get("status") not in {"failed", "completed"}:
                row["status"] = "running"
            role_value = str(row.get("role") or "worker")

            elapsed_ms = self._trace_elapsed_ms(runtime=runtime)
            budget_remaining = float(runtime.get("budget_remaining") or 0.0)
            if tokens_total > 0:
                runtime["tokens_total"] = float(runtime.get("tokens_total") or 0.0) + float(tokens_total)
                runtime["tokens_thinking"] = float(runtime.get("tokens_thinking") or 0.0) + float(tokens_thinking)
                runtime["tokens_coding"] = float(runtime.get("tokens_coding") or 0.0) + float(tokens_coding)
                runtime["tokens_communication"] = float(runtime.get("tokens_communication") or 0.0) + float(
                    tokens_communication
                )
                budget_remaining = max(0.0, budget_remaining - float(tokens_total))
                runtime["budget_remaining"] = budget_remaining
                budget_entries.append(
                    {
                        "timestamp": ts,
                        "event_type": "LLM_Call",
                        "credit_deducted": float(tokens_total),
                        "budget_remaining": budget_remaining,
                        "wall_clock_elapsed_ms": elapsed_ms,
                    }
                )

            local_eval_entry = self._infer_local_eval_event(
                action=normalized_action,
                input_data=input_data,
                output_data=output_data,
                elapsed_ms=elapsed_ms,
            )
            if local_eval_entry is not None:
                runtime["evaluation_runs"] = int(runtime.get("evaluation_runs") or 0) + 1
                runtime["evaluation_overhead_total"] = float(runtime.get("evaluation_overhead_total") or 0.0) + float(
                    local_eval_entry["cost_credit"]
                )
                budget_remaining = max(0.0, budget_remaining - float(local_eval_entry["cost_credit"]))
                runtime["budget_remaining"] = budget_remaining
                local_eval_entry["index"] = int(runtime["evaluation_runs"])
                local_eval_entry["budget_remaining"] = budget_remaining
                eval_trace = runtime.get("evaluation_trace")
                if isinstance(eval_trace, list):
                    eval_trace.append(local_eval_entry)
                budget_entries.append(
                    {
                        "timestamp": ts,
                        "event_type": "Local_Test",
                        "credit_deducted": float(local_eval_entry["cost_credit"]),
                        "budget_remaining": budget_remaining,
                        "wall_clock_elapsed_ms": elapsed_ms,
                    }
                )

            events_path = trace.events_path
            budget_path = trace.budget_log_path
            self._trace_runtime = runtime

        event = {
            "timestamp": ts,
            "agent_id": normalized_agent_id,
            "role": role_value,
            "action": normalized_action,
            "status": normalized_status,
            "input": self._json_safe(input_data),
            "output": self._json_safe(output_data),
            "tokens_thinking": int(round(tokens_thinking)),
            "tokens_coding": int(round(tokens_coding)),
            "tokens_communication": int(round(tokens_communication)),
        }
        if local_eval_entry is not None:
            event["evaluation"] = self._json_safe(local_eval_entry)

        self._safe_trace_write(events_path, json.dumps(event, ensure_ascii=False) + "\n")
        for entry in budget_entries:
            self._append_budget_log_row(budget_path, entry)

    def _initialize_budget_log(self, trace: RunTrace) -> None:
        trace.budget_log_path.parent.mkdir(parents=True, exist_ok=True)
        with trace.budget_log_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "timestamp",
                    "event_type",
                    "credit_deducted",
                    "budget_remaining",
                    "wall_clock_elapsed_ms",
                ],
            )
            writer.writeheader()
        runtime = self._trace_runtime if isinstance(self._trace_runtime, dict) else {}
        self._append_budget_log_row(
            trace.budget_log_path,
            {
                "timestamp": trace.started_at,
                "event_type": "RunStart",
                "credit_deducted": 0.0,
                "budget_remaining": float(runtime.get("budget_remaining") or 0.0),
                "wall_clock_elapsed_ms": 0,
            },
        )

    @staticmethod
    def _append_budget_log_row(path: Path, row: Dict[str, Any]) -> None:
        try:
            with path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "timestamp",
                        "event_type",
                        "credit_deducted",
                        "budget_remaining",
                        "wall_clock_elapsed_ms",
                    ],
                )
                writer.writerow(
                    {
                        "timestamp": row.get("timestamp"),
                        "event_type": row.get("event_type"),
                        "credit_deducted": f"{float(row.get('credit_deducted') or 0.0):.6f}",
                        "budget_remaining": f"{float(row.get('budget_remaining') or 0.0):.6f}",
                        "wall_clock_elapsed_ms": int(row.get("wall_clock_elapsed_ms") or 0),
                    }
                )
        except OSError:
            return

    @staticmethod
    def _trace_elapsed_ms(*, runtime: Dict[str, Any]) -> int:
        start = runtime.get("start_perf_counter")
        if not isinstance(start, (int, float)):
            return 0
        try:
            elapsed = (time.perf_counter() - float(start)) * 1000.0
        except Exception:
            return 0
        return max(0, int(round(elapsed)))

    @staticmethod
    def _extract_total_tokens(payload: Any) -> float:
        if not isinstance(payload, dict):
            return 0.0

        usage = payload.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, (int, float)):
                return max(0.0, float(total))
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            if isinstance(prompt, (int, float)) or isinstance(completion, (int, float)):
                return max(0.0, float(prompt or 0) + float(completion or 0))
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if isinstance(input_tokens, (int, float)) or isinstance(output_tokens, (int, float)):
                return max(0.0, float(input_tokens or 0) + float(output_tokens or 0))

        for key in ("tokens_used", "total_tokens", "token_cost"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return max(0.0, float(value))

        nested = payload.get("payload")
        if isinstance(nested, dict):
            return CodexLoopRunner._extract_total_tokens(nested)

        return 0.0

    @staticmethod
    def _split_tokens_by_category(*, action: str, payload: Any, total: float) -> tuple[float, float, float]:
        total_tokens = max(0.0, float(total))
        if total_tokens <= 0:
            return 0.0, 0.0, 0.0

        marker = f"{action} {payload}".lower()
        coding_hints = ("code", "patch", "write", "edit", "compile", "submit", "solution", "coder")
        thinking_hints = ("plan", "analysis", "reason", "think", "decompose", "algo")

        if any(token in marker for token in coding_hints):
            return 0.0, total_tokens, 0.0
        if any(token in marker for token in thinking_hints):
            return total_tokens, 0.0, 0.0
        return 0.0, 0.0, total_tokens

    def _infer_local_eval_event(
        self,
        *,
        action: str,
        input_data: Any,
        output_data: Any,
        elapsed_ms: int,
    ) -> Optional[Dict[str, Any]]:
        marker = f"{action} {input_data} {output_data}".lower()
        eval_markers = (
            "local_evaluator",
            "local test",
            "arena_cli.py test",
            "test_code",
            "pytest",
            "unit test",
            "sandbox",
        )
        if not any(token in marker for token in eval_markers):
            return None

        result = "unknown"
        if any(token in marker for token in ("pass", "passed", "success")):
            result = "pass"
        elif any(token in marker for token in ("fail", "failed", "error", "exception")):
            result = "fail"

        return {
            "timestamp": _utc_now(),
            "action": action,
            "result": result,
            "latency_ms": max(0, int(elapsed_ms)),
            "cost_credit": float(_DEFAULT_LOCAL_EVAL_OVERHEAD_CREDIT),
        }

    @staticmethod
    def _status_to_payload(status: ParticipantStatus) -> Dict[str, Any]:
        return {
            "is_running": bool(status.is_running),
            "termination_reason": status.termination_reason,
            "remaining_tokens": int(status.remaining_tokens),
            "score": float(status.score),
            "elapsed_time_seconds": int(status.elapsed_time_seconds),
            "delivery_time_multiplier": float(status.delivery_time_multiplier),
            "delivery_time_settled": bool(status.delivery_time_settled),
            "delivery_time_credit": float(status.delivery_time_credit),
        }

    def _start_run_trace(
        self,
        *,
        run_index: int,
        use_resume: bool,
        selected_problem: str,
        command: List[str],
        prompt: str,
        strategy_profile: str,
        max_credit: float,
        budget_remaining: float,
    ) -> RunTrace:
        started_at = _utc_now()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_dir = self.runner_runs_dir / stamp
        suffix = 1
        while run_dir.exists():
            run_dir = self.runner_runs_dir / f"{stamp}_{suffix:02d}"
            suffix += 1
        run_dir.mkdir(parents=True, exist_ok=True)

        run_tag = f"run_{run_index:05d}_{run_dir.name}"
        trace = RunTrace(
            run_index=run_index,
            run_tag=run_tag,
            run_dir=run_dir,
            events_path=run_dir / "events.jsonl",
            budget_log_path=run_dir / "budget_log.csv",
            agents_path=run_dir / "agents.csv",
            evaluation_trace_path=run_dir / "evaluation_trace.json",
            manifest_path=run_dir / "artifacts_manifest.json",
            summary_path=run_dir / "run_summary.md",
            agent_exec_path=run_dir / "agent_exec.log",
            tool_stats_path=run_dir / "tool_stats.json",
            session_meta_path=run_dir / "session_meta.json",
            codex_events_path=run_dir / "codex_events.jsonl",
            codex_stderr_path=run_dir / "codex_stderr.log",
            prompt_path=run_dir / "start_prompt.txt",
            command_path=run_dir / "command.json",
            started_at=started_at,
        )

        trace.prompt_path.write_text(prompt, encoding="utf-8")
        trace.command_path.write_text(
            json.dumps(
                {
                    "run_index": run_index,
                    "run_tag": run_tag,
                    "command": command,
                    "use_resume": use_resume,
                    "selected_problem_id": selected_problem,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        with self._trace_lock:
            self._active_trace = trace
            self._trace_agents = {}
            self._trace_runtime = {
                "max_credit": float(max(0.0, max_credit)),
                "budget_remaining": float(max(0.0, budget_remaining)),
                "start_perf_counter": time.perf_counter(),
                "strategy_profile": str(strategy_profile or ""),
                "tokens_total": 0.0,
                "tokens_thinking": 0.0,
                "tokens_coding": 0.0,
                "tokens_communication": 0.0,
                "evaluation_runs": 0,
                "evaluation_trace": [],
                "evaluation_overhead_total": 0.0,
            }

        self._initialize_budget_log(trace)

        self._touch_trace_agent(agent_id="runner", role="orchestrator", status="running", timestamp=started_at)
        if self._state.session_id:
            self._touch_trace_agent(
                agent_id=self._state.session_id,
                role="primary_solver",
                status="running",
                timestamp=started_at,
            )
        self._append_trace_event(
            action="run.started",
            status="running",
            input_data={
                "run_index": run_index,
                "use_resume": use_resume,
                "selected_problem_id": selected_problem,
                "strategy_profile": strategy_profile,
                "max_credit": max_credit,
                "budget_remaining": budget_remaining,
            },
            output_data={"run_dir": _safe_relative(run_dir, self.workspace)},
        )
        return trace

    def _finalize_active_trace(
        self,
        *,
        exit_code: int,
        use_resume: bool,
        selected_problem: str,
        command: List[str],
        pre_status: ParticipantStatus,
        post_status: Optional[ParticipantStatus],
        error: Optional[str],
    ) -> None:
        final_status = "completed" if int(exit_code) == 0 else "failed"
        self._append_trace_event(
            action="run.finished",
            status=final_status,
            output_data={
                "exit_code": int(exit_code),
                "error": error,
                "post_status_available": post_status is not None,
            },
        )

        with self._trace_lock:
            trace = self._active_trace
            if trace is None:
                return
            agents_snapshot = {
                key: dict(value) for key, value in self._trace_agents.items()
            }
            runtime_snapshot = dict(self._trace_runtime) if isinstance(self._trace_runtime, dict) else {}
            self._active_trace = None
            self._trace_agents = {}
            self._trace_runtime = {}

        ended_at = _utc_now()
        self._append_budget_log_row(
            trace.budget_log_path,
            {
                "timestamp": ended_at,
                "event_type": "RunEnd",
                "credit_deducted": 0.0,
                "budget_remaining": float(runtime_snapshot.get("budget_remaining") or 0.0),
                "wall_clock_elapsed_ms": self._trace_elapsed_ms(runtime=runtime_snapshot),
            },
        )
        try:
            self._write_agents_csv(
                trace=trace,
                agents_snapshot=agents_snapshot,
                ended_at=ended_at,
                final_status=final_status,
            )
            self._write_session_metrics(
                trace=trace,
                exit_code=int(exit_code),
                runtime_snapshot=runtime_snapshot,
                error=error,
            )
            self._write_run_summary(
                trace=trace,
                started_at=trace.started_at,
                ended_at=ended_at,
                exit_code=int(exit_code),
                use_resume=use_resume,
                selected_problem=selected_problem,
                pre_status=pre_status,
                post_status=post_status,
                error=error,
                command=command,
                agent_count=len(agents_snapshot),
                runtime_snapshot=runtime_snapshot,
            )
            self._write_agent_exec_log(
                trace=trace,
                started_at=trace.started_at,
                ended_at=ended_at,
                exit_code=int(exit_code),
                use_resume=use_resume,
                selected_problem=selected_problem,
                error=error,
                command=command,
                pre_status=pre_status,
                post_status=post_status,
            )
            self._write_artifact_manifest(trace=trace)
            self._write_evaluation_trace(trace=trace, runtime_snapshot=runtime_snapshot)
            self._append_workspace_exec_log(
                trace=trace,
                ended_at=ended_at,
                exit_code=int(exit_code),
                selected_problem=selected_problem,
                error=error,
                runtime_snapshot=runtime_snapshot,
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[codex-loop] trace finalize error: {exc}")

    def _write_agents_csv(
        self,
        *,
        trace: RunTrace,
        agents_snapshot: Dict[str, Dict[str, Any]],
        ended_at: str,
        final_status: str,
    ) -> None:
        if not agents_snapshot:
            agents_snapshot = {
                "runner": {
                    "agent_id": "runner",
                    "role": "orchestrator",
                    "spawn_time": trace.started_at,
                    "last_seen": ended_at,
                    "end_time": ended_at,
                    "status": final_status,
                    "event_count": 0,
                    "error_count": 0,
                    "total_token_cost": 0.0,
                }
            }

        rows: List[Dict[str, Any]] = []
        for agent_id in sorted(agents_snapshot):
            row = dict(agents_snapshot[agent_id])
            role = str(row.get("role") or "worker")
            status = str(row.get("status") or "running")
            if status == "running":
                status = "completed" if final_status == "completed" else "failed"
            rows.append(
                {
                    "agent_id": str(row.get("agent_id") or agent_id),
                    "role": role,
                    "spawn_time": str(row.get("spawn_time") or trace.started_at),
                    "end_time": str(row.get("end_time") or row.get("last_seen") or ended_at),
                    "total_token_cost": float(row.get("total_token_cost") or 0.0),
                    "status": status,
                    "event_count": int(row.get("event_count") or 0),
                    "error_count": int(row.get("error_count") or 0),
                }
            )

        trace.agents_path.parent.mkdir(parents=True, exist_ok=True)
        with trace.agents_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "agent_id",
                    "role",
                    "spawn_time",
                    "end_time",
                    "total_token_cost",
                    "status",
                    "event_count",
                    "error_count",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_run_summary(
        self,
        *,
        trace: RunTrace,
        started_at: str,
        ended_at: str,
        exit_code: int,
        use_resume: bool,
        selected_problem: str,
        pre_status: ParticipantStatus,
        post_status: Optional[ParticipantStatus],
        error: Optional[str],
        command: List[str],
        agent_count: int,
        runtime_snapshot: Dict[str, Any],
    ) -> None:
        status_line = "failed" if exit_code != 0 else "completed"
        total_time_ms = self._trace_elapsed_ms(runtime=runtime_snapshot)
        total_token_cost = float(runtime_snapshot.get("tokens_total") or 0.0)
        communication_tokens = float(runtime_snapshot.get("tokens_communication") or 0.0)
        communication_ratio = 0.0
        if total_token_cost > 0:
            communication_ratio = communication_tokens / total_token_cost
        evaluation_runs = int(runtime_snapshot.get("evaluation_runs") or 0)
        final_submission_decision = self._derive_submission_decision(
            post_status=post_status,
            exit_code=exit_code,
            error=error,
        )
        reproduction = [
            "python scripts/run_codex_loop_agent.py",
            f"--api-base {self.config.api_base}",
            f"--competition-id {self.config.competition_id}",
            f"--participant-id {self.config.participant_id}",
            f"--template-dir {self.config.template_dir}",
            f"--model {self.config.model}",
            f"--language {self.config.language}",
        ]
        if self.config.explicit_problem_id:
            reproduction.append(f"--problem-id {self.config.explicit_problem_id}")
        lines = [
            f"# Run Summary: {trace.run_tag}",
            "",
            f"- started_at: {started_at}",
            f"- ended_at: {ended_at}",
            f"- exit_code: {exit_code}",
            f"- final_status: {status_line}",
            f"- use_resume: {use_resume}",
            f"- selected_problem_id: {selected_problem}",
            f"- traced_agents: {max(1, agent_count)}",
            f"- retries_so_far: {self._state.consecutive_failures}",
            f"- strategy_profile: {runtime_snapshot.get('strategy_profile') or self._resolve_swarm_strategy_profile()}",
            "",
            "## Economic Metrics",
            f"- Total Absolute Time (ms): {total_time_ms}",
            f"- Total Token Cost: {int(round(total_token_cost))}",
            f"- Communication Overhead Ratio: {communication_ratio:.6f}",
            f"- Total Evaluation Runs: {evaluation_runs}",
            f"- Final USACOArena Submission Decision: {final_submission_decision}",
            f"- Budget Remaining (estimated): {float(runtime_snapshot.get('budget_remaining') or 0.0):.2f}",
            "",
            "## Failures And Retries",
            f"- last_error: {error or '(none)'}",
            "",
            "## Participant Status Snapshot",
            f"- pre_run: {json.dumps(self._status_to_payload(pre_status), ensure_ascii=False)}",
            f"- post_run: {json.dumps(self._status_to_payload(post_status), ensure_ascii=False) if post_status else '(unavailable)'}",
            "",
            "## Reproduction Commands",
            "```bash",
            " ".join(reproduction),
            "```",
            "",
            "## Command",
            "```bash",
            " ".join(command),
            "```",
            "",
        ]
        trace.summary_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_agent_exec_log(
        self,
        *,
        trace: RunTrace,
        started_at: str,
        ended_at: str,
        exit_code: int,
        use_resume: bool,
        selected_problem: str,
        error: Optional[str],
        command: List[str],
        pre_status: ParticipantStatus,
        post_status: Optional[ParticipantStatus],
    ) -> None:
        trace.agent_exec_path.parent.mkdir(parents=True, exist_ok=True)
        with trace.agent_exec_path.open("w", encoding="utf-8") as handle:
            handle.write("# Agent Execution Log\n\n")
            handle.write(f"- run_tag: {trace.run_tag}\n")
            handle.write(f"- started_at: {started_at}\n")
            handle.write(f"- ended_at: {ended_at}\n")
            handle.write(f"- exit_code: {exit_code}\n")
            handle.write(f"- use_resume: {use_resume}\n")
            handle.write(f"- session_id: {self._state.session_id or '(none)'}\n")
            handle.write(f"- selected_problem_id: {selected_problem}\n")
            handle.write(f"- error: {error or '(none)'}\n\n")

            handle.write("## Status\n")
            handle.write(f"- pre_run: {json.dumps(self._status_to_payload(pre_status), ensure_ascii=False)}\n")
            handle.write(
                f"- post_run: {json.dumps(self._status_to_payload(post_status), ensure_ascii=False) if post_status else '(unavailable)'}\n\n"
            )

            handle.write("## Command\n")
            handle.write("-- BEGIN command --\n")
            handle.write(" ".join(command))
            handle.write("\n-- END command --\n\n")

            handle.write("## Artifacts\n")
            handle.write(f"- events: {trace.events_path.name}\n")
            handle.write(f"- budget_log: {trace.budget_log_path.name}\n")
            handle.write(f"- agents: {trace.agents_path.name}\n")
            handle.write(f"- evaluation_trace: {trace.evaluation_trace_path.name}\n")
            handle.write(f"- codex_events: {trace.codex_events_path.name}\n")
            handle.write(f"- codex_stderr: {trace.codex_stderr_path.name}\n")
            handle.write(f"- tool_stats: {trace.tool_stats_path.name}\n")
            handle.write(f"- session_meta: {trace.session_meta_path.name}\n")
            handle.write(f"- summary: {trace.summary_path.name}\n\n")

            self._write_file_section(
                handle=handle,
                title="Codex Input (stdin prompt)",
                source_path=trace.prompt_path,
            )
            self._write_file_section(
                handle=handle,
                title="Codex Output (stdout raw JSON lines)",
                source_path=trace.codex_events_path,
            )
            self._write_file_section(
                handle=handle,
                title="Codex Error Output (stderr raw)",
                source_path=trace.codex_stderr_path,
            )

    def _write_session_metrics(
        self,
        *,
        trace: RunTrace,
        exit_code: int,
        runtime_snapshot: Dict[str, Any],
        error: Optional[str],
    ) -> None:
        tool_stats = {
            "agent_tool_calls_total": 0,
            "agent_mcp_calls_total": 0,
            "agent_experience_read_calls": 0,
            "agent_reference_read_calls": 0,
            "agent_ancestor_code_read_calls": 0,
            "agent_file_read_calls_total": 0,
            "agent_mcp_calls_by_server": {},
        }
        stop_reason_raw = ""
        context_limit_hit = False

        parsed = self._parse_codex_events_for_metrics(trace.codex_events_path)
        tool_stats.update(parsed["tool_stats"])
        stop_reason_raw = parsed["stop_reason_raw"]
        context_limit_hit = parsed["context_limit_hit"]

        if not context_limit_hit:
            context_limit_hit = self._detect_context_limit_from_stderr(trace.codex_stderr_path)
        if not stop_reason_raw and error:
            stop_reason_raw = str(error).strip()[:500]

        llm_wall_ms = self._trace_elapsed_ms(runtime=runtime_snapshot)
        tokens_used = int(round(float(runtime_snapshot.get("tokens_total") or 0.0)))
        end_reason = "natural"
        if context_limit_hit:
            end_reason = "context_limit"
        elif int(exit_code) != 0:
            end_reason = "unknown"

        session_meta = {
            "agent_backend": "codex",
            "agent_end_reason": end_reason,
            "agent_context_limit_hit": bool(context_limit_hit),
            "agent_stop_reason_raw": stop_reason_raw,
            "agent_exit_code": int(exit_code),
            "llm_wall_ms": int(llm_wall_ms),
            "tokens_used": max(0, int(tokens_used)),
        }

        trace.tool_stats_path.write_text(
            json.dumps(tool_stats, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        trace.session_meta_path.write_text(
            json.dumps(session_meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _parse_codex_events_for_metrics(self, path: Path) -> Dict[str, Any]:
        tool_calls_total = 0
        mcp_calls_total = 0
        file_read_calls_total = 0
        mcp_calls_by_server: Dict[str, int] = {}
        context_limit_hit = False
        stop_reason_raw = ""

        if not path.is_file():
            return {
                "tool_stats": {
                    "agent_tool_calls_total": 0,
                    "agent_mcp_calls_total": 0,
                    "agent_experience_read_calls": 0,
                    "agent_reference_read_calls": 0,
                    "agent_ancestor_code_read_calls": 0,
                    "agent_file_read_calls_total": 0,
                    "agent_mcp_calls_by_server": {},
                },
                "stop_reason_raw": "",
                "context_limit_hit": False,
            }

        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    payload = self._parse_json_line(line)
                    if payload is None:
                        continue
                    event_type = str(payload.get("type") or "").strip().lower()
                    if event_type == "item.completed":
                        item = payload.get("item")
                        if isinstance(item, dict):
                            item_type = str(item.get("type") or "").strip().lower()
                            if item_type in {"command_execution", "collab_tool_call", "mcp_tool_call"}:
                                tool_calls_total += 1

                            if item_type == "command_execution":
                                command = str(item.get("command") or "")
                                if self._looks_like_file_read_command(command):
                                    file_read_calls_total += 1

                            if item_type == "mcp_tool_call":
                                mcp_calls_total += 1
                                tool_name = str(item.get("tool") or item.get("server") or "unknown").strip()
                                if tool_name:
                                    mcp_calls_by_server[tool_name] = mcp_calls_by_server.get(tool_name, 0) + 1
                            elif item_type == "collab_tool_call":
                                tool_name = str(item.get("tool") or "").strip()
                                if tool_name.startswith("mcp__"):
                                    mcp_calls_total += 1
                                    mcp_calls_by_server[tool_name] = mcp_calls_by_server.get(tool_name, 0) + 1

                    if event_type in {"error", "turn.failed"}:
                        message = self._extract_event_error_message(payload)
                        if message and not stop_reason_raw:
                            stop_reason_raw = message[:500]
                        lowered = message.lower()
                        if "context" in lowered and ("limit" in lowered or "length" in lowered):
                            context_limit_hit = True
        except OSError:
            pass

        tool_stats = {
            "agent_tool_calls_total": int(tool_calls_total),
            "agent_mcp_calls_total": int(mcp_calls_total),
            "agent_experience_read_calls": 0,
            "agent_reference_read_calls": 0,
            "agent_ancestor_code_read_calls": 0,
            "agent_file_read_calls_total": int(file_read_calls_total),
            "agent_mcp_calls_by_server": dict(sorted(mcp_calls_by_server.items())),
        }
        for key, value in sorted(mcp_calls_by_server.items()):
            tool_stats[f"agent_mcp_calls.{key}"] = int(value)

        return {
            "tool_stats": tool_stats,
            "stop_reason_raw": stop_reason_raw,
            "context_limit_hit": context_limit_hit,
        }

    @staticmethod
    def _extract_event_error_message(payload: Dict[str, Any]) -> str:
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        error_payload = payload.get("error")
        if isinstance(error_payload, str) and error_payload.strip():
            return error_payload.strip()
        if isinstance(error_payload, dict):
            nested = error_payload.get("message")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return ""

    @staticmethod
    def _detect_context_limit_from_stderr(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        lowered = text.lower()
        return "context" in lowered and ("limit" in lowered or "length" in lowered)

    @staticmethod
    def _looks_like_file_read_command(command: str) -> bool:
        lowered = str(command or "").lower()
        if not lowered:
            return False
        if lowered.startswith(("cat ", "sed -n", "head ", "tail ", "rg ", "find ", "ls ", "awk ", "wc ")):
            return True
        read_markers = (
            " cat ",
            "sed -n",
            "head ",
            "tail ",
            "rg ",
            "rg --files",
            "find ",
            "ls ",
            "awk ",
            "wc ",
        )
        return any(marker in lowered for marker in read_markers)

    @staticmethod
    def _derive_submission_decision(
        *,
        post_status: Optional[ParticipantStatus],
        exit_code: int,
        error: Optional[str],
    ) -> str:
        if post_status is not None:
            if post_status.is_running:
                return "continue_iteration_and_submit"
            reason = (post_status.termination_reason or "").strip() or "terminated"
            if reason == "out_of_tokens":
                return "no_further_submission_out_of_tokens"
            return f"stop_submission_{reason}"
        if exit_code == 0:
            return "continue_iteration_and_submit"
        if error:
            return "retry_after_failure"
        return "undetermined"

    def _write_evaluation_trace(self, *, trace: RunTrace, runtime_snapshot: Dict[str, Any]) -> None:
        rows = runtime_snapshot.get("evaluation_trace")
        if not isinstance(rows, list):
            rows = []
        payload = {
            "generated_at": _utc_now(),
            "evaluation_runs": int(runtime_snapshot.get("evaluation_runs") or 0),
            "evaluation_overhead_total": float(runtime_snapshot.get("evaluation_overhead_total") or 0.0),
            "entries": rows,
        }
        trace.evaluation_trace_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_artifact_manifest(self, *, trace: RunTrace) -> None:
        artifacts: List[Dict[str, Any]] = []
        for path in sorted(trace.run_dir.rglob("*")):
            if not path.is_file():
                continue
            if path == trace.manifest_path:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            artifacts.append(
                {
                    "path": _safe_relative(path, self.workspace),
                    "size_bytes": int(size),
                    "sha256": self._file_sha256(path),
                }
            )
        for path in self._collect_workspace_code_test_artifacts():
            if path.is_file():
                artifacts.append(
                    {
                        "path": _safe_relative(path, self.workspace),
                        "size_bytes": int(path.stat().st_size),
                        "sha256": self._file_sha256(path),
                        "kind": "workspace_code_or_test",
                    }
                )
        artifacts.append(
            {
                "path": _safe_relative(trace.manifest_path, self.workspace),
                "size_bytes": None,
                "sha256": None,
                "note": "manifest_self_entry",
            }
        )
        payload = {
            "run_tag": trace.run_tag,
            "generated_at": _utc_now(),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }
        trace.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _collect_workspace_code_test_artifacts(self) -> List[Path]:
        patterns = (
            "main.*",
            "solution.*",
            "test*.*",
            "*_test.*",
            "*.cpp",
            "*.cc",
            "*.cxx",
            "*.py",
            "*.java",
            "*.rs",
            "*.go",
        )
        rows: List[Path] = []
        seen: set[str] = set()
        for pattern in patterns:
            for candidate in sorted(self.workspace.glob(pattern)):
                if not candidate.is_file():
                    continue
                if candidate.name.startswith("."):
                    continue
                key = str(candidate.resolve())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(candidate)
        return rows

    def _append_workspace_exec_log(
        self,
        *,
        trace: RunTrace,
        ended_at: str,
        exit_code: int,
        selected_problem: str,
        error: Optional[str],
        runtime_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else {}
        entry = {
            "timestamp": ended_at,
            "run_tag": trace.run_tag,
            "run_dir": _safe_relative(trace.run_dir, self.workspace),
            "exit_code": int(exit_code),
            "selected_problem_id": selected_problem,
            "session_id": self._state.session_id,
            "error": error,
            "total_token_cost": float(snapshot.get("tokens_total") or 0.0),
            "evaluation_runs": int(snapshot.get("evaluation_runs") or 0),
            "budget_remaining": float(snapshot.get("budget_remaining") or 0.0),
        }
        self._safe_trace_write(
            self.agent_exec_summary_path,
            json.dumps(entry, ensure_ascii=False) + "\n",
        )

        try:
            with self.agent_exec_log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"# Workspace Run: {trace.run_tag}\n")
                handle.write(f"- timestamp: {ended_at}\n")
                handle.write(f"- run_dir: {_safe_relative(trace.run_dir, self.workspace)}\n")
                handle.write(f"- exit_code: {int(exit_code)}\n")
                handle.write(f"- selected_problem_id: {selected_problem}\n")
                handle.write(f"- error: {error or '(none)'}\n\n")
                handle.write("## Run Agent Exec Log\n")
                self._write_file_section(
                    handle=handle,
                    title=trace.agent_exec_path.name,
                    source_path=trace.agent_exec_path,
                )
        except OSError:
            return

    @staticmethod
    def _write_file_section(*, handle: TextIO, title: str, source_path: Path) -> None:
        handle.write(f"## {title}\n")
        handle.write(f"-- BEGIN {source_path.name} --\n")
        wrote_content = False
        ended_with_newline = True
        try:
            with source_path.open("r", encoding="utf-8", errors="ignore") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), ""):
                    if not chunk:
                        break
                    wrote_content = True
                    ended_with_newline = chunk.endswith("\n")
                    handle.write(chunk)
        except OSError:
            handle.write("(missing)\n")
            wrote_content = True
        if not wrote_content:
            handle.write("(empty)\n")
        elif not ended_with_newline:
            handle.write("\n")
        handle.write(f"-- END {source_path.name} --\n\n")

    def _write_final_metrics_snapshot(
        self,
        *,
        status: ParticipantStatus,
        stop_stage: str,
        stop_reason: str,
    ) -> None:
        errors: Dict[str, str] = {}
        participant_state: Optional[Dict[str, Any]] = None
        rankings: List[Dict[str, Any]] = []

        try:
            participant_state = self.client.get_participant_state(
                self.config.competition_id,
                self.config.participant_id,
            )
        except ArenaAPIError as exc:
            errors["participant_state"] = str(exc)

        try:
            rankings = self.client.get_rankings(self.config.competition_id)
        except ArenaAPIError as exc:
            errors["rankings"] = str(exc)

        if participant_state is not None:
            self._write_json_atomic(self.final_participant_state_path, participant_state)
        if rankings:
            self._write_json_atomic(self.final_rankings_path, {"rankings": rankings})

        participant_rank: Optional[int] = None
        participant_ranking_row: Optional[Dict[str, Any]] = None
        for index, row in enumerate(rankings, start=1):
            row_participant = str(row.get("participant_id") or row.get("id") or "").strip()
            if row_participant == self.config.participant_id:
                participant_rank = _to_int(row.get("rank"), index)
                participant_ranking_row = row
                break

        metric_summary: Dict[str, Any] = {}
        if isinstance(participant_state, dict):
            for key in (
                "problem_pass_score",
                "score",
                "consumed_credit",
                "consumed_tokens",
                "submission_penalty",
                "remaining_tokens",
                "accepted_count",
                "submission_count",
                "elapsed_time_seconds",
                "delivery_time_seconds",
                "delivery_time_multiplier",
                "delivery_time_credit",
                "delivery_time_settled",
            ):
                if key in participant_state:
                    metric_summary[key] = participant_state.get(key)
            solved_problems = participant_state.get("solved_problems")
            if isinstance(solved_problems, list):
                metric_summary["solved_problem_count"] = len(solved_problems)

        if "score" not in metric_summary:
            metric_summary["score"] = float(status.score)
        if "remaining_tokens" not in metric_summary:
            metric_summary["remaining_tokens"] = int(status.remaining_tokens)
        if "elapsed_time_seconds" not in metric_summary:
            metric_summary["elapsed_time_seconds"] = int(status.elapsed_time_seconds)
        if "delivery_time_multiplier" not in metric_summary:
            metric_summary["delivery_time_multiplier"] = float(status.delivery_time_multiplier)
        if "delivery_time_credit" not in metric_summary:
            metric_summary["delivery_time_credit"] = float(status.delivery_time_credit)
        if "delivery_time_settled" not in metric_summary:
            metric_summary["delivery_time_settled"] = bool(status.delivery_time_settled)

        final_metrics = {
            "generated_at": _utc_now(),
            "competition_id": self.config.competition_id,
            "participant_id": self.config.participant_id,
            "stop_stage": stop_stage,
            "stop_reason": stop_reason,
            "participant_status": self._status_to_payload(status),
            "participant_metrics": metric_summary,
            "participant_rank": participant_rank,
            "participant_ranking_row": participant_ranking_row,
            "total_participants": len(rankings),
            "runner_state": self._state.to_payload(),
            "artifacts": {
                "participant_state": (
                    self.final_participant_state_path.name if participant_state is not None else None
                ),
                "rankings": self.final_rankings_path.name if rankings else None,
            },
            "errors": errors,
        }
        self._write_json_atomic(self.final_metrics_path, final_metrics)
        self.final_metrics_markdown_path.write_text(
            self._render_final_metrics_markdown(final_metrics),
            encoding="utf-8",
        )

    def _render_final_metrics_markdown(self, payload: Dict[str, Any]) -> str:
        lines: List[str] = [
            "# Final Metrics Snapshot",
            "",
            f"- generated_at: {payload.get('generated_at')}",
            f"- competition_id: {payload.get('competition_id')}",
            f"- participant_id: {payload.get('participant_id')}",
            f"- stop_stage: {payload.get('stop_stage')}",
            f"- stop_reason: {payload.get('stop_reason')}",
            "",
            "## Participant Status",
            f"- status: {json.dumps(payload.get('participant_status'), ensure_ascii=False)}",
            "",
            "## Key Metrics",
        ]

        metric_summary = payload.get("participant_metrics")
        if isinstance(metric_summary, dict) and metric_summary:
            for key in sorted(metric_summary):
                lines.append(f"- {key}: {metric_summary.get(key)}")
        else:
            lines.append("- (unavailable)")

        lines.extend(
            [
                "",
                "## Ranking Snapshot",
                f"- participant_rank: {payload.get('participant_rank')}",
                f"- total_participants: {payload.get('total_participants')}",
                f"- participant_row: {json.dumps(payload.get('participant_ranking_row'), ensure_ascii=False)}",
                "",
                "## Artifacts",
                f"- final_metrics.json: {self.final_metrics_path.name}",
                f"- final_metrics.md: {self.final_metrics_markdown_path.name}",
                f"- final_participant_state.json: {payload.get('artifacts', {}).get('participant_state') or '(missing)'}",
                f"- final_rankings.json: {payload.get('artifacts', {}).get('rankings') or '(missing)'}",
            ]
        )

        errors = payload.get("errors")
        if isinstance(errors, dict) and errors:
            lines.append("")
            lines.append("## API Errors")
            for key in sorted(errors):
                lines.append(f"- {key}: {errors.get(key)}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _safe_trace_write(path: Path, content: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(content)
        except OSError:
            return

    @staticmethod
    def _file_sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    if not chunk:
                        break
                    hasher.update(chunk)
        except OSError:
            return ""
        return hasher.hexdigest()

    def _should_stop(self, status: ParticipantStatus) -> bool:
        if not status.is_running:
            return True
        if status.remaining_tokens <= 0:
            return True
        return False

    def _safe_get_status(self) -> ParticipantStatus:
        return self.client.get_participant_status(
            self.config.competition_id,
            self.config.participant_id,
        )

    def _resume_session_missing(self, stderr_path: Path) -> bool:
        try:
            text = stderr_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        lowered = text.lower()
        hints = (
            "no matching session",
            "no session",
            "session not found",
            "unable to resume",
            "resume failed",
        )
        return any(hint in lowered for hint in hints)

    def _build_context_markdown(self) -> str:
        lines: List[str] = [
            "# USACOArena Codex Loop Context",
            "",
            f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
            f"- api_base: {self.config.api_base}",
            f"- competition_id: {self.config.competition_id}",
            f"- participant_id: {self.config.participant_id}",
            f"- selected_problem_id: {self._state.selected_problem_id or '(auto)'}",
            f"- swarm_strategy_profile: {self._resolve_swarm_strategy_profile()}",
            "",
            "## Notes",
            "- This workspace is controlled by standalone `run_codex_loop_agent.py`.",
            "- Runner persists session id in `runner_state.json` and resumes automatically.",
            "- Participant scoped gateway credentials are fetched from server at runtime.",
            "- System runner traces are written under `runner_runs/<timestamp>/`.",
            "- Swarm-authored traces should be written under `runs/<timestamp>/`.",
            "",
        ]
        return "\n".join(lines)

    def _write_runtime_status(self, *, status: ParticipantStatus, message: str) -> None:
        payload = {
            "timestamp": _utc_now(),
            "message": message,
            "competition_id": self.config.competition_id,
            "participant_id": self.config.participant_id,
            "is_running": status.is_running,
            "termination_reason": status.termination_reason,
            "remaining_tokens": status.remaining_tokens,
            "score": status.score,
            "elapsed_time_seconds": status.elapsed_time_seconds,
            "delivery_time_multiplier": status.delivery_time_multiplier,
            "delivery_time_settled": status.delivery_time_settled,
            "delivery_time_credit": status.delivery_time_credit,
            "session_id": self._state.session_id,
            "run_count": self._state.run_count,
            "consecutive_failures": self._state.consecutive_failures,
        }
        self._write_json_atomic(self.runtime_path, payload)

    def _load_state(self) -> RunnerState:
        if not self.state_path.exists():
            return RunnerState()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return RunnerState()
        return RunnerState.from_payload(payload if isinstance(payload, dict) else {})

    def _persist_state(self) -> None:
        with self._state_lock:
            self._persist_state_unlocked()

    def _persist_state_unlocked(self) -> None:
        self._write_json_atomic(self.state_path, self._state.to_payload())

    @staticmethod
    def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)


def _extract_solved_problem_ids(value: Any) -> set[str]:
    solved: set[str] = set()
    if not isinstance(value, list):
        return solved
    for item in value:
        if isinstance(item, dict):
            problem_id = item.get("problem_id")
            if problem_id is not None:
                solved.add(str(problem_id))
        elif item is not None:
            solved.add(str(item))
    return solved


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_relative(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return str(path)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
