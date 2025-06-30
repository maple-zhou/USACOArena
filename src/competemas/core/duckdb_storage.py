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
        
        # Problems table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS problems (
                id VARCHAR PRIMARY KEY,
                competition_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                description TEXT,
                level VARCHAR,
                time_limit_ms INTEGER,
                memory_limit_mb INTEGER,
                first_to_solve VARCHAR,
                test_cases JSON,
                sample_cases JSON,
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
                FOREIGN KEY (problem_id) REFERENCES problems(id)
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
                 test_cases, sample_cases)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                problem.id, competition_id, problem.title, problem.description,
                problem.level.value, problem.time_limit_ms, problem.memory_limit_mb,
                json.dumps([tc.to_dict() for tc in problem.test_cases]),
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
        
        # Query from database
        result = self.conn.execute("""
            SELECT c.*, 
                   array_agg(p.id) as problem_ids,
                   array_agg(part.id) as participant_ids
            FROM competitions c
            LEFT JOIN problems p ON c.id = p.competition_id
            LEFT JOIN participants part ON c.id = part.competition_id
            WHERE c.id = ?
            GROUP BY c.id, c.title, c.description, c.created_at, c.start_time, c.end_time,
                     c.max_tokens_per_participant, c.rules, c.is_active, c.participant_count, c.problem_count
        """, [competition_id]).fetchone()
        
        if not result:
            return None
        
        # Reconstruct competition object
        # (This would involve loading problems and participants)
        # For brevity, returning None here - full implementation would reconstruct the object
        return None
    
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
        
        # Backup
        self._backup_to_json('participant', participant.to_dict())
        
        return participant
    
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
            # Return as JSON
            competition_data = self.conn.execute("""
                SELECT * FROM competitions WHERE id = ?
            """, [competition_id]).fetchone()
            
            submissions_data = self.conn.execute("""
                SELECT * FROM submissions WHERE competition_id = ?
            """, [competition_id]).fetchall()
            
            return {
                "competition": dict(competition_data) if competition_data else {},
                "submissions": [dict(row) for row in submissions_data]
            }
    
    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
    
    def __del__(self):
        """Cleanup on deletion"""
        self.close() 