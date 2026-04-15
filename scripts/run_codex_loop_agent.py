#!/usr/bin/env python3
"""Run a standalone Codex loop agent for one USACOArena participant."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from usacoarena.codex_loop_agent.runner import CodexLoopRunner, RunnerConfig


def _default_workspace(competition_id: str, participant_id: str) -> Path:
    comp = _safe_fs_name(competition_id) or "competition"
    part = _safe_fs_name(participant_id) or "participant"
    return Path("logs") / "codex_loop_agents" / f"{comp}_{part}"


def _safe_fs_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in text)


def _timestamped_workspace(parent: Path, now: datetime | None = None) -> Path:
    """Return a non-existing timestamped child workspace under parent."""

    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    candidate = parent / stamp
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        retry = parent / f"{stamp}_{suffix:02d}"
        if not retry.exists():
            return retry
        suffix += 1


def _reserve_timestamped_workspace(parent: Path, now: datetime | None = None) -> Path:
    """Atomically create and return a unique timestamped child workspace."""

    root = Path(parent).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    suffix = 0
    while True:
        candidate = root / stamp if suffix == 0 else root / f"{stamp}_{suffix:02d}"
        try:
            candidate.mkdir(mode=0o755, parents=False, exist_ok=False)
            return candidate
        except FileExistsError:
            suffix += 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Standalone Codex participant loop for USACOArena. "
            "This process is isolated from existing organizer/competitor pipelines."
        )
    )

    parser.add_argument(
        "--api-base",
        default=os.environ.get("USACOARENA_BASE_URL", "http://127.0.0.1:5000"),
        help="USACOArena API base URL",
    )
    parser.add_argument(
        "--competition-id",
        default=os.environ.get("USACOARENA_COMPETITION_ID", ""),
        help="Competition ID (or set USACOARENA_COMPETITION_ID)",
    )
    parser.add_argument(
        "--participant-id",
        default=os.environ.get("USACOARENA_PARTICIPANT_ID", ""),
        help="Participant ID (or set USACOARENA_PARTICIPANT_ID)",
    )

    parser.add_argument(
        "--workspace",
        default="",
        help=(
            "Workspace parent directory. When set, create a timestamped child directory for actual run workspace. "
            "Default (when omitted): logs/codex_loop_agents/<competition>_<participant>"
        ),
    )
    parser.add_argument(
        "--template-dir",
        default="config/codex_agent/usacoarena",
        help=(
            "Template directory copied into workspace. "
            "If not the default usacoarena template, it is overlaid on top of base files. "
            "Common strategy dirs: config/codex_agent/swarm_fast_7, "
            "config/codex_agent/swarm_balanced_4, config/codex_agent/swarm_lean_2."
        ),
    )

    parser.add_argument(
        "--codex-binary",
        default=os.environ.get("CODEX_BIN", "codex"),
        help="Codex executable path",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("USACOARENA_CODEX_MODEL", "gpt-5.3-codex"),
        help="Codex model name",
    )
    parser.add_argument(
        "--language",
        default=os.environ.get("USACOARENA_LANGUAGE", "cpp"),
        help="Submission language passed to helper tools",
    )

    parser.add_argument(
        "--problem-id",
        default=os.environ.get("USACOARENA_PROBLEM_ID", ""),
        help="Optional fixed problem id; otherwise auto-select unsolved problem",
    )
    parser.add_argument(
        "--resume-session-id",
        default="",
        help="Override saved session id and resume from this id",
    )

    parser.add_argument(
        "--request-timeout",
        type=float,
        default=30.0,
        help="HTTP timeout (seconds)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Sleep between successful runs (seconds)",
    )
    parser.add_argument(
        "--retry-min-backoff",
        type=float,
        default=2.0,
        help="Initial backoff after failures (seconds)",
    )
    parser.add_argument(
        "--retry-max-backoff",
        type=float,
        default=60.0,
        help="Maximum backoff after failures (seconds)",
    )

    parser.add_argument(
        "--llm-isolate",
        action="store_true",
        help="Enable Linux Landlock filesystem isolation for Codex subprocess",
    )
    parser.add_argument(
        "--no-sync-templates",
        action="store_true",
        help="Do not copy template files into workspace",
    )
    parser.add_argument(
        "--force-template-overwrite",
        action="store_true",
        help="Overwrite existing files when syncing templates",
    )

    parser.add_argument(
        "--extra-codex-config",
        action="append",
        default=[],
        help="Additional `-c key=value` codex config override (repeatable)",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    competition_id = str(args.competition_id or "").strip()
    participant_id = str(args.participant_id or "").strip()
    api_base = str(args.api_base or "").strip().rstrip("/")

    if not competition_id:
        parser.exit(2, "ERROR: --competition-id is required (or set USACOARENA_COMPETITION_ID)\n")
    if not participant_id:
        parser.exit(2, "ERROR: --participant-id is required (or set USACOARENA_PARTICIPANT_ID)\n")
    if not api_base:
        parser.exit(2, "ERROR: --api-base must not be empty\n")

    workspace_arg = str(args.workspace or "").strip()
    if workspace_arg:
        workspace_parent = Path(workspace_arg).expanduser()
        workspace = _reserve_timestamped_workspace(workspace_parent)
    else:
        workspace = _default_workspace(competition_id, participant_id)

    config = RunnerConfig(
        api_base=api_base,
        competition_id=competition_id,
        participant_id=participant_id,
        workspace=workspace,
        template_dir=Path(args.template_dir).expanduser(),
        codex_binary=str(args.codex_binary or "codex").strip(),
        model=str(args.model or "").strip(),
        language=str(args.language or "cpp").strip() or "cpp",
        request_timeout=float(args.request_timeout),
        poll_interval_seconds=float(args.poll_interval),
        retry_min_backoff_seconds=float(args.retry_min_backoff),
        retry_max_backoff_seconds=float(args.retry_max_backoff),
        llm_isolate=bool(args.llm_isolate),
        sync_templates=not bool(args.no_sync_templates),
        force_template_overwrite=bool(args.force_template_overwrite),
        explicit_problem_id=(str(args.problem_id).strip() or None),
        resume_session_id=(str(args.resume_session_id).strip() or None),
        extra_codex_configs=[str(item) for item in (args.extra_codex_config or []) if str(item).strip()],
    )

    print("[codex-loop] starting")
    print(f"[codex-loop] api_base={config.api_base}")
    print(f"[codex-loop] competition_id={config.competition_id}")
    print(f"[codex-loop] participant_id={config.participant_id}")
    print(f"[codex-loop] workspace={config.workspace}")
    print(f"[codex-loop] llm_isolate={config.llm_isolate}")

    try:
        runner = CodexLoopRunner(config)
        return runner.run()
    except KeyboardInterrupt:
        print("[codex-loop] interrupted by user")
        return 130
    except Exception as exc:
        print(f"[codex-loop] fatal error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
