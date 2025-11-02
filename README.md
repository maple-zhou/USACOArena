# USACOArena

USACOArena is a benchmarking and analytics platform for multi-agent programming competitions. This
repository hosts the official open-source implementation that accompanies the NeurIPS 2025 LAW
Workshop submission *USACOArena: Cost-Aware Evaluation of Agentic Coding Capabilities of
Multi-Agent Systems*. The release focuses on reproducibility, publication-readiness, and automated
safety auditing for the research community.

> For citation details, see the **Citation** section below.

## Project Overview

- Reproducible Python 3.10 environment management powered by `uv`.
- Modular services for competition orchestration, judging, and live visualization.
- Cost-aware analytics designed to compare agent strategies on efficiency and quality.
- Built-in release audit scripts that keep user-facing documentation concise and leak-free.

## Key Highlights

1. **Paper Companion** – Documentation and repository layout mirror the NeurIPS 2025 LAW Workshop
   manuscript for straightforward review and replication.
2. **Rapid Onboarding** – Environment setup and a demo competition can be completed in minutes (see
   Quick Start).
3. **Release Ready** – Includes a publication checklist, artifact tracking, and automated secret
   scanning.
4. **Data Accessibility** – Documents approved data sources, usage terms, and fallback options for
   constrained environments.

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/maple-zhou/USACOArena.git
   cd USACOArena
   ```
2. **Install uv and sync dependencies**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv sync --dev
   ```
3. **Optional – align Git signature for releases**
   ```bash
   git config user.name "maple-zhou"
   git config user.email "zhoulingfeng@sjtu.edu.cn"
   ```

## Quick Start

> For a full walkthrough—including judge deployment and UI usage—refer to
> [`docs/quickstart.md`](docs/quickstart.md).

1. **Launch the local competition server**
   ```bash
   uv run python -m usacoarena.main --port 5000 --debug
   ```
2. **Run a sample competition**
   ```bash
   uv run python scripts/run_competition.py \
     --competition-title "Demo Match" \
     --max-tokens-per-participant 20000 \
     --port 5000
   ```
3. **Review results** – Output is written to `logs/` and the terminal; the Quick Start guide explains
   the optional UI.
4. **Prepare datasets** – Follow the licensing notes at the end of this README to source the official
   USACO problem sets.

## Release Checklist Overview

Complete the following before publishing a new release:

1. **Documentation** – Update this README, `docs/release/release-checklist.md`, and
   `docs/quickstart.md`.
2. **Dependency freeze** – Run `uv sync --frozen` and commit the updated `uv.lock`.
3. **Dry run** – Execute the Quick Start end-to-end and record results under `docs/release/logs/<date>.md`.
4. **Security audit** – Run `./scripts/release_audit.sh` to generate the secret scan and documentation
   checks; reports are saved under `docs/security/`.
5. **Artifact tracking** – Log added or removed files in `docs/release/artifacts.csv`, including
   rationale and owner.

The full checklist is available in [`docs/release/release-checklist.md`](docs/release/release-checklist.md).

### Repository Layout (docs/)

```text
docs/
├── quickstart.md
├── release/
│   ├── README.md
│   ├── release-checklist.md
│   ├── artifacts.csv
│   └── logs/
└── security/
    └── (scan reports)
```

## Citation

If you build upon USACOArena in your research, please cite:

**Text Citation**

> Zhou, L., et al. (2025). *USACOArena: Cost-Aware Evaluation of Agentic Coding Capabilities of
> Multi-Agent Systems*. NeurIPS 2025 LAW Workshop.

**BibTeX**

```bibtex
@inproceedings{zhou2025usacoarena,
  title     = {USACOArena: Cost-Aware Evaluation of Agentic Coding Capabilities of Multi-Agent Systems},
  author    = {Lingfeng Zhou and Collaborators},
  booktitle = {Proceedings of the NeurIPS 2025 Workshop on Legal Meets AI (LAW)},
  year      = {2025},
  url       = {https://sites.google.com/view/law-2025},
  note      = {See repository for code and experimental setup}
}
```

**PDF** – [_NeurIPS_25_Workshop_LAW__USACOArena.pdf](../_NeurIPS_25_Workshop_LAW__USACOArena.pdf)

## Support & License

- **License** – MIT; see [`LICENSE`](LICENSE).
- **Issues** – Report bugs, feature requests, or security concerns via GitHub Issues.
- **Data usage** – Follow original licensing terms for USACO problems and samples (details in the
  Quick Start appendix).
- **Security audit** – Run `./scripts/release_audit.sh --output docs/security/scan-latest.json`.
  Baseline data lives in [`.secrets.baseline`](.secrets.baseline); an example report is provided in
  [`docs/security/scan-template.json`](docs/security/scan-template.json).
- **Security contact** – Submit audit reports or disclosures to `zhoulingfeng@sjtu.edu.cn`.

---

*This README is intentionally capped well below 200 lines to keep key information immediately
accessible to reviewers and practitioners.*
