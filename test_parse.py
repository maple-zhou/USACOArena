#!/usr/bin/env python3

import re
import json_repair

def test_parse_action(response: str):
    """Test the parse_action logic"""
    print("=" * 60)
    print("Testing response:")
    print(response)
    print("=" * 60)
    
    # Look for JSON in code blocks with various formats
    patterns = [
        r"```(?:json)?\s*(.+?)\s*```",  # ```json ... ```
        r"````(?:json)?\s*(.+?)\s*````",  # ````json ... ````
        r"```\s*(.+?)\s*```",  # ``` ... ``` (any language)
        r"````\s*(.+?)\s*````"  # ```` ... ```` (any language)
    ]
    
    json_str = None
    for i, pattern in enumerate(patterns):
        print(f"Trying pattern {i+1}: {pattern}")
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            print(f"Found {len(matches)} matches")
            # Try to parse each match as JSON
            for j, match in enumerate(matches):
                try:
                    # Test if this is valid JSON
                    test_parse = json_repair.loads(match.strip())
                    if isinstance(test_parse, dict) and "action" in test_parse:
                        json_str = match.strip()
                        print(f"Valid JSON found in match {j+1}: {json_str[:100]}...")
                        break
                except Exception as e:
                    print(f"Match {j+1} not valid JSON: {e}")
                    continue
            if json_str:
                break
        else:
            print("No matches found")
    
    # If no valid JSON found in code blocks, try to extract JSON from the entire response
    if not json_str:
        # Look for JSON-like structure in the entire response
        json_start = response.find('{')
        json_end = response.rfind('}')
        if json_start != -1 and json_end != -1 and json_end > json_start:
            potential_json = response[json_start:json_end + 1]
            print(f"Trying to extract JSON from position {json_start} to {json_end}")
            try:
                test_parse = json_repair.loads(potential_json)
                if isinstance(test_parse, dict) and "action" in test_parse:
                    json_str = potential_json
                    print("Valid JSON extracted from response")
            except Exception as e:
                print(f"Failed to parse extracted JSON: {e}")
    
    # If still no JSON found, try a more aggressive approach
    if not json_str:
        # Look for the last occurrence of a JSON-like structure
        # This handles cases where there might be multiple JSON-like structures
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, response, re.DOTALL)
        if matches:
            print(f"Found {len(matches)} JSON-like structures with aggressive pattern")
            # Try each match from the end (most likely to be the action JSON)
            for i, match in enumerate(reversed(matches)):
                try:
                    test_parse = json_repair.loads(match)
                    if isinstance(test_parse, dict) and "action" in test_parse:
                        json_str = match
                        print(f"Valid JSON found in aggressive match {len(matches) - i}")
                        break
                except Exception as e:
                    print(f"Aggressive match {len(matches) - i} not valid JSON: {e}")
                    continue
    
    if not json_str:
        # If no JSON found in code blocks, try the entire response
        json_str = response
        print("Using entire response as JSON")
    
    try:
        action = json_repair.loads(json_str)
        print("SUCCESS: Parsed action:", action)
        return action
    except Exception as e:
        print("FAILED: Could not parse JSON:", e)
        return None

# Test with the actual response from the log
test_response = '''An elegant solution to this problem involves dynamic programming, leveraging a key insight about the nature of the possible scores.

### Method Explanation

First, let's analyze how the "excitement level" (score) changes. When we decide the identity of an 'F', say at index `i`, it can affect the score contribution from the pair `(S[i-1], S[i])` and `(S[i], S[i+1])`. If we change our choice for `S[i]` from 'B' to 'E', the score from `(S[i-1], S[i])` changes by `I(S[i-1]=='E') - I(S[i-1]=='B')`, which is either +1, -1, or 0. Similarly, the score from `(S[i], S[i+1])` also changes by +1, -1, or 0. The total change in score from flipping a single 'F' is always an even number (-2, 0, or 2).

This implies a crucial property: **all possible excitement scores must have the same parity.** For example, if 3 is an achievable score, then 4 is not, but 5 might be. This means the set of all possible scores forms an arithmetic progression with a common difference of 2.

Therefore, to find all possible scores, we only need to find the minimum and maximum possible scores. Let's call them `min_total` and `max_total`. The set of all achievable scores will then be `{min_total, min_total + 2, min_total + 4, ..., max_total}`.

We can find the minimum and maximum scores using dynamic programming. Let's define our DP state at each position `i` (from 0 to N-1) of the string `S`:
- `min_b[i]`: The minimum score for the prefix `S[0...i]` if `S[i]` is 'B'.
- `max_b[i]`: The maximum score for the prefix `S[0...i]` if `S[i]` is 'B'.
- `min_e[i]`: The minimum score for the prefix `S[0...i]` if `S[i]` is 'E'.
- `max_e[i]`: The maximum score for the prefix `S[0...i]` if `S[i]` is 'E'.

The transitions are as follows:
To calculate the state for position `i`, we use the values from `i-1`.
If we set `S[i]` to 'B':
- The new minimum score is `min(min_b[i-1] + 1, min_e[i-1] + 0)`.
- The new maximum score is `max(max_b[i-1] + 1, max_e[i-1] + 0)`.
If we set `S[i]` to 'E':
- The new minimum score is `min(min_b[i-1] + 0, min_e[i-1] + 1)`.
- The new maximum score is `max(max_b[i-1] + 0, max_e[i-1] + 1)`.

We iterate from `i = 1` to `N-1`, updating these four values. At each step, we consider the character `S[i]`. If `S[i]` is 'B', the states ending in 'E' become impossible (we can represent this with `min > max`). If `S[i]` is 'E', the states ending in 'B' become impossible. If `S[i]` is 'F', both choices are possible.

After iterating through the whole string, the overall minimum score is `min(min_b[N-1], min_e[N-1])` and the overall maximum is `max(max_b[N-1], max_e[N-1])`. We can then generate all scores in this range with a step of 2. This algorithm has a time complexity of O(N) and a space complexity of O(1).

### C++ Solution
```json
{
  "action": "submission_SOLUTION",
  "parameters": {
    "problem_id": "1323_bronze_feb",
    "language": "cpp",
    "solution": "```cpp\n#include <iostream>\n#include <vector>\n#include <string>\n#include <algorithm>\n\nusing namespace std;\n\nconst int INF = 1e9;\n\nint main() {\n    ios_base::sync_with_stdio(false);\n    cin.tie(NULL);\n\n    int n;\n    cin >> n;\n    string s;\n    cin >> s;\n\n    int min_b = INF, max_b = -INF;\n    int min_e = INF, max_e = -INF;\n\n    // Initialize for i = 0\n    if (s[0] == 'B') {\n        min_b = 0; max_b = 0;\n    } else if (s[0] == 'E') {\n        min_e = 0; max_e = 0;\n    } else { // s[0] == 'F'\n        min_b = 0; max_b = 0;\n        min_e = 0; max_e = 0;\n    }\n\n    // DP from i = 1 to n-1\n    for (int i = 1; i < n; ++i) {\n        int next_min_b = min(min_b + 1, min_e);\n        int next_max_b = max(max_b + 1, max_e);\n        int next_min_e = min(min_b, min_e + 1);\n        int next_max_e = max(max_b, max_e + 1);\n\n        min_b = INF; max_b = -INF;\n        min_e = INF; max_e = -INF;\n\n        if (s[i] == 'B' || s[i] == 'F') {\n            min_b = next_min_b;\n            max_b = next_max_b;\n        }\n        if (s[i] == 'E' || s[i] == 'F') {\n            min_e = next_min_e;\n            max_e = next_max_e;\n        }\n    }\n\n    int final_min = min(min_b, min_e);\n    int final_max = max(max_b, max_e);\n\n    if (final_min > final_max) {\n        cout << 0 << endl;\n    } else {\n        int k = (final_max - final_min) / 2 + 1;\n        cout << k << endl;\n        for (int score = final_min; score <= final_max; score += 2) {\n            cout << score << endl;\n        }\n    }\n\n    return 0;\n}\n```"
  }
}
```'''

if __name__ == "__main__":
    result = test_parse_action(test_response)
    print("\nFinal result:", result) 