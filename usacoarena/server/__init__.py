"""
API module for USACOArena platform.

This module provides REST API endpoints for competition management,
participant interaction, and system monitoring.
"""

from .server import app, run_api

__all__ = ["app", "run_api"] 
