import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from flask import Flask, request, jsonify, Response
import threading
from queue import Queue
import time
import os

from models import Competition, Participant, Problem, Submission, TestCase, SubmissionStatus, Level, generate_id
from storage import DataStorage
from judge import Judge
from problem_loader import USACOProblemLoader
from rank_bm25 import BM25Okapi

# Initialize data storage and judge
data_storage = DataStorage()
judge = Judge()

# Initialize problem library loader
problem_loader = USACOProblemLoader()

# Create Flask app
app = Flask(__name__)


# Helper functions
def success_response(data: Any = None, message: str = "Success") -> Response:
    """Create a success response"""
    response = {
        "status": "success",
        "message": message
    }
    if data is not None:
        response["data"] = data
    return jsonify(response)


def error_response(message: str, status_code: int = 400) -> Tuple[Response, int]:
    """Create an error response"""
    return jsonify({
        "status": "error",
        "message": message
    }), status_code


# API Routes for Competitions
@app.route("/api/competitions", methods=["GET"])
def list_competitions():
    """List all competitions"""
    active_only = request.args.get("active_only", "false").lower() == "true"
    competitions = data_storage.list_competitions(active_only=active_only)
    return success_response([comp.to_dict() for comp in competitions])


@app.route("/api/competitions/<competition_id>", methods=["GET"])
def get_competition(competition_id: str):
    """Get details of a specific competition"""
    competition = data_storage.get_competition(competition_id)
    if not competition:
        return error_response(f"Competition with ID {competition_id} not found", 404)
    
    include_details = request.args.get("include_details", "false").lower() == "true"
    return success_response(competition.to_dict(include_details=include_details))


@app.route("/api/competitions", methods=["POST"])
def create_competition():
    """Create a new competition"""
    try:
        data = request.get_json()
        
        # Parse problems
        problems = []
        not_found_problems = []
        for problem_id in data.get("problem_ids", []):
            # Load problem from library
            problem = problem_loader.load_problem(problem_id)
            if not problem:
                not_found_problems.append(problem_id)
            else:
                problems.append(problem)
        
        if not problems:
            return error_response("No valid problems found in library", 404)
        
        # Create competition
        competition = data_storage.create_competition(
            title=data.get("title", ""),
            description=data.get("description", ""),
            problems=problems,
            max_tokens_per_participant=data.get("max_tokens_per_participant", 100000),
            rules=data.get("rules")
        )
        
        response_data = {
            "competition": competition.to_dict(include_details=True),
            "not_found_problems": not_found_problems
        }
        
        message = "Competition created successfully"
        if not_found_problems:
            message += f" (Note: Following problems not found in library: {', '.join(not_found_problems)})"
        
        return success_response(response_data, message)
    
    except Exception as e:
        return error_response(f"Failed to create competition: {str(e)}")


# API Routes for Participants
@app.route("/api/competitions/<competition_id>/participants", methods=["GET"])
def list_participants(competition_id: str):
    """List all participants in a competition"""
    competition = data_storage.get_competition(competition_id)
    if not competition:
        return error_response(f"Competition with ID {competition_id} not found", 404)
    
    return success_response([p.to_dict() for p in competition.participants])


@app.route("/api/competitions/<competition_id>/participants", methods=["POST"])
def add_participant(competition_id: str):
    """Add a participant to a competition"""
    try:
        data = request.get_json()
        name = data.get("name", "")
        
        if not name:
            return error_response("Participant name is required")
        
        participant = data_storage.add_participant(competition_id, name)
        if not participant:
            return error_response(f"Competition with ID {competition_id} not found", 404)
        
        return success_response(
            participant.to_dict(),
            "Participant added successfully"
        )
    
    except Exception as e:
        return error_response(f"Failed to add participant: {str(e)}")


@app.route("/api/competitions/<competition_id>/participants/<participant_id>", methods=["GET"])
def get_participant(competition_id: str, participant_id: str):
    """Get details of a specific participant"""
    participant = data_storage.get_participant(competition_id, participant_id)
    if not participant:
        return error_response(f"Participant not found", 404)
    
    include_submissions = request.args.get("include_submissions", "false").lower() == "true"
    return success_response(participant.to_dict(include_submissions=include_submissions))


# API Routes for Problems
@app.route("/api/competitions/<competition_id>/problems", methods=["GET"])
def list_problems(competition_id: str):
    """List all problems in a competition"""
    competition = data_storage.get_competition(competition_id)
    if not competition:
        return error_response(f"Competition with ID {competition_id} not found", 404)
    
    problems = []
    for p in competition.problems:
        problems.append({
            "id": p.id,
            "title": p.title,
            "level": p.level.value,
            "first_to_solve": p.first_to_solve
        })
    
    return success_response(problems)


@app.route("/api/competitions/<competition_id>/problems/<problem_id>", methods=["GET"])
def get_problem(competition_id: str, problem_id: str):
    """Get details of a specific problem"""
    competition = data_storage.get_competition(competition_id)
    if not competition:
        return error_response(f"Competition with ID {competition_id} not found", 404)
    
    problem = competition.get_problem(problem_id)
    if not problem:
        return error_response(f"Problem with ID {problem_id} not found", 404)
    
    # include_test_cases = request.args.get("include_test_cases", "false").lower() == "true"
    include_test_cases = False
    return success_response(problem.to_dict(include_test_cases=include_test_cases))


# API Routes for Submissions
@app.route("/api/competitions/<competition_id>/submit", methods=["POST"])
def create_submission(competition_id: str):
    """Create a new submission"""
    try:
        data = request.get_json()
        if not data:
            return error_response("No data provided")
        
        participant_id = data.get("participant_id")
        problem_id = data.get("problem_id")
        code = data.get("code")
        language = data.get("language", "cpp")
        
        if not all([participant_id, problem_id, code]):
            return error_response("Missing required fields")
        
        # Get competition and validate
        competition = data_storage.get_competition(competition_id)
        if not competition:
            return error_response("Competition not found")
        
        # Create submission first to get its ID
        submission = data_storage.create_submission(
            competition_id=competition_id,
            participant_id=participant_id,
            problem_id=problem_id,
            code=code,
            language=language
        )
        
        if not submission:
            return error_response("Failed to create submission")
            
        # Direct evaluation instead of using queue
        problem = competition.get_problem(problem_id)
        if not problem:
            return error_response("Problem not found")
            
        judge = Judge()
        submission = judge.evaluate_submission(submission, problem, competition)

        # Update submission in storage
        # submission = data_storage.update_submission(submission)
        
        # If this is an accepted solution and the first for this problem,
        # update the problem's first_to_solve attribute and add bonus
        if submission.status == SubmissionStatus.ACCEPTED:
            for problem in competition.problems:
                if problem.id == submission.problem_id:
                    if problem.first_to_solve is None:
                        problem.first_to_solve = submission.participant_id
                        # Add bonus for first AC
                        bonus = competition.rules.get("bonus_for_first_ac", 100)
                        submission.score += bonus
                    break
        data_storage.submissions[submission.id] = submission
        data_storage._save_submission(submission)

        # Get participant and update their submissions
        participant = competition.get_participant(participant_id)
        if participant:
            # if not any(s.id == submission.id for s in participant.submissions):
            #     participant.submissions.append(submission)
            participant.submissions.append(submission)
            participant.calculate_score()
            data_storage.update_competition(competition)
        
        return success_response({
            "submission_id": submission.id,
            "status": submission.status.value,
            "score": submission.score,
            "penalty": submission.penalty,
            "participant_score": participant.score if participant else 0,
            "message": "Submission has been evaluated",
            "poll_url": f"/api/competitions/{competition_id}/submissions/{submission.id}",
            "test_results": [tr.to_dict() for tr in submission.test_results],
            "passed_tests": sum(1 for tr in submission.test_results if tr.status == SubmissionStatus.ACCEPTED),
            "total_tests": len(problem.test_cases)
        })
    
    except Exception as e:
        return error_response(f"Failed to process submission: {str(e)}")


@app.route("/api/competitions/<competition_id>/submissions", methods=["GET"])
def list_submissions(competition_id: str):
    """List submissions with optional filters"""
    participant_id = request.args.get("participant_id")
    problem_id = request.args.get("problem_id")
    
    submissions = data_storage.list_submissions(
        competition_id=competition_id,
        participant_id=participant_id,
        problem_id=problem_id
    )
    
    include_code = request.args.get("include_code", "false").lower() == "true"
    return success_response([s.to_dict(include_code=include_code) for s in submissions])


@app.route("/api/submissions/<submission_id>", methods=["GET"])
def get_submission(submission_id: str):
    """Get details of a specific submission"""
    submission = data_storage.get_submission(submission_id)
    if not submission:
        return error_response(f"Submission with ID {submission_id} not found", 404)
    
    include_code = request.args.get("include_code", "false").lower() == "true"
    return success_response(submission.to_dict(include_code=include_code))


# API Routes for Rankings
@app.route("/api/competitions/<competition_id>/rankings", methods=["GET"])
def get_rankings(competition_id: str):
    """Get the current rankings for a competition"""
    rankings = data_storage.calculate_rankings(competition_id)
    if not rankings:
        return error_response(f"Competition with ID {competition_id} not found", 404)
    
    return success_response(rankings)


# API Route for checking OJ status
@app.route("/api/system/oj-status", methods=["GET"])
def check_oj_status():
    """Check if the Online Judge system is available"""
    is_connected = judge.test_oj_connection()
    return success_response({"connected": is_connected})


# Problem library API routes
@app.route("/api/problem-library", methods=["GET"])
def list_problem_library():
    """List all problems in the library"""
    level = request.args.get("level")
    problem_ids = problem_loader.get_problem_ids(level)
    
    problems = []
    for pid in problem_ids:
        problem_data = problem_loader.problems_dict.get(pid, {})
        problems.append({
            "id": pid,
            "title": problem_data.get("name", ""),
            "level": problem_data.get("problem_level", "None")
        })
    
    return success_response(problems)

@app.route("/api/problem-library/<problem_id>", methods=["GET"])
def get_problem_from_library(problem_id: str):
    """Get detailed information about a specific problem from the library"""
    problem = problem_loader.load_problem(problem_id)
    if not problem:
        return error_response(f"Problem with ID {problem_id} not found in library", 404)
    
    return success_response(problem.to_dict(include_test_cases=False))

@app.route("/api/competitions/<competition_id>/import-problems", methods=["POST"])
def import_problems_to_competition(competition_id: str):
    """Import problems from the library to a competition"""
    try:
        data = request.get_json()
        problem_ids = data.get("problem_ids", [])
        
        if not problem_ids:
            return error_response("No problem IDs provided for import")
        
        competition = data_storage.get_competition(competition_id)
        if not competition:
            return error_response(f"Competition with ID {competition_id} not found", 404)
        
        count = problem_loader.import_problems_to_competition(competition, problem_ids)
        data_storage.update_competition(competition)
        
        return success_response(
            {"imported_count": count},
            f"Successfully imported {count} problems to the competition"
        )
    
    except Exception as e:
        return error_response(f"Failed to import problems: {str(e)}")


# Problem retrieval API routes
@app.route("/api/problems/similar", methods=["GET"])
def get_similar_problems():
    """Get similar problems based on problem ID"""
    try:
        problem_id = request.args.get('problem_id')
        num_problems = int(request.args.get('num_problems', 2))
        competition_id = request.args.get('competition_id')
        
        if not problem_id:
            return error_response("Problem ID is required")
        
        # Load problem dictionary
        problem_dict_path = os.path.join("data", "datasets", "usaco_v2_dict.json")
        try:
            with open(problem_dict_path, 'r') as f:
                problem_dict = json.load(f)
        except FileNotFoundError:
            return error_response("Problem dictionary not found", 404)
        
        # if problem_id not in problem_dict:
        #     return error_response(f"Problem with ID {problem_id} not found", 404)
        
        # Get competition problems to exclude
        excluded_problems = set()
        if competition_id:
            competition = data_storage.get_competition(competition_id)
            if competition:
                excluded_problems = set([problem.id for problem in competition.problems])
        
        # Create corpus for BM25
        corpus = []
        problem_ids = []
        for pid, problem in problem_dict.items():
            if pid not in excluded_problems:
                text = f"{problem['description']}\nSolution: \n{problem['solution']}\n"
                corpus.append(text)
                problem_ids.append(pid)
        
        if not corpus:
            return error_response("No problems available for comparison")
        
        # Tokenize corpus
        tokenized_corpus = [doc.split() for doc in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        
        # Create query from target problem
        target_problem = problem_dict[problem_id]
        query = f"{target_problem['description']}\nSolution: \n{target_problem['solution']}\n"
        tokenized_query = query.split()
        
        # Get top similar problems
        scores = bm25.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:num_problems]
        
        similar_problems = []
        for idx in top_indices:
            pid = problem_ids[idx]
            problem = problem_dict[pid]
            similar_problems.append({
                "id": pid,
                "title": problem.get('name', ''),
                "description": problem['description'],
                "solution": problem['solution'],
                "similarity_score": float(scores[idx])
            })
        
        return success_response(similar_problems)
        
    except Exception as e:
        return error_response(f"Failed to get similar problems: {str(e)}")

@app.route("/api/textbook/search", methods=["GET"])
def search_textbook():
    """Search textbook content based on query"""
    try:
        query = request.args.get('query')
        max_results = int(request.args.get('max_results', 2))
        
        if not query:
            return error_response("Search query is required")
        
        # Load textbook content
        textbook_path = "data/corpuses/cpbook_v2.json"
        try:
            with open(textbook_path, 'r') as f:
                textbook = json.load(f)
        except FileNotFoundError:
            return error_response("Textbook content not found", 404)
        
        # Create corpus for BM25
        corpus = [article['full_article'] for article in textbook]
        tokenized_corpus = [doc.split() for doc in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        
        # Search
        tokenized_query = query.split()
        scores = bm25.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:max_results]
        
        results = []
        for idx in top_indices:
            article = textbook[idx]
            results.append({
                "title": article.get('title', ''),
                "content": article['full_article'],
                "relevance_score": float(scores[idx])
            })
        
        return success_response(results)
        
    except Exception as e:
        return error_response(f"Failed to search textbook: {str(e)}")

# Main entrypoint
def run_api(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the API server"""
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_api(debug=True)