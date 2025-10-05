import json
import time
import requests
import asyncio
import os
from typing import Dict, List, Optional
from datetime import datetime
from scripts.competitors import Competitor
from usacoarena.utils.logger_config import get_logger

logger = get_logger("competition_organizer")


class CompetitionOrganizer:
    """Organizer for LLM programming competition"""
    
    def __init__(self, api_base: str, log_dir: Optional[str] = None):
        """
        Initialize the competition organizer
        
        Args:
            api_base: Base URL for the competition API
            log_dir: Directory for saving competitor results (optional)
        """
        self.api_base = api_base
        self.log_dir = log_dir
        self.competitors: List[Competitor] = []
        self.competition_id: Optional[str] = None
        self.competition_data: Optional[Dict] = None
        logger.info(f"Initialized CompetitionOrganizer with API base: {api_base}, log_dir: {log_dir}")
    
    @property
    def problem_ids(self) -> List[str]:
        """Dynamically get problem IDs from competition data"""
        if not self.competition_data:
            return []
        
        problems = self.competition_data.get("problems", [])
        return [
            str(p.get("id")) for p in problems 
            if isinstance(p, dict) and p.get("id") is not None
        ]
    
    def add_competitor(self, competitor: Competitor) -> None:
        """Add a competitor to the competition"""
        self.competitors.append(competitor)
        logger.info(f"Added competitor: {competitor.name}")
    
    def create_competition(
        self,
        title: str,
        description: str,
        problem_ids: List[str],
        max_tokens_per_participant: int = 100000,
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
            
            # Make API request - use the correct endpoint
            response = requests.post(
                f"{self.api_base}/api/competitions/create",
                json=data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            # Parse response
            result = response.json()
            if not isinstance(result, dict):
                logger.error("Invalid API response: not a JSON object")
                return None
                
            if result.get("status") != "success":
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"API error: {error_msg}")
                return None
            
            # Store competition data
            result_data = result.get("data", {})
            if not result_data or not result_data.get("competition"):
                logger.error("Invalid API response: missing competition data")
                return None
                
            competition_data = result_data["competition"]
            if not isinstance(competition_data, dict):
                logger.error("Invalid API response: competition data is not a JSON object")
                return None
                
            self.competition_id = competition_data.get("id")
            if not self.competition_id:
                logger.error("Invalid API response: missing competition ID")
                return None
                
            self.competition_data = competition_data
            
            # Note: problem_ids are now available via the property, no need to store separately
            
            # Log any problems that were not found
            not_found_problems = result_data.get("not_found_problems", [])
            if not_found_problems:
                logger.warning(f"Some problems not found: {not_found_problems}")
            
            logger.info(f"Successfully created competition: {self.competition_id}")
            return self.competition_id
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create competition: {e}", exc_info=True)
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
            if not self.competition_id and not self.competition_data:
                # Get competition details
                response = requests.get(
                    f"{self.api_base}/api/competitions/get/{competition_id}",
                    params={"include_details": "true"}
                )
                response.raise_for_status()
                
                result = response.json()
                if not isinstance(result, dict):
                    logger.error("Invalid API response: not a JSON object")
                    return False
                    
                if result.get("status") != "success":
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"API error: {error_msg}")
                    return False
                
                # Store competition data
                competition_data = result.get("data")
                if not isinstance(competition_data, dict):
                    logger.error("Invalid API response: missing or invalid competition data")
                    return False
                    
                self.competition_id = competition_id
                self.competition_data = competition_data
            
            # Note: problem_ids are now dynamically available via property
            # No need to extract and store separately
                
            # Get lambda value from rules
            rules = self.competition_data.get("rules", {}) if self.competition_data else {}
            lambda_ = rules.get("lambda", 100) if isinstance(rules, dict) else 100

            # Register each participant
            for competitor in self.competitors:
                participant_id = competitor.join_competition(self.api_base, competition_id, lambda_)
                
                # Immediately verify if the participant can be found after creation
                time.sleep(1)  # Wait 1 second to ensure data has been properly saved to storage
                
                verification_response = requests.get(
                    f"{self.api_base}/api/participants/get/{competition_id}/{participant_id}",
                    params={"include_submissions": "false"}
                )
                
                if verification_response.status_code == 200:
                    verification_data = verification_response.json()
                    if verification_data.get("status") == "success":
                        logger.info(f"✓ Verification successful: Participant {participant_id} found")
                    else:
                        logger.error(f"✗ Verification failed: {verification_data.get('message', 'Unknown error')}")
                        raise ValueError(f"Participant verification failed for {competitor.name}")
                else:
                    logger.error(f"✗ Verification failed: HTTP {verification_response.status_code}")
                    logger.error(f"Response: {verification_response.text}")
                    raise ValueError(f"Cannot verify participant {participant_id} was created successfully")
            
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to join competition: {e}")
            return False
    
    async def _run_competitor(self, competitor: Competitor) -> Dict:
        """
        Run competition for a single competitor with optimized API usage
        
        Args:
            competitor: The competitor to run
        
        Returns:
            Dictionary containing competitor results
        """
        logger.info(f"Starting competition for competitor: {competitor.name}")
        

        problems_result = competitor.view_problems()
        problems = problems_result.get("problems", []) if "error" not in problems_result else []
        logger.debug(f"Loaded {len(problems)} problems for competitor {competitor.name}")
        
        problems_state = {
            "problems_id": [p.get("id") for p in problems],
            "problems_first_to_solve": [p.get("first_to_solve") for p in problems],
        }
        # Initialize competitors state
        for c in self.competitors:
            logger.debug(f"Initialized competitor: {c.name}")
        
        # Build initial state
        state = {
            "api_base": self.api_base,
            "competition_details": self.competition_data,
            "competitor_state": competitor.get_participant_state(),
            "problems": problems_state,
            "rankings": self.get_enhanced_rankings(),
            "other_competitors_status": [
                {
                    "name": c.name,
                    "is_terminated": not c.is_running,
                    "termination_reason": c.termination_reason
                }
                for c in self.competitors if c.name != competitor.name
            ]
        }
        logger.debug(f"Initial state for {competitor.name}: running={competitor.is_running},state={state}")
        
        # Run competition loop
        while competitor.is_running:
            try:
                # Get next action from competitor
                logger.info(f"Begin call LLM for next action for competitor {competitor.name}")
                action = await competitor.agent.process(state)

                # Add safety check for participant state
                participant_state = competitor.get_participant_state()
                if participant_state:
                    logger.warning(f"\nAfter LLM call:\
                        \n Name:{participant_state.get('name', 'unknown')}\
                        \n LLM_tokens:{participant_state.get('LLM_tokens', 0)}\
                        \n llm_inference_count:{participant_state.get('llm_inference_count', 0)}\
                        \n hint_tokens:{participant_state.get('hint_tokens', 0)}\
                        \n submission_tokens:{participant_state.get('submission_tokens', 0)}\
                        \n remaining_tokens:{participant_state.get('remaining_tokens', 0)}\
                        \n submission_count:{participant_state.get('submission_count', 0)}\
                        \n accepted_count:{participant_state.get('accepted_count', 0)}\
                        \n submission_penalty:{participant_state.get('submission_penalty', 0)}\
                        \n problem_pass_score:{participant_state.get('problem_pass_score', 0)}\
                        \n score:{participant_state.get('score', 0)}\
                        \n is_running:{participant_state.get('is_running', True)}\
                        \n termination_reason:{participant_state.get('termination_reason', 'unknown')}")
                else:
                    logger.warning(f"After LLM call: Failed to get participant state for {competitor.name}")

                logger.info(f"Competitor {competitor.name} choose the next action: {action['action']}, remaining_tokens: {competitor.remaining_tokens}, score: {competitor.score}")

                # Process action (this will trigger sync_from_api if needed)
                action_result = self._process_action(action, competitor)

                action_result_str = str(action_result)
                if len(action_result_str) > 5000:
                    action_result_str = action_result_str[:5000] + "... (truncated)"
                logger.warning(f"Agent:{competitor.name}, Action: {action['action']}, Action_result: {action_result_str}")

                # Add safety check for participant state after action
                participant_state_after = competitor.get_participant_state()
                if participant_state_after:
                    logger.warning(f"\nAfter action_result:\
                        \n Name:{participant_state_after.get('name', 'unknown')}\
                        \n LLM_tokens:{participant_state_after.get('LLM_tokens', 0)}\
                        \n llm_inference_count:{participant_state_after.get('llm_inference_count', 0)}\
                        \n hint_tokens:{participant_state_after.get('hint_tokens', 0)}\
                        \n submission_tokens:{participant_state_after.get('submission_tokens', 0)}\
                        \n remaining_tokens:{participant_state_after.get('remaining_tokens', 0)}\
                        \n submission_count:{participant_state_after.get('submission_count', 0)}\
                        \n accepted_count:{participant_state_after.get('accepted_count', 0)}\
                        \n submission_penalty:{participant_state_after.get('submission_penalty', 0)}\
                        \n problem_pass_score:{participant_state_after.get('problem_pass_score', 0)}\
                        \n score:{participant_state_after.get('score', 0)}\
                        \n is_running:{participant_state_after.get('is_running', True)}\
                        \n termination_reason:{participant_state_after.get('termination_reason', 'unknown')}")
                else:
                    logger.warning(f"After action_result: Failed to get participant state for {competitor.name}")


                # Update rankings (only when needed)
                rankings_result = self.get_enhanced_rankings()
                logger.debug(f"Rankings result: {rankings_result}")

                # Format rankings for better readability
                if "rankings" in rankings_result and isinstance(rankings_result["rankings"], list):
                    formatted_rankings = "{\n  'rankings': [\n"
                    for i, ranking in enumerate(rankings_result["rankings"]):
                        formatted_rankings += f"    {ranking}"
                        if i < len(rankings_result["rankings"]) - 1:
                            formatted_rankings += ","
                        formatted_rankings += "\n"
                    formatted_rankings += "  ]\n}"
                    logger.critical(f"Time: {datetime.now().strftime('%m-%d %H:%M:%S')}, rankings_result: {formatted_rankings}")
                else:
                    logger.critical(f"Time: {datetime.now().strftime('%m-%d %H:%M:%S')}, rankings_result: {rankings_result}")

                if "error" not in rankings_result:
                    state["rankings"] = rankings_result.get("rankings", [])
                    logger.debug(f"State rankings result: {state['rankings']}")

                # Update state for next iteration (competitor state is automatically fresh after action)
                state["competitor_state"] = competitor.get_participant_state()
                state["last_action_result"] = action_result

                problems_result = competitor.view_problems()
                problems = problems_result.get("problems", []) if "error" not in problems_result else []

                problems_state = {
                    "problems_id": [p.get("id") for p in problems],
                    "problems_first_to_solve": [p.get("first_to_solve") for p in problems],
                }

                state["problems"] = problems_state
                # Update other competitors status (minimal sync)
                state["other_competitors_status"] = [
                    {
                        "name": c.name,
                        "is_terminated": not c.is_running,
                        "termination_reason": c.termination_reason
                    }
                    for c in self.competitors if c.name != competitor.name
                ]

                logger.info(f"Competitor {competitor.name} completed the action: {action['action']}, remaining_tokens: {competitor.remaining_tokens}, score: {competitor.score}")

                # Check if participant has solved all problems
                participant_state_current = competitor.get_participant_state()
                if participant_state_current:
                    solved_problems_data = participant_state_current.get('solved_problems', [])

                    # Handle both list of dicts and list of strings format
                    if solved_problems_data and isinstance(solved_problems_data[0], dict):
                        # List of dicts format: extract problem_id from each dict
                        solved_problems = set(str(p.get("problem_id", "")) for p in solved_problems_data if p.get("problem_id"))
                    else:
                        # List of strings format
                        solved_problems = set(str(p) for p in solved_problems_data if p)

                    all_problems = set(str(p) for p in problems_state.get("problems_id", []) if p)

                    if solved_problems and all_problems and solved_problems >= all_problems:
                        logger.info(f"Competitor {competitor.name} has solved all problems ({len(solved_problems)}/{len(all_problems)})! Terminating with 'all_problems_solved'")
                        competitor.terminate("all_problems_solved")
                        break


            except Exception as e:
                logger.error(f"Error in competition loop for {competitor.name}: {e}", exc_info=True)
                error_reason = "error"
                competitor.terminate(error_reason)

                # Check if error propagation is enabled
                if self._is_error_propagation_enabled():
                    logger.warning(f"Error propagation enabled - terminating all other participants due to {competitor.name}'s error")
                    self._propagate_error_termination(competitor.name, error_reason)

                break
        
        logger.info(f"Competitor {competitor.name} terminated: {competitor.termination_reason}")
        # Get final state (force sync for accurate final results)
        logger.info(f"Competition ended for {competitor.name}, getting final state")
        
        # Get final state from competitor
        final_state = competitor.get_participant_state()
        logger.info(f"Final state for {competitor.name}: {final_state}")
        logger.debug(f"problem_stats: {final_state.get('problem_stats', {})}")
        
        # Save results to file
        results = {
            "participant_id": final_state.get("id", "unknown"),
            "competition_id": final_state.get("competition_id", "unknown"),
            "name": final_state.get("name", "unknown"),
            "LLM_tokens": final_state.get("LLM_tokens", 0),
            "hint_tokens": final_state.get("hint_tokens", 0),
            "submission_tokens": final_state.get("submission_tokens", 0),
            "limit_tokens": final_state.get("limit_tokens", 0),
            "remaining_tokens": final_state.get("remaining_tokens", 0),
            "consumed_tokens": final_state.get("consumed_tokens", 0),
            "consumed_credit": final_state.get("consumed_tokens", 0) + final_state.get("submission_penalty", 0),
            "submission_count": final_state.get("submission_count", 0),
            "accepted_count": final_state.get("accepted_count", 0),
            "submission_penalty": final_state.get("submission_penalty", 0),
            "problem_pass_score": final_state.get("problem_pass_score", 0),
            "score": final_state.get("score", 0),
            "is_running": final_state.get("is_running", False),
            "termination_reason": final_state.get("termination_reason", "unknown"),
            "solved_problems": final_state.get("solved_problems", []),

            "llm_inference_count": final_state.get("llm_inference_count", 0),
            "first_ac_score": final_state.get("first_ac_score", 0),
            "problem_score": final_state.get("problem_score", 0),
            "bronze_score": final_state.get("bronze_score", 0),
            "silver_score": final_state.get("silver_score", 0),
            "gold_score": final_state.get("gold_score", 0),
            "platinum_score": final_state.get("platinum_score", 0),
            "bonus_score": final_state.get("bonus_score", 0),
            "problem_stats": final_state.get("problem_stats", {}),
            "rules": self.competition_data.get("rules", {}),
        }
        
        # Create results directory if it doesn't exist
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.log_dir:
            # Use the passed log_dir, save results in agent subdirectory
            agent_result_dir = os.path.join(self.log_dir, competitor.name)
            os.makedirs(agent_result_dir, exist_ok=True)
            result_file = os.path.join(agent_result_dir, f"{final_state['name']}_results_{timestamp}.json")
        else:
            # Use default competitor_results directory
            os.makedirs("competitor_results", exist_ok=True)
            result_file = f"competitor_results/{competitor.name}_{timestamp}.json"
        
        try:
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved competition results for {competitor.name} to {result_file}")
        except Exception as e:
            logger.error(f"Failed to save competition results for {competitor.name}: {e}", exc_info=True)
        
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
        logger.info(f"Running {len(competitor_tasks)} competitors")
        
        # Wait for all competitors to complete
        results_list = await asyncio.gather(*competitor_tasks)
        
        # Combine results
        results = {
            competitor.name: result
            for competitor, result in zip(self.competitors, results_list)
        }
        
        return results

    def _is_error_propagation_enabled(self) -> bool:
        """Check if error propagation is enabled in competition rules"""
        if not self.competition_data:
            return False

        rules = self.competition_data.get("rules", {})
        error_propagation = rules.get("error_propagation", {})
        return error_propagation.get("enabled", False)

    def _propagate_error_termination(self, error_competitor_name: str, error_reason: str) -> None:
        """Terminate all other competitors due to an error from one competitor"""
        propagation_reason = f"terminated_due_to_{error_competitor_name}_error"

        for competitor in self.competitors:
            if competitor.name != error_competitor_name and competitor.is_running:
                try:
                    logger.info(f"Propagating error termination: terminating {competitor.name} due to {error_competitor_name}'s error")
                    competitor.terminate(propagation_reason)
                except Exception as e:
                    logger.error(f"Failed to propagate error termination to {competitor.name}: {e}", exc_info=True)

    def get_enhanced_rankings(self) -> Dict:
        """Get competition rankings with competitor termination status"""
        if not self.competition_id:
            return {"error": "Competition not initialized"}

        try:
            # Get base rankings from API
            response = requests.get(f"{self.api_base}/api/rankings/get/{self.competition_id}")
            response.raise_for_status()

            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}

            rankings_data = result["data"]

            # Create a mapping of competitor names to termination status
            competitor_status_map = {}
            for competitor in self.competitors:
                competitor_status_map[competitor.name] = {
                    "is_terminated": not competitor.is_running,
                    "termination_reason": competitor.termination_reason
                }

            # Enhance rankings with termination status
            enhanced_rankings = []
            for ranking_item in rankings_data:
                if isinstance(ranking_item, list) and len(ranking_item) >= 4:
                    participant_name = ranking_item[0]
                    score = ranking_item[1]
                    tokens = ranking_item[2]
                    rank = ranking_item[3]

                    # Get termination status from our competitors
                    status_info = competitor_status_map.get(participant_name, {
                        "is_terminated": False,  # Default for unknown competitors
                        "termination_reason": None
                    })

                    # Add termination status as the 5th element
                    enhanced_item = [
                        participant_name,
                        score,
                        tokens,
                        rank,
                        status_info["is_terminated"]
                    ]
                    enhanced_rankings.append(enhanced_item)
                else:
                    # If format is unexpected, keep original item
                    enhanced_rankings.append(ranking_item)

            return {"rankings": enhanced_rankings}

        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch rankings: {str(e)}"}

    def _process_action(self, action: Dict, competitor: Competitor) -> Dict:
        """
        Process an action from a competitor
        
        Args:
            action: Action dictionary from the agent
            competitor: The competitor performing the action
        
        Returns:
            Dictionary containing action result and termination info
        """
        action_type = action.get("action")
        if action_type is None:
            return {
                "status": "error",
                "data": {
                    "action": "unknown",
                    "action_result": {"error": "Missing action"},
                },
                "should_terminate": False,
                "termination_reason": None
            }
        action_type = action_type.lower()
        
        try:
            if action_type == "view_problems":
                result = competitor.view_problems()
                return {
                    "status": "success",
                    "data": {
                        "action": "view_problems",
                        "action_result": result,
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "view_problem":
                problem_id = action.get("parameters", {}).get("problem_id")
                if not problem_id:
                    return {
                        "status": "error",
                        "data": {
                            "action": "view_problem",
                            "action_result": {"error": "Missing problem_id"},
                        },
                        "should_terminate": False,
                        "termination_reason": None
                    }
                
                result = competitor.view_problem(problem_id)
                return {
                    "status": "success",
                    "data": {
                        "action": "view_problem",
                        "action_result": result,
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "get_hint":
                hint_level = action.get("parameters", {}).get("hint_level", 1)
                problem_id = action.get("parameters", {}).get("problem_id")
                hint_knowledge = action.get("parameters", {}).get("hint_knowledge", None)
                problem_difficulty = action.get("parameters", {}).get("problem_difficulty", None)
                
                # Validate parameters based on hint level
                if hint_level == 0:
                    # Strategy hint - no additional parameters required
                    pass
                elif hint_level == 1:
                    # Problem relevant textbook hint - requires problem_id
                    if not problem_id:
                        return {
                            "status": "error",
                            "data": {
                                "action": "get_hint",
                                "action_result": {"error": "Missing problem_id for hint level 1"},
                            },
                            "should_terminate": False,
                            "termination_reason": None
                        }
                elif hint_level == 2:
                    # Knowledge point relevant textbook hint - requires hint_knowledge
                    if not hint_knowledge:
                        return {
                            "status": "error",
                            "data": {
                                "action": "get_hint",
                                "action_result": {"error": "Missing hint_knowledge for hint level 2"},
                            },
                            "should_terminate": False,
                            "termination_reason": None
                        }
                elif hint_level == 3:
                    # Similar problem hint - requires problem_id
                    if not problem_id:
                        return {
                            "status": "error",
                            "data": {
                                "action": "get_hint",
                                "action_result": {"error": "Missing problem_id for hint level 3"},
                            },
                            "should_terminate": False,
                            "termination_reason": None
                        }
                elif hint_level == 4:
                    # Knowledge point example problem hint - requires problem_difficulty and hint_knowledge
                    if not problem_difficulty or not hint_knowledge:
                        return {
                            "status": "error",
                            "data": {
                                "action": "get_hint",
                                "action_result": {"error": "Missing problem_difficulty or hint_knowledge for hint level 4"},
                            },
                            "should_terminate": False,
                            "termination_reason": None
                        }
                elif hint_level == 5:
                    # Comprehensive hint - requires problem_id
                    if not problem_id:
                        return {
                            "status": "error",
                            "data": {
                                "action": "get_hint",
                                "action_result": {"error": "Missing problem_id for hint level 5"},
                            },
                            "should_terminate": False,
                            "termination_reason": None
                        }
                else:
                    return {
                        "status": "error",
                        "data": {
                            "action": "get_hint",
                            "action_result": {"error": f"Invalid hint level: {hint_level}. Must be 0-5"},
                        },
                        "should_terminate": False,
                        "termination_reason": None
                    }
                result = competitor.get_hint(problem_id, hint_level, hint_knowledge, problem_difficulty)
                return {
                    "status": "success",
                    "data": {
                        "action": "get_hint",
                        "action_result": result,
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }
                
            
            elif action_type == "submit_solution":
                problem_id = action.get("parameters", {}).get("problem_id")
                code = action.get("parameters", {}).get("solution")
                language = action.get("parameters", {}).get("language", "cpp")
                
                if not problem_id or not code:
                    return {
                        "status": "error",
                        "data": {
                            "action": "submit_solution",
                            "action_result": {"error": "Missing problem_id or code"},
                        },
                        "should_terminate": False,
                        "termination_reason": None
                    }
                
                result = competitor.submit_solution(problem_id, code, language)
                return {
                    "status": "success",
                    "data": {
                        "action": "submit_solution",
                        "action_result": result,
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "view_rankings":
                result = self.get_enhanced_rankings()
                return {
                    "status": "success",
                    "data": {
                        "action": "view_rankings",
                        "action_result": result,
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }

            elif action_type == "test_code":
                code = action.get("parameters", {}).get("code")
                language = action.get("parameters", {}).get("language", "cpp")
                test_cases = action.get("parameters", {}).get("test_cases", [])
                time_limit_ms = action.get("parameters", {}).get("time_limit_ms", 5000)
                memory_limit_mb = action.get("parameters", {}).get("memory_limit_mb", 256)

                if not code or not test_cases:
                    return {
                        "status": "error",
                        "data": {
                            "action": "test_code",
                            "action_result": {"error": "Missing code or test_cases"},
                        },
                        "should_terminate": False,
                        "termination_reason": None
                    }

                if not isinstance(test_cases, list) or len(test_cases) == 0:
                    return {
                        "status": "error",
                        "data": {
                            "action": "test_code",
                            "action_result": {"error": "test_cases must be a non-empty list"},
                        },
                        "should_terminate": False,
                        "termination_reason": None
                    }

                result = competitor.test_code(code, language, test_cases, time_limit_ms, memory_limit_mb)
                return {
                    "status": "success",
                    "data": {
                        "action": "test_code",
                        "action_result": result,
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }

            elif action_type == "terminate":
                reason = action.get("parameters", {}).get("reason", "manual_termination")
                competitor.terminate(reason)
                return {
                    "action": "terminate",
                    "data": {
                        "action": "terminate",
                        "action_result": {"message": f"Competitor terminated: {reason}"},
                    },
                    "should_terminate": True,
                    "termination_reason": reason
                }
            
            else:
                return {
                    "status": "error",
                    "data": {
                        "action": "unknown",
                        "action_result": {"error": f"Unknown action: {action_type}, message: {action.get('message', {})}"},
                    },
                    "should_terminate": False,
                    "termination_reason": None
                }
                
        except Exception as e:
            logger.error(f"Error processing action {action_type} for {competitor.name}: {e}")
            error_reason = "action_error"
            competitor.terminate(error_reason)

            # Check if error propagation is enabled
            if self._is_error_propagation_enabled():
                logger.warning(f"Error propagation enabled - terminating all other participants due to {competitor.name}'s action error")
                self._propagate_error_termination(competitor.name, error_reason)

            return {
                "status": "error",
                "data": {
                    "action": "unknown",
                    "action_result": {"error": f"Action processing failed: {str(e)}"},
                },
                "should_terminate": True,
                "termination_reason": error_reason
            } 
