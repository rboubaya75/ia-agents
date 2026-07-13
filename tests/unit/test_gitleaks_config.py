from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIG = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")


class GitleaksConfigTests(unittest.TestCase):
    def test_gitleaks_824_uses_singular_global_allowlist(self) -> None:
        self.assertIn("[allowlist]", CONFIG)
        self.assertNotIn("[[allowlists]]", CONFIG)

    def test_cognito_allowlist_is_narrowly_scoped(self) -> None:
        self.assertIn("infra/modules/cognito_web_auth/main\\.tf", CONFIG)
        self.assertIn(
            "ALLOW_(USER_PASSWORD|USER_SRP|ADMIN_USER_PASSWORD|REFRESH_TOKEN)_AUTH",
            CONFIG,
        )


if __name__ == "__main__":
    unittest.main()
