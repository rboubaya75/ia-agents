from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

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
PHASE2_PATH = ROOT / "deploy-agentcore" / "lambda_function_phase2.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load("lambda_function_code", BASE_PATH)
hardened = _load("lambda_function_hardened", HARDENED_PATH)
phase2 = _load("lambda_function_phase2", PHASE2_PATH)

USER_A = "user-a"
USER_B = "user-b"
TRIP_A = "550e8400-e29b-41d4-a716-446655440000"
TRIP_A2 = "550e8400-e29b-41d4-a716-446655440001"
OPERATION_ID = "76e6f404-49de-4dc4-9c60-f2c25a0de91f"
REQUEST_ID = "request-phase2"


def context(tool_name: str):
    return SimpleNamespace(
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": f"trip-target___{tool_name}"}
        )
    )


def read_event(user_id: str = USER_A, **values: object) -> dict:
    return {
        "userId": user_id,
        "requestId": REQUEST_ID,
        "deadlineEpochMs": int(time.time() * 1000) + 30_000,
        **values,
    }


def mutation_event(user_id: str = USER_A, **values: object) -> dict:
    return read_event(
        user_id,
        operationId=OPERATION_ID,
        confirmationVerified=True,
        **values,
    )


def client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class TripToolsPhase2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.table = Mock()
        self.table.meta = SimpleNamespace(client=self.client)
        self.previous_get_table = base._get_table
        base._get_table = Mock(return_value=self.table)

    def tearDown(self) -> None:
        base._get_table = self.previous_get_table

    def test_get_trip_reads_only_authenticated_partition_consistently(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_A,
                "tripId": TRIP_A,
                "tripName": "Setif",
                "creationOperationId": OPERATION_ID,
            }
        }

        response = phase2.lambda_handler(
            read_event(tripId=TRIP_A), context("get_trip")
        )

        self.assertTrue(response["found"])
        self.assertNotIn("userId", response["trip"])
        self.assertNotIn("creationOperationId", response["trip"])
        self.table.get_item.assert_called_once_with(
            Key={"userId": USER_A, "tripId": TRIP_A},
            ConsistentRead=True,
        )

    def test_get_trip_cross_user_and_missing_are_indistinguishable(self) -> None:
        self.table.get_item.return_value = {}

        cross_user = phase2.lambda_handler(
            read_event(USER_B, tripId=TRIP_A), context("get_trip")
        )
        missing = phase2.lambda_handler(
            read_event(USER_B, tripId=TRIP_A2), context("get_trip")
        )

        self.assertEqual(cross_user["found"], False)
        self.assertEqual(missing["found"], False)
        self.assertEqual(cross_user["message"], missing["message"])
        keys = [call.kwargs["Key"] for call in self.table.get_item.call_args_list]
        self.assertEqual(keys[0], {"userId": USER_B, "tripId": TRIP_A})
        self.assertEqual(keys[1], {"userId": USER_B, "tripId": TRIP_A2})
        self.assertNotIn(USER_A, json.dumps(keys))

    def test_pagination_has_no_duplicate_and_consumes_same_actor_cursor(self) -> None:
        self.table.query.side_effect = [
            {
                "Items": [{"userId": USER_A, "tripId": TRIP_A, "tripName": "A"}],
                "LastEvaluatedKey": {"userId": USER_A, "tripId": TRIP_A},
            },
            {
                "Items": [
                    {"userId": USER_A, "tripId": TRIP_A2, "tripName": "A2"}
                ]
            },
        ]

        first = phase2.lambda_handler(read_event(limit=1), context("get_trips"))
        second = phase2.lambda_handler(
            read_event(limit=1, nextToken=first["nextToken"]),
            context("get_trips"),
        )

        ids = [first["trips"][0]["tripId"], second["trips"][0]["tripId"]]
        self.assertEqual(ids, [TRIP_A, TRIP_A2])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            self.table.query.call_args_list[1].kwargs["ExclusiveStartKey"],
            {"userId": USER_A, "tripId": TRIP_A},
        )

    def test_pagination_cursor_from_user_a_is_rejected_for_user_b(self) -> None:
        self.table.query.return_value = {
            "Items": [{"userId": USER_A, "tripId": TRIP_A}],
            "LastEvaluatedKey": {"userId": USER_A, "tripId": TRIP_A},
        }
        first = phase2.lambda_handler(read_event(limit=1), context("get_trips"))
        self.table.query.reset_mock()

        response = phase2.lambda_handler(
            read_event(USER_B, limit=1, nextToken=first["nextToken"]),
            context("get_trips"),
        )

        self.assertEqual(response["error"], "validation_error")
        self.assertIn("authenticated user", response["message"])
        self.table.query.assert_not_called()

    def test_tampered_cursor_actor_binding_is_rejected(self) -> None:
        token = phase2._encode_next_token(
            {"userId": USER_A, "tripId": TRIP_A}, USER_A
        )
        payload = json.loads(
            base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        )
        payload["actorHash"] = "000000000000"
        tampered = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).decode().rstrip("=")

        response = phase2.lambda_handler(
            read_event(nextToken=tampered), context("get_trips")
        )

        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_update_without_confirmation_has_no_dynamodb_effect(self) -> None:
        response = phase2.lambda_handler(
            mutation_event(
                confirmationVerified=False,
                tripId=TRIP_A,
                status="confirmed",
            ),
            context("update_trip"),
        )

        self.assertEqual(response["error"], "validation_error")
        self.table.get_item.assert_not_called()
        self.client.transact_write_items.assert_not_called()

    def test_user_b_cannot_update_user_a_trip(self) -> None:
        self.table.get_item.side_effect = [{}, {}]

        response = phase2.lambda_handler(
            mutation_event(USER_B, tripId=TRIP_A, status="confirmed"),
            context("update_trip"),
        )

        self.assertFalse(response["updated"])
        self.assertEqual(response["message"], "Trip not found.")
        self.assertEqual(
            self.table.get_item.call_args_list[1].kwargs["Key"],
            {"userId": USER_B, "tripId": TRIP_A},
        )
        self.client.transact_write_items.assert_not_called()

    def test_create_replay_emits_redacted_outcome_without_duplicate(self) -> None:
        payload = {
            "tripName": "Setif",
            "startDate": "2026-08-26",
            "endDate": "2026-09-06",
        }
        trip_id = base._deterministic_trip_id(USER_A, OPERATION_ID)
        self.table.put_item.side_effect = client_error(
            "ConditionalCheckFailedException", "PutItem"
        )
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_A,
                "tripId": trip_id,
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": base._operation_hash(payload),
            }
        }
        previous_info = base.logger.info
        base.logger.info = Mock()
        try:
            response = phase2.lambda_handler(
                mutation_event(**payload), context("create_trip")
            )
        finally:
            log_calls = base.logger.info.call_args_list
            base.logger.info = previous_info

        self.assertTrue(response["replayed"])
        self.table.put_item.assert_called_once()
        evidence = "\n".join(str(call.args[0]) for call in log_calls if call.args)
        self.assertIn("trip_mutation_outcome", evidence)
        self.assertIn('"replayed": true', evidence.lower())
        self.assertNotIn(USER_A, evidence)
        self.assertNotIn(OPERATION_ID, evidence)
        self.assertNotIn(trip_id, evidence)

    def test_reused_create_operation_with_different_payload_is_conflict(self) -> None:
        trip_id = base._deterministic_trip_id(USER_A, OPERATION_ID)
        self.table.put_item.side_effect = client_error(
            "ConditionalCheckFailedException", "PutItem"
        )
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_A,
                "tripId": trip_id,
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": "different",
            }
        }

        response = phase2.lambda_handler(
            mutation_event(
                tripName="Setif",
                startDate="2026-08-26",
                endDate="2026-09-06",
            ),
            context("create_trip"),
        )

        self.assertEqual(response["error"], "idempotency_conflict")

    def test_terraform_packages_and_uses_phase2_wrapper(self) -> None:
        root = Path(__file__).resolve().parents[2]
        environment = (
            root / "infra" / "environments" / "test" / "trip_tools.tf"
        ).read_text(encoding="utf-8")
        module = (
            root / "infra" / "modules" / "trip_tools_lambda" / "main.tf"
        ).read_text(encoding="utf-8")
        variables = (
            root / "infra" / "modules" / "trip_tools_lambda" / "variables.tf"
        ).read_text(encoding="utf-8")

        self.assertIn("phase2_source_file", environment)
        self.assertIn('filename = "lambda_function_phase2.py"', module)
        self.assertIn('handler = "lambda_function_phase2.lambda_handler"', module)
        self.assertIn('variable "phase2_source_file"', variables)


if __name__ == "__main__":
    unittest.main()
