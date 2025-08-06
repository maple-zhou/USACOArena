"""
Competition-related classes for CompeteMAS platform.

This module contains the Competitor class which serves as an optimized bridge
between Agent and Participant data, minimizing API calls and state management overhead.
"""

import requests
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from competemas.utils.logger_config import get_logger

if TYPE_CHECKING:
    from agents import Agent

logger = get_logger("competition")


class Competitor:
    """Optimized bridge between Agent and Participant data"""
    
    def __init__(self, name: str, agent: "Agent", limit_tokens: int = 10000000):
        self.name = name
        self.api_base: Optional[str] = None
        self.agent = agent
        self.participant_id: Optional[str] = None
        self.competition_id: Optional[str] = None
        
        # Store initialization parameters
        self.limit_tokens = limit_tokens
    
    # Properties with direct API access
    @property
    def remaining_tokens(self) -> int:
        """Get remaining tokens from API"""
        state = self.get_participant_state()
        return state.get("remaining_tokens", 0)
    
    @property
    def score(self) -> int:
        """Get current score from API"""
        state = self.get_participant_state()
        return state.get("score", 0)
    
    
    @property
    def is_running(self) -> bool:
        """Get running status from API"""
        state = self.get_participant_state()
        return state.get("is_running", True)
    
    @property
    def termination_reason(self) -> Optional[str]:
        """Get termination reason from API"""
        state = self.get_participant_state()
        return state.get("termination_reason")

    def _ensure_participant(self):
        """Ensure participant is available, raise error if not"""
        if self.participant_id is None:
            raise RuntimeError("Competitor not properly initialized. Call join_competition first.")
    
    def get_participant_state(self) -> Dict:
        """Get current participant state from API"""
        self._ensure_participant()
        
        try:
            response = requests.get(
                f"{self.api_base}/api/participants/get_solved_problems/{self.competition_id}/{self.participant_id}",
            )
            response.raise_for_status()

            result = response.json()
            if result["status"] == "success":
                return result["data"]
            else:
                logger.warning(f"Failed to get participant state: {result.get('message', 'Unknown error')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting participant state: {e}")
            return {}
    
    def join_competition(self, api_base: str, competition_id: str, lambda_: int):
        """Join a competition by creating a participant via API"""
        self.api_base = api_base
        self.competition_id = competition_id
        
        try:
            participant_response = requests.post(
                f"{self.api_base}/api/participants/create/{competition_id}",
                json={
                    "name": self.name, 
                    "api_base_url": self.agent.api_base_url, 
                    "api_key": self.agent.api_key, 
                    "limit_tokens": self.limit_tokens,
                    "lambda_value": lambda_
                }, 
                headers={"Content-Type": "application/json"}
            )

            participant_response.raise_for_status()
            participant_result = participant_response.json()
            
            if participant_result["status"] != "success":
                raise ValueError(f"Failed to register {self.name}: {participant_result.get('message', 'Unknown error')}")
            
            self.participant_id = participant_result["data"]["id"]
            
            return self.participant_id   
            
        except Exception as e:
            logger.error(f"Failed to join competition: {e}")
            raise
    
    def terminate(self, reason: str) -> None:
        """Terminate the competitor by updating state via API"""
        self._ensure_participant()
        
        try:
            response = requests.post(
                f"{self.api_base}/api/participants/terminate/{self.competition_id}/{self.participant_id}",
                json={"reason": reason},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            logger.info(f"Competitor {self.name} terminated: {reason}")
            
        except Exception as e:
            logger.error(f"Failed to terminate competitor: {e}")
    
    
    def view_problems(self) -> Dict:
        """Get list of competition problems"""
        self._ensure_participant()
        
        
        try:
            response = requests.get(f"{self.api_base}/api/problems/list/{self.competition_id}")
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return {"problems": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch problems: {str(e)}"}
    
    def view_problem(self, problem_id: str) -> Dict:
        """Get details of a specific problem"""
        self._ensure_participant()
        
        try:
            response = requests.get(
                f"{self.api_base}/api/problems/get/{self.competition_id}/{problem_id}"
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return {"problem": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch problem: {str(e)}"}
    
    def get_hint(self, problem_id: str, hint_level: int, hint_knowledge: Optional[str] = None, problem_difficulty: Optional[str] = None) -> Dict:
        """Get a hint for a specific problem"""
        self._ensure_participant()
        
        try:
            request_data: Dict[str, Any] = {"hint_level": hint_level}
            if problem_id is not None:
                request_data["problem_id"] = problem_id
            
            # Add optional parameters based on hint level
            if hint_knowledge is not None:
                request_data["hint_knowledge"] = hint_knowledge
            if problem_difficulty is not None:
                request_data["problem_difficulty"] = problem_difficulty
            
            # For hint levels that don't require problem_id (like level 0 strategy hints)
            url = f"{self.api_base}/api/hints/get/{self.competition_id}/{self.participant_id}"
            response = requests.post(url, json=request_data)
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return result["data"]

        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to get hint: {str(e)}"}
    
    def submission_solution(self, problem_id: str, code: str, language: str = "cpp") -> Dict:
        """Submit a solution for a problem"""
        self._ensure_participant()
        
        try:
            response = requests.post(
                f"{self.api_base}/api/submissions/create/{self.competition_id}/{self.participant_id}/{problem_id}",
                json={"code": code, "language": language}
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return {"submission": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to submit solution: {str(e)}"}
    
    def view_rankings(self) -> Dict:
        """Get current competition rankings"""
        self._ensure_participant()
        
        try:
            response = requests.get(f"{self.api_base}/api/rankings/get/{self.competition_id}")
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return {"rankings": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch rankings: {str(e)}"}

