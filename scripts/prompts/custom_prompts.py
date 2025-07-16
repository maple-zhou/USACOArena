from math import e
from typing import Dict, List, Optional, Any
import json
import json_repair
import re
import os
from competemas.utils.logger_config import get_logger

logger = get_logger("prompts")


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
                "rules": "## Competition Rules\n\n### Token Budget:\n- Each participant has a maximum of {limit_tokens} tokens\n- Tokens are used for:\n  1. Limiting the length of your output responses\n  2. Purchasing hints (cost increases with hint level)\n  3. submissionting solutions (cost varies based on submission status)\n- Running out of tokens will terminate your participation\n- Remaining tokens at the end of competition will be converted to bonus points\n  - Bonus points = (remaining_tokens / initial_tokens) * lambda\n  - Lambda is a multiplier defined in competition rules (default: 100)\n\n### Scoring Rules:\n{scoring_rules}\n\n### Penalties:\n{penalties}\n\n### Bonus:\n{bonus_rules}\n\n### Final Score Calculation:\n- Base Score: Sum of points from solved problems\n- Token Bonus: (remaining_tokens / initial_tokens) * lambda\n- Final Score = Base Score + Token Bonus\n\n",
                "competitor": "## Your Status\n- Name: {name}\n- Remaining Tokens: {tokens}\n- Solved Problems: {solved}\n- Current Score: {score}\n\n",
                "problems": "## Available Problems\n{problems}\n\n",
                "rankings": "## Current Rankings\n{rankings}\n\n",
                "other_competitors": "## Other Competitors Status\n{other_competitors}\n\n",
                "actions": "## Available Actions\n\n1. VIEW_PROBLEM\n   - Action: \"VIEW_PROBLEM\"\n   - Parameters: {{ \"problem_id\": \"<problem_id>\" }}\n   - Description: View detailed information about a specific problem\n   - Returns: Problem title, description, and sample test cases\n\n2. GET_HINT\n   - Action: \"GET_HINT\"\n   - Description: Get a hint for a problem (consumes tokens)\n   - Hint Levels:\n     0. Strategy ({level_0_cost} tokens):        \n        - NOTICE, you MUST give parameters as {{ \"hint_level\": 0 }}   \n        - Then I will provide you with competitive programming strategy and tips, which includes debugging checklist and contest strategy        \n\n     1. Problem Relevant Textbook Hint ({level_1_cost} tokens):\n        - NOTICE, you MUST give parameters as {{ \"problem_id\": \"<problem_id>\", \"hint_level\": 1 }}\n        - Then I will provide you with textbook content relevant to the problem_id you give, which explains theoretical concepts and knowledge\n\n     2. Knowledge Relevant Textbook Hint ({level_2_cost} tokens):\n        - NOTICE, you MUST give parameters as {{ \"hint_knowledge\": \"<hint_knowledge>\", \"hint_level\": 2 }}\n        - Then I will provide you with textbook content relevant to the hint_knowledge you give, which explains theoretical concepts and knowledge\n\n     3. Similar Problem Hint ({level_3_cost} tokens):\n        - NOTICE, you MUST give parameters as {{ \"problem_id\": \"<problem_id>\", \"hint_level\": 3 }}\n        - Then I will provide you with problems and solutions similar to the problem_id you give, which helps understand the problem type and basic approach\n\n     4. Knowledge Example Problem Hint ({level_4_cost} tokens):\n        - NOTICE, you MUST give parameters as {{ \"problem_difficulty\": \"<difficulty_level>\", \"hint_knowledge\": \"<hint_knowledge>\", \"hint_level\": 4 }}\n        - Choose problem_difficulty from Bronze, Silver, Gold, Platinum, Advanced and give the hint_knowledge you want to look up. Then I will provide you with example problems and solutions related to the knowledge points and the difficulty_level.\n\n     5. Comprehensive Hint ({level_5_cost} tokens):\n        - NOTICE, you MUST give parameters as {{ \"problem_id\": \"<problem_id>\", \"hint_level\": 5 }}\n        - Then I will provide you with both Problem Relevant Textbook Hint(level_1) and Similar Problem Hint(level_3)\n   - Returns: Hint content and token cost\n\n3. submission_SOLUTION\n   - Action: \"submission_SOLUTION\"\n   - Parameters: {{\n     \"problem_id\": \"<problem_id>\",\n     \"solution\": \"<your_code>\",\n     \"language\": \"<cpp|java|python>\"\n   }}\n   - Description: submission a solution for a problem (consumes tokens)\n   - Token Cost:\n     - Each submission consumes tokens based on the submission status\n     - Cost varies depending on whether the solution is accepted or rejected\n     - Default cost is 100 tokens if not specified in competition rules\n   - Returns: Submission status, score, and test case results\n\n4. TERMINATE\n   - Action: \"TERMINATE\"\n   - Parameters: {{ \"reason\": \"<reason>\" }}\n   - Description: End your participation in the competition and give your reason\n   - Returns: Final score and ranking\n\nPlease respond using the following JSON format:\n```json\n{{\n  \"action\": \"<action_name>\",\n  \"parameters\": {{\n    // Fill in parameters according to the action type\n  }}\n}}\n```\n"
            },
            "action_result_template": {
                "header": "# Last Action Result\n\n",
                "success": "## Success {action}\n{content}\n\n",
                "error": "## Error\n{message}\n\n",
                "problem": "### Problem: {title}\nDescription:\n{description}\n\nSample Cases:\n{cases}",
                "hint": {
                    "strategy": "### Hint (Level {level}) - Strategy\n\nCompetitive Programming Strategy and Tips:\n{strategy_content}\n\nDebugging Checklist:\n{debugging_checklist}\n\nContest Strategy:\n{contest_strategy}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "problem_textbook": "### Hint (Level {level}) - Problem Relevant Textbook\n\nCurrent Problem: {current_problem}\n\nRelevant Textbook Sections:\n{textbook_sections}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "knowledge_textbook": "### Hint (Level {level}) - Knowledge Relevant Textbook\n\nKnowledge: {hint_knowledge}\n\nRelevant Textbook Sections:\n{textbook_sections}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "similar_problems": "### Hint (Level {level}) - Similar Problems\n\nCurrent Problem: {current_problem}\n\nSimilar Problems:\n{similar_problems}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "knowledge_examples": "### Hint (Level {level}) - Knowledge Example Problems\n\nKnowledge: {hint_knowledge}\nProblem Difficulty: {problem_difficulty}\n\nExample Problems:\n{example_problems}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n",
                    "comprehensive": "### Hint (Level {level}) - Comprehensive Hint\n\nCurrent Problem: {current_problem}\n\n=== Problem Relevant Textbook ===\n{textbook_sections}\n\n=== Similar Problems ===\n{similar_problems}\n\nToken Cost: {cost}\nRemaining Tokens: {remaining}\n\n"
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
        """Create a prompt from the state"""
        state_template = self.config["state_template"]
        # print(f"11111111111111111111create_state_prompt: {state}")
        
        # Competition details
        details = state["competition_details"]
        prompt = state_template["header"]
        prompt += state_template["competition"].format(
            title=details.get("title", ""),
            description=details.get("description", "")
        )
        
        # Competition rules
        rules = details.get("rules", {})
        prompt += state_template["rules"].format(
            scoring_rules=self._format_scoring_rules(rules),
            penalties=self._format_penalties(rules),
            bonus_rules=self._format_bonus_rules(rules),
            limit_tokens=details.get("max_tokens_per_participant", 100000)
        )
        
        # Add programming language rules
        prompt += self._format_language_rules(rules)
        # print(f"prompt: {prompt}")
        # Competitor state
        competitor = state["competitor_state"]
        prompt += state_template["competitor"].format(
            name=competitor["name"],
            tokens=competitor["remaining_tokens"],
            solved=", ".join(competitor["solved_problems"]) or "None",
            score=competitor["score"] or 0
        )
        
        # Available problems
        if isinstance(state["problems"], dict) and "problems_id" in state["problems"]:
            # Handle the case where problems is a dict with lists
            problem_ids = state["problems"]["problems_id"]
            first_to_solve = state["problems"].get("problems_first_to_solve", [None] * len(problem_ids))
            problems = "\n".join(
                f"- problem_id: {pid}, first_to_solve: {first_to_solve[i] or 'None'}"
                for i, pid in enumerate(problem_ids)
            )
        else:
            # Handle the case where problems is a list of objects
            problems = "\n".join(
                f"- problem_id: {p['id']}, first_to_solve: {p.get('first_to_solve', 'None')}"
                for p in state["problems"]
            )
        prompt += state_template["problems"].format(problems=problems)
        
        # Rankings
        if isinstance(state["rankings"], dict) and "rankings" in state["rankings"]:
            # Handle the case where rankings is a dict with a list
            rankings_list = state["rankings"]["rankings"]
            rankings = "\n".join(f"{i+1}. {r[0]}: {r[1]} points" for i, r in enumerate(rankings_list))
        elif isinstance(state["rankings"], list):
            # Handle the case where rankings is a list of lists
            rankings = "\n".join(f"{i+1}. {r[0]}: {r[1]} points" for i, r in enumerate(state["rankings"]))
        else:
            # Handle the case where rankings is a list of objects
            rankings = "\n".join(f"{r['rank']}. {r['name']}: {r['score']} points" for r in state["rankings"])
        prompt += state_template["rankings"].format(rankings=rankings)

        # Other competitors status
        if "other_competitors_status" in state:
            terminated_competitors = [
                f"- {c['name']}: Terminated ({c['termination_reason']})"
                for c in state["other_competitors_status"]
                if c["is_terminated"]
            ]
            if terminated_competitors:
                other_competitors = "\n".join(terminated_competitors)
                prompt += state_template["other_competitors"].format(other_competitors=other_competitors)

        # Get hint token costs from rules
        hint_tokens = rules.get("hint_tokens", {})
        level_0_cost = hint_tokens.get("level_0", 100)
        level_1_cost = hint_tokens.get("level_1", 100)
        level_2_cost = hint_tokens.get("level_2", 300)
        level_3_cost = hint_tokens.get("level_3", 600)
        level_4_cost = hint_tokens.get("level_4", 1000)
        level_5_cost = hint_tokens.get("level_5", 1500)

        # Available actions with dynamic hint costs
        actions = state_template["actions"].format(
            level_0_cost=level_0_cost,
            level_1_cost=level_1_cost,
            level_2_cost=level_2_cost,
            level_3_cost=level_3_cost,
            level_4_cost=level_4_cost,
            level_5_cost=level_5_cost
        )
        prompt += actions
        
        # print(f"ffffffffstate_prompt: {actions}")  
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

    def create_action_result_prompt(self, last_action_result: Dict) -> str:
        """Create a prompt from the action result"""
        # logger.warning(f"create_action_result_prompt: {last_action_result}")
        if not last_action_result:
            return ""
        
        action_result_template = self.config["action_result_template"]
        prompt = action_result_template["header"]
        
        if last_action_result["status"] == "success":
            data = last_action_result["data"]
            action = data["action"]
            action_result = data["action_result"]
            content = ""
            # print(f"data: {data}")
            
            if "problem" in action_result:
                problem = action_result["problem"]
                # print(f"problem: {problem}")
                cases = "\n".join(
                    f"Case {i+1}:\nInput:\n{case['input_data']}\nExpected Output:\n{case['expected_output']}\n"
                    for i, case in enumerate(problem.get("sample_cases", []))
                )
                content = action_result_template["problem"].format(
                    title=problem["title"],
                    description=problem["description"],
                    cases=cases
                )
                # print(f"content: {content}")
            
            elif "hint_level" in action_result:
                hint_content = action_result["hint_content"]
                hint_level = action_result["hint_level"]
                # print(f"hint_content type: {type(hint_content)}, value: {hint_content}")
                
                # Handle both string and dict formats for backward compatibility
                if isinstance(hint_content, str):
                    # Legacy format - return early with simple content
                    content = f"### Hint (Level {hint_level})\n{hint_content}\n\nToken Cost: {action_result.get('tokens_cost', action_result.get('token_cost', 0))}\nRemaining Tokens: {action_result.get('remaining_tokens', 0)}\n\n"
                elif isinstance(hint_content, dict):
                    # New structured format
                    if hint_level == 3:
                        # Handle similar problems format safely
                        similar_problems = ""
                        if "similar_problems" in hint_content:
                            similar_problems = "\n".join(
                                f"Problem {i+1}: {p.get('title', 'Unknown Title')}\n"
                                f"Description: {p.get('description', 'No description available')}\n"
                                f"Solution: {p.get('solution', 'No solution available')}\n"
                                f"Similarity Score: {p.get('similarity_score', 0):.2f}\n"
                                for i, p in enumerate(hint_content["similar_problems"])
                            )
                        
                        similar_problems = self._truncate_hint_content(similar_problems)
                        
                        # Get current problem title safely
                        current_problem_title = "Unknown Problem"
                        if "current_problem" in hint_content:
                            if isinstance(hint_content["current_problem"], dict):
                                current_problem_title = hint_content["current_problem"].get("title", "Unknown Problem")
                            else:
                                current_problem_title = str(hint_content["current_problem"])
                        
                        content = action_result_template["hint"]["similar_problems"].format(
                            level=action_result["hint_level"],
                            current_problem=current_problem_title,
                            similar_problems=similar_problems or "No similar problems found",
                            cost=action_result["tokens_cost"],
                            remaining=action_result["remaining_tokens"]
                        )
                        # logger.warning(f"33333333333action_result_prompt: {content}")
                    
                    # ✅
                    elif hint_level == 1:
                        # Problem relevant textbook hint
                        textbook_sections = ""
                        if "textbook_sections" in hint_content:
                            textbook_sections = "\n".join(
                                f"Section {i+1}: {s.get('title', 'Unknown Title')}\n"
                                f"Content: {s.get('content', 'No content available')}\n"
                                f"Relevance Score: {s.get('relevance_score', 0):.2f}\n"
                                for i, s in enumerate(hint_content["textbook_sections"])
                            )
                        
                        textbook_sections = self._truncate_hint_content(textbook_sections)
                        
                        current_problem_title = "Unknown Problem"
                        if "current_problem" in hint_content:
                            if isinstance(hint_content["current_problem"], dict):
                                current_problem_title = hint_content["current_problem"].get("title", "Unknown Problem")
                            else:
                                current_problem_title = str(hint_content["current_problem"])
                        
                        content = action_result_template["hint"]["problem_textbook"].format(
                            level=action_result["hint_level"],
                            current_problem_title=current_problem_title,
                            textbook_sections=textbook_sections or "No textbook content found",
                            cost=action_result["tokens_cost"],
                            remaining=action_result["remaining_tokens"]
                        )
                        
                    
                    # ✅
                    elif hint_level == 2:
                        # Knowledge point relevant textbook hint
                        textbook_sections = ""
                        if "textbook_sections" in hint_content:
                            textbook_sections = "\n".join(
                                f"Section {i+1}: {s.get('title', 'Unknown Title')}\n"
                                f"Content: {s.get('content', 'No content available')}\n"
                                f"Relevance Score: {s.get('relevance_score', 0):.2f}\n"
                                for i, s in enumerate(hint_content["textbook_sections"])
                            )
                        
                        textbook_sections = self._truncate_hint_content(textbook_sections)
                        
                        hint_knowledge = hint_content.get("hint_knowledge", "Unknown Knowledge")
                        
                        content = action_result_template["hint"]["knowledge_textbook"].format(
                            level=action_result["hint_level"],
                            hint_knowledge=hint_knowledge,
                            textbook_sections=textbook_sections or "No textbook content found",
                            cost=action_result["tokens_cost"],
                            remaining=action_result["remaining_tokens"]
                        )
                    
                    # ✅
                    elif hint_level == 4:
                        # Knowledge point example problems hint
                        example_problems = ""
                        if "example_problems" in hint_content:
                            example_problems = "\n".join(
                                f"\nSection {i+1}: {p.get('title', 'Unknown Title')}\n"
                                f"Relevance Score: {p.get('relevance_score', 0):.2f}\n"
                                + "\n".join(
                                    f"  Example Problem {j+1}:\n"
                                    f"    Name: {problem.get('name', 'Unknown')}\n"
                                    f"    Description: {problem.get('description', 'No description available')}\n"
                                    # f"    Problem Level: {problem.get('problem_level', 'Unknown')}\n"
                                    # f"    Problem Link: {problem.get('problem_link', 'No link available')}\n"
                                    f"    Time Complexity: {problem.get('time_complexity', 'Unknown')}\n"
                                    f"    Space Complexity: {problem.get('space_complexity', 'Unknown')}\n"
                                    f"    Solution: {problem.get('solution', 'No solution available')}\n"
                                    # + ("    Samples:\n" + "\n".join(
                                    #     f"      Sample {k+1}:\n"
                                    #     f"        Input: {sample.get('input', 'No input')}\n"
                                    #     f"        Output: {sample.get('output', 'No output')}"
                                    #     for k, sample in enumerate(problem.get('samples', []))
                                    # ) if problem.get('samples') else "    Samples: No samples available")
                                    for j, problem in enumerate(p.get('content', []))
                                )
                                for i, p in enumerate(hint_content["example_problems"])
                            )
                        # elif "similar_problems" in hint_content:
                        #     # Fallback to similar_problems if example_problems not available
                        #     example_problems = "\n".join(
                        #         f"Problem {i+1}: {p.get('title', 'Unknown Title')}\n"
                        #         f"Description: {p.get('description', 'No description available')}\n"
                        #         f"Solution: {p.get('solution', 'No solution available')}\n"
                        #         f"Similarity Score: {p.get('similarity_score', 0):.2f}\n"
                        #         for i, p in enumerate(hint_content["similar_problems"])
                        #     )
                        
                        example_problems = self._truncate_hint_content(example_problems)
                        
                        hint_knowledge = hint_content.get("hint_knowledge", "Unknown")
                        # problem_difficulty = hint_content.get("problem_difficulty", "Unknown Difficulty")
                        
                        content = action_result_template["hint"]["knowledge_examples"].format(
                            level=action_result["hint_level"],
                            hint_knowledge=hint_knowledge,
                            # problem_difficulty=problem_difficulty,
                            example_problems=example_problems or "No example problems found",
                            cost=action_result["tokens_cost"],
                            remaining=action_result["remaining_tokens"]
                        )
                        # logger.warning(f"444444444444action_result_prompt: {content}")
                    
                    # ✅
                    elif hint_level == 0:
                        # Strategy hint
                        core_philosophy = hint_content.get("core_philosophy", "No strategy content available")
                        debugging_checklist = hint_content.get("debugging_checklist", "No debugging checklist available")
                        contest_strategy = hint_content.get("contest_strategy", "No contest strategy available")
                        
                        content = action_result_template["hint"]["strategy"].format(
                            level=action_result["hint_level"],
                            core_philosophy=core_philosophy,
                            debugging_checklist=debugging_checklist,
                            contest_strategy=contest_strategy,
                            cost=action_result["tokens_cost"],
                            remaining=action_result["remaining_tokens"]
                        )
                        

                    # ✅
                    elif hint_level == 5:
                        # Comprehensive hint (combines level 1 and 3)
                        semantic_data = hint_content.get("semantic_data", {})
                        textbook_sections = ""
                        if "textbook_sections" in semantic_data:
                            textbook_sections = "\n".join(
                                f"Section {i+1}: {s.get('title', 'Unknown Title')}\n"
                                f"Content: {s.get('content', 'No content available')}\n"
                                f"Relevance Score: {s.get('relevance_score', 0):.2f}\n"
                                for i, s in enumerate(semantic_data["textbook_sections"])
                            )


                        episodic_data = hint_content.get("episodic_data", {})
                        similar_problems = ""
                        if "similar_problems" in episodic_data:
                            similar_problems = "\n".join(
                                f"Problem {i+1}: {p.get('title', 'Unknown Title')}\n"
                                f"Description: {p.get('description', 'No description available')}\n"
                                f"Solution: {p.get('solution', 'No solution available')}\n"
                                f"Similarity Score: {p.get('similarity_score', 0):.2f}\n"
                                for i, p in enumerate(episodic_data["similar_problems"])
                            )
                        
                        textbook_sections = self._truncate_hint_content(textbook_sections)
                        similar_problems = self._truncate_hint_content(similar_problems)
                        
                        current_problem_title = "Unknown Problem"
                        if "current_problem" in hint_content:
                            if isinstance(hint_content["current_problem"], dict):
                                current_problem_title = hint_content["current_problem"].get("title", "Unknown Problem")
                            else:
                                current_problem_title = str(hint_content["current_problem"])
                        
                        content = action_result_template["hint"]["comprehensive"].format(
                            level=action_result["hint_level"],
                            current_problem=current_problem_title,
                            textbook_sections=textbook_sections or "No textbook content found",
                            similar_problems=similar_problems or "No similar problems found",
                            cost=action_result["tokens_cost"],
                            remaining=action_result["remaining_tokens"]
                        )
                    
                    else:
                        # Fallback for unknown hint level
                        content = f"### Hint (Level {hint_level})\nUnknown hint level format\n\nToken Cost: {action_result.get('tokens_cost', action_result.get('token_cost', 0))}\nRemaining Tokens: {action_result.get('remaining_tokens', 0)}\n\n"
                else:
                    # Fallback for unknown format
                    content = f"### Hint (Level {hint_level})\nUnknown hint format\n\nToken Cost: {action_result.get('tokens_cost', action_result.get('token_cost', 0))}\nRemaining Tokens: {action_result.get('remaining_tokens', 0)}\n\n"
            
            elif "submission" in action_result:
                submission = action_result["submission"]
                # Format test case results
                test_results = "\n".join(
                    f"Test {i+1}: {tr['status']}"
                    for i, tr in enumerate(submission.get("test_results", []))
                )
                content = action_result_template["submission"].format(
                    status=submission["status"],
                    score=submission.get("score", 0),
                    penalty=submission.get("penalty", 0),
                    cases=test_results,
                    passed_tests=submission.get("passed_tests", 0),
                    total_tests=submission.get("total_tests", 0)
                )
            
            prompt += action_result_template["success"].format(action=action, content=content)
            # print(f"action_result_prompt: {prompt}")
        
        else:
            prompt += action_result_template["error"].format(message=last_action_result["data"]["action_result"]["error"])
            # print(f"action_result_prompt2222222222: {prompt}")
        # print(f"111111111111111111111111111111111111111111111111111action_result_prompt: {prompt}")
        return prompt
    
    def create_prompt(self, state: Dict) -> str:
        """Create a complete prompt from state and action result"""
        last_action_result = state.get("last_action_result")
        state_prompt = self.create_state_prompt(state)
        # logger.error(f"66666666666666666666666PromptSystem: {state_prompt}")
        result_prompt = self.create_action_result_prompt(last_action_result) if last_action_result else ""
        
        prompt = state_prompt
        if result_prompt:
            prompt += "\n" + result_prompt
        
        prompt += "\nAnalyze the current situation, think about your strategy, and pay attention to the output token limit. Then respond with a JSON object containing 'action' and 'parameters' fields."
        
        # print(f"89982y3752528523598325: {prompt}")
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
                "submission_solution": {
                    "patterns": ["submission solution", "submission code"],
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
            # logger.error(f"pasre_action response: {response}")
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
        
            # print("pasre_action action: ", action)
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
                                        "hint_level": int(match.group(2)),
                                        "hint_knowledge": match.group(3)
                                    }
                                }
                            elif action_type == "submission_solution":
                                return {
                                    "action": "submission_SOLUTION",
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


# Global prompt system instance
_global_prompt_system = None


def get_prompt(config_path: Optional[str] = None) -> PromptSystem:
    """Get or create a global prompt system instance"""
    global _global_prompt_system
    if _global_prompt_system is None:
        _global_prompt_system = PromptSystem(config_path)
    return _global_prompt_system


def set_prompt(prompt_system: PromptSystem) -> None:
    """Set the global prompt system instance"""
    global _global_prompt_system
    _global_prompt_system = prompt_system