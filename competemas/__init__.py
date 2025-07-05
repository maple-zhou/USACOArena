"""
CompeteMAS - Multi-Agent System Competition Framework

A high-performance framework for running programming competitions
between AI agents with advanced analytics and evaluation capabilities.
"""

from .models.models import (
    Competition, Participant, Problem, Submission, Case, TestResult,
    SubmissionStatus, Level, generate_id
)
from .engine.storage import DuckDBStorage
from .engine.judge import Judge
from .engine.competition import Competitor
from .engine.agent_interface import AgentInterface

__version__ = "0.2.0"
__all__ = [
    "Competition", "Participant", "Problem", "Submission", "Case", "TestResult",
    "SubmissionStatus", "Level", "generate_id",
    "DuckDBStorage", "Judge", "AgentInterface", "Competitor"
] 