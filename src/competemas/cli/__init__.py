"""
Command-line interface for CompeteMAS platform.

This module provides command-line tools for running competitions and managing
the platform.
"""

from .run_competition import main_sync as run_competition_main

__all__ = ["run_competition_main"] 