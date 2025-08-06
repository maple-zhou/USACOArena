"""
Beautiful logging configuration for CompeteMAS

This module provides a unified logging configuration that creates
beautiful, colored output similar to loguru library, and includes
conversation logging functionality.
"""

import logging
import sys
import re
import json
import os
from typing import Optional, List, Dict
from datetime import datetime

class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to console output"""
    
    COLORS = {
        'DEBUG': '\033[32m',      # Green text
        'INFO': '\033[36m',       # Cyan text
        'WARNING': '\033[33m',    # Yellow text
        'ERROR': '\033[31m',      # Red text
        'CRITICAL': '\033[41m\033[97m', # Red background + white text
        'RESET': '\033[0m'
    }

    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record):
        # If not console output, use normal formatting
        if not self.is_console_output():
            return super().format(record)
            
        # Save original attributes
        original_levelname = record.levelname
        original_msg = record.msg
        
        # Get color
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Only add color to log level and message
        record.levelname = f"{color}{original_levelname}{reset}"
        record.msg = f"{color}{original_msg}{reset}"
        
        # Format message
        formatted_message = super().format(record)
        
        # Restore original attributes
        record.levelname = original_levelname
        record.msg = original_msg
        
        return formatted_message

    def format_without_color(self, record):
        """Format log record without adding color codes"""
        formatted = super().format(record)
        # Remove all ANSI escape sequences
        return self.ANSI_ESCAPE.sub('', formatted)
    
    def is_console_output(self):
        """Check if it's console output"""
        # Determine if it's console output by checking handler type
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler) and handler.formatter == self:
                return True
        return False


class NoColorFormatter(ColoredFormatter):
    """Formatter without colors, used for file output"""
    def format(self, record):
        return self.format_without_color(record)


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
        self._logger = get_logger("conversation_logger")
    
    def _get_log_path(self, agent_name: str, session_id: Optional[str] = None) -> str:
        """Get the path for the log file"""
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create subdirectory for each Agent
        agent_dir = os.path.join(self.log_dir, agent_name)
        os.makedirs(agent_dir, exist_ok=True)
        
        return os.path.join(agent_dir, f"{agent_name}_log_{session_id}.json")
    
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

        # Only save the latest conversation record
        message = conversation_history[-1] if conversation_history else None
        
        if message:
            log_data_full = {
                "agent_name": agent_name,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
                f"message{datetime.now().isoformat()}": message,  # Only save the latest one
                # "metadata": metadata or {}
            }
            log_data = {
                f"message{datetime.now().isoformat()}": message,  # Only save the latest one
            }
        try:
            file_exists = os.path.exists(log_path) and os.path.getsize(log_path) > 0
            if file_exists:
                # Read from end of file forward to find the last "}" position
                with open(log_path, 'r+', encoding='utf-8') as f:
                    # Move to end of file
                    f.seek(0, 2)
                    file_size = f.tell()
                    
                    # Read character by character from end forward to find the last "}"
                    pos = file_size - 1
                    while pos >= 0:
                        f.seek(pos)
                        char = f.read(1)
                        if char == '}':
                            # Found the last "}", insert new content before it
                            break
                        pos -= 1
                    
                    if pos >= 0:
                        # Remove {} from log_data, keep only content
                        log_data_str = json.dumps(log_data, indent=2, ensure_ascii=False)
                        # Remove first and last lines (remove {})
                        log_data_lines = log_data_str.split('\n')[1:-1]
                        log_data_content = '\n'.join(log_data_lines)
                        
                        # Move to "}" position
                        f.seek(pos)
                        
                        # Insert new content
                        f.write(',\n' + log_data_content + '\n}')
                    else:
                        # If "}" not found, append directly
                        f.seek(0, 2)  # Move to end of file
                        f.write(',\n')
                        json.dump(log_data, f, indent=2, ensure_ascii=False)
                        f.write('\n}')
                
                # self._logger.info(f"Updated conversation log to {log_path}, log_data: {log_data}")
            else:
                with open(log_path, 'w', encoding='utf-8') as f:
                    json.dump(log_data_full, f, indent=2, ensure_ascii=False)

                # self._logger.info(f"Saved conversation log to {log_path}, log_data_full: {log_data_full}")
            return log_path
        except Exception as e:
            self._logger.error(f"Failed to save conversation log: {e}")
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
            self._logger.error(f"Failed to load conversation log from {log_path}: {e}")
            raise
    
    def list_conversations(self, agent_name: Optional[str] = None) -> List[str]:
        """
        List available conversation logs
        
        Args:
            agent_name: Optional agent name to filter logs
        
        Returns:
            List of log file paths
        """
        if not os.path.exists(self.log_dir):
            return []
            
        pattern = f"{agent_name}_*.json" if agent_name else "*.json"
        return sorted([
            os.path.join(self.log_dir, f)
            for f in os.listdir(self.log_dir)
            if f.endswith('.json') and (not agent_name or f.startswith(f"{agent_name}_"))
        ])


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    enable_colors: bool = True
) -> None:
    """
    Setup beautiful logging configuration
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        enable_colors: Whether to enable colored output for console
    """
    # Remove existing handlers to avoid duplicates
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Basic log format
    base_format = '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(filename)s:%(lineno)d - %(funcName)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Choose formatter based on enable_colors parameter
    if enable_colors:
        console_formatter = ColoredFormatter(base_format, datefmt=date_format)
    else:
        console_formatter = NoColorFormatter(base_format, datefmt=date_format)
    
    console_handler.setFormatter(console_formatter)
    logging.root.addHandler(console_handler)
    
    # If log file is specified, create file handler
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # File records all log levels
        file_formatter = NoColorFormatter(base_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logging.root.addHandler(file_handler)
    
    # Set root logger level
    logging.root.setLevel(logging.DEBUG)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def get_conversation_logger(log_dir: str = "logs") -> ConversationLogger:
    """
    Get a conversation logger instance
    
    Args:
        log_dir: Directory to store conversation logs
        
    Returns:
        ConversationLogger instance
    """
    return ConversationLogger(log_dir)


# Default setup when module is imported
if not logging.root.handlers:
    setup_logging() 