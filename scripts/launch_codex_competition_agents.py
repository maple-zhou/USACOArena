#!/usr/bin/env python3
"""One-click bootstrap + launch script for USACOArena Codex loop agents."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from setup_infinite_tree_agents import (
    DEFAULT_API_BASE,
    DEFAULT_COMPETITION_MAX_TOKENS,
    DEFAULT_DESCRIPTION,
    DEFAULT_TITLE,
    setup,
)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RUN_AGENT_SCRIPT = SCRIPT_DIR / "run_codex_loop_agent.py"


def _safe_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "agent"
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in text)
    return cleaned or "agent"


def _reserve_timestamped_workspace(root: Path, now: datetime | None = None) -> Path:
    """Atomically create and return a unique timestamped workspace under root."""

    parent = Path(root).expanduser()
    parent.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    suffix = 0
    while True:
        candidate = parent / stamp if suffix == 0 else parent / f"{stamp}_{suffix:02d}"
        try:
            candidate.mkdir(mode=0o755, parents=False, exist_ok=False)
            return candidate
        except FileExistsError:
            suffix += 1


def _resolve_templates(template_dirs: List[str], participant_count: int) -> List[str]:
    normalized = [str(item).strip() for item in (template_dirs or []) if str(item).strip()]
    if not normalized:
        normalized = ["config/codex_agent/usacoarena"]
    if participant_count <= 0:
        return []
    if len(normalized) == 1:
        return normalized * participant_count
    if len(normalized) == participant_count:
        return normalized
    raise ValueError(
        "template count mismatch: pass either exactly one --template-dir "
        f"for all participants, or exactly {participant_count} values "
        "(one per participant in creation order)."
    )


def _build_setup_namespace(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        api_base=args.api_base,
        timeout=args.timeout,
        create_competition=bool(args.create_competition),
        competition_config=args.competition_config,
        competition_id=args.competition_id,
        title=args.title,
        description=args.description,
        problem_ids=args.problem_ids,
        competition_max_tokens=args.competition_max_tokens,
        participant_name=list(args.participant_name or []),
        participant_count=int(args.participant_count),
        participant_prefix=args.participant_prefix,
        participant_limit_tokens=int(args.participant_limit_tokens),
        participant_lambda=int(args.participant_lambda),
        problem_id=args.problem_id,
        upstream_api_base_url=args.upstream_api_base_url,
        upstream_api_key=args.upstream_api_key,
    )


def _build_run_command(
    args: argparse.Namespace,
    *,
    competition_id: str,
    participant_id: str,
    template_dir: str,
    workspace_parent: Path,
) -> List[str]:
    command = [
        sys.executable,
        str(RUN_AGENT_SCRIPT),
        "--api-base",
        str(args.api_base),
        "--competition-id",
        competition_id,
        "--participant-id",
        participant_id,
        "--workspace",
        str(Path(workspace_parent).expanduser()),
        "--template-dir",
        template_dir,
        "--codex-binary",
        str(args.codex_binary),
        "--model",
        str(args.model),
        "--language",
        str(args.language),
        "--request-timeout",
        str(float(args.request_timeout)),
        "--poll-interval",
        str(float(args.poll_interval)),
        "--retry-min-backoff",
        str(float(args.retry_min_backoff)),
        "--retry-max-backoff",
        str(float(args.retry_max_backoff)),
    ]
    if args.agent_problem_id:
        command.extend(["--problem-id", str(args.agent_problem_id)])
    if args.resume_session_id:
        command.extend(["--resume-session-id", str(args.resume_session_id)])
    if args.llm_isolate:
        command.append("--llm-isolate")
    if args.no_sync_templates:
        command.append("--no-sync-templates")
    if args.force_template_overwrite:
        command.append("--force-template-overwrite")
    for item in args.extra_codex_config or []:
        value = str(item).strip()
        if value:
            command.extend(["--extra-codex-config", value])
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-click flow: create/reuse competition, register one or more participants, "
            "then launch one run_codex_loop_agent process per participant."
        )
    )

    setup_group = parser.add_argument_group("Competition setup options")
    setup_group.add_argument("--api-base", default=DEFAULT_API_BASE, help="USACOArena base URL")
    setup_group.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    setup_group.add_argument(
        "--create-competition",
        action="store_true",
        help="Create a new competition before adding participants",
    )
    setup_group.add_argument(
        "--competition-config",
        default="",
        help="Optional competition JSON config path (rules/title/description/max tokens)",
    )
    setup_group.add_argument("--competition-id", default="", help="Existing competition id")
    setup_group.add_argument("--title", default=DEFAULT_TITLE, help="Competition title")
    setup_group.add_argument("--description", default=DEFAULT_DESCRIPTION, help="Competition description")
    setup_group.add_argument(
        "--problem-ids",
        default="",
        help="Comma-separated problem IDs, or a JSON file path when creating a competition",
    )
    setup_group.add_argument(
        "--competition-max-tokens",
        type=int,
        default=DEFAULT_COMPETITION_MAX_TOKENS,
        help="max_tokens_per_participant when creating competition",
    )
    setup_group.add_argument(
        "--participant-name",
        action="append",
        default=[],
        help="Participant name (repeatable)",
    )
    setup_group.add_argument(
        "--participant-count",
        type=int,
        default=0,
        help="Auto-generate this many participants using --participant-prefix",
    )
    setup_group.add_argument(
        "--participant-prefix",
        default="infinite-tree-agent",
        help="Prefix used with --participant-count",
    )
    setup_group.add_argument(
        "--participant-limit-tokens",
        type=int,
        default=10000000,
        help="Participant token limit",
    )
    setup_group.add_argument(
        "--participant-lambda",
        type=int,
        default=100,
        help="Participant lambda value",
    )
    setup_group.add_argument(
        "--problem-id",
        default="",
        help="Problem id hint consumed by setup script (optional)",
    )
    setup_group.add_argument(
        "--upstream-api-base-url",
        default="",
        help="Optional upstream LLM API base URL stored per participant",
    )
    setup_group.add_argument(
        "--upstream-api-key",
        default="",
        help="Optional upstream LLM API key stored per participant",
    )

    launch_group = parser.add_argument_group("Agent launch options")
    launch_group.add_argument(
        "--workspace",
        default="logs/codex_loop_agents/one_click",
        help=(
            "Workspace root directory. Launcher creates one timestamped batch subdirectory under this root; "
            "all per-agent workspaces and _launcher_logs for this launch are stored inside that batch directory."
        ),
    )
    launch_group.add_argument(
        "--template-dir",
        action="append",
        default=[],
        help=(
            "Template directory for agent(s). Repeat to map one-by-one by participant order. "
            "If only one value is provided, it is applied to all participants."
        ),
    )
    launch_group.add_argument("--codex-binary", default="codex", help="Codex executable path")
    launch_group.add_argument("--model", default="gpt-5.3-codex", help="Codex model name")
    launch_group.add_argument("--language", default="cpp", help="Submission language")
    launch_group.add_argument(
        "--agent-problem-id",
        default="",
        help="Optional fixed --problem-id passed to each run_codex_loop_agent",
    )
    launch_group.add_argument(
        "--resume-session-id",
        default="",
        help="Optional fixed --resume-session-id passed to each run_codex_loop_agent",
    )
    launch_group.add_argument(
        "--request-timeout",
        type=float,
        default=30.0,
        help="HTTP timeout for each launched run_codex_loop_agent",
    )
    launch_group.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Poll interval for each launched run_codex_loop_agent",
    )
    launch_group.add_argument(
        "--retry-min-backoff",
        type=float,
        default=2.0,
        help="Retry minimum backoff for each launched run_codex_loop_agent",
    )
    launch_group.add_argument(
        "--retry-max-backoff",
        type=float,
        default=60.0,
        help="Retry maximum backoff for each launched run_codex_loop_agent",
    )
    launch_group.add_argument(
        "--llm-isolate",
        action="store_true",
        help="Pass --llm-isolate to each run_codex_loop_agent process",
    )
    launch_group.add_argument(
        "--no-sync-templates",
        action="store_true",
        help="Pass --no-sync-templates to each launched agent",
    )
    launch_group.add_argument(
        "--force-template-overwrite",
        action="store_true",
        help="Pass --force-template-overwrite to each launched agent",
    )
    launch_group.add_argument(
        "--extra-codex-config",
        action="append",
        default=[],
        help="Repeatable extra codex config (forwarded as --extra-codex-config)",
    )
    launch_group.add_argument(
        "--wait",
        action="store_true",
        help="Wait for all launched agent processes to exit",
    )
    launch_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print launch plan and commands; do not start agents",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not RUN_AGENT_SCRIPT.is_file():
        parser.exit(1, f"ERROR: missing launcher target script: {RUN_AGENT_SCRIPT}\n")

    setup_args = _build_setup_namespace(args)
    try:
        setup_result = setup(setup_args)
    except Exception as exc:
        parser.exit(1, f"ERROR: setup failed: {exc}\n")

    participants: List[Dict[str, Any]] = list(setup_result.participants or [])
    if not participants:
        parser.exit(1, "ERROR: setup returned no participants\n")

    try:
        template_dirs = _resolve_templates(args.template_dir, len(participants))
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")

    workspace_root = Path(args.workspace).expanduser()
    workspace_parent = _reserve_timestamped_workspace(workspace_root)
    log_dir = workspace_parent / "_launcher_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    launched: List[Dict[str, Any]] = []
    processes: List[subprocess.Popen[str]] = []
    process_indexes: List[int] = []
    stamp = workspace_parent.name

    for index, (participant, template_dir) in enumerate(zip(participants, template_dirs), start=1):
        participant_id = str(participant.get("participant_id") or "").strip()
        if not participant_id:
            parser.exit(1, f"ERROR: participant record missing participant_id: {participant}\n")
        participant_name = str(participant.get("name") or f"agent-{index}")
        command = _build_run_command(
            args,
            competition_id=str(setup_result.competition_id),
            participant_id=participant_id,
            template_dir=template_dir,
            workspace_parent=workspace_parent,
        )
        log_path = log_dir / f"{stamp}_{index:02d}_{_safe_name(participant_name)}_{participant_id[:8]}.log"

        record: Dict[str, Any] = {
            "index": index,
            "name": participant_name,
            "participant_id": participant_id,
            "template_dir": template_dir,
            "log_path": str(log_path),
            "command": command,
            "command_shell": shlex.join(command),
            "pid": None,
            "status": "planned",
            "exit_code": None,
        }

        if not args.dry_run:
            with open(log_path, "a", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    command,
                    cwd=str(REPO_ROOT),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=not bool(args.wait),
                )
            processes.append(process)
            process_indexes.append(len(launched))
            record["pid"] = process.pid
            record["status"] = "started"

        launched.append(record)

    if not args.dry_run:
        time.sleep(0.2)
        for process, record_idx in zip(processes, process_indexes):
            code = process.poll()
            if code is None:
                launched[record_idx]["status"] = "running"
            else:
                launched[record_idx]["status"] = "exited_early"
                launched[record_idx]["exit_code"] = code

    if args.wait and not args.dry_run:
        interrupted = False
        try:
            for process, record_idx in zip(processes, process_indexes):
                code = process.wait()
                launched[record_idx]["exit_code"] = code
                launched[record_idx]["status"] = "exited"
        except KeyboardInterrupt:
            interrupted = True
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process, record_idx in zip(processes, process_indexes):
                code = process.poll()
                launched[record_idx]["exit_code"] = code
                launched[record_idx]["status"] = "terminated_by_launcher"

        if interrupted:
            print("[one-click] interrupted, sent terminate signal to child processes.")

    summary = {
        "api_base": setup_result.api_base,
        "competition_id": setup_result.competition_id,
        "problem_id": setup_result.problem_id,
        "workspace_root": str(workspace_root),
        "workspace_parent": str(workspace_parent),
        "dry_run": bool(args.dry_run),
        "wait": bool(args.wait),
        "participants": launched,
    }
    manifest_path = log_dir / f"launch_manifest_{stamp}.json"
    summary["manifest_path"] = str(manifest_path)
    manifest_payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_payload, f, indent=2, ensure_ascii=False)

    print("=== one-click launch summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.dry_run:
        return 0

    any_early_failure = any(
        item.get("status") in {"exited_early", "exited"} and int(item.get("exit_code") or 0) != 0
        for item in launched
    )
    return 1 if any_early_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
