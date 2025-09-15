# 统计变量更新机制总结

## 已实现的统计更新功能

### 1. LLM Inference总次数统计
**字段**: `llm_inference_count`
**更新位置**:
- `storage.py:1010` - 在 `add_llm_tokens` 方法中，每次LLM API调用时自动递增
- `storage.py:1165` - 在 `call_llm_api` 方法中，每次LLM API调用时自动递增

**更新触发**: 每次Agent调用LLM进行推理时自动更新

### 2. 具体规则分数统计
**字段**: `bronze_score`, `silver_score`, `gold_score`, `platinum_score`, `bonus_score`
**更新位置**:
- `storage.py:635-640` - 在 `create_submission` 方法中，当提交被接受时更新
- 通过 `_calculate_level_score_updates` 方法计算各难度级别的分数增量

**更新触发**: 每次提交代码并获得分数时，根据问题难度和是否首次AC自动分配到对应级别

### 3. 每道题详细统计
**字段**: `problem_stats` (JSON格式)
包含每道题的：
- `submission_count` - 提交次数
- `passed_test_cases` / `total_test_cases` - 通过的测试用例数
- `best_score` - 最高得分
- `penalty` - 累计惩罚
- `solved` - 是否解决
- `solved_at` - 解决时间
- `is_first_ac` - 是否首次AC
- `language_used` - 使用的编程语言

**更新位置**:
- `models.py:101-127` - `update_problem_stats` 方法更新单个问题统计
- `storage.py:616-622` - 在提交时调用更新方法
- `storage.py:657` - 将更新后的统计保存到数据库

**更新触发**: 每次向特定问题提交代码时自动更新该问题的统计信息

### 4. Pass Score拆解
**字段**: `first_ac_score`, `problem_score`
- `first_ac_score` - 首次AC获得的奖励分数总和
- `problem_score` - 通过题目本身获得的基础分数总和

**更新位置**:
- `storage.py:641-642` - 在 `create_submission` 方法中分别更新
- `storage.py:456-457` - 在 `_calculate_level_score_updates` 中计算分离

**更新触发**: 每次提交被接受时，自动分离首次AC奖励和基础问题分数

## 更新流程示意

```
用户操作 → 系统响应 → 统计更新
│
├── LLM API调用 → 推理执行 → llm_inference_count++, LLM_tokens更新
│
├── 提交代码 → 评测执行 →
│   ├── submission_count++, penalty更新
│   ├── problem_stats更新(包含测试用例通过情况)
│   ├── 如果AC: accepted_count++, 各级别分数更新
│   └── 如果首次AC: first_ac_score更新, bonus_score更新
│
└── 获取提示 → 消耗tokens → hint_tokens更新
```

## 数据库同步机制

所有统计更新都通过SQL事务确保数据一致性：
- 内存中的Participant对象首先更新统计信息
- 然后通过UPDATE SQL语句同步到数据库
- JSON格式的problem_stats直接序列化存储

## 统计数据可见性

更新的统计数据会在以下地方展示：
1. **竞赛结果日志** (`run_competition.py`) - 显示详细的统计分解
2. **CSV导出** (`json_to_csv_converter.py`) - 包含所有新统计字段
3. **实时API响应** - 参与者状态查询时返回最新统计

## 向后兼容性

- 所有新字段都设置了默认值，不会影响现有数据
- 现有的统计逻辑保持不变，新统计是增量添加
- 数据库迁移会自动为现有记录设置默认值