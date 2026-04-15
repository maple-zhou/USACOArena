"""
DuckDB-based data storage system for USACOArena.
Provides high-performance analytics and SQL querying capabilities.
"""

import duckdb
import json
import os
import time
from typing import Dict, List, Optional, Any, Tuple, Union
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

try:
    import tiktoken
except ImportError:  # pragma: no cover - optional dependency
    tiktoken = None

try:
    from anthropic_tokenizer import get_tokenizer as get_anthropic_tokenizer
except ImportError:  # pragma: no cover - optional dependency
    get_anthropic_tokenizer = None

logger = get_logger("storage")

_ANTHROPIC_TOKENIZER = None
_TIKTOKEN_ENCODINGS: Dict[str, Any] = {}


def _get_anthropic_tokenizer() -> Optional[Any]:
    """Return cached anthropic tokenizer instance if available."""
    global _ANTHROPIC_TOKENIZER
    if _ANTHROPIC_TOKENIZER is not None:
        return _ANTHROPIC_TOKENIZER

    if get_anthropic_tokenizer is None:
        return None

    try:
        _ANTHROPIC_TOKENIZER = get_anthropic_tokenizer("claude-3")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to initialize anthropic tokenizer: {exc}")
        _ANTHROPIC_TOKENIZER = None
    return _ANTHROPIC_TOKENIZER


def _get_tiktoken_encoding(model: Optional[str]) -> Optional[Any]:
    """Return cached tiktoken encoding for the provided model."""
    if tiktoken is None:
        return None

    key = model or "default"
    if key in _TIKTOKEN_ENCODINGS:
        return _TIKTOKEN_ENCODINGS[key]

    try:
        encoding = tiktoken.encoding_for_model(model) if model else None
    except Exception:
        encoding = None

    if encoding is None:
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Failed to initialize tiktoken encoding: {exc}")
            encoding = None

    _TIKTOKEN_ENCODINGS[key] = encoding
    return encoding


def _extract_text(content: Any) -> str:
    """Normalize message content into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                # OpenAI/Anthropic multi-part payloads
                if "text" in item:
                    parts.append(str(item.get("text") or ""))
                elif "content" in item:
                    parts.append(str(item.get("content") or ""))
                elif "input_text" in item:
                    parts.append(str(item.get("input_text") or ""))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        # Some providers wrap content inside nested dictionaries
        if "content" in content:
            return _extract_text(content["content"])
        if "text" in content:
            return str(content.get("text") or "")
    return str(content)


def _serialize_messages(messages: Optional[List[Dict[str, Any]]]) -> str:
    """Convert chat messages into a deterministic string for token counting."""
    if not messages:
        return ""

    serialized: List[str] = []
    for message in messages:
        role = message.get("role", "user")
        text = _extract_text(message.get("content", ""))
        serialized.append(f"{role}: {text}")
    return "\n".join(serialized)


def _extract_completion_text(response_json: Dict[str, Any]) -> str:
    """Extract generated text segments from a completion style response."""
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        texts: List[str] = []
        for choice in choices:
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict) and "content" in message:
                    texts.append(_extract_text(message["content"]))
                elif "text" in choice:
                    texts.append(_extract_text(choice.get("text")))
        combined = "\n".join(t for t in texts if t)
        if combined:
            return combined

    # Fallback to direct content field (some providers respond differently)
    if "content" in response_json:
        return _extract_text(response_json["content"])
    if "result" in response_json:
        return _extract_text(response_json["result"])
    return ""


def _deep_format_template(value: Any, substitutions: Dict[str, Any]) -> Any:
    """Recursively format string values inside dict/list templates."""
    if isinstance(value, str):
        return value.format(**substitutions)
    if isinstance(value, list):
        return [_deep_format_template(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _deep_format_template(item, substitutions)
            for key, item in value.items()
        }
    return value


def _estimate_text_tokens(text: str, model: Optional[str]) -> int:
    """Estimate token count for a block of text using available tokenizers."""
    if not text:
        return 0

    model_lower = (model or "").lower()

    if "claude" in model_lower:
        tokenizer = _get_anthropic_tokenizer()
        if tokenizer is not None:
            try:
                return len(tokenizer.encode(text))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"Anthropic tokenizer failed: {exc}")

    encoding = _get_tiktoken_encoding(model)
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"tiktoken encoding failed: {exc}")

    # Fallback to coarse character-based estimate
    return max(1, len(text) // 4)


def estimate_prompt_tokens(messages: Optional[List[Dict[str, Any]]], model: Optional[str]) -> int:
    """Estimate prompt tokens for chat messages."""
    serialized = _serialize_messages(messages)
    return _estimate_text_tokens(serialized, model)


def estimate_completion_tokens(response_json: Dict[str, Any], model: Optional[str]) -> int:
    """Estimate completion tokens using generated text."""
    completion_text = _extract_completion_text(response_json)
    return _estimate_text_tokens(completion_text, model)

class DuckDBStorage:
    """
    High-performance DuckDB-based storage for competition data with analytics capabilities.
    """
    
    def __init__(self, db_path: str = "data/competition.duckdb", backup_json: bool = True, judge: Optional[Judge] = None):
        logger.info(f"Initializing DuckDB storage at {db_path}")
        self.db_path = Path(db_path)
        self.backup_json = backup_json
        self.backup_dir = self.db_path.parent / "json_backup"
        self.judge = judge

        # Create directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.backup_json:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if the database file already exists before we establish a connection,
        db_exists = self.db_path.exists()
        
        # Initialize DuckDB connection management
        self._thread_local = threading.local()
        
        # Create schema only if the database is new.
        if not db_exists:
            logger.info(f"Database file not found at {self.db_path}, creating new schema.")
            self._create_schema()
        else:
            logger.info(f"Database file exists at {self.db_path}, checking for schema updates.")
            self._migrate_schema()
        
    
    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        """Get or create a new database connection for the current thread"""
        if not hasattr(self._thread_local, 'conn'):
            self._thread_local.conn = duckdb.connect(str(self.db_path))
        return self._thread_local.conn

    def _create_schema(self) -> None:
        """Create the database schema"""
        conn = self._get_conn() # Get connection for current thread
        # Competitions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS competitions (
                id VARCHAR PRIMARY KEY,
                title VARCHAR NOT NULL,
                description TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                max_tokens_per_participant BIGINT,
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
                id VARCHAR PRIMARY KEY,                    -- Unique identifier for participant
                competition_id VARCHAR NOT NULL,           -- Competition ID this participant belongs to
                name VARCHAR NOT NULL,                     -- Participant name
                api_base_url VARCHAR,                      -- API base URL
                api_key VARCHAR,                           -- API key
                agent_profile JSON DEFAULT '{}',           -- Agent integration profile (transport/capabilities/MCP)

                LLM_tokens BIGINT DEFAULT 0,               -- Token count consumed by LLM API calls
                hint_tokens BIGINT DEFAULT 0,              -- Token count consumed by hint requests
                submission_tokens BIGINT DEFAULT 0,        -- Token count consumed by submission actions
                test_tokens BIGINT DEFAULT 0,              -- Token count consumed by test code actions
                consumed_tokens BIGINT DEFAULT 0,          -- Total actual tokens consumed (without penalties)
                limit_tokens BIGINT DEFAULT 0,             -- Maximum token limit
                remaining_tokens BIGINT DEFAULT 0,         -- Remaining token count (includes penalties for scoring)
                lambda_value INTEGER DEFAULT 0,            -- Lambda parameter

                submission_count INTEGER DEFAULT 0,        -- Number of submissions
                accepted_count INTEGER DEFAULT 0,          -- Number of fully accepted submissions

                submission_penalty INTEGER DEFAULT 0,      -- For each problem, if submitted repeatedly, every penalty is counted
                problem_pass_score INTEGER DEFAULT 0,      -- Score for passing test cases, for each problem, if submitted repeatedly, record the highest score

                -- New statistics fields
                llm_inference_count INTEGER DEFAULT 0,     -- Total LLM inference calls
                first_ac_score INTEGER DEFAULT 0,          -- Score from being first to solve problems
                problem_score INTEGER DEFAULT 0,           -- Score from passing problems (excluding first AC bonus)

                -- Detailed rule-based scoring breakdown
                bronze_score INTEGER DEFAULT 0,            -- Score from bronze problems
                silver_score INTEGER DEFAULT 0,            -- Score from silver problems
                gold_score INTEGER DEFAULT 0,              -- Score from gold problems
                platinum_score INTEGER DEFAULT 0,          -- Score from platinum problems
                bonus_score INTEGER DEFAULT 0,             -- First AC bonuses

                -- Per-problem statistics as JSON
                problem_stats JSON DEFAULT '{}',           -- Detailed per-problem statistics

                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Participant join/start time
                terminated_at TIMESTAMP,                  -- Participant termination time
                delivery_time_seconds BIGINT DEFAULT 0,   -- Settled delivery time in seconds
                delivery_time_multiplier DOUBLE DEFAULT 1.0, -- Multiplier applied on settlement
                delivery_time_credit DOUBLE DEFAULT 0.0,  -- Settled credit deduction from delivery time

                score INTEGER DEFAULT 0,                   -- Total score
                is_running BOOLEAN DEFAULT TRUE,           -- Whether the participant is currently running
                termination_reason VARCHAR(500),           -- Reason for termination
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
                submission_tokens BIGINT DEFAULT 0,
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

    def _ensure_participants_column(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        name: str,
        definition: str,
        backfill_sql: Optional[str] = None,
    ) -> None:
        """Add a participants column when missing and optionally backfill values."""
        try:
            conn.execute(f"SELECT {name} FROM participants LIMIT 1").fetchone()
            return
        except Exception:
            pass

        try:
            conn.execute(f"ALTER TABLE participants ADD COLUMN {name} {definition}")
            logger.info(f"Added participants column: {name}")
            if backfill_sql:
                conn.execute(backfill_sql)
        except Exception as exc:
            logger.warning(f"Failed to add participants column {name}: {exc}")

    @staticmethod
    def _is_bigint_type(type_name: Optional[str]) -> bool:
        normalized = str(type_name or "").strip().upper()
        return normalized in {"BIGINT", "INT8", "LONG"}

    def _get_column_type(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        table_name: str,
        column_name: str,
    ) -> Optional[str]:
        try:
            rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        except Exception as exc:
            logger.warning(f"Failed to inspect schema for {table_name}.{column_name}: {exc}")
            return None
        wanted = str(column_name).lower()
        for row in rows:
            if len(row) >= 3 and str(row[1]).lower() == wanted:
                return str(row[2] or "")
        return None

    def _ensure_bigint_column(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        table_name: str,
        column_name: str,
    ) -> None:
        current_type = self._get_column_type(
            conn,
            table_name=table_name,
            column_name=column_name,
        )
        if current_type is None:
            logger.warning(f"Column not found for type migration: {table_name}.{column_name}")
            return
        if self._is_bigint_type(current_type):
            return

        try:
            conn.execute(
                f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE BIGINT"
            )
            logger.info(
                "Migrated column type to BIGINT: "
                f"{table_name}.{column_name} ({current_type} -> BIGINT)"
            )
        except Exception as exc:
            logger.warning(
                f"Failed to migrate {table_name}.{column_name} to BIGINT: {exc}"
            )

    def _migrate_schema(self) -> None:
        """Migrate existing database schema to add new fields."""
        conn = self._get_conn()

        self._ensure_participants_column(
            conn,
            name="test_tokens",
            definition="BIGINT DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="consumed_tokens",
            definition="BIGINT DEFAULT 0",
            backfill_sql="""
                UPDATE participants
                SET consumed_tokens = COALESCE(LLM_tokens, 0)
                    + COALESCE(hint_tokens, 0)
                    + COALESCE(submission_tokens, 0)
                    + COALESCE(test_tokens, 0)
            """,
        )
        self._ensure_participants_column(
            conn,
            name="llm_inference_count",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="first_ac_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="problem_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="bronze_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="silver_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="gold_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="platinum_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="bonus_score",
            definition="INTEGER DEFAULT 0",
        )
        self._ensure_participants_column(
            conn,
            name="problem_stats",
            definition="JSON DEFAULT '{}'",
        )
        self._ensure_participants_column(
            conn,
            name="agent_profile",
            definition="JSON DEFAULT '{}'",
        )
        self._ensure_participants_column(
            conn,
            name="started_at",
            definition="TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            backfill_sql="""
                UPDATE participants
                SET started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
            """,
        )
        self._ensure_participants_column(
            conn,
            name="terminated_at",
            definition="TIMESTAMP",
        )
        self._ensure_participants_column(
            conn,
            name="delivery_time_seconds",
            definition="BIGINT DEFAULT 0",
            backfill_sql="""
                UPDATE participants
                SET delivery_time_seconds = COALESCE(delivery_time_seconds, 0)
            """,
        )
        self._ensure_participants_column(
            conn,
            name="delivery_time_multiplier",
            definition="DOUBLE DEFAULT 1.0",
            backfill_sql="""
                UPDATE participants
                SET delivery_time_multiplier = COALESCE(delivery_time_multiplier, 1.0)
            """,
        )
        self._ensure_participants_column(
            conn,
            name="delivery_time_credit",
            definition="DOUBLE DEFAULT 0.0",
            backfill_sql="""
                UPDATE participants
                SET delivery_time_credit = COALESCE(delivery_time_credit, 0.0)
            """,
        )

        try:
            conn.execute("""
                UPDATE participants
                SET started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
            """)
            conn.execute("""
                UPDATE participants
                SET terminated_at = COALESCE(terminated_at, CURRENT_TIMESTAMP)
                WHERE is_running = FALSE AND terminated_at IS NULL
            """)
            conn.execute("""
                UPDATE participants
                SET delivery_time_multiplier = COALESCE(delivery_time_multiplier, 1.0)
            """)
        except Exception as exc:
            logger.warning(f"Failed to normalize migrated participant timing columns: {exc}")

        self._ensure_bigint_column(
            conn,
            table_name="competitions",
            column_name="max_tokens_per_participant",
        )
        for token_column in (
            "LLM_tokens",
            "hint_tokens",
            "submission_tokens",
            "test_tokens",
            "consumed_tokens",
            "limit_tokens",
            "remaining_tokens",
        ):
            self._ensure_bigint_column(
                conn,
                table_name="participants",
                column_name=token_column,
            )
        self._ensure_bigint_column(
            conn,
            table_name="submissions",
            column_name="submission_tokens",
        )

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
        
        # Backup
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


    def create_participant(self, competition_id: str, name: str, api_base_url: str,
                       api_key: str, limit_tokens: int, lambda_value: int,
                       agent_profile: Optional[Dict[str, Any]] = None) -> Optional[Participant]:
        """Add participant to competition"""
        participant_id = generate_id()
        started_at = datetime.now()
        competition = self.get_competition(competition_id)
        delivery_time_multiplier = self._get_delivery_time_multiplier(
            competition.rules if competition else None
        )

        participant = Participant(
            id=participant_id,
            competition_id=competition_id,
            name=name,
            api_base_url=api_base_url,
            api_key=api_key,
            limit_tokens=limit_tokens,
            lambda_value=lambda_value,
            agent_profile=agent_profile if isinstance(agent_profile, dict) else {},
            started_at=started_at,
            delivery_time_multiplier=delivery_time_multiplier,
        )

        # Initialize problem statistics for all problems in the competition
        problems = self.list_problems(competition_id)
        problem_ids = [problem.id for problem in problems]
        participant.initialize_all_problems_stats(problem_ids)

        # Insert into database
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO participants
            (id, competition_id, name, api_base_url, api_key, agent_profile,
            LLM_tokens, hint_tokens, submission_tokens, test_tokens, consumed_tokens, limit_tokens, remaining_tokens, lambda_value,
            submission_count, accepted_count, submission_penalty, problem_pass_score,
            llm_inference_count, first_ac_score, problem_score, bronze_score, silver_score,
            gold_score, platinum_score, bonus_score, problem_stats,
            started_at, terminated_at, delivery_time_seconds, delivery_time_multiplier, delivery_time_credit,
            score, is_running, termination_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            participant_id, competition_id, name, api_base_url, api_key,
            json.dumps(agent_profile if isinstance(agent_profile, dict) else {}),
            0, 0, 0, 0, 0, limit_tokens, limit_tokens, lambda_value,
            0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0, json.dumps(participant.problem_stats),
            started_at, None, 0, delivery_time_multiplier, 0.0,
            0, True, None
        ])
        
        # Update competition participant count
        conn.execute("""
            UPDATE competitions 
            SET participant_count = participant_count + 1 
            WHERE id = ?
        """, [competition_id])
        
        # Backup
        self._backup_to_json('participant', participant.to_dict())
        
        return participant

    def get_participant(self, competition_id: str, participant_id: str) -> Optional[Participant]:
        """Get a participant by ID"""
        conn = self._get_conn()
        result = conn.execute("""
            SELECT
                id, competition_id, name, api_base_url, api_key, COALESCE(agent_profile, '{}') as agent_profile,
                LLM_tokens, hint_tokens, submission_tokens, COALESCE(test_tokens, 0) as test_tokens, COALESCE(consumed_tokens, 0) as consumed_tokens, limit_tokens, remaining_tokens, lambda_value,
                submission_count, accepted_count, submission_penalty, problem_pass_score,
                COALESCE(llm_inference_count, 0) as llm_inference_count,
                COALESCE(first_ac_score, 0) as first_ac_score,
                COALESCE(problem_score, 0) as problem_score,
                COALESCE(bronze_score, 0) as bronze_score,
                COALESCE(silver_score, 0) as silver_score,
                COALESCE(gold_score, 0) as gold_score,
                COALESCE(platinum_score, 0) as platinum_score,
                COALESCE(bonus_score, 0) as bonus_score,
                COALESCE(problem_stats, '{}') as problem_stats,
                COALESCE(
                    problem_pass_score - submission_penalty
                    + lambda_value * (CAST(remaining_tokens AS DOUBLE) / NULLIF(CAST(limit_tokens AS DOUBLE), 0)),
                    problem_pass_score - submission_penalty
                ) AS score,
                is_running, termination_reason,
                COALESCE(started_at, CURRENT_TIMESTAMP) as started_at,
                terminated_at,
                COALESCE(delivery_time_seconds, 0) as delivery_time_seconds,
                COALESCE(delivery_time_multiplier, 1.0) as delivery_time_multiplier,
                COALESCE(delivery_time_credit, 0.0) as delivery_time_credit
            FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()

        if not result:
            logger.error(f"[DUCKDB_STORAGE] Participant {participant_id} not found in competition {competition_id}")
            return None

        # Parse result using named indices for clarity
        participant_id = result[0]      # id
        comp_id = result[1]             # competition_id
        name = result[2]                # name
        api_base_url = result[3] or ""  # api_base_url
        api_key = result[4] or ""       # api_key
        agent_profile_json = result[5] or "{}"  # agent_profile
        LLM_tokens = result[6] or 0     # LLM_tokens
        hint_tokens = result[7] or 0    # hint_tokens
        submission_tokens = result[8] or 0 # submission_tokens
        test_tokens = result[9] or 0       # test_tokens
        consumed_tokens = result[10] or 0   # consumed_tokens
        limit_tokens = result[11] or 100000  # limit_tokens
        remaining_tokens = result[12] or limit_tokens  # remaining_tokens
        lambda_value = result[13] or 100   # lambda_value

        submission_count = result[14] or 0 # submission_count
        accepted_count = result[15] or 0 # accepted_count
        submission_penalty = result[16] or 0 # submission_penalty
        problem_pass_score = result[17] or 0 # problem_pass_score

        # New statistics fields (using explicit column names above ensures correct order)
        llm_inference_count = result[18] or 0  # llm_inference_count
        first_ac_score = result[19] or 0       # first_ac_score
        problem_score = result[20] or 0        # problem_score
        bronze_score = result[21] or 0         # bronze_score
        silver_score = result[22] or 0         # silver_score
        gold_score = result[23] or 0           # gold_score
        platinum_score = result[24] or 0       # platinum_score
        bonus_score = result[25] or 0          # bonus_score
        problem_stats_json = result[26] or "{}" # problem_stats

        score = result[27] or 0          # score
        is_running = result[28] if result[28] is not None else True  # is_running
        termination_reason = result[29]  # termination_reason
        started_at = self._parse_timestamp(result[30]) or datetime.now()
        terminated_at = self._parse_timestamp(result[31])
        delivery_time_seconds = self._safe_int(result[32], 0)
        delivery_time_multiplier = self._safe_float(result[33], 1.0)
        delivery_time_credit = self._safe_float(result[34], 0.0)
        
        # Create Participant object
        participant = Participant(
            id=participant_id,
            competition_id=comp_id,
            name=name,
            api_base_url=api_base_url,
            api_key=api_key,
            limit_tokens=limit_tokens,
            lambda_value=lambda_value,
            agent_profile={},
            started_at=started_at,
            terminated_at=terminated_at,
            delivery_time_seconds=delivery_time_seconds,
            delivery_time_multiplier=delivery_time_multiplier,
            delivery_time_credit=delivery_time_credit,
        )
        
        # Set state read from database
        participant.LLM_tokens = LLM_tokens
        participant.hint_tokens = hint_tokens
        participant.submission_tokens = submission_tokens
        participant.test_tokens = test_tokens
        participant.consumed_tokens = consumed_tokens
        participant.remaining_tokens = remaining_tokens

        participant.submission_count = submission_count
        participant.accepted_count = accepted_count
        participant.submission_penalty = submission_penalty
        participant.problem_pass_score = problem_pass_score

        # Set new statistics fields
        participant.llm_inference_count = llm_inference_count
        participant.first_ac_score = first_ac_score
        participant.problem_score = problem_score
        participant.bronze_score = bronze_score
        participant.silver_score = silver_score
        participant.gold_score = gold_score
        participant.platinum_score = platinum_score
        participant.bonus_score = bonus_score

        # Parse problem_stats from JSON
        logger.debug(f"[DUCKDB_STORAGE] Problem stats JSON: {problem_stats_json}")
        try:
            participant.problem_stats = json.loads(problem_stats_json) if problem_stats_json else {}
        except (json.JSONDecodeError, TypeError):
            participant.problem_stats = {}

        try:
            participant.agent_profile = (
                json.loads(agent_profile_json) if agent_profile_json else {}
            )
        except (json.JSONDecodeError, TypeError):
            participant.agent_profile = {}

        participant.score = score
        participant.is_running = is_running
        participant.termination_reason = termination_reason
        participant.started_at = started_at
        participant.terminated_at = terminated_at
        participant.delivery_time_seconds = max(0, delivery_time_seconds)
        participant.delivery_time_multiplier = max(0.0, delivery_time_multiplier)
        participant.delivery_time_credit = max(0.0, delivery_time_credit)

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

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    @staticmethod
    def _get_delivery_time_multiplier(rules: Optional[Dict[str, Any]]) -> float:
        if not isinstance(rules, dict):
            return 1.0
        raw = rules.get("delivery_time_multiplier", 1.0)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 1.0
        return max(0.0, value)

    def _calculate_delivery_time_settlement(
        self,
        *,
        participant: Participant,
        competition: Optional[Competition],
        terminated_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        settled_at = terminated_at or datetime.now()
        started_at = participant.started_at or settled_at
        elapsed_seconds = participant.get_elapsed_time_seconds(now=settled_at)
        multiplier = self._get_delivery_time_multiplier(
            competition.rules if competition else None
        )
        delivery_credit = float(elapsed_seconds) * multiplier
        return {
            "started_at": started_at,
            "terminated_at": settled_at,
            "elapsed_seconds": elapsed_seconds,
            "multiplier": multiplier,
            "delivery_credit": delivery_credit,
        }

    def _calculate_level_score_updates(self, problem: Problem, submission: Submission,
                                     add_problem_pass_score: int, is_first_ac: bool) -> Dict[str, int]:
        """Calculate score updates by level and type"""
        updates = {
            'bronze_score': 0,
            'silver_score': 0,
            'gold_score': 0,
            'platinum_score': 0,
            'bonus_score': 0,
            'first_ac_score': 0,
            'problem_score': 0
        }

        if submission.status == SubmissionStatus.ACCEPTED and add_problem_pass_score > 0:
            # Calculate base problem score (excluding first AC bonus)
            base_score = add_problem_pass_score
            first_ac_bonus = 0

            if is_first_ac:
                # Extract first AC bonus from the total score
                competition = self.get_competition(submission.competition_id)
                if competition:
                    first_ac_bonus = competition.rules.get("bonus_for_first_ac", 100)
                    base_score = add_problem_pass_score - first_ac_bonus
                    updates['bonus_score'] = first_ac_bonus
                    updates['first_ac_score'] = first_ac_bonus

            # Assign to appropriate level
            level = problem.level.value
            if level == 'bronze':
                updates['bronze_score'] = base_score
            elif level == 'silver':
                updates['silver_score'] = base_score
            elif level == 'gold':
                updates['gold_score'] = base_score
            elif level == 'platinum':
                updates['platinum_score'] = base_score

            updates['problem_score'] = base_score

        return updates

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
            SET score = problem_pass_score - submission_penalty + lambda_value * (CAST(remaining_tokens AS DOUBLE) / CAST(limit_tokens AS DOUBLE))
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
        
        # Read directly from database fields
        problem_id = result[0]      # id
        title = result[2]           # title
        description = result[3] or ""  # description
        level_str = result[4]       # level
        time_limit_ms = result[5] or 1000  # time_limit_ms
        memory_limit_mb = result[6] or 256  # memory_limit_mb
        first_to_solve = result[7]  # first_to_solve
        
        # Parse sample_cases
        sample_cases = []
        sample_cases_json = result[8]  # sample_cases
        if sample_cases_json:
            try:
                sample_cases_data = json.loads(sample_cases_json)
                for case_data in sample_cases_data:
                    case = Case(
                        id=case_data.get('id', generate_id()),
                        input_data=case_data.get('input_data', ''),
                        expected_output=case_data.get('expected_output', ''),
                        input_path=case_data.get('input_path')
                    )
                    sample_cases.append(case)
            except (json.JSONDecodeError, KeyError):
                # If JSON parsing fails, use empty list
                sample_cases = []
        
        # Determine difficulty level
        if level_str == 'bronze':
            level = Level.BRONZE
        elif level_str == 'silver':
            level = Level.SILVER
        elif level_str == 'gold':
            level = Level.GOLD
        elif level_str == 'platinum':
            level = Level.PLATINUM
        else:
            level = Level.BRONZE  # Default value
        
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

        participant = self.get_participant(competition_id, participant_id)
        if participant is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")
        first_to_solve = participant.name

        conn.execute("""
            UPDATE problems 
            SET first_to_solve = ? 
            WHERE competition_id = ? AND id = ?
        """, [first_to_solve, competition_id, problem_id])

    

    def create_submission(self, competition_id: str, participant_id: str, 
                         problem_id: str, code: str, language: str) -> Tuple[Optional[Submission], Optional[str]]:
        """Create a new submission with evaluation and scoring"""
        # Validate competition exists
        competition = self.get_competition(competition_id)
        if not competition:
            return None, None
        
        # Validate problem exists
        problem = self.get_problem(competition_id, problem_id)
        if not problem:
            return None, None
        
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
        judge = self.judge
        if judge is None:
            raise ValueError("Judge is not initialized")
        logger.critical(f"judge: {judge}")
        submission = judge.evaluate_submission(submission, problem, competition, first_one)
        
        
        # # Handle first AC bonus
        if submission.status == SubmissionStatus.ACCEPTED and first_one:
            # Update problem's first_to_solve in database
            self._update_problem_first_to_solve(competition_id, problem_id, participant_id)
        
        # Insert submission into database and update statistics
        conn = self._get_conn()

        # Get current participant and their problem stats
        participant = self.get_participant(competition_id, participant_id)
        if not participant:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")

        # Get current best score for this problem
        current_best_score_result = conn.execute("""
            SELECT MAX(pass_score) FROM submissions
            WHERE competition_id = ? AND participant_id = ? AND problem_id = ?
        """, [competition_id, participant_id, problem_id]).fetchone()

        if current_best_score_result is None:
            # If no submission has been made yet, directly add the current submission score
            add_problem_pass_score = submission.pass_score
            current_best_score = 0
        else:
            current_best_score = current_best_score_result[0] if current_best_score_result[0] else 0
            # If current submission score is greater than current best score, add the difference
            if submission.pass_score >= current_best_score:
                add_problem_pass_score = submission.pass_score - current_best_score
            else:
                add_problem_pass_score = 0

        # Update per-problem statistics
        participant.update_problem_stats(
            problem_id,
            submission,
            passed_cases=len([tr for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED]),
            total_cases=len(submission.test_results),
            is_first_ac=first_one and submission.status == SubmissionStatus.ACCEPTED
        )

        # Calculate detailed scoring updates
        level_score_updates = self._calculate_level_score_updates(problem, submission, add_problem_pass_score, first_one)

        conn.execute("""
            UPDATE participants
            SET submission_tokens = submission_tokens + ?,
                consumed_tokens = COALESCE(consumed_tokens, 0) + ?,
                remaining_tokens = remaining_tokens - ? - ?,
                submission_count = submission_count + 1,
                accepted_count = accepted_count + ?,
                submission_penalty = submission_penalty + ?,
                problem_pass_score = problem_pass_score + ?,
                bronze_score = bronze_score + ?,
                silver_score = silver_score + ?,
                gold_score = gold_score + ?,
                platinum_score = platinum_score + ?,
                bonus_score = bonus_score + ?,
                first_ac_score = first_ac_score + ?,
                problem_score = problem_score + ?,
                problem_stats = ?
            WHERE competition_id = ? AND id = ?
        """, [
            submission.submission_tokens,
            submission.submission_tokens,
            submission.submission_tokens,
            submission.penalty,
            1 if submission.status == SubmissionStatus.ACCEPTED else 0,
            submission.penalty,
            add_problem_pass_score,
            level_score_updates['bronze_score'],
            level_score_updates['silver_score'],
            level_score_updates['gold_score'],
            level_score_updates['platinum_score'],
            level_score_updates['bonus_score'],
            level_score_updates['first_ac_score'],
            level_score_updates['problem_score'],
            json.dumps(participant.problem_stats),
            competition_id,
            participant_id
        ])
        
        # Get current consumed_tokens and limit_tokens for termination check
        token_status = conn.execute("""
            SELECT COALESCE(consumed_tokens, 0) as consumed_tokens, limit_tokens FROM participants WHERE competition_id = ? AND id = ?
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

        if token_status is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")

        consumed_tokens, limit_tokens = token_status[0], token_status[1]

        # Check if participant should be terminated due to token exhaustion (based on actual consumption, not penalties)
        if consumed_tokens >= limit_tokens:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")
        
        # Backup
        self._backup_to_json('submission', submission.to_dict(include_code=False))
        
        return submission, problem.title
    
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

    # Analytics and Reporting Methods
    def calculate_competition_rankings(self, competition_id: str) -> List[Dict]:
        """Get competition rankings using SQL"""
        conn = self._get_conn()
        # Get rankings based on new ranking rules:
        # 1. Higher problem_pass_score ranks higher
        # 2. For same problem_pass_score, lower consumed_credit ranks higher
        #    consumed_credit = consumed_tokens + submission_penalty + settled_delivery_time_credit
        rows = conn.execute("""
            SELECT
                p.id,
                p.name,
                p.problem_pass_score,
                COALESCE(
                    p.problem_pass_score - p.submission_penalty
                    + p.lambda_value * (CAST(p.remaining_tokens AS DOUBLE) / NULLIF(CAST(p.limit_tokens AS DOUBLE), 0)),
                    p.problem_pass_score - p.submission_penalty
                ) AS score,
                (
                    COALESCE(p.consumed_tokens, 0)
                    + p.submission_penalty
                    + CASE
                        WHEN p.is_running THEN 0.0
                        ELSE COALESCE(p.delivery_time_credit, 0.0)
                    END
                ) as consumed_credit,
                COALESCE(p.delivery_time_credit, 0.0) as delivery_time_credit,
                COALESCE(p.delivery_time_seconds, 0) as delivery_time_seconds,
                RANK() OVER (
                    ORDER BY
                        p.problem_pass_score DESC,
                        (
                            COALESCE(p.consumed_tokens, 0)
                            + p.submission_penalty
                            + CASE
                                WHEN p.is_running THEN 0.0
                                ELSE COALESCE(p.delivery_time_credit, 0.0)
                            END
                        ) ASC
                ) as rank
            FROM participants p
            WHERE p.competition_id = ?
            ORDER BY
                p.problem_pass_score DESC,
                (
                    COALESCE(p.consumed_tokens, 0)
                    + p.submission_penalty
                    + CASE
                        WHEN p.is_running THEN 0.0
                        ELSE COALESCE(p.delivery_time_credit, 0.0)
                    END
                ) ASC
        """, [competition_id]).fetchall()

        rankings: List[Dict[str, Any]] = []
        for row in rows:
            participant_id = row[0]
            name = row[1]
            problem_pass_score = row[2]
            total_score = row[3]
            consumed_credit = row[4]
            delivery_time_credit = row[5]
            delivery_time_seconds = row[6]
            rank = row[7]
            rankings.append(
                {
                    "participant_id": participant_id,
                    "name": name,
                    "problem_pass_score": int(problem_pass_score or 0),
                    "score": int(problem_pass_score or 0),
                    "total_score": float(total_score or 0),
                    "consumed_credit": float(consumed_credit or 0.0),
                    "delivery_time_credit": float(delivery_time_credit or 0.0),
                    "delivery_time_seconds": int(delivery_time_seconds or 0),
                    "rank": int(rank or 0),
                }
            )
        return rankings
    
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
        """Called when entering the context manager"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Called when exiting the context manager, ensures connection is closed"""
        self.close()
    
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
        
        logger.info(f"DuckDB backup created: {backup_path}")
        return str(backup_path)
    
    # Agent-related methods
    def resolve_participant_api_config(self, participant: Participant) -> Tuple[str, str]:
        """
        Resolve upstream LLM API configuration for a participant.

        Priority:
        1. Participant-level config stored in DB.
        2. Server-level fallback env:
           - USACOARENA_UPSTREAM_API_BASE_URL
           - USACOARENA_UPSTREAM_API_KEY
        """
        api_base_url = (participant.api_base_url or "").strip()
        api_key = (participant.api_key or "").strip()

        if not api_base_url:
            api_base_url = (os.environ.get("USACOARENA_UPSTREAM_API_BASE_URL", "") or "").strip()
        if not api_key:
            api_key = (os.environ.get("USACOARENA_UPSTREAM_API_KEY", "") or "").strip()

        return api_base_url, api_key

    def validate_participant_api_config(self, participant: Participant) -> bool:
        """
        Validate that participant has valid API configuration.
        
        Args:
            participant: Participant object
            
        Returns:
            True if configuration is valid, False otherwise
        """
        api_base_url, api_key = self.resolve_participant_api_config(participant)
        profile = participant.agent_profile if isinstance(participant.agent_profile, dict) else {}
        request_format = profile.get("request_format") if isinstance(profile, dict) else {}
        headers = request_format.get("headers") if isinstance(request_format, dict) else {}
        needs_key = False
        if isinstance(headers, dict):
            for value in headers.values():
                if isinstance(value, str) and "{api_key}" in value:
                    needs_key = True
                    break
        return bool(api_base_url and (api_key or not needs_key))

    @staticmethod
    def _resolve_request_format(
        participant: Participant,
        request_data: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        profile = participant.agent_profile if isinstance(participant.agent_profile, dict) else {}
        profile_request_format = (
            profile.get("request_format") if isinstance(profile.get("request_format"), dict) else {}
        )
        profile_response_format = (
            profile.get("response_format") if isinstance(profile.get("response_format"), dict) else {}
        )

        request_meta = (
            request_data.pop("_usacoarena_request_format", None)
            if isinstance(request_data, dict)
            else None
        )
        response_meta = (
            request_data.pop("_usacoarena_response_format", None)
            if isinstance(request_data, dict)
            else None
        )

        effective_request_format = (
            request_meta if isinstance(request_meta, dict) else profile_request_format
        )
        effective_response_format = (
            response_meta if isinstance(response_meta, dict) else profile_response_format
        )

        if not isinstance(effective_request_format, dict):
            effective_request_format = {}
        if not isinstance(effective_response_format, dict):
            effective_response_format = {}

        return profile, effective_request_format, effective_response_format

    @staticmethod
    def _build_upstream_request(
        *,
        request_data: Dict[str, Any],
        request_format: Dict[str, Any],
        api_key: str,
    ) -> Tuple[str, str, Dict[str, str], Dict[str, Any]]:
        selected_api_path = DuckDBStorage._normalize_api_path(
            request_format.get("url") or request_data.get("api_path") or "/v1/chat/completions"
        )
        method = str(request_format.get("method") or "POST").strip().upper() or "POST"
        header_template = request_format.get("headers")
        headers: Dict[str, str] = {}
        substitutions = {"api_key": api_key}
        if isinstance(header_template, dict):
            for key, value in header_template.items():
                if not str(key).strip():
                    continue
                if isinstance(value, str):
                    headers[str(key).strip()] = value.format(**substitutions)
                else:
                    headers[str(key).strip()] = str(value)
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        body_template = request_format.get("body_template")
        payload_json: Dict[str, Any]
        if isinstance(body_template, dict) and body_template:
            substitutions_with_payload = {
                **substitutions,
                "messages": json.dumps(
                    request_data.get("messages", []), ensure_ascii=False
                ),
                "model_id": str(request_data.get("model") or ""),
                "prompt": str(request_data.get("prompt") or ""),
            }
            payload_json = _deep_format_template(body_template, substitutions_with_payload)
            if isinstance(payload_json.get("messages"), str):
                try:
                    payload_json["messages"] = json.loads(payload_json["messages"])
                except Exception:
                    pass
        else:
            payload_json = dict(request_data or {})

        payload_json.pop("api_path", None)
        timeout_raw = payload_json.pop("timeout", request_data.get("timeout", 300.0))
        timeout_s = float(timeout_raw or 300.0)
        return selected_api_path, method, headers, payload_json

    @staticmethod
    def _normalize_api_path(api_path: str) -> str:
        normalized = "/" + str(api_path or "").lstrip("/")
        return normalized or "/v1/chat/completions"

    @staticmethod
    def _candidate_api_paths(selected_api_path: str) -> List[str]:
        normalized = DuckDBStorage._normalize_api_path(selected_api_path)
        candidates = [normalized]
        if normalized.startswith("/v1/"):
            alt = normalized[3:]
            if alt and alt not in candidates:
                candidates.append(alt)
        return candidates

    @staticmethod
    def _should_try_path_fallback(status_code: int, response_body: str) -> bool:
        if status_code < 400:
            return False
        lowered = (response_body or "").lower()
        fallback_hints = (
            "v1/v1",
            "no static resource",
            "no_matching_channel",
            "no openai-compatible channels available",
        )
        return any(hint in lowered for hint in fallback_hints)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _request_upstream_with_retries(
        self,
        *,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
        stream: bool = False,
        max_retries: Optional[int] = None,
    ) -> requests.Response:
        retryable_statuses = {429, 500, 502, 503, 504}
        if max_retries is None:
            max_retries = self._safe_int(
                os.environ.get("USACOARENA_UPSTREAM_MAX_RETRIES", "6"),
                6,
            )
        max_retries = max(1, min(max_retries, 10))
        last_error = ""
        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                    stream=stream,
                )
            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                if attempt < max_retries - 1:
                    sleep_s = min(8.0, 0.6 * (2 ** attempt))
                    logger.warning(
                        f"LLM request network failure, retrying ({attempt + 1}/{max_retries}) "
                        f"url={url}, sleep={sleep_s:.2f}s, err={exc}"
                    )
                    time.sleep(sleep_s)
                    continue
                raise Exception(f"LLM API request failed: {exc}") from exc

            if response.status_code in retryable_statuses and attempt < max_retries - 1:
                sleep_s = min(8.0, 0.6 * (2 ** attempt))
                logger.warning(
                    f"LLM request got retryable status={response.status_code}, retrying "
                    f"({attempt + 1}/{max_retries}) url={url}, sleep={sleep_s:.2f}s"
                )
                time.sleep(sleep_s)
                continue

            return response

        raise Exception(f"LLM API request failed after retries: {last_error}")

    @staticmethod
    def _empty_usage_payload(remaining_tokens: int) -> Dict[str, int]:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "remaining_tokens": max(0, remaining_tokens),
        }
    
    def process_agent_request(
        self, 
        competition_id: str, 
        participant_id: str, 
        request_data: Dict[str, Any],
        api_path: Optional[str] = None,
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

        upstream_api_base_url, upstream_api_key = self.resolve_participant_api_config(participant)
        request_payload = dict(request_data or {})
        _, effective_request_format, _ = self._resolve_request_format(
            participant, request_payload
        )
        selected_api_path, request_method, headers, payload_json = self._build_upstream_request(
            request_data=request_payload,
            request_format=effective_request_format,
            api_key=upstream_api_key,
        )
        if api_path:
            selected_api_path = self._normalize_api_path(api_path)
        timeout_s = float(payload_json.pop("timeout", 300.0) or 300.0)

        result: Optional[Dict[str, Any]] = None
        response_is_sse = False
        response_sse_body = ""
        response: Optional[requests.Response] = None
        active_api_path = selected_api_path
        stream_mode = bool(payload_json.get("stream", False))
        candidate_paths = self._candidate_api_paths(selected_api_path)
        for index, candidate_path in enumerate(candidate_paths):
            active_api_path = candidate_path
            request_url = f"{upstream_api_base_url.rstrip('/')}{candidate_path}"
            response = self._request_upstream_with_retries(
                method=request_method,
                url=request_url,
                headers=headers,
                payload=payload_json,
                timeout=timeout_s,
                stream=stream_mode,
            )

            parsed_json: Any = None
            parsed_ok = True
            content_type = (response.headers.get("Content-Type", "") or "").lower()
            is_sse = "text/event-stream" in content_type

            if is_sse and response.status_code < 400:
                response_is_sse = True
                sse_lines: List[str] = []
                completed_response: Optional[Dict[str, Any]] = None
                for raw_line in response.iter_lines(decode_unicode=True):
                    if raw_line is None:
                        continue
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="ignore")
                    sse_lines.append(line)
                    if not line.startswith("data:"):
                        continue
                    data_line = line[5:].strip()
                    if not data_line or data_line == "[DONE]":
                        continue
                    try:
                        event_payload = json.loads(data_line)
                    except Exception:
                        continue
                    if not isinstance(event_payload, dict):
                        continue
                    event_type = str(event_payload.get("type", ""))
                    if event_type in {"response.completed", "response.failed"}:
                        response_payload = event_payload.get("response")
                        if isinstance(response_payload, dict):
                            completed_response = response_payload

                response_sse_body = "\n".join(sse_lines) + ("\n" if sse_lines else "")
                if completed_response is None:
                    completed_response = {}
                parsed_json = completed_response
                parsed_ok = isinstance(parsed_json, dict)
            else:
                try:
                    parsed_json = response.json()
                except ValueError:
                    parsed_ok = False

            body_preview = ""
            if parsed_ok:
                try:
                    body_preview = json.dumps(parsed_json, ensure_ascii=False)
                except Exception:
                    body_preview = str(parsed_json)
            else:
                body_preview = (response.text or "")

            body_preview = body_preview[:1500]

            if response.status_code >= 400:
                request_model = payload_json.get("model")
                request_stream = payload_json.get("stream")
                request_tools = payload_json.get("tools")
                tools_count = len(request_tools) if isinstance(request_tools, list) else 0
                logger.warning(
                    "Upstream LLM error: "
                    f"status={response.status_code}, api_path={active_api_path}, model={request_model}, "
                    f"stream={request_stream}, tools_count={tools_count}, body={body_preview[:400]}"
                )
                if (
                    index < len(candidate_paths) - 1
                    and self._should_try_path_fallback(response.status_code, body_preview)
                ):
                    logger.warning(
                        f"Retrying upstream API with fallback path: {selected_api_path} -> {candidate_paths[index + 1]} "
                        f"(status={response.status_code})"
                    )
                    continue

                error_payload: Any
                if parsed_ok and isinstance(parsed_json, (dict, list)):
                    error_payload = parsed_json
                else:
                    error_payload = {
                        "error": {
                            "type": "upstream_error",
                            "code": str(response.status_code),
                            "message": body_preview or f"HTTP {response.status_code}",
                        }
                    }

                return {
                    "content": error_payload,
                    "usage": self._empty_usage_payload(participant.remaining_tokens),
                    "status_code": response.status_code,
                    "api_path": active_api_path,
                    "is_sse": False,
                }

            if not parsed_ok or not isinstance(parsed_json, dict):
                return {
                    "content": {
                        "error": {
                            "type": "invalid_upstream_response",
                            "message": (
                                f"Upstream returned non-JSON body for {active_api_path}: "
                                f"{body_preview or '<empty>'}"
                            ),
                        }
                    },
                    "usage": self._empty_usage_payload(participant.remaining_tokens),
                    "status_code": 502,
                    "api_path": active_api_path,
                    "is_sse": False,
                }

            result = parsed_json
            break

        if response is None or result is None:
            raise Exception(
                f"LLM API request failed with no valid response (api_path={selected_api_path})"
            )
        
        # Parse token usage
        usage_data = result.get("usage", {}) or {}
        prompt_tokens = self._safe_int(
            usage_data.get("prompt_tokens", usage_data.get("input_tokens", 0)),
            0,
        )
        completion_tokens = self._safe_int(
            usage_data.get("completion_tokens", usage_data.get("output_tokens", 0)),
            0,
        )
        reasoning_tokens = self._safe_int(
            (usage_data.get("completion_tokens_details", {}) or {}).get("reasoning_tokens", None),
            self._safe_int(
                (usage_data.get("output_tokens_details", {}) or {}).get("reasoning_tokens", 0),
                0,
            ),
        )

        model_id = payload_json.get("model")
        if prompt_tokens == 0:
            estimate_messages = payload_json.get("messages")
            if not estimate_messages and payload_json.get("input") is not None:
                estimate_messages = [{"role": "user", "content": payload_json.get("input")}]
            estimated_prompt = estimate_prompt_tokens(
                estimate_messages, model_id
            )
            if estimated_prompt:
                prompt_tokens = estimated_prompt
                logger.debug(
                    f"Estimated prompt tokens for model {model_id}: {prompt_tokens}"
                )

        if completion_tokens == 0:
            estimated_completion = estimate_completion_tokens(result, model_id)
            if estimated_completion:
                completion_tokens = estimated_completion
                logger.debug(
                    f"Estimated completion tokens for model {model_id}: {completion_tokens}"
                )
        
        # Apply competition rules multipliers
        if competition and competition.rules:
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

        # Update database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants
            SET LLM_tokens = LLM_tokens + ?,
                consumed_tokens = COALESCE(consumed_tokens, 0) + ?,
                remaining_tokens = remaining_tokens - ?,
                llm_inference_count = llm_inference_count + 1
            WHERE competition_id = ? AND id = ?
        """, [llm_tokens, llm_tokens, llm_tokens, competition_id, participant_id])

        # Get current consumed_tokens and limit_tokens for termination check
        token_status = conn.execute("""
            SELECT COALESCE(consumed_tokens, 0) as consumed_tokens, limit_tokens FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()

        if token_status is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")

        consumed_tokens, limit_tokens = token_status[0], token_status[1]

        # Calculate new_remaining_tokens for response (using the old logic with penalties)
        new_remaining_tokens = max(0, participant.remaining_tokens - llm_tokens)

        # Check if participant should be terminated due to token exhaustion (based on actual consumption, not penalties)
        if consumed_tokens >= limit_tokens:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")


        return {
            "content": result,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": llm_tokens,
                "remaining_tokens": new_remaining_tokens
            },
            "status_code": response.status_code,
            "api_path": active_api_path,
            "is_sse": response_is_sse,
            "sse_body": response_sse_body if response_is_sse else "",
        }
    
    def process_stream_agent_request(
        self, 
        competition_id: str, 
        participant_id: str, 
        request_data: Dict[str, Any],
        api_path: Optional[str] = None,
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

        upstream_api_base_url, upstream_api_key = self.resolve_participant_api_config(participant)
        if isinstance(request_data.get("json"), dict):
            request_payload = dict(request_data.get("json") or {})
        else:
            request_payload = dict(request_data or {})
        _, effective_request_format, _ = self._resolve_request_format(
            participant, request_payload
        )
        selected_api_path, request_method, request_headers, request_json = self._build_upstream_request(
            request_data=request_payload,
            request_format=effective_request_format,
            api_key=upstream_api_key,
        )
        if api_path:
            selected_api_path = self._normalize_api_path(api_path)
        complete_request = {
            'method': request_method,
            'headers': request_headers,
            'json': request_json,
            'timeout': request_data.get('timeout', 300.0)
        }

        # Add streaming parameter to request
        if 'stream' not in complete_request['json']:
            complete_request['json']['stream'] = True
        
        # Make streaming HTTP request to LLM API (with compatibility fallback)
        response: Optional[requests.Response] = None
        candidate_paths = self._candidate_api_paths(selected_api_path)
        for index, candidate_path in enumerate(candidate_paths):
            response = self._request_upstream_with_retries(
                method=complete_request['method'],
                url=f"{upstream_api_base_url.rstrip('/')}{candidate_path}",
                headers=complete_request['headers'],
                payload=complete_request['json'],
                timeout=float(complete_request.get('timeout', 300.0) or 300.0),
                stream=True,
            )

            if response.status_code < 400:
                break

            body_preview = (response.text or "")[:1500]
            if (
                index < len(candidate_paths) - 1
                and self._should_try_path_fallback(response.status_code, body_preview)
            ):
                logger.warning(
                    f"Retrying upstream streaming API with fallback path: {selected_api_path} -> {candidate_paths[index + 1]} "
                    f"(status={response.status_code})"
                )
                continue

            raise Exception(
                f"LLM API streaming request failed: HTTP {response.status_code}, body={body_preview}"
            )

        if response is None or response.status_code >= 400:
            raise Exception("LLM API streaming request failed: no valid upstream response")
        
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

        # Update database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants
            SET LLM_tokens = LLM_tokens + ?,
                consumed_tokens = COALESCE(consumed_tokens, 0) + ?,
                remaining_tokens = remaining_tokens - ?,
                llm_inference_count = llm_inference_count + 1
            WHERE competition_id = ? AND id = ?
        """, [llm_tokens, llm_tokens, llm_tokens, competition_id, participant_id])

        # Get current consumed_tokens and limit_tokens for termination check
        token_status = conn.execute("""
            SELECT COALESCE(consumed_tokens, 0) as consumed_tokens, limit_tokens FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()

        if token_status is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")

        consumed_tokens, limit_tokens = token_status[0], token_status[1]
        new_remaining_tokens = max(0, participant.remaining_tokens - llm_tokens)

        # Check if participant should be terminated due to token exhaustion (based on actual consumption, not penalties)
        if consumed_tokens >= limit_tokens:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")
        
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
            SET hint_tokens = hint_tokens + ?,
                consumed_tokens = COALESCE(consumed_tokens, 0) + ?,
                remaining_tokens = ?
            WHERE competition_id = ? AND id = ?
        """, [hint_cost, hint_cost, new_remaining_tokens, competition_id, participant_id])

        # Get current consumed_tokens and limit_tokens for termination check
        token_status = conn.execute("""
            SELECT COALESCE(consumed_tokens, 0) as consumed_tokens, limit_tokens FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()

        if token_status is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")

        consumed_tokens, limit_tokens = token_status[0], token_status[1]

        # Check if participant should be terminated due to token exhaustion (based on actual consumption, not penalties)
        if consumed_tokens >= limit_tokens:
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
        from usacoarena.utils.problem_loader import USACOProblemLoader
        from usacoarena.utils.textbook_loader import TextbookLoader
        from usacoarena.utils.strategy_loader import StrategyLoader
        from usacoarena.utils.usacoguide_loader import USACOGuideLoader
        
        problem_loader = USACOProblemLoader()
        textbook_loader = TextbookLoader()
        strategy_loader = StrategyLoader()
        guide_loader = USACOGuideLoader()
        
        # Initialize hint content
        hint_content: Dict[str, Any] = {}

        if problem is not None: 
            hint_content["current_problem"] = {
                "title": problem.title,
                "id": problem.id
            }
        if hint_knowledge is not None:
            hint_content["hint_knowledge"] = hint_knowledge

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
                    textbook_results = textbook_loader.search_content(" ".join(search_terms), max_results=1)
                    
                    if textbook_results:
                        for result in textbook_results:
                            hint_content["textbook_sections"].append({
                                "title": result.get('title', 'Section'),
                                "content": result.get('content', '')[:1000] + "...",
                                "relevance_score": result.get('relevance_score', 0.0)
                            })
                            
        elif hint_level == 2:
            hint_content["textbook_sections"] = []
            # Search textbook for relevant content
            if textbook_loader.is_loaded():
                
                search_terms = hint_knowledge
                textbook_results = textbook_loader.search_content(str(search_terms), max_results=1)

                if textbook_results:
                    for result in textbook_results:
                        hint_content["textbook_sections"].append({
                            "title": result.get('title', 'Section'),
                            "content": result.get('content', '')[:1000] + "...",
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
                        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:1]
                        
                        for idx in top_indices:
                            pid = problem_ids[idx]
                            p = problem_loader.load_problem(pid)
                            solution = problem_loader.load_solution(pid)

                            if p:
                                hint_content["similar_problems"].append({
                                    "title": p.title,
                                    "description": p.description[:500] + "...",
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
                    
                    if hint_knowledge is not None:
                        hint_content["example_problems"] = guide_loader.search_second_level_key_similar(problem_difficulty, hint_knowledge)
                    
                except Exception as e:
                    # Add error information
                    hint_content["example_problems"] = [{
                        "title": "Error",
                        "description": f"Error finding second level keys: {str(e)}",
                        "solution": "Please try again later",
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
        
        # Avoid double termination and double participant_count decrement
        if not participant.is_running:
            logger.warning(
                f"Participant {participant_id} already terminated "
                f"(reason={participant.termination_reason}), skipping duplicate termination"
            )
            return

        competition = self.get_competition(competition_id)
        settlement = self._calculate_delivery_time_settlement(
            participant=participant,
            competition=competition,
            terminated_at=datetime.now(),
        )

        # Update participant status in database and settle delivery-time credit.
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants 
            SET is_running = ?,
                termination_reason = ?,
                started_at = ?,
                terminated_at = ?,
                delivery_time_seconds = ?,
                delivery_time_multiplier = ?,
                delivery_time_credit = ?
            WHERE competition_id = ? AND id = ?
        """, [
            False,
            reason,
            settlement["started_at"],
            settlement["terminated_at"],
            settlement["elapsed_seconds"],
            settlement["multiplier"],
            settlement["delivery_credit"],
            competition_id,
            participant_id,
        ])

        # Update competition status
        conn.execute("""
            UPDATE competitions 
            SET participant_count = participant_count - 1
            WHERE id = ?
        """, [competition_id])
        
        # Log termination
        logger.warning(
            "Participant %s terminated: %s (elapsed_seconds=%s, multiplier=%s, delivery_credit=%s)",
            participant_id,
            reason,
            settlement["elapsed_seconds"],
            settlement["multiplier"],
            settlement["delivery_credit"],
        )
        
        # Backup the updated participant data
        updated_participant = self.get_participant(competition_id, participant_id)
        if updated_participant:
            self._backup_to_json('participant', updated_participant.to_dict())

    def process_test_code_request(
        self,
        competition_id: str,
        participant_id: str,
        code: str,
        language: str,
        test_cases: List[Case],
        time_limit_ms: int = 5000,
        memory_limit_mb: int = 256
    ) -> Dict[str, Any]:
        """
        Process a test code request and update participant token usage.
        This action does not affect competition scoring or statistics.

        Args:
            competition_id: Competition ID
            participant_id: Participant ID
            code: Source code to test
            language: Programming language
            test_cases: List of custom test cases
            time_limit_ms: Time limit in milliseconds
            memory_limit_mb: Memory limit in MB

        Returns:
            Dictionary containing test results and token usage information
        """
        # Get competition and participant
        competition = self.get_competition(competition_id)
        if not competition:
            raise ValueError(f"Competition with ID {competition_id} not found")

        participant = self.get_participant(competition_id, participant_id)
        if not participant:
            raise ValueError(f"Participant with ID {participant_id} not found")

        # Get test token cost from competition rules
        test_tokens_config = competition.rules.get("test_tokens", {})

        # Support different pricing strategies
        if isinstance(test_tokens_config, dict):
            # Base cost
            test_cost = test_tokens_config.get("default", 50)

            # Optional: Additional cost based on number of test cases
            cost_per_case = test_tokens_config.get("per_test_case", 0)
            if cost_per_case > 0:
                test_cost += len(test_cases) * cost_per_case

            # Optional: Language-specific pricing
            language_multiplier = test_tokens_config.get("language_multipliers", {}).get(language, 1.0)
            test_cost = int(test_cost * language_multiplier)
        else:
            # Fallback for simple integer configuration
            test_cost = int(test_tokens_config) if test_tokens_config else 50

        # Check if participant has enough tokens
        if participant.remaining_tokens < test_cost:
            raise ValueError(f"Insufficient tokens. Required: {test_cost}, Available: {participant.remaining_tokens}")

        # Validate judge is available
        judge = self.judge
        if judge is None:
            raise ValueError("Judge is not initialized")

        # Execute test code with custom test cases
        try:
            test_results = judge.test_code_with_custom_cases(
                code=code,
                language=language,
                test_cases=test_cases,
                time_limit_ms=time_limit_ms,
                memory_limit_mb=memory_limit_mb
            )
        except Exception as e:
            logger.error(f"Error testing code: {str(e)}", exc_info=True)
            raise ValueError(f"Code testing failed: {str(e)}")

        # Update participant token usage (deduct test cost)
        new_remaining_tokens = participant.remaining_tokens - test_cost

        # Update database
        conn = self._get_conn()
        conn.execute("""
            UPDATE participants
            SET test_tokens = test_tokens + ?,
                consumed_tokens = COALESCE(consumed_tokens, 0) + ?,
                remaining_tokens = ?
            WHERE competition_id = ? AND id = ?
        """, [test_cost, test_cost, new_remaining_tokens, competition_id, participant_id])

        # Get current consumed_tokens and limit_tokens for termination check
        token_status = conn.execute("""
            SELECT COALESCE(consumed_tokens, 0) as consumed_tokens, limit_tokens FROM participants WHERE competition_id = ? AND id = ?
        """, [competition_id, participant_id]).fetchone()

        if token_status is None:
            raise ValueError(f"Participant {participant_id} not found in competition {competition_id}")

        consumed_tokens, limit_tokens = token_status[0], token_status[1]

        # Check if participant should be terminated due to token exhaustion (based on actual consumption, not penalties)
        if consumed_tokens >= limit_tokens:
            self.terminate_participant(competition_id, participant_id, "out_of_tokens")

        # Calculate test statistics
        passed_tests = sum(1 for tr in test_results if tr.status == SubmissionStatus.ACCEPTED)
        total_tests = len(test_results)

        logger.info(f"Test code request completed for participant {participant_id}: {passed_tests}/{total_tests} tests passed, {test_cost} tokens consumed")

        return {
            "test_results": [tr.to_dict() for tr in test_results],
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "tokens_cost": test_cost,
            "remaining_tokens": new_remaining_tokens,
            "language": language,
            "execution_summary": {
                "compilation_errors": sum(1 for tr in test_results if tr.status == SubmissionStatus.COMPILATION_ERROR),
                "runtime_errors": sum(1 for tr in test_results if tr.status == SubmissionStatus.RUNTIME_ERROR),
                "time_limit_exceeded": sum(1 for tr in test_results if tr.status == SubmissionStatus.TIME_LIMIT_EXCEEDED),
                "memory_limit_exceeded": sum(1 for tr in test_results if tr.status == SubmissionStatus.MEMORY_LIMIT_EXCEEDED),
                "wrong_answers": sum(1 for tr in test_results if tr.status == SubmissionStatus.WRONG_ANSWER),
                "accepted": passed_tests
            }
        }
