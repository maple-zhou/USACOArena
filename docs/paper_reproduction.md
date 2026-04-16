# Paper Reproduction Guide

This guide reproduces the experiments for the ICLR 2026 paper *Credit-Budgeted ICPC-Style Coding: When Agents Must Pay for Every Decision* using the public release of USACOArena with Hydro as the judging backend.

The guide is intentionally no-skip: every section starts from explicit prerequisites, gives concrete commands, and explains where artifacts are written.

## 1. Shared Prerequisites

Complete these steps once before running any experiment.

### 1.1 Clone the Repository

```bash
git clone https://github.com/maple-zhou/USACOArena.git
cd USACOArena
```

### 1.2 Install Dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --dev
```

### 1.3 Extract the Dataset Archive

Download the released artifacts first:

- Hydro addon package: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDLk840K7kKQIcantsdu2VsAXUUVQsuCxqbkYO0L0sJy0U?e=L6gXuD`
- Hydro problemset zip: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDuOy0L6BSJT4c33LH67LEAAYozwuSaGg7mpTgsp2OSTp4?e=0hXevh`
- Local resource dataset: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQCzXH4s4Ab7RJiSkpzbkO5eAdwrEzRBLW05RTlQyWknkLo?e=hSjB5X`

The released Hydro problemset already includes the latest publicly available USACO 2025-2026 season contests. The only remaining gap is the newest March open contest, because the official problem data is not public yet.

Extract the local resource dataset into the repository root. This is the local hint/textbook/guide resource bundle, not the Hydro problemset zip. Then validate it:

```bash
test -f dataset/datasets/USACO_guide.json
test -f dataset/corpuses/cpbook_v2.json
test -f dataset/corpuses/USACO_strategy.json
```

### 1.4 Start Hydro and Install the Addon

In terminal A:

```bash
git clone https://github.com/hydro-dev/Hydro.git ../Hydro
cd ../Hydro
```

Install Hydro using the official workflow, then extract and add the released addon package:

```bash
tar -xzf usacoarena_hydro_plugin_v0.1.0.tar.gz
hydrooj addon add /path/to/usacoarena_hydro_plugin_v0.1.0/hydro_plugin_usacoarena
```

Restart Hydro after the addon is added.

### 1.5 Import the Problemset

Import the released `usacoarena_hydro_problemset_normalized.zip` through the Hydro admin UI.

### 1.6 Start the USACOArena API Server

In terminal B:

```bash
cd /path/to/USACOArena
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --host 0.0.0.0 \
  --port 5000 \
  --hydro-base-url http://127.0.0.1:8888 \
  --hydro-api-token "<token>"
```

### 1.7 Optional: Start the UI

In terminal C:

```bash
cd /path/to/USACOArena
uv run python -m usacoarena.ui.app \
  --host 127.0.0.1 \
  --port 5500
```

### 1.8 Export Provider Credentials

All public configs use official URLs and blank keys. Set the credentials through environment variables:

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

## 2. Common Reporting Pattern

For any competition run in this guide:

1. create a dedicated output directory
2. run the competition with `--competition-id-output`
3. read the competition ID from the output file
4. export the intelligence report
5. optionally export the timeline

Final report export pattern:

```bash
COMPETITION_ID="$(cat <run_dir>/competition_id.txt)"
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --output-dir <run_dir>/report
```

Timeline export pattern:

```bash
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --interval 10 \
  --output-dir <run_dir>/timeline
```

## 3. Section 4.2 Main Benchmark

Paper setting:

- four contests from the 2024-2025 USACO season
- five runs per contest
- `alpha = 0`
- representative GPT-5-series model: `gpt-5-codex`

Public release configs:

- competition: `config/paper/competition/main_alpha0.json`
- competitors: `config/paper/competitors/main_8_models.json`

### 3.1 December 2024

```bash
for run in 1 2 3 4 5; do
  RUN_DIR="runs/paper/4_2_main/december_2024/run_${run}"
  mkdir -p "$RUN_DIR"
  uv run python scripts/run_competition.py \
    --competition-config config/paper/competition/main_alpha0.json \
    --competitors-config config/paper/competitors/main_8_models.json \
    --problem-ids config/paper/problems/main_december_2024.json \
    --log-dir "$RUN_DIR/logs" \
    --competition-id-output "$RUN_DIR/competition_id.txt"

  COMPETITION_ID="$(cat "$RUN_DIR/competition_id.txt")"
  uv run python scripts/benchmark_cli.py report \
    --api-base http://127.0.0.1:5000 \
    --competition-id "$COMPETITION_ID" \
    --output-dir "$RUN_DIR/report"
done
```

### 3.2 January 2025

```bash
for run in 1 2 3 4 5; do
  RUN_DIR="runs/paper/4_2_main/january_2025/run_${run}"
  mkdir -p "$RUN_DIR"
  uv run python scripts/run_competition.py \
    --competition-config config/paper/competition/main_alpha0.json \
    --competitors-config config/paper/competitors/main_8_models.json \
    --problem-ids config/paper/problems/main_january_2025.json \
    --log-dir "$RUN_DIR/logs" \
    --competition-id-output "$RUN_DIR/competition_id.txt"

  COMPETITION_ID="$(cat "$RUN_DIR/competition_id.txt")"
  uv run python scripts/benchmark_cli.py report \
    --api-base http://127.0.0.1:5000 \
    --competition-id "$COMPETITION_ID" \
    --output-dir "$RUN_DIR/report"
done
```

### 3.3 February 2025

```bash
for run in 1 2 3 4 5; do
  RUN_DIR="runs/paper/4_2_main/february_2025/run_${run}"
  mkdir -p "$RUN_DIR"
  uv run python scripts/run_competition.py \
    --competition-config config/paper/competition/main_alpha0.json \
    --competitors-config config/paper/competitors/main_8_models.json \
    --problem-ids config/paper/problems/main_february_2025.json \
    --log-dir "$RUN_DIR/logs" \
    --competition-id-output "$RUN_DIR/competition_id.txt"

  COMPETITION_ID="$(cat "$RUN_DIR/competition_id.txt")"
  uv run python scripts/benchmark_cli.py report \
    --api-base http://127.0.0.1:5000 \
    --competition-id "$COMPETITION_ID" \
    --output-dir "$RUN_DIR/report"
done
```

### 3.4 US Open 2025

```bash
for run in 1 2 3 4 5; do
  RUN_DIR="runs/paper/4_2_main/us_open_2025/run_${run}"
  mkdir -p "$RUN_DIR"
  uv run python scripts/run_competition.py \
    --competition-config config/paper/competition/main_alpha0.json \
    --competitors-config config/paper/competitors/main_8_models.json \
    --problem-ids config/paper/problems/main_us_open_2025.json \
    --log-dir "$RUN_DIR/logs" \
    --competition-id-output "$RUN_DIR/competition_id.txt"

  COMPETITION_ID="$(cat "$RUN_DIR/competition_id.txt")"
  uv run python scripts/benchmark_cli.py report \
    --api-base http://127.0.0.1:5000 \
    --competition-id "$COMPETITION_ID" \
    --output-dir "$RUN_DIR/report"
done
```

### 3.5 Optional Timeline Export During a Main Run

```bash
COMPETITION_ID="$(cat runs/paper/4_2_main/february_2025/run_1/competition_id.txt)"
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --interval 10 \
  --output-dir runs/paper/4_2_main/february_2025/run_1/timeline
```

## 4. Section 4.3 Self-Play

Public release entrypoints:

- `config/paper/competitors/self_play_gemini.json`
- `config/paper/competitors/self_play_gemini_duel_prompt.json`

The paper reports nine competitions between identical `gemini-2.5-pro` agents. Run one competition per repeat:

### 4.1 Standard Self-Play

```bash
for run in 1 2 3 4 5 6 7 8 9; do
  RUN_DIR="runs/paper/4_3_self_play/standard/run_${run}"
  mkdir -p "$RUN_DIR"
  uv run python scripts/run_competition.py \
    --competition-config config/paper/competition/main_alpha0.json \
    --competitors-config config/paper/competitors/self_play_gemini.json \
    --problem-ids config/paper/problems/main_february_2025.json \
    --log-dir "$RUN_DIR/logs" \
    --competition-id-output "$RUN_DIR/competition_id.txt"

  COMPETITION_ID="$(cat "$RUN_DIR/competition_id.txt")"
  uv run python scripts/benchmark_cli.py report \
    --api-base http://127.0.0.1:5000 \
    --competition-id "$COMPETITION_ID" \
    --output-dir "$RUN_DIR/report"
done
```

### 4.2 Duel-Prompt Self-Play

```bash
for run in 1 2 3 4 5 6 7 8 9; do
  RUN_DIR="runs/paper/4_3_self_play/duel_prompt/run_${run}"
  mkdir -p "$RUN_DIR"
  uv run python scripts/run_competition.py \
    --competition-config config/paper/competition/main_alpha0.json \
    --competitors-config config/paper/competitors/self_play_gemini_duel_prompt.json \
    --problem-ids config/paper/problems/main_february_2025.json \
    --log-dir "$RUN_DIR/logs" \
    --competition-id-output "$RUN_DIR/competition_id.txt"

  COMPETITION_ID="$(cat "$RUN_DIR/competition_id.txt")"
  uv run python scripts/benchmark_cli.py report \
    --api-base http://127.0.0.1:5000 \
    --competition-id "$COMPETITION_ID" \
    --output-dir "$RUN_DIR/report"
done
```

## 5. Section 4.4 and Appendix Benchmarks

Use the checked-in public configs under `config/paper/competition/`, `config/paper/competitors/`, and `config/paper/problems/` in the same pattern shown above:

```bash
uv run python scripts/run_competition.py \
  --competition-config <competition.json> \
  --competitors-config <competitors.json> \
  --problem-ids <problem_ids.json> \
  --log-dir <run_dir>/logs \
  --competition-id-output <run_dir>/competition_id.txt
```

Then export the report and, if needed, the timeline.

## 6. Section 4.5 Codex Swarm

The standalone Codex runner is documented in `docs/codex_loop_agent.md`. The Hydro prerequisite is exactly the same as in this document: the same Hydro deployment, addon installation, and imported problemset are reused for the swarm experiments.

## 7. Notes on Hydro-Specific Behavior

- USACOArena no longer reads hidden testcases directly from the repository dataset.
- Official judging and ad-hoc pretest both route through Hydro.
- The released `usacoarena_hydro_problemset_normalized.zip` is imported into Hydro so that paper-facing long problem IDs remain valid.
- If a Hydro deployment has not imported the problemset or has not installed the addon, `api/problem-library` and submissions will fail as expected.
