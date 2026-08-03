import asyncio
import logging
import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException
from jwt import InvalidTokenError, PyJWKSet

from app.config import settings

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_cache: dict[str, Any] | None = None
_cached_at: float = 0.0
# None, never 0.0: time.monotonic() counts from host boot, and on a freshly launched
# Fargate microVM it is a single-digit number. A 0.0 sentinel reads as "last attempted
# at boot", so the anti-amplification guard below would reject the very first refresh
# and the task would never start.
_attempted_at: float | None = None


def _jwks_uri() -> str:
    return f"{settings.cognito_issuer.rstrip('/')}/.well-known/jwks.json"


async def _fetch() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(_jwks_uri())
        response.raise_for_status()
        return response.json()


async def _get_jwks(force: bool = False) -> dict[str, Any]:
    """Return the cached keyset, refreshing it once the TTL has elapsed.

    `force` bypasses the TTL — a token carrying an unknown kid is the signal that the
    cache predates a key rotation — but never bypasses jwks_refresh_min_interval_seconds
    (V2-LLD-001 §7.1.4), which is what keeps a burst of bad tokens from amplifying into
    a burst of requests to Cognito.
    """
    global _cache, _cached_at, _attempted_at

    ttl = settings.jwks_cache_ttl_seconds
    tolerance = settings.jwks_stale_tolerance_seconds
    min_interval = settings.jwks_refresh_min_interval_seconds

    async with _lock:
        # Measured under the lock: a value read before acquiring it would be stale by
        # however long the holder spent fetching.
        now = time.monotonic()
        age = now - _cached_at if _cache is not None else float("inf")

        if not force and age < ttl:
            return _cache  # type: ignore[return-value]

        if _attempted_at is not None and (now - _attempted_at) < min_interval:
            # A rate-limited forced refresh still hands back the keyset we hold: the
            # caller rejects that one token itself, which beats a 503 for everyone.
            if _cache is not None and (force or age < ttl + tolerance):
                return _cache
            raise HTTPException(503, "JWKS endpoint temporarily unavailable")

        _attempted_at = now
        try:
            _cache = await _fetch()
            _cached_at = now
            return _cache
        except Exception:
            if _cache is not None and (force or age < ttl + tolerance):
                logger.warning("JWKS refresh failed, serving cached keyset", exc_info=True)
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


def _signing_key(jwks: dict[str, Any], kid: str | None) -> Any | None:
    if kid is None:
        return None
    try:
        keyset = PyJWKSet.from_dict(jwks)
    except Exception:
        logger.warning("JWKS payload holds no usable key", exc_info=True)
        return None
    for key in keyset.keys:
        if key.key_id == kid:
            return key.key
    return None


async def verify_token(token: str) -> dict[str, Any]:
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except InvalidTokenError as exc:
        logger.info("token rejected, malformed header: %s", exc)
        raise HTTPException(401, "Malformed token") from exc

    key = _signing_key(await _get_jwks(), kid)

    # Cognito rotates its signing keys. An unknown kid means the cached keyset is older
    # than the rotation far more often than it means a forged token, so refresh once
    # before rejecting — otherwise valid tokens are refused for a whole TTL.
    if key is None:
        key = _signing_key(await _get_jwks(force=True), kid)
    if key is None:
        logger.info("token rejected, unknown kid %r", kid)
        raise HTTPException(401, "Unknown signing key")

    try:
        # §7.1.3 — iss and aud are compared to the configured parameters, never to a
        # value read out of the token itself.
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=settings.cognito_issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except InvalidTokenError as exc:
        logger.info("token rejected: %s", exc)
        raise HTTPException(401, "Invalid token") from exc
