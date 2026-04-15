# Standalone Codex Loop Agent

This guide covers the public standalone Codex runner used for the swarm case study in Section 4.5.

## 1. Start the Shared Services

In terminal 1, start Hydro, install the addon, and import the normalized problemset as described in `docs/oj.md`.

In terminal 2, start the USACOArena API server:

```bash
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --host 0.0.0.0 \
  --port 5000 \
  --hydro-base-url http://127.0.0.1:8888 \
  --hydro-api-token "<token>"
```

## 2. Register a Codex Competition

The helper below creates a competition, registers baseline participants, and also registers one Codex participant without starting the Codex process yet.

```bash
mkdir -p runs/codex_swarm
uv run python scripts/run_competition_for_codex.py \
  --competition-config config/paper/competition/codex_swarm.json \
  --competitors-config config/paper/competitors/three_model_sanity.json \
  --problem-ids config/paper/problems/main_us_open_2025.json \
  --log-dir runs/codex_swarm/setup_logs \
  --competition-id-output runs/codex_swarm/competition_id.txt \
  --codex-name "Codex Swarm Agent" \
  --codex-env-output runs/codex_swarm/codex_env.txt
```

The helper writes:

- `runs/codex_swarm/competition_id.txt`
- `runs/codex_swarm/codex_env.txt`

Load the generated environment file:

```bash
source runs/codex_swarm/codex_env.txt
export USACOARENA_BASE_URL="$SERVER_BASE_URL"
export USACOARENA_COMPETITION_ID="$COMPETITION_ID"
export USACOARENA_PARTICIPANT_ID="$PARTICIPANT_ID"
```

## 3. Run the Default Codex Loop

```bash
uv run python scripts/run_codex_loop_agent.py \
  --api-base "$USACOARENA_BASE_URL" \
  --competition-id "$USACOARENA_COMPETITION_ID" \
  --participant-id "$USACOARENA_PARTICIPANT_ID" \
  --workspace runs/codex_swarm/workspaces/default \
  --template-dir config/codex_agent/usacoarena \
  --llm-isolate
```

## 4. Run the Three Swarm Strategy Profiles

Speedy Spendthrift:

```bash
uv run python scripts/run_codex_loop_agent.py \
  --api-base "$USACOARENA_BASE_URL" \
  --competition-id "$USACOARENA_COMPETITION_ID" \
  --participant-id "$USACOARENA_PARTICIPANT_ID" \
  --workspace runs/codex_swarm/workspaces/speedy \
  --template-dir config/codex_agent/swarm_fast_7 \
  --llm-isolate
```

Cost-Aware Strategist:

```bash
uv run python scripts/run_codex_loop_agent.py \
  --api-base "$USACOARENA_BASE_URL" \
  --competition-id "$USACOARENA_COMPETITION_ID" \
  --participant-id "$USACOARENA_PARTICIPANT_ID" \
  --workspace runs/codex_swarm/workspaces/balanced \
  --template-dir config/codex_agent/swarm_balanced_4 \
  --llm-isolate
```

Frugal Perfectionist:

```bash
uv run python scripts/run_codex_loop_agent.py \
  --api-base "$USACOARENA_BASE_URL" \
  --competition-id "$USACOARENA_COMPETITION_ID" \
  --participant-id "$USACOARENA_PARTICIPANT_ID" \
  --workspace runs/codex_swarm/workspaces/frugal \
  --template-dir config/codex_agent/swarm_lean_2 \
  --llm-isolate
```

## 5. Manual Control from the Runner Workspace

From the active workspace directory:

```bash
python arena_cli.py status
python arena_cli.py state
python arena_cli.py list-problems
python arena_cli.py rankings
python arena_cli.py quit --reason "Voluntarily Quit Competition"
```

## 6. Export Reports and Timelines

```bash
COMPETITION_ID="$(cat runs/codex_swarm/competition_id.txt)"
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --output-dir runs/codex_swarm/reports
```

```bash
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --interval 10 \
  --output-dir runs/codex_swarm/timeline
```

## 7. Workspace Artifacts

Each runner workspace contains:

- `runner_state.json`
- `runtime_status.json`
- `runs/<timestamp>/events.jsonl`
- `runs/<timestamp>/run_summary.md`
- `final_metrics.json`
- `final_rankings.json`
- `AGENTS.md`
- `problem.md`
- `arena_cli.py`

These are the primary artifacts for reproducing the Section 4.5 swarm analysis.
