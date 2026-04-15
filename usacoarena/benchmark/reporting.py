"""Report renderers for benchmark intelligence outputs."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


CSV_COLUMNS: List[str] = [
    "intelligence_rank",
    "arena_rank",
    "name",
    "participant_id",
    "agent_type",
    "transport",
    "mcp_enabled",
    "is_running",
    "termination_reason",
    "intelligence_score",
    "problem_pass_score",
    "score",
    "solved_problems",
    "attempted_problems",
    "submission_count",
    "accepted_count",
    "consumed_tokens",
    "consumed_credit",
    "delivery_time_seconds",
    "solve_component",
    "efficiency_component",
    "reliability_component",
    "speed_component",
    "coverage_component",
]


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def render_csv(report: Dict[str, Any]) -> str:
    rows = report.get("rows", []) if isinstance(report, dict) else []
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    for row in rows:
        if not isinstance(row, dict):
            continue
        payload = {key: row.get(key, "") for key in CSV_COLUMNS}
        writer.writerow(payload)

    return stream.getvalue()


def render_markdown(report: Dict[str, Any]) -> str:
    competition = report.get("competition", {}) if isinstance(report, dict) else {}
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    rows = report.get("rows", []) if isinstance(report, dict) else []

    lines: List[str] = []
    lines.append(f"# Intelligence Report: {_safe_text(competition.get('title', 'Unknown'))}")
    lines.append("")
    lines.append(f"- Competition ID: `{_safe_text(competition.get('id'))}`")
    lines.append(f"- Generated At: `{_safe_text(report.get('generated_at'))}`")
    lines.append(f"- Participants: `{_safe_text(summary.get('participant_count', 0))}`")
    lines.append(f"- Avg Intelligence Score: `{_safe_text(summary.get('avg_intelligence_score', 0))}`")
    lines.append(f"- Top Participant: `{_safe_text(summary.get('top_participant', 'N/A'))}`")
    lines.append("")
    lines.append("| Rank | Arena Rank | Name | Intelligence | Solve | Efficiency | Reliability | Speed | Coverage |")
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---:|")

    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {intelligence_rank} | {arena_rank} | {name} | {intelligence_score} | "
            "{solve_component} | {efficiency_component} | {reliability_component} | "
            "{speed_component} | {coverage_component} |".format(
                intelligence_rank=_safe_text(row.get("intelligence_rank", "")),
                arena_rank=_safe_text(row.get("arena_rank", "")),
                name=_safe_text(row.get("name", "")),
                intelligence_score=_safe_text(row.get("intelligence_score", "")),
                solve_component=_safe_text(row.get("solve_component", "")),
                efficiency_component=_safe_text(row.get("efficiency_component", "")),
                reliability_component=_safe_text(row.get("reliability_component", "")),
                speed_component=_safe_text(row.get("speed_component", "")),
                coverage_component=_safe_text(row.get("coverage_component", "")),
            )
        )

    return "\n".join(lines) + "\n"


def render_html(report: Dict[str, Any]) -> str:
    competition = report.get("competition", {}) if isinstance(report, dict) else {}
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    rows = report.get("rows", []) if isinstance(report, dict) else []

    header_cells = "".join(f"<th>{col}</th>" for col in CSV_COLUMNS)
    body_rows: List[str] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = "".join(f"<td>{_safe_text(row.get(col, ''))}</td>" for col in CSV_COLUMNS)
        body_rows.append(f"<tr>{cells}</tr>")

    table_body = "\n".join(body_rows)

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>USACOArena Intelligence Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; background: #f9fafb; }}
    .card {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
    h1 {{ margin: 0 0 8px 0; font-size: 24px; }}
    .meta {{ color: #374151; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; }}
    th {{ position: sticky; top: 0; background: #f3f4f6; }}
    .table-wrap {{ overflow: auto; max-height: 70vh; border-radius: 8px; border: 1px solid #e5e7eb; }}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>{_safe_text(competition.get('title', 'USACOArena Intelligence Report'))}</h1>
    <div class=\"meta\">Competition ID: {_safe_text(competition.get('id'))}</div>
    <div class=\"meta\">Generated At: {_safe_text(report.get('generated_at'))}</div>
    <div class=\"meta\">Participants: {_safe_text(summary.get('participant_count', 0))}, Avg Intelligence: {_safe_text(summary.get('avg_intelligence_score', 0))}</div>
  </div>
  <div class=\"table-wrap\">
    <table>
      <thead><tr>{header_cells}</tr></thead>
      <tbody>
      {table_body}
      </tbody>
    </table>
  </div>
</body>
</html>
"""


def save_report_bundle(report: Dict[str, Any], output_dir: Path, file_stem: str = "intelligence") -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{file_stem}.json"
    csv_path = output_dir / f"{file_stem}.csv"
    md_path = output_dir / f"{file_stem}.md"
    html_path = output_dir / f"{file_stem}.html"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path.write_text(render_csv(report), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")

    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
        "html": str(html_path),
    }


def render_by_format(report: Dict[str, Any], fmt: str) -> str:
    normalized = (fmt or "json").strip().lower()
    if normalized == "csv":
        return render_csv(report)
    if normalized in {"md", "markdown"}:
        return render_markdown(report)
    if normalized == "html":
        return render_html(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def rows_for_table(report: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    rows = report.get("rows", []) if isinstance(report, dict) else []
    for row in rows:
        if isinstance(row, dict):
            yield row
