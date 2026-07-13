from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "repair-tainted-test-facade.yml"
SCRIPT = ROOT / "scripts" / "validate_tainted_facade_recovery.py"
SPEC = importlib.util.spec_from_file_location("taint_recovery", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def values(target: str) -> dict:
    contract = recovery.TARGETS[target]
    return {
        "function_name": contract["function_name"],
        "role": f"arn:aws:iam::123456789012:role/{contract['function_name']}-role",
        "handler": contract["handler"],
        "runtime": contract["runtime"],
        "architectures": contract["architectures"],
    }


def plan(*changes: dict) -> dict:
    return {"resource_changes": list(changes)}


def lambda_change(target: str, *, reason="replace_because_tainted", after=None, replace_paths=None) -> dict:
    contract = recovery.TARGETS[target]
    before = values(target)
    return {
        "address": contract["address"],
        "mode": "managed",
        "type": contract["resource_type"],
        "action_reason": reason,
        "change": {
            "actions": ["delete", "create"],
            "before": before,
            "after": dict(before if after is None else after),
            "replace_paths": [] if replace_paths is None else replace_paths,
        },
    }


class TaintedLambdaRecoveryTests(unittest.TestCase):
    def test_exact_facade_taint_is_accepted(self) -> None:
        result = recovery.inspect_plan(plan(lambda_change("facade")), "facade")
        self.assertEqual(result["target"], "facade")
        self.assertEqual(result["address"], recovery.TARGETS["facade"]["address"])

    def test_exact_trip_tools_taint_is_accepted(self) -> None:
        result = recovery.inspect_plan(plan(lambda_change("trip-tools")), "trip-tools")
        self.assertEqual(result["target"], "trip-tools")
        self.assertEqual(result["function_name"], "wildrydes-test-trip-tools")

    def test_selected_target_must_match_plan(self) -> None:
        with self.assertRaisesRegex(ValueError, "selected test Lambda"):
            recovery.inspect_plan(plan(lambda_change("trip-tools")), "facade")

    def test_non_taint_reason_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "replace_because_tainted"):
            recovery.inspect_plan(
                plan(lambda_change("trip-tools", reason="replace_because_cannot_update")),
                "trip-tools",
            )

    def test_changed_handler_is_rejected(self) -> None:
        changed = values("trip-tools")
        changed["handler"] = "other.handler"
        with self.assertRaisesRegex(ValueError, "handler"):
            recovery.inspect_plan(plan(lambda_change("trip-tools", after=changed)), "trip-tools")

    def test_force_replacement_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "force-replacement"):
            recovery.inspect_plan(
                plan(lambda_change("trip-tools", replace_paths=[["function_name"]])),
                "trip-tools",
            )

    def test_other_destructive_change_is_rejected(self) -> None:
        other = lambda_change("facade")
        with self.assertRaisesRegex(ValueError, "exactly one destructive"):
            recovery.inspect_plan(plan(lambda_change("trip-tools"), other), "trip-tools")

    def test_aws_configuration_must_be_active_and_identical(self) -> None:
        contract = recovery.TARGETS["trip-tools"]
        role = values("trip-tools")["role"]
        config = {
            "FunctionName": contract["function_name"],
            "Runtime": contract["runtime"],
            "Handler": contract["handler"],
            "Architectures": contract["architectures"],
            "Role": role,
            "State": "Active",
            "LastUpdateStatus": "Successful",
        }
        recovery.verify_aws(config, "trip-tools", role)
        config["State"] = "Failed"
        with self.assertRaisesRegex(ValueError, "State"):
            recovery.verify_aws(config, "trip-tools", role)

    def test_workflow_supports_exact_target_selection(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("target:", workflow)
        self.assertIn("- facade", workflow)
        self.assertIn("- trip-tools", workflow)
        self.assertIn('--target "${{ inputs.target }}"', workflow)
        self.assertIn('terraform untaint "${{ steps.contract.outputs.address }}"', workflow)


if __name__ == "__main__":
    unittest.main()
