from __future__ import annotations

from pathlib import Path
from typing import Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
README_PATH = PROJECT_ROOT / "README.md"

REQUIRED_SECTIONS: tuple[str, ...] = (
    "## Paper Companion",
    "## Installation",
    "## Quick Start",
    "## Citation",
    "## Repository Layout",
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
        (
            "Credit-Budgeted ICPC-Style Coding: When Agents Must Pay for Every Decision",
            "README must reference the ICLR 2026 paper title explicitly.",
        ),
        (
            "Published as a conference paper at ICLR 2026",
            "README must mention the ICLR 2026 publication status explicitly.",
        ),
        ("```bibtex", "README must include a BibTeX citation block."),
        (
            "docs/paper_reproduction.md",
            "README must point readers to the full paper reproduction guide.",
        ),
        (
            "https://github.com/maple-zhou/USACOArena",
            "README must reference the public USACOArena repository URL.",
        ),
        (
            "https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDLk840K7kKQIcantsdu2VsAXUUVQsuCxqbkYO0L0sJy0U?e=L6gXuD",
            "README must include the released Hydro addon package link.",
        ),
        (
            "https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDuOy0L6BSJT4c33LH67LEAAYozwuSaGg7mpTgsp2OSTp4?e=0hXevh",
            "README must include the released Hydro problemset zip link.",
        ),
        (
            "https://1drv.ms/u/c/1ef7b7bac0da57e6/IQCzXH4s4Ab7RJiSkpzbkO5eAdwrEzRBLW05RTlQyWknkLo?e=hSjB5X",
            "README must include the released local resource dataset link.",
        ),
    )
    errors: List[str] = []
    for token, message in keywords:
        if token not in content:
            errors.append(message)
    return errors


def _check_length(lines: list[str]) -> List[str]:
    if len(lines) > 260:
        return [f"README.md has {len(lines)} lines; keep the file within 260 lines."]
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
