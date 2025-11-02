# USACOArena Release Checklist

> Complete each item before publishing and log file adjustments in `docs/release/artifacts.csv`.

## Documentation
- [ ] README and `docs/quickstart.md` are updated with the latest experimental configuration.
- [ ] `docs/release/artifacts.csv` lists every added/removed file with justification and archive location.
- [ ] `docs/release/logs/<date>.md` captures the current dry run (commands, outputs, screenshots).

## Testing
- [ ] Execute the Quick Start in a clean environment (including judge service or fallback) and finish within 30 minutes.
- [ ] Run `uv run pytest`, `uv run ruff check`, `uv run black --check`, and `uv run mypy`, storing the outputs.
- [ ] Add or update regression tests when configuration or scripts change.

## Security
- [ ] Run `./scripts/release_audit.sh --include-secret-scan` and review the generated report.
- [ ] Refresh `.secrets.baseline`, marking high-severity findings as `resolved` or `false_positive` with rationale.
- [ ] Confirm the repository and linked assets contain no personal or unauthorized data.

## Packaging
- [ ] Execute `uv sync --frozen` and commit the updated `uv.lock`.
- [ ] Ensure release artifacts exclude logs, temporary data, and generated files; update `.gitignore` if needed.
- [ ] Verify the `usacoarena` package builds via `uv build` (if publishing to PyPI).

## Communication
- [ ] Prepare release notes summarizing changes, compatibility considerations, and upgrade guidance.
- [ ] Update the Release Checklist summary in the README with the publication date and owner.
- [ ] Notify collaborators or Workshop review channels and provide the latest PDF plus runbook.

Have two maintainers cross-review this checklist and attach signatures or comments to the PR/release notes once complete.
