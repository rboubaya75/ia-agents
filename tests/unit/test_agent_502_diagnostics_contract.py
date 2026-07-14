from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "diagnose-test-agent-502.yml"
DOCKERFILE = ROOT / "deploy-agentcore" / "Dockerfile"
ENTRYPOINT = ROOT / "deploy-agentcore" / "agents" / "entrypoint.py"
CHAT_SERVICE = ROOT / "frontend" / "src" / "services" / "chatService.ts"
FACADE = ROOT / "infra" / "modules" / "agent_api_facade" / "src" / "lambda_function.py"


class Agent502DiagnosticsContractTests(unittest.TestCase):
    def test_diagnostic_workflow_is_manual_protected_and_oidc_scoped(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("inputs.confirm_diagnosis == true", content)
        self.assertIn("environment:\n      name: test", content)
        self.assertIn("id-token: write", content)
        self.assertIn("contents: read", content)

    def test_diagnostic_workflow_reproduces_valid_facade_contract(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("operation_id=", content)
        self.assertIn("--arg operation_id", content)
        self.assertIn("operationId:$operation_id", content)
        self.assertIn("response_operation_id", content)
        self.assertIn("did not preserve the smoke operation identifier", content)

    def test_diagnostic_workflow_collects_both_log_planes(self) -> None:
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("aws lambda invoke", content)
        self.assertIn("aws logs filter-log-events", content)
        self.assertIn("agent_api_facade_log_group_name", content)
        self.assertIn("/aws/bedrock-agentcore/runtimes/", content)
        self.assertIn("Upload protected diagnostic evidence", content)
        self.assertIn("retention-days: 7", content)
        self.assertNotIn("cat diagnostics/facade-logs.json", content)

    def test_runtime_container_declares_agentcore_port_and_safe_entrypoint(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("EXPOSE 8080", dockerfile)
        self.assertNotIn("EXPOSE 9000", dockerfile)
        self.assertIn('CMD ["python", "-m", "agents.entrypoint"]', dockerfile)
        self.assertIn("app.run()", entrypoint)
        self.assertNotIn("initialize_mcp_tools", entrypoint)

    def test_browser_displays_only_safe_correlation_reference(self) -> None:
        content = CHAT_SERVICE.read_text(encoding="utf-8")
        self.assertIn("requestId?: unknown", content)
        self.assertIn("Reference: ${payload.requestId}", content)
        self.assertNotIn("payload.code", content)

    def test_facade_logs_safe_runtime_metadata_and_returns_reference(self) -> None:
        content = FACADE.read_text(encoding="utf-8")
        self.assertIn('"event": "runtime_response_metadata"', content)
        self.assertIn('"event": "runtime_client_error"', content)
        self.assertIn('"runtime_arn_hash": safe_hash(RUNTIME_ARN)', content)
        self.assertIn('"requestId": request_id', content)
        self.assertNotIn('"accessToken"', content)
        self.assertNotIn('"authorization":', content.lower())


if __name__ == "__main__":
    unittest.main()
