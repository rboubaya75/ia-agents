from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

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


def active_memory(strategies: list[dict] | None = None) -> dict:
    return {"status": "ACTIVE", "strategies": strategies or []}


def preference_strategy(namespace: str = NAMESPACE) -> dict:
    return {
        "strategyId": "strategy-123",
        "name": STRATEGY_NAME,
        "namespaceTemplates": [namespace],
    }


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
        self.assertEqual(modification["namespaceTemplates"], [NAMESPACE])

    def test_compliant_strategy_is_unchanged(self) -> None:
        client = FakeClient([active_memory([preference_strategy()])])

        action = module.ensure_strategy(
            client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
        )

        self.assertEqual(action, "unchanged")
        self.assertEqual(client.update_calls, [])

    def test_check_fails_when_strategy_is_missing(self) -> None:
        client = FakeClient([active_memory()])

        with self.assertRaisesRegex(RuntimeError, "not compliant"):
            module.check_strategy(
                client, MEMORY_ID, STRATEGY_NAME, NAMESPACE, timeout_seconds=30
            )

    def test_namespace_validation_requires_actor_isolation(self) -> None:
        self.assertEqual(module.validate_namespace_template(NAMESPACE), NAMESPACE)
        with self.assertRaises(ValueError):
            module.validate_namespace_template("/travel/preferences")
        with self.assertRaises(ValueError):
            module.validate_namespace_template("travel/{actorId}/preferences")

    def test_terraform_contract_runs_strategy_before_runtime(self) -> None:
        terraform = (
            ROOT / "infra" / "environments" / "test" / "agentcore_native.tf"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'resource "terraform_data" "agentcore_memory_preferences_strategy"',
            terraform,
        )
        self.assertIn("configure_agentcore_memory_strategy.py", terraform)
        self.assertIn('MEMORY_NAMESPACE_TEMPLATE   =', terraform)
        self.assertIn(
            "terraform_data.agentcore_memory_preferences_strategy", terraform
        )


if __name__ == "__main__":
    unittest.main()
