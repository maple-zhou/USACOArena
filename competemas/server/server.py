import json
import traceback
import time
import threading
from typing import Any, Dict, List, Optional, Tuple
import requests
from datetime import datetime
import os
from flask import Flask, Response, jsonify, request
from rank_bm25 import BM25Okapi

# AgentRequest, AgentResponse, TokenUsage classes were removed with agent_interface.py
from ..engine.storage import DuckDBStorage
from ..engine.judge import Judge
from ..models.models import (Case, Competition, Level, Participant, Problem, Submission, SubmissionStatus, generate_id)
from ..utils.problem_loader import USACOProblemLoader
from ..utils.textbook_loader import TextbookLoader
from ..utils.logger_config import get_logger, setup_logging
import logging


# Get logger
logger = get_logger("server")

# Initialize problem library loader and textbook loader
problem_loader = USACOProblemLoader()

textbook_loader = TextbookLoader()

# Create Flask app
app = Flask(__name__)
logger.info("Created Flask application")

# Add global request frequency control
class GlobalRateLimiter:
    """Global request frequency limiter"""
    def __init__(self, min_interval: float = 0.05):
        self._last_request_time = 0  # Record last request time
        self._lock = threading.Lock()
        self._min_interval = min_interval  # Minimum request interval (seconds)
    
    def should_rate_limit(self) -> bool:
        """Check if request frequency should be limited"""
        with self._lock:
            current_time = time.time()
            
            if current_time - self._last_request_time < self._min_interval:
                return True
            
            self._last_request_time = current_time
            return False
    
    def get_wait_time(self) -> float:
        """Get the time to wait"""
        with self._lock:
            current_time = time.time()
            return max(0, self._min_interval - (current_time - self._last_request_time))

# Global request limiter (will be configured during initialization)
global_rate_limiter = GlobalRateLimiter()


def get_text_from_path(data: Dict, path: str) -> str:
    """
    Extract text value from nested dictionary using dot notation path.
    
    Args:
        data: Dictionary to extract value from
        path: Dot notation path (e.g., "choices[0].message.content")
        
    Returns:
        Extracted text value as string
        
    Raises:
        KeyError: If path is invalid or key not found
    """
    if not path:
        return str(data)
    
    parts = path.split('.')
    current = data
    
    for part in parts:
        if '[' in part:
            key, index = part.split('[')
            index = int(index.rstrip(']'))
            if key not in current or not isinstance(current[key], (list, tuple)) or index >= len(current[key]):
                raise KeyError(f"Invalid array access: {key}[{index}]")
            current = current[key][index]
        else:
            if part not in current:
                raise KeyError(f"Key '{part}' not found in data")
            current = current[part]
    
    return str(current) if current is not None else ""




# Helper functions
def success_response(data: Any = None, message: str = "Success") -> Response:
    """
    Create a standardized success response.
    
    Args:
        data: Optional data to include in response
        message: Success message string
        
    Returns:
        Flask Response object with success status
    """
    response = {
        "status": "success",
        "message": message
    }
    if data is not None:
        response["data"] = data
    return jsonify(response)


def error_response(message: str, status_code: int = 400) -> Tuple[Response, int]:
    """
    Create a standardized error response.
    
    Args:
        message: Error message string
        status_code: HTTP status code (default: 400)
        
    Returns:
        Tuple of (Flask Response object, status code)
    """
    response = {
        "status": "error",
        "message": message
    }
    return jsonify(response), status_code


@app.route("/api/competitions/create", methods=["POST"])
def create_competition():
    """
    Create a new competition with specified problems.
    
    Request format:
    {
        "title": "Competition Title",
        "description": "Competition Description", 
        "problem_ids": ["problem_1", "problem_2"],
        "max_tokens_per_participant": 100000,
        "rules": {...}
    }
    
    Returns:
        Success response with competition details and any not found problems
    """
    try:
        data = request.get_json()
        # Get JSON data from client request
        
        # Parse problems: Load specified problems from problem library
        problems = []                    # List of successfully loaded problems
        not_found_problems = []          # List of problem IDs not found

        # Iterate through problem IDs in the request
        for problem_id in data.get("problem_ids", []):
            # Load problem from problem library
            problem = problem_loader.load_problem(problem_id)
            if not problem:
                # If problem doesn't exist, add to not found list
                not_found_problems.append(problem_id)
            else:
                # If problem exists, add to problems list
                problems.append(problem)
        
        # Validation: At least one valid problem is required
        if not problems:
            return error_response("No valid problems found in library", 404)

        # Create competition: Call data storage layer to create competition object
        with DuckDBStorage(db_path=db_path) as data_storage:
            competition = data_storage.create_competition(
                title=data.get("title", ""),                                    # Competition title
                description=data.get("description", ""),                        # Competition description
                problems=problems,                                              # Problem list
                max_tokens_per_participant=data.get("max_tokens_per_participant", 100000),  # Token limit
                rules=data.get("rules"),                                                # Competition rules
            )
        
        # Build response data
        response_data = {
            "competition": competition.to_dict(),      # Competition details
            "not_found_problems": not_found_problems                       # List of not found problems
        }
        
        # Build success message
        message = "Competition created successfully"
        if not_found_problems:
            # If there are not found problems, mention them in the message
            message += f" (Note: Following problems not found in library: {', '.join(not_found_problems)})"
        
        # Return success response
        return success_response(response_data, message)
    
    except Exception as e:
        logger.error(f"Error creating competition: {e}")
        # Catch all exceptions and return error response
        return error_response(f"Failed to create competition: {str(e)}")

@app.route("/api/competitions/get/<competition_id>", methods=["GET"])
def get_competition(competition_id: str):
    """
    Get competition details by ID.
    
    Args:
        competition_id: Unique competition identifier
        
    Query Parameters:
        include_details: If "true", includes problems, participants, and rankings
        
    Returns:
        Competition details with optional extended information
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            competition = data_storage.get_competition(competition_id)
        if not competition:
            return error_response(f"Competition with ID {competition_id} not found", 404)
        
        include_details = request.args.get("include_details", "false").lower() == "true"
        
        if include_details:
            # Get detailed information from database
            with DuckDBStorage(db_path=db_path) as data_storage:
                problems = data_storage.list_problems(competition_id)
                participants = data_storage.list_participants(competition_id)
                rankings = data_storage.calculate_competition_rankings(competition_id)
            
            # Build detailed response
            response_data = competition.to_dict(include_details=False)
            response_data["problems"] = [p.to_dict() for p in problems]
            response_data["participants"] = [p.to_dict() for p in participants]
            response_data["rankings"] = rankings
            
            return success_response(response_data)
        else:
            return success_response(competition.to_dict(include_details=False))
    except Exception as e:
        return error_response(f"Failed to get competition: {str(e)}")

# API Routes for Competitions
@app.route("/api/competitions/list", methods=["GET"])
def list_competitions():
    """
    List all competitions or active competitions only.
    
    Query Parameters:
        active_only: If "true", returns only active competitions
        
    Returns:
        List of competition objects
    """
    try:
        active_only = request.args.get("active_only", "false").lower() == "true"
        with DuckDBStorage(db_path=db_path) as data_storage:
            competitions = data_storage.list_competitions(active_only=active_only)
        return success_response([comp.to_dict() for comp in competitions])
    except Exception as e:
        return error_response(f"Failed to list competitions: {str(e)}")




@app.route("/api/participants/create/<competition_id>", methods=["POST"])
def create_participant(competition_id: str):
    """
    Create a new participant in a competition.
    
    Args:
        competition_id: Competition identifier
        
    Request Body:
        name: Participant name
        api_base_url: Base URL for participant's API
        
    Returns:
        Participant details with generated ID
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)
    
    try:
        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)
        
        name = data.get("name")
        api_base_url = data.get("api_base_url", "")
        api_key = data.get("api_key", "")
        limit_tokens = data.get("limit_tokens", 100000)
        lambda_value = data.get("lambda_value", 100)
        
        if not name:
            return error_response("Name is required", 400)
        
        # Create participant
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.create_participant(
            competition_id=competition_id,
            name=name,
            api_base_url=api_base_url,
            api_key=api_key,
            limit_tokens=limit_tokens,
            lambda_value=lambda_value
        )
        
        if not participant:
            return error_response("Failed to create participant", 500)
        
        return success_response(
            participant.to_dict(),
            "Participant added successfully"
        )
    
    except Exception as e:
        error_msg = f"Failed to add participant: {str(e)}"
        logger.error(f"[ERROR] {error_msg}")
        import traceback
        logger.error(f"[ERROR] Traceback:")
        traceback.print_exc()
        if 'data' in locals():
            logger.error(f"[ERROR] Request data: {data}")
        return error_response(error_msg)

@app.route("/api/participants/get/<competition_id>/<participant_id>", methods=["GET"])
def get_participant(competition_id: str, participant_id: str):
    """
    Get participant details by ID.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
        
    Query Parameters:
        include_submissions: If "true", includes submission history
        
    Returns:
        Participant details with optional submission history
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.get_participant(competition_id, participant_id)
        if not participant:
            return error_response(f"Participant not found", 404)

        include_submissions = request.args.get("include_submissions", "false").lower() == "true"
        
        if include_submissions:
            # Get submissions from database
            with DuckDBStorage(db_path=db_path) as data_storage:
                submissions = data_storage.list_submissions(
                    competition_id=competition_id, 
                    participant_id=participant_id
                )
            
            # Build detailed response
            response_data = participant.to_dict(include_submissions=False)
            response_data["submissions"] = [s.to_dict() for s in submissions]
            
            return success_response(response_data)
        else:
            return success_response(participant.to_dict(include_submissions=False))
    except Exception as e:
        return error_response(f"Failed to get participant data: {str(e)}", 500)


@app.route("/api/participants/get_solved_problems/<competition_id>/<participant_id>", methods=["GET"])
def get_participant_solved_problems(competition_id: str, participant_id: str):
    """
    Get participant details by ID.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
        
    Query Parameters:
        include_submissions: If "true", includes submission history
        
    Returns:
        Participant details with optional submission history
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.get_participant(competition_id, participant_id)
        if not participant:
            return error_response(f"Participant not found", 404)

        with DuckDBStorage(db_path=db_path) as data_storage:
            submissions = data_storage.list_submissions(
                competition_id=competition_id, 
                participant_id=participant_id
            )
        
        # Extract solved problems from submissions
        solved_problems = []
        for submission in submissions:
            if submission.status == SubmissionStatus.ACCEPTED:
                # Check if this problem is already in solved_problems
                problem_already_solved = any(p["problem_id"] == submission.problem_id for p in solved_problems)
                if not problem_already_solved:
                    solved_problems.append({
                        "problem_id": submission.problem_id,
                        "submission_id": submission.id,
                        "solved_at": submission.submitted_at.isoformat(),
                        "language": submission.language,
                        "score": submission.pass_score
                    })
        
        # Build detailed response
        response_data = participant.to_dict(include_submissions=False)
        response_data["submissions"] = [s.to_dict() for s in submissions]
        response_data["solved_problems"] = solved_problems
        
        return success_response(response_data)
       
    except Exception as e:
        logger.error(f"Failed to get participant data: {e}", exc_info=True)
        return error_response(f"Failed to get participant data: {str(e)}", 500)

def check_termination(competition_id: str, participant_id: str):
    with DuckDBStorage(db_path=db_path) as data_storage:
        participant = data_storage.get_participant(competition_id, participant_id)
    if not participant:
        return error_response("Participant not found")
    if not participant.is_running:
        return error_response(f"Participant is not running, termination_reason: {participant.termination_reason}")
    
    return None
        
# API Routes for Participants
@app.route("/api/participants/list/<competition_id>", methods=["GET"])
def list_participants(competition_id: str):
    """
    List all participants in a competition.
    
    Args:
        competition_id: Competition identifier
        
    Returns:
        List of participant objects
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participants = data_storage.list_participants(competition_id)
        return success_response([p.to_dict() for p in participants])
    except Exception as e:
        return error_response(f"Failed to list participants: {str(e)}")

@app.route("/api/problems/get/<competition_id>/<problem_id>", methods=["GET"])
def get_problem(competition_id: str, problem_id: str):
    """
    Get detailed problem information by ID.
    
    Args:
        competition_id: Competition identifier
        problem_id: Problem identifier
        
    Returns:
        Problem details including description, test cases, and constraints
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            problem = data_storage.get_problem(competition_id, problem_id)
        if not problem:
            return error_response(f"Problem with ID {problem_id} not found", 404)
        
        return success_response(problem.to_dict())
    except Exception as e:
        logger.error(f"Failed to get problem: {e}", exc_info=True)
        return error_response(f"Failed to fetch problem: {str(e)}", 500)

@app.route("/api/problems/list/<competition_id>", methods=["GET"])
def list_problems(competition_id: str):
    """
    List all problems for a competition.
    
    Args:
        competition_id: Competition identifier
        
    Returns:
        List of problems with basic information
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            problems = data_storage.list_problems(competition_id)
        return success_response([p.to_dict() for p in problems])
    except Exception as e:
        logger.error(f"Failed to list problems: {e}", exc_info=True)
        return error_response(f"Failed to list problems: {str(e)}", 500)



# API Routes for Submissions
@app.route("/api/submissions/create/<competition_id>/<participant_id>/<problem_id>", methods=["POST"])
def create_submission(competition_id: str, participant_id: str, problem_id: str):
    """
    Create a new submission for a problem.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
        problem_id: Problem identifier
        
    Request Body:
        code: Source code for the solution
        language: Programming language (default: "cpp")
        
    Returns:
        Submission details with evaluation results
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)
    
    try:
        if check_termination(competition_id, participant_id):
            return error_response("Participant is not running, termination_reason: {participant.termination_reason}")
        
        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)
        
        code = data.get("code")
        language = data.get("language", "cpp")
        
        if not all([participant_id, problem_id, code]):
            return error_response("Missing required fields")
        
        # Create submission with evaluation (handled in storage layer)
        with DuckDBStorage(db_path=db_path, judge=judge) as data_storage:
            submission, problem_name = data_storage.create_submission(
                competition_id=competition_id,
                participant_id=participant_id,
                problem_id=problem_id,
                code=code,
                language=language
            )
        

        if not submission:
            return error_response("Failed to create submission", 500)
        
        
        return success_response({
            "submission_id": submission.id,
            "status": submission.status.value,
            "pass_score": submission.pass_score,
            "penalty": submission.penalty,
            # "participant_score": new_score,
            "problem_name": problem_name,
            "message": "Submission has been evaluated",
            "poll_url": f"/api/competitions/{competition_id}/submissions/{submission.id}",
            "test_results": [tr.to_dict() for tr in submission.test_results],
            "passed_tests": sum(1 for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED),
            "total_tests": len(submission.test_results)
        })
    
    except Exception as e:
        logger.error(f"Failed to create submission: {e}", exc_info=True)
        return error_response(f"Failed to create submission: {str(e)}", 500)

@app.route("/api/submissions/list/<competition_id>", methods=["GET"])
def list_submissions(competition_id: str):
    """
    List submissions in a competition with optional filtering.
    
    Args:
        competition_id: Competition identifier
        
    Query Parameters:
        participant_id: Filter by specific participant (optional)
        problem_id: Filter by specific problem (optional)
        include_code: If "true", includes source code in response
        
    Returns:
        List of submission objects with optional source code
    """
    # participant_id and problem_id are optional, different from the ones in the URL path
    participant_id = request.args.get("participant_id")
    problem_id = request.args.get("problem_id")
    
    with DuckDBStorage(db_path=db_path) as data_storage:
        submissions = data_storage.list_submissions(
            competition_id=competition_id,
            participant_id=participant_id,
            problem_id=problem_id
        )
    
    include_code = request.args.get("include_code", "false").lower() == "true"
    return success_response([s.to_dict(include_code=include_code) for s in submissions])

@app.route("/api/submissions/get/<submission_id>", methods=["GET"])
def get_submission(submission_id: str):
    """
    Get submission details by ID.
    
    Args:
        submission_id: Submission identifier
        
    Query Parameters:
        include_code: If "true", includes source code in response
        
    Returns:
        Submission details with optional source code
    """
    include_code = request.args.get("include_code", "false").lower() == "true"
    with DuckDBStorage(db_path=db_path) as data_storage:
        submission = data_storage.get_submission(submission_id, include_code=include_code)

    if not submission:
        return error_response(f"Submission with ID {submission_id} not found", 404)

    return success_response(submission.to_dict(include_code=include_code))



# API Routes for Rankings
@app.route("/api/rankings/get/<competition_id>", methods=["GET"])
def get_rankings(competition_id: str):
    """
    Get current competition rankings.
    
    Args:
        competition_id: Competition identifier
        
    Returns:
        List of participants ranked by score with detailed statistics
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)
    
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            with DuckDBStorage(db_path=db_path) as data_storage:
                rankings = data_storage.calculate_competition_rankings(competition_id)
                logger.critical(f"rankings: {rankings}")
            if not rankings:
                return error_response(f"Competition with ID {competition_id} not found", 404)
            
            return success_response(rankings)
            
        except Exception as e:
            if "TransactionContext Error: Conflict on update" in str(e) and attempt < max_retries - 1:
                logger.warning(f"Database conflict on rankings request (attempt {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Failed to get rankings after {attempt + 1} attempts: {e}", exc_info=True)
                return error_response(f"Failed to get rankings: {str(e)}", 500)
    
    # If all retries failed, return error
    return error_response("Failed to get rankings after all retries", 500)


# API Route for checking OJ status
@app.route("/api/system/oj-status", methods=["GET"])
def check_oj_status():
    """
    Check online judge connection status.
    
    Returns:
        Connection status and any error information
    """
    try:
        is_connected = judge.test_oj_connection()
        return success_response({"connected": is_connected})
    except Exception as e:
        # Log the error for debugging
        logger.error(f"Error checking OJ status: {str(e)}")
        return success_response({"connected": False, "error": "Unable to check OJ status"})

# Problem library API routes
@app.route("/api/problem-library", methods=["GET"])
def list_problem_library():
    """
    List available problems in the problem library.
    
    Query Parameters:
        level: Filter by problem level (bronze, silver, gold, platinum)
        
    Returns:
        List of problem objects with basic information
    """
    try:
        level = request.args.get("level")
        problem_ids = problem_loader.get_problem_ids(level)
        
        problems = []
        for pid in problem_ids:
            # Load problem using the standardized interface
            problem = problem_loader.load_problem(pid)
            if problem:
                problems.append({
                    "id": problem.id,
                    "title": problem.title,
                    "level": problem.level.value,  # Use enum value for consistency
                    "time_limit_ms": problem.time_limit_ms,
                    "memory_limit_mb": problem.memory_limit_mb,
                    "sample_count": len(problem.sample_cases)
                })
        
        return success_response(problems)
    except Exception as e:
        return error_response(f"Failed to list problem library: {str(e)}")

# Problem retrieval API routes
@app.route("/api/problems/similar", methods=["GET"])
def get_similar_problems():
    """
    Find similar problems using BM25 similarity search.
    
    Query Parameters:
        problem_id: Target problem to find similar problems for
        num_problems: Number of similar problems to return (default: 2)
        competition_id: Competition ID to exclude its problems from search
        
    Returns:
        List of similar problems with similarity scores
    """
    try:
        problem_id = request.args.get('problem_id')
        num_problems = int(request.args.get('num_problems', 2))
        competition_id = request.args.get('competition_id')
        
        if not problem_id:
            return error_response("Problem ID is required")
        
        # Load target problem using standardized interface
        target_problem = problem_loader.load_problem(problem_id)
        if not target_problem:
            return error_response(f"Problem with ID {problem_id} not found", 404)
        
        # Get competition problems to exclude
        excluded_problems = set()
        if competition_id:
            with DuckDBStorage(db_path=db_path) as data_storage:
                problems = data_storage.list_problems(competition_id)
            excluded_problems = set([problem.id for problem in problems])
        
        # Get all available problem IDs
        all_problem_ids = problem_loader.get_problem_ids()
        
        # Create corpus for BM25 using standardized interface
        corpus = []
        problem_ids = []
        for pid in all_problem_ids:
            if pid not in excluded_problems and pid != problem_id:
                problem = problem_loader.load_problem(pid)
                if problem:
                    # Create text for similarity comparison
                    text = f"{problem.description}\n"
                    # Add sample cases if available
                    for case in problem.sample_cases:
                        text += f"Sample Input: {case.input_data}\nSample Output: {case.expected_output}\n"
                corpus.append(text)
                problem_ids.append(pid)
        
        if not corpus:
            return error_response("No problems available for comparison")
        
        # Tokenize corpus
        tokenized_corpus = [doc.split() for doc in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        
        # Create query from target problem
        query = f"{target_problem.description}\n"
        for case in target_problem.sample_cases:
            query += f"Sample Input: {case.input_data}\nSample Output: {case.expected_output}\n"
        tokenized_query = query.split()
        
        # Get top similar problems
        scores = bm25.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:num_problems]
        
        similar_problems = []
        for idx in top_indices:
            pid = problem_ids[idx]
            problem = problem_loader.load_problem(pid)
            if problem:
                similar_problems.append({
                            "id": problem.id,
                            "title": problem.title,
                            "description": problem.description,
                            "level": problem.level.value,
                            "time_limit_ms": problem.time_limit_ms,
                            "memory_limit_mb": problem.memory_limit_mb,
                            "sample_count": len(problem.sample_cases),
                    "similarity_score": float(scores[idx])
                })
        
        return success_response(similar_problems)
        
    except Exception as e:
        return error_response(f"Failed to get similar problems: {str(e)}")

@app.route("/api/textbook/search", methods=["GET"])
def search_textbook():
    """
    Search textbook content for relevant information.
    
    Query Parameters:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)
        
    Returns:
        List of relevant textbook sections matching the query
    """
    try:
        query = request.args.get('query')
        max_results = int(request.args.get('max_results', 5))
        
        if not query:
            return error_response("Search query is required")
        
        # Check if textbook is loaded
        if not textbook_loader.is_loaded():
            return error_response("Textbook content not available", 503)
        
        # Search using standardized interface
        results = textbook_loader.search(query, max_results)
        
        return success_response(results)
        
    except Exception as e:
        return error_response(f"Failed to search textbook: {str(e)}")

@app.route("/api/hints/get/<competition_id>/<participant_id>", methods=["POST"])
def get_hint(competition_id: str, participant_id: str):
    """
    Get a hint for a specific problem.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
        problem_id: Problem identifier
        
    Request Body:
        hint_level: Level of hint to get (1-3)
        
    Returns:
        Hint content and token usage information
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)
    
    try:
        if check_termination(competition_id, participant_id):
            return error_response("Participant is not running, termination_reason: {participant.termination_reason}")

        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)
        
        hint_level = data.get("hint_level", 1)
        hint_knowledge = data.get("hint_knowledge", None)
        problem_id = data.get("problem_id", None)
        problem_difficulty = data.get("problem_difficulty", None)
        
        # Validate hint level
        if hint_level not in [0, 1, 2, 3, 4]:
            return error_response("Invalid hint level. Must be 0, 1, 2, 3, 4.")
        # Process hint request using data storage layer
        with DuckDBStorage(db_path=db_path) as data_storage:
            result = data_storage.process_hint_request(competition_id, participant_id, hint_level, problem_id, hint_knowledge, problem_difficulty)
        
        return success_response(result)
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to get hint: {e}", exc_info=True)
        return error_response(f"Failed to get hint: {str(e)}", 500)
        
# HTTP request endpoint for GenericAPIAgent
@app.route("/api/agent/call/<competition_id>/<participant_id>", methods=["POST"])
def generate_response(competition_id: str, participant_id: str):
    """
    Direct request forwarding endpoint for debugging.
    
    This endpoint directly forwards the received request to the target LLM API
    without any processing, useful for debugging request format issues.
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)
    
    try:
        if check_termination(competition_id, participant_id):
            return error_response("Participant is not running, termination_reason: {participant.termination_reason}")
        
        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)
        
        # Process request using data storage layer
        with DuckDBStorage(db_path=db_path) as data_storage:
            result = data_storage.process_agent_request(competition_id, participant_id, data)
        
        # Return response in expected format (array wrapper for compatibility)
        return jsonify([result["content"]]), result["status_code"]
        
    except ValueError as e:
        logger.error(f"ValueError in generate_response: {str(e)}")
        return error_response(str(e), 404)
    except Exception as e:
        import traceback
        error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
        logger.error(f"Exception in generate_response: {str(e)} at line {error_line}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response(f"Agent request failed: {str(e)} (line {error_line})")


@app.route("/api/stream_agent/call/<competition_id>/<participant_id>", methods=["POST"])
def stream_generate_response(competition_id: str, participant_id: str):
    """
    Call the streaming agent with a request.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
        
    Request Body:
        request_data: Data to send to the agent
        
    Returns:
        Streaming agent response
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)
    
    try:
        if check_termination(competition_id, participant_id):
            return error_response("Participant is not running, termination_reason: {participant.termination_reason}")
        
        data = request.get_json()
        if not data:
            return error_response("No data provided")

        # Process streaming request using data storage layer
        with DuckDBStorage(db_path=db_path) as data_storage:
            result = data_storage.process_stream_agent_request(competition_id, participant_id, data)
        
        # Return streaming response in expected format (array wrapper for compatibility)
        structured_response = [
            result["reasoning_content"],
            result["content"],
            result["usage_info"],
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"]
        ]
        
        return jsonify(structured_response), result["status_code"]
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        import traceback
        error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
        return error_response(f"Streaming agent request failed: {str(e)} (line {error_line})")

@app.route("/api/participants/terminate/<competition_id>/<participant_id>", methods=["POST"])
def terminate_participant(competition_id: str, participant_id: str):
    """
    Terminate a participant in a competition.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
    
    Request format:
    {
        "reason": "Termination reason (optional, defaults to 'manual_termination')"
    }
    
    Common termination reasons:
    - "manual_termination": Manual termination by admin
    - "out_of_tokens": Participant ran out of tokens
    - "error": System error occurred
    - "timeout": Participant exceeded time limits
    - "violation": Rule violation
    
    Returns:
        Success response with termination reason
    """
    try:
        data = request.get_json() or {}
        reason = data.get("reason", "manual_termination")
        
        # Validate reason
        if not isinstance(reason, str):
            return error_response("Reason must be a string")
        
        
        # Terminate participant using data storage layer
        with DuckDBStorage(db_path=db_path) as data_storage:
            data_storage.terminate_participant(competition_id, participant_id, reason)
        
        return success_response(
            message=f"Participant {participant_id} terminated successfully",
            data={"termination_reason": reason}
        )
        
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        import traceback
        error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
        return error_response(f"Failed to terminate participant: {str(e)} (line {error_line})")


@app.route("/api/participants/status/<competition_id>/<participant_id>", methods=["GET"])
def get_participant_status(competition_id: str, participant_id: str):
    """
    Get participant termination status and reason.
    
    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier
        
    Returns:
        Participant status including running state, termination reason, tokens, and score
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.get_participant(competition_id, participant_id)
        if not participant:
            return error_response(f"Participant not found", 404)
        
        status_data = {
            "is_running": participant.is_running,
            "termination_reason": participant.termination_reason,
            "remaining_tokens": participant.remaining_tokens,
            "score": participant.score
        }
        
        return success_response(status_data)
        
    except Exception as e:
        return error_response(f"Failed to get participant status: {str(e)}")


@app.route("/api/participants/terminated/<competition_id>", methods=["GET"])
def list_terminated_participants(competition_id: str):
    """
    Get list of terminated participants in a competition.
    
    Args:
        competition_id: Competition identifier
        
    Returns:
        List of terminated participants with termination reasons and final statistics
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participants = data_storage.list_participants(competition_id)
        
        # Filter terminated participants
        terminated_participants = [
            {
                "id": p.id,
                "name": p.name,
                "termination_reason": p.termination_reason,
                "score": p.score,
                "remaining_tokens": p.remaining_tokens,
                "submission_count": p.submission_count,
                "accepted_count": p.accepted_count
            }
            for p in participants if not p.is_running
        ]
        
        return success_response(terminated_participants)
        
    except Exception as e:
        return error_response(f"Failed to get terminated participants: {str(e)}")


# Main entrypoint
def run_api(host: str = "0.0.0.0", port: int = 5000, debug: bool = False, config=None):
    """
    Start the Flask API server.
    
    Args:
        host: Host address to bind to (default: "0.0.0.0")
        port: Port number to bind to (default: 5000)
        debug: Enable debug mode (default: False)
        config: Configuration manager instance (optional)
    """
    global global_rate_limiter, problem_loader, textbook_loader, db_path, judge
    
    
    if port:
        db_path = f"data/competition_{port}.duckdb"
    else:
        db_path = "data/competition_5000.duckdb"

    # Initialize configuration if provided
    if config:
        # Configure rate limiter
        rate_limit_config = config.get_section("rate_limit")
        min_interval = rate_limit_config.get("min_interval", 0.05)
        global_rate_limiter = GlobalRateLimiter(min_interval)
        logger.info(f"Configured rate limiter with interval: {min_interval}s")
        
        judge = Judge(config.get_section("oj").get("endpoint"))

        # Configure problem loader with custom data directory
        data_config = config.get_section("data")
        problem_data_dir = data_config.get("problem_data_dir", "dataset/datasets/usaco_2025")
        textbook_data_dir = data_config.get("textbook_data_dir", "dataset/textbooks")
        
        # Always reinitialize loaders with configured paths
        problem_loader = USACOProblemLoader(data_path=problem_data_dir)
        logger.info(f"Initialized problem loader with data path: {problem_data_dir}")
        
        # Verify problem loader initialization
        problem_count = len(problem_loader.problems_dict)
        logger.info(f"Loaded {problem_count} problems from problem library")
        if problem_count == 0:
            logger.warning("No problems loaded! Check data path and file permissions")
        
        textbook_loader = TextbookLoader(data_path=textbook_data_dir)
        logger.info(f"Initialized textbook loader with data path: {textbook_data_dir}")
        
        logger.info("Server configuration applied successfully")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_api(debug=True)