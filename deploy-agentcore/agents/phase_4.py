"""Secure V1 AgentCore Runtime entrypoint.

Inbound requests are accepted only from the Lambda security facade through IAM.
The facade derives the actor from a validated Cognito access token and injects a
strict ``trustedIdentity`` object. Runtime rejects every other identity source.
All V1 tools are loaded from AgentCore Gateway and signed with the Runtime role.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
import httpx
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry, MessageAddedEvent
from strands.models import BedrockModel
from strands.session import FileSessionManager
from strands.tools.mcp.mcp_client import MCPClient

PHASE4_SYSTEM_PROMPT_BASE = """You are a helpful travel assistant with long-term memory and trip planning capabilities.

Guidelines:
- Be friendly and conversational.
- Ask clarifying questions when needed.
- Provide specific, actionable travel recommendations.
- Stay focused on travel-related topics.
- Use trip planning tools to create, view and update trips for users.
- Never ask for userId, actorId, tenantId or trustedIdentity.
- Tool identity is injected by the trusted server context.
- Use only the tools exposed by the governed AgentCore Gateway.
- Keep answers concise and helpful.
"""

MODEL_ID = os.getenv("MODEL_ID", "eu.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-3"))
SESSION_DIR = os.getenv("SESSION_DIR", "/tmp/sessions")
MEMORY_ID = os.getenv("MEMORY_ID", "")
GATEWAY_URL = os.getenv("GATEWAY_URL", "")
GATEWAY_AUTH_MODE = os.getenv("GATEWAY_AUTH_MODE", "aws_iam").lower()
REQUIRE_MCP_TOOLS = os.getenv("REQUIRE_MCP_TOOLS", "true").lower() == "true"
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "4000"))
GUARDRAILS_ID = os.getenv("GUARDRAILS_ID", "")
GUARDRAILS_VERSION = os.getenv("GUARDRAILS_VERSION", "1")

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{33,128}$")
ACTOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:@+-]{1,256}$")
ALLOWED_REQUEST_FIELDS = {"prompt", "sessionId", "trustedIdentity"}
FORBIDDEN_IDENTITY_FIELDS = {
    "actorId",
    "actor_id",
    "userId",
    "user_id",
    "tenantId",
    "tenant_id",
    "trusted_identity",
    "groups",
}
TRIP_TOOL_NAMES = ("create_trip", "get_trips", "get_trip", "update_trip")


def setup_logging(level: str = "INFO") -> logging.Logger:
    runtime_logger = logging.getLogger("travel-agent-phase4")
    runtime_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    runtime_logger.propagate = False
    if not runtime_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
                '"component":"phase4","message":"%(message)s"}'
            )
        )
        runtime_logger.addHandler(handler)
    return runtime_logger


logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))
app = BedrockAgentCoreApp()
memory_client = MemoryClient(region_name=REGION)
mcp_client: Optional[MCPClient] = None
mcp_tools: list[Any] = []
_mcp_initialized = False
_mcp_init_lock = threading.Lock()


def safe_hash(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def build_system_prompt() -> str:
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return (
        f"{PHASE4_SYSTEM_PROMPT_BASE}\nCurrent Date: {current_date}\n"
        "Use this date as reference for planning and scheduling."
    )


def normalize_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object.")
    wrapped = payload.get("input")
    request_payload = wrapped if isinstance(wrapped, dict) else payload
    if not isinstance(request_payload, dict):
        raise ValueError("Request payload must be a JSON object.")
    return request_payload


def validate_request(payload: Dict[str, Any]) -> tuple[str, str, str]:
    forbidden = sorted(FORBIDDEN_IDENTITY_FIELDS.intersection(payload))
    if forbidden:
        raise ValueError("Untrusted identity fields are forbidden.")

    unexpected = sorted(set(payload).difference(ALLOWED_REQUEST_FIELDS))
    if unexpected:
        raise ValueError("Unsupported request fields are forbidden.")

    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"prompt must be {MAX_PROMPT_CHARS} characters or fewer.")

    session_id = payload.get("sessionId")
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("sessionId must contain 33 to 128 safe characters.")

    trusted_identity = payload.get("trustedIdentity")
    if not isinstance(trusted_identity, dict) or set(trusted_identity) != {"actorId"}:
        raise ValueError("A server-generated trustedIdentity is required.")
    actor_id = trusted_identity.get("actorId")
    if not isinstance(actor_id, str) or not ACTOR_ID_PATTERN.fullmatch(actor_id):
        raise ValueError("trustedIdentity.actorId is invalid.")

    return prompt, session_id, actor_id


def log_invocation(session_id: str, actor_id: str, duration_ms: float, status: str, error: Any = None) -> None:
    event: Dict[str, Any] = {
        "event": "agent_invocation",
        "session_hash": safe_hash(session_id),
        "actor_hash": safe_hash(actor_id),
        "duration_ms": round(duration_ms, 2),
        "status": status,
    }
    if error is not None:
        event["error_type"] = type(error).__name__
    logger.info(json.dumps(event))


class UserIdInjectionHook(HookProvider):
    """Overwrite userId on every trip tool call with the trusted actor ID."""

    def __init__(self, actor_id: str):
        self.actor_id = actor_id

    def inject_user_id(self, event: Any) -> None:
        from strands.hooks import BeforeToolCallEvent

        if not isinstance(event, BeforeToolCallEvent):
            return
        tool_name = str(event.tool_use.get("name", ""))
        tool_input = event.tool_use.get("input")
        if not isinstance(tool_input, dict):
            return
        if any(name in tool_name for name in TRIP_TOOL_NAMES):
            tool_input["userId"] = self.actor_id
            logger.info(
                json.dumps(
                    {
                        "event": "tool_identity_injection",
                        "tool": tool_name,
                        "actor_hash": safe_hash(self.actor_id),
                    }
                )
            )

    def register_hooks(self, registry: HookRegistry) -> None:
        from strands.hooks import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self.inject_user_id)


class TravelAgentMemoryHooks(HookProvider):
    """Retrieve and save memory under the authenticated actor namespace."""

    def __init__(self, memory_id: str, client: MemoryClient):
        self.memory_id = memory_id
        self.client = client
        self.namespace = "travel/{actorId}/preferences"

    def retrieve_user_context(self, event: MessageAddedEvent) -> None:
        messages = event.agent.messages
        if not messages or messages[-1].get("role") != "user":
            return
        content = messages[-1].get("content", [{}])[0]
        if "toolResult" in content:
            return

        actor_id = event.agent.state.get("actor_id")
        user_query = content.get("text", "")
        if not actor_id or not user_query:
            return
        try:
            memories = self.client.retrieve_memories(
                memory_id=self.memory_id,
                namespace=self.namespace.format(actorId=actor_id),
                query=user_query,
                top_k=3,
            )
            context_items = []
            for memory in memories:
                memory_content = memory.get("content", {}) if isinstance(memory, dict) else {}
                text = memory_content.get("text", "").strip() if isinstance(memory_content, dict) else ""
                if text:
                    context_items.append(text)
            if context_items:
                content["text"] = (
                    "User Context from Previous Sessions:\n"
                    + "\n".join(context_items)
                    + f"\n\nCurrent Query: {user_query}"
                )
                logger.info(
                    json.dumps(
                        {
                            "event": "memory_retrieved",
                            "actor_hash": safe_hash(actor_id),
                            "count": len(context_items),
                        }
                    )
                )
        except Exception:
            logger.warning("memory_retrieval_failed")

    def save_interaction(self, event: AfterInvocationEvent) -> None:
        try:
            messages = event.agent.messages
            actor_id = event.agent.state.get("actor_id")
            session_id = event.agent.state.get("session_id")
            if len(messages) < 2 or not actor_id or not session_id:
                return

            user_query = None
            assistant_response = None
            for message in reversed(messages):
                content = message.get("content", [{}])[0]
                if message.get("role") == "assistant" and assistant_response is None:
                    assistant_response = content.get("text")
                elif message.get("role") == "user" and user_query is None and "toolResult" not in content:
                    user_query = content.get("text")
                    break
            if not user_query or not assistant_response:
                return
            if "Current Query:" in user_query:
                user_query = user_query.split("Current Query:", 1)[1].strip()

            self.client.create_event(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(user_query, "USER"), (assistant_response, "ASSISTANT")],
            )
            logger.info(json.dumps({"event": "memory_saved", "actor_hash": safe_hash(actor_id)}))
        except Exception:
            logger.warning("memory_save_failed")

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(MessageAddedEvent, self.retrieve_user_context)
        registry.add_callback(AfterInvocationEvent, self.save_interaction)


class AgentCoreSigV4Auth(httpx.Auth):
    """Sign each AgentCore Gateway HTTP request with the Runtime role."""

    requires_request_body = True

    def __init__(self, region: str):
        self.region = region
        self.session = boto3.Session(region_name=region)

    def auth_flow(self, request: httpx.Request):
        credentials = self.session.get_credentials()
        if credentials is None:
            raise RuntimeError("AWS credentials are unavailable for MCP Gateway signing.")
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", self.region).add_auth(aws_request)
        for name, value in aws_request.headers.items():
            request.headers[name] = value
        yield request


@asynccontextmanager
async def create_iam_mcp_transport(gateway_url: str):
    timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
    async with httpx.AsyncClient(auth=AgentCoreSigV4Auth(REGION), timeout=timeout) as client:
        async with streamablehttp_client(gateway_url, http_client=client) as streams:
            yield streams


def get_all_mcp_tools(client: MCPClient) -> list[Any]:
    tools: list[Any] = []
    pagination_token = None
    while True:
        page = client.list_tools_sync(pagination_token=pagination_token)
        tools.extend(page)
        pagination_token = getattr(page, "pagination_token", None)
        if pagination_token is None:
            return tools


def initialize_mcp_tools() -> list[Any]:
    global _mcp_initialized, mcp_client, mcp_tools

    with _mcp_init_lock:
        if _mcp_initialized:
            return mcp_tools

        if not GATEWAY_URL:
            if REQUIRE_MCP_TOOLS:
                raise RuntimeError("GATEWAY_URL is required for V1 MCP tools.")
            logger.warning("gateway_tools_not_configured")
            _mcp_initialized = True
            return []
        if GATEWAY_AUTH_MODE != "aws_iam":
            raise RuntimeError("Only aws_iam MCP Gateway authentication is supported in V1.")

        candidate_client: Optional[MCPClient] = None
        try:
            candidate_client = MCPClient(lambda: create_iam_mcp_transport(GATEWAY_URL))
            candidate_client.__enter__()
            candidate_tools = get_all_mcp_tools(candidate_client)
            if REQUIRE_MCP_TOOLS and not candidate_tools:
                raise RuntimeError("AgentCore Gateway returned no MCP tools for V1.")

            mcp_client = candidate_client
            mcp_tools = candidate_tools
            _mcp_initialized = True
            logger.info(json.dumps({"event": "gateway_tools_loaded", "count": len(mcp_tools)}))
            return mcp_tools
        except Exception as exc:
            if candidate_client is not None:
                try:
                    candidate_client.__exit__(type(exc), exc, exc.__traceback__)
                except Exception:
                    logger.warning("gateway_tools_cleanup_failed")
            mcp_client = None
            mcp_tools = []
            _mcp_initialized = False
            logger.error(json.dumps({"event": "gateway_tools_load_failed", "error_type": type(exc).__name__}))
            if REQUIRE_MCP_TOOLS:
                raise
            _mcp_initialized = True
            return []


def response_text(response: Any) -> str:
    message = getattr(response, "message", None)
    if not isinstance(message, dict):
        raise RuntimeError("Agent response message is missing.")
    content = message.get("content")
    if not isinstance(content, list):
        raise RuntimeError("Agent response content is missing.")
    parts = [item.get("text", "") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
    result = "".join(parts).strip()
    if not result:
        raise RuntimeError("Agent response text is empty.")
    return result


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: RequestContext = None) -> str:
    started = datetime.now(timezone.utc)
    session_id = "unknown"
    actor_id = "unknown"
    try:
        request_payload = normalize_request_payload(payload)
        user_input, session_id, actor_id = validate_request(request_payload)
        logger.info(
            json.dumps(
                {
                    "event": "request_accepted",
                    "session_hash": safe_hash(session_id),
                    "actor_hash": safe_hash(actor_id),
                    "payload_keys": sorted(request_payload.keys()),
                }
            )
        )

        model_config: Dict[str, Any] = {"model_id": MODEL_ID, "region_name": REGION}
        if GUARDRAILS_ID:
            model_config.update(
                {
                    "guardrail_id": GUARDRAILS_ID,
                    "guardrail_version": GUARDRAILS_VERSION,
                    "guardrail_trace": "enabled",
                }
            )

        hooks: list[HookProvider] = [UserIdInjectionHook(actor_id)]
        if MEMORY_ID:
            hooks.append(TravelAgentMemoryHooks(MEMORY_ID, memory_client))

        tools = initialize_mcp_tools()
        agent = Agent(
            system_prompt=build_system_prompt(),
            model=BedrockModel(**model_config),
            session_manager=FileSessionManager(session_id=session_id, session_dir=SESSION_DIR),
            hooks=hooks,
            tools=tools,
            state={"actor_id": actor_id, "session_id": session_id},
        )

        result = response_text(agent(user_input))
        duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        log_invocation(session_id, actor_id, duration_ms, "success")
        return result
    except Exception as exc:
        duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        log_invocation(session_id, actor_id, duration_ms, "error", exc)
        raise


if __name__ == "__main__":
    app.run()
