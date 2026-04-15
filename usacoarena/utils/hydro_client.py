"""HTTP client for the USACOArena Hydro plugin API."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

from usacoarena.utils.logger_config import get_logger

logger = get_logger("hydro_client")


class HydroClientError(RuntimeError):
    """Raised when the Hydro plugin API returns an error."""


class HydroClient:
    """Thin HTTP client for machine-facing Hydro plugin endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        api_token: Optional[str] = None,
        api_base: str = "/usacoarena/api",
        timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
        submission_timeout_seconds: float = 120.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        base = (base_url or "").strip().rstrip("/")
        if not base:
            raise ValueError("Hydro base URL must not be empty")

        self.base_url = base
        self.api_base = "/" + (api_base or "usacoarena/api").strip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self.submission_timeout_seconds = max(1.0, float(submission_timeout_seconds))
        self.api_token = (api_token or "").strip()
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls) -> Optional["HydroClient"]:
        base_url = (os.environ.get("USACOARENA_HYDRO_BASE_URL", "") or "").strip()
        if not base_url:
            return None
        return cls(
            base_url=base_url,
            api_token=os.environ.get("USACOARENA_HYDRO_API_TOKEN"),
            api_base=os.environ.get("USACOARENA_HYDRO_API_BASE", "/usacoarena/api"),
            timeout_seconds=float(
                os.environ.get("USACOARENA_HYDRO_TIMEOUT_SECONDS", "30") or "30"
            ),
            poll_interval_seconds=float(
                os.environ.get("USACOARENA_HYDRO_POLL_INTERVAL_SECONDS", "0.5") or "0.5"
            ),
            submission_timeout_seconds=float(
                os.environ.get("USACOARENA_HYDRO_SUBMISSION_TIMEOUT_SECONDS", "120")
                or "120"
            ),
        )

    def clone_with_overrides(
        self,
        *,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
        submission_timeout_seconds: Optional[float] = None,
    ) -> "HydroClient":
        return HydroClient(
            base_url=self.base_url,
            api_token=self.api_token,
            api_base=self.api_base,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
            poll_interval_seconds=poll_interval_seconds or self.poll_interval_seconds,
            submission_timeout_seconds=(
                submission_timeout_seconds or self.submission_timeout_seconds
            ),
            session=self.session,
        )

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def list_problems(
        self, *, level: Optional[str] = None, detail: bool = False
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if level:
            params["level"] = level
        if detail:
            params["detail"] = "full"
        data = self._request("GET", "/problems", params=params)
        if not isinstance(data, list):
            raise HydroClientError("Hydro plugin returned non-list problem payload")
        return [row for row in data if isinstance(row, dict)]

    def get_problem(self, problem_id: str) -> Dict[str, Any]:
        data = self._request("GET", f"/problems/{problem_id}")
        if not isinstance(data, dict):
            raise HydroClientError("Hydro plugin returned invalid problem detail")
        return data

    def get_problem_solution(self, problem_id: str) -> Optional[str]:
        try:
            data = self._request("GET", f"/problems/{problem_id}/solution")
        except HydroClientError:
            return None
        if not isinstance(data, dict):
            return None
        content = data.get("content")
        return str(content) if isinstance(content, str) and content.strip() else None

    def resolve_problem(self, problem_id: str) -> Dict[str, Any]:
        data = self._request("GET", "/resolve", params={"problem_id": problem_id})
        if not isinstance(data, dict):
            raise HydroClientError("Hydro plugin returned invalid resolve payload")
        return data

    def submit_solution(
        self, problem_id: str, code: str, language: str
    ) -> Dict[str, Any]:
        data = self._request(
            "POST",
            "/submissions",
            json_data={
                "problem_id": problem_id,
                "code": code,
                "language": language,
            },
        )
        if not isinstance(data, dict):
            raise HydroClientError("Hydro plugin returned invalid submission payload")
        return data

    def pretest(
        self,
        problem_id: str,
        code: str,
        language: str,
        inputs: List[str],
    ) -> Dict[str, Any]:
        data = self._request(
            "POST",
            "/pretest",
            json_data={
                "problem_id": problem_id,
                "code": code,
                "language": language,
                "inputs": inputs,
            },
        )
        if not isinstance(data, dict):
            raise HydroClientError("Hydro plugin returned invalid pretest payload")
        return data

    def get_record(self, record_id: str) -> Dict[str, Any]:
        data = self._request("GET", f"/records/{record_id}")
        if not isinstance(data, dict):
            raise HydroClientError("Hydro plugin returned invalid record payload")
        return data

    def wait_for_record(
        self,
        record_id: str,
        *,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        timeout = (
            self.submission_timeout_seconds
            if timeout_seconds is None
            else max(1.0, float(timeout_seconds))
        )
        interval = (
            self.poll_interval_seconds
            if poll_interval_seconds is None
            else max(0.1, float(poll_interval_seconds))
        )

        deadline = time.monotonic() + timeout
        last_payload: Optional[Dict[str, Any]] = None

        while time.monotonic() < deadline:
            payload = self.get_record(record_id)
            last_payload = payload
            if bool(payload.get("finished")):
                return payload
            time.sleep(interval)

        raise HydroClientError(
            f"Timed out while waiting for Hydro record {record_id}. "
            f"Last payload: {last_payload}"
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{self.api_base}{path}"
        headers = {
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            headers["X-USACOArena-Token"] = self.api_token

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise HydroClientError(
                f"Failed to call Hydro plugin endpoint {method} {url}: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise HydroClientError(
                f"Hydro plugin endpoint {method} {url} returned non-JSON body: "
                f"status={response.status_code}, body={response.text[:500]}"
            ) from exc

        if not response.ok:
            message = payload.get("error") if isinstance(payload, dict) else None
            raise HydroClientError(
                f"Hydro plugin endpoint {method} {url} failed with "
                f"HTTP {response.status_code}: {message or payload}"
            )

        if isinstance(payload, dict):
            if payload.get("ok") is False:
                raise HydroClientError(
                    f"Hydro plugin endpoint {method} {url} returned error: "
                    f"{payload.get('error') or payload}"
                )
            if "data" in payload:
                return payload["data"]

        return payload
