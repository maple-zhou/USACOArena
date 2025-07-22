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
    """为控制台输出添加颜色的格式化器"""
    
    COLORS = {
        'DEBUG': '\033[32m',      # 绿色字
        'INFO': '\033[36m',       # 青色字
        'WARNING': '\033[33m',    # 黄色字
        'ERROR': '\033[31m',      # 红色字
        'CRITICAL': '\033[41m\033[97m', # 红色背景+白色字
        'RESET': '\033[0m'
    }

    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record):
        # 如果不是控制台输出，使用普通格式化
        if not self.is_console_output():
            return super().format(record)
            
        # 保存原始属性
        original_levelname = record.levelname
        original_msg = record.msg
        
        # 获取颜色
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # 只给日志级别和消息添加颜色
        record.levelname = f"{color}{original_levelname}{reset}"
        record.msg = f"{color}{original_msg}{reset}"
        
        # 格式化消息
        formatted_message = super().format(record)
        
        # 恢复原始属性
        record.levelname = original_levelname
        record.msg = original_msg
        
        return formatted_message

    def format_without_color(self, record):
        """格式化日志记录，但不添加颜色代码"""
        formatted = super().format(record)
        # 移除所有ANSI转义序列
        return self.ANSI_ESCAPE.sub('', formatted)
    
    def is_console_output(self):
        """检查是否是控制台输出"""
        # 通过判断handler类型来确定是否是控制台输出
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler) and handler.formatter == self:
                return True
        return False


class NoColorFormatter(ColoredFormatter):
    """不带颜色的格式化器，用于文件输出"""
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
        
        # 为每个Agent创建子目录
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
            self._logger.info(f"Saved conversation log to {log_path}")
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
    
    # 基本日志格式
    base_format = '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(filename)s:%(lineno)d - %(funcName)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # 根据enable_colors参数选择格式化器
    if enable_colors:
        console_formatter = ColoredFormatter(base_format, datefmt=date_format)
    else:
        console_formatter = NoColorFormatter(base_format, datefmt=date_format)
    
    console_handler.setFormatter(console_formatter)
    logging.root.addHandler(console_handler)
    
    # 如果指定了日志文件，创建文件处理器
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别的日志
        file_formatter = NoColorFormatter(base_format, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logging.root.addHandler(file_handler)
    
    # 设置根日志记录器级别
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