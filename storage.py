import os
import json
import pickle
from typing import Dict, List, Optional, Any
from datetime import datetime
from models import Competition, Participant, Problem, Submission, TestCase, TestResult, SubmissionStatus, generate_id


class DataStorage:
    """
    A simple file-based data storage system for the competition.
    In a production environment, this would be replaced with a proper database.
    """
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.competitions: Dict[str, Competition] = {}
        self.submissions: Dict[str, Submission] = {}
        
        # Create data directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "competitions"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "submissions"), exist_ok=True)
        
        # Try to load existing data
        self._load_data()
    
    def _load_data(self) -> None:
        """Load existing data from the data directory"""
        # Load competitions
        competitions_dir = os.path.join(self.data_dir, "competitions")
        for filename in os.listdir(competitions_dir):
            if filename.endswith(".pickle"):
                with open(os.path.join(competitions_dir, filename), "rb") as f:
                    competition = pickle.load(f)
                    self.competitions[competition.id] = competition
        
        # Load submissions
        submissions_dir = os.path.join(self.data_dir, "submissions")
        for competition_folder in os.listdir(submissions_dir):
            competition_path = os.path.join(submissions_dir, competition_folder)
            if os.path.isdir(competition_path):
                for participant_folder in os.listdir(competition_path):
                    participant_path = os.path.join(competition_path, participant_folder)
                    if os.path.isdir(participant_path):
                        for problem_folder in os.listdir(participant_path):
                            problem_path = os.path.join(participant_path, problem_folder)
                            if os.path.isdir(problem_path):
                                for filename in os.listdir(problem_path):
                                    if filename.endswith(".pickle"):
                                        with open(os.path.join(problem_path, filename), "rb") as f:
                                            submission = pickle.load(f)
                                            self.submissions[submission.id] = submission
    
    def _save_competition(self, competition: Competition) -> None:
        """Save a competition to disk"""
        filename = os.path.join(self.data_dir, "competitions", f"{competition.id}.pickle")
        with open(filename, "wb") as f:
            pickle.dump(competition, f)
    
    def _save_submission(self, submission: Submission) -> None:
        """Save a submission to disk with the new directory structure"""
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
        base_path = os.path.join(self.data_dir, "submissions")
        competition_path = os.path.join(base_path, competition_dir)
        participant_path = os.path.join(competition_path, participant_dir)
        problem_path = os.path.join(participant_path, problem_dir)
        
        os.makedirs(problem_path, exist_ok=True)
        
        # Save the submission file
        filename = os.path.join(problem_path, f"{submission.id}.pickle")
        with open(filename, "wb") as f:
            pickle.dump(submission, f)
    
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
        self.competitions[competition_id] = competition
        self._save_competition(competition)
        return competition
    
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get a competition by ID, always reading from the latest file data"""
        try:
            filename = os.path.join(self.data_dir, "competitions", f"{competition_id}.pickle")
            with open(filename, "rb") as f:
                return pickle.load(f)
        except (FileNotFoundError, pickle.UnpicklingError) as e:
            print(f"Error reading competition data: {e}")
            return None
    
    def list_competitions(self, active_only: bool = False) -> List[Competition]:
        """List all competitions, optionally only active ones"""
        if active_only:
            return [c for c in self.competitions.values() if c.is_active()]
        return list(self.competitions.values())
    
    def update_competition(self, competition: Competition) -> None:
        """Update a competition"""
        self.competitions[competition.id] = competition
        self._save_competition(competition)
    
    def add_participant(self, competition_id: str, name: str) -> Optional[Participant]:
        """Add a participant to a competition"""
        competition = self.get_competition(competition_id)
        if not competition:
            return None
        
        participant_id = generate_id()
        participant = Participant(id=participant_id, name=name)
        competition.add_participant(participant)
        self._save_competition(competition)
        return participant
    
    def get_participant(self, competition_id: str, participant_id: str) -> Optional[Participant]:
        """Get a participant by ID"""
        competition = self.get_competition(competition_id)
        if not competition:
            return None
        return competition.get_participant(participant_id)
    
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
        self._save_submission(submission)
        self._save_competition(competition)
        
        return submission
    
    def update_submission(self, submission: Submission) -> None:
        """Update a submission"""
        self.submissions[submission.id] = submission
        self._save_submission(submission)
        
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
                        self._save_submission(submission)
                    break
            
            # # Update participant's score
            # participant = competition.get_participant(submission.participant_id)
            # if participant:
            #     participant.calculate_score()
            #     self._save_competition(competition)
        return submission
    
    def get_submission(self, submission_id: str) -> Optional[Submission]:
        """Get a submission by ID"""
        return self.submissions.get(submission_id)
    
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

    def import_competition_data(self, data: Dict) -> Optional[str]:
        """Import competition data (not implemented in this simple storage)"""
        # This would be a complex operation converting dict data back to objects
        # For simplicity, we're not implementing this in the file-based storage
        return None 