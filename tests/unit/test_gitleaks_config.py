import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
IGNORE = (ROOT / ".gitleaksignore").read_text(encoding="utf-8")

COGNITO_FINGERPRINT = (
    "47f4474af00e1316d106a2223660bec48e1e0e53:"
    "infra/modules/cognito_web_auth/main.tf:"
    "hashicorp-tf-password:51"
)


class GitleaksConfigTests(unittest.TestCase):
    def test_no_global_allowlist_masks_repository_files(self) -> None:
        self.assertNotIn("[allowlist]", CONFIG)
        self.assertNotIn("[[allowlists]]", CONFIG)

    def test_historical_cognito_finding_is_ignored_exactly_once(self) -> None:
        entries = [
            line.strip()
            for line in IGNORE.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertEqual(entries.count(COGNITO_FINGERPRINT), 1)

    def test_no_broad_cognito_path_ignore_exists(self) -> None:
        entries = [
            line.strip()
            for line in IGNORE.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        self.assertNotIn("infra/modules/cognito_web_auth/main.tf", entries)
        self.assertNotIn("hashicorp-tf-password", entries)


if __name__ == "__main__":
    unittest.main()
