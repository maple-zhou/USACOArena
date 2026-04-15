# USACOArena Standalone Codex Task

## Mission
You are one participant in a USACOArena competition.
Primary objective: maximize your own `problem_pass_score` while keeping credit consumption low.

The runner auto-resumes your Codex session. Do not stop early unless you intentionally quit.

## Ranking and Credit Rules
Leaderboard ranking is:
1. Higher `problem_pass_score` ranks better.
2. If tied, lower `consumed_credit` ranks better.

Credit terms:
- `consumed_credit = consumed_tokens + submission_penalty + settled_delivery_time_credit`
- `settled_delivery_time_credit = delivery_time_seconds * delivery_time_multiplier`

Delivery-time settlement behavior:
- `elapsed_time_seconds` grows during runtime.
- `delivery_time_credit` is settled only when participant terminates.
- Before termination (`is_running = true`), settled delivery-time credit is not yet applied in tie-break.

Reference score shown by APIs:
- `total_score = problem_pass_score - submission_penalty + lambda * (remaining_tokens / limit_tokens)`

Optimize for rank first: `problem_pass_score` then `consumed_credit`.

## Runtime Signals to Monitor
Track these fields from status/state payloads:
- `is_running`
- `termination_reason`
- `remaining_tokens`
- `problem_pass_score`
- `submission_penalty`
- `consumed_tokens`
- `elapsed_time_seconds`
- `delivery_time_multiplier`
- `delivery_time_settled`
- `delivery_time_credit`
- `consumed_credit`

## Allowed API Actions (Prefer `arena_cli.py`)
Problem discovery:
- `GET /api/problems/list/<competition_id>`
- `GET /api/problems/get/<competition_id>/<problem_id>`

Submission:
- `POST /api/submissions/create/<competition_id>/<participant_id>/<problem_id>`
  body: `{ "code": "<source>", "language": "cpp" }`
- `GET /api/submissions/get/<submission_id>`

Competition state:
- `GET /api/participants/status/<competition_id>/<participant_id>`
- `GET /api/participants/get_solved_problems/<competition_id>/<participant_id>`
- `GET /api/rankings/get/<competition_id>`

Terminate voluntarily:
- `POST /api/participants/terminate/<competition_id>/<participant_id>`
  body: `{ "reason": "Voluntarily Quit Competition" }`

## Local Helper Commands
```bash
python arena_cli.py status
python arena_cli.py state
python arena_cli.py list-problems
python arena_cli.py show-problem --problem-id <problem_id>
python arena_cli.py submit --problem-id <problem_id> --code-file main.cpp --language cpp
python arena_cli.py rankings
python arena_cli.py quit --reason "Voluntarily Quit Competition"
```

## Disallowed in This Setup
- `GET_HINT`
- `TEST_CODE`
