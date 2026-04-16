# USACOArena

USACOArena is the official open-source companion codebase for the ICLR 2026 paper *Credit-Budgeted ICPC-Style Coding: When Agents Must Pay for Every Decision*. This release keeps the original competition server, agent integration layer, paper configs, reporting utilities, and reproduction scripts, while replacing the legacy self-maintained OJ stack with a Hydro-based judging and problem-management workflow.

Paper status: Published as a conference paper at ICLR 2026.

## Paper Companion

- Paper: [*Credit-Budgeted ICPC-Style Coding: When Agents Must Pay for Every Decision*](https://arxiv.org/abs/2604.10182)
- Authors: Lingfeng Zhou, Junhao Shi, Jin Gao, Dequan Wang
- Repository: `https://github.com/maple-zhou/USACOArena`
- Judge infrastructure: [Hydro](https://github.com/hydro-dev/Hydro)

## Installation

1. Clone this repository:

```bash
git clone https://github.com/maple-zhou/USACOArena.git
cd USACOArena
```

2. Install `uv` and sync Python dependencies:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --dev
```

3. Download the released artifacts:

- Hydro addon package: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDLk840K7kKQIcantsdu2VsAXUUVQsuCxqbkYO0L0sJy0U?e=L6gXuD`
- Hydro problemset zip: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDuOy0L6BSJT4c33LH67LEAAYozwuSaGg7mpTgsp2OSTp4?e=0hXevh`
- Local resource dataset: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQCzXH4s4Ab7RJiSkpzbkO5eAdwrEzRBLW05RTlQyWknkLo?e=hSjB5X`

The released Hydro problemset has already been refreshed to include the latest publicly available USACO 2025-2026 season contests as well. At the moment, the only missing piece is the newest March open contest, because the official problem data has not been published yet.

4. Extract the local resource dataset into the repository root. This archive is for hint corpora, textbook resources, and guide content. It is not the Hydro problemset zip used for judging:

```text
dataset/
  corpuses/
    cpbook_v2.json
    USACO_strategy.json
  datasets/
    USACO_guide.json
    usaco_2025_dict.json  # optional compatibility metadata
```

See `docs/dataset.md` for the exact layout and validation commands.

5. Prepare Hydro as the judging backend. The recommended flow is:

```bash
git clone https://github.com/hydro-dev/Hydro.git ../Hydro
```

Then follow `docs/oj.md` to:

- install and start Hydro
- install the released `hydro_plugin_usacoarena` addon package
- configure the addon token and mounted API base
- import the released Hydro problemset zip

## Quick Start

1. Start Hydro and make sure the addon API is reachable. With a default local Hydro deployment, USACOArena expects:

```text
http://127.0.0.1:8888/usacoarena/api/health
```

2. Start the USACOArena API server:

```bash
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --host 0.0.0.0 \
  --port 5000 \
  --hydro-base-url http://127.0.0.1:8888
```

If the Hydro addon uses a token, also pass:

```bash
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --hydro-base-url http://127.0.0.1:8888 \
  --hydro-api-token "<token>"
```

3. In another terminal, start the management UI:

```bash
uv run python -m usacoarena.ui.app \
  --host 127.0.0.1 \
  --port 5500
```

4. Export official-provider environment variables. All checked-in public configs intentionally keep `api_key` blank:

```bash
export OPENAI_BASE_URL="https://api.openai.com"
export OPENAI_API_KEY=""
export GEMINI_BASE_URL="https://generativelanguage.googleapis.com/openai"
export GEMINI_API_KEY=""
export ANTHROPIC_BASE_URL="https://api.anthropic.com"
export ANTHROPIC_API_KEY=""
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_API_KEY=""
export MOONSHOT_BASE_URL="https://api.moonshot.ai"
export MOONSHOT_API_KEY=""
export DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode"
export DASHSCOPE_API_KEY=""
export GLM_BASE_URL="https://open.bigmodel.cn/api/paas"
export GLM_API_KEY=""
```

5. Run a minimal sanity benchmark:

```bash
mkdir -p runs/sanity
uv run python scripts/run_competition.py \
  --competition-config config/paper/competition/main_alpha0.json \
  --competitors-config config/paper/competitors/three_model_sanity.json \
  --problem-ids config/paper/problems/qualification_february_2025.json \
  --log-dir runs/sanity/logs \
  --competition-id-output runs/sanity/competition_id.txt
```

6. Export the final intelligence report:

```bash
COMPETITION_ID="$(cat runs/sanity/competition_id.txt)"
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --output-dir runs/sanity/reports
```

7. Export the metric timeline:

```bash
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --interval 10 \
  --output-dir runs/sanity/timeline
```

## Citation

If you use USACOArena or its public experiment configs, please cite:

```bibtex
@inproceedings{zhou2026creditbudgeted,
  title     = {Credit-Budgeted ICPC-Style Coding: When Agents Must Pay for Every Decision},
  author    = {Lingfeng Zhou and Junhao Shi and Jin Gao and Dequan Wang},
  booktitle = {The Fourteenth International Conference on Learning Representations},
  year      = {2026},
  note      = {Published as a conference paper at ICLR 2026},
  eprint    = {2604.10182},
  archivePrefix = {arXiv},
  primaryClass = {cs.AI},
  url       = {https://github.com/maple-zhou/USACOArena}
}
```

## Repository Layout

- `config/paper/competition/`: competition-rule configs used in the paper
- `config/paper/competitors/`: public competitor configs used in the paper
- `config/paper/problems/`: contest problem lists for main, qualification, and appendix experiments
- `hydro_plugin_usacoarena/`: Hydro addon source that exposes machine-facing APIs for USACOArena
- `scripts/hydro/normalize_hydro_problemset.py`: injects alias tags into a Hydro problemset zip
- `scripts/run_competition.py`: standard multi-model competition entrypoint
- `scripts/run_competition_for_codex.py`: competition setup plus Codex participant registration
- `scripts/benchmark_cli.py`: benchmark setup / report / smoke CLI
- `docs/oj.md`: Hydro deployment, addon installation, and problemset import guide
- `docs/quickstart.md`: end-to-end local setup guide
- `docs/paper_reproduction.md`: no-skip paper reproduction guide

## Support & License

- Code license: MIT, see `LICENSE`
- Released artifact links are listed above and deployment details live in `docs/oj.md`, `docs/dataset.md`, and `docs/quickstart.md`
- Dataset and problem content usage must continue to follow the original licensing terms of the released USACO materials and third-party corpora; see `docs/dataset.md`
- For exact experiment commands and paper-aligned reproduction flow, start with `docs/paper_reproduction.md`
- For release audit scope and packaging expectations, see `docs/release/`
