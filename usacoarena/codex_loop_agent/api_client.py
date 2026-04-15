"""HTTP client for standalone Codex loop agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


class ArenaAPIError(RuntimeError):
    """Raised when USACOArena API returns an error."""


@dataclass(frozen=True)
class GatewayCredentials:
    """Participant-scoped gateway credentials for OpenAI-compatible calls."""

    competition_id: str
    participant_id: str
    participant_name: str
    gateway_base_url: str
    openai_api_base: str
    openai_api_key: str


@dataclass(frozen=True)
class ParticipantStatus:
    """Live participant status."""

    is_running: bool
    termination_reason: Optional[str]
    remaining_tokens: int
    score: float
    elapsed_time_seconds: int
    delivery_time_multiplier: float
    delivery_time_settled: bool
    delivery_time_credit: float


class ArenaClient:
    """Thin typed wrapper over USACOArena endpoints used by codex loop runner."""

    def __init__(self, api_base: str, timeout: float = 30.0) -> None:
        normalized = str(api_base or "").strip().rstrip("/")
        if not normalized:
            raise ValueError("api_base must not be empty")
        self.api_base = normalized
        self.timeout = float(timeout)
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.api_base}{path}"
        try:
            response = self.session.request(method, url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ArenaAPIError(f"network error for {method} {path}: {exc}") from exc

        response_json: Optional[Dict[str, Any]] = None
        parse_error: Optional[Exception] = None
        try:
            loaded = response.json()
            if isinstance(loaded, dict):
                response_json = loaded
        except Exception as exc:  # pragma: no cover - defensive
            parse_error = exc

        if response.status_code >= 400:
            if isinstance(response_json, dict):
                message = response_json.get("message") or response_json.get("error") or str(response_json)
            else:
                text = (response.text or "").strip()
                message = text[:500] if text else response.reason
            raise ArenaAPIError(f"HTTP {response.status_code} for {method} {path}: {message}")

        if parse_error is not None:
            raise ArenaAPIError(f"invalid JSON response for {method} {path}: {parse_error}") from parse_error
        if response_json is None:
            raise ArenaAPIError(f"response for {method} {path} is not a JSON object")

        if response_json.get("status") != "success":
            message = response_json.get("message") or "unknown API error"
            raise ArenaAPIError(f"API error for {method} {path}: {message}")

        return response_json

    @staticmethod
    def _require_dict(value: Any, *, context: str) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ArenaAPIError(f"{context} payload must be a JSON object")
        return value

    def get_gateway_credentials(self, competition_id: str, participant_id: str) -> GatewayCredentials:
        data = self._request(
            "GET",
            f"/api/participants/gateway_credentials/{competition_id}/{participant_id}",
        )
        payload = self._require_dict(data.get("data"), context="gateway_credentials")
        return GatewayCredentials(
            competition_id=str(payload.get("competition_id") or competition_id),
            participant_id=str(payload.get("participant_id") or participant_id),
            participant_name=str(payload.get("participant_name") or ""),
            gateway_base_url=str(payload.get("gateway_base_url") or "").rstrip("/"),
            openai_api_base=str(payload.get("openai_api_base") or "").rstrip("/"),
            openai_api_key=str(payload.get("openai_api_key") or "").strip(),
        )

    def get_participant_status(self, competition_id: str, participant_id: str) -> ParticipantStatus:
        data = self._request("GET", f"/api/participants/status/{competition_id}/{participant_id}")
        payload = self._require_dict(data.get("data"), context="participant_status")
        return ParticipantStatus(
            is_running=bool(payload.get("is_running", False)),
            termination_reason=(
                str(payload.get("termination_reason")).strip()
                if payload.get("termination_reason") is not None
                else None
            ),
            remaining_tokens=_to_int(payload.get("remaining_tokens"), default=0),
            score=_to_float(payload.get("score"), default=0.0),
            elapsed_time_seconds=_to_int(payload.get("elapsed_time_seconds"), default=0),
            delivery_time_multiplier=_to_float(
                payload.get("delivery_time_multiplier"), default=1.0
            ),
            delivery_time_settled=bool(payload.get("delivery_time_settled", False)),
            delivery_time_credit=_to_float(payload.get("delivery_time_credit"), default=0.0),
        )

    def get_participant_state(self, competition_id: str, participant_id: str) -> Dict[str, Any]:
        data = self._request(
            "GET",
            f"/api/participants/get_solved_problems/{competition_id}/{participant_id}",
        )
        return self._require_dict(data.get("data"), context="participant_state")

    def list_problems(self, competition_id: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/api/problems/list/{competition_id}")
        rows = data.get("data")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def get_problem(self, competition_id: str, problem_id: str) -> Dict[str, Any]:
        data = self._request("GET", f"/api/problems/get/{competition_id}/{problem_id}")
        return self._require_dict(data.get("data"), context="problem_detail")

    def submit_solution(
        self,
        competition_id: str,
        participant_id: str,
        problem_id: str,
        *,
        code: str,
        language: str,
    ) -> Dict[str, Any]:
        payload = {
            "code": code,
            "language": language,
        }
        data = self._request(
            "POST",
            f"/api/submissions/create/{competition_id}/{participant_id}/{problem_id}",
            payload=payload,
        )
        return self._require_dict(data.get("data"), context="submission_create")

    def get_submission(self, submission_id: str) -> Dict[str, Any]:
        data = self._request("GET", f"/api/submissions/get/{submission_id}")
        return self._require_dict(data.get("data"), context="submission_detail")

    def get_rankings(self, competition_id: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/api/rankings/get/{competition_id}")
        rows = data.get("data")
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def terminate_participant(
        self,
        competition_id: str,
        participant_id: str,
        *,
        reason: str,
    ) -> Dict[str, Any]:
        data = self._request(
            "POST",
            f"/api/participants/terminate/{competition_id}/{participant_id}",
            payload={"reason": reason},
        )
        payload = data.get("data")
        return payload if isinstance(payload, dict) else {}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
