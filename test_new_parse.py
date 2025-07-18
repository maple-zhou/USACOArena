#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.prompts.custom_prompts import ActionParser

def test_parse_action(response: str):
    """Test the improved parse_action logic"""
    print("=" * 60)
    print("Testing improved parse_action with response:")
    print(response[:200] + "..." if len(response) > 200 else response)
    print("=" * 60)
    
    parser = ActionParser()
    
    try:
        result = parser.parse_action(response)
        print("SUCCESS: Parsed action successfully!")
        print("Action:", result.get("action"))
        print("Parameters keys:", list(result.get("parameters", {}).keys()))
        
        # Check if solution is properly extracted
        if "solution" in result.get("parameters", {}):
            solution = result["parameters"]["solution"]
            print(f"Solution length: {len(solution)} characters")
            print(f"Solution preview: {solution[:100]}...")
        
        return result
    except Exception as e:
        print("FAILED:", str(e))
        return None

# Test with the actual response from the log
test_response = '''An elegant dynamic programming approach can solve this problem efficiently.

### Method

The core idea is that for any prefix of the string, the set of all possible "excitement levels" can be complex. However, if we categorize these levels by the last character of the prefix (Bessie or Elsie) and by the parity of the score (even or odd), we find a surprisingly simple structure.

For a prefix of length `i` ending with a specific character ('B' or 'E'), the set of achievable scores of a certain parity forms a contiguous arithmetic progression with a step of 2. For example, all possible even scores might be `{2, 4, 6, 8}`. This can be represented by just its minimum and maximum values, `(2, 8)`.

This allows us to define a dynamic programming state as follows:
`dp[i][char][parity] = (min_score, max_score)`

This stores the minimum and maximum achievable scores for the prefix `S[0...i-1]`, given that the character at `i-1` is `char` ('B' or 'E'), and the score has a specific `parity` (0 for even, 1 for odd).

We can build this DP table iteratively:

1.  **State:** `dp[c][p] = (min, max)` where `c` is the last character (0 for 'B', 1 for 'E') and `p` is the parity. We only need to store the DP state for the previous step `i-1` to compute the state for the current step `i`, making the space complexity `O(1)`.
2.  **Base Case (i=0):**
    *   If `S[0]` is 'B', the only possibility is a score of 0, ending in 'B'. So, `dp[B][even] = (0, 0)`.
    *   If `S[0]` is 'E', `dp[E][even] = (0, 0)`.
    *   If `S[0]` is 'F', it can be 'B' or 'E', so `dp[B][even] = (0, 0)` and `dp[E][even] = (0, 0)`.
3.  **Transition (for i > 0):**
    To compute the DP state for step `i`, we look at the states from `i-1`. For each possible current character `curr_c` ('B' or 'E') and previous character `prev_c`:
    *   If `S[i]` is fixed (not 'F'), `curr_c` must match `S[i]`.
    *   The score increases by 1 if `curr_c == prev_c`.
    *   For each range `(min_prev, max_prev)` from `dp[prev_c][p_prev]`, the new range becomes `(min_prev + added_score, max_prev + added_score)`.
    *   We update the corresponding `dp[curr_c][new_parity]` range by taking the union of the new range with the existing one. Since all scores in a range have the same parity, taking the union of two ranges with the same parity simply means taking the minimum of the two minimums and the maximum of the two maximums.

4.  **Final Result:**
    After iterating through the entire string, the final DP table `dp[N]` contains all possible `(min, max)` ranges for each ending character and parity. We collect all numbers from these valid ranges into a `std::set` to get the unique, sorted list of all possible total excitement levels.

This approach has a time complexity of `O(N)` and a space complexity of `O(1)`, which is efficient enough for the given constraints.

```json
{
  "action": "submission_SOLUTION",
  "parameters": {
    "problem_id": "1323_bronze_feb",
    "language": "cpp",
    "solution": "```cpp\n#include <iostream>\n#include <vector>\n#include <string>\n#include <set>\n#include <algorithm>\n\nconst int INF = 1e9;\n\nstruct Range {\n    int min_val = INF;\n    int max_val = -INF;\n\n    void update(const Range& other) {\n        if (other.min_val != INF) {\n            min_val = std::min(min_val, other.min_val);\n            max_val = std::max(max_val, other.max_val);\n        }\n    }\n};\n\nint main() {\n    std::ios_base::sync_with_stdio(false);\n    std::cin.tie(NULL);\n    int n;\n    std::cin >> n;\n    std::string s;\n    std::cin >> s;\n\n    // dp[char][parity], char 0:B, 1:E, parity 0:even, 1:odd\n    std::vector<std::vector<Range>> dp(2, std::vector<Range>(2));\n\n    // Base case i = 0\n    if (s[0] == 'B') {\n        dp[0][0].update({0, 0}); // dp[B][even]\n    } else if (s[0] == 'E') {\n        dp[1][0].update({0, 0}); // dp[E][even]\n    } else { // 'F'\n        dp[0][0].update({0, 0});\n        dp[1][0].update({0, 0});\n    }\n\n    for (int i = 1; i < n; ++i) {\n        std::vector<std::vector<Range>> next_dp(2, std::vector<Range>(2));\n        char s_char = s[i];\n\n        for (int prev_c = 0; prev_c < 2; ++prev_c) { \n            for (int curr_c = 0; curr_c < 2; ++curr_c) {\n                if (s_char == 'B' && curr_c == 1) continue;\n                if (s_char == 'E' && curr_c == 0) continue;\n\n                int added_score = (prev_c == curr_c);\n\n                for (int p = 0; p < 2; ++p) {\n                    if (dp[prev_c][p].min_val == INF) continue;\n\n                    int new_min = dp[prev_c][p].min_val + added_score;\n                    int new_max = dp[prev_c][p].max_val + added_score;\n                    int new_p = new_min % 2;\n\n                    next_dp[curr_c][new_p].update({new_min, new_max});\n                }\n            }\n        }\n        dp = next_dp;\n    }\n\n    std::set<int> results;\n    for (int c = 0; c < 2; ++c) {\n        for (int p = 0; p < 2; ++p) {\n            if (dp[c][p].min_val != INF) {\n                for (int val = dp[c][p].min_val; val <= dp[c][p].max_val; val += 2) {\n                    results.insert(val);\n                }\n            }\n        }\n    }\n\n    std::cout << results.size() << \"\\n\";\n    for (int val : results) {\n        std::cout << val << \"\\n\";\n    }\n\n    return 0;\n}\n```"
  }
}
```'''

if __name__ == "__main__":
    result = test_parse_action(test_response)
    print("\nFinal result:", result) 