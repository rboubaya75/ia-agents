"""Trip tools Lambda for AgentCore Gateway.

This implementation avoids hardcoded table names and avoids logging raw events.
The caller must inject the authenticated userId before invoking the tool.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

DYNAMODB_TABLE_NAME = os.getenv("TRIPS_TABLE_NAME")
dynamodb = boto3.resource("dynamodb")


class ValidationError(ValueError):
    pass


def _response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(body, default=str) if not isinstance(body, str) else body,
    }


def _get_table():
    if not DYNAMODB_TABLE_NAME:
        raise RuntimeError("TRIPS_TABLE_NAME environment variable is required.")
    return dynamodb.Table(DYNAMODB_TABLE_NAME)


def _extract_tool_name(context: Any) -> str:
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    tool_name = custom.get("bedrockAgentCoreToolName", "")
    delimiter = "___"
    if delimiter in tool_name:
        tool_name = tool_name[tool_name.index(delimiter) + len(delimiter):]
    return tool_name


def _require(event: Dict[str, Any], fields: Iterable[str]) -> None:
    missing = [field for field in fields if not event.get(field)]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _require(event, ["userId", "tripName", "startDate", "endDate"])
    table = _get_table()
    trip_id = str(uuid.uuid4())

    item = {
        "userId": event["userId"],
        "tripId": trip_id,
        "tripName": event["tripName"],
        "startDate": event["startDate"],
        "endDate": event["endDate"],
        "createdAt": _utc_now(),
        "updatedAt": _utc_now(),
    }

    for optional_field in ("destination", "description", "status"):
        if optional_field in event and event[optional_field] is not None:
            item[optional_field] = event[optional_field]

    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(tripId)",
    )
    return _response(200, {"message": "Trip created successfully.", "tripId": trip_id})


def get_trips(event: Dict[str, Any]) -> Dict[str, Any]:
    _require(event, ["userId"])
    table = _get_table()
    result = table.query(KeyConditionExpression=Key("userId").eq(event["userId"]))
    return _response(200, result.get("Items", []))


def get_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _require(event, ["userId", "tripId"])
    table = _get_table()
    result = table.get_item(Key={"userId": event["userId"], "tripId": event["tripId"]})
    item = result.get("Item")
    if not item:
        return _response(404, {"message": "Trip not found."})
    return _response(200, item)


def update_trip(event: Dict[str, Any]) -> Dict[str, Any]:
    _require(event, ["userId", "tripId"])
    table = _get_table()

    allowed_fields = ("tripName", "startDate", "endDate", "destination", "description", "status")
    update_names = {"#updatedAt": "updatedAt"}
    update_values = {":updatedAt": _utc_now()}
    update_parts = ["#updatedAt = :updatedAt"]

    for field in allowed_fields:
        if field in event and event[field] is not None:
            name_key = f"#{field}"
            value_key = f":{field}"
            update_names[name_key] = field
            update_values[value_key] = event[field]
            update_parts.append(f"{name_key} = {value_key}")

    if len(update_parts) == 1:
        raise ValidationError("At least one updatable trip field is required.")

    try:
        table.update_item(
            Key={"userId": event["userId"], "tripId": event["tripId"]},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=update_names,
            ExpressionAttributeValues=update_values,
            ConditionExpression="attribute_exists(userId) AND attribute_exists(tripId)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return _response(404, {"message": "Trip not found."})
        raise

    return _response(200, {"message": "Trip updated successfully.", "tripId": event["tripId"]})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    tool_name = _extract_tool_name(context)
    logger.info("trip_tool_invocation tool=%s", tool_name or "unknown")

    try:
        handlers = {
            "create_trip": create_trip,
            "get_trips": get_trips,
            "get_trip": get_trip,
            "update_trip": update_trip,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return _response(400, {"message": "Unsupported operation."})
        return handler(event)
    except ValidationError as exc:
        return _response(400, {"message": str(exc)})
    except Exception:
        logger.exception("trip_tool_error tool=%s", tool_name or "unknown")
        return _response(500, {"message": "Internal tool error."})
