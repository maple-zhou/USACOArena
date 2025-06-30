"""
API layer for CompeteMAS platform.

This module provides the Flask-based REST API server for the competition platform.
"""

from .server import app, run_api

__all__ = ["app", "run_api"] 