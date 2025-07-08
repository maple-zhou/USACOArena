"""
Beautiful logging configuration for CompeteMAS

This module provides a unified logging configuration that creates
beautiful, colored output similar to loguru library.
"""

import logging
import sys
import re
from typing import Optional

class ColoredFormatter(logging.Formatter):
    """为控制台输出添加颜色的格式化器"""
    
    COLORS = {
        'DEBUG': '\033[32m',      # 绿色
        'INFO': '\033[36m',       # 青色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[41m\033[97m', # 红色背景+白字
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


# Default setup when module is imported
if not logging.root.handlers:
    setup_logging() 