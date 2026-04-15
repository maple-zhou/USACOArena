"""
Simple debugging utility for USACOArena LLM configurations.

Usage example:
    uv run python debug_llm.py \
        --competitors-config config/1v3.json \
        --competitor-name deepseek-v3 \
        --prompt "What is 2+2?"

To test every LLM in config/8llm.json, run:
    uv run python debug_llm.py --all

The script will reuse the same request/response formats defined for the
competition agent, send a single prompt, and print the raw response.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug a single LLM competitor config")
    parser.add_argument(
        "--competitors-config",
        default="config/1v3.json",
        help="Path to competitors configuration JSON",
    )
    parser.add_argument(
        "--competitor-name",
        help="Name of the competitor to debug (defaults to the first entry)",
    )
    parser.add_argument(
        "--prompt",
        default='''"# Competition State\n\n## Competition Rules\n\n### Credit System:\n- Each participant starts with a total of 40000000 credit limit\n- Credit is consumed by three main sources:\n  1. **LLM Inference**: Generating thoughts and actions consumes credit based on the number of tokens used.\n  2. **Purchasing Hints**: Hints can be bought for a problem at a specified credit cost.\n  3. **Testing Code**: You can test your code before a final submission, which costs credit per test run.\n- **IMPORTANT**: Your participation ends when your **actual consumed credit** reaches the limit. Penalties from wrong submissions do NOT count toward termination - they only affect your rankings.\n\n### Scoring Rules:\n- Your **Final Score** is the sum of points from all problems you solve completely (achieve 'Accepted' status).\n- No partial credit is awarded for passing some test cases.\n- The points awarded for solving a problem are weighted by its difficulty level. For example, a solved Silver problem is worth more than a solved Bronze problem.\n- Bronze problems: 100 points each\n- Gold problems: 500 points each\n- Platinum problems: 1000 points each\n- Silver problems: 200 points each\n\nPoints are awarded proportionally to the number of test cases passed. For example, if you pass 7 out of 10 test cases for a Bronze problem, you'll receive 70 points.\n\n### Penalties:\nEach submission with the following results will incur a penalty:\n- AC: 0 points\n- CE: 10 points\n- MLE: 10 points\n- RE: 10 points\n- TLE: 10 points\n- WA: 10 points\n\n### Ranking and Tie-Breaking:\n- Participants are ranked primarily by their **Final Score**, which is the weighted sum of solved problems.\n- In case of a tie in score, the participant with the lower **(Actual Consumed Credit + Penalties)** ranks higher.\n- Penalties affect your ranking tie-breaker but NOT your termination status.\n\n### Programming Languages:\nAvailable languages: C++17, Java, and Python3.\n\nImportant Notes:\n- C++17 solutions are guaranteed to pass all test cases within time limits\n- Java and Python solutions may not be able to pass all test cases due to time constraints\n- Choose your programming language wisely based on the problem requirements\n\n## Your Status\n- Name: gemini-2.5-pro\n- Consumed Credit: 133157\n- Solved Problems: 1491_bronze_reflection\n- Current Score: 100\n- Penalty: 0\n\n## Available Problems\n- problem_id: 1500_platinum_min_max_subarrays\n- problem_id: 1501_platinum_transforming_pairs\n- problem_id: 1502_platinum_true_or_false_test\n- problem_id: 1497_gold_bessie's_function\n- problem_id: 1498_gold_the_best_subsequence\n- problem_id: 1499_gold_friendship_editing\n- problem_id: 1494_silver_the_best_lineup\n- problem_id: 1495_silver_vocabulary_quiz\n- problem_id: 1496_silver_transforming_pairs\n- problem_id: 1491_bronze_reflection\n- problem_id: 1492_bronze_making_mexes\n- problem_id: 1493_bronze_printing_sequences\n\n## Current Rankings\n1. gpt-5-codex: Score 400 points, Consumed Credit + Penalty: 109886 [ACTIVE]\n2. glm-4.5: Score 100 points, Consumed Credit + Penalty: 24735 [ACTIVE]\n3. gemini-2.5-pro: Score 100 points, Consumed Credit + Penalty: 133157 [ACTIVE]\n4. claude-sonnet-4-20250514: Score 0 points, Consumed Credit + Penalty: 220 [ACTIVE]\n5. deepseek-v3.1: Score 0 points, Consumed Credit + Penalty: 11802 [ACTIVE]\n6. deepseek-v3: Score 0 points, Consumed Credit + Penalty: 21050 [ACTIVE]\n7. qwen3-235b: Score 0 points, Consumed Credit + Penalty: 28411 [ACTIVE]\n8. kimi-k2-0905: Score 0 points, Consumed Credit + Penalty: 61775 [ACTIVE]\n\n## Available Actions (Only use the following actions. DO NOT use other actions)\n\n1. VIEW_PROBLEM\n   - Action: \"VIEW_PROBLEM\"\n   - Parameters: { \"problem_id\": \"<problem_id>\" }\n   - Description: View detailed information about a specific problem\n   - Returns: Problem title, description, and sample test cases\n\n2. GET_HINT\n   - Action: \"GET_HINT\"\n   - Description: Get a hint for a problem (consume credit)\n   - Hint Levels:\n     0. Competition Strategy (500 credit):        \n        - NOTICE, you MUST give parameters as { \"hint_level\": 0 }   \n        - Then you will be provided with competitive programming strategy and tips, which includes debugging checklist and contest strategy        \n\n     1. Problem Relevant Textbook Hint (1000 credit):\n        - NOTICE, you MUST give parameters as { \"problem_id\": \"<problem_id>\", \"hint_level\": 1 }\n        - Then you will be provided with textbook content relevant to the problem_id you give, which explains theoretical concepts and knowledge\n\n     2. Knowledge Relevant Textbook Hint (1000 credit):\n        - NOTICE, you MUST give parameters as { \"hint_knowledge\": \"<hint_knowledge>\", \"hint_level\": 2 }\n        - Then you will be provided with textbook content relevant to the hint_knowledge you give, which explains theoretical concepts and knowledge\n\n     3. Similar Problem Hint (1500 credit):\n        - NOTICE, you MUST give parameters as { \"problem_id\": \"<problem_id>\", \"hint_level\": 3 }\n        - Then you will be provided with problems and solutions similar to the problem_id you give, which helps understand the problem type and basic approach\n\n     4. Knowledge Example Problem Hint (1500 credit):\n        - NOTICE, you MUST give parameters as { \"problem_difficulty\": \"<difficulty_level>\", \"hint_knowledge\": \"<hint_knowledge>\", \"hint_level\": 4 }\n        - Choose problem_difficulty from Bronze, Silver, Gold, Platinum, Advanced and give the hint_knowledge you want to look up. Then you will be provided with example problems and solutions related to the knowledge points and the difficulty_level.\n\n3. SUBMIT_SOLUTION\n   - Action: \"SUBMIT_SOLUTION\"\n   - Parameters: {\n     \"problem_id\": \"<problem_id>\",\n     \"solution\": \"<your_code>\",\n     \"language\": \"<cpp|java|python>\"\n   }\n   - Description: submission a solution for a problem (consumes credit)\n   - Credit Cost:\n     - Each submission consumes credit based on the submission status\n     - Cost varies depending on whether the solution is accepted or rejected\n   - Returns: Submission status, score, and test case results\n\n4. TEST_CODE\n   - Action: \"TEST_CODE\"\n   - Parameters: {\n     \"code\": \"<your_code>\",\n     \"language\": \"<cpp|java|python>\",\n     \"test_cases\": [\n       {\n         \"input\": \"<input_data>\",\n         \"expected_output\": \"<expected_output>\"\n       }\n     ],\n     \"time_limit_ms\": <time_limit_optional>,\n     \"memory_limit_mb\": <memory_limit_optional>\n   }\n   - Description: Test your code with custom test cases (consumes credit)\n   - Credit Cost: 10 credit per test request\n   - Features:\n     - Test code without affecting competition score\n     - Use your own test cases to debug and verify solutions\n     - Get detailed execution results including compilation errors, runtime errors, etc.\n   - Returns: Test results, execution summary, and credit usage\n\n5. TERMINATE\n   - Action: \"TERMINATE\"\n   - Parameters: { \"reason\": \"<reason>\" }\n   - Description: End your participation in the competition and give your reason. Keep in mind that voluntary termination only stops your own run—other participants can continue playing, so your ranking may still shift afterward.\n   - Returns: Final score and ranking\n\nPlease respond using the following JSON format:\n```json\n{\n  \"action\": \"<action_name>\",\n  \"parameters\": {\n    // Fill in parameters according to the action type\n  }\n}\n```\n\n# Last Action Result\n\n## Success view_problem\n### Problem: Making Mexes\nDescription:\n\nYou are given an array $a$ of $N$ non-negative integers $a_1, a_2, \\dots, a_N$\n($1\\le N\\le 2\\cdot 10^5, 0\\le a_i\\le N$). In one operation, you can change any\nelement of $a$ to any non-negative integer.\n\nThe mex of an array is the minimum non-negative integer that it does not\ncontain. For each $i$ in the range $0$ to $N$ inclusive, compute the minimum\nnumber of operations you need  in order to make the mex of $a$ equal $i$.\n\n\nINPUT FORMAT (INPUT ARRIVES FROM THE TERMINAL / STDIN)::\n\nThe first line contains $N$.\n\nThe next line contains $a_1,a_2,\\dots, a_N$.\n\n\n\nOUTPUT FORMAT (PRINT OUTPUT TO THE TERMINAL / STDOUT)::\n\nFor each $i$ in the range $0$ to $N$, output the minimum number of operations\nfor $i$ on a new line. Note that it is always possible to make the mex of $a$\nequal to any $i$ in the range $0$ to $N$.\n\n\nSAMPLE INPUT::\n\n4\n2 2 2 0\n\nSAMPLE OUTPUT::\n \n1\n0\n3\n1\n2\n\nTo make the mex of $a$ equal to $0$, we can change $a_4$ to $3$ (or any\npositive integer). In the resulting array, $[2, 2, 2, 3]$, $0$ is the smallest\nnon-negative integer that the array does not contain, so $0$ is the mex of the\narray.To make the mex of $a$ equal to $1$, we don't need to make any changes since\n$1$ is already the smallest non-negative integer that $a = [2, 2, 2, 0]$ does\nnot contain.To make the mex of $a$ equal to $2$, we need to change the first three\nelements of $a$. For example, we can change $a$ to be $[3, 1, 1, 0]$.\n\nSCORING::\n\nInputs 2-6: $N\\le 10^3$Inputs 7-11: No additional constraints.\n\n\nProblem credits: Benjamin Qi\n\n\nSample Cases:\nCase 1:\nInput:\n4\n2 2 2 0\nExpected Output:\n1\n0\n3\n1\n2\n\n\n\nAnalyze the current situation, think about your strategy, and pay attention to the output token limit. Then respond with a JSON object containing 'action' and 'parameters' fields."''',
        help="User prompt to send to the LLM",
    )
    parser.add_argument(
        "--system",
        default="You are a helpful assistant for debugging LLM connectivity.",
        help="Optional system prompt",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test all LLMs defined in config/8llm.json (ignores --competitor-name)",
    )
    return parser.parse_args()


def load_competitors(config_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    competitors: List[Dict[str, Any]] = data.get("competitors", [])
    if not competitors:
        raise ValueError(f"No competitors defined in {config_path}")
    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        if not str(competitor.get("api_base_url") or "").strip():
            env_name = str(competitor.get("api_base_url_env") or "").strip()
            if env_name:
                competitor["api_base_url"] = str(os.environ.get(env_name, "") or "").strip()
        if not str(competitor.get("api_key") or "").strip():
            env_name = str(competitor.get("api_key_env") or "").strip()
            if env_name:
                competitor["api_key"] = str(os.environ.get(env_name, "") or "").strip()
    return competitors


def load_competitor(config_path: Path, name: Optional[str]) -> Dict[str, Any]:
    competitors = load_competitors(config_path)

    if name:
        for competitor in competitors:
            if competitor.get("name") == name:
                return competitor
        raise ValueError(f"Competitor '{name}' not found in {config_path}")

    return competitors[0]


def build_payload(
    competitor: Dict[str, Any],
    messages: List[Dict[str, str]],
) -> Dict[str, Any]:
    request_format = competitor.get("request_format", {})
    body_template = dict(request_format.get("body_template", {}))
    formatted: Dict[str, Any] = {}

    for key, value in body_template.items():
        if isinstance(value, str):
            formatted[key] = value.format(
                messages=json.dumps(messages, ensure_ascii=False),
                model_id=competitor.get("model_id", ""),
            )
        else:
            formatted[key] = value

    # Ensure messages/model fields exist as proper structures
    if isinstance(formatted.get("messages"), str):
        formatted["messages"] = json.loads(formatted["messages"])
    else:
        formatted.setdefault("messages", messages)

    formatted.setdefault("model", competitor.get("model_id"))
    return formatted


def format_detail(value: Any, limit: int = 400) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + "... [truncated]"
    return text


def debug_competitor(
    competitor: Dict[str, Any],
    messages: List[Dict[str, str]],
    timeout: float,
    verbose: bool = True,
) -> Tuple[bool, str]:
    name = competitor.get("name", "<unknown>")
    api_base = competitor.get("api_base_url", "").rstrip("/")
    request_format = competitor.get("request_format", {})
    url_path = request_format.get("url", "/v1/chat/completions")
    url = f"{api_base}{url_path}"

    payload = build_payload(competitor, messages)

    headers = {}
    for key, value in request_format.get("headers", {}).items():
        if isinstance(value, str):
            headers[key] = value.format(api_key=competitor.get("api_key", ""))
        else:
            headers[key] = value

    method = request_format.get("method", "POST").upper()

    if verbose:
        print(f"\n=== Testing {name} ===")
        print(f"Sending {method} request to {url}")

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except Exception as exc:  # requests raises many subclasses; keep it simple
        summary = f"[ERROR] {name}: request failed: {exc}"
        if verbose:
            print(summary)
        return False, summary

    if verbose:
        print(f"Status: {response.status_code}")

    try:
        response_json = response.json()
    except ValueError:
        if verbose:
            print("Raw response:")
            print(response.text)
        snippet = format_detail(response.text, limit=500)
        summary = (
            f"[ERROR] {name}: invalid JSON response (HTTP {response.status_code}). "
            f"Raw: {snippet}"
        )
        if verbose:
            print(summary)
        return False, summary

    response_format = competitor.get("response_format", {})
    response_path = response_format.get("response_path", "choices[0].message.content")
    error_path = response_format.get("error_path")
    content = dig_value(response_json, response_path)
    error_message = dig_value(response_json, error_path) if error_path else None

    if verbose:
        print("Raw JSON response:")
        print(json.dumps(response_json, indent=2, ensure_ascii=False))
        print("\nExtracted content:")
        print(content)

    issues: List[str] = []
    if response.status_code >= 400:
        issues.append(f"HTTP {response.status_code}")
    if error_message:
        detail = format_detail(error_message)
        issues.append(f"error at '{error_path}': {detail}")
    if content in (None, ""):
        issues.append(f"no content at '{response_path}'")

    if issues:
        summary = f"[ERROR] {name}: " + "; ".join(issues)
    else:
        summary = f"[OK] {name}: HTTP {response.status_code}"

    if verbose:
        print(summary)

    return not issues, summary


def build_messages(system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    return messages


def main() -> None:
    args = parse_args()
    system_prompt = args.system.strip()
    messages = build_messages(system_prompt, args.prompt)

    if args.all:
        config_path = Path("config/8llm.json")
        competitors = load_competitors(config_path)
        successes = 0
        failures = 0
        for competitor in competitors:
            success, summary = debug_competitor(
                competitor, messages, args.timeout, verbose=False
            )
            print(summary)
            if success:
                successes += 1
            else:
                failures += 1
        print(
            f"\nFinished testing {len(competitors)} competitors: "
            f"{successes} OK, {failures} failed."
        )
        return

    config_path = Path(args.competitors_config)
    competitor = load_competitor(config_path, args.competitor_name)
    debug_competitor(competitor, messages, args.timeout, verbose=True)


def dig_value(data: Any, path: str, default: Any = None) -> Any:
    """Traverse dotted/array paths like choices[0].message.content."""
    current = data
    for segment in path.replace("/", ".").split("."):
        if not segment:
            continue
        if "[" in segment and segment.endswith("]"):
            key, index_text = segment[:-1].split("[", 1)
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
            try:
                index = int(index_text)
                current = current[index]
            except (ValueError, IndexError, TypeError):
                return default
        else:
            if isinstance(current, dict):
                current = current.get(segment, default)
            else:
                return default
    return current


if __name__ == "__main__":
    main()
