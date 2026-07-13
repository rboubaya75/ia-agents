from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
QUALITY_WORKFLOW = ROOT / ".github" / "workflows" / "test-application-quality.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "test-application-deploy.yml"
REPAIR_WORKFLOW = ROOT / ".github" / "workflows" / "repair-frontend-lock.yml"
FRONTEND_MODULE = ROOT / "infra" / "modules" / "frontend_static_site" / "main.tf"


class FrontendDeliveryContractTests(unittest.TestCase):
    def test_quality_gate_remains_immutable_and_strict(self) -> None:
        content = QUALITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("run: npm ci", content)
        self.assertIn("npm audit --omit=dev --audit-level=high", content)
        self.assertNotIn("npm audit fix", content)
        self.assertIn("contents: read", content)

    def test_lock_repair_is_manual_scoped_and_audited(self) -> None:
        content = REPAIR_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("inputs.confirm_repair == true", content)
        self.assertIn("environment:\n      name: test", content)
        self.assertIn("npm audit fix --package-lock-only --ignore-scripts", content)
        self.assertIn("npm audit --omit=dev --audit-level=moderate", content)
        self.assertIn("git diff --exit-code -- frontend/package.json", content)
        self.assertIn('git push origin HEAD:migration/secure-agentcore-v1', content)

    def test_audited_lock_is_persisted_before_application_checks(self) -> None:
        content = REPAIR_WORKFLOW.read_text(encoding="utf-8")
        commit = content.index("- name: Commit audited lockfile")
        lint = content.index("- name: Lint frontend")
        build = content.index("- name: Build frontend")
        self.assertLess(commit, lint)
        self.assertLess(commit, build)

    def test_deploy_builds_and_publishes_before_invalidation(self) -> None:
        content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        build = content.index("- name: Build frontend")
        sync = content.index("- name: Sync frontend assets to S3")
        invalidate = content.index("- name: Invalidate CloudFront distribution")
        self.assertLess(build, sync)
        self.assertLess(sync, invalidate)
        self.assertIn('aws s3 sync dist/ "s3://${{ steps.tfout_after.outputs.frontend_bucket_name }}" --delete', content)

    def test_deploy_reads_terraform_outputs_once_as_json(self) -> None:
        content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("terraform output -raw", content)
        self.assertGreaterEqual(content.count("terraform output -json"), 2)
        self.assertIn("Terraform remote state exposes no outputs", content)
        self.assertIn("terraform_wrapper: false", content)

    def test_agentcore_plan_exit_code_is_captured_without_wrapper_outputs(self) -> None:
        content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        start = content.index("- name: Terraform plan native AgentCore control plane and facade")
        end = content.index("- name: Render AgentCore plan evidence", start)
        plan_step = content[start:end]
        self.assertIn("set +e", plan_step)
        self.assertIn("exitcode=$?", plan_step)
        self.assertIn('echo "exitcode=$exitcode" >> "$GITHUB_OUTPUT"', plan_step)
        self.assertIn("test -s tfplan-agentcore-control-plane", plan_step)
        self.assertNotIn("continue-on-error: true", plan_step)

    def test_agentcore_plan_evidence_is_runtime_scoped(self) -> None:
        content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        runtime_scope = "inputs.deploy_mode == 'runtime-only' || inputs.deploy_mode == 'full'"
        guarded_steps = (
            "Render AgentCore plan evidence",
            "Analyze AgentCore plan safety",
            "Record immutable AgentCore plan metadata",
            "Publish AgentCore plan summary",
            "Upload reviewed AgentCore plan artifact",
            "Fail on unsafe AgentCore plan",
        )
        for step_name in guarded_steps:
            start = content.index(f"- name: {step_name}")
            end = content.find("\n      - name:", start + 1)
            if end == -1:
                end = len(content)
            step = content[start:end]
            self.assertIn(runtime_scope, step, msg=step_name)
            self.assertIn("steps.agentcore_plan.conclusion == 'success'", step, msg=step_name)

    def test_cloudfront_uses_private_s3_oac_and_index_root(self) -> None:
        content = FRONTEND_MODULE.read_text(encoding="utf-8")
        self.assertIn('default_root_object = "index.html"', content)
        self.assertIn('origin_access_control_origin_type = "s3"', content)
        self.assertIn('signing_behavior                  = "always"', content)
        self.assertIn('actions   = ["s3:GetObject"]', content)
        self.assertIn('identifiers = ["cloudfront.amazonaws.com"]', content)


if __name__ == "__main__":
    unittest.main()
