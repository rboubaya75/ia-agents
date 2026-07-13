"""Trip tools Lambda for AgentCore Gateway.

The Runtime injects the authenticated ``userId`` before every trip tool call.
Inputs are validated, DynamoDB access is partition-scoped, list responses are
bounded and paginated, and raw payloads are never logged.
"""
from __future__ import annotations

import base64
import binascii
import json
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
DEFAULT_PAGE_SIZE = int(os.getenv("TRIPS_DEFAULT_PAGE_SIZE", "20"))
MAX_PAGE_SIZE = int(os.getenv("TRIPS_MAX_PAGE_SIZE", "50"))
MAX_NEXT_TOKEN_CHARS = 512
if DEFAULT_PAGE_SIZE < 1 or MAX_PAGE_SIZE < DEFAULT_PAGE_SIZE or MAX_PAGE_SIZE > 100:
    raise RuntimeError("Trip pagination limits are invalid.")

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:@+-]{1,256}$")
TRIP_ID_PATTERN = re.compile(r"^[A-Fa-f0-9-]{36}$")
CREATE_FIELDS = {"userId", "tripName", "startDate", "endDate", "destination", "description", "status"}
UPDATE_FIELDS = {"userId", "tripId", "tripName", "startDate", "endDate", "destination", "description", "status"}
GET_TRIPS_FIELDS = {"userId", "limit", "nextToken"}

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


def _public_trip(item: Dict[str, Any]) -> Dict[str, Any]:
    return _json_safe({key: value for key, value in item.items() if key != "userId"})


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


def _bounded_integer(event: Dict[str, Any], field: str, default: int, maximum: int) -> int:
    value = event.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer.")
    if value < 1 or value > maximum:
        raise ValidationError(f"{field} must be between 1 and {maximum}.")
    return value


def _user_id(event: Dict[str, Any]) -> str:
    value = _string(event, "userId", 256, required=True)
    assert value is not None
    if not USER_ID_PATTERN.fullmatch(value):
        raise ValidationError("userId has an invalid format.")
    return value


def _trip_id_value(value: Any, field: str = "tripId") -> str:
    if not isinstance(value, str) or not TRIP_ID_PATTERN.fullmatch(value):
        raise ValidationError(f"{field} must be a UUID.")
    return value


def _trip_id(event: Dict[str, Any]) -> str:
    value = _string(event, "tripId", 36, required=True)
    assert value is not None
    return _trip_id_value(value)


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


def _encode_next_token(last_key: Dict[str, Any], user_id: str) -> str:
    if last_key.get("userId") != user_id:
        raise RuntimeError("DynamoDB pagination key escaped the authenticated partition.")
    trip_id = _trip_id_value(last_key.get("tripId"), "pagination tripId")
    payload = json.dumps({"v": 1, "tripId": trip_id}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_next_token(token: Any, user_id: str) -> Dict[str, str] | None:
    if token is None:
        return None
    if not isinstance(token, str) or not token or len(token) > MAX_NEXT_TOKEN_CHARS:
        raise ValidationError("nextToken is invalid.")
    try:
        padded = token + "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValidationError("nextToken is invalid.") from exc
    if not isinstance(value, dict) or set(value) != {"v", "tripId"} or value.get("v") != 1:
        raise ValidationError("nextToken is invalid.")
    return {"userId": user_id, "tripId": _trip_id_value(value.get("tripId"), "nextToken tripId")}


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
    _get_table().put_item(Item=item, ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(tripId)")
    return {"created": True, "tripId": trip_id, "message": "Trip created successfully."}


def get_trips(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, GET_TRIPS_FIELDS)
    user_id = _user_id(event)
    limit = _bounded_integer(event, "limit", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
    exclusive_start_key = _decode_next_token(event.get("nextToken"), user_id)
    query: Dict[str, Any] = {
        "KeyConditionExpression": Key("userId").eq(user_id),
        "Limit": limit,
    }
    if exclusive_start_key:
        query["ExclusiveStartKey"] = exclusive_start_key
    result = _get_table().query(**query)
    trips = [_public_trip(item) for item in result.get("Items", [])]
    response: Dict[str, Any] = {"trips": trips, "count": len(trips)}
    last_key = result.get("LastEvaluatedKey")
    if isinstance(last_key, dict) and last_key:
        response["nextToken"] = _encode_next_token(last_key, user_id)
    return response


def get_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, {"userId", "tripId"})
    user_id = _user_id(event)
    trip_id = _trip_id(event)
    item = _get_table().get_item(Key={"userId": user_id, "tripId": trip_id}).get("Item")
    if not item:
        return {"found": False, "tripId": trip_id, "message": "Trip not found."}
    return {"found": True, "trip": _public_trip(item)}


def update_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _reject_unexpected(event, UPDATE_FIELDS)
    user_id = _user_id(event)
    trip_id = _trip_id(event)
    table = _get_table()
    existing = table.get_item(Key={"userId": user_id, "tripId": trip_id}).get("Item")
    if not existing:
        return {"updated": False, "tripId": trip_id, "message": "Trip not found."}
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
    if not updates:
        raise ValidationError("At least one updatable trip field is required.")
    effective_start = start_date or existing.get("startDate")
    effective_end = end_date or existing.get("endDate")
    if not isinstance(effective_start, str) or not isinstance(effective_end, str):
        raise ValidationError("The stored trip dates are incomplete.")
    try:
        if date.fromisoformat(effective_end) < date.fromisoformat(effective_start):
            raise ValidationError("endDate must not be earlier than startDate.")
    except ValueError as exc:
        raise ValidationError("The effective trip dates must use YYYY-MM-DD format.") from exc

    update_names = {"#updatedAt": "updatedAt"}
    update_values: Dict[str, Any] = {":updatedAt": _utc_now()}
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
    try:
        table.update_item(
            Key={"userId": user_id, "tripId": trip_id},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=update_names,
            ExpressionAttributeValues=update_values,
            ConditionExpression=condition_expression,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return {"updated": False, "tripId": trip_id, "message": "Trip changed concurrently; retry with fresh data."}
        raise
    return {"updated": True, "tripId": trip_id, "message": "Trip updated successfully."}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    tool_name = _extract_tool_name(context)
    logger.info("trip_tool_invocation tool=%s", tool_name or "unknown")
    handlers = {"create_trip": create_trip, "get_trips": get_trips, "get_trip": get_trip, "update_trip": update_trip}
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
