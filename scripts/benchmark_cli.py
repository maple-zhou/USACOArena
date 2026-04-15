#!/usr/bin/env python3
"""Unified benchmark CLI for USACOArena."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from usacoarena.benchmark.config import (
    BenchmarkConfigError,
    build_benchmark_template,
    load_benchmark_config,
)
from usacoarena.benchmark.reporting import save_report_bundle


def _request_json(
    method: str,
    base: str,
    path: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    url = f"{base.rstrip('/')}{path}"
    response = requests.request(method=method, url=url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response from {url}: not a JSON object")
    return data


def cmd_init_template(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists() and not args.force:
        raise RuntimeError(f"Refusing to overwrite existing file: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_benchmark_template(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Template written to: {output}")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    cfg = load_benchmark_config(Path(args.config))
    api_base = cfg["api_base"]
    competition_cfg = cfg["competition"]

    create_payload = {
        "title": competition_cfg["title"],
        "description": competition_cfg["description"],
        "problem_ids": competition_cfg["problem_ids"],
        "max_tokens_per_participant": competition_cfg["max_tokens_per_participant"],
        "rules": competition_cfg.get("rules", {}),
    }

    create_res = _request_json(
        "POST",
        api_base,
        "/api/competitions/create",
        payload=create_payload,
        timeout=args.timeout,
    )
    if create_res.get("status") != "success":
        raise RuntimeError(create_res.get("message", "Failed to create competition"))

    competition_data = create_res.get("data", {}).get("competition", {})
    competition_id = str(competition_data.get("id") or "").strip()
    if not competition_id:
        raise RuntimeError("Create competition response missing competition ID")

    participants = cfg["participants"]
    default_lambda = int(
        competition_cfg.get("rules", {}).get("lambda", args.default_lambda_value)
    )

    batch_payload = {
        "default_limit_tokens": competition_cfg["max_tokens_per_participant"],
        "default_lambda_value": default_lambda,
        "participants": participants,
    }

    batch_res = _request_json(
        "POST",
        api_base,
        f"/api/participants/create_batch/{competition_id}",
        payload=batch_payload,
        timeout=args.timeout,
    )
    if batch_res.get("status") != "success":
        raise RuntimeError(batch_res.get("message", "Failed to create participants"))

    batch_data = batch_res.get("data", {})
    created = batch_data.get("created", []) if isinstance(batch_data, dict) else []
    errors = batch_data.get("errors", []) if isinstance(batch_data, dict) else []

    participant_entries = []
    for item in created:
        if not isinstance(item, dict):
            continue
        participant_id = str(item.get("id") or "").strip()
        gateway = None
        if participant_id:
            try:
                cred_res = _request_json(
                    "GET",
                    api_base,
                    f"/api/participants/gateway_credentials/{competition_id}/{participant_id}",
                    timeout=args.timeout,
                )
                if cred_res.get("status") == "success":
                    gateway = cred_res.get("data")
            except Exception:
                gateway = None

        participant_entries.append(
            {
                "participant_id": participant_id,
                "name": item.get("name"),
                "agent_profile": item.get("agent_profile", {}),
                "gateway": gateway,
            }
        )

    output_dir = Path(args.output_dir or cfg["report"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"setup_manifest_{competition_id}.json"

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "api_base": api_base,
        "competition_id": competition_id,
        "competition": competition_data,
        "participants_created": participant_entries,
        "participant_errors": errors,
        "source_config": str(Path(args.config).resolve()),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"competition_id={competition_id}")
    print(f"participants_created={len(participant_entries)}")
    print(f"participant_errors={len(errors)}")
    print(f"manifest={manifest_path}")

    if errors and args.fail_on_errors:
        return 2
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    report_res = _request_json(
        "GET",
        args.api_base,
        f"/api/metrics/intelligence/{args.competition_id}?format=json&include_test_points={'true' if args.include_test_points else 'false'}",
        timeout=args.timeout,
    )
    if report_res.get("status") != "success":
        raise RuntimeError(report_res.get("message", "Failed to fetch intelligence metrics"))

    report = report_res.get("data", {})
    if not isinstance(report, dict):
        raise RuntimeError("Metrics API returned invalid report payload")

    output_dir = Path(args.output_dir or f"reports/intelligence/{args.competition_id}")
    artifacts = save_report_bundle(report, output_dir)

    print(f"competition_id={args.competition_id}")
    for key, path in artifacts.items():
        print(f"{key}={path}")
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    health = _request_json("GET", args.api_base, "/health", timeout=args.timeout)
    print(f"health={health.get('status')}")

    if args.competition_id:
        metrics = _request_json(
            "GET",
            args.api_base,
            f"/api/metrics/intelligence/{args.competition_id}?format=json",
            timeout=args.timeout,
        )
        print(f"metrics={metrics.get('status')}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="USACOArena benchmark CLI (setup/report/smoke)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init-template", help="Write benchmark config template")
    init_p.add_argument(
        "--output", default="config/benchmark_template.json", help="Output template path"
    )
    init_p.add_argument("--force", action="store_true", help="Overwrite existing file")
    init_p.set_defaults(func=cmd_init_template)

    setup_p = sub.add_parser("setup", help="Create competition and register participants")
    setup_p.add_argument("--config", required=True, help="Benchmark config path (json/yaml)")
    setup_p.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    setup_p.add_argument("--default-lambda-value", type=int, default=100)
    setup_p.add_argument("--output-dir", default="", help="Manifest output directory")
    setup_p.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Return non-zero if any participant creation failed",
    )
    setup_p.set_defaults(func=cmd_setup)

    report_p = sub.add_parser("report", help="Fetch metrics and export report artifacts")
    report_p.add_argument("--api-base", required=True, help="USACOArena API base URL")
    report_p.add_argument("--competition-id", required=True)
    report_p.add_argument("--timeout", type=float, default=30.0)
    report_p.add_argument("--output-dir", default="", help="Report output directory")
    report_p.add_argument("--include-test-points", action="store_true")
    report_p.set_defaults(func=cmd_report)

    smoke_p = sub.add_parser("smoke", help="Basic endpoint smoke checks")
    smoke_p.add_argument("--api-base", required=True, help="USACOArena API base URL")
    smoke_p.add_argument("--competition-id", default="")
    smoke_p.add_argument("--timeout", type=float, default=15.0)
    smoke_p.set_defaults(func=cmd_smoke)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return int(args.func(args))
    except BenchmarkConfigError as exc:
        parser.exit(2, f"CONFIG ERROR: {exc}\n")
    except requests.RequestException as exc:
        parser.exit(2, f"HTTP ERROR: {exc}\n")
    except Exception as exc:  # pylint: disable=broad-except
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
