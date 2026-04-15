# Metrics and Timeline Inspection

USACOArena exposes both final intelligence reports and trajectory data across a live competition.

## 1. Final Intelligence Report

Export the report bundle:

```bash
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id <competition_id> \
  --output-dir runs/reports
```

Artifacts:

- `intelligence.json`
- `intelligence.csv`
- `intelligence.md`
- `intelligence.html`

## 2. Direct API Access

Structured JSON:

```bash
curl "http://127.0.0.1:5000/api/metrics/intelligence/<competition_id>?format=json"
```

HTML table:

```bash
curl "http://127.0.0.1:5000/api/metrics/intelligence/<competition_id>?format=html"
```

Rankings:

```bash
curl "http://127.0.0.1:5000/api/rankings/get/<competition_id>"
```

Submission list:

```bash
curl "http://127.0.0.1:5000/api/submissions/list/<competition_id>"
```

## 3. Export a Metric Timeline

Use the polling exporter:

```bash
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id <competition_id> \
  --interval 15 \
  --output-dir runs/timeline
```

This writes:

- `participant_metrics_timeline.jsonl`
- `participant_metrics_timeline.csv`
- `rankings_raw.jsonl`
- `submissions_raw.jsonl`
- `intelligence_report_raw.jsonl`

## 4. What the Timeline Contains

Per participant snapshot fields include:

- `rank`
- `score`
- `problem_pass_score`
- `remaining_tokens`
- `consumed_tokens`
- `consumed_credit`
- `submission_penalty`
- `LLM_tokens`
- `hint_tokens`
- `test_tokens`
- `submission_tokens`
- `llm_inference_count`
- `submission_count`
- `accepted_count`
- `elapsed_time_seconds`
- `delivery_time_seconds`
- `delivery_time_credit`
- `delivery_time_multiplier`
- `is_running`
- `termination_reason`
- `solved_problem_count`

## 5. Recommended Workflow During Paper Reproduction

1. start the competition
2. save the competition ID with `--competition-id-output`
3. start `export_metrics_timeline.py` in another terminal
4. wait for the run to finish
5. export the final intelligence report
6. archive the log directory, timeline directory, and final report directory together

## 6. Example

```bash
mkdir -p runs/example
uv run python scripts/run_competition.py \
  --competition-config config/paper/competition/main_alpha0.json \
  --competitors-config config/paper/competitors/three_model_sanity.json \
  --problem-ids config/paper/problems/qualification_february_2025.json \
  --log-dir runs/example/logs \
  --competition-id-output runs/example/competition_id.txt
```

```bash
COMPETITION_ID="$(cat runs/example/competition_id.txt)"
uv run python scripts/export_metrics_timeline.py \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --interval 10 \
  --output-dir runs/example/timeline
```

```bash
uv run python scripts/benchmark_cli.py report \
  --api-base http://127.0.0.1:5000 \
  --competition-id "$COMPETITION_ID" \
  --output-dir runs/example/report
```

## 7. Aggregate Repeated Paper Runs

After running the full paper reproduction layout under `runs/paper/...`, aggregate repeated runs into the paper tables:

```bash
uv run python scripts/aggregate_paper_results.py \
  --runs-root runs/paper \
  --output-dir runs/paper/aggregated
```

Key outputs:

- `table_8_main.md`: Section 4.2 / Appendix F aggregated main benchmark
- `table_2_appendix_b.md`: Appendix B mega-ablation matrix
- `table_9_appendix_g.md`: Appendix G GPT-5 family case study
- `manifest.json`: output inventory and missing-artifact warnings
