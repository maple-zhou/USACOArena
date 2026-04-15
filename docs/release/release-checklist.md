# USACOArena Release Checklist

> Complete each item before publishing and log file adjustments in `docs/release/artifacts.csv`.

## Documentation
- [ ] README clearly states this repository is the companion codebase for the accepted ICLR 2026 paper and includes a BibTeX citation.
- [ ] `docs/paper_reproduction.md` covers all experiments in the main paper and appendix with copy-pasteable commands.
- [ ] `docs/dataset.md`, `docs/oj.md`, and `docs/metrics.md` match the released dataset archive, Hydro addon workflow, and current reporting scripts.
- [ ] README and docs point to the current public download links for the Hydro addon package, Hydro problemset zip, and local resource dataset.
- [ ] `docs/release/artifacts.csv` lists every added/removed file with justification and archive location.

## Testing
- [ ] Execute the quick start end to end against the released dataset layout, a local Hydro deployment, the USACOArena addon, and the normalized problemset zip.
- [ ] Run `uv run pytest` and store the output.
- [ ] Run `python -m usacoarena.main --help`, `python -m usacoarena.ui.app --help`, `python scripts/benchmark_cli.py --help`, and `python scripts/export_metrics_timeline.py --help`.
- [ ] Add or update regression tests when config normalization, README validation, Hydro integration, or release audit behavior changes.

## Security
- [ ] Run `./scripts/release_audit.sh --output docs/security/scan-latest.json` and review the generated report.
- [ ] Confirm all public configs use official API base URLs and blank checked-in API keys.
- [ ] Confirm no private relay URLs, active credentials, personal data, or unauthorized artifacts remain in tracked files.

## Packaging
- [ ] Confirm the public release excludes generated logs, local run outputs, and deleted private config artifacts.
- [ ] Ensure the released dataset archive expands into the documented directory structure without code changes.
- [ ] Ensure the Hydro addon package and normalized Hydro problemset zip are produced and stored at the documented external release locations.
- [ ] Ensure the published external links still serve the expected addon package, problemset zip, and local resource dataset.
- [ ] Ensure Hydro upstream plus this repository can be deployed together using the published instructions.

## Communication
- [ ] Prepare release notes summarizing the open-source release scope, Hydro dependency boundary, experiment coverage, and credential handling policy.
- [ ] Point users to `docs/paper_reproduction.md` for exact experiment commands and to `docs/oj.md` for Hydro deployment and addon installation.
