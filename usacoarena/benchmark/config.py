"""Configuration helpers for benchmark-oriented workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .agent_profile import build_agent_profile_template, normalize_agent_profile


class BenchmarkConfigError(ValueError):
    """Raised when benchmark configuration is invalid."""


def _load_structured_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise BenchmarkConfigError(
                "YAML config requires PyYAML. Use JSON or install pyyaml."
            ) from exc
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)

    if not isinstance(payload, dict):
        raise BenchmarkConfigError("Benchmark config root must be an object")
    return payload


def _resolve_env_tokens(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("$ENV:"):
        env_key = value.split(":", 1)[1].strip()
        return os.environ.get(env_key, "")
    if isinstance(value, list):
        return [_resolve_env_tokens(item) for item in value]
    if isinstance(value, dict):
        return {k: _resolve_env_tokens(v) for k, v in value.items()}
    return value


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def load_benchmark_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise BenchmarkConfigError(f"Config file not found: {path}")

    raw = _resolve_env_tokens(_load_structured_file(path))

    api_base = str(raw.get("api_base") or "").strip().rstrip("/")
    if not api_base:
        raise BenchmarkConfigError("`api_base` is required")

    competition = raw.get("competition")
    if not isinstance(competition, dict):
        raise BenchmarkConfigError("`competition` section is required")

    problem_ids = competition.get("problem_ids")
    if not isinstance(problem_ids, list) or not problem_ids:
        raise BenchmarkConfigError("`competition.problem_ids` must be a non-empty list")

    participants_raw = raw.get("participants")
    if not isinstance(participants_raw, list) or not participants_raw:
        raise BenchmarkConfigError("`participants` must be a non-empty list")

    participants: List[Dict[str, Any]] = []
    for index, item in enumerate(participants_raw):
        if not isinstance(item, dict):
            raise BenchmarkConfigError(f"participants[{index}] must be an object")

        name = str(item.get("name") or "").strip()
        if not name:
            raise BenchmarkConfigError(f"participants[{index}].name is required")

        participants.append(
            {
                "name": name,
                "api_base_url": str(item.get("api_base_url") or "").strip(),
                "api_key": str(item.get("api_key") or "").strip(),
                "limit_tokens": _safe_int(item.get("limit_tokens"), _safe_int(competition.get("max_tokens_per_participant"), 100000)),
                "lambda_value": _safe_int(item.get("lambda_value"), 100),
                "agent_profile": normalize_agent_profile(
                    {
                        **(item.get("agent_profile") if isinstance(item.get("agent_profile"), dict) else {}),
                        "request_format": item.get("request_format")
                        if isinstance(item.get("request_format"), dict)
                        else (
                            (item.get("agent_profile") or {}).get("request_format")
                            if isinstance(item.get("agent_profile"), dict)
                            else {}
                        ),
                        "response_format": item.get("response_format")
                        if isinstance(item.get("response_format"), dict)
                        else (
                            (item.get("agent_profile") or {}).get("response_format")
                            if isinstance(item.get("agent_profile"), dict)
                            else {}
                        ),
                    }
                ),
            }
        )

    report_cfg = raw.get("report") if isinstance(raw.get("report"), dict) else {}

    return {
        "api_base": api_base,
        "competition": {
            "title": str(competition.get("title") or "USACOArena Benchmark").strip(),
            "description": str(competition.get("description") or "").strip(),
            "problem_ids": [str(pid) for pid in problem_ids if str(pid).strip()],
            "max_tokens_per_participant": _safe_int(
                competition.get("max_tokens_per_participant"),
                100000,
            ),
            "rules": competition.get("rules") if isinstance(competition.get("rules"), dict) else {},
        },
        "participants": participants,
        "report": {
            "output_dir": str(report_cfg.get("output_dir") or "reports/intelligence").strip(),
            "weights": report_cfg.get("weights") if isinstance(report_cfg.get("weights"), dict) else {},
        },
    }


def build_benchmark_template() -> Dict[str, Any]:
    return {
        "api_base": "http://127.0.0.1:5000",
        "competition": {
            "title": "USACOArena Open Benchmark",
            "description": "Reproducible benchmark run",
            "problem_ids": [
                "1515_bronze_hoof_paper_scissors_minus_one",
                "1516_bronze_more_cow_photos",
            ],
            "max_tokens_per_participant": 100000,
            "rules": {
                "lambda": 100,
                "delivery_time_multiplier": 1.0,
                "intelligence_weights": {
                    "solve": 0.45,
                    "efficiency": 0.2,
                    "reliability": 0.15,
                    "speed": 0.1,
                    "coverage": 0.1,
                },
            },
        },
        "participants": [
            {
                "name": "codex-baseline",
                "api_base_url": "$ENV:OPENAI_BASE_URL",
                "api_key": "$ENV:OPENAI_API_KEY",
                "limit_tokens": 100000,
                "lambda_value": 100,
                "request_format": {
                    "url": "/v1/chat/completions",
                    "method": "POST",
                    "headers": {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer {api_key}",
                    },
                    "body_template": {
                        "messages": "{messages}",
                        "model": "{model_id}",
                    },
                },
                "response_format": {
                    "response_path": "choices[0].message.content",
                    "error_path": "error.message",
                },
                "agent_profile": {
                    **build_agent_profile_template(),
                    "agent_type": "codex",
                    "transport": "openai_compatible_http",
                },
            },
            {
                "name": "claude-baseline",
                "api_base_url": "$ENV:ANTHROPIC_BASE_URL",
                "api_key": "$ENV:ANTHROPIC_API_KEY",
                "limit_tokens": 100000,
                "lambda_value": 100,
                "request_format": {
                    "url": "/v1/messages",
                    "method": "POST",
                    "headers": {
                        "Content-Type": "application/json",
                        "x-api-key": "{api_key}",
                        "anthropic-version": "2023-06-01",
                    },
                    "body_template": {
                        "model": "{model_id}",
                        "max_tokens": 4096,
                        "messages": "{messages}",
                    },
                },
                "response_format": {
                    "response_path": "content[0].text",
                    "error_path": "error.message",
                    "usage_path": "usage",
                },
                "agent_profile": {
                    **build_agent_profile_template(),
                    "agent_type": "claude_code",
                    "transport": "openai_compatible_http",
                    "mcp": {
                        "enabled": True,
                        "servers": [],
                    },
                },
            },
        ],
        "report": {
            "output_dir": "reports/intelligence",
            "weights": {
                "solve": 0.45,
                "efficiency": 0.2,
                "reliability": 0.15,
                "speed": 0.1,
                "coverage": 0.1,
            },
        },
    }
