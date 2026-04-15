"""Agent profile schema and normalization helpers.

This module provides a stable, provider-neutral schema so any external agent
runtime (Codex, Claude Code, custom MCP orchestrators, etc.) can describe its
capabilities when joining USACOArena.
"""

from __future__ import annotations

from typing import Any, Dict, List


_AGENT_PROFILE_EXAMPLE: Dict[str, Any] = {
    "version": "1.0",
    "agent_type": "codex",
    "transport": "openai_compatible_http",
    "entrypoint": "codex --json",
    "capabilities": [
        "read_problem",
        "submit_solution",
        "request_hint",
        "test_code",
        "mcp_tools",
    ],
    "mcp": {
        "enabled": True,
        "servers": [
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "mcp-server-filesystem",
                "args": ["--root", "/workspace"],
                "description": "Read/write files inside workspace",
                "enabled": True,
            }
        ],
    },
    "request_format": {
        "url": "/v1/chat/completions",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer {api_key}",
        },
        "body_template": {
            "messages": "{messages}",
            "model": "{model_id}",
            "temperature": 0.7,
        },
    },
    "response_format": {
        "response_path": "choices[0].message.content",
        "error_path": "error.message",
    },
    "metadata": {
        "vendor": "openai",
        "runtime": "cli",
    },
}


AGENT_PROFILE_SCHEMA: Dict[str, Any] = {
    "name": "USACOArenaAgentProfile",
    "version": "1.0",
    "description": (
        "Provider-neutral agent integration schema used by participant registration."
    ),
    "required": ["agent_type", "transport"],
    "fields": {
        "version": "schema version, default 1.0",
        "agent_type": "agent family, e.g. codex/claude/custom",
        "transport": "integration transport, e.g. openai_compatible_http/mcp/stdio",
        "entrypoint": "optional runtime entry command",
        "capabilities": "list of capability tags",
        "mcp": {
            "enabled": "whether MCP routing is enabled",
            "servers": "list of MCP server descriptors",
        },
        "request_format": "optional request template override",
        "response_format": "optional response parsing override",
        "metadata": "free-form metadata",
    },
    "example": _AGENT_PROFILE_EXAMPLE,
}


def _as_str(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    return []


def _normalize_mcp_servers(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    servers: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _as_str(item.get("name"))
        if not name:
            continue
        server = {
            "name": name,
            "transport": _as_str(item.get("transport"), "stdio"),
            "url": _as_str(item.get("url")),
            "command": _as_str(item.get("command")),
            "args": _as_string_list(item.get("args")),
            "description": _as_str(item.get("description")),
            "enabled": _as_bool(item.get("enabled"), True),
            "env": item.get("env") if isinstance(item.get("env"), dict) else {},
        }
        servers.append(server)
    return servers


def normalize_agent_profile(value: Any) -> Dict[str, Any]:
    """Normalize input into a stable `agent_profile` payload."""
    data = value if isinstance(value, dict) else {}

    request_format = data.get("request_format")
    response_format = data.get("response_format")
    normalized_request_format = request_format if isinstance(request_format, dict) else {}
    normalized_response_format = response_format if isinstance(response_format, dict) else {}

    request_headers = normalized_request_format.get("headers")
    if not isinstance(request_headers, dict):
        request_headers = {}
    request_body_template = normalized_request_format.get("body_template")
    if not isinstance(request_body_template, dict):
        request_body_template = {}

    normalized: Dict[str, Any] = {
        "version": _as_str(data.get("version"), "1.0"),
        "agent_type": _as_str(data.get("agent_type"), "custom"),
        "transport": _as_str(data.get("transport"), "openai_compatible_http"),
        "entrypoint": _as_str(data.get("entrypoint")),
        "capabilities": _as_string_list(data.get("capabilities")),
        "mcp": {
            "enabled": _as_bool(
                (data.get("mcp") or {}).get("enabled") if isinstance(data.get("mcp"), dict) else None,
                False,
            ),
            "servers": _normalize_mcp_servers(
                (data.get("mcp") or {}).get("servers") if isinstance(data.get("mcp"), dict) else None
            ),
        },
        "request_format": {
            "url": _as_str(normalized_request_format.get("url")),
            "method": _as_str(normalized_request_format.get("method"), "POST"),
            "headers": {
                str(key).strip(): value
                for key, value in request_headers.items()
                if str(key).strip()
            },
            "body_template": {
                str(key).strip(): value
                for key, value in request_body_template.items()
                if str(key).strip()
            },
        },
        "response_format": {
            "response_path": _as_str(
                normalized_response_format.get("response_path"),
                "choices[0].message.content",
            ),
            "error_path": _as_str(normalized_response_format.get("error_path")),
            "usage_path": _as_str(normalized_response_format.get("usage_path")),
        },
        "metadata": data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
    }

    return normalized


def build_agent_profile_template() -> Dict[str, Any]:
    """Return a deep-copy friendly template payload for configuration files."""
    return {
        "version": "1.0",
        "agent_type": "custom",
        "transport": "openai_compatible_http",
        "entrypoint": "",
        "capabilities": [],
        "mcp": {"enabled": False, "servers": []},
        "request_format": {
            "url": "",
            "method": "POST",
            "headers": {},
            "body_template": {},
        },
        "response_format": {
            "response_path": "choices[0].message.content",
            "error_path": "error.message",
            "usage_path": "",
        },
        "metadata": {},
    }
