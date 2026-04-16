# USACOArena Quick Start

This guide brings up the released open-source stack end to end: dataset resources, Hydro, the USACOArena Hydro addon, the API server, the UI, one sanity competition, the final report export, and the metric timeline export.

Released artifact links:

- Hydro addon package: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDLk840K7kKQIcantsdu2VsAXUUVQsuCxqbkYO0L0sJy0U?e=L6gXuD`
- Hydro problemset zip: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDuOy0L6BSJT4c33LH67LEAAYozwuSaGg7mpTgsp2OSTp4?e=0hXevh`
- Local resource dataset: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQCzXH4s4Ab7RJiSkpzbkO5eAdwrEzRBLW05RTlQyWknkLo?e=hSjB5X`

The released Hydro problemset already covers the latest publicly available USACO 2025-2026 season contests. The only missing contest is the newest March open contest, because the official problem data has not been published yet.

## 1. Install Dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --dev
```

## 2. Deploy the Dataset Archive

Extract the released local resource dataset into the repository root. This is the local hint/textbook/guide resource bundle, not the Hydro problemset zip:

```bash
find dataset -maxdepth 3 -type f | sort | head -50
test -f dataset/datasets/USACO_guide.json
test -f dataset/corpuses/cpbook_v2.json
test -f dataset/corpuses/USACO_strategy.json
```

If any of the checks fail, fix the dataset layout before proceeding. See `docs/dataset.md` for the full archive contract.

## 3. Start Hydro and Install the Addon

In a second terminal:

```bash
git clone https://github.com/hydro-dev/Hydro.git ../Hydro
cd ../Hydro
```

Install Hydro using the official method, then extract and register the released addon package:

```bash
tar -xzf usacoarena_hydro_plugin_v0.1.0.tar.gz
hydrooj addon add /path/to/usacoarena_hydro_plugin_v0.1.0/hydro_plugin_usacoarena
```

Restart Hydro after the addon is added.

## 4. Import the Released Problemset

Import the released `usacoarena_hydro_problemset_normalized.zip` through the Hydro admin UI.

Smoke-test the addon API:

```bash
curl -H 'Authorization: Bearer <token>' \
  http://127.0.0.1:8888/usacoarena/api/health
```

Return to this repository after Hydro is healthy:

```bash
cd /path/to/USACOArena
```

## 5. Start the USACOArena API Server

```bash
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --host 0.0.0.0 \
  --port 5000 \
  --hydro-base-url http://127.0.0.1:8888 \
  --hydro-api-token "<token>"
```

Verify the health endpoint:

```bash
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5000/api/system/oj-status
```

## 6. Start the Management UI

In a third terminal:

```bash
uv run python -m usacoarena.ui.app \
  --host 127.0.0.1 \
  --port 5500
```

Open `http://127.0.0.1:5500/ui` if you want the dashboard, but all steps below are CLI-complete and do not require the browser.

## 7. Export Provider Credentials

All public configs use official URLs and blank keys. Inject the real credentials through environment variables only.

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

## 8. Run a Sanity Competition

```bash
mkdir -p runs/quickstart
uv run python scripts/run_competition.py \
  --competition-config config/paper/competition/main_alpha0.json \
  --competitors-config config/paper/competitors/three_model_sanity.json \
  --problem-ids config/paper/problems/qualification_february_2025.json \
  --log-dir runs/quickstart/logs \
  --competition-id-output runs/quickstart/competition_id.txt
```

Read back the competition ID:

```bash
cat runs/quickstart/competition_id.txt
```

## 9. Export the Final Intelligence Report

```bash
COMPETITION_ID="$(cat runs/quickstart/competition_id.txt)"
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --output-dir runs/quickstart/reports
```

Inspect the generated files:

```bash
find runs/quickstart/reports -maxdepth 2 -type f | sort
```

## 10. Export the Metric Timeline

```bash
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --interval 10 \
  --output-dir runs/quickstart/timeline
```

Inspect the exported files:

```bash
find runs/quickstart/timeline -maxdepth 2 -type f | sort
```

## 11. Next Steps

- Full paper reproduction: `docs/paper_reproduction.md`
- Dataset archive details: `docs/dataset.md`
- Hydro deployment and addon installation: `docs/oj.md`
- Metric and leaderboard inspection: `docs/metrics.md`
- Codex swarm runner: `docs/codex_loop_agent.md`
