import json
import os
from typing import List, Dict, Optional
from datetime import datetime
from competemas.utils.logger_config import get_logger

logger = get_logger("conversation_logger")


class ConversationLogger:
    """Logger for saving and loading conversation histories"""
    
    def __init__(self, log_dir: str = "logs"):
        """
        Initialize the conversation logger
        
        Args:
            log_dir: Directory to store conversation logs
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_log_path(self, agent_name: str, session_id: Optional[str] = None) -> str:
        """Get the path for the log file"""
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.log_dir, f"{agent_name}_{session_id}.json")
    
    def save_conversation(
        self,
        agent_name: str,
        conversation_history: List[Dict],
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Save conversation history to a file
        
        Args:
            agent_name: Name of the agent
            conversation_history: List of conversation messages
            session_id: Optional session identifier
            metadata: Optional metadata about the conversation
        
        Returns:
            Path to the saved log file
        """
        log_path = self._get_log_path(agent_name, session_id)
        
        log_data = {
            "agent_name": agent_name,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "conversation": conversation_history,
            "metadata": metadata or {}
        }
        
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved conversation log to {log_path}")
            return log_path
        except Exception as e:
            logger.error(f"Failed to save conversation log: {e}")
            raise
    
    def load_conversation(self, log_path: str) -> Dict:
        """
        Load conversation history from a file
        
        Args:
            log_path: Path to the log file
        
        Returns:
            Dictionary containing the conversation data
        """
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load conversation log from {log_path}: {e}")
            raise
    
    def list_conversations(self, agent_name: Optional[str] = None) -> List[str]:
        """
        List available conversation logs
        
        Args:
            agent_name: Optional agent name to filter logs
        
        Returns:
            List of log file paths
        """
        pattern = f"{agent_name}_*.json" if agent_name else "*.json"
        return sorted([
            os.path.join(self.log_dir, f)
            for f in os.listdir(self.log_dir)
            if f.endswith('.json') and (not agent_name or f.startswith(f"{agent_name}_"))
        ]) 