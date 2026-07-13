from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_secure_facade_contract.py"
SPEC = importlib.util.spec_from_file_location("secure_facade_contract", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def frontend_values() -> dict[str, str]:
    return {
        "api_base_url": "https://nw71qm7gqe.execute-api.eu-west-3.amazonaws.com",
        "agent_invoke_url": "https://nw71qm7gqe.execute-api.eu-west-3.amazonaws.com/agent/invoke",
        "agent_runtime_invoke_url": "",
        "agentcore_gateway_mcp_url": "",
        "agentcore_memory_id": "",
        "runtime_arn": "",
        "facade_function_name": "wildrydes-test-agent-invocation-facade",
        "trip_tools_function_name": "wildrydes-test-trip-tools",
        "trip_tools_target_id": "",
        "secure_facade_ready": "false",
    }


def complete_values() -> dict[str, str]:
    values = frontend_values()
    values.update(
        {
            "agent_runtime_invoke_url": (
                "https://bedrock-agentcore.eu-west-3.amazonaws.com/"
                "runtimes/wildrydes-test/invocations?qualifier=DEFAULT"
            ),
            "agentcore_gateway_mcp_url": "https://gateway.example.com/mcp",
            "agentcore_memory_id": "memory-test",
            "runtime_arn": "arn:aws:bedrock-agentcore:eu-west-3:123456789012:runtime/wildrydes-test",
            "trip_tools_target_id": "trip-tools-target",
            "secure_facade_ready": "true",
        }
    )
    return values


class SecureFacadeContractModeTests(unittest.TestCase):
    def test_frontend_only_accepts_deployed_public_facade_without_runtime_outputs(self) -> None:
        self.assertEqual(contract.validate_contract("frontend-only", frontend_values()), [])

    def test_frontend_only_still_requires_public_facade(self) -> None:
        values = frontend_values()
        values["facade_function_name"] = ""
        self.assertIn("facade_function_name is missing", contract.validate_contract("frontend-only", values))

    def test_runtime_only_rejects_missing_runtime_contract(self) -> None:
        errors = contract.validate_contract("runtime-only", frontend_values())
        self.assertIn("agent_runtime_invoke_url must remain a valid technical IAM Runtime URL", errors)
        self.assertIn("agentcore_gateway_mcp_url is missing or invalid", errors)
        self.assertIn("agentcore_memory_id is missing", errors)
        self.assertIn("runtime_arn is missing or invalid", errors)
        self.assertIn("trip_tools_target_id is missing", errors)
        self.assertIn("secure_facade_ready is not true", errors)

    def test_full_accepts_complete_secure_runtime_contract(self) -> None:
        self.assertEqual(contract.validate_contract("full", complete_values()), [])

    def test_image_only_does_not_require_deployed_outputs(self) -> None:
        self.assertEqual(contract.validate_contract("image-only", {}), [])


if __name__ == "__main__":
    unittest.main()
