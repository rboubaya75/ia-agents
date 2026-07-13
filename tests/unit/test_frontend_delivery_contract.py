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

    def test_deploy_builds_and_publishes_before_invalidation(self) -> None:
        content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
        build = content.index("- name: Build frontend")
        sync = content.index("- name: Sync frontend assets to S3")
        invalidate = content.index("- name: Invalidate CloudFront distribution")
        self.assertLess(build, sync)
        self.assertLess(sync, invalidate)
        self.assertIn('aws s3 sync dist/ "s3://${{ steps.tfout_after.outputs.frontend_bucket_name }}" --delete', content)

    def test_cloudfront_uses_private_s3_oac_and_index_root(self) -> None:
        content = FRONTEND_MODULE.read_text(encoding="utf-8")
        self.assertIn('default_root_object = "index.html"', content)
        self.assertIn('origin_access_control_origin_type = "s3"', content)
        self.assertIn('signing_behavior                  = "always"', content)
        self.assertIn('actions   = ["s3:GetObject"]', content)
        self.assertIn('identifiers = ["cloudfront.amazonaws.com"]', content)


if __name__ == "__main__":
    unittest.main()
