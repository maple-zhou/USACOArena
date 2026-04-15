# Codex Swarm 实验结果整理（`20260228_121021`）

## 1) 策略与 workspace 映射（证据）
- `Speedy Spendthrift`：workspace `20260228_121021_02`，participant `38266509-2224-4bc3-8758-b41c589e96f5`
  - 证据：`_launcher_logs/launch_manifest_20260228_121021.json`（`template_dir=swarm_fast_7`）
  - 证据：`20260228_121021_02/AGENTS.md` 首行策略名
- `Cost-Aware Strategist`：workspace `20260228_121021_01`，participant `c30d0df7-06b3-47a0-b2e0-a123974d4f19`
  - 证据：manifest 中 `template_dir=swarm_balanced_4`
  - 证据：`20260228_121021_01/AGENTS.md` 首行策略名
- `Frugal Perfectionist`：workspace `20260228_121021`，participant `ad4462bf-7551-40d3-bbb1-ac6115c06eb6`
  - 证据：manifest 中 `template_dir=swarm_lean_2`
  - 证据：`20260228_121021/AGENTS.md` 首行策略名

## 2) 数据完整性说明（非常重要）
- `Speedy` 与 `Frugal` 已终止，有 `final_metrics.json`。
- `Cost-Aware` 仍在运行（`runtime_status.json` 显示 `is_running=true`，时间戳 `2026-03-02T05:40:29Z`），因此没有 `final_metrics.json`。
- 因此下面给两套口径：
  - `A. Trace聚合口径`：用于论文表和作图（可在三策略上统一计算）
  - `B. Competition快照口径`：补充展示真实比赛状态（其中 Cost-Aware 为“截至快照”）

## 3) 计算口径与公式（A: Trace聚合）
对每个 workspace 的全部 `runs/*` 聚合：

1. `Total Tokens = Σ(tokens_thinking + tokens_coding + tokens_communication)`
   - 来源：`runs/*/events.jsonl`
2. `Comm. Ratio = Σ(tokens_communication) / Total Tokens`
3. `Delivery Time (mins) = Σ(run_summary 的 Total Absolute Time (ms)) / 60000`
   - 来源：`runs/*/run_summary.md`
4. `Eval Overhead (Runs) = Σ(run_summary 的 Total Evaluation Runs)`
5. `Final Score`：
   - 优先取 `final_metrics.json -> participant_metrics.problem_pass_score`
   - 若无 final_metrics（Cost-Aware），取最新 `runs/*/run_summary.md` 的 `Problem Pass Score`

## 4) A口径结果（可直接填 LaTeX 表）

| Swarm Strategy Profile | Final Score | Delivery Time (mins) | Total Tokens (M) | Comm. Ratio | Eval Overhead (Runs) |
|---|---:|---:|---:|---:|---:|
| Speedy Spendthrift | 3.0 | 66.98 | 15.775 | 17.62% | 70 |
| Frugal Perfectionist | 8.0 | 83.16 | 0.033 | 29.13% | 8 |
| Cost-Aware Strategist* | 8.0 | 230.47 | 93.587 | 27.37% | 21 |

\* `Cost-Aware` 仍在运行，以上是“截至当前产物快照”的聚合值。

### 4.1 关键中间值（token三分项，单位=token）
- Speedy: thinking `7,244,575`, coding `5,750,451`, communication `2,780,000`, total `15,775,026`
- Cost-Aware: thinking `60,085,715`, coding `7,888,625`, communication `25,612,214`, total `93,586,554`
- Frugal: thinking `16,325`, coding `6,850`, communication `9,525`, total `32,700`

### 4.2 Comm Ratio 计算示例
- Speedy: `2,780,000 / 15,775,026 = 0.1762279 -> 17.62%`
- Cost-Aware: `25,612,214 / 93,586,554 = 0.2736741 -> 27.37%`
- Frugal: `9,525 / 32,700 = 0.2912844 -> 29.13%`

## 5) 作图数据（对应 `/home/ubuntu/scratch/lfzhou/USACO_camera_ready.py`）
脚本里的策略顺序是：`[Speedy, Cost-Aware, Frugal]`。

```python
strategies = ['Speedy Spendthrift', 'Cost-Aware Strategist', 'Frugal Perfectionist']

# 左图（气泡图）
delivery_time = [66.9833333333, 230.47175, 83.1553333333]   # minutes
total_tokens = [15.775026, 93.586554, 0.0327]                # millions
scores = [3.0, 8.0, 8.0]                                     # bubble size

# 右图（堆叠条形图）
thinking_tokens = [7.244575, 60.085715, 0.016325]            # millions
coding_tokens = [5.750451, 7.888625, 0.00685]                # millions
comm_tokens = [2.78, 25.612214, 0.009525]                    # millions
```

## 6) B口径（Competition快照补充，不用于上表）
- Speedy（已终止）：
  - `problem_pass_score=3`, `total_score=-6001.333252`, `consumed_tokens=43,326,420`, `delivery_time_seconds=14,791`
- Frugal（已终止）：
  - `problem_pass_score=8`, `total_score=-796.73558`, `consumed_tokens=47,354,900`, `delivery_time_seconds=18,404`
- Cost-Aware（运行中快照）：
  - `is_running=true`, `total_score=-1959.3865091`, `remaining_tokens=326,134,909`, `elapsed_time_seconds=178,208`

## 7) 主要证据文件
- 策略映射
  - `logs/codex_loop_agents/analysis/20260228_121021/_launcher_logs/launch_manifest_20260228_121021.json`
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021/AGENTS.md`
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021_01/AGENTS.md`
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021_02/AGENTS.md`
- Final score / 终态指标
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021/final_metrics.json`
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021_02/final_metrics.json`
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021_01/runtime_status.json`
  - `logs/codex_loop_agents/analysis/20260228_121021/20260228_121021_01/runs/20260302_133951/run_summary.md`
- 聚合计算输入
  - `logs/codex_loop_agents/analysis/20260228_121021/<workspace>/runs/*/events.jsonl`
  - `logs/codex_loop_agents/analysis/20260228_121021/<workspace>/runs/*/run_summary.md`
