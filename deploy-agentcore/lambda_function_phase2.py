"""Phase 2 read isolation, pagination binding and redacted evidence wrapper.

The existing hardened mutation implementation remains the source of truth for
confirmation and durable idempotency. This wrapper strengthens read behavior,
binds continuation tokens to the authenticated actor and emits evidence-safe
outcome events for all four Trip tools.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
from typing import Any, Dict

from boto3.dynamodb.conditions import Key

import lambda_function_code as base
import lambda_function_hardened as hardened

TOKEN_VERSION = 2
TOKEN_ACTOR_FIELD = "actorHash"
TOKEN_TRIP_FIELD = "tripId"


def _event_hash(event: Dict[str, Any], field: str) -> str:
    value = event.get(field)
    return base._safe_hash(value) if isinstance(value, str) and value else "unknown"


def _encode_next_token(last_key: Dict[str, Any], user_id: str) -> str:
    if last_key.get("userId") != user_id:
        raise RuntimeError(
            "DynamoDB pagination key escaped the authenticated partition."
        )
    trip_id = base._trip_id_value(last_key.get("tripId"), "pagination tripId")
    payload = json.dumps(
        {
            "v": TOKEN_VERSION,
            TOKEN_ACTOR_FIELD: base._safe_hash(user_id),
            TOKEN_TRIP_FIELD: trip_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_next_token(token: Any, user_id: str) -> Dict[str, str] | None:
    if token is None:
        return None
    if (
        not isinstance(token, str)
        or not token
        or len(token) > base.MAX_NEXT_TOKEN_CHARS
    ):
        raise base.ValidationError("nextToken is invalid.")
    try:
        padded = token + "=" * (-len(token) % 4)
        value = json.loads(
            base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        )
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as exc:
        raise base.ValidationError("nextToken is invalid.") from exc

    expected_keys = {"v", TOKEN_ACTOR_FIELD, TOKEN_TRIP_FIELD}
    if (
        not isinstance(value, dict)
        or set(value) != expected_keys
        or value.get("v") != TOKEN_VERSION
    ):
        raise base.ValidationError("nextToken is invalid.")

    actor_hash = value.get(TOKEN_ACTOR_FIELD)
    expected_actor_hash = base._safe_hash(user_id)
    if not isinstance(actor_hash, str) or not hmac.compare_digest(
        actor_hash, expected_actor_hash
    ):
        raise base.ValidationError(
            "nextToken is not valid for the authenticated user."
        )

    return {
        "userId": user_id,
        "tripId": base._trip_id_value(
            value.get(TOKEN_TRIP_FIELD), "nextToken tripId"
        ),
    }


def get_trips(event: Dict[str, Any]) -> Dict[str, Any]:
    base._reject_unexpected(event, base.GET_TRIPS_FIELDS)
    user_id, request_id = base._validate_context(event)
    limit = base._bounded_integer(
        event, "limit", base.DEFAULT_PAGE_SIZE, base.MAX_PAGE_SIZE
    )
    exclusive_start_key = _decode_next_token(event.get("nextToken"), user_id)
    query: Dict[str, Any] = {
        "KeyConditionExpression": Key("userId").eq(user_id),
        "Limit": limit,
    }
    if exclusive_start_key:
        query["ExclusiveStartKey"] = exclusive_start_key

    result = base._get_table().query(**query)
    trips = [base._public_trip(item) for item in result.get("Items", [])]
    response: Dict[str, Any] = {"trips": trips, "count": len(trips)}
    last_key = result.get("LastEvaluatedKey")
    has_more = isinstance(last_key, dict) and bool(last_key)
    if has_more:
        response["nextToken"] = _encode_next_token(last_key, user_id)

    base.logger.info(
        json.dumps(
            {
                "event": "trips_listed",
                "request_id": request_id,
                "actor_hash": base._safe_hash(user_id),
                "count": len(trips),
                "has_more": has_more,
            }
        )
    )
    return response


def get_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    base._reject_unexpected(event, base.CONTEXT_FIELDS | {"tripId"})
    user_id, request_id = base._validate_context(event)
    trip_id = base._trip_id(event)
    item = base._get_table().get_item(
        Key={"userId": user_id, "tripId": trip_id},
        ConsistentRead=True,
    ).get("Item")
    found = isinstance(item, dict) and bool(item)
    base.logger.info(
        json.dumps(
            {
                "event": "trip_read",
                "request_id": request_id,
                "actor_hash": base._safe_hash(user_id),
                "trip_hash": base._safe_hash(trip_id),
                "found": found,
            }
        )
    )
    if not found:
        return {"found": False, "tripId": trip_id, "message": "Trip not found."}
    return {"found": True, "trip": base._public_trip(item)}


def _log_mutation_outcome(
    tool_name: str,
    event: Dict[str, Any],
    request_id: str,
    response: Dict[str, Any],
) -> None:
    success_field = "created" if tool_name == "create_trip" else "updated"
    base.logger.info(
        json.dumps(
            {
                "event": "trip_mutation_outcome",
                "tool": tool_name,
                "request_id": request_id,
                "actor_hash": _event_hash(event, "userId"),
                "operation_hash": _event_hash(event, "operationId"),
                "trip_hash": _event_hash(response, "tripId"),
                "successful": response.get(success_field) is True,
                "replayed": response.get("replayed") is True,
            }
        )
    )


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    tool_name = base._extract_tool_name(context)
    raw_request_id = event.get("requestId") if isinstance(event, dict) else None
    request_id = (
        raw_request_id
        if isinstance(raw_request_id, str)
        and base.REQUEST_ID_PATTERN.fullmatch(raw_request_id)
        else "unknown"
    )
    base.logger.info(
        json.dumps(
            {
                "event": "trip_tool_invocation",
                "tool": tool_name or "unknown",
                "request_id": request_id,
            }
        )
    )
    handlers = {
        "create_trip": hardened.create_trip,
        "get_trips": get_trips,
        "get_trip": get_trip,
        "update_trip": hardened.update_trip,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return {"error": "unsupported_operation", "message": "Unsupported operation."}
    if not isinstance(event, dict):
        return {
            "error": "validation_error",
            "message": "Tool input must be a JSON object.",
        }

    try:
        response = handler(event)
        if tool_name in {"create_trip", "update_trip"} and isinstance(response, dict):
            _log_mutation_outcome(tool_name, event, request_id, response)
        return response
    except base.IdempotencyConflictError as exc:
        base.logger.warning(
            json.dumps(
                {
                    "event": "trip_idempotency_conflict",
                    "tool": tool_name,
                    "request_id": request_id,
                    "actor_hash": _event_hash(event, "userId"),
                    "operation_hash": _event_hash(event, "operationId"),
                    "trip_hash": _event_hash(event, "tripId"),
                }
            )
        )
        return {"error": "idempotency_conflict", "message": str(exc)}
    except base.ValidationError as exc:
        base.logger.warning(
            json.dumps(
                {
                    "event": "trip_validation_rejected",
                    "tool": tool_name,
                    "request_id": request_id,
                    "actor_hash": _event_hash(event, "userId"),
                }
            )
        )
        return {"error": "validation_error", "message": str(exc)}
    except Exception:
        base.logger.exception(
            "trip_tool_error tool=%s request_id=%s",
            tool_name or "unknown",
            request_id,
        )
        raise
