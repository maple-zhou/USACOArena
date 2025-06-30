from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


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
    def __init__(self, id: str, name: str, api_base_url: str, api_key: str, max_tokens: int, lambda_: int):
        print(f"[*******] API base URL: {api_base_url}")
        self.id = id
        self.name = name
        self.submissions: List[Submission] = []
        self.score = 0
        self.final_score = lambda_
        self.remaining_tokens = max_tokens
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.lambda_ = lambda_
        
    def calculate_score(self) -> None:
        """Calculate the participant's total score based on their submissions"""
        # Calculate best scores per problem
        problem_best_scores = {}
        for submission in self.submissions:
            problem_id = submission.problem_id
            if problem_id not in problem_best_scores or submission.score > problem_best_scores[problem_id]:
                problem_best_scores[problem_id] = submission.score
        
        # Calculate total penalty
        penalty = sum(submission.penalty for submission in self.submissions)
        
        # Update total score
        self.score = sum(problem_best_scores.values()) - penalty
    
    def to_dict(self, include_submissions: bool = False) -> Dict:
        result = {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "final_score": self.final_score,
            "remaining_tokens": self.remaining_tokens
        }
        
        if include_submissions:
            result["submissions"] = [s.to_dict() for s in self.submissions]
            
        return result


class TestCase:
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


class Problem:
    def __init__(
        self, 
        id: str, 
        title: str, 
        description: str, 
        level: Level,
        test_cases: List[TestCase],
        sample_cases: List[TestCase],
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256
    ):
        self.id = id
        self.title = title
        self.description = description
        self.level = level
        self.test_cases = test_cases
        self.sample_cases = sample_cases
        self.time_limit_ms = time_limit_ms
        self.memory_limit_mb = memory_limit_mb
        self.first_to_solve: Optional[str] = None  # Participant ID
        
    def to_dict(self, include_test_cases: bool = False) -> Dict:
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "level": self.level,
            "sample_cases": [case.to_dict() for case in self.sample_cases],
            "time_limit_ms": self.time_limit_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "first_to_solve": self.first_to_solve
        }
        
        if include_test_cases:
            result["test_cases"] = [case.to_dict() for case in self.test_cases]
            
        return result


class TestResult:
    def __init__(
        self,
        test_case_id: str,
        status: SubmissionStatus,
        execution_time_ms: Optional[int] = None,
        memory_used_kb: Optional[int] = None,
        output: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        self.test_case_id = test_case_id
        self.status = status
        self.execution_time_ms = execution_time_ms
        self.memory_used_kb = memory_used_kb
        self.output = output
        self.error_message = error_message
    
    def to_dict(self) -> Dict:
        return {
            "test_case_id": self.test_case_id,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "memory_used_kb": self.memory_used_kb,
            "output": self.output,
            "error_message": self.error_message
        }


class Competition:
    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        problems: List[Problem],
        participants: Optional[List[Participant]] = None,
        max_tokens_per_participant: int = 100000,
        rules: Optional[Dict[str, Any]] = None
    ):
        self.id = id
        self.title = title
        self.description = description
        self.problems = problems
        self.participants = participants or []
        self.max_tokens_per_participant = max_tokens_per_participant
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
            "input_token_multipliers": {
                "gemini-2.5-pro": 1.25,
                "gpt-4.1": 2,
                "gpt-4o": 2.5,
                "gpt-4o-mini": 0.15,
                "claude-3.7-sonnet": 3,
            },
            "output_token_multipliers": {
                "gemini-2.5-pro": 10,
                "gpt-4.1": 8,
                "gpt-4o": 10,
                "gpt-4o-mini": 0.6,
                "claude-3.7-sonnet": 15,
            }
        }
    
    def add_participant(self, participant: Participant) -> None:
        """Add a participant to the competition"""
        self.participants.append(participant)
    
    def get_participant(self, participant_id: str) -> Optional[Participant]:
        """Get a participant by ID"""
        for participant in self.participants:
            if participant.id == participant_id:
                return participant
        return None
    
    def get_problem(self, problem_id: str) -> Optional[Problem]:
        """Get a problem by ID"""
        for problem in self.problems:
            if problem.id == problem_id:
                return problem
        return None
    
    def is_active(self) -> bool:
        """Check if the competition is currently active"""
        return True
    
    def calculate_rankings(self) -> List[Dict]:
        """Calculate current rankings based on scores"""
        rankings = [participant.to_dict() for participant in self.participants]
        rankings.sort(key=lambda x: x["score"], reverse=True)
        
        for i, rank in enumerate(rankings):
            rank["rank"] = i + 1
        
        return rankings
    
    def get_problem_max_score(self, problem: Problem) -> int:
        """Get the maximum possible score for a problem based on competition rules"""
        scoring_rules = self.rules.get("scoring", {})
        return scoring_rules.get(problem.level.value, 0)
    
    def to_dict(self, include_details: bool = False) -> Dict:
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "max_tokens_per_participant": self.max_tokens_per_participant,
            "rules": self.rules,
            "is_active": self.is_active(),
            "participant_count": len(self.participants),
            "problem_count": len(self.problems)
        }
        
        if include_details:
            problems_dict = []
            for p in self.problems:
                p_dict = p.to_dict()
                p_dict["max_score"] = self.get_problem_max_score(p)
                problems_dict.append(p_dict)
            result["problems"] = problems_dict
            result["participants"] = [p.to_dict() for p in self.participants]
            result["rankings"] = self.calculate_rankings()
            
        return result


# Helper function to generate unique IDs
def generate_id() -> str:
    """Generate a unique ID for entities"""
    return str(uuid.uuid4())


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
        test_results: Optional[List[TestResult]] = None,
        score: int = 0,
        penalty: int = 0
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
        self.score = score
        self.penalty = penalty
    
    def calculate_penalty(self, competition: Optional[Competition] = None) -> int:
        """
        Calculate penalty based on submission status and competition rules.
        If competition is not provided, returns 0.
        """
        if not competition:
            return 0
            
        penalties = competition.rules.get("penalties", {})
        
        if self.status == SubmissionStatus.WRONG_ANSWER:
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
    
    def to_dict(self, include_code: bool = False) -> Dict:
        result = {
            "id": self.id,
            "competition_id": self.competition_id,
            "participant_id": self.participant_id,
            "problem_id": self.problem_id,
            "language": self.language,
            "submitted_at": self.submitted_at.isoformat(),
            "status": self.status,
            "test_results": [tr.to_dict() for tr in self.test_results],
            "score": self.score,
            "penalty": self.penalty
        }
        
        if include_code:
            result["code"] = self.code
            
        return result
