"""
Configuration management for CompeteMAS server.

This module provides a centralized configuration management system
that supports file-based configuration, environment variables, and
command-line arguments with proper precedence handling.
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from competemas.utils.logger_config import get_logger

logger = get_logger("config_manager")


class ConfigManager:
    """Centralized configuration management for CompeteMAS server"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager
        
        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = config_path or "config/server_config.json"
        self._config = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file and environment variables"""
        # Load default configuration
        self._config = self._get_default_config()
        
        # Load from file if exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                self._merge_config(file_config)
                logger.info(f"Loaded configuration from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config file {self.config_path}: {e}")
        
        # Override with environment variables
        self._load_from_env()
        
        logger.info("Configuration loaded successfully")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        return {
            "logging": {
                "level": "INFO",
                "directory": "logs/competition_system",
                "enable_colors": True
            },
            "online_judge": {
                "endpoint": "http://localhost:9000/2015-03-31/functions/function/invocations"
            },
            "rate_limiting": {
                "min_interval": 0.05
            },
            "database": {
                "path": "data/competemas.duckdb",
                "backup_json": True
            },
            "data_sources": {
                "problem_data_dir": "dataset/datasets/usaco_2025",
                "textbook_data_dir": "dataset/textbooks"
            }
        }
    
    def _merge_config(self, new_config: Dict[str, Any]) -> None:
        """Merge new configuration into existing config"""
        def merge_dict(target: Dict[str, Any], source: Dict[str, Any]) -> None:
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    merge_dict(target[key], value)
                else:
                    target[key] = value
        
        merge_dict(self._config, new_config)
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables"""
        env_mappings = {
            "COMPETEMAS_LOG_LEVEL": ("logging", "level"),
            "COMPETEMAS_LOG_DIR": ("logging", "directory"),
            "COMPETEMAS_OJ_ENDPOINT": ("online_judge", "endpoint"),
            "COMPETEMAS_RATE_LIMIT_INTERVAL": ("rate_limiting", "min_interval"),
            "COMPETEMAS_DB_PATH": ("database", "path"),
            "COMPETEMAS_DB_BACKUP_JSON": ("database", "backup_json"),
            "COMPETEMAS_PROBLEM_DATA_DIR": ("data_sources", "problem_data_dir"),
            "COMPETEMAS_TEXTBOOK_DATA_DIR": ("data_sources", "textbook_data_dir"),
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                self._set_nested_value(config_path, self._parse_env_value(value))
    
    def _set_nested_value(self, path: tuple, value: Any) -> None:
        """Set a nested configuration value"""
        current = self._config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value
    
    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type"""
        # Boolean values
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True
        if value.lower() in ('false', '0', 'no', 'off'):
            return False
        
        # Integer values
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float values
        try:
            return float(value)
        except ValueError:
            pass
        
        # List values (comma-separated)
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        
        # String values
        return value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key: Configuration key (e.g., "logging.level")
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        current = self._config
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        
        return current
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value using dot notation
        
        Args:
            key: Configuration key (e.g., "logging.level")
            value: Value to set
        """
        keys = key.split('.')
        current = self._config
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get entire configuration section
        
        Args:
            section: Section name (e.g., "logging")
            
        Returns:
            Configuration section as dictionary
        """
        return self._config.get(section, {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary"""
        return self._config.copy()
    
    def save(self, path: Optional[str] = None) -> None:
        """
        Save current configuration to file
        
        Args:
            path: File path to save to (uses default if not specified)
        """
        save_path = path or self.config_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Configuration saved to {save_path}")


# Global configuration instance
_global_config: Optional[ConfigManager] = None


def get_config(config_path: Optional[str] = None) -> ConfigManager:
    """
    Get or create global configuration instance
    
    Args:
        config_path: Configuration file path (optional)
        
    Returns:
        Global configuration manager instance
    """
    global _global_config
    if _global_config is None:
        _global_config = ConfigManager(config_path)
    return _global_config


def set_config(config_manager: ConfigManager) -> None:
    """
    Set global configuration instance
    
    Args:
        config_manager: Configuration manager instance
    """
    global _global_config
    _global_config = config_manager 