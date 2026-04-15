"""Aggregate paper experiment runs under runs/paper into publication-ready tables."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_competition_results(run_dir: Path) -> Optional[Path]:
    candidates: List[Path] = []
    for base in (run_dir, run_dir / "logs"):
        if not base.exists():
            continue
        candidates.extend(sorted(base.rglob("competition_results_*.json")))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _mean_std(values: Sequence[float]) -> Dict[str, float]:
    clean = [float(v) for v in values]
    if not clean:
        return {"mean": 0.0, "std": 0.0, "count": 0}
    if len(clean) == 1:
        return {"mean": clean[0], "std": 0.0, "count": 1}
    return {
        "mean": mean(clean),
        "std": pstdev(clean),
        "count": len(clean),
    }


def _format_decimal(value: float, digits: int = 2, thousands: bool = False) -> str:
    if thousands:
        return f"{value:,.{digits}f}"
    return f"{value:.{digits}f}"


def _format_mean_std(value: Mapping[str, float], digits: int = 2, thousands: bool = False) -> str:
    return f"{_format_decimal(float(value.get('mean', 0.0)), digits, thousands)} ± {_format_decimal(float(value.get('std', 0.0)), digits, thousands)}"


def _format_credit_short(value: Mapping[str, float]) -> str:
    def _short(number: float) -> str:
        abs_number = abs(number)
        if abs_number >= 1_000_000:
            return f"{number / 1_000_000:.2f}M"
        if abs_number >= 1_000:
            return f"{number / 1_000:.1f}K"
        return f"{number:.0f}"

    return f"{_short(float(value.get('mean', 0.0)))} ± {_short(float(value.get('std', 0.0)))}"


def _snake_to_title(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _canonical_model_name(name: str) -> str:
    lowered = (name or "").strip()
    aliases = {
        "gpt-5-2025-08-07": "GPT-5 (Base)",
        "gpt-5-codex": "GPT-5-Codex",
        "codex-cli": "Codex-CLI",
        "gemini-2.5-pro": "Gemini-2.5-pro",
        "qwen3-235b": "Qwen3-235B",
        "qwen3-coder-480b": "Qwen3-Coder-480B",
        "glm-4.5": "GLM-4.5",
        "deepseek-v3": "DeepSeek-V3",
        "deepseek-v3.1": "DeepSeek-V3.1",
        "kimi-k2-0905": "Kimi-K2-0905",
        "claude-sonnet-4-20250514": "Claude-4-Sonnet",
        "competitor a": "Competitor A",
        "competitor b": "Competitor B",
    }
    return aliases.get(lowered.lower(), lowered)


def _paper_score_value(summary: Mapping[str, Any]) -> float:
    # Table 8 / Table 9 use problem-pass score semantics, not the internal lambda-adjusted score.
    if "problem_pass_score" in summary:
        return _safe_float(summary.get("problem_pass_score"), 0.0)
    return _safe_float(summary.get("score"), 0.0)


def _attempted_problems_value(summary: Mapping[str, Any]) -> int:
    if "attempted_problems" in summary:
        return _safe_int(summary.get("attempted_problems"), 0)
    problem_stats = summary.get("problem_stats")
    if isinstance(problem_stats, dict):
        return sum(
            1
            for item in problem_stats.values()
            if isinstance(item, dict) and _safe_int(item.get("submission_count"), 0) > 0
        )
    return 0


def _submission_precision_value(summary: Mapping[str, Any]) -> float:
    submissions = _safe_int(summary.get("submission_count"), 0)
    accepted = _safe_int(summary.get("accepted_count"), 0)
    if submissions <= 0:
        return 0.0
    return 100.0 * accepted / submissions


def _compute_rank_from_details(participants: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    sorted_rows = sorted(
        participants,
        key=lambda item: (
            -_paper_score_value(item),
            _safe_float(item.get("consumed_credit"), 0.0),
            _canonical_model_name(str(item.get("name", ""))).lower(),
        ),
    )
    return {
        _canonical_model_name(str(item.get("name", ""))): index
        for index, item in enumerate(sorted_rows, start=1)
    }


@dataclass
class ParticipantRunRecord:
    model: str
    run_key: str
    paper_score: float
    internal_score: float
    arena_rank: float
    consumed_credit: float
    inference_credit: float
    hint_credit: float
    penalty_credit: float
    test_credit: float
    submission_credit: float
    delivery_time_credit: float
    attempted_problems: int
    submission_precision: float
    solved_problems: int
    source_paths: Dict[str, str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "run_key": self.run_key,
            "paper_score": self.paper_score,
            "internal_score": self.internal_score,
            "arena_rank": self.arena_rank,
            "consumed_credit": self.consumed_credit,
            "inference_credit": self.inference_credit,
            "hint_credit": self.hint_credit,
            "penalty_credit": self.penalty_credit,
            "test_credit": self.test_credit,
            "submission_credit": self.submission_credit,
            "delivery_time_credit": self.delivery_time_credit,
            "attempted_problems": self.attempted_problems,
            "submission_precision": self.submission_precision,
            "solved_problems": self.solved_problems,
            "source_paths": dict(self.source_paths),
        }


def _load_run_records(run_dir: Path) -> Tuple[List[ParticipantRunRecord], List[str]]:
    report_path = run_dir / "report" / "intelligence.json"
    details_path = _find_latest_competition_results(run_dir)
    warnings: List[str] = []

    report_rows_by_model: Dict[str, Dict[str, Any]] = {}
    if report_path.exists():
        report_payload = _read_json(report_path)
        for row in report_payload.get("rows", []):
            if isinstance(row, dict):
                report_rows_by_model[_canonical_model_name(str(row.get("name", "")))] = row
    else:
        warnings.append(f"missing_report:{run_dir}")

    detail_rows_by_model: Dict[str, Dict[str, Any]] = {}
    if details_path and details_path.exists():
        details_payload = _read_json(details_path)
        if isinstance(details_payload, dict):
            for _, row in details_payload.items():
                if isinstance(row, dict):
                    detail_rows_by_model[_canonical_model_name(str(row.get("name", "")))] = row
    else:
        warnings.append(f"missing_competition_results:{run_dir}")

    model_names = sorted(set(report_rows_by_model.keys()) | set(detail_rows_by_model.keys()))
    if not model_names:
        warnings.append(f"empty_run:{run_dir}")
        return [], warnings

    inferred_rank_map = _compute_rank_from_details(list(detail_rows_by_model.values()))
    records: List[ParticipantRunRecord] = []
    run_key = str(run_dir)

    for model_name in model_names:
        report_row = report_rows_by_model.get(model_name, {})
        detail_row = detail_rows_by_model.get(model_name, {})
        paper_score = (
            _safe_float(report_row.get("problem_pass_score"), math.nan)
            if report_row
            else math.nan
        )
        if math.isnan(paper_score):
            paper_score = _paper_score_value(detail_row)

        internal_score = (
            _safe_float(report_row.get("score"), math.nan)
            if report_row
            else math.nan
        )
        if math.isnan(internal_score):
            internal_score = _safe_float(detail_row.get("score"), 0.0)

        arena_rank = (
            _safe_float(report_row.get("arena_rank"), math.nan)
            if report_row
            else math.nan
        )
        if math.isnan(arena_rank):
            arena_rank = float(inferred_rank_map.get(model_name, 0))

        solved_problems = _safe_int(report_row.get("solved_problems"), -1)
        if solved_problems < 0:
            problem_stats = detail_row.get("problem_stats")
            if isinstance(problem_stats, dict):
                solved_problems = sum(
                    1 for item in problem_stats.values() if isinstance(item, dict) and bool(item.get("solved"))
                )
            else:
                solved_problems = 0

        records.append(
            ParticipantRunRecord(
                model=model_name,
                run_key=run_key,
                paper_score=paper_score,
                internal_score=internal_score,
                arena_rank=arena_rank,
                consumed_credit=_safe_float(
                    report_row.get("consumed_credit", detail_row.get("consumed_credit")),
                    0.0,
                ),
                inference_credit=_safe_float(detail_row.get("LLM_tokens"), 0.0),
                hint_credit=_safe_float(detail_row.get("hint_tokens"), 0.0),
                penalty_credit=_safe_float(detail_row.get("submission_penalty"), 0.0),
                test_credit=_safe_float(detail_row.get("test_tokens"), 0.0),
                submission_credit=_safe_float(detail_row.get("submission_tokens"), 0.0),
                delivery_time_credit=_safe_float(detail_row.get("delivery_time_credit"), 0.0),
                attempted_problems=_attempted_problems_value(report_row or detail_row),
                submission_precision=_submission_precision_value(report_row or detail_row),
                solved_problems=solved_problems,
                source_paths={
                    "report": str(report_path) if report_path.exists() else "",
                    "competition_results": str(details_path) if details_path else "",
                },
            )
        )

    return records, warnings


def _collect_records_for_run_dirs(run_dirs: Iterable[Path]) -> Tuple[List[ParticipantRunRecord], List[str]]:
    all_records: List[ParticipantRunRecord] = []
    warnings: List[str] = []
    for run_dir in run_dirs:
        records, local_warnings = _load_run_records(run_dir)
        all_records.extend(records)
        warnings.extend(local_warnings)
    return all_records, warnings


def _aggregate_by_model(records: Sequence[ParticipantRunRecord]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[ParticipantRunRecord]] = {}
    for record in records:
        grouped.setdefault(record.model, []).append(record)

    rows: List[Dict[str, Any]] = []
    for model_name, items in grouped.items():
        rows.append(
            {
                "model": model_name,
                "runs_count": len(items),
                "avg_rank": _mean_std([item.arena_rank for item in items]),
                "avg_score": _mean_std([item.paper_score for item in items]),
                "avg_consumed_credit": _mean_std([item.consumed_credit for item in items]),
                "inference_credit": _mean_std([item.inference_credit for item in items]),
                "hint_credit": _mean_std([item.hint_credit for item in items]),
                "penalty_credit": _mean_std([item.penalty_credit for item in items]),
                "test_credit": _mean_std([item.test_credit for item in items]),
                "submission_credit": _mean_std([item.submission_credit for item in items]),
                "delivery_time_credit": _mean_std([item.delivery_time_credit for item in items]),
                "attempted_problems": _mean_std([float(item.attempted_problems) for item in items]),
                "submission_precision": _mean_std([item.submission_precision for item in items]),
                "solved_problems": _mean_std([float(item.solved_problems) for item in items]),
                "run_keys": [item.run_key for item in items],
            }
        )

    rows.sort(
        key=lambda item: (
            float(item["avg_rank"]["mean"]),
            -float(item["avg_score"]["mean"]),
            float(item["avg_consumed_credit"]["mean"]),
            item["model"].lower(),
        )
    )
    return rows


def _render_markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not headers:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _save_json_csv_md(
    payload: Mapping[str, Any],
    *,
    output_dir: Path,
    stem: str,
    csv_rows: Sequence[Mapping[str, Any]],
    csv_fields: Sequence[str],
    markdown: str,
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    md_path = output_dir / f"{stem}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_csv(csv_path, csv_fields, csv_rows)
    md_path.write_text(markdown, encoding="utf-8")
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
    }


def _main_section_run_dirs(runs_root: Path) -> Dict[str, List[Path]]:
    section_root = runs_root / "4_2_main"
    contests = [
        "december_2024",
        "january_2025",
        "february_2025",
        "us_open_2025",
    ]
    return {
        contest: sorted(path for path in (section_root / contest).glob("run_*") if path.is_dir())
        for contest in contests
    }


def aggregate_main_table(runs_root: Path, output_dir: Path) -> Dict[str, Any]:
    contest_run_dirs = _main_section_run_dirs(runs_root)
    flat_run_dirs = [path for paths in contest_run_dirs.values() for path in paths]
    records, warnings = _collect_records_for_run_dirs(flat_run_dirs)
    rows = _aggregate_by_model(records)

    csv_rows: List[Dict[str, Any]] = []
    markdown_rows: List[List[str]] = []
    for row in rows:
        csv_row = {
            "model": row["model"],
            "runs_count": row["runs_count"],
            "avg_rank_mean": _format_decimal(row["avg_rank"]["mean"], 2),
            "avg_rank_std": _format_decimal(row["avg_rank"]["std"], 2),
            "avg_score_mean": _format_decimal(row["avg_score"]["mean"], 2),
            "avg_score_std": _format_decimal(row["avg_score"]["std"], 2),
            "avg_consumed_credit_mean": _format_decimal(row["avg_consumed_credit"]["mean"], 2),
            "avg_consumed_credit_std": _format_decimal(row["avg_consumed_credit"]["std"], 2),
            "inference_credit_mean": _format_decimal(row["inference_credit"]["mean"], 2),
            "inference_credit_std": _format_decimal(row["inference_credit"]["std"], 2),
            "hint_credit_mean": _format_decimal(row["hint_credit"]["mean"], 2),
            "hint_credit_std": _format_decimal(row["hint_credit"]["std"], 2),
            "penalty_credit_mean": _format_decimal(row["penalty_credit"]["mean"], 2),
            "penalty_credit_std": _format_decimal(row["penalty_credit"]["std"], 2),
            "test_credit_mean": _format_decimal(row["test_credit"]["mean"], 2),
            "test_credit_std": _format_decimal(row["test_credit"]["std"], 2),
            "submission_credit_mean": _format_decimal(row["submission_credit"]["mean"], 2),
            "submission_credit_std": _format_decimal(row["submission_credit"]["std"], 2),
            "delivery_time_credit_mean": _format_decimal(row["delivery_time_credit"]["mean"], 2),
            "delivery_time_credit_std": _format_decimal(row["delivery_time_credit"]["std"], 2),
        }
        csv_rows.append(csv_row)
        markdown_rows.append(
            [
                row["model"],
                _format_mean_std(row["avg_rank"], 2),
                _format_mean_std(row["avg_score"], 2),
                _format_mean_std(row["avg_consumed_credit"], 0, thousands=True),
                _format_credit_short(row["inference_credit"]),
                _format_credit_short(row["hint_credit"]),
                _format_credit_short(row["penalty_credit"]),
            ]
        )

    markdown = "# Table 8 Aggregation\n\n"
    markdown += "Aggregated results from Section 4.2 / Appendix F. `Avg. Score` follows the paper's problem-pass-score semantics.\n\n"
    markdown += _render_markdown_table(
        [
            "Model",
            "Avg. Rank",
            "Avg. Score",
            "Avg. Consumed Credit",
            "Inference Credit",
            "Hint Credit",
            "Penalty Credit",
        ],
        markdown_rows,
    )
    if warnings:
        markdown += "\nWarnings:\n"
        for warning in warnings:
            markdown += f"- `{warning}`\n"

    payload = {
        "section": "table_8_main",
        "source_root": str(runs_root),
        "contest_run_counts": {key: len(value) for key, value in contest_run_dirs.items()},
        "warnings": warnings,
        "rows": rows,
        "records": [record.as_dict() for record in records],
    }
    artifacts = _save_json_csv_md(
        payload,
        output_dir=output_dir,
        stem="table_8_main",
        csv_rows=csv_rows,
        csv_fields=list(csv_rows[0].keys()) if csv_rows else [
            "model",
            "runs_count",
            "avg_rank_mean",
            "avg_rank_std",
            "avg_score_mean",
            "avg_score_std",
            "avg_consumed_credit_mean",
            "avg_consumed_credit_std",
            "inference_credit_mean",
            "inference_credit_std",
            "hint_credit_mean",
            "hint_credit_std",
            "penalty_credit_mean",
            "penalty_credit_std",
            "test_credit_mean",
            "test_credit_std",
            "submission_credit_mean",
            "submission_credit_std",
            "delivery_time_credit_mean",
            "delivery_time_credit_std",
        ],
        markdown=markdown,
    )
    payload["artifacts"] = artifacts
    return payload


APPENDIX_B_TABLE2_SETTINGS: Sequence[Tuple[str, str]] = (
    ("main_result", "Main Result"),
    ("low_credit_10m", "Low Credit (10M)"),
    ("high_credit_40m", "High Credit (40M)"),
    ("free_test", "Free Test ($0)"),
    ("high_test", "High Test ($1k)"),
    ("free_hint", "Free Hint ($0)"),
    ("high_hint", "High Hint (100x)"),
    ("flat_score", "Flat Score"),
    ("exp_score", "Exp. Score"),
)


APPENDIX_B_EXTRA_SETTINGS: Sequence[Tuple[str, str]] = (
    ("free_penalty", "Free Penalty"),
    ("prompt_p11", "Prompt P1.1"),
    ("prompt_p12", "Prompt P1.2"),
    ("prompt_p21", "Prompt P2.1"),
    ("prompt_p22", "Prompt P2.2"),
)


def _aggregate_score_matrix(
    runs_root: Path,
    settings: Sequence[Tuple[str, str]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[str]]:
    warnings: List[str] = []
    per_setting_rows: Dict[str, Dict[str, Any]] = {}
    setting_counts: Dict[str, int] = {}

    for key, title in settings:
        run_dirs = sorted(path for path in (runs_root / key).glob("run_*") if path.is_dir())
        setting_counts[key] = len(run_dirs)
        records, local_warnings = _collect_records_for_run_dirs(run_dirs)
        warnings.extend(local_warnings)
        per_setting_rows[key] = {
            "title": title,
            "rows": _aggregate_by_model(records),
        }

    models = sorted(
        {
            row["model"]
            for value in per_setting_rows.values()
            for row in value["rows"]
        }
    )
    matrix_rows: List[Dict[str, Any]] = []
    for model in models:
        item: Dict[str, Any] = {"model": model}
        for key, title in settings:
            match = next((row for row in per_setting_rows[key]["rows"] if row["model"] == model), None)
            if match is None:
                item[key] = None
                item[f"{key}_credit"] = None
            else:
                item[key] = round(float(match["avg_score"]["mean"]), 4)
                item[f"{key}_credit"] = round(float(match["avg_consumed_credit"]["mean"]), 4)
        matrix_rows.append(item)

    return matrix_rows, setting_counts, warnings


def aggregate_appendix_b_table(runs_root: Path, output_dir: Path) -> Dict[str, Any]:
    matrix_rows, setting_counts, warnings = _aggregate_score_matrix(runs_root / "appendix_b", APPENDIX_B_TABLE2_SETTINGS)

    markdown_rows = []
    csv_rows = []
    for row in matrix_rows:
        markdown_rows.append([row["model"]] + [
            "" if row[key] is None else _format_decimal(float(row[key]), 2)
            for key, _ in APPENDIX_B_TABLE2_SETTINGS
        ])
        csv_row = {"model": row["model"]}
        for key, title in APPENDIX_B_TABLE2_SETTINGS:
            csv_row[title] = "" if row[key] is None else _format_decimal(float(row[key]), 2)
            csv_row[f"{title} Credit"] = "" if row.get(f"{key}_credit") is None else _format_decimal(float(row[f"{key}_credit"]), 2)
        csv_rows.append(csv_row)

    markdown = "# Table 2 Aggregation\n\n"
    markdown += "Appendix B mega-ablation matrix. Values are averaged `problem_pass_score` across repeats.\n\n"
    markdown += _render_markdown_table(
        ["Model"] + [title for _, title in APPENDIX_B_TABLE2_SETTINGS],
        markdown_rows,
    )
    if warnings:
        markdown += "\nWarnings:\n"
        for warning in warnings:
            markdown += f"- `{warning}`\n"

    payload = {
        "section": "table_2_appendix_b",
        "source_root": str(runs_root / "appendix_b"),
        "setting_run_counts": setting_counts,
        "warnings": warnings,
        "rows": matrix_rows,
    }
    artifacts = _save_json_csv_md(
        payload,
        output_dir=output_dir,
        stem="table_2_appendix_b",
        csv_rows=csv_rows,
        csv_fields=list(csv_rows[0].keys()) if csv_rows else ["model"] + [title for _, title in APPENDIX_B_TABLE2_SETTINGS],
        markdown=markdown,
    )
    payload["artifacts"] = artifacts
    return payload


def aggregate_appendix_b_extended(runs_root: Path, output_dir: Path) -> Dict[str, Any]:
    settings = list(APPENDIX_B_TABLE2_SETTINGS) + list(APPENDIX_B_EXTRA_SETTINGS)
    matrix_rows, setting_counts, warnings = _aggregate_score_matrix(runs_root / "appendix_b", settings)

    markdown_rows = []
    csv_rows = []
    for row in matrix_rows:
        markdown_rows.append([row["model"]] + [
            "" if row[key] is None else _format_decimal(float(row[key]), 2)
            for key, _ in settings
        ])
        csv_row = {"model": row["model"]}
        for key, title in settings:
            csv_row[title] = "" if row[key] is None else _format_decimal(float(row[key]), 2)
            csv_row[f"{title} Credit"] = "" if row.get(f"{key}_credit") is None else _format_decimal(float(row[f"{key}_credit"]), 2)
        csv_rows.append(csv_row)

    markdown = "# Appendix B Extended Aggregation\n\n"
    markdown += "Superset of the paper table: includes the published Table 2 settings plus `Free Penalty` and prompt variants P1.1/P1.2/P2.1/P2.2.\n\n"
    markdown += _render_markdown_table(["Model"] + [title for _, title in settings], markdown_rows)
    if warnings:
        markdown += "\nWarnings:\n"
        for warning in warnings:
            markdown += f"- `{warning}`\n"

    payload = {
        "section": "appendix_b_extended",
        "source_root": str(runs_root / "appendix_b"),
        "setting_run_counts": setting_counts,
        "warnings": warnings,
        "rows": matrix_rows,
    }
    artifacts = _save_json_csv_md(
        payload,
        output_dir=output_dir,
        stem="appendix_b_extended",
        csv_rows=csv_rows,
        csv_fields=list(csv_rows[0].keys()) if csv_rows else ["model"] + [title for _, title in settings],
        markdown=markdown,
    )
    payload["artifacts"] = artifacts
    return payload


def aggregate_self_play(runs_root: Path, output_dir: Path) -> Dict[str, Any]:
    section_root = runs_root / "4_3_self_play"
    variants = [("standard", "Standard Self-Play"), ("duel_prompt", "Duel Prompt Self-Play")]
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    for key, title in variants:
        run_dirs = sorted(path for path in (section_root / key).glob("run_*") if path.is_dir())
        records, local_warnings = _collect_records_for_run_dirs(run_dirs)
        warnings.extend(local_warnings)
        grouped = _aggregate_by_model(records)
        for item in grouped:
            rows.append(
                {
                    "variant": title,
                    "model": item["model"],
                    "runs_count": item["runs_count"],
                    "avg_score": item["avg_score"],
                    "avg_consumed_credit": item["avg_consumed_credit"],
                    "submission_precision": item["submission_precision"],
                }
            )

    markdown_rows = [
        [
            row["variant"],
            row["model"],
            str(row["runs_count"]),
            _format_mean_std(row["avg_score"], 2),
            _format_credit_short(row["avg_consumed_credit"]),
            _format_mean_std(row["submission_precision"], 2),
        ]
        for row in rows
    ]
    markdown = "# Section 4.3 Self-Play Aggregation\n\n"
    markdown += _render_markdown_table(
        ["Variant", "Agent", "Runs", "Avg. Score", "Avg. Credit Consumed", "Submission Precision (%)"],
        markdown_rows,
    )
    if warnings:
        markdown += "\nWarnings:\n"
        for warning in warnings:
            markdown += f"- `{warning}`\n"

    csv_rows = [
        {
            "variant": row["variant"],
            "model": row["model"],
            "runs_count": row["runs_count"],
            "avg_score_mean": _format_decimal(row["avg_score"]["mean"], 2),
            "avg_score_std": _format_decimal(row["avg_score"]["std"], 2),
            "avg_credit_mean": _format_decimal(row["avg_consumed_credit"]["mean"], 2),
            "avg_credit_std": _format_decimal(row["avg_consumed_credit"]["std"], 2),
            "submission_precision_mean": _format_decimal(row["submission_precision"]["mean"], 2),
            "submission_precision_std": _format_decimal(row["submission_precision"]["std"], 2),
        }
        for row in rows
    ]

    payload = {
        "section": "section_4_3_self_play",
        "source_root": str(section_root),
        "warnings": warnings,
        "rows": rows,
    }
    artifacts = _save_json_csv_md(
        payload,
        output_dir=output_dir,
        stem="section_4_3_self_play",
        csv_rows=csv_rows,
        csv_fields=list(csv_rows[0].keys()) if csv_rows else [
            "variant",
            "model",
            "runs_count",
            "avg_score_mean",
            "avg_score_std",
            "avg_credit_mean",
            "avg_credit_std",
            "submission_precision_mean",
            "submission_precision_std",
        ],
        markdown=markdown,
    )
    payload["artifacts"] = artifacts
    return payload


def _matchup_win_rate_map(records: Sequence[ParticipantRunRecord]) -> Dict[str, float]:
    if not records:
        return {}
    wins_by_model: Dict[str, int] = {}
    grouped_by_run: Dict[str, List[ParticipantRunRecord]] = {}
    for record in records:
        grouped_by_run.setdefault(record.run_key, []).append(record)
    for participants in grouped_by_run.values():
        participants = sorted(
            participants,
            key=lambda item: (
                -item.paper_score,
                item.consumed_credit,
                item.model.lower(),
            ),
        )
        if participants:
            winner = participants[0].model
            wins_by_model[winner] = wins_by_model.get(winner, 0) + 1
    total_runs = max(len(grouped_by_run), 1)
    return {
        model: 100.0 * wins_by_model.get(model, 0) / total_runs
        for model in {record.model for record in records}
    }


def _aggregate_matchup(run_dirs: Sequence[Path], experiment_title: str) -> Dict[str, Any]:
    records, warnings = _collect_records_for_run_dirs(run_dirs)
    grouped = _aggregate_by_model(records)
    raw_by_model: Dict[str, List[ParticipantRunRecord]] = {}
    for record in records:
        raw_by_model.setdefault(record.model, []).append(record)
    win_rate_map = _matchup_win_rate_map(records)

    rows = []
    for item in grouped:
        rows.append(
            {
                "experiment": experiment_title,
                "agent": item["model"],
                "runs_count": item["runs_count"],
                "win_rate": round(win_rate_map.get(item["model"], 0.0), 4),
                "avg_score": item["avg_score"],
                "avg_credit_consumed": item["avg_consumed_credit"],
                "attempted_problems": item["attempted_problems"],
                "submission_precision": item["submission_precision"],
            }
        )
    rows.sort(key=lambda item: item["agent"].lower())
    return {
        "warnings": warnings,
        "rows": rows,
        "records": [record.as_dict() for record in records],
    }


def aggregate_appendix_g_table(runs_root: Path, output_dir: Path) -> Dict[str, Any]:
    section_root = runs_root / "appendix_g"
    experiments = [
        ("gpt5_vs_gpt5_codex", "Experiment 1: Generalist vs. Specialist"),
        ("gpt5_codex_vs_codex_cli", "Experiment 2: Specialist vs. Agentic Framework"),
    ]

    all_rows: List[Dict[str, Any]] = []
    all_records: List[Dict[str, Any]] = []
    warnings: List[str] = []
    run_counts: Dict[str, int] = {}

    for key, title in experiments:
        run_dirs = sorted(path for path in (section_root / key).glob("run_*") if path.is_dir())
        run_counts[key] = len(run_dirs)
        payload = _aggregate_matchup(run_dirs, title)
        warnings.extend(payload["warnings"])
        all_rows.extend(payload["rows"])
        all_records.extend(payload["records"])

    markdown = "# Table 9 Aggregation\n\n"
    for title in [item[1] for item in experiments]:
        markdown += f"## {title}\n\n"
        subset = [row for row in all_rows if row["experiment"] == title]
        markdown += _render_markdown_table(
            [
                "Agent",
                "Win Rate",
                "Avg. Score",
                "Avg. Credit Consumed",
                "Attempted Problems",
                "Submission Precision (%)",
            ],
            [
                [
                    row["agent"],
                    f"{row['win_rate']:.0f}%",
                    _format_decimal(row["avg_score"]["mean"], 2),
                    _format_credit_short(row["avg_credit_consumed"]),
                    _format_decimal(row["attempted_problems"]["mean"], 2),
                    _format_decimal(row["submission_precision"]["mean"], 2),
                ]
                for row in subset
            ],
        )
        markdown += "\n"

    if warnings:
        markdown += "Warnings:\n"
        for warning in warnings:
            markdown += f"- `{warning}`\n"

    csv_rows = [
        {
            "experiment": row["experiment"],
            "agent": row["agent"],
            "runs_count": row["runs_count"],
            "win_rate": _format_decimal(row["win_rate"], 2),
            "avg_score_mean": _format_decimal(row["avg_score"]["mean"], 2),
            "avg_score_std": _format_decimal(row["avg_score"]["std"], 2),
            "avg_credit_mean": _format_decimal(row["avg_credit_consumed"]["mean"], 2),
            "avg_credit_std": _format_decimal(row["avg_credit_consumed"]["std"], 2),
            "attempted_problems_mean": _format_decimal(row["attempted_problems"]["mean"], 2),
            "attempted_problems_std": _format_decimal(row["attempted_problems"]["std"], 2),
            "submission_precision_mean": _format_decimal(row["submission_precision"]["mean"], 2),
            "submission_precision_std": _format_decimal(row["submission_precision"]["std"], 2),
        }
        for row in all_rows
    ]

    payload = {
        "section": "table_9_appendix_g",
        "source_root": str(section_root),
        "run_counts": run_counts,
        "warnings": warnings,
        "rows": all_rows,
        "records": all_records,
    }
    artifacts = _save_json_csv_md(
        payload,
        output_dir=output_dir,
        stem="table_9_appendix_g",
        csv_rows=csv_rows,
        csv_fields=list(csv_rows[0].keys()) if csv_rows else [
            "experiment",
            "agent",
            "runs_count",
            "win_rate",
            "avg_score_mean",
            "avg_score_std",
            "avg_credit_mean",
            "avg_credit_std",
            "attempted_problems_mean",
            "attempted_problems_std",
            "submission_precision_mean",
            "submission_precision_std",
        ],
        markdown=markdown,
    )
    payload["artifacts"] = artifacts
    return payload


def aggregate_paper_runs(runs_root: Path, output_dir: Path) -> Dict[str, Any]:
    main_payload = aggregate_main_table(runs_root, output_dir)
    self_play_payload = aggregate_self_play(runs_root, output_dir)
    appendix_b_payload = aggregate_appendix_b_table(runs_root, output_dir)
    appendix_b_extended_payload = aggregate_appendix_b_extended(runs_root, output_dir)
    appendix_g_payload = aggregate_appendix_g_table(runs_root, output_dir)

    manifest = {
        "source_root": str(runs_root),
        "output_dir": str(output_dir),
        "generated_sections": {
            "table_8_main": main_payload.get("artifacts", {}),
            "section_4_3_self_play": self_play_payload.get("artifacts", {}),
            "table_2_appendix_b": appendix_b_payload.get("artifacts", {}),
            "appendix_b_extended": appendix_b_extended_payload.get("artifacts", {}),
            "table_9_appendix_g": appendix_g_payload.get("artifacts", {}),
        },
        "warnings": (
            main_payload.get("warnings", [])
            + self_play_payload.get("warnings", [])
            + appendix_b_payload.get("warnings", [])
            + appendix_b_extended_payload.get("warnings", [])
            + appendix_g_payload.get("warnings", [])
        ),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    return manifest
