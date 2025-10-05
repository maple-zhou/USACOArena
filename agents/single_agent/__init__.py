"""
Single Agent Implementation for USACOArena

This module provides generic agent implementations that can work with various LLM providers.
"""

from .single_agent import GenericAPIAgent, StreamingGenericAPIAgent

__all__ = ["GenericAPIAgent", "StreamingGenericAPIAgent"] 
