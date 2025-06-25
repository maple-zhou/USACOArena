import json
import time
import requests
import logging
import asyncio
import os
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta

from agents import Agent, GenericAPIAgent
from models import SubmissionStatus

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
logger = logging.getLogger("competition")


class Competitor:
    """Base class for competitors"""
    def __init__(self, name: str, agent: Agent, max_tokens: int = 1e7):
        self.name = name
        self.agent = agent
        self.participant_id: Optional[str] = None
        self.remaining_tokens: int = max_tokens
        self.token_limit: int = max_tokens
        self.solved_problems: List[str] = []
        self.is_running: bool = False
        self.termination_reason: Optional[str] = None
        self.score: int = 0
        self.final_score: int = 0
        self.submission_trial: Dict[str, List] = {}
        self.hint_tokens: int = 0
        self.tokens_score: List[(int, float)] = []
    
    def get_competition_state(self) -> Dict:
        """Get the current state of the competition"""
        return {
            "name": self.name,
            "remaining_tokens": self.remaining_tokens,
            "solved_problems": self.solved_problems,
            "is_running": self.is_running,
            "termination_reason": self.termination_reason,
            "score": self.score,
            "final_score": self.final_score
        }
    
    def terminate(self, reason: str) -> None:
        """Terminate the competitor with a reason"""
        self.is_running = False
        self.termination_reason = reason


class CompetitionOrganizer:
    """Organizer for LLM programming competition"""
    
    def __init__(self, api_base_url: str):
        """
        Initialize the competition organizer
        
        Args:
            api_base_url: Base URL for the competition API
        """
        self.api_base_url = api_base_url
        self.competitors: List[Competitor] = []
        self.competition_id: Optional[str] = None
        self.competition_data: Optional[Dict] = None
        self.output_token_multipliers: Dict[str, float] = {}
        self.input_token_multipliers: Dict[str, float] = {}

        self.output_token_multipliers['gemini-2.5-pro'] = 10
        self.output_token_multipliers['gpt-4.1'] = 8
        self.output_token_multipliers['gpt-4o'] = 10
        self.output_token_multipliers['gpt-4o-mini'] = 0.6
        self.output_token_multipliers['claude-3.7-sonnet'] = 15
        self.output_token_multipliers['grok-3-beta'] = 15
        self.output_token_multipliers['qwen3'] = 0.6
        self.output_token_multipliers['deepseek-v3'] = 1.1

        self.input_token_multipliers['gemini-2.5-pro'] = 1.25
        self.input_token_multipliers['gpt-4.1'] = 2
        self.input_token_multipliers['gpt-4o'] = 2.5
        self.input_token_multipliers['gpt-4o-mini'] = 0.15
        self.input_token_multipliers['claude-3.7-sonnet'] = 3
        self.input_token_multipliers['grok-3-beta'] = 3
        self.input_token_multipliers['qwen3'] = 0.2
        self.input_token_multipliers['deepseek-v3'] = 0.27
    
    def add_competitor(self, competitor: Competitor) -> None:
        """Add a competitor to the competition"""
        self.competitors.append(competitor)
        logger.info(f"Added competitor: {competitor.name}")
    
    def create_competition(
        self,
        title: str,
        description: str,
        problem_ids: List[str],
        max_tokens_per_participant: int = 1e7,
        rules: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Create a new competition
        
        Args:
            title: Competition title
            description: Competition description
            problem_ids: List of problem IDs
            max_tokens_per_participant: Maximum tokens per participant
            rules: Optional competition rules
        
        Returns:
            Competition ID if successful, None otherwise
        """
        try:
            # Prepare request data
            data = {
                "title": title,
                "description": description,
                "problem_ids": problem_ids,
                "max_tokens_per_participant": max_tokens_per_participant,
                "rules": rules or {}
            }
            
            # Make API request
            response = requests.post(
                f"{self.api_base_url}/api/competitions",
                json=data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            if result["status"] != "success":
                raise ValueError(f"API error: {result.get('message', 'Unknown error')}")
            
            # Store competition data
            competition_data = result["data"]["competition"]
            self.competition_id = competition_data["id"]
            self.competition_data = competition_data
            self.competition_data["problem_ids"] = [p["id"] for p in competition_data["problems"]]
            
            # Log any problems that were not found
            not_found_problems = result["data"].get("not_found_problems", [])
            if not_found_problems:
                logger.warning(f"Some problems not found: {not_found_problems}")
            
            logger.info(f"Created competition: {self.competition_id}")
            return self.competition_id
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create competition: {e}")
            return None
    
    def join_competition(self, competition_id: str) -> bool:
        """
        Join the competition
        
        Args:
            competition_id: Competition ID
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get competition details first
            response = requests.get(
                f"{self.api_base_url}/api/competitions/{competition_id}",
                params={"include_details": "true"}
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                raise ValueError(f"API error: {result.get('message', 'Unknown error')}")
            
            # Store competition data
            self.competition_id = competition_id
            self.competition_data = result["data"]
            self.competition_data["problem_ids"] = [p["id"] for p in self.competition_data["problems"]]
            
            # Register each competitor
            for competitor in self.competitors:
                # Add participant
                participant_response = requests.post(
                    f"{self.api_base_url}/api/competitions/{competition_id}/participants",
                    json={"name": competitor.name},
                    headers={"Content-Type": "application/json"}
                )
                participant_response.raise_for_status()
                
                participant_result = participant_response.json()
                if participant_result["status"] != "success":
                    raise ValueError(f"Failed to register {competitor.name}: {participant_result.get('message', 'Unknown error')}")
                
                competitor.is_running = True
                competitor.participant_id = participant_result["data"]["id"]
                logger.info(f"Competitor {competitor.name} joined competition {competition_id}")
            
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to join competition: {e}")
            return False
    
    async def _run_competitor(self, competitor: Competitor) -> Dict:
        """
        Run competition for a single competitor
        
        Args:
            competitor: The competitor to run
        
        Returns:
            Dictionary containing competitor results
        """
        logger.info(f"Starting competition for {competitor.name}")
        
        # Initialize problems list
        problems_result = self._view_problems(competitor)
        problems = problems_result.get("problems", []) if "error" not in problems_result else []
        
        # Initialize competitor state
        competitor.final_score = competitor.score + competitor.remaining_tokens / competitor.token_limit * self.competition_data.get("rules", {}).get("lambda", 100)
        state = {
            "competition_id": self.competition_id,
            "competition_details": self.competition_data,
            "competitor_state": competitor.get_competition_state(),
            "problems": problems,
            "rankings": [],
            "last_action_result": None,
            "other_competitors_status": [
                {
                    "name": c.name,
                    "is_terminated": not c.is_running,
                    "termination_reason": c.termination_reason
                }
                for c in self.competitors if c.name != competitor.name
            ]
        }
        
        # Run competition loop
        while competitor.is_running:
            try:
                # Stop if out of tokens
                if competitor.remaining_tokens <= 0:
                    competitor.terminate("out_of_tokens")
                    logger.info(f"{competitor.name} ran out of tokens")
                    break
                
                # Get next action from competitor
                logger.info(f"Competitor {competitor.name}")
                action = await competitor.agent.process(state)

                logger.info(f"{competitor.name} choose Action: {action['action']}, Tokens remaining: {competitor.remaining_tokens}, Score: {competitor.final_score}")
                
                # Check if action contains token usage information
                prompt_tokens, completion_tokens = action.get("tokens_used", (0, 0))
                
                # Apply token multiplier if set for this competitor
                if competitor.name in self.input_token_multipliers:
                    prompt_tokens = int(prompt_tokens * self.input_token_multipliers[competitor.name])
                    logger.info(f"Applied input token multiplier {self.input_token_multipliers[competitor.name]} for {competitor.name}, adjusted prompt tokens: {prompt_tokens}")
                
                if competitor.name in self.output_token_multipliers:
                    completion_tokens = int(completion_tokens * self.output_token_multipliers[competitor.name])
                    logger.info(f"Applied output token multiplier {self.output_token_multipliers[competitor.name]} for {competitor.name}, adjusted completion tokens: {completion_tokens}")
                
                competitor.remaining_tokens -= (prompt_tokens + completion_tokens)
                if competitor.remaining_tokens < 0:
                    competitor.remaining_tokens = 0
                
                # Stop if out of tokens
                if competitor.remaining_tokens <= 0:
                    competitor.terminate("out_of_tokens")
                    logger.info(f"{competitor.name} ran out of tokens")
                    break
                
                # Process action and update state
                action_result = self._process_action(action, competitor)
                
                # Update rankings
                rankings_result = self._view_rankings()
                if "error" not in rankings_result:
                    state["rankings"] = rankings_result.get("rankings", [])
                
                competitor.final_score = competitor.score + competitor.remaining_tokens / competitor.token_limit * self.competition_data.get("rules", {}).get("lambda", 100)
                competitor.tokens_score.append((competitor.token_limit - competitor.remaining_tokens, competitor.final_score))
                
                # Update state for next iteration
                state["competitor_state"] = competitor.get_competition_state()
                state["last_action_result"] = action_result["action_result"]
                state["other_competitors_status"] = [
                    {
                        "name": c.name,
                        "is_terminated": not c.is_running,
                        "termination_reason": c.termination_reason
                    }
                    for c in self.competitors if c.name != competitor.name
                ]
                
                logger.info(f"{competitor.name} finish Action: {action['action']}, Tokens remaining: {competitor.remaining_tokens}, Score: {competitor.final_score}")

                
                
                # Check if should terminate
                if action_result["should_terminate"]:
                    competitor.terminate(action_result["termination_reason"])
                    break
                
            except Exception as e:
                logger.error(f"Error in competition loop for {competitor.name}: {e}")
                competitor.terminate("error")
                break
        
        # Return final results
        competitor.final_score = competitor.score + competitor.remaining_tokens / competitor.token_limit * self.competition_data.get("rules", {}).get("lambda", 100)
        competitor.tokens_score.append((competitor.token_limit - competitor.remaining_tokens, competitor.final_score))
        
        # Save results to file
        results = {
            "final_score": competitor.final_score,
            "termination_reason": competitor.termination_reason,
            "hint_tokens": competitor.hint_tokens,
            "remaining_tokens": competitor.remaining_tokens,
            "participant_id": competitor.participant_id,
            "solved_problems": competitor.solved_problems,
            "submission_trial": competitor.submission_trial,
            "tokens_score": competitor.tokens_score
        }
        
        # Create results directory if it doesn't exist
        os.makedirs("competitor_results", exist_ok=True)
        
        # Save results with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"competitor_results/{competitor.name}_{timestamp}.json"
        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved competition results for {competitor.name} to {result_file}")
        except Exception as e:
            logger.error(f"Failed to save competition results for {competitor.name}: {e}")
        
        return results

    async def run_llm_competition(self) -> Dict:
        """
        Run the competition in parallel for all competitors
        
        Returns:
            Dictionary containing competition results
        """
        if not self.competition_id or not self.competition_data:
            raise ValueError("Competition not created")
        
        # Run all competitors in parallel
        competitor_tasks = [
            self._run_competitor(competitor)
            for competitor in self.competitors
        ]
        logger.info(f"Competitors: {self.competitors}")
        logger.info(f"Running {len(competitor_tasks)} competitors")
        # Wait for all competitors to complete
        results_list = await asyncio.gather(*competitor_tasks)
        
        # Combine results
        results = {
            competitor.name: result
            for competitor, result in zip(self.competitors, results_list)
        }
        
        return results
    
    def _process_action(self, action: Dict, competitor: Competitor) -> Dict:
        """
        Process an action and return the result
        
        Args:
            action: Action to process
            competitor: The competitor taking the action
        
        Returns:
            Dictionary containing:
            - action_result: Result of the specific action
            - competitor_state: Current state of the competitor
            - should_terminate: Whether the competitor should terminate
            - termination_reason: Reason for termination if should_terminate is True
        """
        action_type = action["action"]
        params = action.get("parameters", {})
        
        # Process the specific action
        if action_type == "VIEW_PROBLEMS":
            data = self._view_problems(competitor)
        elif action_type == "VIEW_PROBLEM":
            data = self._view_problem(params.get("problem_id"))
        elif action_type == "GET_HINT":
            data = self._get_hint(
                params.get("problem_id"),
                params.get("hint_level", 1),
                competitor
            )
        elif action_type == "SUBMIT_SOLUTION":
            data = self._submit_solution(
                params.get("problem_id"),
                params.get("solution"),
                params.get("language", "cpp"),
                competitor
            )
        elif action_type == "VIEW_RANKINGS":
            data = self._view_rankings()
        elif action_type == "TERMINATE":
            data = {"status": "success", "message": "Competitor terminated"}
        else:
            data = {
                "error": f"Unknown action: {action_type}"
            }
        
        # Check if all problems are solved
        all_problems_solved = all(
            problem_id in competitor.solved_problems 
            for problem_id in self.competition_data["problem_ids"]
        )
        
        # Determine if competitor should terminate
        should_terminate = False
        termination_reason = None

        if all_problems_solved:
            should_terminate = True
            termination_reason = "all_problems_solved"
        elif action_type == "TERMINATE":
            should_terminate = True
            termination_reason = "competitor_terminated"
        
        # Return unified response format
        action_result = {}
        if "error" not in data:
            action_result["status"] = "success"
            action_result["data"] = data
        else:
            action_result["status"] = "error"
            action_result["message"] = data["error"]

        return {
            "action_result": action_result,
            "competitor_state": competitor.get_competition_state(),
            "should_terminate": should_terminate,
            "termination_reason": termination_reason
        }

    def _view_problems(self, competitor: Competitor) -> Dict:
        """Handle VIEW_PROBLEMS action"""
        try:
            response = requests.get(
                f"{self.api_base_url}/api/competitions/{self.competition_id}/problems"
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {
                    "error": f"API error: {result.get('message', 'Unknown error')}"
                }
            
            return {
                "problems": result["data"]
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Failed to fetch problems: {str(e)}"
            }

    def _view_problem(self, problem_id: str) -> Dict:
        """Handle VIEW_PROBLEM action"""
        if problem_id not in self.competition_data["problem_ids"]:
            return {
                "error": f"Problem {problem_id} not found"
            }
        
        try:
            response = requests.get(
                f"{self.api_base_url}/api/competitions/{self.competition_id}/problems/{problem_id}"
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {
                    "error": f"API error: {result.get('message', 'Unknown error')}"
                }
            
            return {
                "problem": result["data"]
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Failed to fetch problem: {str(e)}"
            }

    def _get_hint(self, problem_id: str, hint_level: int, competitor: Competitor) -> Dict:
        """Handle GET_HINT action
        
        Args:
            problem_id: ID of the problem to get hint for
            hint_level: Level of hint (1-3)
                1: Basic approach and key concepts from similar problems
                2: Detailed solution strategy with textbook knowledge
                3: Combined episodic and semantic knowledge
            competitor: The competitor requesting the hint
        
        Returns:
            Dictionary containing hint information
        """
        if problem_id not in self.competition_data["problem_ids"]:
            return {
                "error": f"Problem {problem_id} not found"
            }
        
        # Get hint token costs from rules
        hint_tokens = self.competition_data.get("rules", {}).get("hint_tokens", {})
        
        # Validate hint level
        if hint_level < 1 or hint_level > 3:
            return {
                "error": "Invalid hint level. Must be between 1 and 3"
            }
        
        # Get token cost for the requested level
        token_cost = hint_tokens.get(f"level_{hint_level}", 100 * hint_level)  # fallback to old calculation if not configured
        
        if competitor.remaining_tokens < token_cost:
            return {
                "error": f"Not enough tokens. Required: {token_cost}, Available: {competitor.remaining_tokens}"
            }
        
        try:
            # Get problem details
            response = requests.get(
                f"{self.api_base_url}/api/competitions/{self.competition_id}/problems/{problem_id}"
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {
                    "error": f"API error: {result.get('message', 'Unknown error')}"
                }
            
            problem_data = result["data"]
            
            # Generate hint based on level using retrieval
            hint_data = {}
            if hint_level == 1:
                hint_data = self._generate_semantic_hint(problem_data)
            elif hint_level == 2:
                hint_data = self._generate_episodic_hint(problem_data, num_problems=2)
            else:
                hint_data = self._generate_combined_hint(problem_data, num_problems=3)
            
            # Deduct tokens
            competitor.remaining_tokens -= token_cost
            competitor.hint_tokens += token_cost
            
            # Return structured hint data
            return {
                "hint": {
                    "problem_id": problem_id,
                    "hint_level": hint_level,
                    "hint_data": hint_data,
                    "tokens_cost": token_cost,
                    "remaining_tokens": competitor.remaining_tokens
                }
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Failed to get hint: {str(e)}"
            }
    
    def _generate_episodic_hint(self, problem_data: Dict, num_problems: int = 2) -> Dict:
        """Generate hint based on similar problems"""
        try:
            # Get similar problems
            response = requests.get(
                f"{self.api_base_url}/api/problems/similar",
                params={
                    "problem_id": problem_data["id"],
                    "num_problems": num_problems,
                    "competition_id": self.competition_id
                }
            )
            response.raise_for_status()
            
            similar_problems = response.json()["data"]
            
            return {
                "type": "episodic",
                "current_problem": {
                    "id": problem_data["id"],
                    "title": problem_data["title"]
                },
                "similar_problems": [
                    {
                        "id": similar["id"],
                        "title": similar["title"],
                        "description": similar["description"],
                        "solution": similar["solution"],
                        "similarity_score": similar["similarity_score"]
                    }
                    for similar in similar_problems
                ]
            }
            
        except Exception as e:
            return {
                "error": f"Error retrieving similar problems: {str(e)}"
            }
    
    def _generate_semantic_hint(self, problem_data: Dict) -> Dict:
        """Generate hint based on textbook knowledge"""
        try:
            # Get relevant textbook content
            response = requests.get(
                f"{self.api_base_url}/api/textbook/search",
                params={
                    "query": problem_data["title"] + " " + problem_data.get("description", ""),
                    "max_results": 2
                }
            )
            response.raise_for_status()
            
            textbook_content = response.json()["data"]
            
            return {
                "type": "semantic",
                "current_problem": {
                    "id": problem_data["id"],
                    "title": problem_data["title"]
                },
                "textbook_sections": [
                    {
                        "title": content["title"],
                        "content": content["content"],
                        "relevance_score": content["relevance_score"]
                    }
                    for content in textbook_content
                ]
            }
            
        except Exception as e:
            return {
                "error": f"Error retrieving textbook content: {str(e)}"
            }
    
    def _generate_combined_hint(self, problem_data: Dict, num_problems: int = 3) -> Dict:
        """Generate hint combining episodic and semantic knowledge"""
        episodic_hint = self._generate_episodic_hint(problem_data, num_problems)
        semantic_hint = self._generate_semantic_hint(problem_data)
        
        return {
            "type": "combined",
            "current_problem": {
                "id": problem_data["id"],
                "title": problem_data["title"]
            },
            "episodic_data": episodic_hint,
            "semantic_data": semantic_hint,
            "integration_points": [
                "Common patterns in similar problems",
                "Theoretical concepts that apply to these patterns",
                "How to adapt these concepts to the current problem"
            ]
        }

    def _submit_solution(self, problem_id: str, solution: str, language: str, competitor: Competitor) -> Dict:
        """Handle SUBMIT_SOLUTION action"""
        if problem_id not in self.competition_data["problem_ids"]:
            return {
                "error": f"Problem {problem_id} not found"
            }
        
        if problem_id in competitor.solved_problems:
            return {
                "error": f"Problem {problem_id} already solved"
            }
        
        try:
            # Submit the solution
            response = requests.post(
                f"{self.api_base_url}/api/competitions/{self.competition_id}/submit",
                json={
                    "participant_id": competitor.participant_id,
                    "problem_id": problem_id,
                    "code": solution,
                    "language": language
                }
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {
                    "error": f"API error: {result.get('message', 'Unknown error')}"
                }
            
            # Get submission result directly
            submission_data = result["data"]
            
            # Update solved problems list if submission is accepted
            if submission_data["status"] == SubmissionStatus.ACCEPTED:
                if problem_id not in competitor.solved_problems:
                    competitor.solved_problems.append(problem_id)
            
            # Get submission token cost from rules
            submission_tokens = self.competition_data.get("rules", {}).get("submission_tokens", {})
            token_cost = submission_tokens.get(submission_data["status"], 100)
            
            # Deduct tokens
            competitor.remaining_tokens -= token_cost
            if competitor.remaining_tokens < 0:
                competitor.remaining_tokens = 0

            if problem_id not in competitor.submission_trial:
                competitor.submission_trial[problem_id] = []
            competitor.submission_trial[problem_id].append((submission_data["status"], submission_data["score"], submission_data["penalty"]))

            # Update competitor score
            competitor.score = submission_data["participant_score"]
            logger.info(f"Competitor {competitor.name} passed {submission_data['passed_tests']}/{submission_data['total_tests']} tests, scored {submission_data['score']} points with penalty {submission_data['penalty']} for problem {problem_id}")
            
            return {
                "submission": submission_data,
                "participant_score": competitor.score
            }
            
            # Original polling implementation (commented out)
            """
            # Get initial submission status
            submission_data = result["data"]
            
            # Start polling submission status
            max_retries = 300
            retry_interval = 5  # Check every 5 seconds
            
            for _ in range(max_retries):
                # Get latest status
                status_response = requests.get(f"{self.api_base_url}{submission_data['poll_url']}")
                status_response.raise_for_status()
                status_result = status_response.json()
                
                if status_result["status"] != "success":
                    return {
                        "error": f"Failed to get submission status: {status_result.get('message', 'Unknown error')}"
                    }
                
                current_status = status_result["data"]
                
                # Return result if submission is completed or has an error
                if current_status["status"] != SubmissionStatus.PENDING:
                    # Update solved problems list if submission is accepted
                    if current_status["status"] == SubmissionStatus.ACCEPTED:
                        if problem_id not in competitor.solved_problems:
                            competitor.solved_problems.append(problem_id)
                    
                    # Get current participant score
                    participant_response = requests.get(
                        f"{self.api_base_url}/api/competitions/{self.competition_id}/participants/{competitor.participant_id}"
                    )
                    participant_response.raise_for_status()
                    participant_data = participant_response.json()
                    competitor.score = participant_data["data"]["score"]
                    
                    return {
                        "submission": current_status,
                        "participant_score": competitor.score
                    }
                
                # Wait before next check
                time.sleep(retry_interval)
            
            # Return current status if timeout
            return {
                "submission": current_status,
                "message": "Submission is still being processed"
            }
            """
            
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Failed to submit solution: {str(e)}"
            }

    def _view_rankings(self) -> Dict:
        """Handle VIEW_RANKINGS action"""
        try:
            response = requests.get(
                f"{self.api_base_url}/api/competitions/{self.competition_id}/rankings"
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {
                    "error": f"API error: {result.get('message', 'Unknown error')}"
                }
            
            return {
                "rankings": result["data"]
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Failed to fetch rankings: {str(e)}"
            }

