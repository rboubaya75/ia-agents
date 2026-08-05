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

# Cognito emet deux jetons pour le meme utilisateur, et ils ne nomment pas de la meme
# facon le claim qui designe le client applicatif : le jeton d'identite porte `aud`, le
# jeton d'acces porte `client_id`. La valeur est la meme — l'identifiant du client. Le
# service accepte les deux et choisit le claim d'apres `token_use`, ce qui laisse au
# client le choix du jeton qu'il presente sans jamais relacher la comparaison.
#
# Une audience verifiee « quand le claim est la » ne serait pas un controle : un
# `token_use` inattendu doit refuser, pas passer sans comparaison. C'est pourquoi la
# table est fermee et l'absence de correspondance vaut refus.
AUDIENCE_CLAIM_BY_TOKEN_USE = {
    "id": "aud",
    "access": "client_id",
}

# Tolerance d'horloge, bornee et declaree (V2-LLD-005 §3.5). Cognito n'emet pas de
# `nbf` : il est verifie lorsqu'il est present, jamais exige, sans quoi tout jeton
# Cognito serait refuse.
CLOCK_LEEWAY_SECONDS = 60

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
        # §7.1.3 — iss is compared to the configured parameter, never to a value read
        # out of the token itself.
        #
        # L'audience ne peut pas etre deleguee a PyJWT : son parametre `audience` ne sait
        # lire que `aud`, absent du jeton d'acces. Et le laisser a None ne revient pas a
        # « ne rien exiger » — PyJWT refuse alors tout jeton *portant* un `aud`, donc tous
        # les jetons d'identite. La verification est donc desactivee ici et reprise juste
        # apres, sur le claim que designe `token_use`.
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.cognito_issuer,
            leeway=CLOCK_LEEWAY_SECONDS,
            options={
                "verify_aud": False,
                "require": ["exp", "iat", "iss", "sub", "token_use"],
            },
        )
    except InvalidTokenError as exc:
        logger.info("token rejected: %s", exc)
        raise HTTPException(401, "Invalid token") from exc

    _verify_audience(claims)
    _verify_subject(claims)
    return claims


def _verify_audience(claims: dict[str, Any]) -> None:
    """Compare le client applicatif designe par le jeton a la valeur configuree.

    Un jeton correctement signe par notre pool mais emis pour un autre client est un
    jeton authentique : seule cette comparaison etablit qu'il nous est destine.
    """
    token_use = claims.get("token_use")
    claim_name = AUDIENCE_CLAIM_BY_TOKEN_USE.get(token_use)
    if claim_name is None:
        logger.info("token rejected, unexpected token_use %r", token_use)
        raise HTTPException(401, "Invalid token")

    value = claims.get(claim_name)
    # `aud` vaut une chaine sur un jeton Cognito, mais la RFC 7519 autorise une liste.
    # Normaliser evite de comparer une chaine a une liste, ce qui echouerait en silence.
    audiences = value if isinstance(value, list) else [value]
    if settings.cognito_app_client_id not in audiences:
        logger.info("token rejected, %s does not designate the configured client", claim_name)
        raise HTTPException(401, "Invalid token")


def _verify_subject(claims: dict[str, Any]) -> None:
    # `require` etablit la presence, pas la substance : un `sub` vide passerait et
    # deviendrait un actorId vide jusque dans le registre d'autorisation.
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        logger.info("token rejected, sub absent or empty")
        raise HTTPException(401, "Invalid token")
