from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_agentcore_memory_plan.py"
SPEC = importlib.util.spec_from_file_location("agentcore_memory_plan", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def valid_plan() -> dict:
    resources = [
        {"address": address}
        for address in sorted(module.REQUIRED_PLANNED_ADDRESSES)
    ]
    changes = [
        {"address": address, "change": {"actions": ["delete", "create"]}}
        for address in sorted(module.REQUIRED_CHANGED_ADDRESSES)
    ]
    return {
        "planned_values": {"root_module": {"resources": resources}},
        "resource_changes": changes,
    }


class AgentCoreMemoryPlanTests(unittest.TestCase):
    def test_accepts_complete_agentcore_memory_plan(self) -> None:
        module.validate_plan(valid_plan())

    def test_finds_resources_in_child_modules(self) -> None:
        plan = valid_plan()
        resources = plan["planned_values"]["root_module"].pop("resources")
        plan["planned_values"]["root_module"]["child_modules"] = [
            {"resources": resources}
        ]

        module.validate_plan(plan)

    def test_rejects_plan_without_memory_verification_resource(self) -> None:
        plan = valid_plan()
        plan["planned_values"]["root_module"]["resources"] = [
            resource
            for resource in plan["planned_values"]["root_module"]["resources"]
            if resource["address"]
            != "terraform_data.agentcore_memory_preferences_verification[0]"
        ]

        with self.assertRaisesRegex(RuntimeError, "absent from planned values"):
            module.validate_plan(plan)

    def test_rejects_noop_strategy_resource(self) -> None:
        plan = valid_plan()
        for change in plan["resource_changes"]:
            if (
                change["address"]
                == "terraform_data.agentcore_memory_preferences_strategy[0]"
            ):
                change["change"]["actions"] = ["no-op"]

        with self.assertRaisesRegex(RuntimeError, "must be created or replaced"):
            module.validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
