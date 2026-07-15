from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

import boto3
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "configure_agentcore_memory_strategy.py"
SPEC = importlib.util.spec_from_file_location("memory_strategy_config", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

MEMORY_ID = "memory-123"
STRATEGY_NAME = "TravelPreferences"
NAMESPACE = "/travel/{actorId}/preferences"


class FakeClient:
    def __init__(self, memories: list[dict]):
        self.memories = list(memories)
        self.update_calls: list[dict] = []

    def get_memory(self, **_kwargs):
        if len(self.memories) > 1:
            memory = self.memories.pop(0)
        else:
            memory = self.memories[0]
        return {"memory": memory}

    def update_memory(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"memory": {"status": "UPDATING"}}


def preference_strategy(
    namespace: str = NAMESPACE,
    *,
    strategy_type: str = "USER_PREFERENCE",
    status: str = "ACTIVE",
    description: str = module.DEFAULT_DESCRIPTION,
) -> dict:
    return {
        "strategyId": "strategy-123",
        "name": STRATEGY_NAME,
        "description": description,
        "type": strategy_type,
        "status": status,
        "namespaces": [],
        "namespaceTemplates": [namespace],
    }


def active_memory(strategies: list[dict] | None = None) -> dict:
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    return {
        "arn": "arn:aws:bedrock-agentcore:eu-west-3:123456789012:memory/memory-123",
        "id": MEMORY_ID,
        "name": "wildrydes_test_memory",
        "eventExpiryDuration": 30,
        "status": "ACTIVE",
        "createdAt": now,
        "updatedAt": now,
        "strategies": strategies or [],
    }


def botocore_client():
    return boto3.client(
        "bedrock-agentcore-control",
        region_name="eu-west-3",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
    )


class AgentCoreMemoryStrategyTests(unittest.TestCase):
    def test_adds_missing_user_preference_strategy(self) -> None:
        client = FakeClient(
            [active_memory(), active_memory([preference_strategy()])]
        )

        action = module.ensure_strategy(
            client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
        )

        self.assertEqual(action, "added")
        payload = client.update_calls[0]["memoryStrategies"]
        strategy = payload["addMemoryStrategies"][0][
            "userPreferenceMemoryStrategy"
        ]
        self.assertEqual(strategy["name"], STRATEGY_NAME)
        self.assertEqual(strategy["description"], module.DEFAULT_DESCRIPTION)
        self.assertEqual(strategy["namespaceTemplates"], [NAMESPACE])

    def test_modifies_wrong_namespace_without_recreating_memory(self) -> None:
        client = FakeClient(
            [
                active_memory([preference_strategy("/wrong/{actorId}")]),
                active_memory([preference_strategy()]),
            ]
        )

        action = module.ensure_strategy(
            client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
        )

        self.assertEqual(action, "modified")
        modification = client.update_calls[0]["memoryStrategies"][
            "modifyMemoryStrategies"
        ][0]
        self.assertEqual(modification["memoryStrategyId"], "strategy-123")
        self.assertEqual(modification["description"], module.DEFAULT_DESCRIPTION)
        self.assertEqual(modification["namespaceTemplates"], [NAMESPACE])

    def test_compliant_strategy_is_unchanged(self) -> None:
        client = FakeClient([active_memory([preference_strategy()])])

        action = module.ensure_strategy(
            client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
        )

        self.assertEqual(action, "unchanged")
        self.assertEqual(client.update_calls, [])

    def test_waits_for_existing_strategy_to_become_active(self) -> None:
        client = FakeClient(
            [
                active_memory([preference_strategy(status="CREATING")]),
                active_memory([preference_strategy()]),
            ]
        )

        action = module.ensure_strategy(
            client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
        )

        self.assertEqual(action, "unchanged")
        self.assertEqual(client.update_calls, [])

    def test_rejects_same_name_with_wrong_strategy_type(self) -> None:
        client = FakeClient(
            [active_memory([preference_strategy(strategy_type="SEMANTIC")])]
        )

        with self.assertRaisesRegex(RuntimeError, "unexpected type"):
            module.ensure_strategy(
                client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
            )

    def test_check_fails_when_strategy_is_missing(self) -> None:
        client = FakeClient([active_memory()])

        with self.assertRaisesRegex(TimeoutError, "strategy"):
            module.check_strategy(
                client,
                MEMORY_ID,
                STRATEGY_NAME,
                NAMESPACE,
                timeout_seconds=0,
            )

    def test_namespace_validation_requires_actor_isolation(self) -> None:
        self.assertEqual(module.validate_namespace_template(NAMESPACE), NAMESPACE)
        with self.assertRaises(ValueError):
            module.validate_namespace_template("/travel/preferences")
        with self.assertRaises(ValueError):
            module.validate_namespace_template("travel/{actorId}/preferences")

    def test_botocore_contract_accepts_add_strategy_request(self) -> None:
        client = botocore_client()
        module.validate_client_contract(client)
        expected_update = {
            "memoryId": MEMORY_ID,
            "memoryStrategies": {
                "addMemoryStrategies": [
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": STRATEGY_NAME,
                            "description": module.DEFAULT_DESCRIPTION,
                            "namespaceTemplates": [NAMESPACE],
                        }
                    }
                ]
            },
        }
        with Stubber(client) as stubber:
            stubber.add_response(
                "get_memory",
                {"memory": active_memory()},
                {"memoryId": MEMORY_ID, "view": "full"},
            )
            stubber.add_response("update_memory", {}, expected_update)
            stubber.add_response(
                "get_memory",
                {"memory": active_memory([preference_strategy()])},
                {"memoryId": MEMORY_ID, "view": "full"},
            )

            action = module.ensure_strategy(
                client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
            )

        self.assertEqual(action, "added")

    def test_botocore_contract_accepts_modify_strategy_request(self) -> None:
        client = botocore_client()
        expected_update = {
            "memoryId": MEMORY_ID,
            "memoryStrategies": {
                "modifyMemoryStrategies": [
                    {
                        "memoryStrategyId": "strategy-123",
                        "description": module.DEFAULT_DESCRIPTION,
                        "namespaceTemplates": [NAMESPACE],
                    }
                ]
            },
        }
        with Stubber(client) as stubber:
            stubber.add_response(
                "get_memory",
                {
                    "memory": active_memory(
                        [preference_strategy("/wrong/{actorId}")]
                    )
                },
                {"memoryId": MEMORY_ID, "view": "full"},
            )
            stubber.add_response("update_memory", {}, expected_update)
            stubber.add_response(
                "get_memory",
                {"memory": active_memory([preference_strategy()])},
                {"memoryId": MEMORY_ID, "view": "full"},
            )

            action = module.ensure_strategy(
                client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
            )

        self.assertEqual(action, "modified")

    def test_terraform_contract_runs_strategy_and_verification_before_runtime(self) -> None:
        terraform = (
            ROOT / "infra" / "environments" / "test" / "agentcore_native.tf"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'resource "terraform_data" "agentcore_memory_preferences_strategy"',
            terraform,
        )
        self.assertIn(
            'resource "terraform_data" "agentcore_memory_preferences_verification"',
            terraform,
        )
        self.assertIn("configure_agentcore_memory_strategy.py", terraform)
        self.assertIn("requirements-deploy.txt", terraform)
        self.assertIn("deployment_revision = var.agentcore_image_tag", terraform)
        self.assertIn('"$SCRIPT_PATH" ensure', terraform)
        self.assertIn('"$SCRIPT_PATH" check', terraform)
        self.assertIn("MEMORY_NAMESPACE_TEMPLATE", terraform)
        self.assertIn("local.agentcore_memory_namespace_template", terraform)
        self.assertIn(
            "terraform_data.agentcore_memory_preferences_verification", terraform
        )


if __name__ == "__main__":
    unittest.main()
