"""
Competition-related classes for CompeteMAS platform.

This module contains the Competitor class which serves as an optimized bridge
between AgentInterface and Participant data, minimizing API calls and state management overhead.
"""

import requests
from typing import Dict, List, Optional, Tuple
from competemas.engine.agent_interface import AgentInterface
from competemas.utils.logger_config import get_logger

logger = get_logger("competition")


class Competitor:
    """Optimized bridge between AgentInterface and Participant data"""
    
    def __init__(self, name: str, agent: AgentInterface, limit_tokens: int = 10000000):
        self.name = name
        self.api_base: Optional[str] = None
        self.agent = agent
        self.participant_id: Optional[str] = None
        self.competition_id: Optional[str] = None
        
        # Store initialization parameters
        self.limit_tokens = limit_tokens
        
        # Competition context (cached for efficiency)
        self._competition_problems: Optional[List[Dict]] = None
        self._competition_rules: Optional[Dict] = None
    
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
    
    # @property
    # def solved_problems(self) -> List[str]:
    #     """Get solved problems from cached state or API"""
    #     # TODO: 实现从submissions API获取已解决的问题
    #     return []
    
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
                # params={"include_submissions": "true"}
            )
            response.raise_for_status()
            # print(f"1111111111111111111111: {response.json()}")
            # print(f"solved_problems: {response.json()}")
            result = response.json()
            if result["status"] == "success":
                # print(f"result: {result['data']}")
                return result["data"]
            else:
                logger.warning(f"Failed to get participant state: {result.get('message', 'Unknown error')}")
                return {}
                
        except Exception as e:
            logger.warning(f"Error getting participant state: {e}")
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
            
            # Cache competition context for efficiency
            # self._cache_competition_context()
            
            return self.participant_id   
            
        except Exception as e:
            logger.error(f"Failed to join competition: {e}")
            raise
    
    # def _cache_competition_context(self) -> None:
        """Cache competition problems and rules for efficient access"""
        try:
            # Cache problems list
            problems_response = requests.get(f"{self.api_base}/api/problems/list/{self.competition_id}")
            if problems_response.status_code == 200:
                result = problems_response.json()
                if result.get("status") == "success":
                    self._competition_problems = result.get("data", [])
            
            # Cache competition rules (if needed for local calculations)
            comp_response = requests.get(f"{self.api_base}/api/competitions/get/{self.competition_id}")
            if comp_response.status_code == 200:
                result = comp_response.json()
                if result.get("status") == "success":
                    comp_data = result.get("data", {})
                    self._competition_rules = comp_data.get("rules", {})
                    
        except Exception as e:
            logger.warning(f"Failed to cache competition context: {e}")
    
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
    
    # def get_competition_state(self) -> Dict:
    #     """Get the current state of the competition for this competitor"""
    #     return {
    #         "name": self.name,
    #         "participant_id": self.participant_id,
    #         "remaining_tokens": self.remaining_tokens,
    #         "solved_problems": [],  # TODO: 实现从submissions API获取已解决的问题
    #         "is_running": self.is_running,
    #         "termination_reason": self.termination_reason,
    #         "score": self.score,
    #     }
    
    def view_problems(self) -> Dict:
        """Get list of competition problems (with caching)"""
        self._ensure_participant()
        
        # Use cached problems if available
        if self._competition_problems:
            return {"problems": self._competition_problems}
        
        try:
            response = requests.get(f"{self.api_base}/api/problems/list/{self.competition_id}")
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            # Cache for future use
            self._competition_problems = result["data"]
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
    
    def get_hint(self, problem_id: str, hint_level: int) -> Dict:
        """Get a hint for a specific problem"""
        self._ensure_participant()
        
        try:
            response = requests.post(
                f"{self.api_base}/api/hints/get/{self.competition_id}/{self.participant_id}/{problem_id}",
                json={"hint_level": hint_level}
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return {"hint": result["data"]}
            
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

