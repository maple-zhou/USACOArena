from __future__ import annotations

import csv
from pathlib import Path


CHECKLIST_PATH = Path(__file__).resolve().parents[2] / "docs" / "release" / "release-checklist.md"
ARTIFACTS_PATH = Path(__file__).resolve().parents[2] / "docs" / "release" / "artifacts.csv"


def test_release_checklist_has_required_sections() -> None:
    content = CHECKLIST_PATH.read_text(encoding="utf-8")

    categories = (
        "## Documentation",
        "## Testing",
        "## Security",
        "## Packaging",
        "## Communication",
    )

    for category in categories:
        assert (
            category in content
        ), f"release-checklist.md is missing required section: {category}"

    checkbox_count = content.count("- [ ]")
    assert (
        checkbox_count >= len(categories)
    ), "Each category must contain at least one checklist item"

    assert (
        "artifacts.csv" in content
    ), "Checklist must reference artifacts.csv to track file changes"


def test_artifacts_csv_has_expected_headers() -> None:
    with ARTIFACTS_PATH.open(encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        assert header == ["path", "action", "reason", "replacement", "reviewer"], "artifacts.csv header must match the expected format"
        rows = list(reader)
        assert rows, "artifacts.csv must record at least one row to document changes"
