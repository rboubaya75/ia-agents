from typing import Any

from fastapi import Header, HTTPException

from app.auth import verify_token


async def bearer_claims(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Validate the Authorization header and return the verified JWT claims.

    The header is declared optional so that a missing or malformed one is answered with
    401 — `Header(...)` would let FastAPI reject it as a request validation error (422),
    which tells the client nothing about how to recover. The scheme is matched case
    insensitively, as RFC 7235 §2.1 requires.
    """
    if authorization is None or authorization[:7].lower() != "bearer ":
        raise HTTPException(
            401,
            "Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await verify_token(authorization[7:])
