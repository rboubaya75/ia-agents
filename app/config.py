from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    sse_keepalive_seconds: int
    cognito_issuer: str
    cognito_app_client_id: str
    jwks_cache_ttl_seconds: int
    jwks_stale_tolerance_seconds: int
    jwks_refresh_min_interval_seconds: int


settings = Settings()
