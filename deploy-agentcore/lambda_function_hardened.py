"""Hardened mutation handlers for the AgentCore Trip Tools Lambda.

The stable read-only and validation helpers remain in ``lambda_function_code``.
This module adds server-enforced confirmation, strongly consistent replay
resolution and a durable update idempotency ledger without duplicating the
public read handlers.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from typing import Any, Dict

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

import lambda_function_code as base

IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "604800"))
if IDEMPOTENCY_TTL_SECONDS < 3600 or IDEMPOTENCY_TTL_SECONDS > 2_592_000:
    raise RuntimeError("IDEMPOTENCY_TTL_SECONDS must be between 3600 and 2592000.")

IDEMPOTENCY_PARTITION_PREFIX = "IDEMPOTENCY#"
IDEMPOTENCY_SORT_PREFIX = "MUTATION#"
IDEMPOTENCY_ENTITY_TYPE = "IDEMPOTENCY"
CONFIRMATION_FIELD = "confirmationVerified"

CREATE_FIELDS = set(base.CREATE_FIELDS) | {CONFIRMATION_FIELD}
UPDATE_FIELDS = set(base.UPDATE_FIELDS) | {CONFIRMATION_FIELD}
_serializer = TypeSerializer()


def _confirmation_verified(event: Dict[str, Any]) -> None:
    if event.get(CONFIRMATION_FIELD) is not True:
        raise base.ValidationError(
            "Explicit user confirmation is required for this mutation."
        )


def _serialize_item(item: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {key: _serializer.serialize(value) for key, value in item.items()}


def _idempotency_key(user_id: str, operation_id: str) -> Dict[str, str]:
    return {
        "userId": f"{IDEMPOTENCY_PARTITION_PREFIX}{user_id}",
        "tripId": f"{IDEMPOTENCY_SORT_PREFIX}{operation_id}",
    }


def _read_idempotency(
    table: Any, user_id: str, operation_id: str
) -> Dict[str, Any] | None:
    item = table.get_item(
        Key=_idempotency_key(user_id, operation_id),
        ConsistentRead=True,
    ).get("Item")
    return item if isinstance(item, dict) else None


def _idempotency_record(
    user_id: str,
    operation_id: str,
    operation_hash: str,
    trip_id: str,
) -> Dict[str, Any]:
    return {
        **_idempotency_key(user_id, operation_id),
        "entityType": IDEMPOTENCY_ENTITY_TYPE,
        "operationType": "update_trip",
        "operationHash": operation_hash,
        "targetTripId": trip_id,
        "createdAt": base._utc_now(),
        "expiresAt": int(time.time()) + IDEMPOTENCY_TTL_SECONDS,
    }


def _validate_idempotency_record(
    record: Dict[str, Any], operation_hash: str, trip_id: str
) -> None:
    if (
        record.get("entityType") != IDEMPOTENCY_ENTITY_TYPE
        or record.get("operationType") != "update_trip"
        or record.get("operationHash") != operation_hash
        or record.get("targetTripId") != trip_id
    ):
        raise base.IdempotencyConflictError(
            "operationId was already used with a different mutation request."
        )


def create_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    base._reject_unexpected(event, CREATE_FIELDS)
    base._require(
        event,
        [
            "userId",
            "requestId",
            "deadlineEpochMs",
            "operationId",
            CONFIRMATION_FIELD,
            "tripName",
            "startDate",
            "endDate",
        ],
    )
    user_id, request_id = base._validate_context(event)
    _confirmation_verified(event)
    operation_id = base._operation_id(event)
    trip_name = base._string(event, "tripName", 200, required=True)
    start_date = base._iso_date(event, "startDate", required=True)
    end_date = base._iso_date(event, "endDate", required=True)
    assert trip_name and start_date and end_date
    if date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise base.ValidationError("endDate must not be earlier than startDate.")

    optional_fields = base._validate_optional_fields(event)
    operation_payload = {
        "tripName": trip_name,
        "startDate": start_date,
        "endDate": end_date,
        **optional_fields,
    }
    operation_hash = base._operation_hash(operation_payload)
    trip_id = base._deterministic_trip_id(user_id, operation_id)
    now = base._utc_now()
    item: Dict[str, Any] = {
        "userId": user_id,
        "tripId": trip_id,
        "tripName": trip_name,
        "startDate": start_date,
        "endDate": end_date,
        "createdAt": now,
        "updatedAt": now,
        "creationOperationId": operation_id,
        "creationOperationHash": operation_hash,
        **optional_fields,
    }

    table = base._get_table()
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(tripId)",
        )
        replayed = False
    except ClientError as exc:
        if (
            exc.response.get("Error", {}).get("Code")
            != "ConditionalCheckFailedException"
        ):
            raise
        existing = table.get_item(
            Key={"userId": user_id, "tripId": trip_id},
            ConsistentRead=True,
        ).get("Item")
        if (
            not isinstance(existing, dict)
            or existing.get("creationOperationId") != operation_id
            or existing.get("creationOperationHash") != operation_hash
        ):
            raise base.IdempotencyConflictError(
                "operationId was already used with a different create request."
            ) from exc
        replayed = True

    base.logger.info(
        json.dumps(
            {
                "event": "trip_created",
                "request_id": request_id,
                "operation_hash": base._safe_hash(operation_id),
                "trip_hash": base._safe_hash(trip_id),
                "replayed": replayed,
            }
        )
    )
    return {
        "created": True,
        "replayed": replayed,
        "tripId": trip_id,
        "message": "Trip creation already completed."
        if replayed
        else "Trip created successfully.",
    }


def update_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    base._reject_unexpected(event, UPDATE_FIELDS)
    base._require(
        event,
        [
            "userId",
            "requestId",
            "deadlineEpochMs",
            "operationId",
            CONFIRMATION_FIELD,
            "tripId",
        ],
    )
    user_id, request_id = base._validate_context(event)
    _confirmation_verified(event)
    operation_id = base._operation_id(event)
    trip_id = base._trip_id(event)

    updates: Dict[str, str] = base._validate_optional_fields(event)
    trip_name = base._string(event, "tripName", 200)
    start_date = base._iso_date(event, "startDate")
    end_date = base._iso_date(event, "endDate")
    if trip_name is not None:
        updates["tripName"] = trip_name
    if start_date is not None:
        updates["startDate"] = start_date
    if end_date is not None:
        updates["endDate"] = end_date
    if not updates:
        raise base.ValidationError("At least one updatable trip field is required.")

    operation_hash = base._operation_hash({"tripId": trip_id, **updates})
    table = base._get_table()
    prior = _read_idempotency(table, user_id, operation_id)
    if prior is not None:
        _validate_idempotency_record(prior, operation_hash, trip_id)
        return {
            "updated": True,
            "replayed": True,
            "tripId": trip_id,
            "message": "Trip update already completed.",
        }

    existing = table.get_item(
        Key={"userId": user_id, "tripId": trip_id},
        ConsistentRead=True,
    ).get("Item")
    if not existing:
        return {
            "updated": False,
            "replayed": False,
            "tripId": trip_id,
            "message": "Trip not found.",
        }

    effective_start = start_date or existing.get("startDate")
    effective_end = end_date or existing.get("endDate")
    if not isinstance(effective_start, str) or not isinstance(effective_end, str):
        raise base.ValidationError("The stored trip dates are incomplete.")
    try:
        if date.fromisoformat(effective_end) < date.fromisoformat(effective_start):
            raise base.ValidationError("endDate must not be earlier than startDate.")
    except ValueError as exc:
        raise base.ValidationError(
            "The effective trip dates must use YYYY-MM-DD format."
        ) from exc

    update_names = {"#updatedAt": "updatedAt"}
    update_values: Dict[str, Any] = {":updatedAt": base._utc_now()}
    update_parts = ["#updatedAt = :updatedAt"]
    for field, value in updates.items():
        name_key, value_key = f"#{field}", f":{field}"
        update_names[name_key] = field
        update_values[value_key] = value
        update_parts.append(f"{name_key} = {value_key}")

    condition_expression = "attribute_exists(userId) AND attribute_exists(tripId)"
    expected_updated_at = existing.get("updatedAt")
    if isinstance(expected_updated_at, str) and expected_updated_at:
        condition_expression += " AND #updatedAt = :expectedUpdatedAt"
        update_values[":expectedUpdatedAt"] = expected_updated_at

    ledger_item = _idempotency_record(
        user_id,
        operation_id,
        operation_hash,
        trip_id,
    )
    transact_items = [
        {
            "Update": {
                "TableName": base.DYNAMODB_TABLE_NAME,
                "Key": _serialize_item({"userId": user_id, "tripId": trip_id}),
                "UpdateExpression": "SET " + ", ".join(update_parts),
                "ExpressionAttributeNames": update_names,
                "ExpressionAttributeValues": _serialize_item(update_values),
                "ConditionExpression": condition_expression,
            }
        },
        {
            "Put": {
                "TableName": base.DYNAMODB_TABLE_NAME,
                "Item": _serialize_item(ledger_item),
                "ConditionExpression": (
                    "attribute_not_exists(userId) AND attribute_not_exists(tripId)"
                ),
            }
        },
    ]

    try:
        table.meta.client.transact_write_items(
            TransactItems=transact_items,
            ClientRequestToken=operation_id,
        )
        replayed = False
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "IdempotentParameterMismatchException":
            raise base.IdempotencyConflictError(
                "operationId was already used with a different mutation request."
            ) from exc
        if error_code != "TransactionCanceledException":
            raise

        current_record = _read_idempotency(table, user_id, operation_id)
        if current_record is not None:
            _validate_idempotency_record(current_record, operation_hash, trip_id)
            replayed = True
        else:
            current_trip = table.get_item(
                Key={"userId": user_id, "tripId": trip_id},
                ConsistentRead=True,
            ).get("Item")
            if not current_trip:
                return {
                    "updated": False,
                    "replayed": False,
                    "tripId": trip_id,
                    "message": "Trip not found.",
                }
            return {
                "updated": False,
                "replayed": False,
                "tripId": trip_id,
                "message": "Trip changed concurrently; retry with fresh data.",
            }

    base.logger.info(
        json.dumps(
            {
                "event": "trip_updated",
                "request_id": request_id,
                "operation_hash": base._safe_hash(operation_id),
                "trip_hash": base._safe_hash(trip_id),
                "replayed": replayed,
            }
        )
    )
    return {
        "updated": True,
        "replayed": replayed,
        "tripId": trip_id,
        "message": "Trip update already completed."
        if replayed
        else "Trip updated successfully.",
    }


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
        "create_trip": create_trip,
        "get_trips": base.get_trips,
        "get_trip": base.get_trip,
        "update_trip": update_trip,
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
        return handler(event)
    except base.IdempotencyConflictError as exc:
        return {"error": "idempotency_conflict", "message": str(exc)}
    except base.ValidationError as exc:
        return {"error": "validation_error", "message": str(exc)}
    except Exception:
        base.logger.exception(
            "trip_tool_error tool=%s request_id=%s",
            tool_name or "unknown",
            request_id,
        )
        raise
