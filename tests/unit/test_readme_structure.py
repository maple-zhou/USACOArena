from __future__ import annotations

from usacoarena.tools import readme_checks


def test_readme_has_release_ready_structure() -> None:
    errors = readme_checks.validate_readme()
    assert not errors, f"README validation failed: {'; '.join(errors)}"
