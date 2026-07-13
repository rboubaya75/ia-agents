from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "AWS_DEFAULT_REGION": "eu-west-3",
        "AWS_EC2_METADATA_DISABLED": "true",
        "TRIPS_TABLE_NAME": "test-trips",
        "TRIPS_DEFAULT_PAGE_SIZE": "20",
        "TRIPS_MAX_PAGE_SIZE": "50",
        "TRIPS_MIN_DEADLINE_REMAINING_MS": "100",
        "IDEMPOTENCY_TTL_SECONDS": "604800",
    }
)

ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "deploy-agentcore" / "lambda_function_code.py"
HARDENED_PATH = ROOT / "deploy-agentcore" / "lambda_function_hardened.py"

base_spec = importlib.util.spec_from_file_location("lambda_function_code", BASE_PATH)
if base_spec is None or base_spec.loader is None:
    raise RuntimeError(f"Unable to load trip tools base module from {BASE_PATH}")
base = importlib.util.module_from_spec(base_spec)
sys.modules["lambda_function_code"] = base
base_spec.loader.exec_module(base)

hardened_spec = importlib.util.spec_from_file_location(
    "lambda_function_hardened", HARDENED_PATH
)
if hardened_spec is None or hardened_spec.loader is None:
    raise RuntimeError(
        f"Unable to load hardened trip tools module from {HARDENED_PATH}"
    )
hardened = importlib.util.module_from_spec(hardened_spec)
hardened_spec.loader.exec_module(hardened)

USER_ID = "user-123"
TRIP_ID = "550e8400-e29b-41d4-a716-446655440000"
OPERATION_ID = "76e6f404-49de-4dc4-9c60-f2c25a0de91f"
REQUEST_ID = "request-1"
_deserializer = TypeDeserializer()


def context(tool_name: str):
    return SimpleNamespace(
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": f"trip-target___{tool_name}"}
        )
    )


def event(**values: object) -> dict:
    return {
        "userId": USER_ID,
        "requestId": REQUEST_ID,
        "deadlineEpochMs": int(time.time() * 1000) + 30_000,
        "operationId": OPERATION_ID,
        "confirmationVerified": True,
        **values,
    }


def client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def deserialize_item(item: dict) -> dict:
    return {key: _deserializer.deserialize(value) for key, value in item.items()}


class HardenedTripToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.table = Mock()
        self.table.meta = SimpleNamespace(client=self.client)
        self.previous_get_table = base._get_table
        base._get_table = Mock(return_value=self.table)

    def tearDown(self) -> None:
        base._get_table = self.previous_get_table

    def test_create_requires_server_verified_confirmation(self) -> None:
        response = hardened.lambda_handler(
            event(
                confirmationVerified=False,
                tripName="Tokyo",
                startDate="2026-09-01",
                endDate="2026-09-10",
            ),
            context("create_trip"),
        )
        self.assertEqual(response["error"], "validation_error")
        self.assertIn("confirmation", response["message"].lower())
        self.table.put_item.assert_not_called()

    def test_create_replay_uses_consistent_read(self) -> None:
        payload = {
            "tripName": "Tokyo",
            "startDate": "2026-09-01",
            "endDate": "2026-09-10",
        }
        trip_id = base._deterministic_trip_id(USER_ID, OPERATION_ID)
        self.table.put_item.side_effect = client_error(
            "ConditionalCheckFailedException", "PutItem"
        )
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": trip_id,
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": base._operation_hash(payload),
            }
        }

        response = hardened.lambda_handler(event(**payload), context("create_trip"))

        self.assertTrue(response["replayed"])
        self.table.get_item.assert_called_once_with(
            Key={"userId": USER_ID, "tripId": trip_id},
            ConsistentRead=True,
        )

    def test_update_is_atomic_with_durable_ttl_ledger(self) -> None:
        self.table.get_item.side_effect = [
            {},
            {
                "Item": {
                    "userId": USER_ID,
                    "tripId": TRIP_ID,
                    "startDate": "2026-09-01",
                    "endDate": "2026-09-10",
                    "updatedAt": "2026-07-13T10:00:00+00:00",
                }
            },
        ]

        response = hardened.lambda_handler(
            event(tripId=TRIP_ID, status="confirmed"),
            context("update_trip"),
        )

        self.assertTrue(response["updated"])
        call = self.client.transact_write_items.call_args.kwargs
        self.assertEqual(call["ClientRequestToken"], OPERATION_ID)
        self.assertEqual(len(call["TransactItems"]), 2)
        ledger = deserialize_item(call["TransactItems"][1]["Put"]["Item"])
        self.assertEqual(ledger["entityType"], "IDEMPOTENCY")
        self.assertEqual(ledger["targetTripId"], TRIP_ID)
        self.assertGreater(ledger["expiresAt"], int(time.time()))

    def test_late_replay_is_resolved_from_ledger(self) -> None:
        operation_hash = base._operation_hash(
            {"tripId": TRIP_ID, "status": "confirmed"}
        )
        self.table.get_item.return_value = {
            "Item": {
                **hardened._idempotency_key(USER_ID, OPERATION_ID),
                "entityType": "IDEMPOTENCY",
                "operationType": "update_trip",
                "operationHash": operation_hash,
                "targetTripId": TRIP_ID,
            }
        }

        response = hardened.lambda_handler(
            event(tripId=TRIP_ID, status="confirmed"),
            context("update_trip"),
        )

        self.assertTrue(response["replayed"])
        self.client.transact_write_items.assert_not_called()
        self.table.get_item.assert_called_once_with(
            Key=hardened._idempotency_key(USER_ID, OPERATION_ID),
            ConsistentRead=True,
        )

    def test_transaction_cancellation_reads_ledger_consistently(self) -> None:
        operation_hash = base._operation_hash(
            {"tripId": TRIP_ID, "status": "confirmed"}
        )
        self.table.get_item.side_effect = [
            {},
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
                    **hardened._idempotency_key(USER_ID, OPERATION_ID),
                    "entityType": "IDEMPOTENCY",
                    "operationType": "update_trip",
                    "operationHash": operation_hash,
                    "targetTripId": TRIP_ID,
                }
            },
        ]
        self.client.transact_write_items.side_effect = client_error(
            "TransactionCanceledException", "TransactWriteItems"
        )

        response = hardened.lambda_handler(
            event(tripId=TRIP_ID, status="confirmed"),
            context("update_trip"),
        )

        self.assertTrue(response["replayed"])
        self.assertTrue(self.table.get_item.call_args_list[2].kwargs["ConsistentRead"])

    def test_read_tools_still_delegate_to_stable_base(self) -> None:
        self.table.query.return_value = {"Items": []}
        read_event = {
            "userId": USER_ID,
            "requestId": REQUEST_ID,
            "deadlineEpochMs": int(time.time() * 1000) + 30_000,
        }
        response = hardened.lambda_handler(read_event, context("get_trips"))
        self.assertEqual(response, {"trips": [], "count": 0})


if __name__ == "__main__":
    unittest.main()
