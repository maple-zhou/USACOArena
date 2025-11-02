# USACOArena Quick Start Guide

This guide extends the README with a full end-to-end walkthrough so researchers can reproduce the
paper environment in roughly 30 minutes.

## 1. Environment Setup

1. Install dependencies
   ```bash
   uv sync --dev
   ```
2. (Optional) Activate the virtual environment in your shell:
   ```bash
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

## 2. Data Resources

- **USACO dataset** – Download the archive using the link listed in the README and extract it to the
  repository root.
- **Online Judge** – Use the companion repository [`USACOArena_online_judge`](https://github.com/maple-zhou/USACOArena_online_judge); follow its README to
  build the Docker image and run it on `localhost:10086`.

## 3. Launch Services and a Competition

1. **Start the web console**
   ```bash
   uv run python -m usacoarena.ui.app --host 0.0.0.0 --port 5500
   ```
   Visit `http://localhost:5500/ui` to manage competition instances.

2. **Command-line demo**
   ```bash
   uv run python -m usacoarena.main --port 5000 --debug
   uv run python scripts/run_competition.py      --competition-title "Demo Match"      --max-tokens-per-participant 20000      --port 5000
   ```

3. **Inspect results**
   - Logs are written to directories under `logs/competition_*`.
   - Aggregate metrics are available through the UI or `STATISTICS_UPDATE_SUMMARY.md`.

## 4. Release Dry Run

1. Check off tasks in `docs/release/release-checklist.md` as you complete them.
2. Run `./scripts/release_audit.sh` and confirm the latest security report appears in
   `docs/security/`.
3. Append the dry-run record to `docs/release/logs/<date>.md` (for example,
   `docs/release/logs/2025-11-01.md`).

## 5. Frequently Asked Questions

- **Dependency installation is slow** – Increase `UV_HTTP_TIMEOUT=120` or prefetch packages with
  `uv lock --offline` when operating offline.
- **Judge service is unavailable** – Follow the fallback strategy noted in the README Release
  Checklist summary to rehearse the competition flow without remote judging.
- **Logs or data grow too large** – Tune retention in `config/` and use
  `scripts/convert_all_json_to_csv.sh` to compress archives.

After completing these steps, the experimental environment is ready for further exploration of
multi-agent strategies.
