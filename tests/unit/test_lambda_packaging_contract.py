from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
FACADE_MAIN = ROOT / "infra" / "modules" / "agent_api_facade" / "main.tf"
FACADE_VARIABLES = ROOT / "infra" / "modules" / "agent_api_facade" / "variables.tf"
TRIP_TOOLS_MAIN = ROOT / "infra" / "modules" / "trip_tools_lambda" / "main.tf"
TRIP_TOOLS_VARIABLES = ROOT / "infra" / "modules" / "trip_tools_lambda" / "variables.tf"


class LambdaPackagingContractTests(unittest.TestCase):
    def test_lambda_archives_are_resources_for_multiphase_apply(self) -> None:
        facade = FACADE_MAIN.read_text(encoding="utf-8")
        trip_tools = TRIP_TOOLS_MAIN.read_text(encoding="utf-8")

        self.assertIn('resource "archive_file" "facade"', facade)
        self.assertIn('filename                       = archive_file.facade.output_path', facade)
        self.assertIn('source_code_hash               = archive_file.facade.output_base64sha256', facade)
        self.assertNotIn('data "archive_file" "facade"', facade)

        self.assertIn('resource "archive_file" "this"', trip_tools)
        self.assertIn('filename                       = archive_file.this.output_path', trip_tools)
        self.assertIn('source_code_hash               = archive_file.this.output_base64sha256', trip_tools)
        self.assertNotIn('data "archive_file" "this"', trip_tools)

    def test_reserved_concurrency_is_optional_by_default(self) -> None:
        for path in (FACADE_VARIABLES, TRIP_TOOLS_VARIABLES):
            with self.subTest(path=path):
                content = path.read_text(encoding="utf-8")
                section = content.split('variable "reserved_concurrent_executions"', 1)[1].split("\n}\n", 1)[0]
                self.assertIn("default     = null", section)
                self.assertIn("var.reserved_concurrent_executions == null ? true", section)
                self.assertIn("between 1 and 100", section)


if __name__ == "__main__":
    unittest.main()
