#!/usr/bin/env python3
"""Bootstrap USACOArena competition + participant-specific gateway credentials for infinite_tree."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


DEFAULT_API_BASE = "http://127.0.0.1:5000"
DEFAULT_TITLE = "infinite_tree vs USACOArena"
DEFAULT_DESCRIPTION = "Competition bootstrapped for infinite_tree agents"
DEFAULT_COMPETITION_MAX_TOKENS = 100000
INT32_MAX = (2**31) - 1
INT64_MAX = (2**63) - 1


def _normalize_base(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("api base url must not be empty")
    return value.rstrip("/")


def _parse_problem_ids(raw: str) -> List[str]:
    values = [token.strip() for token in (raw or "").split(",") if token.strip()]
    if not values:
        return []

    if len(values) == 1:
        candidate = values[0]
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            if isinstance(loaded, list):
                return [str(item).strip() for item in loaded if str(item).strip()]

            if isinstance(loaded, dict):
                for key in ("problem_ids", "problems", "ids"):
                    arr = loaded.get(key)
                    if isinstance(arr, list):
                        return [str(item).strip() for item in arr if str(item).strip()]
                raise ValueError(
                    f"problem id file {candidate!r} must contain a list, "
                    "or a dict with one of keys: problem_ids/problems/ids"
                )

            raise ValueError(f"problem id file {candidate!r} must be a JSON list or object")

        if candidate.endswith(".json") or "/" in candidate or "\\" in candidate:
            raise FileNotFoundError(
                f"problem id file not found: {candidate!r}. "
                "Pass an existing JSON file path, or pass comma-separated problem IDs."
            )

    return values


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name.strip())
    return cleaned or "agent"


def _load_competition_config(path: str) -> Dict[str, Any]:
    candidate = (path or "").strip()
    if not candidate:
        return {}
    if not os.path.isfile(candidate):
        raise FileNotFoundError(f"competition config file not found: {candidate!r}")

    with open(candidate, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"competition config file must contain a JSON object: {candidate!r}")

    rules = loaded.get("rules")
    if rules is not None and not isinstance(rules, dict):
        raise ValueError(f"'rules' must be a JSON object in competition config: {candidate!r}")
    return loaded


def _pick_text_value(value: Any, *, fallback: str) -> str:
    if value is None:
        return fallback
    normalized = str(value).strip()
    return normalized or fallback


def _pick_int_value(
    value: Any,
    *,
    fallback: int,
    field_name: str,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    if value is None:
        result = fallback
    elif isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer, got {value!r}")
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be an integer, got {value!r}")
        result = int(value)
    else:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc

    if min_value is not None and result < min_value:
        raise ValueError(
            f"{field_name} must be >= {min_value}, got {result!r}"
        )
    if max_value is not None and result > max_value:
        raise ValueError(
            f"{field_name} must be <= {max_value}, got {result!r}"
        )
    return result


@dataclass
class SetupResult:
    api_base: str
    competition_id: str
    problem_id: Optional[str]
    participants: List[Dict[str, Any]]


class ArenaClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = _normalize_base(base_url)
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = self.session.request(method, url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise RuntimeError(f"network error for {method} {path}: {exc}") from exc

        data: Optional[Dict[str, Any]] = None
        parse_error: Optional[Exception] = None
        try:
            decoded = response.json()
            if isinstance(decoded, dict):
                data = decoded
        except Exception as exc:  # pragma: no cover - defensive on malformed upstream replies
            parse_error = exc

        if response.status_code >= 400:
            if isinstance(data, dict):
                message = data.get("message") or data.get("error") or str(data)
            else:
                body_text = (response.text or "").strip()
                message = body_text[:500] if body_text else response.reason
            raise RuntimeError(
                f"HTTP {response.status_code} for {method} {path}: {message}"
            )

        if parse_error is not None:
            raise RuntimeError(
                f"failed to parse JSON response for {method} {path}: {parse_error}"
            ) from parse_error
        if data is None:
            raise RuntimeError(f"response for {method} {path} is not a JSON object")

        if data.get("status") != "success":
            raise RuntimeError(f"API call failed ({path}): {data.get('message', 'unknown error')}")
        return data

    def create_competition(
        self,
        *,
        title: str,
        description: str,
        problem_ids: List[str],
        max_tokens_per_participant: int,
        rules: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = {
            "title": title,
            "description": description,
            "problem_ids": problem_ids,
            "max_tokens_per_participant": max_tokens_per_participant,
        }
        if rules is not None:
            payload["rules"] = rules
        data = self._request("POST", "/api/competitions/create", payload=payload)
        competition = data.get("data", {}).get("competition", {})
        competition_id = competition.get("id")
        if not competition_id:
            raise RuntimeError(f"missing competition id in response: {data}")
        return str(competition_id)

    def list_problems(self, competition_id: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/api/problems/list/{competition_id}")
        raw = data.get("data", [])
        return raw if isinstance(raw, list) else []

    def create_participants_batch(
        self,
        *,
        competition_id: str,
        participant_names: List[str],
        limit_tokens: int,
        lambda_value: int,
        upstream_api_base_url: str,
        upstream_api_key: str,
    ) -> List[Dict[str, Any]]:
        participants_payload: List[Dict[str, Any]] = []
        for name in participant_names:
            row: Dict[str, Any] = {"name": name}
            if upstream_api_base_url:
                row["api_base_url"] = upstream_api_base_url
            if upstream_api_key:
                row["api_key"] = upstream_api_key
            participants_payload.append(row)

        payload = {
            "default_limit_tokens": limit_tokens,
            "default_lambda_value": lambda_value,
            "participants": participants_payload,
        }
        data = self._request("POST", f"/api/participants/create_batch/{competition_id}", payload=payload)
        created = data.get("data", {}).get("created", [])
        errors = data.get("data", {}).get("errors", [])
        if errors:
            raise RuntimeError(f"batch create returned errors: {errors}")
        if not isinstance(created, list) or not created:
            raise RuntimeError("batch create returned no participants")
        return created

    def get_gateway_credentials(self, competition_id: str, participant_id: str) -> Dict[str, Any]:
        data = self._request(
            "GET",
            f"/api/participants/gateway_credentials/{competition_id}/{participant_id}",
        )
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise RuntimeError(
                "gateway credentials response payload is missing or invalid "
                f"(competition_id={competition_id}, participant_id={participant_id})"
            )
        return payload


def _build_participant_names(
    explicit_names: List[str],
    *,
    count: int,
    prefix: str,
) -> List[str]:
    names = [name.strip() for name in explicit_names if name and name.strip()]
    if count > 0:
        width = len(str(count))
        for idx in range(1, count + 1):
            names.append(f"{prefix}-{idx:0{width}d}")
    deduped: List[str] = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def setup(args: argparse.Namespace) -> SetupResult:
    competition_config = _load_competition_config(args.competition_config)

    effective_api_base = args.api_base
    if args.api_base == DEFAULT_API_BASE:
        cfg_api_base = competition_config.get("api_base")
        if isinstance(cfg_api_base, str) and cfg_api_base.strip():
            effective_api_base = cfg_api_base.strip()

    participant_names = _build_participant_names(
        args.participant_name,
        count=args.participant_count,
        prefix=args.participant_prefix,
    )
    if not participant_names:
        raise ValueError("at least one participant is required (--participant-name or --participant-count)")

    client = ArenaClient(effective_api_base, timeout=args.timeout)

    if args.create_competition:
        problem_ids = _parse_problem_ids(args.problem_ids)
        if not problem_ids:
            raise ValueError("--problem-ids is required when --create-competition is set")

        cfg_title = competition_config.get("competition_title")
        if cfg_title is None:
            cfg_title = competition_config.get("title")
        cfg_description = competition_config.get("competition_description")
        if cfg_description is None:
            cfg_description = competition_config.get("description")
        cfg_max_tokens = competition_config.get("max_tokens_per_participant")
        cfg_rules = competition_config.get("rules")

        title = args.title
        if args.title == DEFAULT_TITLE:
            title = _pick_text_value(cfg_title, fallback=DEFAULT_TITLE)

        description = args.description
        if args.description == DEFAULT_DESCRIPTION:
            description = _pick_text_value(cfg_description, fallback=DEFAULT_DESCRIPTION)

        max_tokens_per_participant = args.competition_max_tokens
        if args.competition_max_tokens == DEFAULT_COMPETITION_MAX_TOKENS:
            max_tokens_per_participant = _pick_int_value(
                cfg_max_tokens,
                fallback=DEFAULT_COMPETITION_MAX_TOKENS,
                field_name="max_tokens_per_participant",
                min_value=0,
                max_value=INT64_MAX,
            )
        else:
            max_tokens_per_participant = _pick_int_value(
                max_tokens_per_participant,
                fallback=DEFAULT_COMPETITION_MAX_TOKENS,
                field_name="max_tokens_per_participant",
                min_value=0,
                max_value=INT64_MAX,
            )

        competition_id = client.create_competition(
            title=title,
            description=description,
            problem_ids=problem_ids,
            max_tokens_per_participant=max_tokens_per_participant,
            rules=cfg_rules if isinstance(cfg_rules, dict) else None,
        )
    else:
        if not args.competition_id:
            raise ValueError("--competition-id is required when not creating competition")
        competition_id = args.competition_id

    problems = client.list_problems(competition_id)
    problem_id = args.problem_id
    if not problem_id and problems:
        first_problem = problems[0]
        value = first_problem.get("id")
        if value is not None:
            problem_id = str(value)

    created = client.create_participants_batch(
        competition_id=competition_id,
        participant_names=participant_names,
        limit_tokens=_pick_int_value(
            args.participant_limit_tokens,
            fallback=10000000,
            field_name="participant_limit_tokens",
            min_value=0,
            max_value=INT64_MAX,
        ),
        lambda_value=_pick_int_value(
            args.participant_lambda,
            fallback=100,
            field_name="participant_lambda",
            min_value=0,
            max_value=INT32_MAX,
        ),
        upstream_api_base_url=(args.upstream_api_base_url or "").strip(),
        upstream_api_key=(args.upstream_api_key or "").strip(),
    )

    participants: List[Dict[str, Any]] = []
    for row in created:
        participant_id = str(row.get("id") or "")
        if not participant_id:
            raise RuntimeError(f"participant record missing id: {row}")
        gateway = client.get_gateway_credentials(competition_id, participant_id)
        participants.append(
            {
                "name": row.get("name"),
                "participant_id": participant_id,
                "gateway_base_url": gateway.get("gateway_base_url"),
                "openai_api_base": gateway.get("openai_api_base"),
                "openai_api_key": gateway.get("openai_api_key"),
            }
        )

    return SetupResult(
        api_base=effective_api_base,
        competition_id=competition_id,
        problem_id=problem_id,
        participants=participants,
    )


def _print_summary(result: SetupResult, args: argparse.Namespace) -> None:
    payload = {
        "api_base": result.api_base,
        "competition_id": result.competition_id,
        "problem_id": result.problem_id,
        "participants": result.participants,
    }
    print("=== setup summary ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("")
    print("=== infinite_tree env snippets ===")

    for item in result.participants:
        name = str(item.get("name") or "agent")
        participant_id = str(item.get("participant_id"))
        safe_name = _safe_name(name)
        openai_api_base = str(item.get("openai_api_base") or "")
        openai_api_key = str(item.get("openai_api_key") or "")

        print(f"# {name}")
        print(f"export USACOARENA_BASE_URL={json.dumps(result.api_base)}")
        print(f"export USACOARENA_COMPETITION_ID={json.dumps(result.competition_id)}")
        print(f"export USACOARENA_PARTICIPANT_ID={json.dumps(participant_id)}")
        if result.problem_id:
            print(f"export USACOARENA_PROBLEM_ID={json.dumps(result.problem_id)}")
        print(f"export OPENAI_API_BASE={json.dumps(openai_api_base)}")
        print(f"export OPENAI_BASE_URL={json.dumps(openai_api_base)}")
        print(f"export OPENAI_API_KEY={json.dumps(openai_api_key)}")
        print(
            "uv run main.py "
            "--config usacoArena "
            f"--output history/usacoArena/{safe_name} "
            "--llm-backend codex "
            f"--iterations {args.iterations} "
            "--llm-isolate"
        )
        print("")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or reuse a USACOArena competition, register one or multiple "
            "infinite_tree participants, and print participant-specific gateway credentials."
        )
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="USACOArena base URL")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")

    parser.add_argument(
        "--create-competition",
        action="store_true",
        help="Create a new competition before adding participants",
    )
    parser.add_argument(
        "--competition-config",
        default="",
        help=(
            "Optional JSON config path (e.g. config/competition_main.json). "
            "When creating a competition, uses its rules/title/description/max_tokens_per_participant; "
            "CLI arguments with non-default values override config values."
        ),
    )
    parser.add_argument("--competition-id", default="", help="Existing competition id")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Competition title")
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION, help="Competition description")
    parser.add_argument(
        "--problem-ids",
        default="",
        help="Comma-separated problem IDs, or a JSON file path when creating a competition",
    )
    parser.add_argument(
        "--competition-max-tokens",
        type=int,
        default=DEFAULT_COMPETITION_MAX_TOKENS,
        help="max_tokens_per_participant when creating a competition",
    )

    parser.add_argument(
        "--participant-name",
        action="append",
        default=[],
        help="Participant name (can be repeated)",
    )
    parser.add_argument(
        "--participant-count",
        type=int,
        default=0,
        help="Auto-generate this many participants using --participant-prefix",
    )
    parser.add_argument(
        "--participant-prefix",
        default="infinite-tree-agent",
        help="Prefix used with --participant-count",
    )
    parser.add_argument(
        "--participant-limit-tokens",
        type=int,
        default=10000000,
        help="Participant token limit",
    )
    parser.add_argument(
        "--participant-lambda",
        type=int,
        default=100,
        help="Participant lambda value",
    )
    parser.add_argument(
        "--problem-id",
        default="",
        help="Problem id used by infinite_tree evaluate.py (default: first problem in competition)",
    )
    parser.add_argument(
        "--upstream-api-base-url",
        default="",
        help=(
            "Optional upstream LLM API base URL stored per participant. "
            "If omitted, server falls back to USACOARENA_UPSTREAM_API_BASE_URL environment variable."
        ),
    )
    parser.add_argument(
        "--upstream-api-key",
        default="",
        help=(
            "Optional upstream LLM API key stored per participant. "
            "If omitted, server falls back to USACOARENA_UPSTREAM_API_KEY environment variable."
        ),
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=200,
        help="Suggested iteration count printed in the run command",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = setup(args)
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    _print_summary(result, args)


if __name__ == "__main__":
    main()
