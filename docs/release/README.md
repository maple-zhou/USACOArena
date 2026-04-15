# USACOArena Release Documentation

This directory tracks the public open-source release process for the ICLR 2026 companion codebase.

## Structure Overview

- `release-checklist.md`: pre-release checklist for docs, testing, security, packaging, and communication
- `artifacts.csv`: inventory of removed or intentionally retained release artifacts
- `../security/`: secret-scan and release-audit outputs

## Release Expectations

Before publishing:

1. verify the README and `docs/paper_reproduction.md`
2. verify the dataset guide and Hydro deployment / addon installation guide
3. run the release audit and tests
4. confirm no private API endpoint or key remains in tracked files
5. verify that the published Hydro addon package, Hydro problemset zip, and local resource dataset links in the docs still resolve to the intended release artifacts
