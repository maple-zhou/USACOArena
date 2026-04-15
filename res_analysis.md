# Codex Swarm 产物复核（synthesis）

## 1) 数据范围与映射
- 仅使用目录：`logs/codex_loop_agents/analysis/synthesis`
- 3 个策略与 workspace 映射：

| 策略 | workspace | competition_id | participant_id |
|---|---|---|---|
| Speedy Spendthrift | `20260228_121021_02` | `a35e0bf7-4e30-447d-8c22-ba715aafba33` | `38266509-2224-4bc3-8758-b41c589e96f5` |
| Frugal Perfectionist | `20260228_121021` | `a35e0bf7-4e30-447d-8c22-ba715aafba33` | `ad4462bf-7551-40d3-bbb1-ac6115c06eb6` |
| Cost-Aware Strategist | `20260228_235203_01` | `6344b995-a937-4fec-930c-a63c62861c20` | `b25efcf6-da1f-4139-b6af-40a10badd1e7` |

说明：Cost-Aware 来自不同 `competition_id`，横向比较需在论文中注明该条件差异。

## 2) 指标口径（主口径：Trace，自洽用于图与表）
- `Final Score`：`final_metrics.json -> participant_metrics.problem_pass_score`
- `Delivery Time (mins)`：`sum(run_summary.md 中 Total Absolute Time (ms)) / 60000`
- `Total Tokens (M)`：`sum(run_summary.md 中 Total Token Cost) / 1e6`
- `Comm. Ratio`：`sum(events.jsonl tokens_communication) / sum(tokens_thinking + tokens_coding + tokens_communication)`
- `Eval Overhead (Runs)`：`sum(run_summary.md 中 Total Evaluation Runs)`

## 3) LaTeX 表格可用数据（主口径）

| Swarm Strategy Profile | Final Score | Delivery Time (mins) | Total Tokens (M) | Comm. Ratio | Eval Overhead (Runs) |
|---|---:|---:|---:|---:|---:|
| Speedy Spendthrift | 3 | 66.9833 | 15.7750 | 17.6228% | 70 |
| Frugal Perfectionist | 8 | 299.1053 | 0.0327 | 29.1284% | 8 |
| Cost-Aware Strategist | 8 | 219.9841 | 23.5247 | 65.5241% | 24 |

可直接填表的四舍五入版本（1 位小数）
- Speedy: `3.0, 67.0, 15.8, 17.6\%, 70`
- Frugal: `8.0, 299.1, 0.03, 29.1\%, 8`
- Cost-Aware: `8.0, 220.0, 23.5, 65.5\%, 24`

## 4) 作图数据（对应 `USACO_camera_ready.py`）
脚本中的策略顺序是：`['Speedy Spendthrift', 'Cost-Aware Strategist', 'Frugal Perfectionist']`。

按该顺序可直接替换的数组（主口径）：

```python
strategies = ['Speedy Spendthrift', 'Cost-Aware Strategist', 'Frugal Perfectionist']

delivery_time = [66.9833, 219.9841, 299.1053]   # minutes
total_tokens = [15.7750, 23.5247, 0.0327]       # millions
scores = [3, 8, 8]

thinking_tokens = np.array([7.2446, 6.6132, 0.0163])
coding_tokens = np.array([5.7505, 1.4971, 0.0069])
comm_tokens = np.array([2.7800, 15.4143, 0.0095])
```

注意：当前脚本写死了 `ax1.set_xlim(0, 70)`，会截断 Cost-Aware 与 Frugal；建议改为例如 `ax1.set_xlim(0, 320)`。

## 5) 备选口径（结算口径，来自 final_metrics）
如果你希望 `Total Tokens` 使用平台结算值（而不是 trace token）：

- `Final Score`：`problem_pass_score`
- `Delivery Time (mins)`：`delivery_time_seconds / 60`
- `Total Tokens (M)`：`consumed_tokens / 1e6`

结果为：
- Speedy: `score=3, delivery=246.5167, total_tokens=43.3264M`
- Cost-Aware: `score=8, delivery=420.2500, total_tokens=71.7763M`
- Frugal: `score=8, delivery=306.7333, total_tokens=47.3549M`

该口径下右图分解没有原生字段；可将 trace 分解比例按 `consumed_tokens` 缩放（推导值）。

## 6) 证据路径
- 策略/participant 映射：
  - `_launcher_logs/launch_manifest_20260228_121021.json`（`summary.participants`）
  - 各 workspace 的 `competition_context.md`、`AGENTS.md`
- Final score/结算 token/结算时间：
  - `20260228_121021/final_metrics.json`
  - `20260228_121021_02/final_metrics.json`
  - `20260228_235203_01/final_metrics.json`
- Trace token 分解与 Comm Ratio：
  - 各 workspace `runs/*/events.jsonl`
- Delivery Time(trace) 与 Eval Overhead(trace)：
  - 各 workspace `runs/*/run_summary.md`
- Runner 级备选评测开销：
  - 各 workspace `agent_exec_summary.jsonl`（`evaluation_runs`）

## 7) 复算产物
- 我已将完整聚合结果落盘到：`.codex/phase31_metrics.json`
- 该文件包含：
  - 主口径结果
  - 结算口径结果
  - token 分解缩放结果
  - 每个策略对应的证据文件列表
