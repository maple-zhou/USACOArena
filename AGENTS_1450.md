# AGENTS_1450 — Interstellar Intervals

面向自动编码代理提供题面、统一提示词以及判题接口的请求/返回示例。

## System Prompt

```
你是一名只负责写代码的竞技编程选手。请根据给定的题目描述与样例，编写用于提交的完整程序，并根据测评结果修改程序直到程序完全通过为止。

核心要求：
1. **必须**先确保程序可以通过题目提供的所有样例输入输出；
2. 可以自选题目允许的编程语言，但请只输出源代码本身，不要添加额外解释；
3. 仔细阅读题面中的所有限制与边界条件，并在代码中妥善处理；
4. 提交前请自行检查输入输出格式是否与题面完全一致；
5. 注意参考历史提交记录中的测评结果。

系统会在下文附上题目详情与样例，请在理解后直接返回可提交的最终代码。
```

## 题目描述（USACO Gold CPID 1450）

```
It's the year 3000, and Bessie became the first cow in space! During her
journey between the stars, she found a number line with N
(2 ≤ N ≤ 5 ⋅ 10^5) points, numbered from 1 to N. All points are
initially colored white. She can perform the following operation any number of
times.

Choose a position i within the number line and a positive integer x.
Then, color all the points in the interval [i, i + x - 1] red and all points
in [i + x, i + 2x - 1] blue. All chosen intervals must be disjoint
(i.e. no points in [i, i + 2x - 1] can be already colored red or blue). The
entire interval must also fall within the number line (i.e.
1 ≤ i ≤ i + 2x - 1 ≤ N).
Farmer John gives Bessie a string s of length N consisting of characters
R, B, and X. The string represents Farmer John's color preferences for
each point: s_i = R means the i'th point must be colored red, s_i = B means
the i'th point must be colored blue, and s_i = X means there is no
constraint on the color for the i'th point.

Help Bessie count the number of distinct ways for the number line to be colored
while satisfying Farmer John's preferences. Two colorings are different if there
is at least one corresponding point with a different color. Because the answer
may be large, output it modulo 10^9+7.

INPUT FORMAT:
The first line contains an integer N.
The following line contains string s.

OUTPUT FORMAT:
Output the number of distinct ways for the number line to be colored while
satisfying Farmer John's preferences modulo 10^9+7.
```

### 样例 1

```
输入：
6
RXXXXB

输出：
5
```

### 样例 2

```
输入：
6
XXRBXX

输出：
6
```

### 样例 3

```
输入：
12
XBXXXXRXRBXX

输出：
18
```

## 判题请求体示例

- 提交地址：`POST http://localhost:8081/api/judge/evaluate`

```json
{
  "problem_id": "1450_gold_interstellar_intervals",
  "code": "// TODO: 在此替换为最终提交的完整 C++ 源代码",
  "language": "cpp",
  "participant_id": "agent-demo",
  "submission_id": "interstellar-001",
  "competition": {
    "id": "offline-demo",
    "title": "Ad-hoc Evaluation",
    "max_tokens": 500000,
    "rules": {
      "penalties": { "WA": 10, "RE": 10, "CE": 5, "TLE": 10, "MLE": 10 },
      "submission_tokens": { "AC": 100, "WA": 50 }
    }
  }
}
```

## 判题返回示例（节选）

```json
{
  "ok": true,
  "submission": {
    "id": "interstellar-001",
    "competition_id": "offline-demo",
    "participant_id": "agent-demo",
    "problem_id": "1450_gold_interstellar_intervals",
    "language": "cpp",
    "submitted_at": "2025-02-20T10:15:32.541258+00:00",
    "status": "AC",
    "test_results": [
      { "test_case_id": "execution", "status": "AC", "runtime_ms": 12, "memory_kb": 512, "output": "…", "error_message": null }
    ],
    "pass_score": 100,
    "penalty": 0,
    "submission_tokens": 100
  },
  "summary": { "passed": 1, "total": 1, "status": "AC" },
  "feedback": "你最近的一次提交测评结果为：通过了 1/1 个测试用例，全部测试均已通过。"
}
```
