from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_secure_facade_contract.py"
DEPLOY_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "test-application-deploy.yml"
QUALITY_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "test-application-quality.yml"

SPEC = importlib.util.spec_from_file_location("secure_facade_contract", VALIDATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load secure facade validator from {VALIDATOR_PATH}")

validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class SecureFacadeDeployContractTests(unittest.TestCase):
    @staticmethod
    def run_validator(*arguments: str) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with patch.object(sys, "argv", [str(VALIDATOR_PATH), *arguments]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return_code = validator.main()
        return return_code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def valid_arguments() -> list[str]:
        return [
            "--mode",
            "full",
            "--api-base-url",
            "https://abc123.execute-api.eu-west-3.amazonaws.com",
            "--agent-invoke-url",
            "https://abc123.execute-api.eu-west-3.amazonaws.com/agent/invoke",
            "--agent-runtime-invoke-url",
            "https://bedrock-agentcore.eu-west-3.amazonaws.com/runtimes/test/invocations?qualifier=DEFAULT",
            "--agentcore-gateway-mcp-url",
            "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/test/mcp",
            "--agentcore-memory-id",
            "memory-test",
            "--runtime-arn",
            "arn:aws:bedrock-agentcore:eu-west-3:123456789012:runtime/test",
            "--facade-function-name",
            "agent-api-facade-test",
            "--trip-tools-function-name",
            "trip-tools-test",
            "--trip-tools-target-id",
            "target-test",
            "--secure-facade-ready",
            "true",
            "--enforce",
        ]

    def test_complete_full_contract_passes_in_enforce_mode(self) -> None:
        return_code, stdout, stderr = self.run_validator(*self.valid_arguments())

        self.assertEqual(return_code, 0)
        self.assertIn("completed with 0 warning(s)", stdout)
        self.assertEqual(stderr, "")

    def test_previous_partial_workflow_contract_is_rejected(self) -> None:
        arguments = self.valid_arguments()
        missing_options = {
            "--agent-invoke-url",
            "--trip-tools-function-name",
            "--trip-tools-target-id",
            "--secure-facade-ready",
        }
        partial_arguments: list[str] = []
        index = 0
        while index < len(arguments):
            option = arguments[index]
            if option in missing_options:
                index += 2
                continue
            partial_arguments.append(option)
            index += 1
            if option != "--enforce":
                partial_arguments.append(arguments[index])
                index += 1

        return_code, _, stderr = self.run_validator(*partial_arguments)

        self.assertEqual(return_code, 1)
        self.assertIn("agent_invoke_url", stderr)
        self.assertIn("trip_tools_function_name", stderr)
        self.assertIn("trip_tools_target_id", stderr)
        self.assertIn("secure_facade_ready", stderr)

    def test_image_only_contract_does_not_require_deployed_outputs(self) -> None:
        return_code, stdout, stderr = self.run_validator("--mode", "image-only", "--enforce")

        self.assertEqual(return_code, 0)
        self.assertIn("does not require deployed application outputs", stdout)
        self.assertEqual(stderr, "")

    def test_deployment_workflow_has_non_bypassable_quality_and_contract_gates(self) -> None:
        workflow = DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("application-quality-gate:", workflow)
        self.assertIn("uses: ./.github/workflows/test-application-quality.yml", workflow)
        self.assertIn("needs: application-quality-gate", workflow)
        self.assertIn("scripts/validate_secure_facade_contract.py", workflow)
        self.assertNotIn("validate_gateway_first_contract.py", workflow)
        self.assertNotIn("enforce_secure_facade", workflow)
        self.assertIn("--enforce", workflow)

        for option in (
            "--agent-invoke-url",
            "--trip-tools-function-name",
            "--trip-tools-target-id",
            "--secure-facade-ready",
        ):
            self.assertIn(option, workflow)

    def test_quality_workflow_is_reusable_and_no_longer_compiles_legacy_wrapper(self) -> None:
        workflow = QUALITY_WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("workflow_call:", workflow)
        self.assertIn("${{ github.workflow }}-${{ github.ref }}", workflow)
        self.assertNotIn("validate_gateway_first_contract.py", workflow)


if __name__ == "__main__":
    unittest.main()
