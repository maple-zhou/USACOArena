"""
Core business logic for CompeteMAS platform.

This module contains the core components for competition management,
data models, storage, agents, and judging system.
"""

from .models import (
    Competition, Participant, Problem, Submission, TestCase, TestResult,
    SubmissionStatus, Level, generate_id
)
from .storage import DataStorage
from .json_storage import JSONDataStorage
from .judge import Judge
from .agents import Agent, GenericAPIAgent
from .competition import CompetitionOrganizer, Competitor

__all__ = [
    "Competition", "Participant", "Problem", "Submission", "TestCase", "TestResult",
    "SubmissionStatus", "Level", "generate_id",
    "DataStorage", "JSONDataStorage", "Judge", "Agent", "GenericAPIAgent",
    "CompetitionOrganizer", "Competitor"
] 