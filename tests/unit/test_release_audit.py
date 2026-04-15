from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from usacoarena.tools import release_audit


pytestmark = pytest.mark.skipif(
    shutil.which("detect-secrets") is None,
    reason="detect-secrets CLI not installed",
)


def test_release_audit_detects_fixture_secret() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "tests" / "fixtures" / "release_audit"

    result = release_audit.run_audit(
        project_root=repo_root,
        include_readme_lint=False,
        include_checklist=False,
        include_artifact_sweep=False,
        scan_root=fixture_root,
    )

    assert (
        result["secret_scan"]["findings"]
    ), "Fixture secrets should be detected"
    assert (
        result["status"] == "failed"
    ), "Audit status should be failed when secrets are detected"
