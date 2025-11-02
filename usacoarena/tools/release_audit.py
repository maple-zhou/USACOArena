from __future__ import annotations

import csv
import json
import subprocess
import sys
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import readme_checks


REQUIRED_CHECKLIST_SECTIONS: tuple[str, ...] = (
    "## Documentation",
    "## Testing",
    "## Security",
    "## Packaging",
    "## Communication",
)

IGNORED_SEGMENTS = (
    ".venv/",
    "__pycache__",
    "logs/",
    "competition_results",
    "competitor_results",
    "tests/fixtures/",
)


@dataclass
class AuditResult:
    status: str
    readme: Dict[str, Any]
    release_checklist: Dict[str, Any]
    artifact_sweep: Dict[str, Any]
    secret_scan: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "readme": self.readme,
            "release_checklist": self.release_checklist,
            "artifact_sweep": self.artifact_sweep,
            "secret_scan": self.secret_scan,
        }


def validate_release_checklist(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.exists():
        return ["Missing docs/release/release-checklist.md"]

    content = path.read_text(encoding="utf-8")
    for section in REQUIRED_CHECKLIST_SECTIONS:
        if section not in content:
            errors.append(f"release-checklist.md is missing required section: {section}")

    checkbox_total = content.count("- [ ]")
    if checkbox_total < len(REQUIRED_CHECKLIST_SECTIONS):
        errors.append("Each section must contain at least one checklist item (- [ ])")

    if "artifacts.csv" not in content:
        errors.append("release-checklist.md must reference artifacts.csv")

    return errors


def _read_artifacts(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError("Missing docs/release/artifacts.csv")

    with path.open(encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        expected_fields = ["path", "action", "reason", "replacement", "reviewer"]
        if reader.fieldnames != expected_fields:
            raise ValueError("artifacts.csv header does not match the expected format")
        return list(reader)


def evaluate_artifacts(project_root: Path, path: Path) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"errors": [], "items": []}

    try:
        rows = _read_artifacts(path)
    except FileNotFoundError as exc:
        summary["errors"].append(str(exc))
        return summary
    except ValueError as exc:  # header mismatch
        summary["errors"].append(str(exc))
        return summary

    for row in rows:
        artifact_path = (project_root / row["path"]).resolve()
        action = row["action"].strip().lower()

        exists = artifact_path.exists()
        summary["items"].append({"path": str(artifact_path), "action": action, "exists": exists})

        if action == "removed" and exists:
            summary["errors"].append(f"File marked as removed still exists: {artifact_path}")
        if action == "kept" and not exists:
            summary["errors"].append(f"File marked as kept is missing: {artifact_path}")

    return summary


def run_secret_scan(project_root: Path, *, ignored_segments: Iterable[str] = IGNORED_SEGMENTS) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "detect_secrets",
        "scan",
        "--all-files",
        str(project_root),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    stdout = proc.stdout.strip()
    findings: List[Dict[str, Any]] = []
    raw: Dict[str, Any] = {}

    if stdout:
        try:
            raw = json.loads(stdout)
        except json.JSONDecodeError:
            raw = {"error": "Failed to parse detect-secrets output", "stdout": stdout}
    else:
        raw = {"error": "detect-secrets produced no output", "stderr": proc.stderr}

    results = raw.get("results", {}) if isinstance(raw, dict) else {}
    for filename, secrets in results.items():
        if any(segment in filename for segment in ignored_segments):
            continue
        for secret in secrets:
            findings.append(
                {
                    "filename": str((project_root / filename).resolve()),
                    "type": secret.get("type"),
                    "line_number": secret.get("line_number"),
                }
            )

    return {
        "returncode": proc.returncode,
        "findings": findings,
        "raw": raw,
        "stderr": proc.stderr.strip(),
    }


def run_audit(
    project_root: Path,
    *,
    include_secret_scan: bool = True,
    include_readme_lint: bool = True,
    include_checklist: bool = True,
    include_artifact_sweep: bool = True,
    scan_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    project_root = project_root.resolve()

    readme_result: Dict[str, Any] = {"errors": []}
    if include_readme_lint:
        readme_errors = readme_checks.validate_readme(project_root / "README.md")
        readme_result["errors"] = readme_errors

    checklist_result: Dict[str, Any] = {"errors": []}
    if include_checklist:
        checklist_path = project_root / "docs" / "release" / "release-checklist.md"
        checklist_result["errors"] = validate_release_checklist(checklist_path)

    artifact_result: Dict[str, Any] = {"errors": [], "items": []}
    if include_artifact_sweep:
        artifact_path = project_root / "docs" / "release" / "artifacts.csv"
        artifact_result = evaluate_artifacts(project_root, artifact_path)

    secret_result: Dict[str, Any] = {"findings": [], "returncode": None, "stderr": ""}
    if include_secret_scan:
        target = (scan_root or project_root).resolve()
        ignored = IGNORED_SEGMENTS if scan_root is None else ()
        secret_result = run_secret_scan(target, ignored_segments=ignored)

    status = "passed"
    for section in (readme_result, checklist_result, artifact_result):
        if section.get("errors"):
            status = "failed"
    if include_secret_scan and secret_result.get("findings"):
        status = "failed"
    if include_secret_scan and secret_result.get("returncode") not in (0, None):
        status = "failed"

    audit_result = AuditResult(
        status=status,
        readme=readme_result,
        release_checklist=checklist_result,
        artifact_sweep=artifact_result,
        secret_scan=secret_result,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(audit_result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    return audit_result.to_dict()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run USACOArena release audit checks")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root (defaults to current working directory)",
    )
    parser.add_argument(
        "--scan-root",
        type=Path,
        help="Directory to scan with detect-secrets (defaults to project root)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the audit result to a JSON file",
    )
    parser.add_argument(
        "--no-secret-scan",
        action="store_true",
        help="Skip secret scanning (not recommended except for debugging)",
    )
    parser.add_argument(
        "--no-readme",
        action="store_true",
        help="Skip README structural checks",
    )
    parser.add_argument(
        "--no-checklist",
        action="store_true",
        help="Skip release-checklist validation",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Skip artifacts.csv validation",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    report = run_audit(
        project_root=args.project_root,
        include_secret_scan=not args.no_secret_scan,
        include_readme_lint=not args.no_readme,
        include_checklist=not args.no_checklist,
        include_artifact_sweep=not args.no_artifacts,
        scan_root=args.scan_root,
        output_path=args.output,
    )
    if report["status"] == "passed":
        print("Release audit passed ✅")
        return 0

    print("Release audit reported issues ❌")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
