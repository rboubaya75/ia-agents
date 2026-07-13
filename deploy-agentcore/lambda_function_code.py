"""Trip tools Lambda for AgentCore Gateway.

The Runtime injects the authenticated ``userId`` before every trip tool call.
The function validates all inputs, never logs raw payloads, scopes every
DynamoDB operation to the authenticated partition key, and returns the native
object format expected by AgentCore Gateway Lambda targets.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

DYNAMODB_TABLE_NAME = os.getenv("TRIPS_TABLE_NAME")
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:@+-]{1,256}$")
TRIP_ID_PATTERN = re.compile(r"^[A-Fa-f0-9-]{36}$")
CREATE_FIELDS = {"userId", "tripName", "startDate", "endDate", "destination", "description", "status"}
UPDATE_FIELDS = {"userId", "tripId", "tripName", "startDate", "endDate", "destination", "description", "status"}

dynamodb = boto3.resource("dynamodb")


class ValidationError(ValueError):
    pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _get_table():
    if not DYNAMODB_TABLE_NAME:
        raise RuntimeError("TRIPS_TABLE_NAME environment variable is required.")
    return dynamodb.Table(DYNAMODB_TABLE_NAME)


def _extract_tool_name(context: Any) -> str:
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    extended_name = custom.get("bedrockAgentCoreToolName", "")
    delimiter = "___"
    return extended_name.split(delimiter, 1)[1] if delimiter in extended_name else extended_name


def _require(event: Dict[str, Any], fields: Iterable[str]) -> None:
    missing = [field for field in fields if event.get(field) in (None, "")]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def _reject_unexpected(event: Dict[str, Any], allowed: set[str]) -> None:
    unexpected = sorted(set(event).difference(allowed))
    if unexpected:
        raise ValidationError("Unsupported field(s): " + ", ".join(unexpected))


def _string(event: Dict[str, Any], field: str, max_length: int, *, required: bool = False) -> str | None:
    value = event.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError(f"{field} must be {max_length} characters or fewer.")
    return value


def _user_id(event: Dict[str, Any]) -> str:
    value = _string(event, "userId", 256, required=True)
    assert value is not None
    if not USER_ID_PATTERN.fullmatch(value):
        raise ValidationError("userId has an invalid format.")
    return value


def _trip_id(event: Dict[str, Any]) -> str:
    value = _string(event, "tripId", 36, required=True)
    assert value is not None
    if not TRIP_ID_PATTERN.fullmatch(value):
        raise ValidationError("tripId must be a UUID.")
    return value


def _iso_date(event: Dict[str, Any], field: str, *, required: bool = False) -> str | None:
    value = _string(event, field, 10, required=required)
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise ValidationError(f"{field} must use YYYY-MM-DD format.")
    return value


def _validate_optional_fields(event: Dict[str, Any]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for field, limit in {"destination": 200, "description": 2000, "status": 50}.items():
        value = _string(event, field, limit)
        if value is not None:
            values[field] = value
    return values


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, CREATE_FIELDS)
    _require(event, ["userId", "tripName", "startDate", "endDate"])

    user_id = _user_id(event)
    trip_name = _string(event, "tripName", 200, required=True)
    start_date = _iso_date(event, "startDate", required=True)
    end_date = _iso_date(event, "endDate", required=True)
    assert trip_name and start_date and end_date
    if date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise ValidationError("endDate must not be earlier than startDate.")

    trip_id = str(uuid.uuid4())
    now = _utc_now()
    item: Dict[str, Any] = {
        "userId": user_id,
        "tripId": trip_id,
        "tripName": trip_name,
        "startDate": start_date,
        "endDate": end_date,
        "createdAt": now,
        "updatedAt": now,
        **_validate_optional_fields(event),
    }

    _get_table().put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(tripId)",
    )
    return {"created": True, "tripId": trip_id, "message": "Trip created successfully."}


def get_trips(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, {"userId"})
    user_id = _user_id(event)
    result = _get_table().query(KeyConditionExpression=Key("userId").eq(user_id))
    return {"trips": _json_safe(result.get("Items", []))}


def get_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, {"userId", "tripId"})
    user_id = _user_id(event)
    trip_id = _trip_id(event)
    result = _get_table().get_item(Key={"userId": user_id, "tripId": trip_id})
    item = result.get("Item")
    if not item:
        return {"found": False, "tripId": trip_id, "message": "Trip not found."}
    return {"found": True, "trip": _json_safe(item)}


def update_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, UPDATE_FIELDS)
    user_id = _user_id(event)
    trip_id = _trip_id(event)

    updates: Dict[str, str] = _validate_optional_fields(event)
    trip_name = _string(event, "tripName", 200)
    start_date = _iso_date(event, "startDate")
    end_date = _iso_date(event, "endDate")
    if trip_name is not None:
        updates["tripName"] = trip_name
    if start_date is not None:
        updates["startDate"] = start_date
    if end_date is not None:
        updates["endDate"] = end_date
    if start_date and end_date and date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise ValidationError("endDate must not be earlier than startDate.")
    if not updates:
        raise ValidationError("At least one updatable trip field is required.")

    update_names = {"#updatedAt": "updatedAt"}
    update_values: Dict[str, Any] = {":updatedAt": _utc_now()}
    update_parts = ["#updatedAt = :updatedAt"]
    for field, value in updates.items():
        name_key = f"#{field}"
        value_key = f":{field}"
        update_names[name_key] = field
        update_values[value_key] = value
        update_parts.append(f"{name_key} = {value_key}")

    try:
        _get_table().update_item(
            Key={"userId": user_id, "tripId": trip_id},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=update_names,
            ExpressionAttributeValues=update_values,
            ConditionExpression="attribute_exists(userId) AND attribute_exists(tripId)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return {"updated": False, "tripId": trip_id, "message": "Trip not found."}
        raise

    return {"updated": True, "tripId": trip_id, "message": "Trip updated successfully."}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    tool_name = _extract_tool_name(context)
    logger.info("trip_tool_invocation tool=%s", tool_name or "unknown")

    handlers = {
        "create_trip": create_trip,
        "get_trips": get_trips,
        "get_trip": get_trip,
        "update_trip": update_trip,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return {"error": "unsupported_operation", "message": "Unsupported operation."}
    if not isinstance(event, dict):
        return {"error": "validation_error", "message": "Tool input must be a JSON object."}

    try:
        return handler(event)
    except ValidationError as exc:
        return {"error": "validation_error", "message": str(exc)}
    except Exception:
        logger.exception("trip_tool_error tool=%s", tool_name or "unknown")
        raise
