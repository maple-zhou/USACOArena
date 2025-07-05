"""
Agent interface for CompeteMAS competition system.

Defines the abstract interface that all competition agents must implement.
This allows for loose coupling between the engine competition system and
user-defined agent implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass


@dataclass
class AgentRequest:
    """Standardized agent request format"""
    method: str
    url: str
    headers: Dict[str, str]
    json_data: Dict[str, Any]
    timeout: float = 30.0
    response_format: Optional[Dict[str, Any]] = None


@dataclass
class AgentResponse:
    """Standardized agent response format"""
    content: str
    usage: Dict[str, Any]
    status_code: int = 200
    error: Optional[str] = None


@dataclass
class TokenUsage:
    """Token usage information"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    
    def __post_init__(self):
        self.total_tokens = self.prompt_tokens + self.completion_tokens + self.reasoning_tokens


class AgentInterface(ABC):
    """
    Abstract interface for competition agents.
    
    All agents participating in CompeteMAS competitions must implement this interface.
    This ensures consistent interaction patterns while allowing for flexible 
    agent implementations in user scripts.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the agent name"""
        pass
    
    @property 
    @abstractmethod
    def api_base_url(self) -> str:
        """Get the agent's API base URL"""
        pass
    
    @property
    @abstractmethod
    def api_key(self) -> str:
        """Get the agent's API key"""
        pass
    
    @abstractmethod
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the current competition state and generate the next action.
        
        Args:
            state: Dictionary containing the current competition state
            
        Returns:
            Dictionary containing the next action to take
        """
        pass
    
    @abstractmethod
    async def generate_response(self, state: Dict[str, Any], prompt: str) -> tuple[str, tuple[int, int]]:
        """
        Generate a response using the agent's configured API.
        
        Args:
            state: Competition state dictionary
            prompt: Input prompt for the agent
            
        Returns:
            Tuple of (response_text, (prompt_tokens, completion_tokens))
        """
        pass
    
    def create_request(self, method: str, url: str, headers: Dict[str, str], 
                      json_data: Dict[str, Any], timeout: float = 30.0,
                      response_format: Optional[Dict[str, Any]] = None) -> AgentRequest:
        """
        Create a standardized agent request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            headers: Request headers
            json_data: Request body data
            timeout: Request timeout in seconds
            response_format: Optional response format configuration
            
        Returns:
            AgentRequest object
        """
        return AgentRequest(
            method=method,
            url=url,
            headers=headers,
            json_data=json_data,
            timeout=timeout,
            response_format=response_format
        )
    
    def parse_token_usage(self, usage_data: Dict[str, Any]) -> TokenUsage:
        """
        Parse token usage from API response.
        
        Args:
            usage_data: Usage data from API response
            
        Returns:
            TokenUsage object
        """
        return TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            reasoning_tokens=usage_data.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        )
    
    def apply_token_multipliers(self, token_usage: TokenUsage, 
                               competition_rules: Dict[str, Any], 
                               model_id: str) -> TokenUsage:
        """
        Apply token multipliers based on competition rules.
        
        Args:
            token_usage: Original token usage
            competition_rules: Competition rules dictionary
            model_id: Model identifier
            
        Returns:
            TokenUsage with applied multipliers
        """
        if not competition_rules:
            return token_usage
        
        # Apply input token multiplier
        input_multiplier = competition_rules.get("input_token_multipliers", {}).get(model_id)
        if input_multiplier is not None:
            token_usage.prompt_tokens = int(token_usage.prompt_tokens * input_multiplier)
        
        # Apply output token multiplier
        output_multiplier = competition_rules.get("output_token_multipliers", {}).get(model_id)
        if output_multiplier is not None:
            token_usage.completion_tokens = int(token_usage.completion_tokens * output_multiplier)
        
        # Recalculate total
        token_usage.total_tokens = token_usage.prompt_tokens + token_usage.completion_tokens + token_usage.reasoning_tokens
        
        return token_usage 