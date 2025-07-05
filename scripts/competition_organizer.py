import json
import time
import requests
import logging
import asyncio
import os
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, timedelta

from competemas.engine.agent_interface import AgentInterface
from competemas.models.models import SubmissionStatus
from competemas.engine.competition import Competitor

logger = logging.getLogger("competition")


class CompetitionOrganizer:
    """Organizer for LLM programming competition"""
    
    def __init__(self, api_base: str):
        """
        Initialize the competition organizer
        
        Args:
            api_base: Base URL for the competition API
        """
        self.api_base = api_base
        self.competitors: List[Competitor] = []
        self.competition_id: Optional[str] = None
        self.competition_data: Optional[Dict] = None
    
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
            
            # Make API request
            response = requests.post(
                f"{self.api_base}/api/competitions",
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
            if competition_data and "problems" in competition_data:
                self.competition_data["problem_ids"] = [p["id"] for p in competition_data["problems"]]
            else:
                self.competition_data["problem_ids"] = []
            
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
            # Get competition details
            response = requests.get(
                f"{self.api_base}/api/competitions/get/{competition_id}",
                params={"include_details": "true"}
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                raise ValueError(f"API error: {result.get('message', 'Unknown error')}")
            
            # Store competition data
            self.competition_id = competition_id
            self.competition_data = result["data"]
            if self.competition_data and "problems" in self.competition_data:
                self.competition_data["problem_ids"] = [p["id"] for p in self.competition_data["problems"]]
            else:
                self.competition_data["problem_ids"] = []
            lambda_ = self.competition_data.get("rules", {}).get("lambda", 100) if self.competition_data and self.competition_data.get("rules") else 100

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
        Run competition for a single competitor
        
        Args:
            competitor: The competitor to run
        
        Returns:
            Dictionary containing competitor results
        """
        logger.info(f"Starting competition for {competitor.name}")
        
        # Initialize problems list using competitor API
        problems_result = competitor.view_problems()
        problems = problems_result.get("problems", []) if "error" not in problems_result else []
        
        # print(f"problems: {problems}")  
        # Initialize state using competitor API
        # First sync all competitors to get latest state
        for c in self.competitors:
            c.sync_from_api()
        
        # Build state with cached data to avoid multiple API calls
        state = {
            "competitor_state": competitor.get_competition_state(),
            "other_competitors_status": [
                {
                    "name": c.name,
                    "is_terminated": not c.is_running,  # 现在是API属性
                    "termination_reason": c.termination_reason  # 现在是API属性
                }
                for c in self.competitors if c.name != competitor.name
            ]
        }
        print(f"    competitor.is_running: {competitor.is_running}")
        
        # print(f"state: {state}")
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
                
                # Sync state from API before processing action
                competitor.sync_from_api()
                
                logger.info(f"{competitor.name} choose Action: {action['action']}, Tokens remaining: {competitor.remaining_tokens}, Score: {competitor.final_score}")
                
                # Stop if out of tokens after sync
                if competitor.remaining_tokens <= 0:
                    competitor.terminate("out_of_tokens")
                    logger.info(f"{competitor.name} ran out of tokens")
                    break
                
                # Process action using competitor API
                action_result = self._process_action(action, competitor)
                
                # Update rankings using competitor API
                rankings_result = competitor.view_rankings()
                if "error" not in rankings_result:
                    state["rankings"] = rankings_result.get("rankings", [])
                
                # Sync state after action execution
                competitor.sync_from_api()
                
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
                logger.error(f"Error type: {type(e).__name__}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                competitor.terminate("error")
                break
        
        # Get final state
        logger.info(f"Getting final state for {competitor.name}")
        competitor.sync_from_api()
        
        # Get final state from competitor
        final_state = competitor.get_competition_state()
        
        # Save results to file
        results = {
            "final_score": final_state["final_score"],
            "termination_reason": final_state["termination_reason"],
            "remaining_tokens": final_state["remaining_tokens"],
            "solved_problems": final_state["solved_problems"],
            "score": final_state["score"]
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
        Process an action from a competitor
        
        Args:
            action: Action dictionary from the agent
            competitor: The competitor performing the action
        
        Returns:
            Dictionary containing action result and termination info
        """
        action_type = action.get("action")
        
        try:
            if action_type == "view_problems":
                result = competitor.view_problems()
                return {
                    "action_result": result,
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "view_problem":
                problem_id = action.get("problem_id")
                if not problem_id:
                    return {
                        "action_result": {"error": "Missing problem_id"},
                        "should_terminate": False,
                        "termination_reason": None
                    }
                
                result = competitor.view_problem(problem_id)
                return {
                    "action_result": result,
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "get_hint":
                problem_id = action.get("problem_id")
                hint_level = action.get("hint_level", 1)
                
                if not problem_id:
                    return {
                        "action_result": {"error": "Missing problem_id"},
                        "should_terminate": False,
                        "termination_reason": None
                    }
                
                result = competitor.get_hint(problem_id, hint_level)
                return {
                    "action_result": result,
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "submission_solution":
                problem_id = action.get("problem_id")
                code = action.get("code")
                language = action.get("language", "cpp")
                
                if not problem_id or not code:
                    return {
                        "action_result": {"error": "Missing problem_id or code"},
                        "should_terminate": False,
                        "termination_reason": None
                    }
                
                result = competitor.submission_solution(problem_id, code, language)
                return {
                    "action_result": result,
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "view_rankings":
                result = competitor.view_rankings()
                return {
                    "action_result": result,
                    "should_terminate": False,
                    "termination_reason": None
                }
            
            elif action_type == "terminate":
                reason = action.get("reason", "manual_termination")
                competitor.terminate(reason)
                return {
                    "action_result": {"message": f"Competitor terminated: {reason}"},
                    "should_terminate": True,
                    "termination_reason": reason
                }
            
            else:
                return {
                    "action_result": {"error": f"Unknown action: {action_type}"},
                    "should_terminate": False,
                    "termination_reason": None
                }
                
        except Exception as e:
            logger.error(f"Error processing action {action_type} for {competitor.name}: {e}")
            return {
                "action_result": {"error": f"Action processing failed: {str(e)}"},
                "should_terminate": True,
                "termination_reason": "action_error"
            } 