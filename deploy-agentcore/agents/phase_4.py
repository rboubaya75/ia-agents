"""Secure Phase 4 AgentCore runtime entrypoint.

V1 security principles:
- user requests are authorized by AgentCore Runtime native JWT inbound auth;
- client-side identity fields are rejected;
- actor identity is derived from Runtime-validated JWT claims propagated through
  the allowlisted Authorization header, or from legacy trustedIdentity.actorId;
- logs must avoid raw prompts, tokens, secrets and tool inputs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
import requests
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from ddgs import DDGS
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.hooks import AfterInvocationEvent, HookProvider, HookRegistry, MessageAddedEvent
from strands.models import BedrockModel
from strands.session import FileSessionManager
from strands.tools import tool
from strands.tools.mcp.mcp_client import MCPClient


PHASE4_SYSTEM_PROMPT_BASE = """You are a helpful travel assistant with long-term memory and trip planning capabilities.

Guidelines:
- Be friendly and conversational.
- Ask clarifying questions when needed.
- Provide specific, actionable travel recommendations.
- Stay focused on travel-related topics.
- Use trip planning tools to create, view and update trips for users when tools are available.
- Do not ask the user for userId, actorId, tenantId or trustedIdentity.
- Trip tool identity is injected by the runtime based on the authenticated server context.
- Keep answers concise and helpful.
"""

TOOLS_DISABLED_PROMPT_SUFFIX = """

Runtime note: external tools are unavailable for the selected model in streaming mode.
Answer from model knowledge and conversation context only, and do not claim to have created,
updated, searched or persisted trips unless a tool result is present in the conversation.
"""


def build_system_prompt_with_date(base_prompt: str) -> str:
    current_date = datetime.utcnow().strftime("%B %d, %Y")
    return f"{base_prompt}\nCurrent Date: {current_date}\nUse this date as reference for planning and scheduling."


PHASE4_SYSTEM_PROMPT = build_system_prompt_with_date(PHASE4_SYSTEM_PROMPT_BASE)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("travel-agent-phase4")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","component":"phase4","message":"%(message)s"}'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))


MODEL_ID = os.getenv("MODEL_ID", "eu.mistral.pixtral-large-2502-v1:0")
REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "eu-west-3"))
SESSION_DIR = os.getenv("SESSION_DIR", "/tmp/sessions")
APP_SECRET_NAME = os.getenv("APP_SECRET_NAME")

app = BedrockAgentCoreApp()
memory_client = MemoryClient(region_name=REGION)
mcp_client: Optional[MCPClient] = None
mcp_tools = []
_secret_cache: Optional[Dict[str, Any]] = None
_secret_lookup_failed = False


FORBIDDEN_IDENTITY_FIELDS = {
    "actorId",
    "actor_id",
    "userId",
    "user_id",
    "tenantId",
    "tenant_id",
}

TRUSTED_ACTOR_HEADERS = (
    "x-trusted-actor-id",
    "x-agentcore-actor-id",
    "x-amzn-oidc-identity",
)

ACTOR_CLAIM_NAMES = ("sub", "username", "cognito:username")
TOOLS_ENABLED_VALUES = {"1", "true", "yes", "on"}
TOOLS_DISABLED_VALUES = {"0", "false", "no", "off"}
STREAMING_TOOL_UNSUPPORTED_MODEL_MARKERS = (
    "mistral",
    "pixtral",
)


def safe_hash(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def validate_session_id(session_id: str) -> bool:
    return isinstance(session_id, str) and len(session_id) >= 33


def get_secret_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read config from env first, then optional Secrets Manager config.

    Terraform injects runtime config directly as environment variables. Secrets
    Manager is optional. Missing optional secrets must not fail the Runtime path.
    """
    global _secret_cache, _secret_lookup_failed

    env_value = os.getenv(key)
    if env_value is not None:
        return env_value

    if not APP_SECRET_NAME or _secret_lookup_failed:
        return default

    if _secret_cache is None:
        try:
            client = boto3.client("secretsmanager", region_name=REGION)
            response = client.get_secret_value(SecretId=APP_SECRET_NAME)
            _secret_cache = json.loads(response.get("SecretString", "{}"))
        except Exception as exc:
            _secret_lookup_failed = True
            logger.warning(
                json.dumps(
                    {
                        "event": "optional_secret_lookup_failed",
                        "secret_hash": safe_hash(APP_SECRET_NAME),
                        "error_type": type(exc).__name__,
                    }
                )
            )
            return default

    return _secret_cache.get(key, default)


def normalize_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Accept both raw app payloads and AgentCore Runtime target input envelopes."""
    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object.")

    wrapped_payload = payload.get("input")
    if isinstance(wrapped_payload, dict):
        return wrapped_payload

    return payload


def _context_get(source: Any, key: str) -> Any:
    if source is None:
        return None

    if isinstance(source, dict):
        if key in source:
            return source[key]
        lower_key = key.lower()
        for candidate_key, candidate_value in source.items():
            if isinstance(candidate_key, str) and candidate_key.lower() == lower_key:
                return candidate_value
        return None

    getter = getattr(source, "get", None)
    if callable(getter):
        try:
            value = getter(key)
            if value is not None:
                return value
        except Exception:
            pass

    return getattr(source, key, None)


def _context_path(source: Any, *path: str) -> Any:
    current = source
    for key in path:
        current = _context_get(current, key)
        if current is None:
            return None
    return current


def _header_value(headers: Any, name: str) -> Optional[str]:
    if not isinstance(headers, dict):
        return None

    lower_name = name.lower()
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == lower_name and isinstance(value, str):
            return value
    return None


def _extract_headers(context: RequestContext | None) -> Dict[str, str]:
    candidates = [
        _context_get(context, "request_headers"),
        _context_get(context, "headers"),
        _context_path(context, "request", "headers"),
        _context_path(context, "requestContext", "headers"),
        _context_path(context, "request_context", "headers"),
        context,
    ]

    for candidate in candidates:
        if isinstance(candidate, dict):
            string_headers = {
                str(key): str(value)
                for key, value in candidate.items()
                if isinstance(key, str) and value is not None
            }
            if string_headers:
                return string_headers
    return {}


def _normalize_claims(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_claims_from_context(context: RequestContext | None) -> Dict[str, Any]:
    paths = [
        ("authorizer", "jwt", "claims"),
        ("requestContext", "authorizer", "jwt", "claims"),
        ("request_context", "authorizer", "jwt", "claims"),
        ("jwt", "claims"),
        ("identity", "claims"),
        ("claims",),
    ]

    for path in paths:
        claims = _normalize_claims(_context_path(context, *path))
        if claims:
            return claims
    return {}


def _decode_jwt_claims_unverified(token: str) -> Dict[str, Any]:
    """Decode JWT claims after upstream Runtime validation. This does not verify the signature locally."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
        claims = json.loads(decoded.decode("utf-8"))
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def _extract_claims_from_authorization_header(headers: Dict[str, str]) -> Dict[str, Any]:
    authorization = _header_value(headers, "authorization")
    if not authorization:
        return {}

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return {}

    return _decode_jwt_claims_unverified(token.strip())


def _claim_actor_id(claims: Dict[str, Any]) -> Optional[str]:
    for claim_name in ACTOR_CLAIM_NAMES:
        value = claims.get(claim_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _trusted_header_actor_id(headers: Dict[str, str]) -> Optional[str]:
    token_use = _header_value(headers, "x-trusted-token-use")
    if token_use and token_use != "access":
        logger.warning(json.dumps({"event": "trusted_actor_header_rejected", "reason": "unexpected_token_use"}))
        return None

    for header_name in TRUSTED_ACTOR_HEADERS:
        value = _header_value(headers, header_name)
        if value and value.strip():
            return value.strip()
    return None


def extract_session_id(payload: Dict[str, Any], context: RequestContext | None) -> str:
    session_id = payload.get("sessionId") or payload.get("session_id")

    if not session_id and context:
        session_id = _context_get(context, "session_id") or _context_get(context, "sessionId")

    if not session_id:
        raise ValueError("Session ID is required.")
    if not validate_session_id(session_id):
        raise ValueError("Invalid session ID: must be at least 33 characters.")
    return session_id


def extract_actor_id(payload: Dict[str, Any], context: RequestContext | None) -> str:
    supplied = sorted(field for field in FORBIDDEN_IDENTITY_FIELDS if field in payload)
    if supplied:
        raise ValueError("Client-supplied identity fields are forbidden.")

    headers = _extract_headers(context)
    actor_id = _trusted_header_actor_id(headers)
    if actor_id:
        return actor_id

    context_claims = _extract_claims_from_context(context)
    actor_id = _claim_actor_id(context_claims)
    if actor_id:
        return actor_id

    header_claims = _extract_claims_from_authorization_header(headers)
    actor_id = _claim_actor_id(header_claims)
    if actor_id:
        return actor_id

    trusted_identity = payload.get("trustedIdentity") or payload.get("trusted_identity")
    if isinstance(trusted_identity, dict):
        legacy_actor_id = trusted_identity.get("actorId") or trusted_identity.get("actor_id")
        if isinstance(legacy_actor_id, str) and legacy_actor_id.strip():
            return legacy_actor_id.strip()

    logger.warning(
        json.dumps(
            {
                "event": "actor_resolution_failed",
                "payload_keys": sorted(payload.keys()),
                "context_type": type(context).__name__ if context else "none",
                "header_keys_hash": [safe_hash(key.lower()) for key in sorted(headers.keys())],
                "context_claim_keys": sorted(context_claims.keys()),
                "header_claim_keys": sorted(header_claims.keys()),
            }
        )
    )
    raise ValueError("Authenticated actor identity is unavailable from Runtime JWT context.")


def log_invocation(session_id: str, actor_id: str, duration_ms: float, status: str, error: str | None = None) -> None:
    payload = {
        "event": "agent_invocation",
        "session_hash": safe_hash(session_id),
        "actor_hash": safe_hash(actor_id),
        "duration_ms": round(duration_ms, 2),
        "status": status,
    }
    if error:
        payload["error_type"] = error.__class__.__name__ if not isinstance(error, str) else "error"
    logger.info(json.dumps(payload))


@tool
def web_search(keywords: str, region: str = "us-en", max_results: int = 5) -> str:
    """Search the web for public travel information."""
    try:
        safe_max = min(max(int(max_results), 1), 5)
        results = DDGS().text(keywords, region=region, max_results=safe_max)
        if not results:
            return "No search results found."

        formatted_results = []
        for index, result in enumerate(results, 1):
            title = result.get("title", "No title")
            body = result.get("body", "No description")
            formatted_results.append(f"{index}. {title}\n   {body}")
        return "\n".join(formatted_results)
    except Exception:
        logger.warning("web_search_unavailable")
        return "Search temporarily unavailable."


class UserIdInjectionHook(HookProvider):
    """Inject server-derived userId into trip tool calls."""

    def __init__(self, actor_id: str):
        self.actor_id = actor_id

    def inject_user_id(self, event: Any) -> None:
        from strands.hooks import BeforeToolCallEvent

        if not isinstance(event, BeforeToolCallEvent):
            return

        tool_name = str(event.tool_use.get("name", ""))
        tool_input = event.tool_use.get("input", {})

        if not isinstance(tool_input, dict):
            return

        trip_tools = ("create_trip", "get_trips", "get_trip", "update_trip")
        if any(name in tool_name for name in trip_tools):
            had_user_id = "userId" in tool_input
            tool_input["userId"] = self.actor_id
            logger.info(
                json.dumps(
                    {
                        "event": "tool_identity_injection",
                        "tool": tool_name,
                        "actor_hash": safe_hash(self.actor_id),
                        "overrode_user_id": had_user_id,
                    }
                )
            )

    def register_hooks(self, registry: HookRegistry) -> None:
        from strands.hooks import BeforeToolCallEvent

        registry.add_callback(BeforeToolCallEvent, self.inject_user_id)


class TravelAgentMemoryHooks(HookProvider):
    """Retrieve and save user memory under travel/{actorId}/preferences."""

    def __init__(self, memory_id: str, client: MemoryClient):
        self.memory_id = memory_id
        self.client = client
        self.namespace = "travel/{actorId}/preferences"
        self.memory_retrieved_count = 0

    def retrieve_user_context(self, event: MessageAddedEvent) -> None:
        messages = event.agent.messages
        if not messages or messages[-1].get("role") != "user":
            return
        if "toolResult" in messages[-1].get("content", [{}])[0]:
            return

        user_query = messages[-1]["content"][0].get("text", "")
        actor_id = event.agent.state.get("actor_id")
        if not actor_id:
            logger.warning("memory_retrieval_skipped_missing_actor")
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
                content = memory.get("content", {}) if isinstance(memory, dict) else {}
                text = content.get("text", "").strip() if isinstance(content, dict) else ""
                if text:
                    context_items.append(text)

            if context_items:
                original_text = messages[-1]["content"][0]["text"]
                messages[-1]["content"][0]["text"] = (
                    "User Context from Previous Sessions:\n"
                    + "\n".join(context_items)
                    + f"\n\nCurrent Query: {original_text}"
                )
                self.memory_retrieved_count = len(context_items)
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
            if len(messages) < 2 or messages[-1].get("role") != "assistant":
                return

            actor_id = event.agent.state.get("actor_id")
            session_id = event.agent.state.get("session_id")
            if not actor_id or not session_id:
                logger.warning("memory_save_skipped_missing_context")
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


def fetch_gateway_access_token(client_id: str, client_secret: str, token_url: str, scope_string: str) -> str:
    response = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope_string,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_streamable_http_transport(gateway_url: str, token: str):
    return streamablehttp_client(gateway_url, headers={"Authorization": f"Bearer {token}"})


def get_all_mcp_tools(client: MCPClient) -> list[Any]:
    tools: list[Any] = []
    pagination_token = None

    while True:
        page = client.list_tools_sync(pagination_token=pagination_token)
        tools.extend(page)
        pagination_token = getattr(page, "pagination_token", None)
        if pagination_token is None:
            break

    return tools


def initialize_mcp_tools() -> list[Any]:
    global mcp_client, mcp_tools

    if mcp_tools:
        return mcp_tools

    gateway_url = get_secret_value("GATEWAY_URL")
    client_id = get_secret_value("CLIENT_ID")
    client_secret = get_secret_value("CLIENT_SECRET")
    token_url = get_secret_value("TOKEN_URL")
    scope_string = get_secret_value("SCOPE_STRING")

    if not all([gateway_url, client_id, client_secret, token_url, scope_string]):
        logger.warning("gateway_tools_not_configured")
        mcp_tools = []
        return mcp_tools

    token = fetch_gateway_access_token(client_id, client_secret, token_url, scope_string)
    mcp_client = MCPClient(lambda: create_streamable_http_transport(gateway_url, token))
    mcp_client.__enter__()
    mcp_tools = get_all_mcp_tools(mcp_client)
    logger.info(json.dumps({"event": "gateway_tools_loaded", "count": len(mcp_tools)}))
    return mcp_tools


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in TOOLS_ENABLED_VALUES:
        return True
    if normalized in TOOLS_DISABLED_VALUES:
        return False
    return None


def model_supports_streaming_tools(model_id: str) -> bool:
    """Return whether tools should be passed to Strands for the current streaming Bedrock path.

    Strands uses Bedrock ConverseStream under the hood. Some Bedrock models, including
    the currently selected Mistral/Pixtral inference profile, reject toolConfig with
    ConverseStream and fail with: "This model doesn't support tool use in streaming mode."
    """
    override = _parse_bool(os.getenv("AGENT_TOOLS_ENABLED"))
    if override is not None:
        return override

    normalized_model_id = model_id.lower()
    return not any(marker in normalized_model_id for marker in STREAMING_TOOL_UNSUPPORTED_MODEL_MARKERS)


def build_tools_for_model(model_id: str) -> list[Any]:
    if not model_supports_streaming_tools(model_id):
        logger.warning(
            json.dumps(
                {
                    "event": "agent_tools_disabled_for_model",
                    "model_hash": safe_hash(model_id),
                    "reason": "model_does_not_support_tool_use_in_streaming_mode",
                }
            )
        )
        return []

    tools: list[Any] = [web_search]
    tools.extend(initialize_mcp_tools())
    return tools


def system_prompt_for_tools(tools: list[Any]) -> str:
    if tools:
        return PHASE4_SYSTEM_PROMPT
    return PHASE4_SYSTEM_PROMPT + TOOLS_DISABLED_PROMPT_SUFFIX


@app.entrypoint
async def invoke(payload: Dict[str, Any], context: RequestContext = None) -> str:
    start_time = datetime.utcnow()
    session_id = "unknown"
    actor_id = "unknown"

    try:
        request_payload = normalize_request_payload(payload)
        user_input = request_payload.get("prompt")
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("prompt is required.")

        session_id = extract_session_id(request_payload, context)
        actor_id = extract_actor_id(request_payload, context)

        memory_id = get_secret_value("MEMORY_ID")
        guardrail_id = get_secret_value("GUARDRAILS_ID")
        guardrail_version = get_secret_value("GUARDRAILS_VERSION", "1")

        logger.info(
            json.dumps(
                {
                    "event": "request_accepted",
                    "session_hash": safe_hash(session_id),
                    "actor_hash": safe_hash(actor_id),
                    "payload_keys": sorted(request_payload.keys()),
                    "outer_payload_keys": sorted(payload.keys()) if payload is not request_payload else [],
                }
            )
        )

        model_config: Dict[str, Any] = {"model_id": MODEL_ID, "region_name": REGION}
        if guardrail_id:
            model_config.update(
                {
                    "guardrail_id": guardrail_id,
                    "guardrail_version": guardrail_version,
                    "guardrail_trace": "enabled",
                }
            )

        model = BedrockModel(**model_config)
        session_manager = FileSessionManager(session_id=session_id, session_dir=SESSION_DIR)

        hooks: list[HookProvider] = [UserIdInjectionHook(actor_id)]
        if memory_id:
            hooks.append(TravelAgentMemoryHooks(memory_id, memory_client))

        tools = build_tools_for_model(MODEL_ID)
        agent_kwargs: Dict[str, Any] = {
            "system_prompt": system_prompt_for_tools(tools),
            "model": model,
            "session_manager": session_manager,
            "hooks": hooks,
            "state": {"actor_id": actor_id, "session_id": session_id},
        }
        if tools:
            agent_kwargs["tools"] = tools

        agent = Agent(**agent_kwargs)

        response = agent(user_input)
        result = response.message["content"][0]["text"]

        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_invocation(session_id, actor_id, duration_ms, "success")
        return result

    except ValueError as exc:
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_invocation(session_id, actor_id, duration_ms, "validation_error", str(exc))
        raise
    except Exception as exc:
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        log_invocation(session_id, actor_id, duration_ms, "error", str(exc))
        raise


if __name__ == "__main__":
    app.run()
