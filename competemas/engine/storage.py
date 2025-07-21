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
import threading

from ..models.models import (
    Competition, Participant, Problem, Submission, Case, TestResult, 
    SubmissionStatus, Level, generate_id
)
from .judge import Judge
import requests
from ..utils.logger_config import get_logger

logger = get_logger("storage")

class DuckDBStorage:
    """
    High-performance DuckDB-based storage for competition data with analytics capabilities.
    """
    
    def __init__(self, db_path: str = "data/competemas.duckdb", backup_json: bool = True):
        logger.info(f"Initializing DuckDB storage at {db_path}")
        self.db_path = Path(db_path)
        self.backup_json = backup_json
        self.backup_dir = self.db_path.parent / "json_backup"
        
        # Create directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.backup_json:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Created backup directory for JSON files")
        
        # Check if the database file already exists before we establish a connection,
        # as duckdb.connect() creates the file if it's missing.
        db_exists = self.db_path.exists()
        
        # Initialize DuckDB connection management
        self._thread_local = threading.local()
        logger.debug("Initialized DuckDB connection manager")
        
        # Create schema only if the database is new.
        if not db_exists:
            logger.info(f"Database file not found at {self.db_path}, creating new schema.")
            self._create_schema()
        
        # Initialize problem loader for dynamic test case loading
        # Use lazy import to avoid circular import
        self.problem_loader = None
        
        # In-memory cache for objects
        self.competitions_cache: Dict[str, Competition] = {}
        self.submissions_cache: Dict[str, Submission] = {}
        logger.info("DuckDBStorage initialized")
    
    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """为当前线程获取或创建一个新的数据库连接"""
        if not hasattr(self._thread_local, 'conn'):
            self._thread_local.conn = duckdb.connect(str(self.db_path))
        return self._thread_local.conn

    def _create_schema(self) -> None:
        """Create the database schema"""
        conn = self._get_conn() # 获取当前线程的连接
        # Competitions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS competitions (
                id VARCHAR PRIMARY KEY,
                title VARCHAR NOT NULL,
                description TEXT,
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
        conn.execute("""
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id VARCHAR PRIMARY KEY,                    -- 参赛者唯一标识符
                competition_id VARCHAR NOT NULL,           -- 所属竞赛ID
                name VARCHAR NOT NULL,                     -- 参赛者姓名
                api_base_url VARCHAR,                      -- API基础URL
                api_key VARCHAR,                           -- API密钥
                
                LLM_tokens INTEGER DEFAULT 0,              -- LLM api调用消耗的 token数量
                hint_tokens INTEGER DEFAULT 0,             -- 获得提示消耗的token数量
                submission_tokens INTEGER DEFAULT 0,       -- submission动作消耗的token数量
                limit_tokens INTEGER DEFAULT 0,            -- 最大上限token数量
                remaining_tokens INTEGER DEFAULT 0,        -- 剩余token数量
                lambda_value INTEGER DEFAULT 0,            -- lambda参数
                
                submission_count INTEGER DEFAULT 0,        -- 提交次数
                accepted_count INTEGER DEFAULT 0,          -- 完全通过的次数

                submission_penalty INTEGER DEFAULT 0,      -- 对于一道题目，如果反复提交，每一次的penalty都要计入 
                problem_pass_score INTEGER DEFAULT 0,      -- 通过测试点的得分，对于一道题目，如果反复提交，记录最高的一次score

                score INTEGER DEFAULT 0,                   -- 总分数
                is_running BOOLEAN DEFAULT TRUE,           -- 参与者是否正在运行
                termination_reason VARCHAR(500),           -- 终止原因
                FOREIGN KEY (competition_id) REFERENCES competitions(id)
            )
        """)
        
        # Submissions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id VARCHAR PRIMARY KEY,
                competition_id VARCHAR NOT NULL,
                participant_id VARCHAR NOT NULL,
                problem_id VARCHAR NOT NULL,
                code TEXT,
                language VARCHAR,
                submitted_at TIMESTAMP,
                status VARCHAR,
                pass_score INTEGER DEFAULT 0,
                penalty INTEGER DEFAULT 0,
                submission_tokens INTEGER DEFAULT 0,
                test_results JSON,
                FOREIGN KEY (competition_id) REFERENCES competitions(id),
                FOREIGN KEY (participant_id) REFERENCES participants(id),
                FOREIGN KEY (problem_id, competition_id) REFERENCES problems(id, competition_id)
            )
        """)
        
        # Create indexes for better performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_competition ON submissions(competition_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_participant ON submissions(participant_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_problem ON submissions(problem_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submissions_submitted_at ON submissions(submitted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_participants_competition ON participants(competition_id)")
    
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
        rules: Dict[str, Any] = {}
    ) -> Competition:
        """Create a new competition"""
        competition_id = generate_id()
        start_time = datetime.now()
        end_time = None
        
        competition = Competition(
            id=competition_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            max_tokens_per_participant=max_tokens_per_participant,
            rules=rules,
            is_active=True,
            participant_count=0,
            problem_count=len(problems)
        )
        
        # Insert into database
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO competitions 
            (id, title, description, start_time, end_time, max_tokens_per_participant, rules, is_active, participant_count, problem_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            competition_id, title, description, start_time, 
            end_time, max_tokens_per_participant, json.dumps(rules or {}), 
            True, 0, len(problems)
        ])
        
        # Insert problems
        for problem in problems:
            conn.execute("""
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
        # self.competitions_cache[competition_id] = competition
        self._backup_to_json('competition', competition.to_dict())
        
        return competition
    
    def get_competition(self, competition_id: str) -> Optional[Competition]:
        """Get competition by ID"""
        conn = self._get_conn()
        # Query competition from database
        comp_result = conn.execute("""
            SELECT * FROM competitions WHERE id = ?
        """, [competition_id]).fetchone()
        
        if not comp_result:
            return None
        
        # # Query problems for this competition
        # problems_results = self.conn.execute("""
        #     SELECT * FROM problems WHERE competition_id = ?
        # """, [competition_id]).fetchall()
        
        # # Query participants for this competition
        # participants_results = self.conn.execute("""
        #     SELECT * FROM participants WHERE competition_id = ?
        # """, [competition_id]).fetchall()
        
        # # Reconstruct Problem objects
        # problems = []
        # for prob_row in problems_results:
        #     # 从数据库字段直接读取
        #     problem_id = prob_row[0]      # id
        #     title = prob_row[2]           # title
        #     description = prob_row[3] or ""  # description
        #     level_str = prob_row[4]       # level
        #     time_limit_ms = prob_row[5] or 1000  # time_limit_ms
        #     memory_limit_mb = prob_row[6] or 256  # memory_limit_mb
        #     first_to_solve = prob_row[7]  # first_to_solve
            
        #     # 解析sample_cases
        #     sample_cases = []
        #     sample_cases_json = prob_row[8]  # sample_cases
        #     if sample_cases_json:
        #         try:
        #             sample_cases_data = json.loads(sample_cases_json)
        #             for case_data in sample_cases_data:
        #                 case = Case(
        #                     id=case_data.get('id', generate_id()),
        #                     input_data=case_data.get('input_data', ''),
        #                     expected_output=case_data.get('expected_output', '')
        #                 )
        #                 sample_cases.append(case)
        #         except (json.JSONDecodeError, KeyError):
        #             # 如果JSON解析失败，使用空列表
        #             sample_cases = []
            
        #     # 确定难度等级
        #     if level_str == 'bronze':
        #         level = Level.BRONZE
        #     elif level_str == 'silver':
        #         level = Level.SILVER
        #     elif level_str == 'gold':
        #         level = Level.GOLD
        #     elif level_str == 'platinum':
        #         level = Level.PLATINUM
        #     else:
        #         level = Level.BRONZE  # 默认值
            
        #     problem = Problem(
        #         id=problem_id,
        #         title=title,
        #         description=description,
        #         level=level,
        #         time_limit_ms=time_limit_ms,
        #         memory_limit_mb=memory_limit_mb,
        #         first_to_solve=first_to_solve,
        #         sample_cases=sample_cases
        #     )
        #     problems.append(problem)
        
        # # Reconstruct Participant objects
        # participants = []
        # for part_row in participants_results:
        #     # 从数据库字段直接读取
        #     participant_id = part_row[0]      # id
        #     comp_id = part_row[1]             # competition_id
        #     name = part_row[2]                # name
        #     api_base_url = part_row[3] or ""  # api_base_url
        #     api_key = part_row[4] or ""       # api_key
        #     limit_tokens = part_row[5] or 100000  # limit_tokens
        #     lambda_value = part_row[6] or 100   # lambda_value
        #     score = part_row[7] or 0          # score
        #     score = part_row[8] or lambda_value  # score
        #     remaining_tokens = part_row[9] or limit_tokens  # remaining_tokens
            
        #     # 创建Participant对象
        #     participant = Participant(
        #         id=participant_id,
        #         competition_id=comp_id,
        #         name=name,
        #         api_base_url=api_base_url,
        #         api_key=api_key,
        #         limit_tokens=limit_tokens,
        #         lambda_value=lambda_value
        #     )
            
        #     # 设置从数据库读取的状态
        #     participant.score = score
        #     # participant.score = score
        #     participant.remaining_tokens = remaining_tokens
        #     participant.submissions = []  # 提交记录按需加载
        #     participants.append(participant)
        
        # 6. 构建Competition对象
        competition = Competition(
            id=comp_result[0],  # id
            title=comp_result[1],  # title
            description=comp_result[2] or "",  # description
            start_time=comp_result[3] or datetime.now(),  # start_time
            end_time=comp_result[4],  # end_time
            max_tokens_per_participant=comp_result[5] or 100000,  # max_tokens_per_participant
            rules=json.loads(comp_result[6]) if isinstance(comp_result[6], str) and comp_result[6] else {},  # rules
            is_active=comp_result[7] if len(comp_result) > 7 else True,  # is_active
            participant_count=comp_result[8] if len(comp_result) > 8 else 0,  # participant_count
            problem_count=comp_result[9] if len(comp_result) > 9 else 0,  # problem_count
        )
        
        # 7. 缓存并返回
        # self.competitions_cache[competition_id] = competition
        return competition
      
    def list_competitions(self, active_only: bool = False) -> List[Competition]:
        """List all competitions"""
        conn = self._get_conn()
        if active_only:
            results = conn.execute("""
                SELECT id FROM competitions WHERE is_active = true
            """).fetchall()
        else:
            results = conn.execute("""
                SELECT id FROM competitions
            """).fetchall()
        
        competitions = []
        for result in results:
            competition = self.get_competition(result[0])
            if competition:
                competitions.append(competition)
        
        return competitions

    # def update_competition(self, competition: Competition) -> None:
    #     """Update a competition"""
    #     # Get current counts from database
    #     participant_result = self.conn.execute("""
    #         SELECT COUNT(*) FROM participants WHERE competition_id = ?
    #     """, [competition.id]).fetchone()
    #     participant_count = participant_result[0] if participant_result else 0
        
    #     problem_result = self.conn.execute("""
    #         SELECT COUNT(*) FROM problems WHERE competition_id = ?
    #     """, [competition.id]).fetchone()
    #     problem_count = problem_result[0] if problem_result else 0
        
    #     # Update competition in database
    #     self.conn.execute("""
    #         UPDATE competitions 
    #         SET title = ?, description = ?, max_tokens_per_participant = ?, 
    #             rules = ?, is_active = ?, participant_count = ?, problem_count = ?
    #         WHERE id = ?
    #     """, [
    #         competition.title, competition.description, competition.max_tokens_per_participant,
    #         json.dumps(competition.rules), competition.is_active, 
    #         participant_count, problem_count, competition.id
    #     ])
        
    #     # Update cache
    #     self.competitions_cache[competition.id] = competition
        
    #     # Backup
    #     self._backup_to_json('competition', competition.to_dict())


    def create_participant(self, competition_id: str, name: str, api_base_url: str, 
                       api_key: str, limit_tokens: int, lambda_value: int) -> Optional[Participant]:
        """Add participant to competition"""
        participant_id = generate_id()
        
        participant = Participant(
            id=participant_id,
            competition_id=competition_id,
            name=name,
            api_base_url=api_base_url,
            api_key=api_key,
            limit_tokens=limit_tokens,
            lambda_value=lambda_value
        )
        
        # Insert into database
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO participants 
            (id, competition_id, name, api_base_url, api_key, 
            LLM_tokens, hint_tokens, submission_tokens, limit_tokens, remaining_tokens, lambda_value,
            submission_count, accepted_count, submission_penalty, problem_pass_score, score, is_running, termination_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            participant_id, competition_id, name, api_base_url, api_key,
            0, 0, 0, limit_tokens, limit_tokens, lambda_value,
            0, 0, 0, 0, 0, True, None
        ])
        
        # Update competition participant count
        conn.execute("""
            UPDATE competitions 
            SET participant_count = participant_count + 1 
            WHERE id = ?
        """, [competition_id])
        
        # # Clear competition cache to force reload with new participant
        # if competition_id in self.competitions_cache:
        #     del self.competitions_cache[competition_id]
        
        # Backup
        self._backup_to_json('participant', participant.to_dict())
        
        # # Force reload the competition to ensure the new participant is included
        # self.get_competition(competition_id)
        
        return participant

    def get_participant(self, competition_id: str, participant_id: str) -> Optional[Participant]:
        """Get a participant by ID"""
        self.update_participant_score(competition_id, participant_id)
        
        conn = self._get_conn()
        result = conn.execute("""
            SELECT * FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()
        
        if not result:
            logger.error(f"[DUCKDB_STORAGE] Participant {participant_id} not found in competition {competition_id}")
            return None
        
        # 从数据库字段直接读取
        participant_id = result[0]      # id
        comp_id = result[1]             # competition_id
        name = result[2]                # name
        api_base_url = result[3] or ""  # api_base_url
        api_key = result[4] or ""       # api_key
        LLM_tokens = result[5] or 0     # LLM_tokens
        hint_tokens = result[6] or 0    # hint_tokens
        submission_tokens = result[7] or 0 # submission_tokens
        limit_tokens = result[8] or 100000  # limit_tokens
        remaining_tokens = result[9] or limit_tokens  # remaining_tokens
        lambda_value = result[10] or 100   # lambda_value

        submission_count = result[11] or 0 # submission_count
        accepted_count = result[12] or 0 # accepted_count
        submission_penalty = result[13] or 0 # submission_penalty
        problem_pass_score = result[14] or 0 # problem_pass_score
        
        score = result[15] or 0          # score
        is_running = result[16] if result[16] is not None else True  # is_running
        termination_reason = result[17]  # termination_reason
        
        # 创建Participant对象
        participant = Participant(
            id=participant_id,
            competition_id=comp_id,
            name=name,
            api_base_url=api_base_url,
            api_key=api_key,
            limit_tokens=limit_tokens,
            lambda_value=lambda_value
        )
        
        # 设置从数据库读取的状态
        participant.LLM_tokens = LLM_tokens
        participant.hint_tokens = hint_tokens
        participant.submission_tokens = submission_tokens
        participant.remaining_tokens = remaining_tokens
        
        participant.submission_count = submission_count
        participant.accepted_count = accepted_count
        participant.submission_penalty = submission_penalty
        participant.problem_pass_score = problem_pass_score
        participant.score = score
        participant.is_running = is_running
        participant.termination_reason = termination_reason

        # participant.submissions = []  # 提交记录按需加载
        
        logger.debug(f"[DUCKDB_STORAGE] Found participant: {participant.name} (ID: {participant.id})")
        return participant

    def list_participants(self, competition_id: str) -> List[Participant]:
        """List all participants in a competition"""
        conn = self._get_conn()
        results = conn.execute("""
            SELECT id FROM participants WHERE competition_id = ?
        """, [competition_id]).fetchall()
        
        participants = []
        for row in results:
            participant_id = row[0]
            participant = self.get_participant(competition_id, participant_id)
            if participant:
                participants.append(participant)
        
        return participants
    
    def update_participant_running_status(self, competition_id: str, participant_id: str, is_running: bool) -> None:
        """Update participant's running status"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET is_running = ?
            WHERE competition_id = ? AND id = ?
        """, [is_running, competition_id, participant_id])

    def update_participant_score(self, competition_id: str, participant_id: str) -> None:
        """Update participant's score"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET score = problem_pass_score - submission_penalty + lambda_value * remaining_tokens / limit_tokens
            WHERE competition_id = ? AND id = ? 
        """, [competition_id, participant_id])   

    def get_problem(self, competition_id: str, problem_id: str) -> Optional[Problem]:
        """Get a problem by ID"""
        conn = self._get_conn()
        result = conn.execute("""
            SELECT * FROM problems WHERE competition_id = ? AND id = ?
        """, [competition_id, problem_id]).fetchone()
        
        if not result:
            return None
        
        # 从数据库字段直接读取
        problem_id = result[0]      # id
        title = result[2]           # title
        description = result[3] or ""  # description
        level_str = result[4]       # level
        time_limit_ms = result[5] or 1000  # time_limit_ms
        memory_limit_mb = result[6] or 256  # memory_limit_mb
        first_to_solve = result[7]  # first_to_solve
        
        # 解析sample_cases
        sample_cases = []
        sample_cases_json = result[8]  # sample_cases
        if sample_cases_json:
            try:
                sample_cases_data = json.loads(sample_cases_json)
                for case_data in sample_cases_data:
                    case = Case(
                        id=case_data.get('id', generate_id()),
                        input_data=case_data.get('input_data', ''),
                        expected_output=case_data.get('expected_output', '')
                    )
                    sample_cases.append(case)
            except (json.JSONDecodeError, KeyError):
                # 如果JSON解析失败，使用空列表
                sample_cases = []
        
        # 确定难度等级
        if level_str == 'bronze':
            level = Level.BRONZE
        elif level_str == 'silver':
            level = Level.SILVER
        elif level_str == 'gold':
            level = Level.GOLD
        elif level_str == 'platinum':
            level = Level.PLATINUM
        else:
            level = Level.BRONZE  # 默认值
        
        problem = Problem(
            id=problem_id,
            title=title,
            description=description,
            level=level,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
            first_to_solve=first_to_solve,
            sample_cases=sample_cases
        )
        
        return problem
    
    def list_problems(self, competition_id: str) -> List[Problem]:
        """List all problems in a competition"""
        conn = self._get_conn()
        results = conn.execute("""
            SELECT id FROM problems WHERE competition_id = ?
        """, [competition_id]).fetchall()
        
        problems = []
        for row in results:
            problem_id = row[0]
            problem = self.get_problem(competition_id, problem_id)
            if problem:
                problems.append(problem)
        
        return problems
   

    def _update_problem_first_to_solve(self, competition_id: str, problem_id: str, participant_id: str) -> None:
        """Update problem's first_to_solve in database"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE problems 
            SET first_to_solve = ? 
            WHERE competition_id = ? AND id = ?
        """, [participant_id, competition_id, problem_id])
    

    def create_submission(self, competition_id: str, participant_id: str, 
                         problem_id: str, code: str, language: str) -> Optional[Submission]:
        """Create a new submission with evaluation and scoring"""
        # Validate competition exists
        competition = self.get_competition(competition_id)
        if not competition:
            return None
        
        # Validate problem exists
        problem = self.get_problem(competition_id, problem_id)
        if not problem:
            return None
        
        # Create submission
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
        
        # Check if this could be first AC
        first_one = problem.first_to_solve is None
       
        # Evaluate submission and calculate score
        judge = Judge()
        submission = judge.evaluate_submission(submission, problem, competition, first_one)
        
        
        # Handle first AC bonus
        if submission.status == SubmissionStatus.ACCEPTED and first_one:
            # Update problem's first_to_solve in database
            self._update_problem_first_to_solve(competition_id, problem_id, participant_id)
        
        # logger.error(f"333333submission: {submission.pass_score}")
        # Insert submission into database
        conn = self._get_conn()
        
        
        # logger.error(f"submission: {submission.to_dict()}")
        
        # Get current best score for this problem
        current_best_score_result = conn.execute("""
            SELECT MAX(pass_score) FROM submissions 
            WHERE competition_id = ? AND participant_id = ? AND problem_id = ?
        """, [competition_id, participant_id, problem_id]).fetchone()
        # logger.error(f"00000current_best_score_result: {current_best_score_result}")
        
        if current_best_score_result is None:
            # 如果当前没有提交过，则直接加上当前提交的分数
            add_problem_pass_score = submission.pass_score
        else:
            current_best_score = current_best_score_result[0] if current_best_score_result[0] else 0
            # 如果当前提交的分数大于当前最佳分数，则加上当前提交的分数与当前最佳分数的差值
            if submission.pass_score >= current_best_score:
                add_problem_pass_score = submission.pass_score - current_best_score
                # logger.error(f"1111111add_problem_pass_score: {add_problem_pass_score}")
            else:
                add_problem_pass_score = 0
        # logger.error(f"222222add_problem_pass_score: {add_problem_pass_score}")

        # Only update problem_pass_score if new score is higher
        
        # if submission.pass_score >= current_best_score:
        #     add_problem_pass_score = submission.pass_score
        # else:
        #     add_problem_pass_score = current_best_score
        
        # logger.error(f"11111new_problem_pass_score: {add_problem_pass_score}")
        
        # Update participant statistics

        
        conn.execute("""
            UPDATE participants 
            SET submission_tokens = submission_tokens + ?,
                remaining_tokens = remaining_tokens - ?,
                submission_count = submission_count + 1,
                accepted_count = accepted_count + ?,
                submission_penalty = submission_penalty + ?,
                problem_pass_score = problem_pass_score + ?
            WHERE competition_id = ? AND id = ?
        """, [
            submission.submission_tokens, 
            submission.submission_tokens, 
            1 if submission.status == SubmissionStatus.ACCEPTED else 0,
            submission.penalty, 
            add_problem_pass_score, 
            competition_id, 
            participant_id
        ])
        
        new_remaining_tokens = conn.execute("""
            SELECT remaining_tokens FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()

        conn.execute("""
            INSERT INTO submissions 
            (id, competition_id, participant_id, problem_id, code, language, 
             submitted_at, status, pass_score, penalty, submission_tokens, test_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            submission_id, competition_id, participant_id, problem_id,
            code, language, submitted_at, submission.status.value,
            submission.pass_score, submission.penalty, submission.submission_tokens,
            json.dumps([tr.to_dict() for tr in submission.test_results])
        ])
        
        if new_remaining_tokens is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")
        
        new_remaining_tokens = new_remaining_tokens[0]    
        
        # Check if participant should be terminated due to token exhaustion
        if new_remaining_tokens <= 0:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")
        
        # Cache and backup
        # self.submissions_cache[submission_id] = submission
        self._backup_to_json('submission', submission.to_dict(include_code=False))
        # logger.error(f"endddddddddd submission: {submission.pass_score}")
        
        return submission
    
    # def _update_participant_score(self, competition_id: str, participant_id: str) -> None:
        """Update participant's score based on all their submissions"""
        # Get participant from database
        participant = self.get_participant(competition_id, participant_id)
        if participant:
            # Calculate new score based on all submissions
            submissions = self.list_submissions(
                competition_id=competition_id, 
                participant_id=participant_id
            )
            
            # Calculate best scores per problem (like in models.py calculate_score)
            problem_best_scores = {}
            total_penalty = 0
            submission_count = len(submissions)
            accepted_count = sum(1 for s in submissions if s.status == SubmissionStatus.ACCEPTED)
            
            for submission in submissions:
                problem_id = submission.problem_id
                # Track best score for each problem
                if problem_id not in problem_best_scores or submission.pass_score > problem_best_scores[problem_id]:
                    problem_best_scores[problem_id] = submission.pass_score
                
                # Accumulate penalties
                total_penalty += submission.penalty
            
            # Calculate total score: best scores per problem minus total penalties
            new_score = sum(problem_best_scores.values()) - total_penalty
            add_problem_pass_score = sum(problem_best_scores.values())
            
            # Update participant in database
            self.conn.execute("""
                UPDATE participants 
                SET score = ?, problem_pass_score = ?, submission_count = ?, submission_penalty = ?, accepted_count = ?
                WHERE competition_id = ? AND id = ?
            """, [new_score, add_problem_pass_score, submission_count, total_penalty, accepted_count, competition_id, participant_id])
    
    def list_submissions(
        self,
        competition_id: Optional[str] = None,
        participant_id: Optional[str] = None,
        problem_id: Optional[str] = None
    ) -> List[Submission]:
        """List submissions with optional filters"""
        conn = self._get_conn()
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
        
        results = conn.execute(query, params).fetchall()
        
        submissions = []
        for result in results:
            submission = self.get_submission(result[0])
            if submission:
                submissions.append(submission)
        
        return submissions

    def get_submission(self, submission_id: str, include_code: bool = False) -> Optional[Submission]:
        """Get submission by ID"""
        # Check cache first
        # if submission_id in self.submissions_cache:
        #     return self.submissions_cache[submission_id]
        
        # Query from database
        conn = self._get_conn()
        result = conn.execute("""
            SELECT * FROM submissions WHERE id = ?
        """, [submission_id]).fetchone()
        
        if not result:
            return None
        
        # Parse test results from JSON
        test_results_data = json.loads(result[11]) if result[11] else []
        test_results = [
            TestResult(
                test_case_id=tr.get('test_case_id', ''),
                status=SubmissionStatus(tr.get('status', 'PENDING')),
                runtime_ms=tr.get('runtime_ms'),
                memory_kb=tr.get('memory_kb'),
                output=tr.get('output'),
                error_message=tr.get('error_message')
            )
            for tr in test_results_data
        ]
        
        # Create submission object with correct field mapping
        submission = Submission(
            id=result[0],                    # id
            competition_id=result[1],        # competition_id
            participant_id=result[2],        # participant_id
            problem_id=result[3],            # problem_id
            code=result[4] if include_code else "",  # code
            language=result[5],              # language
            submitted_at=result[6],          # submitted_at
            status=SubmissionStatus(result[7]),  # status
            pass_score=result[8] or 0,       # pass_score
            penalty=result[9] or 0,          # penalty
            submission_tokens=result[10] or 0,  # submission_tokens
            test_results=test_results        # test_results
        )
        
        return submission

    # def update_submission(self, submission: Submission) -> None:
    #     """Update submission in database"""
    #     self.conn.execute("""
    #         UPDATE submissions 
    #         SET status = ?, pass_score = ?, penalty = ?, runtime_ms = ?, 
    #             memory_kb = ?, test_results = ?
    #         WHERE id = ?
    #     """, [
    #         submission.status.value, submission.pass_score, submission.penalty,
    #         getattr(submission, 'runtime_ms', None),
    #         getattr(submission, 'memory_kb', None),
    #         json.dumps([tr.to_dict() for tr in submission.test_results]),
    #         submission.id
    #     ])
        
    #     # Update cache
    #     self.submissions_cache[submission.id] = submission


    # def calculate_competition_rankings(self, competition_id: str) -> List[Dict]:
    #     """Calculate rankings for a competition"""
    #     # Get participants with their scores


    #     participants = self.list_participants(competition_id)
        
    #     # Convert to rankings format
    #     rankings = [participant.to_dict() for participant in participants]
    #     rankings.sort(key=lambda x: x["score"], reverse=True)
        
    #     # Add rank numbers
    #     for i, rank in enumerate(rankings):
    #         rank["rank"] = i + 1
        
    #     return rankings   

    # Analytics and Reporting Methods
    def calculate_competition_rankings(self, competition_id: str) -> List[Dict]:
        """Get competition rankings using SQL"""
        conn = self._get_conn()
        # First, update all participants' scores based on the formula:
        # score = problem_pass_score - submission_penalty + lambda_value * max(0, remaining_tokens)
        conn.execute("""
            UPDATE participants 
            SET score = problem_pass_score - submission_penalty + lambda_value * remaining_tokens / limit_tokens
            WHERE competition_id = ?
        """, [competition_id])
        
        # Then, get rankings based on updated scores
        return conn.execute("""
            SELECT 
                p.name,
                p.score,
                p.problem_pass_score,
                p.submission_count,
                p.accepted_count,
                p.submission_penalty,
                p.remaining_tokens,
                p.lambda_value,
                p.is_running,
                p.termination_reason,
                RANK() OVER (ORDER BY p.score DESC, p.problem_pass_score DESC) as rank
            FROM participants p
            WHERE p.competition_id = ?
            ORDER BY rank
        """, [competition_id]).fetchall()
    
    def get_submission_statistics(self, competition_id: str) -> Dict:
        """Get detailed submission statistics"""
        conn = self._get_conn()
        stats = conn.execute("""
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
        conn = self._get_conn()
        if format.lower() == "csv":
            # Export to CSV files
            conn.execute(f"""
                COPY (
                    SELECT * FROM competitions WHERE id = '{competition_id}'
                ) TO 'competition_{competition_id}.csv' WITH (HEADER, DELIMITER ',')
            """)
            
            conn.execute(f"""
                COPY (
                    SELECT * FROM submissions WHERE competition_id = '{competition_id}'
                ) TO 'submissions_{competition_id}.csv' WITH (HEADER, DELIMITER ',')
            """)
            
            return f"Data exported to CSV files"
        
        elif format.lower() == "parquet":
            # Export to Parquet (columnar format)
            conn.execute(f"""
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
                "competition": competition.to_dict() if competition else {},
                "submissions": [s.to_dict(include_code=False) for s in submissions]
            }
    
    def close(self) -> None:
        """Close database connection"""
        if hasattr(self._thread_local, 'conn'):
            self._thread_local.conn.close()
    
    def __enter__(self):
        """进入上下文管理器时调用"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器时调用，确保关闭连接"""
        self.close()
    
    # JSONDataStorage compatibility methods
    # def save_submission(self, submission: Submission) -> None:
    #     """Save a submission (compatibility method)"""
    #     self.update_submission(submission)
    #     # Update compatibility dict
    #     self.submissions_cache[submission.id] = submission
    
    def save_competition(self, competition: Competition) -> None:
        """Save a competition (compatibility method)"""
        # self.update_competition(competition)
        # Update compatibility dict
        self.competitions_cache[competition.id] = competition
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get storage system information"""
        conn = self._get_conn()
        # Get database size
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        # Get counts
        comp_result = conn.execute("SELECT COUNT(*) FROM competitions").fetchone()
        comp_count = comp_result[0] if comp_result else 0
        
        sub_result = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()
        sub_count = sub_result[0] if sub_result else 0
        
        part_result = conn.execute("SELECT COUNT(*) FROM participants").fetchone()
        part_count = part_result[0] if part_result else 0
        
        return {
            "version": 1,
            "storage_format": "duckdb",
            "database_size_mb": db_size / 1024 / 1024,
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
            "total_size_mb": info["database_size_mb"],
            "competitions_count": info["total_competitions"], 
            "submissions_count": info["total_submissions"],
            "participants_count": info["total_participants"],
            "average_competition_size": info["database_size_mb"] / comp_count,
            "average_submission_size": info["database_size_mb"] / sub_count,
            "last_backup": None
        }
    
    def create_backup(self, backup_name: Optional[str] = None) -> str:
        """Create a backup of the current data"""
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_path = self.backup_dir / f"{backup_name}.duckdb"
        
        # Copy database file
        import shutil
        shutil.copy2(self.db_path, backup_path)
        
        print(f"DuckDB backup created: {backup_path}")
        return str(backup_path)
    
    # Agent-related methods
    def validate_participant_api_config(self, participant: Participant) -> bool:
        """
        Validate that participant has valid API configuration.
        
        Args:
            participant: Participant object
            
        Returns:
            True if configuration is valid, False otherwise
        """
        if not participant.api_base_url:
            return False
        if not participant.api_key:
            return False
        return True
    
    def process_agent_request(
        self, 
        competition_id: str, 
        participant_id: str, 
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process agent API request and update participant token usage.
        
        Args:
            competition_id: Competition ID
            participant_id: Participant ID
            request_data: Request data containing json payload and optional parameters
            
        Returns:
            Dictionary containing response data and usage information
        """
        # Get competition and participant
        competition = self.get_competition(competition_id)
        if not competition:
            raise ValueError(f"Competition with ID {competition_id} not found")

        participant = self.get_participant(competition_id, participant_id)
        if not participant:
            raise ValueError(f"Participant with ID {participant_id} not found")

        # Validate participant API configuration
        if not self.validate_participant_api_config(participant):
            raise ValueError(f"Participant {participant_id} has invalid API configuration")

        # Build complete request using participant's API configuration
        api_path = request_data.get('api_path', '/v1/chat/completions')
        # print(f"request_data: {request_data}")
        complete_request = {
            'method': 'POST',
            'url': f"{participant.api_base_url.rstrip('/')}{api_path}",
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {participant.api_key}'
            },
            'json': request_data,
            # 'timeout': request_data.get('timeout', 30.0)
        }
        # print(f"complete_request: {complete_request['json']}")
        # Make HTTP request to LLM API
        try:
            response = requests.request(
                method=complete_request['method'],
                url=complete_request['url'],
                headers=complete_request['headers'],
                json=complete_request['json']
                # timeout=complete_request['timeout']
            )
            response.raise_for_status()
            
        except requests.exceptions.RequestException as req_err:
            raise Exception(f"LLM API request failed: {str(req_err)}")
        
        # Parse response
        try:
            result = response.json()
        except json.JSONDecodeError as json_err:
            raise Exception(f"Invalid JSON response from LLM API: {str(json_err)}")
        
        # Parse token usage
        prompt_tokens = result.get("usage", {}).get("prompt_tokens", 0)
        completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
        reasoning_tokens = result.get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens", 0)
        
        # Apply competition rules multipliers
        if competition and competition.rules:
            model_id = complete_request['json'].get("model")
            if model_id:
                # Apply input token multiplier
                input_multiplier = competition.rules.get("input_token_multipliers", {}).get(model_id)
                if input_multiplier is not None:
                    prompt_tokens = int(prompt_tokens * input_multiplier)
                
                # Apply output token multiplier
                output_multiplier = competition.rules.get("output_token_multipliers", {}).get(model_id)
                if output_multiplier is not None:
                    completion_tokens = int(completion_tokens * output_multiplier)
        
        # Calculate total LLM tokens
        llm_tokens = prompt_tokens + completion_tokens + reasoning_tokens
        
        
        
        # Update participant token usage
        # new_remaining_tokens = max(0, participant.remaining_tokens - llm_tokens)
        
        # Update database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET LLM_tokens = LLM_tokens + ?, remaining_tokens = remaining_tokens - ?   
            WHERE competition_id = ? AND id = ?
        """, [llm_tokens, llm_tokens, competition_id, participant_id])
        
        new_remaining_tokens = conn.execute("""
            SELECT remaining_tokens FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()
        
        if new_remaining_tokens is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")
        new_remaining_tokens = new_remaining_tokens[0]    

        if new_remaining_tokens <= 0:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")
        
        # logger.info(f"999999999process_agent_request: {result}")
        return {
            "content": result,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": llm_tokens,
                "remaining_tokens": new_remaining_tokens
            },
            "status_code": response.status_code
        }
    
    def process_stream_agent_request(
        self, 
        competition_id: str, 
        participant_id: str, 
        request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process streaming agent API request and update participant token usage.
        
        Args:
            competition_id: Competition ID
            participant_id: Participant ID
            request_data: Request data containing json payload and optional parameters
            
        Returns:
            Dictionary containing streaming response data and usage information
        """
        # Get competition and participant
        competition = self.get_competition(competition_id)
        if not competition:
            raise ValueError(f"Competition with ID {competition_id} not found")

        participant = self.get_participant(competition_id, participant_id)
        if not participant:
            raise ValueError(f"Participant with ID {participant_id} not found")

        # Validate participant API configuration
        if not self.validate_participant_api_config(participant):
            raise ValueError(f"Participant {participant_id} has invalid API configuration")

        # Build complete request using participant's API configuration
        api_path = request_data.get('api_path', '/v1/chat/completions')
        complete_request = {
            'method': 'POST',
            'url': f"{participant.api_base_url}{api_path}",
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {participant.api_key}'
            },
            'json': request_data.get('json', {}),
            'timeout': request_data.get('timeout', 30.0)
        }
        
        # Add streaming parameter to request
        if 'stream' not in complete_request['json']:
            complete_request['json']['stream'] = True
        
        # Make streaming HTTP request to LLM API
        try:
            response = requests.request(
                method=complete_request['method'],
                url=complete_request['url'],
                headers=complete_request['headers'],
                json=complete_request['json'],
                timeout=complete_request['timeout'],
                stream=True
            )
            response.raise_for_status()
            
        except requests.exceptions.RequestException as req_err:
            raise Exception(f"LLM API streaming request failed: {str(req_err)}")
        
        # Process streaming response
        reasoning_content = ""
        content = ""
        usage_info = None
        
        for line in response.iter_lines():
            if line:
                # Skip "data: " prefix
                if line.startswith(b"data: "):
                    line = line[6:]
                
                # Skip heartbeat message
                if line == b"[DONE]":
                    break
                
                try:
                    # Parse JSON data
                    chunk = json.loads(line.decode('utf-8'))
                    
                    # Check for usage information
                    if "usage" in chunk:
                        usage_info = chunk["usage"]
                    
                    # Extract reasoning_content and content
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            reasoning_content += delta["reasoning_content"]
                        elif "content" in delta and delta["content"] is not None:
                            content += delta["content"]
                except json.JSONDecodeError:
                    continue
        
        # Calculate tokens
        prompt_tokens = usage_info.get("prompt_tokens", 0) if usage_info else 0
        completion_tokens = usage_info.get("completion_tokens", 0) if usage_info else 0
        reasoning_tokens = usage_info.get("completion_tokens_details", {}).get("reasoning_tokens", 0) if usage_info else 0
        completion_tokens += reasoning_tokens
        
        # Apply competition rules multipliers
        if competition and competition.rules:
            model_id = complete_request['json'].get("model")
            if model_id:
                # Apply input token multiplier
                input_multiplier = competition.rules.get("input_token_multipliers", {}).get(model_id)
                if input_multiplier is not None:
                    prompt_tokens = int(prompt_tokens * input_multiplier)
                
                # Apply output token multiplier
                output_multiplier = competition.rules.get("output_token_multipliers", {}).get(model_id)
                if output_multiplier is not None:
                    completion_tokens = int(completion_tokens * output_multiplier)
        
        # Calculate total LLM tokens
        llm_tokens = prompt_tokens + completion_tokens + reasoning_tokens

        logger.critical(f"\nparticipant: {participant.name}, llm_tokens: {llm_tokens}\n")
        
        # Update participant token usage
        new_remaining_tokens = max(0, participant.remaining_tokens - llm_tokens)
        
        # Update database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET LLM_tokens = ?, remaining_tokens = remaining_tokens - ?   
            WHERE competition_id = ? AND id = ?
        """, [llm_tokens, llm_tokens, competition_id, participant_id])
        
        return {
            "reasoning_content": reasoning_content,
            "content": content,
            "usage_info": usage_info,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": llm_tokens,
                "remaining_tokens": new_remaining_tokens
            },
            "status_code": response.status_code
        }
    
    def process_hint_request(
        self, 
        competition_id: str, 
        participant_id: str, 
        hint_level: int,
        problem_id: Optional[str] = None,
        hint_knowledge: Optional[str] = None,
        problem_difficulty: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process hint request and update participant token usage.
        
        Args:
            competition_id: Competition ID
            participant_id: Participant ID
            problem_id: Problem ID
            hint_level: Hint level (0, 1, 2, or 3)

        Returns:
            Dictionary containing hint content and token usage information
        """
        # Get competition and participant
        # if hint_level == 0:
        # logger.critical(f"Hint request: {competition_id}, {participant_id}, {problem_id}, {hint_level}, {hint_knowledge}, {problem_difficulty}666666")
        competition = self.get_competition(competition_id)
        if not competition:
            logger.error(f"Competition with ID {competition_id} not found")

        participant = self.get_participant(competition_id, participant_id)
        if not participant:
            logger.error(f"Participant with ID {participant_id} not found")

        # Get problem
        if problem_id is not None:
            problem = self.get_problem(competition_id, problem_id)
            if not problem:
                logger.error(f"Problem with ID {problem_id} not found")
        else:
            problem = None

        if competition and participant:
        # Get hint token cost from competition rules
            hint_tokens_config = competition.rules.get("hint_tokens", {})
            hint_cost = hint_tokens_config.get(f"level_{hint_level}")  # Default to 500

            if hint_cost is None:
                logger.error(f"Hint cost not found for level {hint_level}")
        
            # Check if participant has enough tokens
            if participant.remaining_tokens < hint_cost:
                logger.error(f"Insufficient tokens. Required: {hint_cost}, Available: {participant.remaining_tokens}")

            # Generate hint content based on level
            hint_content = self._generate_hint_content(problem, hint_level, competition_id, hint_knowledge, problem_difficulty)
            logger.critical(f"\nNAME: {participant.name}, hint_content: {hint_content}\n")
            # Update participant token usage
            new_remaining_tokens = participant.remaining_tokens - hint_cost
        
        # Update database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET hint_tokens = hint_tokens + ?, remaining_tokens = ?
            WHERE competition_id = ? AND id = ?
        """, [hint_cost, new_remaining_tokens, competition_id, participant_id])
        
        if new_remaining_tokens <= 0:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")

        return {
            "hint_content": hint_content,
            "hint_level": hint_level,
            "tokens_cost": hint_cost,
            "remaining_tokens": new_remaining_tokens,
            "problem_id": problem_id
        }
    
    def _generate_hint_content(self, problem: Optional[Problem], hint_level: int, competition_id: str, hint_knowledge: Optional[str] = None, problem_difficulty: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate hint content based on hint level.
        
        Args:
            problem: Problem object
            hint_level: Hint level (1, 2, or 3)
            competition_id: Competition ID for excluding current problems
            
        Returns:
            Dictionary containing structured hint content
        """
        from competemas.utils.problem_loader import USACOProblemLoader
        from competemas.utils.textbook_loader import TextbookLoader
        from competemas.utils.strategy_loader import StrategyLoader
        from competemas.utils.usacoguide_loader import USACOGuideLoader
        
        problem_loader = USACOProblemLoader()
        textbook_loader = TextbookLoader()
        strategy_loader = StrategyLoader()
        guide_loader = USACOGuideLoader()
        
        # Initialize hint content
        hint_content: Dict[str, Any] = {}

        # Add current_problem for specific conditions
        # if (hint_level in [1, 2] and hint_knowledge is None) or hint_level == 3:
        if problem is not None: 
            hint_content["current_problem"] = {
                "title": problem.title,
                "id": problem.id
            }
        if hint_knowledge is not None:
            hint_content["hint_knowledge"] = hint_knowledge
        # if problem_difficulty is not None:
            # hint_content["problem_difficulty"] = problem_difficulty

        if hint_level == 0:
            # Strategy Hint: Competitive programming strategy and tips
            if strategy_loader.is_loaded():
                # Get formatted strategy content
                hint_content = strategy_loader.format_strategy_for_hint()
                
        elif hint_level == 1:
                # Basic Hint: Textbook knowledge
                hint_content["textbook_sections"] = []
                
                # Search textbook for relevant content
                if textbook_loader.is_loaded() and problem is not None:
                    # Extract key concepts from problem description
                    search_terms = self._extract_search_terms(problem.description)
                    textbook_results = textbook_loader.search_content(" ".join(search_terms), max_results=3)
                    
                    if textbook_results:
                        for result in textbook_results:
                            hint_content["textbook_sections"].append({
                                "title": result.get('title', 'Section'),
                                "content": result.get('content', '')[:300] + "...",
                                "relevance_score": result.get('relevance_score', 0.0)
                            })
                            
        elif hint_level == 2:
            hint_content["textbook_sections"] = []
            
            # Search textbook for relevant content
            if textbook_loader.is_loaded() and problem is not None:
                
                search_terms = hint_knowledge
                if search_terms is None:
                    raise ValueError("No hint knowledge provided")
                textbook_results = textbook_loader.search_content(str(search_terms), max_results=3)
                
                if textbook_results:
                    for result in textbook_results:
                        hint_content["textbook_sections"].append({
                            "title": result.get('title', 'Section'),
                            "content": result.get('content', '')[:300] + "...",
                            "relevance_score": result.get('relevance_score', 0.0)
                        })
            
        elif hint_level == 3:
            # Detailed Hint: Similar problems
            hint_content["similar_problems"] = []
            
            # Get similar problems
            try:
                # Get all available problem IDs
                all_problem_ids = problem_loader.get_problem_ids()
                if problem is not None:
                    # Get competition problems to exclude
                    competition_problems = self.list_problems(competition_id)
                    excluded_problems = set([p.id for p in competition_problems])
                    
                    # Create corpus for similarity search
                    corpus = []
                    problem_ids = []
                    for pid in all_problem_ids:
                        if pid not in excluded_problems and pid != problem.id:
                            p = problem_loader.load_problem(pid)
                            if p:
                                text = f"{p.description}\n"
                                for case in p.sample_cases:
                                    text += f"Sample Input: {case.input_data}\nSample Output: {case.expected_output}\n"
                                corpus.append(text)
                                problem_ids.append(pid)
                    
                    if corpus:
                        # Use BM25 for similarity search
                        from rank_bm25 import BM25Okapi
                        tokenized_corpus = [doc.split() for doc in corpus]
                        bm25 = BM25Okapi(tokenized_corpus)
                        
                        # Create query from current problem
                        query = f"{problem.description}\n"
                        for case in problem.sample_cases:
                            query += f"Sample Input: {case.input_data}\nSample Output: {case.expected_output}\n"
                        tokenized_query = query.split()
                        
                        # Get top similar problems
                        scores = bm25.get_scores(tokenized_query)
                        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:2]
                        
                        for idx in top_indices:
                            pid = problem_ids[idx]
                            p = problem_loader.load_problem(pid)
                            solution = problem_loader.load_solution(pid)
                            # print(f"solution: {solution}")
                            if p:
                                hint_content["similar_problems"].append({
                                    "title": p.title,
                                    "description": p.description[:200] + "...",
                                    "solution": solution,
                                    "similarity_score": scores[idx]
                                })
            except Exception as e:
                # Add error information
                hint_content["similar_problems"] = [{
                    "title": "Error",
                    "description": f"Error finding similar problems: {str(e)}",
                    "solution": "Please try again later",
                    "similarity_score": 0.0
                }]
        
        elif hint_level == 4:
            if hint_knowledge is None:
                raise ValueError("No hint knowledge provided")
            
            if problem_difficulty is None:
                raise ValueError("No problem difficulty provided")
            # first level keys
            if problem_difficulty.lower() == "bronze" or problem_difficulty.lower() == "silver" or problem_difficulty.lower() == "gold" or problem_difficulty.lower() == "platinum" or problem_difficulty.lower() == "advanced":
                try:
                    # section_key = guide_loader.get_second_level_keys(problem_difficulty)
                
                    # hint_content["example_problems"] = guide_loader.search_second_level_key(problem_difficulty, hint_knowledge)
                    
                    if hint_knowledge is not None:
                        hint_content["example_problems"] = guide_loader.search_second_level_key_similar(problem_difficulty, hint_knowledge)
                        # logger.warning(f"Hint request: {hint_content['example_problems']}77777777")
                    
                except Exception as e:
                    # Add error information
                    hint_content["example_problems"] = [{
                        "title": "Error",
                        "description": f"Error finding second level keys: {str(e)}",
                        "solution": "Please try again later",
                    }]
                    
        elif hint_level == 5:
            # Comprehensive Hint: Combined approach
            hint_content["episodic_data"] = {"similar_problems": []}
            hint_content["semantic_data"] = {"textbook_sections": []}
            hint_content["integration_points"] = [
                "Understand the Problem Type: Use textbook knowledge to identify the core concept",
                "Learn from Examples: Study similar problems to understand the approach",
                "Apply Concepts: Combine theoretical knowledge with practical examples",
                "Consider Constraints: Pay attention to time and memory limits",
                "Test Your Understanding: Try to solve the problem step by step"
            ]
            
            # Get textbook knowledge
            if textbook_loader.is_loaded() and problem is not None:
                search_terms = self._extract_search_terms(problem.description)
                textbook_results = textbook_loader.search_content(" ".join(search_terms), max_results=2)
                
                if textbook_results:
                    for result in textbook_results:
                        hint_content["semantic_data"]["textbook_sections"].append({
                            "title": result.get('title', 'Section'),
                            "content": result.get('content', '')[:200] + "...",
                            "relevance_score": result.get('score', 0.0)
                        })
            
            # Get similar problems
            try:
                all_problem_ids = problem_loader.get_problem_ids()
                competition_problems = self.list_problems(competition_id)
                excluded_problems = set([p.id for p in competition_problems])
                if problem is not None:
                
                    corpus = []
                    problem_ids = []
                    for pid in all_problem_ids:
                        if pid not in excluded_problems and pid != problem.id:
                            p = problem_loader.load_problem(pid)
                            if p:
                                text = f"{p.description}\n"
                                for case in p.sample_cases:
                                    text += f"Sample Input: {case.input_data}\nSample Output: {case.expected_output}\n"
                                corpus.append(text)
                                problem_ids.append(pid)
                    
                    if corpus:
                        from rank_bm25 import BM25Okapi
                        tokenized_corpus = [doc.split() for doc in corpus]
                        bm25 = BM25Okapi(tokenized_corpus)
                        
                        query = f"{problem.description}\n"
                        for case in problem.sample_cases:
                            query += f"Sample Input: {case.input_data}\nSample Output: {case.expected_output}\n"
                        tokenized_query = query.split()
                        
                        scores = bm25.get_scores(tokenized_query)
                        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:2]
                        
                        for idx in top_indices:
                            pid = problem_ids[idx]
                            p = problem_loader.load_problem(pid)
                            if p:
                                hint_content["episodic_data"]["similar_problems"].append({
                                    "title": p.title,
                                    "description": p.description[:150] + "...",
                                    "solution": problem_loader.load_solution(pid),
                                    "similarity_score": scores[idx]
                                })
                            
            except Exception as e:
                hint_content["episodic_data"]["similar_problems"] = [{
                    "title": "Error",
                    "description": f"Error finding similar problems: {str(e)}",
                    "solution": "Please try again later",
                    "similarity_score": 0.0
                }]
            
        else:
            raise ValueError(f"Invalid hint level: {hint_level}. Must be 1, 2, or 3.")
        
        return hint_content
    
    def _extract_search_terms(self, problem_description: str) -> List[str]:
        """
        Extract relevant search terms from problem description.
        
        Args:
            problem_description: Problem description text
            
        Returns:
            List of search terms
        """
        # Simple keyword extraction - can be improved with NLP
        keywords = [
            "algorithm", "data structure", "sorting", "searching", "dynamic programming",
            "graph", "tree", "array", "string", "number", "sequence", "pattern",
            "optimization", "greedy", "backtracking", "recursion", "iteration",
            "binary", "matrix", "linked list", "stack", "queue", "heap",
            "hash", "set", "map", "dictionary", "union find", "segment tree"
        ]
        
        found_terms = []
        description_lower = problem_description.lower()
        
        for keyword in keywords:
            if keyword in description_lower:
                found_terms.append(keyword)
        
        # Add some common programming terms
        if "sum" in description_lower or "add" in description_lower:
            found_terms.append("sum")
        if "count" in description_lower or "number" in description_lower:
            found_terms.append("counting")
        if "find" in description_lower or "search" in description_lower:
            found_terms.append("searching")
        if "maximum" in description_lower or "minimum" in description_lower:
            found_terms.append("optimization")
        
        return found_terms[:5]  # Limit to 5 terms
    
    def terminate_participant(self, competition_id: str, participant_id: str, reason: str) -> None:
        """
        Terminate a participant in a competition.
        
        Args:
            competition_id: Competition ID
            participant_id: Participant ID
            reason: Reason for termination
        """
        # Get participant to verify it exists
        participant = self.get_participant(competition_id, participant_id)
        if not participant:
            raise ValueError(f"Participant with ID {participant_id} not found in competition {competition_id}")
        
        # Update participant status in database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET is_running = ?, termination_reason = ?
            WHERE competition_id = ? AND id = ?
        """, [False, reason, competition_id, participant_id])

        # Update competition status
        conn.execute("""
            UPDATE competitions 
            SET participant_count = participant_count - 1
            WHERE id = ?
        """, [competition_id])
        
        # Log termination
        logger.warning(f"Participant {participant_id} terminated: {reason}")
        
        # Backup the updated participant data
        updated_participant = self.get_participant(competition_id, participant_id)
        if updated_participant:
            self._backup_to_json('participant', updated_participant.to_dict()) 