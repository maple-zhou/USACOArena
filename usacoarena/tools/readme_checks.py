from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
README_PATH = PROJECT_ROOT / "README.md"

REQUIRED_SECTIONS: tuple[str, ...] = (
    "## Project Overview",
    "## Key Highlights",
    "## Installation",
    "## Quick Start",
    "## Release Checklist Overview",
    "## Citation",
    "## Support & License",
)


def _check_required_sections(content: str) -> List[str]:
    errors: List[str] = []
    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"Missing required section: {section}")
    return errors


def _check_keywords(content: str) -> List[str]:
    keywords: Iterable[tuple[str, str]] = (
        ("NeurIPS 2025 LAW Workshop", "NeurIPS 2025 LAW Workshop must be referenced explicitly."),
        ("```bibtex", "README must include a BibTeX citation block."),
        ("_NeurIPS_25_Workshop_LAW__USACOArena.pdf", "README must link to the accompanying PDF."),
    )
    errors: List[str] = []
    for token, message in keywords:
        if token not in content:
            errors.append(message)
    return errors


def _check_length(lines: list[str]) -> List[str]:
    if len(lines) > 200:
        return [f"README.md has {len(lines)} lines; keep the file within 200 lines."]
    return []


def validate_readme(path: Path = README_PATH) -> list[str]:
    """Return a list of validation errors for README.md."""

    if not path.exists():
        return [f"README file not found: {path}"]

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    errors: List[str] = []
    errors.extend(_check_required_sections(content))
    errors.extend(_check_keywords(content))
    errors.extend(_check_length(lines))

    return errors


def main() -> int:
    errors = validate_readme()
    if errors:
        for err in errors:
            print(f"[ERROR] {err}")
        return 1

    print("README validation passed ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
