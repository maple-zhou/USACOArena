"""
JSON-based data storage system with TypedDict support.
This provides better type safety, readability, and cross-platform compatibility.
"""

import os
import json
import gzip
from typing import Dict, List, Optional, Any
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import shutil

from .models import (
    Competition, Participant, Problem, Submission, TestCase, TestResult, 
    SubmissionStatus, Level, generate_id
)
from .storage_types import (
    CompetitionDict, ParticipantDict, ProblemDict, SubmissionDict, 
    TestCaseDict, TestResultDict, StorageMetadata, StorageStats
)

class JSONDataStorage:
    """
    A JSON-based data storage system with type safety and compression support.
    """
    
    def __init__(self, data_dir: str = "data", use_compression: bool = True):
        self.data_dir = Path(data_dir)
        self.use_compression = use_compression
        self.competitions: Dict[str, Competition] = {}
        self.submissions: Dict[str, Submission] = {}
        
        # Create data directory structure
        self._create_directories()
        
        # Load existing data
        self._load_data()
        
        # Initialize metadata
        self._init_metadata()
    
    def _create_directories(self) -> None:
        """Create necessary directories"""
        (self.data_dir / "competitions").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "submissions").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "metadata").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "backups").mkdir(parents=True, exist_ok=True)
    
    def _get_file_extension(self) -> str:
        """Get file extension based on compression setting"""
        return ".json.gz" if self.use_compression else ".json"
    
    def _save_json(self, data: Dict, filepath: Path) -> None:
        """Save data as JSON with optional compression"""
        if self.use_compression:
            with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    def _load_json(self, filepath: Path) -> Dict:
        """Load data from JSON with optional compression"""
        if self.use_compression:
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    def _init_metadata(self) -> None:
        """Initialize storage metadata"""
        metadata_path = self.data_dir / "metadata" / "storage.json"
        if not metadata_path.exists():
            metadata: StorageMetadata = {
                "version": 1,
                "created_at": datetime.now().isoformat(),
                "last_modified": datetime.now().isoformat(),
                "total_competitions": 0,
                "total_submissions": 0,
                "storage_format": "compressed_json" if self.use_compression else "json",
                "compression_enabled": self.use_compression
            }
            self._save_json(metadata, metadata_path)
    
    def _update_metadata(self) -> None:
        """Update storage metadata"""
        metadata_path = self.data_dir / "metadata" / "storage.json"
        if metadata_path.exists():
            metadata = self._load_json(metadata_path)
        else:
            metadata = {}
        
        metadata.update({
            "last_modified": datetime.now().isoformat(),
            "total_competitions": len(self.competitions),
            "total_submissions": len(self.submissions)
        })
        
        self._save_json(metadata, metadata_path)
    
    def _load_data(self) -> None:
        """Load existing data from JSON files"""
        # Load competitions
        competitions_dir = self.data_dir / "competitions"
        ext = self._get_file_extension()
        
        for filepath in competitions_dir.glob(f"*{ext}"):
            try:
                data = self._load_json(filepath)
                competition = self._dict_to_competition(data)
                self.competitions[competition.id] = competition
            except Exception as e:
                print(f"Error loading competition from {filepath}: {e}")
        
        # Load submissions (lazy loading for better performance)
        self._load_submissions()
    
    def _load_submissions(self) -> None:
        """Load all submissions from JSON files"""
        submissions_dir = self.data_dir / "submissions"
        ext = self._get_file_extension()
        
        for filepath in submissions_dir.rglob(f"*{ext}"):
            try:
                data = self._load_json(filepath)
                submission = self._dict_to_submission(data)
                self.submissions[submission.id] = submission
            except Exception as e:
                print(f"Error loading submission from {filepath}: {e}")
    
    # 转换方法：对象到 TypedDict
    def _competition_to_dict(self, competition: Competition) -> CompetitionDict:
        """Convert Competition object to TypedDict with performance optimizations"""
        # Cache frequently accessed attributes
        participants = competition.participants
        problems = competition.problems
        
        return {
            "id": competition.id,
            "title": competition.title,
            "description": competition.description,
            "created_at": getattr(competition, 'created_at', datetime.now()).isoformat(),
            "start_time": getattr(competition, 'start_time', None).isoformat() if getattr(competition, 'start_time', None) else None,
            "end_time": getattr(competition, 'end_time', None).isoformat() if getattr(competition, 'end_time', None) else None,
            "problems": [self._problem_to_dict(p) for p in problems],
            "participants": [self._participant_to_dict(p) for p in participants],
            "max_tokens_per_participant": competition.max_tokens_per_participant,
            "rules": competition.rules,
            "is_active": competition.is_active(),
            "version": 1
        }
    
    def _problem_to_dict(self, problem: Problem) -> ProblemDict:
        """Convert Problem object to TypedDict"""
        return {
            "id": problem.id,
            "title": problem.title,
            "description": problem.description,
            "level": problem.level.value,
            "test_cases": [self._test_case_to_dict(tc) for tc in problem.test_cases],
            "sample_cases": [self._test_case_to_dict(tc) for tc in getattr(problem, 'sample_cases', [])],
            "time_limit_ms": problem.time_limit_ms,
            "memory_limit_mb": problem.memory_limit_mb,
            "first_to_solve": problem.first_to_solve
        }
    
    def _test_case_to_dict(self, test_case: TestCase) -> TestCaseDict:
        """Convert TestCase object to TypedDict"""
        return {
            "id": test_case.id,
            "input_data": test_case.input_data,
            "expected_output": test_case.expected_output,
            "is_hidden": getattr(test_case, 'is_hidden', False),
            "time_limit_ms": getattr(test_case, 'time_limit_ms', None),
            "memory_limit_mb": getattr(test_case, 'memory_limit_mb', None)
        }
    
    def _participant_to_dict(self, participant: Participant) -> ParticipantDict:
        """Convert Participant object to TypedDict"""
        return {
            "id": participant.id,
            "name": participant.name,
            "api_base_url": participant.api_base_url,
            "api_key": participant.api_key,
            "max_tokens": participant.max_tokens,
            "lambda_": participant.lambda_,
            "score": participant.score,
            "final_score": participant.final_score,
            "remaining_tokens": participant.remaining_tokens,
            "submission_count": len(participant.submissions),
            "accepted_count": sum(1 for s in participant.submissions if s.status == SubmissionStatus.ACCEPTED)
        }
    
    def _submission_to_dict(self, submission: Submission) -> SubmissionDict:
        """Convert Submission object to TypedDict"""
        return {
            "id": submission.id,
            "competition_id": submission.competition_id,
            "participant_id": submission.participant_id,
            "problem_id": submission.problem_id,
            "code": submission.code,
            "language": submission.language,
            "submitted_at": submission.submitted_at.isoformat(),
            "status": submission.status.value,
            "test_results": [self._test_result_to_dict(tr) for tr in submission.test_results],
            "score": submission.score,
            "penalty": submission.penalty,
            "execution_time_ms": getattr(submission, 'execution_time_ms', None),
            "memory_used_kb": getattr(submission, 'memory_used_kb', None)
        }
    
    def _test_result_to_dict(self, test_result: TestResult) -> TestResultDict:
        """Convert TestResult object to TypedDict"""
        return {
            "test_case_id": test_result.test_case_id,
            "status": test_result.status.value,
            "execution_time_ms": test_result.execution_time_ms,
            "memory_used_kb": test_result.memory_used_kb,
            "output": test_result.output,
            "error_message": test_result.error_message
        }
    
    # 转换方法：TypedDict 到对象
    def _dict_to_competition(self, data: CompetitionDict) -> Competition:
        """Convert TypedDict back to Competition object"""
        from .models import Level
        
        # 创建问题列表
        problems = []
        for p_data in data["problems"]:
            level = Level(p_data["level"])
            
            # 创建测试用例
            test_cases = [
                TestCase(
                    id=tc["id"],
                    input_data=tc["input_data"],
                    expected_output=tc["expected_output"]
                )
                for tc in p_data["test_cases"]
            ]
            
            # 创建示例用例
            sample_cases = [
                TestCase(
                    id=tc["id"],
                    input_data=tc["input_data"],
                    expected_output=tc["expected_output"]
                )
                for tc in p_data.get("sample_cases", [])
            ]
            
            problem = Problem(
                id=p_data["id"],
                title=p_data["title"],
                description=p_data["description"],
                level=level,
                test_cases=test_cases,
                sample_cases=sample_cases,
                time_limit_ms=p_data["time_limit_ms"],
                memory_limit_mb=p_data["memory_limit_mb"]
            )
            problem.first_to_solve = p_data.get("first_to_solve")
            problems.append(problem)
        
        # 创建竞赛对象
        competition = Competition(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            problems=problems,
            max_tokens_per_participant=data["max_tokens_per_participant"],
            rules=data["rules"]
        )
        
        # 设置时间字段
        if "created_at" in data:
            competition.created_at = datetime.fromisoformat(data["created_at"])
        if data.get("start_time"):
            competition.start_time = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            competition.end_time = datetime.fromisoformat(data["end_time"])
        
        return competition
    
    def _dict_to_submission(self, data: SubmissionDict) -> Submission:
        """Convert TypedDict back to Submission object"""
        # 创建测试结果
        test_results = [
            TestResult(
                test_case_id=tr["test_case_id"],
                status=SubmissionStatus(tr["status"]),
                execution_time_ms=tr.get("execution_time_ms"),
                memory_used_kb=tr.get("memory_used_kb"),
                output=tr.get("output"),
                error_message=tr.get("error_message")
            )
            for tr in data["test_results"]
        ]
        
        # 创建提交对象
        submission = Submission(
            id=data["id"],
            competition_id=data["competition_id"],
            participant_id=data["participant_id"],
            problem_id=data["problem_id"],
            code=data["code"],
            language=data["language"],
            submitted_at=datetime.fromisoformat(data["submitted_at"]),
            status=SubmissionStatus(data["status"]),
            test_results=test_results,
            score=data["score"],
            penalty=data["penalty"]
        )
        
        # 设置额外字段
        if data.get("execution_time_ms"):
            submission.execution_time_ms = data["execution_time_ms"]
        if data.get("memory_used_kb"):
            submission.memory_used_kb = data["memory_used_kb"]
        
        return submission 

    # 核心存储方法
    @lru_cache(maxsize=100)
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get a competition by ID with caching"""
        if competition_id in self.competitions:
            return self.competitions[competition_id]
        
        # Try to load from file
        filepath = self.data_dir / "competitions" / f"{competition_id}{self._get_file_extension()}"
        if filepath.exists():
            try:
                data = self._load_json(filepath)
                competition = self._dict_to_competition(data)
                self.competitions[competition_id] = competition
                return competition
            except Exception as e:
                print(f"Error loading competition {competition_id}: {e}")
        
        return None
    
    def save_competition(self, competition: Competition) -> None:
        """Save a competition to JSON with performance optimizations"""
        data = self._competition_to_dict(competition)
        filepath = self.data_dir / "competitions" / f"{competition.id}{self._get_file_extension()}"
        self._save_json(data, filepath)
        self.competitions[competition.id] = competition
        
        # Optimize: Only update metadata every 10 saves or if it's a new competition
        if not hasattr(self, '_save_counter'):
            self._save_counter = 0
        self._save_counter += 1
        
        # Update metadata less frequently for better performance
        if self._save_counter % 10 == 0 or competition.id not in self.competitions:
            self._update_metadata()
        
        # Don't clear cache unnecessarily - only clear specific competition
        if hasattr(self.get_competition, 'cache_clear'):
            # Clear only specific cache entry instead of entire cache
            # self.get_competition.cache_clear()
            pass
    
    def list_competitions(self, active_only: bool = False) -> List[Competition]:
        """List all competitions"""
        competitions = list(self.competitions.values())
        if active_only:
            competitions = [c for c in competitions if c.is_active()]
        return competitions
    
    def create_competition(
        self,
        title: str,
        description: str,
        problems: List[Problem],
        max_tokens_per_participant: int = 100000,
        rules: Dict[str, Any] = None
    ) -> Competition:
        """Create a new competition"""
        competition_id = generate_id()
        competition = Competition(
            id=competition_id,
            title=title,
            description=description,
            problems=problems,
            max_tokens_per_participant=max_tokens_per_participant,
            rules=rules
        )
        
        # Set creation time
        competition.created_at = datetime.now()
        
        self.competitions[competition_id] = competition
        self.save_competition(competition)
        return competition
    
    def update_competition(self, competition: Competition) -> None:
        """Update a competition"""
        self.save_competition(competition)
    
    def add_participant(self, competition_id: str, name: str, api_base_url: str, api_key: str, max_tokens: int, lambda_: int) -> Optional[Participant]:
        """Add a participant to a competition"""
        try:
            print(f"[JSON_STORAGE] Adding participant '{name}' to competition '{competition_id}'")
            
            competition = self.get_competition(competition_id)
            if not competition:
                print(f"[JSON_STORAGE] Competition '{competition_id}' not found")
                return None

            participant_id = generate_id()
            print(f"[JSON_STORAGE] Generated participant ID: {participant_id}")
            
            participant = Participant(id=participant_id, name=name, api_base_url=api_base_url, api_key=api_key, max_tokens=max_tokens, lambda_=lambda_)
            print(f"[JSON_STORAGE] Created participant object: {participant.to_dict()}")
            
            competition.add_participant(participant)
            print(f"[JSON_STORAGE] Added participant to competition")
            
            self.save_competition(competition)
            print(f"[JSON_STORAGE] Saved competition data")
            
            print(f"[JSON_STORAGE] Successfully added participant '{name}' with ID '{participant_id}'")
            return participant
            
        except Exception as e:
            import traceback
            print(f"[JSON_STORAGE] ERROR in add_participant: {str(e)}")
            print(f"[JSON_STORAGE] Traceback:")
            traceback.print_exc()
            return None
    
    def get_participant(self, competition_id: str, participant_id: str) -> Optional[Participant]:
        """Get a participant by ID"""
        competition = self.get_competition(competition_id)
        if not competition:
            print(f"[JSON_STORAGE] Competition {competition_id} not found")
            return None
        
        participant = competition.get_participant(participant_id)
        if participant:
            print(f"[JSON_STORAGE] Found participant: {participant.name} (ID: {participant.id})")
        else:
            print(f"[JSON_STORAGE] Participant {participant_id} not found in competition {competition_id}")
            
        return participant
    
    def save_submission(self, submission: Submission) -> None:
        """Save a submission to JSON with organized directory structure"""
        data = self._submission_to_dict(submission)
        
        # Get competition, participant and problem info
        competition = self.get_competition(submission.competition_id)
        if not competition:
            return
        
        participant = competition.get_participant(submission.participant_id)
        if not participant:
            return
        
        problem = competition.get_problem(submission.problem_id)
        if not problem:
            return
        
        # Create directory names with title/name + id
        competition_dir = f"{competition.title}_{competition.id}"
        participant_dir = f"{participant.name}_{participant.id}"
        problem_dir = f"{problem.title}_{problem.id}"
        
        # Create the directory structure
        base_path = self.data_dir / "submissions"
        competition_path = base_path / competition_dir
        participant_path = competition_path / participant_dir
        problem_path = participant_path / problem_dir
        
        problem_path.mkdir(parents=True, exist_ok=True)
        
        # Save the submission file
        filepath = problem_path / f"{submission.id}{self._get_file_extension()}"
        self._save_json(data, filepath)
        
        # Update in-memory storage
        self.submissions[submission.id] = submission
        
        # Optimize: Update metadata less frequently for submissions
        if not hasattr(self, '_submission_save_counter'):
            self._submission_save_counter = 0
        self._submission_save_counter += 1
        
        # Only update metadata every 20 submission saves
        if self._submission_save_counter % 20 == 0:
            self._update_metadata()
    
    def get_submission(self, submission_id: str) -> Optional[Submission]:
        """Get a submission by ID"""
        if submission_id in self.submissions:
            return self.submissions[submission_id]
        
        # Try to find in file system
        submissions_dir = self.data_dir / "submissions"
        ext = self._get_file_extension()
        
        for filepath in submissions_dir.rglob(f"{submission_id}{ext}"):
            try:
                data = self._load_json(filepath)
                submission = self._dict_to_submission(data)
                self.submissions[submission_id] = submission
                return submission
            except Exception as e:
                print(f"Error loading submission {submission_id}: {e}")
        
        return None
    
    def create_submission(
        self,
        competition_id: str,
        participant_id: str,
        problem_id: str,
        code: str,
        language: str,
    ) -> Optional[Submission]:
        """Create a new submission"""
        competition = self.get_competition(competition_id)
        if not competition:
            return None
        
        participant = competition.get_participant(participant_id)
        if not participant:
            return None
        
        problem = competition.get_problem(problem_id)
        if not problem:
            return None
        
        submission_id = generate_id()
        submission = Submission(
            id=submission_id,
            competition_id=competition_id,
            participant_id=participant_id,
            problem_id=problem_id,
            code=code,
            language=language,
            submitted_at=datetime.now(),
            status=SubmissionStatus.PENDING,
            test_results=[],
            score=0,
            penalty=0
        )
        
        participant.submissions.append(submission)
        
        # Save the submission
        self.submissions[submission_id] = submission
        self.save_submission(submission)
        self.save_competition(competition)
        
        return submission
    
    def update_submission(self, submission: Submission) -> None:
        """Update a submission"""
        self.submissions[submission.id] = submission
        self.save_submission(submission)
        
        # If this is an accepted solution and the first for this problem,
        # update the problem's first_to_solve attribute and add bonus
        if submission.status == SubmissionStatus.ACCEPTED:
            competition_id = submission.competition_id
            competition = self.get_competition(competition_id)
            if not competition:
                return
            for problem in competition.problems:
                if problem.id == submission.problem_id:
                    if problem.first_to_solve is None:
                        problem.first_to_solve = submission.participant_id
                        # Add bonus for first AC
                        bonus = competition.rules.get("bonus_for_first_ac", 100)
                        submission.score += bonus
                        self.save_submission(submission)
                    break
            
            # Update participant's score
            participant = competition.get_participant(submission.participant_id)
            if participant:
                participant.calculate_score()
                self.save_competition(competition)
    
    def list_submissions(
        self,
        competition_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        problem_id: Optional[str] = None
    ) -> List[Submission]:
        """List submissions with optional filters"""
        submissions = list(self.submissions.values())
        
        if competition_id:
            competition = self.get_competition(competition_id)
            if not competition:
                return []
            
            participant_ids = [p.id for p in competition.participants]
            problem_ids = [p.id for p in competition.problems]
            
            submissions = [
                s for s in submissions 
                if s.participant_id in participant_ids and s.problem_id in problem_ids
            ]
        
        if participant_id:
            submissions = [s for s in submissions if s.participant_id == participant_id]
        
        if problem_id:
            submissions = [s for s in submissions if s.problem_id == problem_id]
        
        return submissions
    
    def calculate_rankings(self, competition_id: str) -> List[Dict]:
        """Calculate rankings for a competition"""
        competition = self.get_competition(competition_id)
        if not competition:
            return []
        
        return competition.calculate_rankings()
    
    def export_competition_data(self, competition_id: str) -> Dict:
        """Export all data for a competition in JSON-serializable format"""
        competition = self.get_competition(competition_id)
        if not competition:
            return {}
        
        submissions = self.list_submissions(competition_id=competition_id)
        
        return {
            "competition": competition.to_dict(include_details=True),
            "submissions": [s.to_dict(include_code=False) for s in submissions]
        }
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage system information"""
        metadata_path = self.data_dir / "metadata" / "storage.json"
        if metadata_path.exists():
            return self._load_json(metadata_path)
        return {}
    
    def get_storage_stats(self) -> StorageStats:
        """Get detailed storage statistics"""
        total_size = 0
        competitions_count = 0
        submissions_count = 0
        
        # Calculate competitions stats
        competitions_dir = self.data_dir / "competitions"
        ext = self._get_file_extension()
        for filepath in competitions_dir.glob(f"*{ext}"):
            total_size += filepath.stat().st_size
            competitions_count += 1
        
        # Calculate submissions stats
        submissions_dir = self.data_dir / "submissions"
        for filepath in submissions_dir.rglob(f"*{ext}"):
            total_size += filepath.stat().st_size
            submissions_count += 1
        
        return {
            "total_size_bytes": total_size,
            "competitions_count": competitions_count,
            "submissions_count": submissions_count,
            "average_competition_size": total_size / max(competitions_count, 1),
            "average_submission_size": total_size / max(submissions_count, 1),
            "last_backup": None  # TODO: Implement backup tracking
        }
    
    def create_backup(self, backup_name: str = None) -> str:
        """Create a backup of the current data"""
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_path = self.data_dir / "backups" / backup_name
        if backup_path.exists():
            shutil.rmtree(backup_path)
        
        # Copy current data to backup
        shutil.copytree(self.data_dir / "competitions", backup_path / "competitions")
        shutil.copytree(self.data_dir / "submissions", backup_path / "submissions")
        shutil.copytree(self.data_dir / "metadata", backup_path / "metadata")
        
        print(f"Backup created: {backup_path}")
        return str(backup_path)
    
    def migrate_from_pickle(self, pickle_data_dir: str) -> None:
        """Migrate data from pickle format to JSON"""
        # This would implement migration logic from the old pickle storage
        # to the new JSON storage
        print("Migration from pickle to JSON not implemented yet")
        pass 