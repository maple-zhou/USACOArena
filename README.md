# USACOArena

USACOArena is a benchmarking and analytics platform for multi-agent programming competitions. This
repository hosts the official open-source implementation that accompanies the [NeurIPS 2025 LAW
Workshop](https://sites.google.com/view/law-2025) submission *Credit-Budgeted ICPC-Style Coding: When LLM Agents Must Pay for Every Decision*.

> For citation details, see the [Citation*](#citation) section below.

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/maple-zhou/USACOArena.git
   cd USACOArena
   ```
2. **Install uv and sync dependencies**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv sync
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
4. **Prepare datasets** – Download the official USACO archive from [this link](https://1drv.ms/u/c/1ef7b7bac0da57e6/EScfKJ-Fm9hAorr5gByWMUQBHa0pwbi-HmFBi7XFSF3RiA?e=jOSsYO), extract it into the repository root, and review the licensing notice in Support & License.

## Citation

If you build upon USACOArena in your research, please cite:

**Text Citation**

<!-- > Zhou, L., et al. (2025). *USACOArena: Cost-Aware Evaluation of Agentic Coding Capabilities of
> Multi-Agent Systems*. NeurIPS 2025 LAW Workshop. -->

**BibTeX**

<!-- ```bibtex
@inproceedings{zhou2025usacoarena,
  title     = {USACOArena: Cost-Aware Evaluation of Agentic Coding Capabilities of Multi-Agent Systems},
  author    = {Lingfeng Zhou and Collaborators},
  booktitle = {Proceedings of the NeurIPS 2025 Workshop on Legal Meets AI (LAW)},
  year      = {2025},
  url       = {https://sites.google.com/view/law-2025},
  note      = {See repository for code and experimental setup}
}
``` -->

## Support & License

- **License** – MIT; see [`LICENSE`](LICENSE).
- **Issues** – Report bugs, feature requests, or security concerns via GitHub Issues.
- **Data usage** – Follow original licensing terms for USACO problems and samples (details in the
  Quick Start appendix).
- **Security audit** – Run `./scripts/release_audit.sh --output docs/security/scan-latest.json`.
  Baseline data lives in [`.secrets.baseline`](.secrets.baseline); an example report is provided in
  [`docs/security/scan-template.json`](docs/security/scan-template.json).
- **Security contact** – Submit audit reports or disclosures to `zhoulingfeng@sjtu.edu.cn`.
