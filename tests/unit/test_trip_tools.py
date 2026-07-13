from __future__ import annotations

import importlib.util
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "eu-west-3",
    "AWS_EC2_METADATA_DISABLED": "true",
    "TRIPS_TABLE_NAME": "test-trips",
    "TRIPS_DEFAULT_PAGE_SIZE": "20",
    "TRIPS_MAX_PAGE_SIZE": "50",
})

MODULE_PATH = Path(__file__).resolve().parents[2] / "deploy-agentcore" / "lambda_function_code.py"
SPEC = importlib.util.spec_from_file_location("trip_tools_lambda", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load trip tools module from {MODULE_PATH}")
trip_tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trip_tools)
USER_ID = "user-123"
TRIP_ID = "550e8400-e29b-41d4-a716-446655440000"
NEXT_TRIP_ID = "550e8400-e29b-41d4-a716-446655440001"


def context(tool_name: str):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"trip-target___{tool_name}"}))


class TripToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = Mock()
        self.previous_get_table = trip_tools._get_table
        trip_tools._get_table = Mock(return_value=self.table)

    def tearDown(self) -> None:
        trip_tools._get_table = self.previous_get_table

    def test_create_trip_returns_native_gateway_object(self) -> None:
        response = trip_tools.lambda_handler({
            "userId": USER_ID, "tripName": "Tokyo", "startDate": "2026-09-01",
            "endDate": "2026-09-10", "destination": "Tokyo"
        }, context("create_trip"))
        self.assertTrue(response["created"])
        self.assertIn("tripId", response)
        self.assertNotIn("statusCode", response)
        item = self.table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["userId"], USER_ID)
        self.assertEqual(item["tripName"], "Tokyo")

    def test_rejects_end_date_before_start_date(self) -> None:
        response = trip_tools.lambda_handler({
            "userId": USER_ID, "tripName": "Invalid", "startDate": "2026-09-10", "endDate": "2026-09-01"
        }, context("create_trip"))
        self.assertEqual(response["error"], "validation_error")
        self.table.put_item.assert_not_called()

    def test_rejects_unexpected_identity_field(self) -> None:
        response = trip_tools.lambda_handler({"userId": USER_ID, "actorId": "attacker"}, context("get_trips"))
        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_get_trip_uses_partition_and_redacts_user_identity(self) -> None:
        self.table.get_item.return_value = {"Item": {
            "userId": USER_ID, "tripId": TRIP_ID, "tripName": "Tokyo", "budget": Decimal("100.50")
        }}
        response = trip_tools.lambda_handler({"userId": USER_ID, "tripId": TRIP_ID}, context("get_trip"))
        self.assertTrue(response["found"])
        self.assertEqual(response["trip"]["budget"], 100.5)
        self.assertNotIn("userId", response["trip"])
        self.table.get_item.assert_called_once_with(Key={"userId": USER_ID, "tripId": TRIP_ID})

    def test_get_trips_uses_default_bounded_page_and_redacts_identity(self) -> None:
        self.table.query.return_value = {"Items": [{"userId": USER_ID, "tripId": TRIP_ID, "tripName": "Tokyo"}]}
        response = trip_tools.lambda_handler({"userId": USER_ID}, context("get_trips"))
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["trips"][0]["tripId"], TRIP_ID)
        self.assertNotIn("userId", response["trips"][0])
        self.assertEqual(self.table.query.call_args.kwargs["Limit"], 20)
        self.assertNotIn("ExclusiveStartKey", self.table.query.call_args.kwargs)
        self.assertNotIn("nextToken", response)

    def test_get_trips_returns_and_consumes_opaque_next_token(self) -> None:
        self.table.query.side_effect = [
            {
                "Items": [{"userId": USER_ID, "tripId": TRIP_ID, "tripName": "Tokyo"}],
                "LastEvaluatedKey": {"userId": USER_ID, "tripId": TRIP_ID},
            },
            {"Items": [{"userId": USER_ID, "tripId": NEXT_TRIP_ID, "tripName": "Kyoto"}]},
        ]
        first = trip_tools.lambda_handler({"userId": USER_ID, "limit": 1}, context("get_trips"))
        self.assertEqual(first["count"], 1)
        self.assertIn("nextToken", first)
        self.assertNotIn(USER_ID, first["nextToken"])
        second = trip_tools.lambda_handler({
            "userId": USER_ID, "limit": 1, "nextToken": first["nextToken"]
        }, context("get_trips"))
        self.assertEqual(second["trips"][0]["tripId"], NEXT_TRIP_ID)
        query = self.table.query.call_args.kwargs
        self.assertEqual(query["Limit"], 1)
        self.assertEqual(query["ExclusiveStartKey"], {"userId": USER_ID, "tripId": TRIP_ID})

    def test_get_trips_rejects_invalid_limit(self) -> None:
        for value in (0, 51, True, "10"):
            with self.subTest(value=value):
                response = trip_tools.lambda_handler({"userId": USER_ID, "limit": value}, context("get_trips"))
                self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_get_trips_rejects_invalid_next_token(self) -> None:
        response = trip_tools.lambda_handler({"userId": USER_ID, "nextToken": "not-a-token"}, context("get_trips"))
        self.assertEqual(response["error"], "validation_error")
        self.table.query.assert_not_called()

    def test_update_trip_requires_an_update(self) -> None:
        self.table.get_item.return_value = {"Item": {
            "userId": USER_ID, "tripId": TRIP_ID, "startDate": "2026-09-01",
            "endDate": "2026-09-10", "updatedAt": "2026-07-13T10:00:00+00:00"
        }}
        response = trip_tools.lambda_handler({"userId": USER_ID, "tripId": TRIP_ID}, context("update_trip"))
        self.assertEqual(response["error"], "validation_error")
        self.table.update_item.assert_not_called()

    def test_partial_date_update_cannot_invert_existing_range(self) -> None:
        self.table.get_item.return_value = {"Item": {
            "userId": USER_ID, "tripId": TRIP_ID, "startDate": "2026-09-01",
            "endDate": "2026-09-10", "updatedAt": "2026-07-13T10:00:00+00:00"
        }}
        response = trip_tools.lambda_handler({
            "userId": USER_ID, "tripId": TRIP_ID, "startDate": "2026-09-20"
        }, context("update_trip"))
        self.assertEqual(response["error"], "validation_error")
        self.table.update_item.assert_not_called()

    def test_update_uses_optimistic_concurrency_condition(self) -> None:
        self.table.get_item.return_value = {"Item": {
            "userId": USER_ID, "tripId": TRIP_ID, "startDate": "2026-09-01",
            "endDate": "2026-09-10", "updatedAt": "2026-07-13T10:00:00+00:00"
        }}
        response = trip_tools.lambda_handler({
            "userId": USER_ID, "tripId": TRIP_ID, "status": "confirmed"
        }, context("update_trip"))
        self.assertTrue(response["updated"])
        call = self.table.update_item.call_args.kwargs
        self.assertIn("#updatedAt = :expectedUpdatedAt", call["ConditionExpression"])
        self.assertEqual(call["ExpressionAttributeValues"][":expectedUpdatedAt"], "2026-07-13T10:00:00+00:00")

    def test_unsupported_tool_is_rejected(self) -> None:
        response = trip_tools.lambda_handler({"userId": USER_ID}, context("delete_all_trips"))
        self.assertEqual(response["error"], "unsupported_operation")
        self.assertNotIn("statusCode", response)

    def test_terraform_contract_exposes_pagination_and_five_second_timeout(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = (root / "infra" / "environments" / "test" / "trip_tools.tf").read_text(encoding="utf-8")
        module = (root / "infra" / "modules" / "trip_tools_lambda" / "main.tf").read_text(encoding="utf-8")
        self.assertIn('name        = "limit"', schema)
        self.assertIn('name        = "nextToken"', schema)
        self.assertIn("timeout                        = 5", module)


if __name__ == "__main__":
    unittest.main()
