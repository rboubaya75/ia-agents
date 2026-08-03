import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from app.deps import bearer_claims
from app.state import cancel_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.post("/operations/{operation_id}/cancel")
async def cancel_operation(
    operation_id: str = Path(max_length=64),
    claims: dict[str, Any] = Depends(bearer_claims),
) -> JSONResponse:
    operation = cancel_registry.get(operation_id)

    # An operation owned by another actor is reported exactly like an unknown one:
    # distinguishing the two would confirm the existence of someone else's operation.
    if operation is None or operation.actor_id != claims["sub"]:
        raise HTTPException(404, "Operation not found or already completed")

    operation.cancel_event.set()
    logger.info("operation %s cancelled by its owner", operation_id)
    return JSONResponse({"status": "cancelled", "operationId": operation_id})
