import hashlib
import hmac
import os
import time
import threading
import traceback
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, Response, jsonify, request
from rank_bm25 import BM25Okapi

# AgentRequest, AgentResponse, TokenUsage classes were removed with agent_interface.py
from ..engine.storage import DuckDBStorage
from ..engine.judge import Judge
from ..models.models import Case, SubmissionStatus
from ..benchmark.agent_profile import AGENT_PROFILE_SCHEMA, normalize_agent_profile
from ..benchmark.metrics import build_intelligence_report
from ..benchmark.reporting import render_by_format, save_report_bundle
from ..utils.hydro_client import HydroClient
from ..utils.problem_loader import USACOProblemLoader
from ..utils.textbook_loader import TextbookLoader
from ..utils.logger_config import get_logger


# Get logger
logger = get_logger("server")

# Initialize lazily during run_api so config/env is available first.
problem_loader: Optional[USACOProblemLoader] = None
textbook_loader: Optional[TextbookLoader] = None
judge: Optional[Judge] = None
db_path = "data/competition_5000.duckdb"

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
INT32_MAX = (2**31) - 1
INT64_MAX = (2**63) - 1


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

    parts = path.split(".")
    current = data

    for part in parts:
        if "[" in part:
            key, index = part.split("[")
            index = int(index.rstrip("]"))
            if (
                key not in current
                or not isinstance(current[key], (list, tuple))
                or index >= len(current[key])
            ):
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
    response = {"status": "success", "message": message}
    if data is not None:
        response["data"] = data
    return jsonify(response)


def error_response(
    message: str, status_code: int = 400, data: Any = None
) -> Tuple[Response, int]:
    """
    Create a standardized error response.

    Args:
        message: Error message string
        status_code: HTTP status code (default: 400)

    Returns:
        Tuple of (Flask Response object, status code)
    """
    response = {"status": "error", "message": message}
    if data is not None:
        response["data"] = data
    return jsonify(response), status_code


def _parse_bounded_int(
    value: Any,
    *,
    field_name: str,
    default: Optional[int] = None,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    if value is None:
        if default is None:
            raise ValueError(f"{field_name} is required")
        parsed = int(default)
    elif isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer, got {value!r}")
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be an integer, got {value!r}")
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty")
        try:
            numeric = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc
        if numeric != numeric.to_integral_value():
            raise ValueError(f"{field_name} must be an integer, got {value!r}")
        parsed = int(numeric)
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc

    if min_value is not None and parsed < min_value:
        raise ValueError(f"{field_name} must be >= {min_value}, got {parsed}")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{field_name} must be <= {max_value}, got {parsed}")
    return parsed


def _build_participant_timing_state(participant: Any) -> Dict[str, Any]:
    """Build delivery-time state visible to participants during and after runtime."""
    if participant is None:
        return {
            "elapsed_time_seconds": 0,
            "delivery_time_seconds": 0,
            "delivery_time_multiplier": 1.0,
            "delivery_time_credit": 0.0,
            "delivery_time_settled": False,
            "consumed_credit": 0.0,
        }

    elapsed_seconds = 0
    if hasattr(participant, "get_elapsed_time_seconds"):
        try:
            elapsed_seconds = int(participant.get_elapsed_time_seconds())
        except Exception:
            elapsed_seconds = 0

    is_running = bool(getattr(participant, "is_running", True))
    settled_seconds = (
        int(getattr(participant, "delivery_time_seconds", 0) or 0) if not is_running else 0
    )
    settled_credit = (
        float(getattr(participant, "delivery_time_credit", 0.0) or 0.0)
        if not is_running
        else 0.0
    )
    multiplier = float(getattr(participant, "delivery_time_multiplier", 1.0) or 1.0)

    consumed_credit = (
        float(participant.get_consumed_credit())
        if hasattr(participant, "get_consumed_credit")
        else float(
            (getattr(participant, "consumed_tokens", 0) or 0)
            + (getattr(participant, "submission_penalty", 0) or 0)
            + settled_credit
        )
    )

    return {
        "elapsed_time_seconds": max(0, elapsed_seconds),
        "delivery_time_seconds": max(0, settled_seconds),
        "delivery_time_multiplier": max(0.0, multiplier),
        "delivery_time_credit": max(0.0, settled_credit),
        "delivery_time_settled": (not is_running),
        "consumed_credit": max(0.0, consumed_credit),
    }


def _inject_timing_state(data: Dict[str, Any], participant: Any) -> Dict[str, Any]:
    payload = dict(data or {})
    payload["timing_state"] = _build_participant_timing_state(participant)
    return payload


def _apply_timing_headers(response: Response, participant: Any) -> Response:
    timing_state = _build_participant_timing_state(participant)
    response.headers["X-USACO-Elapsed-Time-Seconds"] = str(
        timing_state["elapsed_time_seconds"]
    )
    response.headers["X-USACO-Delivery-Time-Seconds"] = str(
        timing_state["delivery_time_seconds"]
    )
    response.headers["X-USACO-Delivery-Time-Multiplier"] = str(
        timing_state["delivery_time_multiplier"]
    )
    response.headers["X-USACO-Delivery-Time-Credit"] = str(
        timing_state["delivery_time_credit"]
    )
    response.headers["X-USACO-Delivery-Time-Settled"] = (
        "1" if timing_state["delivery_time_settled"] else "0"
    )
    return response


def _parse_participant_payload(
    payload: Dict[str, Any],
    *,
    default_limit_tokens: int = 100000,
    default_lambda_value: int = 100,
) -> Dict[str, Any]:
    """Normalize participant creation payload and validate required fields."""
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("Name is required")

    api_base_url = str(payload.get("api_base_url", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()

    limit_tokens = _parse_bounded_int(
        payload.get("limit_tokens", default_limit_tokens),
        field_name="limit_tokens",
        min_value=0,
        max_value=INT64_MAX,
    )
    lambda_value = _parse_bounded_int(
        payload.get("lambda_value", default_lambda_value),
        field_name="lambda_value",
        min_value=0,
        max_value=INT32_MAX,
    )

    return {
        "name": name,
        "api_base_url": api_base_url,
        "api_key": api_key,
        "limit_tokens": limit_tokens,
        "lambda_value": lambda_value,
        "agent_profile": normalize_agent_profile(payload.get("agent_profile")),
    }


def _gateway_secret() -> str:
    value = (os.environ.get("USACOARENA_GATEWAY_SECRET", "") or "").strip()
    if value:
        return value
    return "usacoarena-gateway-dev-secret"


def _build_participant_gateway_key(competition_id: str, participant_id: str) -> str:
    message = f"{competition_id}:{participant_id}".encode("utf-8")
    digest = hmac.new(_gateway_secret().encode("utf-8"), message, hashlib.sha256).hexdigest()
    return digest


def _extract_bearer_token(headers: Dict[str, str]) -> str:
    auth_value = headers.get("Authorization", "")
    if not auth_value:
        return ""
    prefix = "Bearer "
    if auth_value.startswith(prefix):
        return auth_value[len(prefix):].strip()
    return ""


def _parse_bool_arg(name: str, default: bool = False) -> bool:
    raw = request.args.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _extract_intelligence_weight_overrides() -> Dict[str, float]:
    overrides: Dict[str, float] = {}
    for key in ("solve", "efficiency", "reliability", "speed", "coverage"):
        raw = request.args.get(f"weight_{key}")
        if raw is None:
            continue
        try:
            overrides[key] = float(raw)
        except ValueError:
            continue
    return overrides


@app.route("/health", methods=["GET"])
def health_check() -> Response:
    """Shallow health endpoint for process supervisors."""

    return success_response({"server": "ok"}, "healthy")


@app.route("/api/agent-profiles/schema", methods=["GET"])
def get_agent_profile_schema() -> Response:
    """Return the canonical agent integration schema for external runtimes."""

    return success_response(AGENT_PROFILE_SCHEMA)


@app.route("/api/metrics/intelligence/<competition_id>", methods=["GET"])
def get_intelligence_metrics(competition_id: str):
    """Compute and return benchmark intelligence metrics for a competition."""

    try:
        output_format = str(request.args.get("format", "json") or "json").strip().lower()
        include_test_points = _parse_bool_arg("include_test_points", False)
        weight_overrides = _extract_intelligence_weight_overrides()

        with DuckDBStorage(db_path=db_path) as data_storage:
            competition = data_storage.get_competition(competition_id)
            if not competition:
                return error_response(
                    f"Competition with ID {competition_id} not found", 404
                )
            participants = data_storage.list_participants(competition_id)
            rankings = data_storage.calculate_competition_rankings(competition_id)

        arena_rank_map = {
            str(item.get("participant_id")): int(item.get("rank", 0))
            for item in rankings
            if isinstance(item, dict)
        }

        report = build_intelligence_report(
            competition,
            participants,
            arena_rank_map=arena_rank_map,
            include_test_points=include_test_points,
            weight_overrides=weight_overrides or None,
        )

        if output_format in {"json", "application/json"}:
            return success_response(report)

        rendered = render_by_format(report, output_format)
        if output_format == "csv":
            return Response(rendered, mimetype="text/csv")
        if output_format in {"md", "markdown"}:
            return Response(rendered, mimetype="text/markdown")
        if output_format == "html":
            return Response(rendered, mimetype="text/html")
        return Response(rendered, mimetype="text/plain")
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(f"Failed to compute intelligence metrics: {exc}", exc_info=True)
        return error_response(f"Failed to compute intelligence metrics: {str(exc)}", 500)


@app.route("/api/reports/intelligence/<competition_id>", methods=["GET"])
def generate_intelligence_report(competition_id: str):
    """Generate and save intelligence report artifacts for easy inspection."""

    try:
        include_test_points = _parse_bool_arg("include_test_points", True)
        output_dir_arg = str(request.args.get("output_dir", "") or "").strip()
        output_dir = (
            Path(output_dir_arg)
            if output_dir_arg
            else Path("reports") / "intelligence" / competition_id
        )

        weight_overrides = _extract_intelligence_weight_overrides()

        with DuckDBStorage(db_path=db_path) as data_storage:
            competition = data_storage.get_competition(competition_id)
            if not competition:
                return error_response(
                    f"Competition with ID {competition_id} not found", 404
                )
            participants = data_storage.list_participants(competition_id)
            rankings = data_storage.calculate_competition_rankings(competition_id)

        arena_rank_map = {
            str(item.get("participant_id")): int(item.get("rank", 0))
            for item in rankings
            if isinstance(item, dict)
        }

        report = build_intelligence_report(
            competition,
            participants,
            arena_rank_map=arena_rank_map,
            include_test_points=include_test_points,
            weight_overrides=weight_overrides or None,
        )
        artifacts = save_report_bundle(report, output_dir)
        return success_response(
            {
                "competition_id": competition_id,
                "output_dir": str(output_dir),
                "artifacts": artifacts,
                "view_urls": {
                    "json": f"/api/metrics/intelligence/{competition_id}?format=json",
                    "csv": f"/api/metrics/intelligence/{competition_id}?format=csv",
                    "markdown": f"/api/metrics/intelligence/{competition_id}?format=markdown",
                    "html": f"/api/metrics/intelligence/{competition_id}?format=html",
                },
            },
            "Intelligence report generated",
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(f"Failed to generate intelligence report: {exc}", exc_info=True)
        return error_response(f"Failed to generate intelligence report: {str(exc)}", 500)


# API Routes for Competitions
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
        if not isinstance(data, dict):
            return error_response("No JSON data provided", 400)

        max_tokens_per_participant = _parse_bounded_int(
            data.get("max_tokens_per_participant"),
            field_name="max_tokens_per_participant",
            default=100000,
            min_value=0,
            max_value=INT64_MAX,
        )
        # Get JSON data from client request

        # Parse problems: Load specified problems from problem library
        problems = []  # List of successfully loaded problems
        not_found_problems = []  # List of problem IDs not found

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
                title=data.get("title", ""),  # Competition title
                description=data.get("description", ""),  # Competition description
                problems=problems,  # Problem list
                max_tokens_per_participant=max_tokens_per_participant,  # Token limit
                rules=data.get("rules"),  # Competition rules
            )

        # Build response data
        response_data = {
            "competition": competition.to_dict(),  # Competition details
            "not_found_problems": not_found_problems,  # List of not found problems
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


# API Routes for Competitions
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
            return error_response(
                f"Competition with ID {competition_id} not found", 404
            )

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


# API Routes for Participants
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

        try:
            participant_payload = _parse_participant_payload(data)
        except ValueError as exc:
            return error_response(str(exc), 400)

        # Create participant
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.create_participant(
                competition_id=competition_id,
                name=participant_payload["name"],
                api_base_url=participant_payload["api_base_url"],
                api_key=participant_payload["api_key"],
                limit_tokens=participant_payload["limit_tokens"],
                lambda_value=participant_payload["lambda_value"],
                agent_profile=participant_payload["agent_profile"],
            )

        if not participant:
            return error_response("Failed to create participant", 500)

        return success_response(participant.to_dict(), "Participant added successfully")

    except Exception as e:
        error_msg = f"Failed to add participant: {str(e)}"
        logger.error(f"[ERROR] {error_msg}")
        logger.error("[ERROR] Traceback:")
        traceback.print_exc()
        if "data" in locals():
            logger.error(f"[ERROR] Request data: {data}")
        return error_response(error_msg)


@app.route("/api/participants/create_batch/<competition_id>", methods=["POST"])
def create_participants_batch(competition_id: str):
    """
    Batch create participants in a competition.

    Request format:
    {
        "default_limit_tokens": 100000,
        "default_lambda_value": 100,
        "participants": [
            {
                "name": "agent-1",
                "api_base_url": "https://gateway.example/v1",
                "api_key": "sk-xxx",
                "limit_tokens": 100000,
                "lambda_value": 100,
                "agent_profile": {
                    "agent_type": "codex",
                    "transport": "openai_compatible_http",
                    "capabilities": ["submit_solution", "test_code"],
                    "mcp": {"enabled": False, "servers": []}
                }
            }
        ]
    }
    """
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)

    try:
        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)

        participants_data = data.get("participants")
        if not isinstance(participants_data, list) or not participants_data:
            return error_response("participants must be a non-empty list", 400)

        default_limit_tokens = _parse_bounded_int(
            data.get("default_limit_tokens"),
            field_name="default_limit_tokens",
            default=100000,
            min_value=0,
            max_value=INT64_MAX,
        )
        default_lambda_value = _parse_bounded_int(
            data.get("default_lambda_value"),
            field_name="default_lambda_value",
            default=100,
            min_value=0,
            max_value=INT32_MAX,
        )

        created: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        with DuckDBStorage(db_path=db_path) as data_storage:
            for index, item in enumerate(participants_data):
                if not isinstance(item, dict):
                    errors.append(
                        {
                            "index": index,
                            "name": None,
                            "message": "participant entry must be an object",
                        }
                    )
                    continue

                try:
                    payload = _parse_participant_payload(
                        item,
                        default_limit_tokens=default_limit_tokens,
                        default_lambda_value=default_lambda_value,
                    )
                    participant = data_storage.create_participant(
                        competition_id=competition_id,
                        name=payload["name"],
                        api_base_url=payload["api_base_url"],
                        api_key=payload["api_key"],
                        limit_tokens=payload["limit_tokens"],
                        lambda_value=payload["lambda_value"],
                        agent_profile=payload["agent_profile"],
                    )
                    if not participant:
                        raise ValueError("Failed to create participant")
                    created.append(participant.to_dict())
                except Exception as exc:  # pylint: disable=broad-except
                    errors.append(
                        {
                            "index": index,
                            "name": item.get("name"),
                            "message": str(exc),
                        }
                    )

        message = (
            f"Batch participant creation completed: {len(created)} created, {len(errors)} failed"
        )
        return success_response({"created": created, "errors": errors}, message)

    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:  # pylint: disable=broad-except
        error_msg = f"Failed batch participant creation: {str(exc)}"
        logger.error(f"[ERROR] {error_msg}")
        logger.error("[ERROR] Traceback:")
        traceback.print_exc()
        return error_response(error_msg, 500)


@app.route(
    "/api/participants/gateway_credentials/<competition_id>/<participant_id>",
    methods=["GET"],
)
def get_participant_gateway_credentials(competition_id: str, participant_id: str):
    """
    Get participant-specific gateway credentials for OpenAI-compatible clients.
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.get_participant(competition_id, participant_id)
        if not participant:
            return error_response("Participant not found", 404)

        base_root = request.url_root.rstrip("/")
        gateway_base = f"{base_root}/api/agent/call/{competition_id}/{participant_id}"
        openai_api_base = f"{gateway_base}/v1"
        gateway_key = _build_participant_gateway_key(competition_id, participant_id)

        return success_response(
            _inject_timing_state(
                {
                "competition_id": competition_id,
                "participant_id": participant_id,
                "participant_name": participant.name,
                "gateway_base_url": gateway_base,
                "openai_api_base": openai_api_base,
                "openai_api_key": gateway_key,
                },
                participant,
            )
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(f"Failed to get participant gateway credentials: {exc}", exc_info=True)
        return error_response(f"Failed to get participant gateway credentials: {str(exc)}", 500)


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
            return error_response("Participant not found", 404)

        include_submissions = (
            request.args.get("include_submissions", "false").lower() == "true"
        )

        if include_submissions:
            # Get submissions from database
            with DuckDBStorage(db_path=db_path) as data_storage:
                submissions = data_storage.list_submissions(
                    competition_id=competition_id, participant_id=participant_id
                )

            # Build detailed response
            response_data = participant.to_dict(include_submissions=False)
            response_data["submissions"] = [s.to_dict() for s in submissions]

            return success_response(response_data)
        else:
            return success_response(participant.to_dict(include_submissions=False))
    except Exception as e:
        return error_response(f"Failed to get participant data: {str(e)}", 500)


# API Routes for Participants
@app.route(
    "/api/participants/get_solved_problems/<competition_id>/<participant_id>",
    methods=["GET"],
)
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
            return error_response("Participant not found", 404)

        with DuckDBStorage(db_path=db_path) as data_storage:
            submissions = data_storage.list_submissions(
                competition_id=competition_id, participant_id=participant_id
            )

        # Extract solved problems from submissions
        solved_problems = []
        for submission in submissions:
            if submission.status == SubmissionStatus.ACCEPTED:
                # Check if this problem is already in solved_problems
                problem_already_solved = any(
                    p["problem_id"] == submission.problem_id for p in solved_problems
                )
                if not problem_already_solved:
                    solved_problems.append(
                        {
                            "problem_id": submission.problem_id,
                            "submission_id": submission.id,
                            "solved_at": submission.submitted_at.isoformat(),
                            "language": submission.language,
                            "score": submission.pass_score,
                        }
                    )

        # Build detailed response
        response_data = participant.to_dict(include_submissions=False)
        response_data["submissions"] = [s.to_dict() for s in submissions]
        response_data["solved_problems"] = solved_problems

        return success_response(response_data)

    except Exception as e:
        logger.error(f"Failed to get participant data: {e}", exc_info=True)
        return error_response(f"Failed to get participant data: {str(e)}", 500)


# API Routes for Participants
def check_termination(competition_id: str, participant_id: str):
    with DuckDBStorage(db_path=db_path) as data_storage:
        participant = data_storage.get_participant(competition_id, participant_id)
    if not participant:
        return error_response("Participant not found")
    if not participant.is_running:
        timing_state = _build_participant_timing_state(participant)
        return error_response(
            f"Participant is not running, termination_reason: {participant.termination_reason}",
            data={"timing_state": timing_state},
        )

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


# API Routes for Participants
@app.route(
    "/api/participants/terminate/<competition_id>/<participant_id>", methods=["POST"]
)
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
    - "all_problems_solved": Participant solved all problems in competition
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
            updated_participant = data_storage.get_participant(
                competition_id, participant_id
            )

        return success_response(
            message=f"Participant {participant_id} terminated successfully",
            data=_inject_timing_state(
                {"termination_reason": reason}, updated_participant
            ),
        )

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
        return error_response(
            f"Failed to terminate participant: {str(e)} (line {error_line})"
        )


# API Routes for Participants
@app.route(
    "/api/participants/status/<competition_id>/<participant_id>", methods=["GET"]
)
def get_participant_status(competition_id: str, participant_id: str):
    """
    Get participant termination status and reason.

    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier

    Returns:
        Participant status including running state, termination reason, tokens,
        problem pass score, and total score
    """
    try:
        with DuckDBStorage(db_path=db_path) as data_storage:
            participant = data_storage.get_participant(competition_id, participant_id)
        if not participant:
            return error_response("Participant not found", 404)

        status_data = {
            "is_running": participant.is_running,
            "termination_reason": participant.termination_reason,
            "remaining_tokens": participant.remaining_tokens,
            "problem_pass_score": getattr(participant, "problem_pass_score", 0),
            "score": participant.score,
        }
        status_data.update(_build_participant_timing_state(participant))

        return success_response(status_data)

    except Exception as e:
        return error_response(f"Failed to get participant status: {str(e)}")


# API Routes for Participants
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
                "accepted_count": p.accepted_count,
                "elapsed_time_seconds": p.get_elapsed_time_seconds(),
                "delivery_time_seconds": p.delivery_time_seconds,
                "delivery_time_multiplier": p.delivery_time_multiplier,
                "delivery_time_credit": p.delivery_time_credit,
                "consumed_credit": p.get_consumed_credit(),
            }
            for p in participants
            if not p.is_running
        ]

        return success_response(terminated_participants)

    except Exception as e:
        return error_response(f"Failed to get terminated participants: {str(e)}")


# API Routes for Problems
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


# API Routes for Problems
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
@app.route(
    "/api/submissions/create/<competition_id>/<participant_id>/<problem_id>",
    methods=["POST"],
)
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
        termination_result = check_termination(competition_id, participant_id)
        if termination_result:
            return termination_result

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
                language=language,
            )
            participant = data_storage.get_participant(competition_id, participant_id)

        if not submission:
            return error_response("Failed to create submission", 500)

        response_payload = {
                "submission_id": submission.id,
                "status": submission.status.value,
                "pass_score": submission.pass_score,
                "penalty": submission.penalty,
                # "participant_score": new_score,
                "problem_name": problem_name,
                "message": "Submission has been evaluated",
                "poll_url": f"/api/competitions/{competition_id}/submissions/{submission.id}",
                "test_results": [tr.to_dict() for tr in submission.test_results],
                "passed_tests": sum(
                    1
                    for tr in submission.test_results
                    if tr.status == SubmissionStatus.ACCEPTED
                ),
                "total_tests": len(submission.test_results),
            }
        if participant:
            response_payload["participant_state"] = participant.to_dict(
                include_submissions=False
            )
        return success_response(_inject_timing_state(response_payload, participant))

    except Exception as e:
        logger.error(f"Failed to create submission: {e}", exc_info=True)
        return error_response(f"Failed to create submission: {str(e)}", 500)


# API Routes for Test Code
@app.route("/api/test_code/<competition_id>/<participant_id>", methods=["POST"])
def test_code(competition_id: str, participant_id: str):
    """
    Test code with custom test cases.

    Args:
        competition_id: Competition identifier
        participant_id: Participant identifier

    Request Body:
        code: Source code to test
        language: Programming language (default: "cpp")
        test_cases: List of test cases with input and expected_output
        time_limit_ms: Time limit in milliseconds (optional, default: 5000)
        memory_limit_mb: Memory limit in MB (optional, default: 256)

    Returns:
        Test results with execution details
    """
    # Global frequency control
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)

    try:
        termination_result = check_termination(competition_id, participant_id)
        if termination_result:
            return termination_result

        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)

        problem_id = data.get("problem_id")
        code = data.get("code")
        language = data.get("language", "cpp")
        test_cases_data = data.get("test_cases", [])
        time_limit_ms = data.get("time_limit_ms", 5000)
        memory_limit_mb = data.get("memory_limit_mb", 256)

        if not all([participant_id, problem_id, code, test_cases_data]):
            return error_response("Missing required fields: problem_id, code and test_cases")

        if not isinstance(test_cases_data, list) or len(test_cases_data) == 0:
            return error_response("test_cases must be a non-empty list")

        # Convert test cases data to Case objects
        test_cases = []
        for i, test_case_data in enumerate(test_cases_data):
            if not isinstance(test_case_data, dict):
                return error_response(f"test_cases[{i}] must be an object")

            input_data = test_case_data.get("input", "")
            expected_output = test_case_data.get("expected_output", "")
            input_path = test_case_data.get("input_path")

            if not input_data and expected_output:
                return error_response(
                    f"test_cases[{i}] must have 'input' and 'expected_output' fields"
                )

            test_case = Case(
                id=f"custom_{i+1}",
                input_data=input_data,
                expected_output=expected_output,
                input_path=input_path or str(problem_id),
            )
            test_cases.append(test_case)

        # Process test code request (handled in storage layer)
        with DuckDBStorage(db_path=db_path, judge=judge) as data_storage:
            result = data_storage.process_test_code_request(
                competition_id=competition_id,
                participant_id=participant_id,
                code=code,
                language=language,
                test_cases=test_cases,
                time_limit_ms=time_limit_ms,
                memory_limit_mb=memory_limit_mb,
            )
            participant = data_storage.get_participant(competition_id, participant_id)

        payload = {
                "message": "Code testing completed",
                "passed_tests": result["passed_tests"],
                "total_tests": result["total_tests"],
                "tokens_cost": result["tokens_cost"],
                "remaining_tokens": result["remaining_tokens"],
                "language": result["language"],
                "test_results": result["test_results"],
                "execution_summary": result["execution_summary"],
            }
        if participant:
            payload["participant_state"] = participant.to_dict(include_submissions=False)

        return success_response(_inject_timing_state(payload, participant))

    except ValueError as e:
        logger.warning(f"Test code validation error: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to test code: {e}", exc_info=True)
        return error_response(f"Failed to test code: {str(e)}", 500)


# API Routes for Submissions
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
            problem_id=problem_id,
        )

    include_code = request.args.get("include_code", "false").lower() == "true"
    return success_response([s.to_dict(include_code=include_code) for s in submissions])


# API Routes for Submissions
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
        submission = data_storage.get_submission(
            submission_id, include_code=include_code
        )

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
                return error_response(
                    f"Competition with ID {competition_id} not found", 404
                )

            return success_response(rankings)

        except Exception as e:
            if (
                "TransactionContext Error: Conflict on update" in str(e)
                and attempt < max_retries - 1
            ):
                logger.warning(
                    f"Database conflict on rankings request (attempt {attempt + 1}/{max_retries}): {str(e)}"
                )
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(
                    f"Failed to get rankings after {attempt + 1} attempts: {e}",
                    exc_info=True,
                )
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
        return success_response(
            {"connected": False, "error": "Unable to check OJ status"}
        )


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
                problems.append(
                    {
                        "id": problem.id,
                        "title": problem.title,
                        "level": problem.level.value,  # Use enum value for consistency
                        "time_limit_ms": problem.time_limit_ms,
                        "memory_limit_mb": problem.memory_limit_mb,
                        "sample_count": len(problem.sample_cases),
                    }
                )

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
        problem_id = request.args.get("problem_id")
        num_problems = int(request.args.get("num_problems", 2))
        competition_id = request.args.get("competition_id")

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
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
            :num_problems
        ]

        similar_problems = []
        for idx in top_indices:
            pid = problem_ids[idx]
            problem = problem_loader.load_problem(pid)
            if problem:
                similar_problems.append(
                    {
                        "id": problem.id,
                        "title": problem.title,
                        "description": problem.description,
                        "level": problem.level.value,
                        "time_limit_ms": problem.time_limit_ms,
                        "memory_limit_mb": problem.memory_limit_mb,
                        "sample_count": len(problem.sample_cases),
                        "similarity_score": float(scores[idx]),
                    }
                )

        return success_response(similar_problems)

    except Exception as e:
        return error_response(f"Failed to get similar problems: {str(e)}")


# API Routes for Textbook
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
        query = request.args.get("query")
        max_results = int(request.args.get("max_results", 5))

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


# API Routes for Hints
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
        termination_result = check_termination(competition_id, participant_id)
        if termination_result:
            return termination_result

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
            result = data_storage.process_hint_request(
                competition_id,
                participant_id,
                hint_level,
                problem_id,
                hint_knowledge,
                problem_difficulty,
            )
            participant = data_storage.get_participant(competition_id, participant_id)

        payload = dict(result or {})
        if participant:
            payload["participant_state"] = participant.to_dict(include_submissions=False)

        return success_response(_inject_timing_state(payload, participant))

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to get hint: {e}", exc_info=True)
        return error_response(f"Failed to get hint: {str(e)}", 500)


# API Routes for Agent
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
        termination_result = check_termination(competition_id, participant_id)
        if termination_result:
            return termination_result

        data = request.get_json()
        if not data:
            return error_response("No JSON data provided", 400)

        # Process request using data storage layer
        with DuckDBStorage(db_path=db_path) as data_storage:
            result = data_storage.process_agent_request(
                competition_id, participant_id, data
            )
            participant = data_storage.get_participant(competition_id, participant_id)

        # Return response in expected format (array wrapper for compatibility)
        response = jsonify([result["content"]])
        response.status_code = result["status_code"]
        return _apply_timing_headers(response, participant)

    except ValueError as e:
        logger.error(f"ValueError in generate_response: {str(e)}")
        return error_response(str(e), 404)
    except Exception as e:
        error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
        logger.error(f"Exception in generate_response: {str(e)} at line {error_line}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response(f"Agent request failed: {str(e)} (line {error_line})")


@app.route("/api/agent/call/<competition_id>/<participant_id>/<path:api_path>", methods=["POST"])
def gateway_generate_response(competition_id: str, participant_id: str, api_path: str):
    """
    OpenAI-compatible gateway endpoint for external clients (e.g., Codex in infinite_tree).

    Example base URL for client:
      /api/agent/call/<competition_id>/<participant_id>/v1
    """
    if global_rate_limiter.should_rate_limit():
        wait_time = global_rate_limiter.get_wait_time()
        logger.info(f"Rate limiting request, waiting {wait_time:.3f}s")
        time.sleep(wait_time)

    try:
        termination_result = check_termination(competition_id, participant_id)
        if termination_result:
            return termination_result

        expected_key = _build_participant_gateway_key(competition_id, participant_id)
        provided_key = _extract_bearer_token(request.headers)
        if not provided_key or provided_key != expected_key:
            return error_response("Unauthorized gateway api key", 401)

        data = request.get_json(silent=True)
        if data is None:
            return error_response("No JSON data provided", 400)

        selected_api_path = "/" + api_path.lstrip("/")
        with DuckDBStorage(db_path=db_path) as data_storage:
            result = data_storage.process_agent_request(
                competition_id,
                participant_id,
                data,
                api_path=selected_api_path,
            )
            participant = data_storage.get_participant(competition_id, participant_id)

        if bool(result.get("is_sse")):
            response = Response(
                result.get("sse_body", ""),
                status=result["status_code"],
                mimetype="text/event-stream",
            )
            return _apply_timing_headers(response, participant)

        response = jsonify(result["content"])
        response.status_code = result["status_code"]
        return _apply_timing_headers(response, participant)
    except ValueError as exc:
        logger.error(f"ValueError in gateway_generate_response: {str(exc)}")
        return error_response(str(exc), 404)
    except Exception as exc:  # pylint: disable=broad-except
        error_line = traceback.extract_tb(exc.__traceback__)[-1].lineno
        logger.error(f"Exception in gateway_generate_response: {str(exc)} at line {error_line}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return error_response(f"Gateway request failed: {str(exc)} (line {error_line})", 502)


# API Routes for Agent
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
        termination_result = check_termination(competition_id, participant_id)
        if termination_result:
            return termination_result

        data = request.get_json()
        if not data:
            return error_response("No data provided")

        # Process streaming request using data storage layer
        with DuckDBStorage(db_path=db_path) as data_storage:
            result = data_storage.process_stream_agent_request(
                competition_id, participant_id, data
            )
            participant = data_storage.get_participant(competition_id, participant_id)

        # Return streaming response in expected format (array wrapper for compatibility)
        structured_response = [
            result["reasoning_content"],
            result["content"],
            result["usage_info"],
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
        ]

        response = jsonify(structured_response)
        response.status_code = result["status_code"]
        return _apply_timing_headers(response, participant)

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
        return error_response(
            f"Streaming agent request failed: {str(e)} (line {error_line})"
        )


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

        hydro_config = config.get_section("hydro")
        hydro_client = HydroClient(
            base_url=hydro_config.get("base_url", "http://127.0.0.1:8888"),
            api_token=hydro_config.get("api_token"),
            api_base=hydro_config.get("api_base", "/usacoarena/api"),
            timeout_seconds=float(hydro_config.get("timeout_seconds", 30.0)),
            poll_interval_seconds=float(
                hydro_config.get("poll_interval_seconds", 0.5)
            ),
            submission_timeout_seconds=float(
                hydro_config.get("submission_timeout_seconds", 120.0)
            ),
        )
        judge = Judge(hydro_client=hydro_client)

        # Configure problem loader with custom data directory
        data_config = config.get_section("data")
        problem_data_dir = data_config.get(
            "problem_data_dir", "dataset/datasets/usaco_2025"
        )
        textbook_data_dir = data_config.get("textbook_data_dir", "dataset/textbooks")

        # Always reinitialize loaders with configured paths
        problem_loader = USACOProblemLoader(
            data_path=problem_data_dir,
            hydro_client=hydro_client,
        )
        logger.info(
            "Initialized Hydro-backed problem loader with base URL: %s",
            hydro_client.base_url,
        )

        # Verify problem loader initialization
        problem_count = len(problem_loader.problems_dict)
        logger.info(f"Loaded {problem_count} problems from problem library")
        if problem_count == 0:
            logger.warning("No problems loaded! Check Hydro base URL, token, and plugin state")

        textbook_loader = TextbookLoader(data_path=textbook_data_dir)
        logger.info(f"Initialized textbook loader with data path: {textbook_data_dir}")

        logger.info("Server configuration applied successfully")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_api(debug=True)
