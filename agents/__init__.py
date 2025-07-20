"""
Custom agent implementations for CompeteMAS competitions.
 
This module contains user-defined AI agents that can participate 
in programming competitions. Users can implement their own agent
strategies and algorithms here.
"""

from .single_agent import GenericAPIAgent, StreamingGenericAPIAgent
from .mapcoder import MapCoderAgent

__all__ = ["GenericAPIAgent", "StreamingGenericAPIAgent", "MapCoderAgent"] 