from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = ROOT / "scripts" / "terraform_plan_guard.py"
TERRAFORM_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "test-terraform-stack.yml"
DEPLOY_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "test-application-deploy.yml"
QUALITY_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "test-application-quality.yml"

SPEC = importlib.util.spec_from_file_location("terraform_plan_guard", GUARD_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load Terraform plan guard from {GUARD_PATH}")

guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def plan_json(*changes: dict) -> dict:
    return {
        "format_version": "1.2",
        "terraform_version": "1.9.0",
        "resource_changes": list(changes),
    }


def resource(address: str, resource_type: str, actions: list[str]) -> dict:
    return {
        "address": address,
        "mode": "managed",
        "type": resource_type,
        "name": address.rsplit(".", 1)[-1],
        "change": {"actions": actions},
    }


class TerraformPlanGuardTests(unittest.TestCase):
    @staticmethod
    def invoke(*arguments: str) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with patch.object(sys, "argv", [str(GUARD_PATH), *arguments]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return_code = guard.main()
        return return_code, stdout.getvalue(), stderr.getvalue()

    def test_safe_plan_passes_and_produces_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tfplan.json"
            summary = root / "summary.md"
            source.write_text(
                json.dumps(
                    plan_json(
                        resource("aws_lambda_function.facade", "aws_lambda_function", ["update"]),
                        resource("aws_s3_object.asset", "aws_s3_object", ["create"]),
                    )
                ),
                encoding="utf-8",
            )

            code, _, stderr = self.invoke(
                "analyze",
                "--plan-json",
                str(source),
                "--summary-output",
                str(summary),
            )

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            content = summary.read_text(encoding="utf-8")
            self.assertIn("| create | 1 |", content)
            self.assertIn("| update | 1 |", content)
            self.assertIn("**PASS**", content)

    def test_critical_delete_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tfplan.json"
            summary = root / "summary.md"
            source.write_text(
                json.dumps(
                    plan_json(
                        resource(
                            "module.cognito.aws_cognito_user_pool.this",
                            "aws_cognito_user_pool",
                            ["delete"],
                        )
                    )
                ),
                encoding="utf-8",
            )

            code, _, stderr = self.invoke(
                "analyze",
                "--plan-json",
                str(source),
                "--summary-output",
                str(summary),
            )

            self.assertEqual(code, 1)
            self.assertIn("blocked Terraform delete", stderr)
            self.assertIn("**BLOCKED**", summary.read_text(encoding="utf-8"))

    def test_critical_replace_is_blocked_regardless_of_action_order(self) -> None:
        for actions in (["delete", "create"], ["create", "delete"]):
            with self.subTest(actions=actions), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "tfplan.json"
                summary = root / "summary.md"
                source.write_text(
                    json.dumps(
                        plan_json(
                            resource(
                                "aws_bedrockagentcore_agent_runtime.agent[0]",
                                "aws_bedrockagentcore_agent_runtime",
                                actions,
                            )
                        )
                    ),
                    encoding="utf-8",
                )

                code, _, stderr = self.invoke(
                    "analyze",
                    "--plan-json",
                    str(source),
                    "--summary-output",
                    str(summary),
                )

                self.assertEqual(code, 1)
                self.assertIn("blocked Terraform replace", stderr)

    def test_report_only_allows_explicit_destroy_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tfdestroyplan.json"
            summary = root / "destroy-summary.md"
            source.write_text(
                json.dumps(
                    plan_json(
                        resource("aws_dynamodb_table.trips", "aws_dynamodb_table", ["delete"])
                    )
                ),
                encoding="utf-8",
            )

            code, _, stderr = self.invoke(
                "analyze",
                "--plan-json",
                str(source),
                "--summary-output",
                str(summary),
                "--policy",
                "report-only",
            )

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("**REVIEW REQUIRED**", summary.read_text(encoding="utf-8"))

    @staticmethod
    def single_path_rule(*changes: dict) -> dict:
        rules = guard.evaluate_guard_rules(plan_json(*changes))
        return next(item for item in rules if item["number"] == "4")

    def test_single_path_rule_does_not_count_a_resource_policy(self) -> None:
        # A resource policy cannot carry the single-path requirement under either form:
        # `aws:RequestHeader` is not a global condition key, and `aws:SourceIp` is
        # evaluated against the end client rather than the CloudFront edge. Counting it
        # would attest a mechanism that does not exist.
        found = self.single_path_rule(
            resource("aws_api_gateway_rest_api.this", "aws_api_gateway_rest_api", ["update"]),
            resource(
                "aws_api_gateway_rest_api_policy.single_path",
                "aws_api_gateway_rest_api_policy",
                ["update"],
            ),
        )

        self.assertEqual(found["status"], "skipped")
        self.assertIn("precondition 9 unmet", found["detail"])

    def test_single_path_rule_passes_on_a_waf_association(self) -> None:
        found = self.single_path_rule(
            resource("aws_api_gateway_rest_api.this", "aws_api_gateway_rest_api", ["update"]),
            resource(
                "aws_wafv2_web_acl_association.this[0]",
                "aws_wafv2_web_acl_association",
                ["create"],
            ),
        )

        self.assertEqual(found["status"], "pass")

    def test_single_path_rule_does_not_count_a_removed_waf_association(self) -> None:
        found = self.single_path_rule(
            resource("aws_api_gateway_rest_api.this", "aws_api_gateway_rest_api", ["update"]),
            resource(
                "aws_wafv2_web_acl_association.this[0]",
                "aws_wafv2_web_acl_association",
                ["delete"],
            ),
        )

        self.assertEqual(found["status"], "skipped")

    def test_metadata_round_trip_and_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "tfplan"
            metadata = root / "tfplan-metadata.json"
            plan.write_bytes(b"immutable-plan")

            code, _, stderr = self.invoke(
                "record",
                "--plan",
                str(plan),
                "--metadata-output",
                str(metadata),
                "--commit-sha",
                "abc123",
                "--stack-path",
                "infra/environments/test",
                "--run-id",
                "42",
                "--terraform-version",
                "1.9.0",
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")

            code, stdout, stderr = self.invoke(
                "verify",
                "--plan",
                str(plan),
                "--metadata",
                str(metadata),
                "--expected-commit-sha",
                "abc123",
                "--expected-stack-path",
                "infra/environments/test",
                "--expected-run-id",
                "42",
                "--expected-terraform-version",
                "1.9.0",
            )
            self.assertEqual(code, 0)
            self.assertIn("verified", stdout)
            self.assertEqual(stderr, "")

            plan.write_bytes(b"tampered-plan")
            code, _, stderr = self.invoke(
                "verify",
                "--plan",
                str(plan),
                "--metadata",
                str(metadata),
                "--expected-commit-sha",
                "abc123",
                "--expected-stack-path",
                "infra/environments/test",
                "--expected-run-id",
                "42",
                "--expected-terraform-version",
                "1.9.0",
            )
            self.assertEqual(code, 1)
            self.assertIn("planSha256", stderr)

    def test_terraform_workflow_publishes_and_reuses_immutable_plan(self) -> None:
        workflow = TERRAFORM_WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("terraform show -no-color tfplan > tfplan.txt", workflow)
        self.assertIn("terraform show -json tfplan > tfplan.json", workflow)
        self.assertIn("scripts/terraform_plan_guard.py analyze", workflow)
        self.assertIn("scripts/terraform_plan_guard.py record", workflow)
        self.assertIn("scripts/terraform_plan_guard.py verify", workflow)
        self.assertIn("tfplan-${{ github.sha }}-${{ github.run_id }}", workflow)
        self.assertIn("retention-days: 14", workflow)
        self.assertIn("environment:\n      name: test", workflow)
        self.assertIn("terraform apply -auto-approve -lock-timeout=120s tfplan", workflow)

    def test_application_deploy_separates_plan_and_apply(self) -> None:
        workflow = DEPLOY_WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("application-plan:", workflow)
        self.assertIn("application-apply-and-publish:", workflow)
        self.assertIn("needs: application-plan", workflow)
        self.assertIn("agentcore-tfplan-${{ github.sha }}-${{ github.run_id }}", workflow)
        self.assertIn("scripts/terraform_plan_guard.py analyze", workflow)
        self.assertIn("scripts/terraform_plan_guard.py verify", workflow)
        self.assertNotIn(
            "terraform plan \\\n            -lock-timeout=60s \\\n            -var=\"enable_agentcore_control_plane=true\" \\\n            -var=\"agentcore_image_tag=${{ steps.tfout.outputs.resolved_image_tag }}\" \\\n            -var=\"agent_runtime_endpoint_name=${{ inputs.endpoint_name }}\" \\\n            -out=tfplan-agentcore-control-plane\n\n          terraform apply",
            workflow,
        )

    def test_quality_workflow_compiles_plan_guard(self) -> None:
        workflow = QUALITY_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("scripts/terraform_plan_guard.py", workflow)


if __name__ == "__main__":
    unittest.main()
