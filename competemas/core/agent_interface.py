"""
Agent interface for CompeteMAS competition system.

Defines the abstract interface that all competition agents must implement.
This allows for loose coupling between the core competition system and
user-defined agent implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


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