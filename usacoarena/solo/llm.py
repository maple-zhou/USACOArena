"""Client wrapper for direct LLM API interactions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from usacoarena.utils.logger_config import get_logger

logger = get_logger("solo_llm")


@dataclass
class LLMUsage:
    """Capture token statistics for a single inference."""

    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]

    @classmethod
    def from_payload(cls, payload: Optional[Dict[str, Any]]) -> "LLMUsage":
        if not payload:
            return cls(None, None, None)
        prompt = payload.get("prompt_tokens")
        completion = payload.get("completion_tokens")
        total = payload.get("total_tokens")
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        return cls(prompt, completion, total)


@dataclass
class LLMConfig:
    """Configuration container for an LLM service."""

    name: str
    model_id: str
    api_base_url: str
    api_key: str
    request_format: Dict[str, Any]
    response_format: Dict[str, Any]

    @classmethod
    def from_file(cls, path: str, competitor_name: Optional[str] = None) -> "LLMConfig":
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"LLM configuration file not found: {path}")

        data = json.loads(config_path.read_text(encoding="utf-8"))
        if "competitors" in data:
            entries = data["competitors"]
            if competitor_name:
                matches = [c for c in entries if c.get("name") == competitor_name]
                if not matches:
                    raise ValueError(f"No competitor named {competitor_name} found in the configuration")
                entry = matches[0]
            else:
                if len(entries) != 1:
                    raise ValueError("Configuration contains multiple competitors; use --competitor-name to specify the target")
                entry = entries[0]
        else:
            entry = data

        required = ["name", "model_id", "api_base_url", "api_key"]
        missing = [key for key in required if key not in entry]
        if missing:
            raise ValueError(f"LLM configuration missing fields: {missing}")

        request_format = entry.get("request_format") or {
            "url": "/v1/chat/completions",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer {api_key}"
            },
            "body_template": {
                "model": "{model_id}",
                "messages": "{messages}",
                "temperature": 0.0
            }
        }
        response_format = entry.get("response_format") or {
            "response_path": "choices[0].message.content",
            "usage_path": "usage"
        }

        return cls(
            name=entry["name"],
            model_id=entry["model_id"],
            api_base_url=entry["api_base_url"].rstrip("/"),
            api_key=entry["api_key"],
            request_format=request_format,
            response_format=response_format,
        )

    def prepare_request(self, messages: List[Dict[str, str]]) -> Tuple[str, str, Dict[str, str], Dict[str, Any]]:
        """Generate request components based on the configured template."""
        method = self.request_format.get("method", "POST")
        url = self.request_format.get("url", "")
        if not url.startswith("http"):
            url = f"{self.api_base_url}{url}"

        headers = {
            key: value.format(api_key=self.api_key)
            for key, value in self.request_format.get("headers", {}).items()
        }

        body_template = self.request_format.get("body_template", {}).copy()
        payload: Dict[str, Any] = {}
        for key, value in body_template.items():
            if isinstance(value, str):
                payload[key] = value.format(
                    model_id=self.model_id,
                    messages=json.dumps(messages, ensure_ascii=False)
                )
            else:
                payload[key] = value

        if "messages" in payload and isinstance(payload["messages"], str):
            payload["messages"] = json.loads(payload["messages"])
        else:
            payload.setdefault("messages", messages)

        payload.setdefault("model", self.model_id)
        return method, url, headers, payload

    def extract_content(self, response_json: Dict[str, Any]) -> str:
        """Extract the model output following the configured path."""
        path = self.response_format.get("response_path", "choices[0].message.content")
        return _dig_value(response_json, path)

    def extract_usage(self, response_json: Dict[str, Any]) -> LLMUsage:
        """Extract usage information from the response."""
        usage_path = self.response_format.get("usage_path", "usage")
        usage = _dig_value(response_json, usage_path, default=None)
        return LLMUsage.from_payload(usage if isinstance(usage, dict) else None)


class LLMClient:
    """Lightweight LLM API client for sending prompts and returning code."""

    def __init__(self, config: LLMConfig, timeout: float = 120.0):
        self._config = config
        self._timeout = timeout

    def infer(self, messages: List[Dict[str, str]]) -> Tuple[str, LLMUsage]:
        """Execute a single inference call."""
        method, url, headers, payload = self._config.prepare_request(messages)
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise RuntimeError("LLM returned invalid JSON data") from exc

        content = self._config.extract_content(response_json)
        if not isinstance(content, str):
            raise RuntimeError("Unable to extract textual content from LLM response")

        usage = self._config.extract_usage(response_json)
        return content, usage


def _dig_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """Resolve a nested field using dotted or slash-delimited syntax."""
    if not path:
        return data
    current: Any = data
    for segment in path.replace("/", ".").split('.'):
        if segment == "":
            continue
        if '[' in segment and segment.endswith(']'):
            key, index_str = segment[:-1].split('[', 1)
            current = current.get(key) if isinstance(current, dict) else default
            if current is default:
                return default
            try:
                index = int(index_str)
                current = current[index]
            except (ValueError, IndexError, TypeError):
                return default
        else:
            if isinstance(current, dict):
                current = current.get(segment, default)
            else:
                return default
        if current is None:
            return default
    return current
