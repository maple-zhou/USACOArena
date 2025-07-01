"""
DuckDB-based data storage system for CompeteMAS.
Provides high-performance analytics and SQL querying capabilities.
"""

import duckdb
import json
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path
import gzip

from .models import (
    Competition, Participant, Problem, Submission, TestCase, TestResult, 
    SubmissionStatus, Level, generate_id
)


class DuckDBStorage:
    """
    High-performance DuckDB-based storage for competition data with analytics capabilities.
    """
    
    def __init__(self, db_path: str = "data/competemas.duckdb", backup_json: bool = True):
        self.db_path = Path(db_path)
        self.backup_json = backup_json
        self.backup_dir = self.db_path.parent / "json_backup"
        
        # Create directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.backup_json:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize DuckDB connection
        self.conn = duckdb.connect(str(self.db_path))
        
        # Create schema
        self._create_schema()
        
        # Initialize problem loader for dynamic test case loading
        # Use lazy import to avoid circular import
        self.problem_loader = None
        
        # In-memory cache for objects
        self.competitions_cache: Dict[str, Competition] = {}
        self.submissions_cache: Dict[str, Submission] = {}
    
    def _create_schema(self) -> None:
        """Create the database schema"""
        # Competitions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS competitions (
                id VARCHAR PRIMARY KEY,
                title VARCHAR NOT NULL,
                description TEXT,
                created_at TIMESTAMP,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                max_tokens_per_participant INTEGER,
                rules JSON,
                is_active BOOLEAN,
                participant_count INTEGER DEFAULT 0,
                problem_count INTEGER DEFAULT 0
            )
        """)
        
        # Problems table (test_cases removed - loaded dynamically from files)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS problems (
                id VARCHAR NOT NULL,
                competition_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                description TEXT,
                level VARCHAR,
                time_limit_ms INTEGER,
                memory_limit_mb INTEGER,
                first_to_solve VARCHAR,
                sample_cases JSON,
                PRIMARY KEY (id, competition_id),
                FOREIGN KEY (competition_id) REFERENCES competitions(id)
            )
        """)
        
        # Participants table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id VARCHAR PRIMARY KEY,
                competition_id VARCHAR NOT NULL,
                name VARCHAR NOT NULL,
                api_base_url VARCHAR,
                api_key VARCHAR,
                max_tokens INTEGER,
                lambda_value INTEGER,
                score INTEGER DEFAULT 0,
                final_score INTEGER DEFAULT 0,
                remaining_tokens INTEGER,
                submission_count INTEGER DEFAULT 0,
                accepted_count INTEGER DEFAULT 0,
                FOREIGN KEY (competition_id) REFERENCES competitions(id)
            )
        """)
        
        # Submissions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id VARCHAR PRIMARY KEY,
                competition_id VARCHAR NOT NULL,
                participant_id VARCHAR NOT NULL,
                problem_id VARCHAR NOT NULL,
                code TEXT,
                language VARCHAR,
                submitted_at TIMESTAMP,
                status VARCHAR,
                score INTEGER DEFAULT 0,
                penalty INTEGER DEFAULT 0,
                execution_time_ms INTEGER,
                memory_used_kb INTEGER,
                test_results JSON,
                FOREIGN KEY (competition_id) REFERENCES competitions(id),
                FOREIGN KEY (participant_id) REFERENCES participants(id),
                FOREIGN KEY (problem_id, competition_id) REFERENCES problems(id, competition_id)
            )
        """)
        
        # Create indexes for better performance
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_competition ON submissions(competition_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_participant ON submissions(participant_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_problem ON submissions(problem_id)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_submitted_at ON submissions(submitted_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_participants_competition ON participants(competition_id)")
    
    def _backup_to_json(self, table_name: str, data: Dict) -> None:
        """Backup data to JSON for reliability"""
        if not self.backup_json:
            return
        
        backup_file = self.backup_dir / f"{table_name}_{data.get('id', 'unknown')}.json.gz"
        with gzip.open(backup_file, 'wt', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
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
        created_at = datetime.now()
        
        competition = Competition(
            id=competition_id,
            title=title,
            description=description,
            problems=problems,
            max_tokens_per_participant=max_tokens_per_participant,
            rules=rules
        )
        competition.created_at = created_at
        
        # Insert into database
        self.conn.execute("""
            INSERT INTO competitions 
            (id, title, description, created_at, max_tokens_per_participant, rules, is_active, problem_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            competition_id, title, description, created_at, 
            max_tokens_per_participant, json.dumps(rules or {}), 
            True, len(problems)
        ])
        
        # Insert problems
        for problem in problems:
            self.conn.execute("""
                INSERT INTO problems 
                (id, competition_id, title, description, level, time_limit_ms, memory_limit_mb, 
                 sample_cases)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                problem.id, competition_id, problem.title, problem.description,
                problem.level.value, problem.time_limit_ms, problem.memory_limit_mb,
                json.dumps([tc.to_dict() for tc in getattr(problem, 'sample_cases', [])])
            ])
        
        # Cache and backup
        self.competitions_cache[competition_id] = competition
        self._backup_to_json('competition', competition.to_dict(include_details=True))
        
        return competition
    
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get competition by ID"""
        # Check cache first
        if competition_id in self.competitions_cache:
            return self.competitions_cache[competition_id]
        
        # Query competition from database
        comp_result = self.conn.execute("""
            SELECT * FROM competitions WHERE id = ?
        """, [competition_id]).fetchone()
        
        if not comp_result:
            return None
        
        # Query problems for this competition
        problems_results = self.conn.execute("""
            SELECT * FROM problems WHERE competition_id = ?
        """, [competition_id]).fetchall()
        
        # Query participants for this competition
        participants_results = self.conn.execute("""
            SELECT * FROM participants WHERE competition_id = ?
        """, [competition_id]).fetchall()
        
        # Reconstruct Problem objects
        problems = []
        for prob_row in problems_results:
            problem_id = prob_row[0]
            
            # 动态加载测试用例，而不是从数据库读取
            if self.problem_loader is None:
                # Lazy import to avoid circular import
                from ..utils.problem_loader import USACOProblemLoader
                self.problem_loader = USACOProblemLoader()
            
            loaded_problem = self.problem_loader.load_problem(problem_id)
            if loaded_problem:
                # 使用从文件加载的完整测试用例
                test_cases = loaded_problem.test_cases
                sample_cases = loaded_problem.sample_cases
            else:
                # 如果加载失败，使用空的测试用例列表
                test_cases = []
                sample_cases = []
            
            problem = Problem(
                id=problem_id,
                title=prob_row[2],
                description=prob_row[3] or "",
                level=Level(prob_row[4]) if prob_row[4] else Level.BRONZE,
                test_cases=test_cases,
                sample_cases=sample_cases,
                time_limit_ms=prob_row[5] or 1000,
                memory_limit_mb=prob_row[6] or 256
            )
            if prob_row[7]:  # first_to_solve
                problem.first_to_solve = prob_row[7]
            problems.append(problem)
        
        # Reconstruct Participant objects
        participants = []
        for part_row in participants_results:
            participant = Participant(
                id=part_row[0],
                name=part_row[2],
                api_base_url=part_row[3] or "",
                api_key=part_row[4] or "",
                max_tokens=part_row[5] or 100000,
                lambda_=part_row[6] or 100
            )
            participant.score = part_row[7] or 0
            participant.final_score = part_row[8] or 0
            participant.remaining_tokens = part_row[9] or participant.max_tokens
            participant.submissions = []  # Will be loaded on demand
            participants.append(participant)
        
        # Create Competition object
        competition = Competition(
            id=comp_result[0],
            title=comp_result[1],
            description=comp_result[2] or "",
            problems=problems,
            participants=[],  # Start with empty list
            max_tokens_per_participant=comp_result[6] or 100000,
            rules=json.loads(comp_result[7]) if comp_result[7] else {}
        )
        
        # Add participants to competition
        for participant in participants:
            competition.add_participant(participant)
        
        # Set additional attributes
        if comp_result[3]:  # created_at
            competition.created_at = comp_result[3]
        if comp_result[4]:  # start_time
            competition.start_time = comp_result[4]
        if comp_result[5]:  # end_time
            competition.end_time = comp_result[5]
        
        # Cache the competition
        self.competitions_cache[competition_id] = competition
        
        return competition
    
    def list_competitions(self, active_only: bool = False) -> List[Competition]:
        """List all competitions"""
        if active_only:
            results = self.conn.execute("""
                SELECT id FROM competitions WHERE is_active = true
            """).fetchall()
        else:
            results = self.conn.execute("""
                SELECT id FROM competitions
            """).fetchall()
        
        competitions = []
        for result in results:
            competition = self.get_competition(result[0])
            if competition:
                competitions.append(competition)
        
        return competitions

    def update_competition(self, competition: Competition) -> None:
        """Update a competition"""
        # Update competition in database
        self.conn.execute("""
            UPDATE competitions 
            SET title = ?, description = ?, max_tokens_per_participant = ?, 
                rules = ?, is_active = ?, participant_count = ?, problem_count = ?
            WHERE id = ?
        """, [
            competition.title, competition.description, competition.max_tokens_per_participant,
            json.dumps(competition.rules), competition.is_active(), 
            len(competition.participants), len(competition.problems), competition.id
        ])
        
        # Update participants
        for participant in competition.participants:
            self.conn.execute("""
                UPDATE participants 
                SET score = ?, final_score = ?, remaining_tokens = ?, 
                    submission_count = ?, accepted_count = ?
                WHERE id = ?
            """, [
                participant.score, participant.final_score, participant.remaining_tokens,
                len(participant.submissions), 
                sum(1 for s in participant.submissions if s.status == SubmissionStatus.ACCEPTED),
                participant.id
            ])
        
        # Update cache
        self.competitions_cache[competition.id] = competition
        
        # Backup
        self._backup_to_json('competition', competition.to_dict(include_details=True))




    def create_submission(self, competition_id: str, participant_id: str, 
                         problem_id: str, code: str, language: str) -> Optional[Submission]:
        """Create a new submission"""
        submission_id = generate_id()
        submitted_at = datetime.now()
        
        submission = Submission(
            id=submission_id,
            competition_id=competition_id,
            participant_id=participant_id,
            problem_id=problem_id,
            code=code,
            language=language,
            submitted_at=submitted_at,
            status=SubmissionStatus.PENDING
        )
        
        # Insert into database
        self.conn.execute("""
            INSERT INTO submissions 
            (id, competition_id, participant_id, problem_id, code, language, 
             submitted_at, status, test_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            submission_id, competition_id, participant_id, problem_id,
            code, language, submitted_at, submission.status.value,
            json.dumps([])
        ])
        
        # Cache and backup
        self.submissions_cache[submission_id] = submission
        self._backup_to_json('submission', submission.to_dict(include_code=False))
        
        return submission
    
    def update_submission(self, submission: Submission) -> None:
        """Update submission in database"""
        self.conn.execute("""
            UPDATE submissions 
            SET status = ?, score = ?, penalty = ?, execution_time_ms = ?, 
                memory_used_kb = ?, test_results = ?
            WHERE id = ?
        """, [
            submission.status.value, submission.score, submission.penalty,
            getattr(submission, 'execution_time_ms', None),
            getattr(submission, 'memory_used_kb', None),
            json.dumps([tr.to_dict() for tr in submission.test_results]),
            submission.id
        ])
        
        # Update cache
        self.submissions_cache[submission.id] = submission
    
    def get_submission(self, submission_id: str) -> Optional[Submission]:
        """Get submission by ID"""
        # Check cache first
        if submission_id in self.submissions_cache:
            return self.submissions_cache[submission_id]
        
        # Query from database
        result = self.conn.execute("""
            SELECT * FROM submissions WHERE id = ?
        """, [submission_id]).fetchone()
        
        if not result:
            return None
        
        # Reconstruct submission object
        test_results_data = json.loads(result[12]) if result[12] else []
        test_results = [
            TestResult(
                test_case_id=tr.get('test_case_id', ''),
                status=SubmissionStatus(tr.get('status', 'PENDING')),
                execution_time_ms=tr.get('execution_time_ms'),
                memory_used_kb=tr.get('memory_used_kb'),
                output=tr.get('output'),
                error_message=tr.get('error_message')
            )
            for tr in test_results_data
        ]
        
        submission = Submission(
            id=result[0],
            competition_id=result[1],
            participant_id=result[2],
            problem_id=result[3],
            code=result[4],
            language=result[5],
            submitted_at=result[6],
            status=SubmissionStatus(result[7]),
            test_results=test_results,
            score=result[8] or 0,
            penalty=result[9] or 0
        )
        
        # Set optional attributes
        if result[10]:  # execution_time_ms
            submission.execution_time_ms = result[10]
        if result[11]:  # memory_used_kb
            submission.memory_used_kb = result[11]
        
        # Cache the submission
        self.submissions_cache[submission_id] = submission
        
        return submission
    
    def list_submissions(
        self,
        competition_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        problem_id: Optional[str] = None
    ) -> List[Submission]:
        """List submissions with optional filters"""
        where_conditions = []
        params = []
        
        if competition_id:
            where_conditions.append("competition_id = ?")
            params.append(competition_id)
        
        if participant_id:
            where_conditions.append("participant_id = ?")
            params.append(participant_id)
        
        if problem_id:
            where_conditions.append("problem_id = ?")
            params.append(problem_id)
        
        query = "SELECT id FROM submissions"
        if where_conditions:
            query += " WHERE " + " AND ".join(where_conditions)
        
        results = self.conn.execute(query, params).fetchall()
        
        submissions = []
        for result in results:
            submission = self.get_submission(result[0])
            if submission:
                submissions.append(submission)
        
        return submissions
        

    def add_participant(self, competition_id: str, name: str, api_base_url: str, 
                       api_key: str, max_tokens: int, lambda_: int) -> Optional[Participant]:
        """Add participant to competition"""
        participant_id = generate_id()
        
        participant = Participant(
            id=participant_id,
            name=name,
            api_base_url=api_base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            lambda_=lambda_
        )
        
        # Insert into database
        self.conn.execute("""
            INSERT INTO participants 
            (id, competition_id, name, api_base_url, api_key, max_tokens, lambda_value, remaining_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            participant_id, competition_id, name, api_base_url, 
            api_key, max_tokens, lambda_, max_tokens
        ])
        
        # Update competition participant count
        self.conn.execute("""
            UPDATE competitions 
            SET participant_count = participant_count + 1 
            WHERE id = ?
        """, [competition_id])
        
        # Clear competition cache to force reload with new participant
        if competition_id in self.competitions_cache:
            del self.competitions_cache[competition_id]
        
        # Backup
        self._backup_to_json('participant', participant.to_dict())
        
        # Force reload the competition to ensure the new participant is included
        self.get_competition(competition_id)
        
        return participant

    def get_participant(self, competition_id: str, participant_id: str) -> Optional[Participant]:
        """Get a participant by ID"""
        competition = self.get_competition(competition_id)
        if not competition:
            print(f"[DUCKDB_STORAGE] Competition {competition_id} not found")
            return None
        
        participant = competition.get_participant(participant_id)
        if participant:
            print(f"[DUCKDB_STORAGE] Found participant: {participant.name} (ID: {participant.id})")
        else:
            print(f"[DUCKDB_STORAGE] Participant {participant_id} not found in competition {competition_id}")
            
        return participant
    


    def calculate_rankings(self, competition_id: str) -> List[Dict]:
        """Calculate rankings for a competition"""
        competition = self.get_competition(competition_id)
        if not competition:
            return []
        
        return competition.calculate_rankings()   

    # Analytics and Reporting Methods
    def get_competition_rankings(self, competition_id: str) -> List[Dict]:
        """Get competition rankings using SQL"""
        return self.conn.execute("""
            SELECT 
                p.name,
                p.score,
                p.final_score,
                p.submission_count,
                p.accepted_count,
                RANK() OVER (ORDER BY p.score DESC, p.final_score DESC) as rank
            FROM participants p
            WHERE p.competition_id = ?
            ORDER BY rank
        """, [competition_id]).fetchall()
    
    def get_submission_statistics(self, competition_id: str) -> Dict:
        """Get detailed submission statistics"""
        stats = self.conn.execute("""
            SELECT 
                COUNT(*) as total_submissions,
                COUNT(DISTINCT participant_id) as unique_participants,
                COUNT(DISTINCT problem_id) as problems_attempted,
                SUM(CASE WHEN status = 'ACCEPTED' THEN 1 ELSE 0 END) as accepted_submissions,
                AVG(score) as average_score,
                DATE_TRUNC('hour', submitted_at) as submission_hour,
                COUNT(*) as hourly_count
            FROM submissions 
            WHERE competition_id = ?
            GROUP BY submission_hour
            ORDER BY submission_hour
        """, [competition_id]).fetchall()
        
        return {
            "total_stats": stats[0] if stats else {},
            "hourly_distribution": [dict(row) for row in stats]
        }
    
    def export_competition_data(self, competition_id: str, format: str = "json") -> Union[str, Dict]:
        """Export competition data in various formats"""
        if format.lower() == "csv":
            # Export to CSV files
            self.conn.execute(f"""
                COPY (
                    SELECT * FROM competitions WHERE id = '{competition_id}'
                ) TO 'competition_{competition_id}.csv' WITH (HEADER, DELIMITER ',')
            """)
            
            self.conn.execute(f"""
                COPY (
                    SELECT * FROM submissions WHERE competition_id = '{competition_id}'
                ) TO 'submissions_{competition_id}.csv' WITH (HEADER, DELIMITER ',')
            """)
            
            return f"Data exported to CSV files"
        
        elif format.lower() == "parquet":
            # Export to Parquet (columnar format)
            self.conn.execute(f"""
                COPY (
                    SELECT * FROM submissions WHERE competition_id = '{competition_id}'
                ) TO 'submissions_{competition_id}.parquet'
            """)
            
            return f"Data exported to Parquet file"
        
        else:
            # Use the existing methods to get properly formatted data
            competition = self.get_competition(competition_id)
            submissions = self.list_submissions(competition_id=competition_id)
            
            return {
                "competition": competition.to_dict(include_details=True) if competition else {},
                "submissions": [s.to_dict(include_code=False) for s in submissions]
            }
    
    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
    
    def __del__(self):
        """Cleanup on deletion"""
        self.close()
    
    # JSONDataStorage compatibility methods
    def save_submission(self, submission: Submission) -> None:
        """Save a submission (compatibility method)"""
        self.update_submission(submission)
        # Update compatibility dict
        self.submissions_cache[submission.id] = submission
    
    def save_competition(self, competition: Competition) -> None:
        """Save a competition (compatibility method)"""
        self.update_competition(competition)
        # Update compatibility dict
        self.competitions_cache[competition.id] = competition
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage system information"""
        # Get database size
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        # Get counts
        comp_count = self.conn.execute("SELECT COUNT(*) FROM competitions").fetchone()[0]
        sub_count = self.conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        part_count = self.conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
        
        return {
            "version": 1,
            "storage_format": "duckdb",
            "database_size_bytes": db_size,
            "total_competitions": comp_count,
            "total_submissions": sub_count,
            "total_participants": part_count,
            "last_modified": datetime.now().isoformat(),
            "backup_enabled": self.backup_json
        }
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get detailed storage statistics"""
        info = self.get_storage_info()
        
        # Calculate averages
        comp_count = max(info["total_competitions"], 1)
        sub_count = max(info["total_submissions"], 1)
        
        return {
            "total_size_bytes": info["database_size_bytes"],
            "competitions_count": info["total_competitions"], 
            "submissions_count": info["total_submissions"],
            "participants_count": info["total_participants"],
            "average_competition_size": info["database_size_bytes"] / comp_count,
            "average_submission_size": info["database_size_bytes"] / sub_count,
            "last_backup": None
        }
    
    def create_backup(self, backup_name: str = None) -> str:
        """Create a backup of the current data"""
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_path = self.backup_dir / f"{backup_name}.duckdb"
        
        # Copy database file
        import shutil
        shutil.copy2(self.db_path, backup_path)
        
        print(f"DuckDB backup created: {backup_path}")
        return str(backup_path) 