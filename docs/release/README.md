# USACOArena Release Documentation

This directory stores all materials required ahead of a public release, as well as audit artifacts.

## Structure Overview

- `release-checklist.md`: Mandatory pre-release checklist covering documentation, testing, security, packaging, and communication tasks.
- `artifacts.csv`: Inventory of files to keep or remove, with destinations to preserve traceability.
- `logs/`: Dry-run or release execution evidence (commands, outputs, screenshots, etc.).
- `../security/`: Security scan reports for compliance reviews.

## Usage Tips

1. Update `release-checklist.md` and complete the self-audit before preparing a new release.
2. Append evidence for each dry run or official release to the `logs/` subdirectory, ideally using `YYYY-MM-DD.md` filenames.
3. When the repository layout changes, update both `artifacts.csv` and the corresponding sections in the root README.
