from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # JWKS / authentication (V2-LLD-001 §7.1.4)
    sse_keepalive_seconds: int
    cognito_issuer: str
    cognito_app_client_id: str
    jwks_cache_ttl_seconds: int
    jwks_stale_tolerance_seconds: int
    jwks_refresh_min_interval_seconds: int

    # Agent runtime (V2-LLD-003 §12.1)
    # Empty string = stub mode (no AgentCore Runtime call)
    agentcore_runtime_arn: str = ""
    bedrock_invocation_id: str = ""
    agent_prompt_version: str = "v1"

    # Agent budgets (V2-LLD-003 §5.2) — defaults are configurable via SSM/Secrets
    agent_max_turns: int = 10
    agent_max_tool_calls: int = 20
    agent_max_tokens: int = 8192
    agent_deadline_seconds: int = 120


settings = Settings()
