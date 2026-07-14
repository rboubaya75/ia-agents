"""Hardened adapter for the Secure V1 AgentCore Runtime.

This module keeps the stable V1 implementation in :mod:`phase_4` and adds the
runtime controls required for safe retries around mutating MCP tools:

* bounded MCP HTTP timeouts;
* deterministic per-tool mutation identifiers;
* server-side confirmation verification;
* no automatic whole-agent retry after a confirmed mutation starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

import httpx
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from mcp.client.streamable_http import streamable_http_client

try:
    from . import phase_4 as base
except ImportError:  # direct file loading in unit tests
    import importlib.util
    from pathlib import Path

    base_path = Path(__file__).with_name("phase_4.py")
    base_spec = importlib.util.spec_from_file_location("secure_runtime_base", base_path)
    if base_spec is None or base_spec.loader is None:
        raise RuntimeError(f"Unable to load Runtime base module from {base_path}")
    base = importlib.util.module_from_spec(base_spec)
    base_spec.loader.exec_module(base)

MCP_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MCP_CONNECT_TIMEOUT_SECONDS", "2"))
MCP_READ_TIMEOUT_SECONDS = float(os.getenv("MCP_READ_TIMEOUT_SECONDS", "6"))
MCP_WRITE_TIMEOUT_SECONDS = float(os.getenv("MCP_WRITE_TIMEOUT_SECONDS", "5"))
MCP_POOL_TIMEOUT_SECONDS = float(os.getenv("MCP_POOL_TIMEOUT_SECONDS", "2"))

for timeout_name, timeout_value in {
    "MCP_CONNECT_TIMEOUT_SECONDS": MCP_CONNECT_TIMEOUT_SECONDS,
    "MCP_READ_TIMEOUT_SECONDS": MCP_READ_TIMEOUT_SECONDS,
    "MCP_WRITE_TIMEOUT_SECONDS": MCP_WRITE_TIMEOUT_SECONDS,
    "MCP_POOL_TIMEOUT_SECONDS": MCP_POOL_TIMEOUT_SECONDS,
}.items():
    if timeout_value <= 0 or timeout_value > 20:
        raise RuntimeError(
            f"{timeout_name} must be greater than 0 and at most 20 seconds."
        )

if "get_trips is paginated" not in base.PHASE4_SYSTEM_PROMPT_BASE:
    base.PHASE4_SYSTEM_PROMPT_BASE += (
        "- get_trips is paginated: use nextToken only when another page is needed.\n"
    )
if "Only invoke create_trip or update_trip" not in base.PHASE4_SYSTEM_PROMPT_BASE:
    base.PHASE4_SYSTEM_PROMPT_BASE += (
        "- Only invoke create_trip or update_trip on a turn where the current user "
        "message explicitly starts with 'Je confirme' or 'I confirm'.\n"
    )

_CONTEXT_FIELDS = {
    "userId",
    "requestId",
    "deadlineEpochMs",
    "operationId",
    "confirmationVerified",
}
_CONFIRMATION_PATTERN = re.compile(
    r"^(?:oui[ ,]+)?je confirme(?:[.!]?$|\s+(?:la|le|les|cette|ce)\s+"
    r"(?:creation|mise a jour|modification|operation|voyage)\b.*$)"
    r"|^(?:yes[ ,]+)?i confirm(?:[.!]?$|\s+(?:the\s+)?"
    r"(?:creation|update|change|operation|trip)\b.*$)"
)


class InvocationState:
    """Tracks whether a confirmed mutation may already have produced a side effect."""

    def __init__(self) -> None:
        self.mutation_started = False


def _normalize_confirmation_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.strip().lower())


def is_explicit_confirmation(prompt: str) -> bool:
    """Return true only for a current-turn, explicit confirmation phrase."""

    return bool(_CONFIRMATION_PATTERN.match(_normalize_confirmation_text(prompt)))


def _canonical_business_payload(tool_input: Dict[str, Any]) -> str:
    business_payload = {
        key: value for key, value in tool_input.items() if key not in _CONTEXT_FIELDS
    }
    return json.dumps(
        business_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def derive_mutation_operation_id(
    request_operation_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    occurrence: int,
) -> str:
    """Derive a stable UUID per mutation within a request-level operation.

    The payload fingerprint distinguishes different mutations in the same model
    turn. The occurrence distinguishes two intentional identical mutations. A
    replay that produces the same ordered tool sequence derives the same keys.
    """

    canonical_payload = _canonical_business_payload(tool_input)
    fingerprint = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    namespace = uuid.UUID(request_operation_id)
    return str(uuid.uuid5(namespace, f"{tool_name}:{fingerprint}:{occurrence}"))


class HardenedToolContextHook(base.HookProvider):
    """Inject trusted context and derive a distinct key for every mutation."""

    def __init__(self, request: base.ValidatedRequest, state: InvocationState):
        self.request = request
        self.state = state
        self._occurrences: dict[str, int] = {}

    def prepare_tool_input(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        base.ensure_deadline_remaining(
            self.request.deadline_epoch_ms,
            base.MIN_TOOL_DEADLINE_REMAINING_MS,
        )
        tool_input["userId"] = self.request.actor_id
        tool_input["requestId"] = self.request.request_id
        tool_input["deadlineEpochMs"] = self.request.deadline_epoch_ms

        mutation_operation_id = None
        confirmation_verified = None
        if tool_name in base.MUTATING_TRIP_TOOL_NAMES:
            canonical_payload = _canonical_business_payload(tool_input)
            sequence_key = f"{tool_name}:{hashlib.sha256(canonical_payload.encode('utf-8')).hexdigest()}"
            occurrence = self._occurrences.get(sequence_key, 0)
            self._occurrences[sequence_key] = occurrence + 1
            mutation_operation_id = derive_mutation_operation_id(
                self.request.operation_id,
                tool_name,
                tool_input,
                occurrence,
            )
            confirmation_verified = is_explicit_confirmation(self.request.prompt)
            tool_input["operationId"] = mutation_operation_id
            tool_input["confirmationVerified"] = confirmation_verified
            if confirmation_verified:
                # From this point the Lambda may perform a side effect. A failure is
                # intentionally surfaced to the client instead of replaying the model.
                self.state.mutation_started = True

        base.logger.info(
            json.dumps(
                {
                    "event": "tool_context_injection",
                    "request_id": self.request.request_id,
                    "tool": tool_name,
                    "actor_hash": base.safe_hash(self.request.actor_id),
                    "request_operation_hash": base.safe_hash(self.request.operation_id),
                    "mutation_operation_hash": base.safe_hash(mutation_operation_id),
                    "confirmation_verified": confirmation_verified,
                }
            )
        )

    def inject_context(self, event: Any) -> None:
        from strands.hooks import BeforeToolCallEvent

        if not isinstance(event, BeforeToolCallEvent):
            return
        raw_tool_name = str(event.tool_use.get("name", ""))
        tool_name = base.canonical_trip_tool_name(raw_tool_name)
        tool_input = event.tool_use.get("input")
        if tool_name not in base.TRIP_TOOL_NAMES or not isinstance(tool_input, dict):
            return
        self.prepare_tool_input(tool_name, tool_input)

    def register_hooks(self, registry: base.HookRegistry) -> None:
        from strands.hooks import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self.inject_context)


def mcp_httpx_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=MCP_CONNECT_TIMEOUT_SECONDS,
        read=MCP_READ_TIMEOUT_SECONDS,
        write=MCP_WRITE_TIMEOUT_SECONDS,
        pool=MCP_POOL_TIMEOUT_SECONDS,
    )


@asynccontextmanager
async def create_iam_mcp_transport(gateway_url: str):
    async with httpx.AsyncClient(
        auth=base.AgentCoreSigV4Auth(base.REGION),
        timeout=mcp_httpx_timeout(),
    ) as client:
        async with streamable_http_client(
            gateway_url, http_client=client
        ) as streams:
            yield streams


# The process-wide provider resolves this global at connection time.
base.create_iam_mcp_transport = create_iam_mcp_transport

app = BedrockAgentCoreApp()
initialize_mcp_tools = base.initialize_mcp_tools
reset_mcp_tools = base.reset_mcp_tools


def invoke_agent_once(
    request: base.ValidatedRequest,
    tools: list[Any],
    invocation_state: InvocationState,
) -> str:
    model_config: Dict[str, Any] = {
        "model_id": base.MODEL_ID,
        "region_name": base.REGION,
    }
    if base.GUARDRAILS_ID:
        model_config.update(
            {
                "guardrail_id": base.GUARDRAILS_ID,
                "guardrail_version": base.GUARDRAILS_VERSION,
                "guardrail_trace": "enabled",
            }
        )

    hooks: list[base.HookProvider] = [
        HardenedToolContextHook(request, invocation_state)
    ]
    if base.MEMORY_ID:
        hooks.append(base.TravelAgentMemoryHooks(base.MEMORY_ID, base.memory_client))

    agent = base.Agent(
        system_prompt=base.build_system_prompt(),
        model=base.BedrockModel(**model_config),
        session_manager=base.FileSessionManager(
            session_id=request.session_id,
            session_dir=base.SESSION_DIR,
        ),
        hooks=hooks,
        tools=tools,
        state={
            "actor_id": request.actor_id,
            "session_id": request.session_id,
            "operation_id": request.operation_id,
            "request_id": request.request_id,
            "deadline_epoch_ms": request.deadline_epoch_ms,
        },
    )
    base.ensure_deadline_remaining(request.deadline_epoch_ms)
    return base.response_text(agent(request.prompt))


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: RequestContext = None) -> str:
    started = time.monotonic()
    request: base.ValidatedRequest | None = None
    mcp_retry_count = 0
    try:
        request_payload = base.normalize_request_payload(payload)
        request = base.validate_request(request_payload)
        base.logger.info(
            json.dumps(
                {
                    "event": "request_accepted",
                    "request_id": request.request_id,
                    "session_hash": base.safe_hash(request.session_id),
                    "actor_hash": base.safe_hash(request.actor_id),
                    "operation_hash": base.safe_hash(request.operation_id),
                    "remaining_ms": base.ensure_deadline_remaining(
                        request.deadline_epoch_ms
                    ),
                    "payload_keys": sorted(request_payload.keys()),
                }
            )
        )

        first_state = InvocationState()
        try:
            tools = initialize_mcp_tools()
            result = invoke_agent_once(request, tools, first_state)
        except Exception as exc:
            if first_state.mutation_started or not base.is_retryable_mcp_error(exc):
                raise
            mcp_retry_count = 1
            reset_mcp_tools(type(exc).__name__)
            base.ensure_deadline_remaining(request.deadline_epoch_ms, 1000)
            base.logger.warning(
                json.dumps(
                    {
                        "event": "mcp_retry",
                        "request_id": request.request_id,
                        "error_type": type(exc).__name__,
                        "mutation_started": False,
                    }
                )
            )
            result = invoke_agent_once(
                request,
                initialize_mcp_tools(),
                InvocationState(),
            )

        duration_ms = (time.monotonic() - started) * 1000
        base.log_invocation(
            request,
            duration_ms,
            "success",
            mcp_retry_count=mcp_retry_count,
        )
        return result
    except Exception as exc:
        duration_ms = (time.monotonic() - started) * 1000
        if request is not None:
            base.log_invocation(
                request,
                duration_ms,
                "error",
                mcp_retry_count=mcp_retry_count,
                error=exc,
            )
        else:
            base.logger.info(
                json.dumps(
                    {
                        "event": "agent_invocation",
                        "request_id": "unknown",
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error_type": type(exc).__name__,
                    }
                )
            )
        raise


def __getattr__(name: str) -> Any:
    return getattr(base, name)


if __name__ == "__main__":
    base.initialize_mcp_tools()
    app.run()
