"""
Competition-related classes for CompeteMAS platform.

This module contains the Competitor class which serves as an abstract wrapper
for convenient API interactions during competitions.
"""

import requests
from typing import Dict, List, Optional, Tuple
from competemas.engine.agent_interface import AgentInterface
from competemas.utils.logger_config import get_logger

logger = get_logger("competition")


class Competitor:
    """Abstract wrapper for convenient competition API interactions"""
    
    def __init__(self, name: str, agent: AgentInterface, max_tokens: int = 10000000):
        self.name = name
        self.agent = agent
        self.participant_id: Optional[str] = None
        self.api_base: Optional[str] = None
        self.competition_id: Optional[str] = None
        
        # Store initialization parameters for later use
        self._init_max_tokens = max_tokens
        
        # Cached state (will be updated via API calls)
        self._cached_state: Optional[Dict] = None
    
    def _ensure_participant(self):
        """Ensure participant is available, raise error if not"""
        if self.participant_id is None:
            raise RuntimeError("Competitor not properly initialized. Call join_competition first.")
    
    def join_competition(self, api_base: str, competition_id: str, lambda_: int) -> str:
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
                    "limit_tokens": self._init_max_tokens,  # 使用正确的参数名
                    "lambda_value": lambda_  # 使用正确的参数名
                }, 
                headers={"Content-Type": "application/json"}
            )

            participant_response.raise_for_status()
            participant_result = participant_response.json()
            
            if participant_result["status"] != "success":
                raise ValueError(f"Failed to register {self.name}: {participant_result.get('message', 'Unknown error')}")
            
            participant_id = participant_result["data"]["id"]
            self.participant_id = participant_id
            return participant_id   
            
        except Exception as e:
            logger.error(f"Failed to join competition: {e}")
            raise
    
    def _get_participant_state(self) -> Dict:
        """Get current participant state from API"""
        self._ensure_participant()
        
        try:
            # 使用正确的API端点: /api/participants/get/{competition_id}/{participant_id}
            response = requests.get(
                f"{self.api_base}/api/participants/get/{self.competition_id}/{self.participant_id}",
                params={"include_submissions": "false"}
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] == "success":
                return result["data"]
            else:
                logger.warning(f"Failed to get participant state: {result.get('message', 'Unknown error')}")
                return {}
                
        except Exception as e:
            logger.warning(f"Error getting participant state: {e}")
            return {}
    
    def sync_from_api(self) -> None:
        """Synchronize participant state from API (cache the state)"""
        self._cached_state = self._get_participant_state()
        if self._cached_state:
            logger.debug(f"Synced state for {self.name}")
    
    @property
    def remaining_tokens(self) -> int:
        """Get remaining tokens from cached state or API"""
        if self._cached_state:
            return self._cached_state.get("remaining_tokens", 0)
        if self.participant_id is None:
            return 0
        state = self._get_participant_state()
        return state.get("remaining_tokens", 0)
    
    @property
    def score(self) -> int:
        """Get current score from cached state or API"""
        if self._cached_state:
            return self._cached_state.get("score", 0)
        if self.participant_id is None:
            return 0
        state = self._get_participant_state()
        return state.get("score", 0)
    
    @property
    def final_score(self) -> int:
        """Get final score from cached state or API"""
        if self._cached_state:
            # 计算最终分数：score - penalty
            score = self._cached_state.get("problem_pass_score", 0)
            penalty = self._cached_state.get("submission_penalty", 0)
            return max(0, score - penalty)
        if self.participant_id is None:
            return 0
        state = self._get_participant_state()
        score = state.get("problem_pass_score", 0)
        penalty = state.get("submission_penalty", 0)
        return max(0, score - penalty)
    
    @property
    def solved_problems(self) -> List[str]:
        """Get solved problems from cached state or API"""
        # 这个需要从submissions中计算，暂时返回空列表
        # TODO: 实现从submissions API获取已解决的问题
        return []
    
    @property
    def is_running(self) -> bool:
        """Get running status from cached state or API"""
        if self._cached_state:
            return self._cached_state.get("is_running", True)
        if self.participant_id is None:
            return True
        state = self._get_participant_state()
        return state.get("is_running", True)
    
    @property
    def termination_reason(self) -> Optional[str]:
        """Get termination reason from cached state or API"""
        if self._cached_state:
            return self._cached_state.get("termination_reason")
        if self.participant_id is None:
            return None
        state = self._get_participant_state()
        return state.get("termination_reason")
    
    def terminate(self, reason: str) -> None:
        """Terminate the competitor by updating state via API"""
        self._ensure_participant()
        
        try:
            # 使用正确的API端点: /api/participants/terminate/{competition_id}/{participant_id}
            response = requests.post(
                f"{self.api_base}/api/participants/terminate/{self.competition_id}/{self.participant_id}",
                json={
                    "reason": reason
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            # Update cached state
            self.sync_from_api()
            logger.info(f"Competitor {self.name} terminated: {reason}")
            
        except Exception as e:
            logger.error(f"Failed to terminate competitor: {e}")
    
    def get_competition_state(self) -> Dict:
        """Get the current state of the competition for this competitor"""
        return {
            "name": self.name,
            "remaining_tokens": self.remaining_tokens,
            "solved_problems": self.solved_problems,
            "is_running": self.is_running,
            "termination_reason": self.termination_reason,
            "score": self.score,
            "final_score": self.final_score
        }
    
    def view_problems(self) -> Dict:
        """Get list of competition problems"""
        self._ensure_participant()
        
        try:
            # 使用正确的API端点: /api/problems/list/{competition_id}
            response = requests.get(
                f"{self.api_base}/api/problems/list/{self.competition_id}"
            )
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
            # 使用正确的API端点: /api/problems/get/{competition_id}/{problem_id}
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
            # API端点正确: /api/hints/get/{competition_id}/{participant_id}/{problem_id}
            response = requests.post(
                f"{self.api_base}/api/hints/get/{self.competition_id}/{self.participant_id}/{problem_id}",
                json={
                    "hint_level": hint_level
                }
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            # Update local state after hint consumption
            self.sync_from_api()
            
            return {"hint": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to get hint: {str(e)}"}
    
    def submission_solution(self, problem_id: str, code: str, language: str = "cpp") -> Dict:
        """Submit a solution for a problem"""
        self._ensure_participant()
        
        try:
            # 使用正确的API端点: /api/submissions/create/{competition_id}/{participant_id}/{problem_id}
            response = requests.post(
                f"{self.api_base}/api/submissions/create/{self.competition_id}/{self.participant_id}/{problem_id}",
                json={
                    "code": code,
                    "language": language
                }
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            # Sync latest state from API
            self.sync_from_api()
            
            return {"submission": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to submit solution: {str(e)}"}
    
    def view_rankings(self) -> Dict:
        """Get current competition rankings"""
        self._ensure_participant()
        
        try:
            # 使用正确的API端点: /api/rankings/get/{competition_id}
            response = requests.get(
                f"{self.api_base}/api/rankings/get/{self.competition_id}"
            )
            response.raise_for_status()
            
            result = response.json()
            if result["status"] != "success":
                return {"error": f"API error: {result.get('message', 'Unknown error')}"}
            
            return {"rankings": result["data"]}
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch rankings: {str(e)}"}

