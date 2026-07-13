from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_tainted_facade_recovery.py"
SPEC = importlib.util.spec_from_file_location("taint_recovery", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)

BASE = {
    "function_name": recovery.FUNCTION_NAME,
    "role": "arn:aws:iam::123456789012:role/wildrydes-test-agent-invocation-facade-role",
    "handler": recovery.HANDLER,
    "runtime": recovery.RUNTIME,
    "architectures": recovery.ARCHITECTURES,
}


def plan(*changes: dict) -> dict:
    return {"resource_changes": list(changes)}


def facade_change(*, reason="replace_because_tainted", after=None, replace_paths=None) -> dict:
    return {
        "address": recovery.ADDRESS,
        "mode": "managed",
        "type": recovery.RESOURCE_TYPE,
        "action_reason": reason,
        "change": {
            "actions": ["delete", "create"],
            "before": dict(BASE),
            "after": dict(BASE if after is None else after),
            "replace_paths": [] if replace_paths is None else replace_paths,
        },
    }


class TaintedFacadeRecoveryTests(unittest.TestCase):
    def test_exact_tainted_facade_is_accepted(self) -> None:
        result = recovery.inspect_plan(plan(facade_change()))
        self.assertEqual(result["address"], recovery.ADDRESS)
        self.assertEqual(result["role"], BASE["role"])

    def test_non_taint_reason_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "replace_because_tainted"):
            recovery.inspect_plan(plan(facade_change(reason="replace_because_cannot_update")))

    def test_changed_handler_is_rejected(self) -> None:
        changed = dict(BASE)
        changed["handler"] = "other.handler"
        with self.assertRaisesRegex(ValueError, "handler"):
            recovery.inspect_plan(plan(facade_change(after=changed)))

    def test_other_destructive_change_is_rejected(self) -> None:
        other = {
            "address": "module.trip_tools_lambda.aws_lambda_function.this",
            "mode": "managed",
            "type": "aws_lambda_function",
            "change": {"actions": ["delete", "create"]},
        }
        with self.assertRaisesRegex(ValueError, "exactly one destructive"):
            recovery.inspect_plan(plan(facade_change(), other))

    def test_aws_configuration_must_be_active_and_identical(self) -> None:
        config = {
            "FunctionName": recovery.FUNCTION_NAME,
            "Runtime": recovery.RUNTIME,
            "Handler": recovery.HANDLER,
            "Architectures": recovery.ARCHITECTURES,
            "Role": BASE["role"],
            "State": "Active",
            "LastUpdateStatus": "Successful",
        }
        recovery.verify_aws(config, BASE["role"])
        config["State"] = "Failed"
        with self.assertRaisesRegex(ValueError, "State"):
            recovery.verify_aws(config, BASE["role"])


if __name__ == "__main__":
    unittest.main()
