#!/usr/bin/env python
"""Lint README structure to ensure release compliance."""

from __future__ import annotations

from usacoarena.tools import readme_checks


def main() -> int:
    return readme_checks.main()


if __name__ == "__main__":
    raise SystemExit(main())
