from usacoarena.benchmark.agent_profile import normalize_agent_profile


def test_normalize_agent_profile_with_mcp_servers() -> None:
    profile = normalize_agent_profile(
        {
            "agent_type": "claude_code",
            "transport": "openai_compatible_http",
            "capabilities": ["submit_solution", "mcp_tools"],
            "mcp": {
                "enabled": True,
                "servers": [
                    {
                        "name": "filesystem",
                        "transport": "stdio",
                        "command": "mcp-server-filesystem",
                        "args": ["--root", "/workspace"],
                    }
                ],
            },
        }
    )

    assert profile["agent_type"] == "claude_code"
    assert profile["mcp"]["enabled"] is True
    assert profile["mcp"]["servers"][0]["name"] == "filesystem"
    assert profile["mcp"]["servers"][0]["args"] == ["--root", "/workspace"]


def test_normalize_agent_profile_preserves_request_and_response_format() -> None:
    profile = normalize_agent_profile(
        {
            "agent_type": "codex",
            "transport": "openai_compatible_http",
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
                },
            },
            "response_format": {
                "response_path": "choices[0].message.content",
                "error_path": "error.message",
                "usage_path": "usage",
            },
        }
    )

    assert profile["request_format"]["url"] == "/v1/chat/completions"
    assert profile["request_format"]["method"] == "POST"
    assert profile["request_format"]["headers"]["Authorization"] == "Bearer {api_key}"
    assert profile["request_format"]["body_template"]["model"] == "{model_id}"
    assert profile["response_format"]["response_path"] == "choices[0].message.content"
    assert profile["response_format"]["usage_path"] == "usage"
