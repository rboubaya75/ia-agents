from __future__ import annotations

import importlib.util
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "eu-west-3",
        "AWS_EC2_METADATA_DISABLED": "true",
        "TRIPS_TABLE_NAME": "test-trips",
    }
)

MODULE_PATH = Path(__file__).resolve().parents[2] / "deploy-agentcore" / "lambda_function_code.py"
SPEC = importlib.util.spec_from_file_location("trip_tools_lambda", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load trip tools module from {MODULE_PATH}")

trip_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trip_tools)

USER_ID = "user-123"
TRIP_ID = "550e8400-e29b-41d4-a716-446655440000"


def context(tool_name: str):
    return SimpleNamespace(
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": f"trip-target___{tool_name}"}
        )
    )


class TripToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = Mock()
        self.previous_get_table = trip_tools._get_table
        trip_tools._get_table = Mock(return_value=self.table)

    def tearDown(self) -> None:
        trip_tools._get_table = self.previous_get_table

    def test_create_trip_returns_native_gateway_object(self) -> None:
        response = trip_tools.lambda_handler(
            {
                "userId": USER_ID,
                "tripName": "Tokyo",
                "startDate": "2026-09-01",
                "endDate": "2026-09-10",
                "destination": "Tokyo",
            },
            context("create_trip"),
        )

        self.assertTrue(response["created"])
        self.assertIn("tripId", response)
        self.assertNotIn("statusCode", response)
        item = self.table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["userId"], USER_ID)
        self.assertEqual(item["tripName"], "Tokyo")

    def test_rejects_end_date_before_start_date(self) -> None:
        response = trip_tools.lambda_handler(
            {
                "userId": USER_ID,
                "tripName": "Invalid",
                "startDate": "2026-09-10",
                "endDate": "2026-09-01",
            },
            context("create_trip"),
        )

        self.assertEqual(response["error"], "validation_error")
        self.table.put_item.assert_not_called()

    def test_rejects_unexpected_identity_field(self) -> None:
        response = trip_tools.lambda_handler(
            {"userId": USER_ID, "actorId": "attacker"},
            context("get_trips"),
        )

        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_get_trip_uses_user_partition_and_returns_native_object(self) -> None:
        self.table.get_item.return_value = {
            "Item": {
                "userId": USER_ID,
                "tripId": TRIP_ID,
                "tripName": "Tokyo",
                "budget": Decimal("100.50"),
            }
        }

        response = trip_tools.lambda_handler(
            {"userId": USER_ID, "tripId": TRIP_ID},
            context("get_trip"),
        )

        self.assertTrue(response["found"])
        self.assertEqual(response["trip"]["budget"], 100.5)
        self.assertNotIn("statusCode", response)
        self.table.get_item.assert_called_once_with(
            Key={"userId": USER_ID, "tripId": TRIP_ID}
        )

    def test_update_trip_requires_an_update(self) -> None:
        response = trip_tools.lambda_handler(
            {"userId": USER_ID, "tripId": TRIP_ID},
            context("update_trip"),
        )

        self.assertEqual(response["error"], "validation_error")
        self.table.update_item.assert_not_called()

    def test_unsupported_tool_is_rejected(self) -> None:
        response = trip_tools.lambda_handler(
            {"userId": USER_ID},
            context("delete_all_trips"),
        )

        self.assertEqual(response["error"], "unsupported_operation")
        self.assertNotIn("statusCode", response)


if __name__ == "__main__":
    unittest.main()
