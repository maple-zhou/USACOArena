"""
TypedDict definitions for JSON-based data storage.
This provides type safety and better data structure for the storage system.
"""

from typing import TypedDict, List, Optional, Dict, Any, Union
from datetime import datetime

# 基础类型定义
class LevelDict(TypedDict):
    name: str
    color: str

class TestCaseDict(TypedDict):
    id: str
    input_data: str
    expected_output: str
    is_hidden: Optional[bool]
    time_limit_ms: Optional[int]
    memory_limit_mb: Optional[int]

class TestResultDict(TypedDict):
    test_case_id: str
    status: str  # SubmissionStatus 的字符串值
    execution_time_ms: Optional[int]
    memory_used_kb: Optional[int]
    output: Optional[str]
    error_message: Optional[str]

class ProblemDict(TypedDict):
    id: str
    title: str
    description: str
    level: str  # Level 枚举的字符串值
    test_cases: List[TestCaseDict]
    sample_cases: List[TestCaseDict]
    time_limit_ms: int
    memory_limit_mb: int
    first_to_solve: Optional[str]  # Participant ID

class ParticipantDict(TypedDict):
    id: str
    name: str
    api_base_url: str
    api_key: str
    max_tokens: int
    lambda_: int
    score: int
    final_score: int
    remaining_tokens: int
    submission_count: int
    accepted_count: int

class SubmissionDict(TypedDict):
    id: str
    competition_id: str
    participant_id: str
    problem_id: str
    code: str
    language: str
    submitted_at: str  # ISO 格式的 datetime 字符串
    status: str  # SubmissionStatus 的字符串值
    test_results: List[TestResultDict]
    score: int
    penalty: int
    execution_time_ms: Optional[int]
    memory_used_kb: Optional[int]

class CompetitionRulesDict(TypedDict):
    scoring: Dict[str, int]
    bonus_for_first_ac: int
    penalties: Dict[str, int]
    input_token_multipliers: Dict[str, float]
    output_token_multipliers: Dict[str, float]

class CompetitionDict(TypedDict):
    id: str
    title: str
    description: str
    created_at: str  # ISO 格式的 datetime 字符串
    start_time: Optional[str]
    end_time: Optional[str]
    problems: List[ProblemDict]
    participants: List[ParticipantDict]
    max_tokens_per_participant: int
    rules: CompetitionRulesDict
    is_active: bool
    version: int  # 数据格式版本

class StorageMetadata(TypedDict):
    """存储元数据"""
    version: int
    created_at: str
    last_modified: str
    total_competitions: int
    total_submissions: int
    storage_format: str  # "json", "compressed_json", etc.
    compression_enabled: bool

class StorageStats(TypedDict):
    """存储统计信息"""
    total_size_bytes: int
    competitions_count: int
    submissions_count: int
    average_competition_size: float
    average_submission_size: float
    last_backup: Optional[str] 