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
    def __init__(self, id: str, competition_id: str, name: str, api_base_url: str, api_key: str, limit_tokens: int, lambda_value: int):
        # Core persistent attributes
        self.id = id
        self.competition_id = competition_id
        self.name = name
        self.api_base_url = api_base_url
        self.api_key = api_key

        # Token tracking   B_token_remaining
        self.LLM_tokens = 0
        self.hint_tokens = 0
        self.submission_tokens = 0
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

        #  total_score = S_accepted_score - P_submission_count + B_token_remaining
        self.score = 0
        
        # Runtime state
        self.is_running: bool = True
        self.termination_reason: Optional[str] = None
        
    # def calculate_score(self) -> None:
    #     """Calculate the participant's total score based on the formula:
    #     score = problem_pass_score - submission_penalty + lambda_value * remaining_tokens / limit_tokens
    #     """
    #     # Calculate score using the formula
    #     self.score = self.problem_pass_score - self.submission_penalty + self.lambda_value * self.remaining_tokens / self.limit_tokens
    
    # def get_competition_state(self) -> Dict:
    #     """Get the current state of the competition"""
    #     return {
    #         "name": self.name,
    #         "remaining_tokens": self.remaining_tokens,
    #         "solved_problems": self.solved_problems,
    #         "is_running": self.is_running,
    #         "termination_reason": self.termination_reason,
    #         "score": self.score,
    #         "problem_pass_score": self.problem_pass_score
    #     }
    
    def terminate(self, reason: str) -> None:
        """Terminate the participant with a reason"""
        self.is_running = False
        self.termination_reason = reason
    
    def to_dict(self, include_submissions: bool = False) -> Dict:
        result = {
            "id": self.id,
            "competition_id": self.competition_id,
            "name": self.name,
            "LLM_tokens": self.LLM_tokens,
            "hint_tokens": self.hint_tokens,
            "submission_tokens": self.submission_tokens,
            "limit_tokens": self.limit_tokens,
            "remaining_tokens": self.remaining_tokens,
            "lambda_value": self.lambda_value,
            "submission_count": self.submission_count,
            "accepted_count": self.accepted_count,
            "submission_penalty": self.submission_penalty,
            "problem_pass_score": self.problem_pass_score,
            "score": self.score,    
            # "solved_problems": self.solved_problems,    
            "is_running": self.is_running,
            "termination_reason": self.termination_reason,
        }
        
        # if include_submissions:
        #     result["submissions"] = [s.to_dict() for s in self.submissions]
            
        return result


class Case:
    def __init__(self, id: str, input_data: str, expected_output: str):
        self.id = id
        self.input_data = input_data
        self.expected_output = expected_output
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "input_data": self.input_data,
            "expected_output": self.expected_output
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
            "lambda": 100,
            "output_token_multipliers": {
                "gemini-2.5-pro": 10,
                "gpt-4.1": 8,
                "gpt-4o": 10,
                "gpt-4o-mini": 0.6,
                "claude-3.7-sonnet": 15,
                "grok-3-beta": 15,
                "qwen3": 0.6,
                "deepseek-v3": 1.1,
                "deepseek-v3": 1
            },
            "input_token_multipliers": {
                "gemini-2.5-pro": 1.25,
                "gpt-4.1": 2,
                "gpt-4o": 2.5,
                "gpt-4o-mini": 0.15,
                "claude-3.7-sonnet": 3,
                "grok-3-beta": 3,
                "qwen3": 0.2,
                "deepseek-v3": 0.27,
                "deepseek-v3": 1
            }
        }
    
    # def add_participant(self, participant: Participant) -> None:
    #     """Add a participant to the competition"""
    #     self.participants.append(participant)
    
    # def get_participant(self, participant_id: str) -> Optional[Participant]:
    #     """Get a participant by ID"""
    #     for participant in self.participants:
    #         if participant.id == participant_id:
    #             return participant
    #     return None
    
    # def get_problem(self, problem_id: str) -> Optional[Problem]:
    #     """Get a problem by ID"""
    #     for problem in self.problems:
    #         if problem.id == problem_id:
    #             return problem
    #     return None

    
    # def calculate_rankings(self) -> List[Dict]:
    #     """Calculate current rankings based on scores"""
    #     rankings = [participant.to_dict() for participant in self.participants]
    #     rankings.sort(key=lambda x: x["score"], reverse=True)
        
    #     for i, rank in enumerate(rankings):
    #         rank["rank"] = i + 1
        
    #     return rankings
    
    
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

            #     id: str,
            # title: str,
            # description: str,
            # problems: List[Problem],
            # participants: Optional[List[Participant]] = None,
            # max_tokens_per_participant: int = 100000,
            # rules: Optional[Dict[str, Any]] = None,
            # created_at: Optional[datetime] = None
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

# class CompetitionRanking:
#     def __init__(self, participant: Participant, score: int, penalty: int):
#         self.participant = participant
#         self.score = score
#         self.penalty = penalty
    
#     def to_dict(self) -> Dict:
#         return {
#             "participant": self.participant.to_dict(),
#             "score": self.score,
#             "penalty": self.penalty
#         }