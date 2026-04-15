from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import uuid

# Helper function to generate unique IDs
def generate_id() -> str:
    """Generate a unique ID for entities"""
    return str(uuid.uuid4())


class SubmissionStatus(str, Enum):
    ACCEPTED = "AC"
    WRONG_ANSWER = "WA"
    RUNTIME_ERROR = "RE"
    COMPILATION_ERROR = "CE"
    TIME_LIMIT_EXCEEDED = "TLE"
    MEMORY_LIMIT_EXCEEDED = "MLE"
    PENDING = "PENDING"


class Level(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class Participant:
    def __init__(
        self,
        id: str,
        competition_id: str,
        name: str,
        api_base_url: str,
        api_key: str,
        limit_tokens: int,
        lambda_value: int,
        agent_profile: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        terminated_at: Optional[datetime] = None,
        delivery_time_seconds: int = 0,
        delivery_time_multiplier: float = 1.0,
        delivery_time_credit: float = 0.0,
    ):
        # Core persistent attributes
        self.id = id
        self.competition_id = competition_id
        self.name = name
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.agent_profile = agent_profile if isinstance(agent_profile, dict) else {}

        # Token tracking   B_token_remaining
        self.LLM_tokens = 0
        self.hint_tokens = 0
        self.submission_tokens = 0
        self.test_tokens = 0
        self.consumed_tokens = 0  # Total actual tokens consumed (without penalties)
        self.limit_tokens = limit_tokens
        self.remaining_tokens = limit_tokens
        self.lambda_value = lambda_value

        # Submission tracking
        self.submission_count = 0
        self.accepted_count = 0

        # P_submission_count
        self.submission_penalty = 0
        # S_accepted_score
        self.problem_pass_score = 0

        # New statistics fields
        self.llm_inference_count = 0  # Total LLM inference calls
        self.first_ac_score = 0  # Score from being first to solve problems
        self.problem_score = 0  # Score from passing problems (excluding first AC bonus)

        # Detailed rule-based scoring breakdown
        self.bronze_score = 0
        self.silver_score = 0
        self.gold_score = 0
        self.platinum_score = 0
        self.bonus_score = 0  # First AC bonuses

        # Per-problem detailed statistics (Dict[problem_id, stats])
        self.problem_stats = {}  # Will contain detailed per-problem statistics

        #  total_score = S_accepted_score - P_submission_count + B_token_remaining
        self.score = 0
        
        # Runtime state
        self.is_running: bool = True
        self.termination_reason: Optional[str] = None

        # Delivery-time settlement state
        self.started_at: datetime = started_at or datetime.now()
        self.terminated_at: Optional[datetime] = terminated_at
        self.delivery_time_seconds: int = self._to_non_negative_int(delivery_time_seconds, 0)
        self.delivery_time_multiplier: float = self._to_non_negative_float(
            delivery_time_multiplier, 1.0
        )
        self.delivery_time_credit: float = self._to_non_negative_float(delivery_time_credit, 0.0)

    @staticmethod
    def _to_non_negative_int(value: Any, default: int = 0) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, parsed)

    @staticmethod
    def _to_non_negative_float(value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, parsed)

    def get_elapsed_time_seconds(self, now: Optional[datetime] = None) -> int:
        if not self.started_at:
            return 0
        end_time = (
            self.terminated_at
            if (not self.is_running and self.terminated_at is not None)
            else (now or datetime.now())
        )
        try:
            # Use unix timestamp delta to avoid aware/naive subtraction errors.
            return max(0, int(end_time.timestamp() - self.started_at.timestamp()))
        except Exception:
            start = self.started_at
            if (start.tzinfo is None) != (end_time.tzinfo is None):
                if start.tzinfo is None and end_time.tzinfo is not None:
                    start = start.replace(tzinfo=end_time.tzinfo)
                elif start.tzinfo is not None and end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=start.tzinfo)
            return max(0, int((end_time - start).total_seconds()))

    def get_consumed_credit(self) -> float:
        base_credit = float((self.consumed_tokens or 0) + (self.submission_penalty or 0))
        if not self.is_running:
            return base_credit + self._to_non_negative_float(self.delivery_time_credit, 0.0)
        return base_credit

    def terminate(self, reason: str, terminated_at: Optional[datetime] = None) -> None:
        """Terminate the participant with a reason"""
        settled_at = terminated_at or datetime.now()
        self.is_running = False
        self.termination_reason = reason
        self.terminated_at = settled_at
        self.delivery_time_seconds = self.get_elapsed_time_seconds(now=settled_at)
        self.delivery_time_credit = (
            float(self.delivery_time_seconds) * self.delivery_time_multiplier
        )

    def initialize_problem_stats(self, problem_id: str) -> None:
        """Initialize statistics for a problem"""
        if problem_id not in self.problem_stats:
            self.problem_stats[problem_id] = {
                "problem_id": problem_id,
                "submission_count": 0,
                "passed_test_cases": 0,
                "total_test_cases": 0,
                "best_score": 0,
                "penalty": 0,
                "solved": False,
                "solved_at": None,
                "first_submission_at": None,
                "last_submission_at": None,
                "is_first_ac": False,
                "language_used": None
            }

    def initialize_all_problems_stats(self, problem_ids: List[str]) -> None:
        """Initialize statistics for all problems in the competition"""
        for problem_id in problem_ids:
            self.initialize_problem_stats(problem_id)

    def update_problem_stats(self, problem_id: str, submission: 'Submission',
                           passed_cases: int = 0, total_cases: int = 0,
                           is_first_ac: bool = False) -> None:
        """Update statistics for a specific problem after a submission"""
        self.initialize_problem_stats(problem_id)

        stats = self.problem_stats[problem_id]
        stats["submission_count"] += 1
        stats["penalty"] += submission.penalty
        stats["last_submission_at"] = submission.submitted_at.isoformat()
        stats["language_used"] = submission.language

        if stats["first_submission_at"] is None:
            stats["first_submission_at"] = submission.submitted_at.isoformat()

        if total_cases > 0:
            stats["passed_test_cases"] = max(stats["passed_test_cases"], passed_cases)
            stats["total_test_cases"] = total_cases

        if submission.pass_score > stats["best_score"]:
            stats["best_score"] = submission.pass_score

        if submission.status == SubmissionStatus.ACCEPTED:
            stats["solved"] = True
            if stats["solved_at"] is None:
                stats["solved_at"] = submission.submitted_at.isoformat()
            stats["is_first_ac"] = is_first_ac
    
    def to_dict(self, include_submissions: bool = False) -> Dict:
        elapsed_time_seconds = self.get_elapsed_time_seconds()
        settled_delivery_seconds = (
            self._to_non_negative_int(self.delivery_time_seconds, 0)
            if not self.is_running
            else 0
        )
        settled_delivery_credit = (
            self._to_non_negative_float(self.delivery_time_credit, 0.0)
            if not self.is_running
            else 0.0
        )

        result = {
            "id": self.id,
            "competition_id": self.competition_id,
            "name": self.name,
            "agent_profile": self.agent_profile,
            "LLM_tokens": self.LLM_tokens,
            "hint_tokens": self.hint_tokens,
            "submission_tokens": self.submission_tokens,
            "test_tokens": self.test_tokens,
            "consumed_tokens": self.consumed_tokens,
            "limit_tokens": self.limit_tokens,
            "remaining_tokens": self.remaining_tokens,
            "lambda_value": self.lambda_value,
            "submission_count": self.submission_count,
            "accepted_count": self.accepted_count,
            "submission_penalty": self.submission_penalty,
            "problem_pass_score": self.problem_pass_score,
            "score": self.score,

            # New statistics fields
            "llm_inference_count": self.llm_inference_count,
            "first_ac_score": self.first_ac_score,
            "problem_score": self.problem_score,

            # Detailed rule-based scoring breakdown
            "bronze_score": self.bronze_score,
            "silver_score": self.silver_score,
            "gold_score": self.gold_score,
            "platinum_score": self.platinum_score,
            "bonus_score": self.bonus_score,

            # Per-problem statistics
            "problem_stats": self.problem_stats,

            # "solved_problems": self.solved_problems,
            "is_running": self.is_running,
            "termination_reason": self.termination_reason,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "terminated_at": self.terminated_at.isoformat() if self.terminated_at else None,
            "elapsed_time_seconds": elapsed_time_seconds,
            "delivery_time_seconds": settled_delivery_seconds,
            "delivery_time_multiplier": self.delivery_time_multiplier,
            "delivery_time_credit": settled_delivery_credit,
            "delivery_time_settled": (not self.is_running),
            "consumed_credit": self.get_consumed_credit(),
        }

        # if include_submissions:
        #     result["submissions"] = [s.to_dict() for s in self.submissions]

        return result


class Case:
    def __init__(
        self,
        id: str,
        input_data: str,
        expected_output: str,
        input_path: Optional[str] = None,
    ):
        self.id = id
        self.input_data = input_data
        self.expected_output = expected_output
        self.input_path = input_path
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "input_data": self.input_data,
            "expected_output": self.expected_output,
            "input_path": self.input_path,
        }





class TestResult:
    def __init__(
        self,
        test_case_id: str,
        status: SubmissionStatus,
        runtime_ms: Optional[int] = None,
        memory_kb: Optional[int] = None,
        output: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        self.test_case_id = test_case_id
        self.status = status
        self.runtime_ms = runtime_ms
        self.memory_kb = memory_kb
        self.output = output
        self.error_message = error_message
    
    def to_dict(self) -> Dict:
        return {
            "test_case_id": self.test_case_id,
            "status": self.status.value,  # Use .value for enum serialization
            "runtime_ms": self.runtime_ms,
            "memory_kb": self.memory_kb,
            "output": self.output,
            "error_message": self.error_message
        }


class Competition:
    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        max_tokens_per_participant: int = 100000,
        rules: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
        participant_count: int = 0,
        problem_count: int = 0,
    ):
        self.id = id
        self.title = title
        self.description = description
        self.max_tokens_per_participant = max_tokens_per_participant
        self.start_time = start_time
        self.end_time = end_time
        self.is_active = is_active
        self.participant_count = participant_count
        self.problem_count = problem_count
        self.rules = rules or {
            "scoring": {
                "bronze": 100,
                "silver": 200,
                "gold": 500,
                "platinum": 1000
            },
            "bonus_for_first_ac": 100,
            "penalties": {
                "WA": 10,
                "RE": 10,
                "CE": 5,
                "TLE": 10,
                "MLE": 10
            },
            "hint_tokens": {
                "level_1": 500,
                "level_2": 1000,
                "level_3": 1500
            },
            "submission_tokens": {
                "AC": 100,
                "WA": 100,
                "RE": 100,
                "CE": 100,
                "TLE": 100,
                "MLE": 100
            },
            "test_tokens": {
                "default": 50,
                "per_test_case": 0,
                "language_multipliers": {
                    "cpp": 1.0,
                    "java": 1.2,
                    "python": 1.5
                }
            },
            "lambda": 100,
            "delivery_time_multiplier": 1.0,
            "input_token_multipliers": {
            "qwen3-235b": 0.7,
            "gemini-2.5-pro": 1.25,
            "gemini-2.5-flash": 0.15,
            "deepseek-v3": 0.27,
            "deepseek-r1": 0.55,
            "kimi-k2": 1,
            "gpt-4o": 2.5,
            "gpt-4.1": 2,
            "gpt-4.1-mini": 0.4,
            "gpt-4.1-nano": 0.1,
            "gpt-4o-mini": 0.15,
            "claude-3.7-sonnet": 3,
            "claude-sonnet-4-20250514": 3,
            "grok-3-beta": 3
            },
            "output_token_multipliers": {
            "qwen3-235b": 2.8,
            "gemini-2.5-pro": 10,
            "gemini-2.5-flash": 0.6,
            "deepseek-v3": 1.1,
            "deepseek-r1": 2.19,
            "kimi-k2": 3,
            "gpt-4o": 10,
            "gpt-4.1": 8,
            "gpt-4.1-mini": 1.6,
            "gpt-4.1-nano": 0.4,
            "gpt-4o-mini": 0.6,
            "claude-3.7-sonnet": 15,
            "claude-sonnet-4-20250514": 15,
            "grok-3-beta": 15
            }
        }
    
    def to_dict(self, include_details: bool = False) -> Dict:
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "max_tokens_per_participant": self.max_tokens_per_participant,
            "rules": self.rules,
            "is_active": self.is_active,
            "participant_count": self.participant_count,
            "problem_count": self.problem_count,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
            }
        
        return result

class Problem:
    def __init__(
        self, 
        id: str, 
        title: str, 
        description: str, 
        level: Level,
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256,
        first_to_solve: Optional[str] = None,
        # test_cases: List[Case] = [],
        sample_cases: List[Case] = []
    ):
        self.id = id
        self.title = title
        self.description = description
        self.level = level
        # self.test_cases = test_cases
        self.sample_cases = sample_cases
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb
        self.first_to_solve: Optional[str] = first_to_solve  # Participant ID
        
    def to_dict(self) -> Dict:
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "level": self.level.value,  # Use .value for enum serialization
            "sample_cases": [case.to_dict() for case in self.sample_cases],
            "time_limit_ms": self.time_limit_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "first_to_solve": self.first_to_solve,
            # "test_cases": [case.to_dict() for case in self.test_cases]
        }
        return result
    
    
    def get_problem_base_score(self, competition: Competition) -> int:
        """Get the maximum possible score for a problem based on competition rules"""
        scoring_rules = competition.rules.get("scoring", {})
        return scoring_rules.get(self.level.value, 0)

    def get_problem_firstAC_bonus(self, competition: Competition) -> int:
        """Get the maximum possible score for a problem based on competition rules"""
        return competition.rules.get("bonus_for_first_ac", 100)

class Submission:
    """A submission made by a participant in a competition, corresponding to a problem"""
    def __init__(
        self,
        id: str,
        competition_id: str,
        participant_id: str,
        problem_id: str,
        code: str,
        language: str,
        submitted_at: datetime,
        status: SubmissionStatus = SubmissionStatus.PENDING,
        
        pass_score: int = 0,
        penalty: int = 0,
        submission_tokens: int = 0,
        test_results: Optional[List[TestResult]] = None,
    ):
        self.id = id
        self.competition_id = competition_id
        self.participant_id = participant_id
        self.problem_id = problem_id
        self.code = code
        self.language = language
        self.submitted_at = submitted_at
        self.status = status
        self.test_results = test_results or []
        self.pass_score = pass_score
        self.penalty = penalty
        self.submission_tokens = submission_tokens
    def calculate_penalty(self, competition: Optional[Competition] = None) -> int:
        """
        Calculate penalty based on submission status and competition rules.
        All submissions (including AC) can have penalties based on competition rules.
        If competition is not provided, returns 0.
        """
        if not competition:
            return 0
            
        penalties = competition.rules.get("penalties", {})
        
        if self.status == SubmissionStatus.ACCEPTED:
            return penalties.get("AC", 0)  # AC can have penalty too
        elif self.status == SubmissionStatus.WRONG_ANSWER:
            return penalties.get("WA", 10)
        elif self.status == SubmissionStatus.RUNTIME_ERROR:
            return penalties.get("RE", 10)
        elif self.status == SubmissionStatus.COMPILATION_ERROR:
            return penalties.get("CE", 5)
        elif self.status == SubmissionStatus.TIME_LIMIT_EXCEEDED:
            return penalties.get("TLE", 10)
        elif self.status == SubmissionStatus.MEMORY_LIMIT_EXCEEDED:
            return penalties.get("MLE", 10)
        return 0
    
    def calculate_submission_tokens(self, competition: Optional[Competition] = None) -> int:
        """
        Calculate submission tokens based on submission status and competition rules.
        If competition is not provided, returns 0.
        """
        if not competition:
            return 0
            
        submission_tokens = competition.rules.get("submission_tokens", {})
        
        if self.status == SubmissionStatus.ACCEPTED:
            return submission_tokens.get("AC", 100)
        elif self.status == SubmissionStatus.WRONG_ANSWER:
            return submission_tokens.get("WA", 100)
        elif self.status == SubmissionStatus.RUNTIME_ERROR:
            return submission_tokens.get("RE", 100)
        elif self.status == SubmissionStatus.COMPILATION_ERROR:
            return submission_tokens.get("CE", 100)
        elif self.status == SubmissionStatus.TIME_LIMIT_EXCEEDED:
            return submission_tokens.get("TLE", 100)
        elif self.status == SubmissionStatus.MEMORY_LIMIT_EXCEEDED:
            return submission_tokens.get("MLE", 100)
        return 0
    
    def to_dict(self, include_code: bool = False) -> Dict:
        result = {
            "id": self.id,
            "competition_id": self.competition_id,
            "participant_id": self.participant_id,
            "problem_id": self.problem_id,
            "language": self.language,
            "submitted_at": self.submitted_at.isoformat(),
            "status": self.status.value,  # Use .value for enum serialization
            "test_results": [tr.to_dict() for tr in self.test_results],
            "pass_score": self.pass_score,
            "penalty": self.penalty,
            "submission_tokens": self.submission_tokens
        }
        
        if include_code:
            result["code"] = self.code
            
        return result
