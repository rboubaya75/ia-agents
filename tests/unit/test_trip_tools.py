from __future__ import annotations

import importlib.util
import os
from decimal import Decimal
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from botocore.exceptions import ClientError

os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "eu-west-3",
        "AWS_EC2_METADATA_DISABLED": "true",
        "TRIPS_TABLE_NAME": "test-trips",
        "TRIPS_DEFAULT_PAGE_SIZE": "20",
        "TRIPS_MAX_PAGE_SIZE": "50",
        "TRIPS_MIN_DEADLINE_REMAINING_MS": "100",
    }
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "deploy-agentcore" / "lambda_function_code.py"
)
SPEC = importlib.util.spec_from_file_location("trip_tools_lambda", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load trip tools module from {MODULE_PATH}")
trip_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trip_tools)

USER_ID = "user-123"
TRIP_ID = "550e8400-e29b-41d4-a716-446655440000"
NEXT_TRIP_ID = "550e8400-e29b-41d4-a716-446655440001"
OPERATION_ID = "76e6f404-49de-4dc4-9c60-f2c25a0de91f"
OTHER_OPERATION_ID = "7928aa02-5382-4d7b-83fb-9e084c8ba06f"
REQUEST_ID = "request-1"


def context(tool_name: str):
    return SimpleNamespace(
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": f"trip-target___{tool_name}"}
        )
    )


def tool_event(**values: object) -> dict:
    return {
        "userId": USER_ID,
        "requestId": REQUEST_ID,
        "deadlineEpochMs": int(time.time() * 1000) + 30_000,
        **values,
    }


def conditional_error(operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "conditional",
            }
        },
        operation,
    )


class TripToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = Mock()
        self.previous_get_table = trip_tools._get_table
        trip_tools._get_table = Mock(return_value=self.table)

    def tearDown(self) -> None:
        trip_tools._get_table = self.previous_get_table

    def test_create_trip_uses_deterministic_idempotency_key(self) -> None:
        event = tool_event(
            operationId=OPERATION_ID,
            tripName="Tokyo",
            startDate="2026-09-01",
            endDate="2026-09-10",
            destination="Tokyo",
        )
        response = trip_tools.lambda_handler(event, context("create_trip"))

        self.assertTrue(response["created"])
        self.assertFalse(response["replayed"])
        expected_trip_id = trip_tools._deterministic_trip_id(USER_ID, OPERATION_ID)
        self.assertEqual(response["tripId"], expected_trip_id)
        item = self.table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["userId"], USER_ID)
        self.assertEqual(item["creationOperationId"], OPERATION_ID)
        self.assertIn("creationOperationHash", item)

    def test_create_trip_replay_returns_original_trip_without_duplicate(self) -> None:
        operation_payload = {
            "tripName": "Tokyo",
            "startDate": "2026-09-01",
            "endDate": "2026-09-10",
            "destination": "Tokyo",
        }
        trip_id = trip_tools._deterministic_trip_id(USER_ID, OPERATION_ID)
        self.table.put_item.side_effect = conditional_error("PutItem")
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": trip_id,
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": trip_tools._operation_hash(operation_payload),
            }
        }

        response = trip_tools.lambda_handler(
            tool_event(operationId=OPERATION_ID, **operation_payload),
            context("create_trip"),
        )

        self.assertTrue(response["created"])
        self.assertTrue(response["replayed"])
        self.assertEqual(response["tripId"], trip_id)

    def test_create_trip_rejects_reused_operation_with_different_payload(self) -> None:
        trip_id = trip_tools._deterministic_trip_id(USER_ID, OPERATION_ID)
        self.table.put_item.side_effect = conditional_error("PutItem")
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": trip_id,
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": "different",
            }
        }

        response = trip_tools.lambda_handler(
            tool_event(
                operationId=OPERATION_ID,
                tripName="Tokyo",
                startDate="2026-09-01",
                endDate="2026-09-10",
            ),
            context("create_trip"),
        )

        self.assertEqual(response["error"], "idempotency_conflict")

    def test_rejects_end_date_before_start_date(self) -> None:
        response = trip_tools.lambda_handler(
            tool_event(
                operationId=OPERATION_ID,
                tripName="Invalid",
                startDate="2026-09-10",
                endDate="2026-09-01",
            ),
            context("create_trip"),
        )
        self.assertEqual(response["error"], "validation_error")
        self.table.put_item.assert_not_called()

    def test_rejects_expired_deadline_before_dynamodb(self) -> None:
        event = tool_event()
        event["deadlineEpochMs"] = int(time.time() * 1000) - 1
        response = trip_tools.lambda_handler(event, context("get_trips"))
        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_rejects_unexpected_identity_field(self) -> None:
        response = trip_tools.lambda_handler(
            tool_event(actorId="attacker"), context("get_trips")
        )
        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_get_trip_uses_partition_and_redacts_internal_metadata(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": TRIP_ID,
                "tripName": "Tokyo",
                "budget": Decimal("100.50"),
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": "hash",
            }
        }
        response = trip_tools.lambda_handler(
            tool_event(tripId=TRIP_ID), context("get_trip")
        )
        self.assertTrue(response["found"])
        self.assertEqual(response["trip"]["budget"], 100.5)
        self.assertNotIn("userId", response["trip"])
        self.assertNotIn("creationOperationId", response["trip"])
        self.table.get_item.assert_called_once_with(
            Key={"userId": USER_ID, "tripId": TRIP_ID}
        )

    def test_get_trips_uses_default_bounded_page_and_redacts_identity(self) -> None:
        self.table.query.return_value = {
            "Items": [
                {
                    "userId": USER_ID,
                    "tripId": TRIP_ID,
                    "tripName": "Tokyo",
                    "lastOperationId": OPERATION_ID,
                }
            ]
        }
        response = trip_tools.lambda_handler(tool_event(), context("get_trips"))
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["trips"][0]["tripId"], TRIP_ID)
        self.assertNotIn("userId", response["trips"][0])
        self.assertNotIn("lastOperationId", response["trips"][0])
        self.assertEqual(self.table.query.call_args.kwargs["Limit"], 20)

    def test_get_trips_returns_and_consumes_opaque_next_token(self) -> None:
        self.table.query.side_effect = [
            {
                "Items": [{"userId": USER_ID, "tripId": TRIP_ID, "tripName": "Tokyo"}],
                "LastEvaluatedKey": {"userId": USER_ID, "tripId": TRIP_ID},
            },
            {
                "Items": [
                    {"userId": USER_ID, "tripId": NEXT_TRIP_ID, "tripName": "Kyoto"}
                ]
            },
        ]
        first = trip_tools.lambda_handler(tool_event(limit=1), context("get_trips"))
        self.assertIn("nextToken", first)
        second = trip_tools.lambda_handler(
            tool_event(limit=1, nextToken=first["nextToken"]), context("get_trips")
        )
        self.assertEqual(second["trips"][0]["tripId"], NEXT_TRIP_ID)
        self.assertEqual(
            self.table.query.call_args.kwargs["ExclusiveStartKey"],
            {"userId": USER_ID, "tripId": TRIP_ID},
        )

    def test_get_trips_rejects_invalid_limit(self) -> None:
        for value in (0, 51, True, "10"):
            with self.subTest(value=value):
                response = trip_tools.lambda_handler(
                    tool_event(limit=value), context("get_trips")
                )
                self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_update_trip_requires_an_update(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": TRIP_ID,
                "startDate": "2026-09-01",
                "endDate": "2026-09-10",
                "updatedAt": "2026-07-13T10:00:00+00:00",
            }
        }
        response = trip_tools.lambda_handler(
            tool_event(operationId=OPERATION_ID, tripId=TRIP_ID),
            context("update_trip"),
        )
        self.assertEqual(response["error"], "validation_error")
        self.table.update_item.assert_not_called()

    def test_partial_date_update_cannot_invert_existing_range(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": TRIP_ID,
                "startDate": "2026-09-01",
                "endDate": "2026-09-10",
                "updatedAt": "2026-07-13T10:00:00+00:00",
            }
        }
        response = trip_tools.lambda_handler(
            tool_event(
                operationId=OPERATION_ID,
                tripId=TRIP_ID,
                startDate="2026-09-20",
            ),
            context("update_trip"),
        )
        self.assertEqual(response["error"], "validation_error")
        self.table.update_item.assert_not_called()

    def test_update_replay_is_returned_without_second_write(self) -> None:
        operation_hash = trip_tools._operation_hash(
            {"tripId": TRIP_ID, "status": "confirmed"}
        )
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": TRIP_ID,
                "startDate": "2026-09-01",
                "endDate": "2026-09-10",
                "updatedAt": "2026-07-13T10:00:00+00:00",
                "lastOperationId": OPERATION_ID,
                "lastOperationHash": operation_hash,
            }
        }
        response = trip_tools.lambda_handler(
            tool_event(
                operationId=OPERATION_ID,
                tripId=TRIP_ID,
                status="confirmed",
            ),
            context("update_trip"),
        )
        self.assertTrue(response["updated"])
        self.assertTrue(response["replayed"])
        self.table.update_item.assert_not_called()

    def test_update_uses_optimistic_concurrency_and_idempotency_metadata(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": TRIP_ID,
                "startDate": "2026-09-01",
                "endDate": "2026-09-10",
                "updatedAt": "2026-07-13T10:00:00+00:00",
            }
        }
        response = trip_tools.lambda_handler(
            tool_event(
                operationId=OPERATION_ID,
                tripId=TRIP_ID,
                status="confirmed",
            ),
            context("update_trip"),
        )
        self.assertTrue(response["updated"])
        self.assertFalse(response["replayed"])
        call = self.table.update_item.call_args.kwargs
        self.assertIn("#updatedAt = :expectedUpdatedAt", call["ConditionExpression"])
        self.assertEqual(call["ExpressionAttributeValues"][":lastOperationId"], OPERATION_ID)
        self.assertIn(":lastOperationHash", call["ExpressionAttributeValues"])

    def test_update_conditional_failure_detects_completed_replay(self) -> None:
        operation_hash = trip_tools._operation_hash(
            {"tripId": TRIP_ID, "status": "confirmed"}
        )
        self.table.get_item.side_effect = [
            {
                "Item": {
                    "userId": USER_ID,
                    "tripId": TRIP_ID,
                    "startDate": "2026-09-01",
                    "endDate": "2026-09-10",
                    "updatedAt": "2026-07-13T10:00:00+00:00",
                }
            },
            {
                "Item": {
                    "userId": USER_ID,
                    "tripId": TRIP_ID,
                    "lastOperationId": OPERATION_ID,
                    "lastOperationHash": operation_hash,
                }
            },
        ]
        self.table.update_item.side_effect = conditional_error("UpdateItem")

        response = trip_tools.lambda_handler(
            tool_event(
                operationId=OPERATION_ID,
                tripId=TRIP_ID,
                status="confirmed",
            ),
            context("update_trip"),
        )

        self.assertTrue(response["updated"])
        self.assertTrue(response["replayed"])

    def test_unsupported_tool_is_rejected(self) -> None:
        response = trip_tools.lambda_handler(tool_event(), context("delete_all_trips"))
        self.assertEqual(response["error"], "unsupported_operation")

    def test_terraform_contract_exposes_server_context_and_pagination(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = (root / "infra" / "environments" / "test" / "trip_tools.tf").read_text(
            encoding="utf-8"
        )
        module = (
            root / "infra" / "modules" / "trip_tools_lambda" / "main.tf"
        ).read_text(encoding="utf-8")
        for name in ("operationId", "requestId", "deadlineEpochMs", "limit", "nextToken"):
            self.assertIn(f'name        = "{name}"', schema)
        self.assertIn("timeout                        = 5", module)


if __name__ == "__main__":
    unittest.main()
