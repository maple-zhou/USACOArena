"""
Core business logic for CompeteMAS platform.

This module contains the core components for competition management,
data models, storage, and judging system.
"""

from .models import (
    Competition, Participant, Problem, Submission, TestCase, TestResult,
    SubmissionStatus, Level, generate_id
)
from .storage import DuckDBStorage
from .agent_interface import AgentInterface
from .judge import Judge
from .competition import CompetitionOrganizer, Competitor

__all__ = [
    "Competition", "Participant", "Problem", "Submission", "TestCase", "TestResult",
    "SubmissionStatus", "Level", "generate_id",
    "DuckDBStorage", "Judge", "AgentInterface",
    "CompetitionOrganizer", "Competitor"
] 