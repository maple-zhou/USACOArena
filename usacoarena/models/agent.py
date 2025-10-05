"""
Agent base class for USACOArena platform.

This module contains the Agent abstract base class that defines the interface
for all LLM agents participating in programming competitions.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import json
import os
import time
from datetime import datetime
from usacoarena.utils.logger_config import get_logger, get_conversation_logger

logger = get_logger("agent")


class Agent(ABC):
    """
    Abstract base class for LLM agents in programming competitions.
    
    This class provides the foundation for all agent implementations, handling:
    - Conversation history management
    - Prompt generation and response parsing
    - Logging and session management
    - API configuration loading
    
    Subclasses must implement the generate_response method to handle
    communication with specific LLM providers.
    """
    
    def __init__(
        self,
        name: str,
        prompt_config_path: Optional[str] = None,
        log_dir: str = "logs",
        session_id: Optional[str] = None
    ):
        """
        Initialize the agent base class
        
        Args:
            name: Agent name
            prompt_config_path: Path to prompt configuration file
            log_dir: Directory for conversation logs
            session_id: Optional session identifier
        """
        self._name = name
        self.prompt_config_path = prompt_config_path
        self.log_dir = log_dir
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize conversation logger
        self.conversation_logger = get_conversation_logger(log_dir=log_dir)
        
        # Load prompt system and action parser
        if prompt_config_path:
            from agents.single_agent.prompts.prompt_manager import PromptSystem, ActionParser
            self.prompt_system = PromptSystem(prompt_config_path)
            self.action_parser = ActionParser(prompt_config_path)
        else:
            self.prompt_system = None
            self.action_parser = None
        
        # API configuration
        self.max_retries = 30
        self.retry_delay = 1.0
        
        # Load API configuration
        self.max_tokens, self.token_multiplier = self._load_api_config()
        
        # Conversation history
        self.conversation_history: List[Dict[str, str]] = []
        self.conversation_history.append({"role": "system", "content": self.prompt_system.system_prompt})
        self.save_conversation()
        
        logger.info(f"Initialized agent: {name}")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the agent name"""
        pass
    
    @property 
    @abstractmethod
    def api_base_url(self) -> str:
        """Get the API base URL"""
        pass
    
    @property
    @abstractmethod
    def api_key(self) -> str:
        """Get the API key"""
        pass
    
    @abstractmethod
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process the current state and return actions"""
        pass
    
    @abstractmethod
    async def generate_response(self, state: Dict[str, Any], prompt: str) -> str:
        """Generate response from LLM"""
        pass
    
    def _load_api_config(self) -> tuple[int, int]:
        """Load API configuration from config file"""
        try:
            config_path = "config/api_config.json"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                return config.get("max_tokens", 100000), config.get("token_multiplier", 1)
            else:
                logger.warning(f"API config file not found: {config_path}")
                return 100000, 1
        except Exception as e:
            logger.error(f"Error loading API config: {e}")
            return 100000, 1
    
    def truncate_conversation_history(self, max_turns: int = 6) -> None:
        """
        Truncate conversation history to prevent token overflow
        
        Args:
            max_turns: Maximum number of conversation turns to keep
        """
        if len(self.conversation_history) > max_turns * 2:  # Each turn has user + assistant
            # Keep the first and last few turns
            keep_start = max_turns // 2
            keep_end = max_turns // 2
            
            start_messages = self.conversation_history[:keep_start * 2]
            end_messages = self.conversation_history[-(keep_end * 2):]
            
            self.conversation_history = start_messages + end_messages
            
            logger.info(f"Truncated conversation history to {len(self.conversation_history)} messages")
    
    def add_to_conversation(self, role: str, content: str) -> None:
        """Add a message to the conversation history"""
        self.conversation_history.append({"role": role, "content": content})
    
    def get_conversation_history(self) -> List[Dict]:
        """Get the current conversation history"""
        return self.conversation_history.copy()
    
    def save_conversation(self, metadata: Optional[Dict] = None) -> str:
        """Save conversation to log file"""
        return self.conversation_logger.save_conversation(
            agent_name=self._name,
            conversation_history=self.conversation_history,
            session_id=self.session_id,
            metadata=metadata
        ) 
