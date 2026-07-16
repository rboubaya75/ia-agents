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


def load(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = load("lambda_function_code", "deploy-agentcore/lambda_function_code.py")
load("lambda_function_hardened", "deploy-agentcore/lambda_function_hardened.py")
phase2 = load("lambda_function_phase2", "deploy-agentcore/lambda_function_phase2.py")

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


def event(user_id: str = USER_A, **values: object) -> dict:
    payload = {
        "userId": user_id,
        "requestId": REQUEST_ID,
        "deadlineEpochMs": int(time.time() * 1000) + 30_000,
    }
    payload.update(values)
    return payload


def mutation_event(user_id: str = USER_A, **values: object) -> dict:
    payload = event(
        user_id,
        operationId=OPERATION_ID,
        confirmationVerified=True,
    )
    payload.update(values)
    return payload


def conditional_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "conflict"}},
        "PutItem",
    )


class TripToolsPhase2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.table = Mock()
        self.table.meta = SimpleNamespace(client=self.client)
        self.previous_get_table = base._get_table
        base._get_table = Mock(return_value=self.table)

    def tearDown(self) -> None:
        base._get_table = self.previous_get_table

    def test_get_trip_is_partition_scoped_consistent_and_redacted(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_A,
                "tripId": TRIP_A,
                "tripName": "Setif",
                "creationOperationId": OPERATION_ID,
            }
        }
        response = phase2.lambda_handler(event(tripId=TRIP_A), context("get_trip"))
        self.assertTrue(response["found"])
        self.assertNotIn("userId", response["trip"])
        self.assertNotIn("creationOperationId", response["trip"])
        self.table.get_item.assert_called_once_with(
            Key={"userId": USER_A, "tripId": TRIP_A}, ConsistentRead=True
        )

    def test_cross_user_and_missing_trip_are_indistinguishable(self) -> None:
        self.table.get_item.return_value = {}
        cross_user = phase2.lambda_handler(
            event(USER_B, tripId=TRIP_A), context("get_trip")
        )
        missing = phase2.lambda_handler(
            event(USER_B, tripId=TRIP_A2), context("get_trip")
        )
        self.assertEqual(cross_user["message"], missing["message"])
        keys = [call.kwargs["Key"] for call in self.table.get_item.call_args_list]
        self.assertEqual(keys[0]["userId"], USER_B)
        self.assertEqual(keys[1]["userId"], USER_B)

    def test_same_actor_pagination_has_no_duplicate(self) -> None:
        self.table.query.side_effect = [
            {
                "Items": [{"userId": USER_A, "tripId": TRIP_A}],
                "LastEvaluatedKey": {"userId": USER_A, "tripId": TRIP_A},
            },
            {"Items": [{"userId": USER_A, "tripId": TRIP_A2}]},
        ]
        first = phase2.lambda_handler(event(limit=1), context("get_trips"))
        second = phase2.lambda_handler(
            event(limit=1, nextToken=first["nextToken"]), context("get_trips")
        )
        ids = [first["trips"][0]["tripId"], second["trips"][0]["tripId"]]
        self.assertEqual(ids, [TRIP_A, TRIP_A2])
        self.assertEqual(len(ids), len(set(ids)))

    def test_cursor_from_user_a_is_rejected_for_user_b(self) -> None:
        token = phase2._encode_next_token(
            {"userId": USER_A, "tripId": TRIP_A}, USER_A
        )
        response = phase2.lambda_handler(
            event(USER_B, nextToken=token), context("get_trips")
        )
        self.assertEqual(response["error"], "validation_error")
        self.assertIn("authenticated user", response["message"])
        self.table.query.assert_not_called()

    def test_tampered_cursor_is_rejected(self) -> None:
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
            event(nextToken=tampered), context("get_trips")
        )
        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_update_without_confirmation_has_no_side_effect(self) -> None:
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
        self.assertEqual(
            self.table.get_item.call_args_list[1].kwargs["Key"],
            {"userId": USER_B, "tripId": TRIP_A},
        )
        self.client.transact_write_items.assert_not_called()

    def test_create_replay_has_one_write_attempt_and_redacted_outcome(self) -> None:
        trip_payload = {
            "tripName": "Setif",
            "startDate": "2026-08-26",
            "endDate": "2026-09-06",
        }
        trip_id = base._deterministic_trip_id(USER_A, OPERATION_ID)
        self.table.put_item.side_effect = conditional_error()
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_A,
                "tripId": trip_id,
                "creationOperationId": OPERATION_ID,
                "creationOperationHash": base._operation_hash(trip_payload),
            }
        }
        original_info = base.logger.info
        base.logger.info = Mock()
        try:
            response = phase2.lambda_handler(
                mutation_event(**trip_payload), context("create_trip")
            )
            logs = "\n".join(
                str(call.args[0]) for call in base.logger.info.call_args_list if call.args
            )
        finally:
            base.logger.info = original_info
        self.assertTrue(response["replayed"])
        self.table.put_item.assert_called_once()
        self.assertIn("trip_mutation_outcome", logs)
        self.assertNotIn(USER_A, logs)
        self.assertNotIn(OPERATION_ID, logs)
        self.assertNotIn(trip_id, logs)

    def test_terraform_uses_phase2_wrapper(self) -> None:
        environment = (ROOT / "infra/environments/test/trip_tools.tf").read_text()
        module = (ROOT / "infra/modules/trip_tools_lambda/main.tf").read_text()
        variables = (ROOT / "infra/modules/trip_tools_lambda/variables.tf").read_text()
        self.assertIn("phase2_source_file", environment)
        self.assertIn('filename = "lambda_function_phase2.py"', module)
        self.assertIn(
            'handler                        = "lambda_function_phase2.lambda_handler"',
            module,
        )
        self.assertIn('variable "phase2_source_file"', variables)


if __name__ == "__main__":
    unittest.main()
