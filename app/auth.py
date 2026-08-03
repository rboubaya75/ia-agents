import asyncio
import time
from typing import Any

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

from app.config import settings

_lock = asyncio.Lock()
_cache: dict[str, Any] | None = None
_cached_at: float = 0.0
_attempted_at: float = 0.0


def _jwks_uri() -> str:
    return f"{settings.cognito_issuer.rstrip('/')}/.well-known/jwks.json"


async def _fetch() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(_jwks_uri())
        response.raise_for_status()
        return response.json()


async def _get_jwks() -> dict[str, Any]:
    global _cache, _cached_at, _attempted_at

    now = time.monotonic()
    ttl = settings.jwks_cache_ttl_seconds
    tolerance = settings.jwks_stale_tolerance_seconds
    min_interval = settings.jwks_refresh_min_interval_seconds

    async with _lock:
        age = now - _cached_at if _cache is not None else float("inf")

        if age < ttl:
            return _cache  # type: ignore[return-value]

        can_attempt = (now - _attempted_at) >= min_interval

        if not can_attempt:
            if _cache is not None and age < ttl + tolerance:
                return _cache
            raise HTTPException(503, "JWKS endpoint temporarily rate-limited")

        _attempted_at = now
        try:
            _cache = await _fetch()
            _cached_at = now
            return _cache
        except Exception:
            if _cache is not None and age < ttl + tolerance:
                return _cache
            raise HTTPException(503, "JWKS refresh failed and no valid cached keyset")


async def warm() -> None:
    await _get_jwks()


async def is_ready() -> bool:
    try:
        await _get_jwks()
        return True
    except Exception:
        return False


async def verify_token(token: str) -> dict[str, Any]:
    jwks = await _get_jwks()
    try:
        return jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=settings.cognito_issuer,
        )
    except JWTError as exc:
        raise HTTPException(401, f"Invalid token: {exc}") from exc
