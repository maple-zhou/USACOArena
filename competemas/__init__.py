"""
CompeteMAS - Multi-Agent System Competition Framework

A high-performance framework for running programming competitions
between AI agents with advanced analytics and evaluation capabilities.
"""

from .core.models import (
    Competition, Participant, Problem, Submission, TestCase, TestResult,
    SubmissionStatus, Level, generate_id
)
from .core.storage import DuckDBStorage
from .core.judge import Judge
from .core.competition import CompetitionOrganizer, Competitor
from .core.agent_interface import AgentInterface

__version__ = "0.2.0"
__all__ = [
    "Competition", "Participant", "Problem", "Submission", "TestCase", "TestResult",
    "SubmissionStatus", "Level", "generate_id",
    "DuckDBStorage", "Judge", "AgentInterface",
    "CompetitionOrganizer", "Competitor"
] 