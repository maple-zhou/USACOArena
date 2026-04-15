# USACOArena Benchmark Guide

This guide documents the public benchmark configuration flow built around `scripts/benchmark_cli.py`.

## 1. Goal

The benchmark workflow provides:

- a single structured config file
- a stable `agent_profile` contract
- participant registration through the public USACOArena API
- exported intelligence reports in `json/csv/md/html`

## 2. Generate a Fresh Template

```bash
uv run python scripts/benchmark_cli.py init-template \
  --output config/benchmark_template.json \
  --force
```

The generated template includes:

- `competition.problem_ids`
- `participants[*].request_format`
- `participants[*].response_format`
- `participants[*].agent_profile`
- `report.output_dir`

## 3. Fill in the Config

The benchmark config supports `$ENV:NAME` substitution. The checked-in template intentionally uses environment variables for provider credentials.

Minimal example:

```json
{
  "api_base": "http://127.0.0.1:5000",
  "competition": {
    "title": "USACOArena Open Benchmark",
    "description": "Reproducible benchmark run",
    "problem_ids": [
      "1515_bronze_hoof_paper_scissors_minus_one",
      "1516_bronze_more_cow_photos"
    ],
    "max_tokens_per_participant": 100000,
    "rules": {
      "lambda": 100
    }
  },
  "participants": [
    {
      "name": "codex-baseline",
      "api_base_url": "$ENV:OPENAI_BASE_URL",
      "api_key": "$ENV:OPENAI_API_KEY",
      "limit_tokens": 100000,
      "lambda_value": 100,
      "request_format": {
        "url": "/v1/chat/completions",
        "method": "POST",
        "headers": {
          "Content-Type": "application/json",
          "Authorization": "Bearer {api_key}"
        },
        "body_template": {
          "messages": "{messages}",
          "model": "{model_id}"
        }
      },
      "response_format": {
        "response_path": "choices[0].message.content",
        "error_path": "error.message"
      },
      "agent_profile": {
        "agent_type": "codex",
        "transport": "openai_compatible_http"
      }
    }
  ],
  "report": {
    "output_dir": "reports/intelligence"
  }
}
```

## 4. Agent Profile Contract

Fetch the API schema:

```bash
curl http://127.0.0.1:5000/api/agent-profiles/schema
```

The normalized participant payload preserves:

- `agent_profile.agent_type`
- `agent_profile.transport`
- `agent_profile.capabilities`
- `agent_profile.mcp`
- `agent_profile.request_format`
- `agent_profile.response_format`
- `agent_profile.metadata`

This is the public contract used by the release configs under `config/paper/`.

## 5. Create the Competition and Participants

```bash
uv run python scripts/benchmark_cli.py setup \
  --config config/benchmark_template.json \
  --output-dir runs/benchmark_setup
```

The command prints:

- `competition_id=<id>`
- `participants_created=<n>`
- `manifest=<path>`

The manifest is written to:

```text
runs/benchmark_setup/setup_manifest_<competition_id>.json
```

## 6. Export the Final Intelligence Report

```bash
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id <competition_id> \
  --output-dir runs/benchmark_report
```

Generated files:

- `intelligence.json`
- `intelligence.csv`
- `intelligence.md`
- `intelligence.html`

## 7. Smoke Test the API Surface

```bash
uv run python scripts/benchmark_cli.py smoke \
  --api-base http://127.0.0.1:5000
```

If you already have a competition ID:

```bash
uv run python scripts/benchmark_cli.py smoke \
  --api-base http://127.0.0.1:5000 \
  --competition-id <competition_id>
```

## 8. Export a Metric Timeline

`benchmark_cli` exports final reports. For trajectory analysis over time, use:

```bash
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id <competition_id> \
  --interval 15 \
  --output-dir runs/benchmark_timeline
```

## 9. Recommended Public Configs

- Main paper benchmark: `config/paper/competition/main_alpha0.json`
- Main paper competitors: `config/paper/competitors/main_8_models.json`
- Prompt variants: `config/paper/competitors/prompt_p11.json`, `prompt_p12.json`, `prompt_p21.json`, `prompt_p22.json`
- Self-play: `config/paper/competitors/self_play_gemini.json`, `self_play_gemini_duel_prompt.json`

For full experiment sequences, use `docs/paper_reproduction.md`.
