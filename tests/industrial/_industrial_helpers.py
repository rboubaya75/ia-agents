from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _set_common_environment() -> None:
    os.environ.update(
        {
            "AWS_ACCESS_KEY_ID": "industrial-test",
            "AWS_SECRET_ACCESS_KEY": "industrial-test",
            "AWS_SESSION_TOKEN": "industrial-test",
            "AWS_DEFAULT_REGION": "eu-west-3",
            "AWS_REGION": "eu-west-3",
            "AWS_EC2_METADATA_DISABLED": "true",
            "MEMORY_ID": "",
            "GATEWAY_URL": "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/industrial/mcp",
            "GATEWAY_AUTH_MODE": "aws_iam",
            "REQUIRE_MCP_TOOLS": "true",
            "MCP_CONNECT_TIMEOUT_SECONDS": "2",
            "MCP_READ_TIMEOUT_SECONDS": "6",
            "MCP_WRITE_TIMEOUT_SECONDS": "5",
            "MCP_POOL_TIMEOUT_SECONDS": "2",
            "RUNTIME_READY": "true",
            "AGENT_RUNTIME_ARN": "arn:aws:bedrock-agentcore:eu-west-3:123456789012:runtime/industrial",
            "AGENT_RUNTIME_ENDPOINT_NAME": "default",
            "COGNITO_CLIENT_ID": "client-industrial",
            "REQUEST_TIMEOUT_SECONDS": "28",
            "RUNTIME_CONNECT_TIMEOUT_SECONDS": "2",
            "RUNTIME_READ_TIMEOUT_SECONDS": "23",
            "RUNTIME_DEADLINE_SAFETY_MS": "1500",
            "MAX_BODY_BYTES": "16384",
        }
    )


def load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_runtime() -> Any:
    _set_common_environment()
    return load_module(
        "industrial_runtime",
        ROOT / "deploy-agentcore" / "agents" / "phase_4_robust.py",
    )


def load_facade() -> Any:
    _set_common_environment()
    return load_module(
        "industrial_facade",
        ROOT
        / "infra"
        / "modules"
        / "agent_api_facade"
        / "src"
        / "lambda_function.py",
    )


def runtime_payload(
    prompt: str = "Plan a trip",
    *,
    actor_id: str = "industrial-actor-raw",
    session_id: str = "sid-v1-" + ("a" * 64),
    operation_id: str = "76e6f404-49de-4dc4-9c60-f2c25a0de91f",
    request_id: str = "industrial-request-1",
    remaining_ms: int = 30_000,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "sessionId": session_id,
        "operationId": operation_id,
        "requestId": request_id,
        "deadlineEpochMs": int(time.time() * 1000) + remaining_ms,
        "trustedIdentity": {"actorId": actor_id},
    }


def json_log_events(logger_mock: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for call in logger_mock.method_calls:
        if not call.args or not isinstance(call.args[0], str):
            continue
        raw = call.args[0]
        if not raw.startswith("{"):
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def serialized_log_messages(logger_mock: Any) -> str:
    values: list[str] = []
    for call in logger_mock.method_calls:
        if call.args and isinstance(call.args[0], str):
            values.append(call.args[0])
    return "\n".join(values)


def extract_hcl_block(source: str, header: str) -> str:
    start = source.find(header)
    if start < 0:
        raise AssertionError(f"HCL block not found: {header}")
    opening = source.find("{", start)
    if opening < 0:
        raise AssertionError(f"HCL block has no opening brace: {header}")
    depth = 0
    in_string = False
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"HCL block is not balanced: {header}")
