"""Benchmark toolkit for USACOArena."""

from .agent_profile import (
    AGENT_PROFILE_SCHEMA,
    build_agent_profile_template,
    normalize_agent_profile,
)
from .config import BenchmarkConfigError, build_benchmark_template, load_benchmark_config
from .metrics import IntelligenceWeights, build_intelligence_report
from .paper_aggregation import aggregate_paper_runs
from .reporting import render_by_format, save_report_bundle

__all__ = [
    "AGENT_PROFILE_SCHEMA",
    "build_agent_profile_template",
    "normalize_agent_profile",
    "BenchmarkConfigError",
    "build_benchmark_template",
    "load_benchmark_config",
    "IntelligenceWeights",
    "build_intelligence_report",
    "aggregate_paper_runs",
    "render_by_format",
    "save_report_bundle",
]
