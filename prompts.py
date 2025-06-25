from typing import Dict, List, Optional, Any
import json
import json_repair
import re
import os
import logging

logger = logging.getLogger("prompts")


class PromptSystem:
    """System for managing competition prompts"""
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load prompt configuration from file or use defaults"""
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load prompt config from {config_path}: {e}")
        
        # Default configuration
        return {
            "system_prompt": "You are a competitive programming agent participating in a coding competition. You will receive the current state of the competition and results of your previous actions. Your goal is to achieve the highest score possible while managing your token budget wisely. Your token budget has two main uses: 1) Limiting the length of your output responses, and 2) Purchasing hints for problems.\n\nBefore taking any action, you should:\n1. Analyze the current competition state and your remaining resources\n2. Evaluate the difficulty and potential score of each problem\n3. Consider the optimal strategy for token usage (e.g., when to use hints)\n4. Plan your approach to maximize score while minimizing token consumption\n\nPlease respond with a JSON object containing 'action' and 'parameters' fields.",
            "state_template": {
                "header": "# Competition State\n\n",
                "competition": "## Competition: {title}\nDescription: {description}\n\n",
                "rules": "## Competition Rules\n\n### Token Budget:\n- Each participant has a maximum of {max_tokens} tokens\n- Tokens are used for:\n  1. Limiting the length of your output responses\n  2. Purchasing hints (cost increases with hint level)\n  3. Submitting solutions (cost varies based on submission status)\n- Running out of tokens will terminate your participation\n- Remaining tokens at the end of competition will be converted to bonus points\n  - Bonus points = (remaining_tokens / initial_tokens) * lambda\n  - Lambda is a multiplier defined in competition rules (default: 100)\n\n### Scoring Rules:\n{scoring_rules}\n\n### Penalties:\n{penalties}\n\n### Bonus:\n{bonus_rules}\n\n### Final Score Calculation:\n- Base Score: Sum of points from solved problems\n- Token Bonus: (remaining_tokens / initial_tokens) * lambda\n- Final Score = Base Score + Token Bonus\n\n",
                "competitor": "## Your Status\n- Name: {name}\n- Remaining Tokens: {tokens}\n- Solved Problems: {solved}\n- Current Score: {score}\n\n",
                "problems": "## Available Problems\n{problems}\n\n",
                "rankings": "## Current Rankings\n{rankings}\n\n",
                "other_competitors": "## Other Competitors Status\n{other_competitors}\n\n",
                "actions": "## Available Actions\n\n1. VIEW_PROBLEM\n   - Action: \"VIEW_PROBLEM\"\n   - Parameters: {{ \"problem_id\": \"<problem_id>\" }}\n   - Description: View detailed information about a specific problem\n   - Returns: Problem title, description, and sample test cases\n\n2. GET_HINT\n   - Action: \"GET_HINT\"\n   - Parameters: {{ \"problem_id\": \"<problem_id>\", \"hint_level\": <level> }}\n   - Description: Get a hint for a problem (consumes tokens)\n   - Hint Levels:\n     1. Basic Hint ({level_1_cost} tokens):\n        - Provides relevant textbook knowledge\n        - Explains theoretical concepts and solution strategies\n     2. Detailed Hint ({level_2_cost} tokens):\n        - Shows similar problems and their solutions\n        - Helps understand the problem type and basic approach\n     3. Comprehensive Hint ({level_3_cost} tokens):\n        - Combines similar problems and textbook knowledge\n        - Includes integration guide for applying concepts\n   - Returns: Hint content and token cost\n\n3. SUBMIT_SOLUTION\n   - Action: \"SUBMIT_SOLUTION\"\n   - Parameters: {{\n     \"problem_id\": \"<problem_id>\",\n     \"solution\": \"<your_code>\",\n     \"language\": \"<cpp|java|python>\"\n   }}\n   - Description: Submit a solution for a problem (consumes tokens)\n   - Token Cost:\n     - Each submission consumes tokens based on the submission status\n     - Cost varies depending on whether the solution is accepted or rejected\n     - Default cost is 100 tokens if not specified in competition rules\n   - Returns: Submission status, score, and test case results\n\n4. TERMINATE\n   - Action: \"TERMINATE\"\n   - Parameters: {{}}\n   - Description: End your participation in the competition\n   - Returns: Final score and ranking\n\nPlease respond using the following JSON format:\n```json\n{{\n  \"action\": \"<action_name>\",\n  \"parameters\": {{\n    // Fill in parameters according to the action type\n  }}\n}}\n```\n"
            },
            "action_result_template": {
                "header": "# Last Action Result\n\n",
                "success": "## Success\n{content}\n\n",
                "error": "## Error\n{message}\n\n",
                "problem": "### Problem: {title}\nDescription:\n{description}\n\nSample Cases:\n{cases}",
                "hint": {
                    "episodic": "### Hint (Level {level}) - Similar Problems\n\nCurrent Problem: {current_problem}\n\nSimilar Problems:\n{similar_problems}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "semantic": "### Hint (Level {level}) - Textbook Knowledge\n\nCurrent Problem: {current_problem}\n\nRelevant Textbook Sections:\n{textbook_sections}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "combined": "### Hint (Level {level}) - Combined Knowledge\n\nCurrent Problem: {current_problem}\n\n=== Similar Problems ===\n{episodic_content}\n\n=== Textbook Knowledge ===\n{semantic_content}\n\n=== Integration Guide ===\n{integration_points}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n"
                },
                "submission": "### Submission Result\nStatus: {status}\nPassed Tests: {passed_tests}/{total_tests}\nScore: {score}\nPenalty: {penalty}\n\nTest Results:\n{cases}\n\n"
            }
        }
    
    def _format_scoring_rules(self, rules: Dict) -> str:
        """Format scoring rules from competition configuration"""
        scoring_rules = []
        for difficulty, points in rules.get("scoring", {}).items():
            scoring_rules.append(f"- {difficulty.capitalize()} problems: {points} points each")
        
        if not scoring_rules:
            scoring_rules = [
                "- Bronze problems: 100 points each",
                "- Silver problems: 200 points each",
                "- Gold problems: 500 points each",
                "- Platinum problems: 1000 points each"
            ]
        
        scoring_rules.append("\nPoints are awarded proportionally to the number of test cases passed. For example, if you pass 7 out of 10 test cases for a Bronze problem, you'll receive 70 points.")
        
        return "\n".join(scoring_rules)
    
    def _format_penalties(self, rules: Dict) -> str:
        """Format penalties from competition configuration"""
        penalties = []
        for status, points in rules.get("penalties", {}).items():
            penalties.append(f"- {status}: {points} points")
        
        if not penalties:
            penalties = [
                "- Wrong Answer (WA): -10 points",
                "- Runtime Error (RE): -10 points",
                "- Compilation Error (CE): -5 points",
                "- Time Limit Exceeded (TLE): -10 points",
                "- Memory Limit Exceeded (MLE): -10 points"
            ]
        
        return "Each submission with the following results will incur a penalty:\n" + "\n".join(penalties)
    
    def _format_bonus_rules(self, rules: Dict) -> str:
        """Format bonus rules from competition configuration"""
        bonus_points = rules.get("bonus_for_first_ac", 100)
        return f"The first participant to solve each problem completely will receive a {bonus_points}-point bonus."
    
    def _format_language_rules(self, rules: Dict) -> str:
        """Format programming language rules"""
        return """### Programming Languages:
Available languages: C++17, Java, and Python3.

Important Notes:
- C++17 solutions are guaranteed to pass all test cases within time limits
- Java and Python solutions may not be able to pass all test cases due to time constraints
- Choose your programming language wisely based on the problem requirements\n\n"""
    
    def create_state_prompt(self, state: Dict) -> str:
        """Create a prompt from the competition state"""
        config = self.config["state_template"]
        
        # Competition details
        details = state["competition_details"]
        prompt = config["header"]
        prompt += config["competition"].format(
            title=details.get("title", ""),
            description=details.get("description", "")
        )
        
        # Competition rules
        rules = details.get("rules", {})
        prompt += config["rules"].format(
            scoring_rules=self._format_scoring_rules(rules),
            penalties=self._format_penalties(rules),
            bonus_rules=self._format_bonus_rules(rules),
            max_tokens=details.get("max_tokens_per_participant", 1e7)
        )
        
        # Add programming language rules
        prompt += self._format_language_rules(rules)
        
        # Competitor state
        competitor = state["competitor_state"]
        prompt += config["competitor"].format(
            name=competitor["name"],
            tokens=competitor["remaining_tokens"],
            solved=", ".join(competitor["solved_problems"]) or "None",
            score=competitor["final_score"] or 0
        )
        
        # Available problems
        problems = "\n".join(
            f"- problem_id: {p['id']}, first_to_solve: {p.get('first_to_solve', 'None')}"
            for p in state["problems"]
        )
        prompt += config["problems"].format(problems=problems)
        
        # Rankings
        rankings = "\n".join(f"{r['rank']}. {r['name']}: {r['score']} points" for r in state["rankings"])
        prompt += config["rankings"].format(rankings=rankings)

        # Other competitors status
        if "other_competitors_status" in state:
            terminated_competitors = [
                f"- {c['name']}: Terminated ({c['termination_reason']})"
                for c in state["other_competitors_status"]
                if c["is_terminated"]
            ]
            if terminated_competitors:
                other_competitors = "\n".join(terminated_competitors)
                prompt += config["other_competitors"].format(other_competitors=other_competitors)

        # Get hint token costs from rules
        hint_tokens = rules.get("hint_tokens", {})
        level_1_cost = hint_tokens.get("level_1", 100)
        level_2_cost = hint_tokens.get("level_2", 300)
        level_3_cost = hint_tokens.get("level_3", 600)

        # Available actions with dynamic hint costs
        actions = config["actions"].format(
            level_1_cost=level_1_cost,
            level_2_cost=level_2_cost,
            level_3_cost=level_3_cost
        )
        prompt += actions
        
        return prompt
    
    def _truncate_hint_content(self, content: str, max_length: int = 20000) -> str:
        """Truncate hint content to ensure it doesn't exceed the maximum length"""
        if len(content) <= max_length:
            return content
        
        # Find the last complete sentence or paragraph
        truncated = content[:max_length]
        last_period = truncated.rfind('.')
        last_newline = truncated.rfind('\n')
        cut_point = max(last_period, last_newline)
        
        if cut_point > 0:
            truncated = truncated[:cut_point + 1]
        
        return truncated

    def create_action_result_prompt(self, action_result: Dict) -> str:
        """Create a prompt from the action result"""
        if not action_result:
            return ""
        
        config = self.config["action_result_template"]
        prompt = config["header"]
        
        if action_result["status"] == "success":
            data = action_result["data"]
            content = ""
            
            if "problem" in data:
                problem = data["problem"]
                cases = "\n".join(
                    f"Case {i+1}:\nInput:\n{case['input_data']}\nExpected Output:\n{case['expected_output']}\n"
                    for i, case in enumerate(problem.get("sample_cases", []))
                )
                content = config["problem"].format(
                    title=problem["title"],
                    description=problem["description"],
                    cases=cases
                )
            
            elif "hint" in data:
                hint = data["hint"]
                hint_data = hint["hint_data"]
                
                if hint_data["type"] == "episodic":
                    similar_problems = "\n".join(
                        f"Problem {i+1}: {p['title']}\n"
                        f"Description: {p['description']}\n"
                        f"Solution: {p['solution']}\n"
                        f"Similarity Score: {p['similarity_score']:.2f}\n"
                        for i, p in enumerate(hint_data["similar_problems"])
                    )
                    similar_problems = self._truncate_hint_content(similar_problems)
                    content = config["hint"]["episodic"].format(
                        level=hint["hint_level"],
                        current_problem=hint_data["current_problem"]["title"],
                        similar_problems=similar_problems,
                        cost=hint["tokens_cost"],
                        remaining=hint["remaining_tokens"]
                    )
                
                elif hint_data["type"] == "semantic":
                    textbook_sections = "\n".join(
                        f"Section {i+1}: {s['title']}\n"
                        f"Content: {s['content']}\n"
                        f"Relevance Score: {s['relevance_score']:.2f}\n"
                        for i, s in enumerate(hint_data["textbook_sections"])
                    )
                    textbook_sections = self._truncate_hint_content(textbook_sections)
                    content = config["hint"]["semantic"].format(
                        level=hint["hint_level"],
                        current_problem=hint_data["current_problem"]["title"],
                        textbook_sections=textbook_sections,
                        cost=hint["tokens_cost"],
                        remaining=hint["remaining_tokens"]
                    )
                
                else:  # combined
                    # Format episodic content
                    episodic_content = "\n".join(
                        f"Problem {i+1}: {p['title']}\n"
                        f"Description: {p['description']}\n"
                        f"Solution: {p['solution']}\n"
                        f"Similarity Score: {p['similarity_score']:.2f}\n"
                        for i, p in enumerate(hint_data["episodic_data"]["similar_problems"])
                    )
                    episodic_content = self._truncate_hint_content(episodic_content)
                    
                    # Format semantic content
                    semantic_content = "\n".join(
                        f"Section {i+1}: {s['title']}\n"
                        f"Content: {s['content']}\n"
                        f"Relevance Score: {s['relevance_score']:.2f}\n"
                        for i, s in enumerate(hint_data["semantic_data"]["textbook_sections"])
                    )
                    semantic_content = self._truncate_hint_content(semantic_content)
                    
                    # Format integration points
                    integration_points = "\n".join(
                        f"{i+1}. {point}"
                        for i, point in enumerate(hint_data["integration_points"])
                    )
                    integration_points = self._truncate_hint_content(integration_points)
                    
                    content = config["hint"]["combined"].format(
                        level=hint["hint_level"],
                        current_problem=hint_data["current_problem"]["title"],
                        episodic_content=episodic_content,
                        semantic_content=semantic_content,
                        integration_points=integration_points,
                        cost=hint["tokens_cost"],
                        remaining=hint["remaining_tokens"]
                    )
            
            elif "submission" in data:
                submission = data["submission"]
                # Format test case results
                test_results = "\n".join(
                    f"Test {i+1}: {tr['status']}"
                    for i, tr in enumerate(submission.get("test_results", []))
                )
                content = config["submission"].format(
                    status=submission["status"],
                    score=submission.get("score", 0),
                    penalty=submission.get("penalty", 0),
                    cases=test_results,
                    passed_tests=submission.get("passed_tests", 0),
                    total_tests=submission.get("total_tests", 0)
                )
            
            prompt += config["success"].format(content=content)
        
        else:
            prompt += config["error"].format(message=action_result["message"])
        
        return prompt
    
    def create_prompt(self, state: Dict) -> str:
        """Create a complete prompt from state and action result"""
        action_result = state["last_action_result"]
        state_prompt = self.create_state_prompt(state)
        result_prompt = self.create_action_result_prompt(action_result) if action_result else ""
        
        prompt = state_prompt
        if result_prompt:
            prompt += "\n" + result_prompt
        
        prompt += "\nAnalyze the current situation, think about your strategy, and pay attention to the output token limit. Then respond with a JSON object containing 'action' and 'parameters' fields."
        
        return prompt


class ActionParser:
    """Parser for agent responses into actions"""
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load action pattern configuration from file or use defaults"""
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if "action_patterns" in config:
                        return {"action_patterns": config["action_patterns"]}
            except Exception as e:
                logger.warning(f"Failed to load action config from {config_path}: {e}")
        
        # Default configuration
        return {
            "action_patterns": {
                "view_problem": {
                    "patterns": ["view problem", "look at problem"],
                    "regex": r"problem_id\s*:\s*[\"']?(\w+)[\"']?"
                },
                "get_hint": {
                    "patterns": ["get hint", "request hint"],
                    "regex": r"problem_id\s*:\s*[\"']?(\w+)[\"']?.*?hint_level\s*:\s*(\d+)"
                },
                "submit_solution": {
                    "patterns": ["submit solution", "submit code"],
                    "regex": r"problem_id\s*:\s*[\"']?(\w+)[\"']?.*?solution\s*:\s*[\"']?```(?:python|cpp|java)?\n(.*?)```[\"']?.*?language\s*:\s*[\"']?(python|cpp|java)[\"']?"
                },
                "view_rankings": {
                    "patterns": ["view rankings", "check rankings"],
                    "regex": None
                },
                "terminate": {
                    "patterns": ["terminate", "stop", "end"],
                    "regex": None
                }
            }
        }
    
    def parse_action(self, response: str) -> Dict:
        """Parse the agent's response into an action"""
        try:
            # Try to parse as JSON first
            pattern = r"```(?:json)?\s*(.+?)\s*```"
            matches = re.findall(pattern, response, re.DOTALL)
            if matches:
                json_str = matches[-1]
            else:
                json_str = response
            action = json_repair.loads(json_str)
            if not isinstance(action, dict):
                raise ValueError("Response is not a dictionary")
            
            # Validate action format
            if "action" not in action:
                raise ValueError("Missing 'action' field")
            if "parameters" not in action:
                raise ValueError("Missing 'parameters' field")
            
            return action
        
        except json.JSONDecodeError:
            # If not JSON, try to extract action from text
            response = response.lower().strip()
            patterns = self.config["action_patterns"]
            
            for action_type, pattern_config in patterns.items():
                if any(p in response for p in pattern_config["patterns"]):
                    if pattern_config["regex"]:
                        match = re.search(pattern_config["regex"], response, re.DOTALL)
                        if match:
                            if action_type == "view_problem":
                                return {
                                    "action": "VIEW_PROBLEM",
                                    "parameters": {"problem_id": match.group(1)}
                                }
                            elif action_type == "get_hint":
                                return {
                                    "action": "GET_HINT",
                                    "parameters": {
                                        "problem_id": match.group(1),
                                        "hint_level": int(match.group(2))
                                    }
                                }
                            elif action_type == "submit_solution":
                                return {
                                    "action": "SUBMIT_SOLUTION",
                                    "parameters": {
                                        "problem_id": match.group(1),
                                        "solution": match.group(2).strip(),
                                        "language": match.group(3).lower()
                                    }
                                }
                    elif action_type == "view_rankings":
                        return {
                            "action": "VIEW_RANKINGS",
                            "parameters": {}
                        }
                    elif action_type == "terminate":
                        return {
                            "action": "TERMINATE",
                            "parameters": {}
                        }
            
            # return {
            #     "action": "UNKNOWN",
            #     "parameters": {},
            #     "error": "Could not parse action from response"
            # }
            raise ValueError("Could not parse action from response")