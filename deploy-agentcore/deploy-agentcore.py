"""Legacy workshop deployment script.

Disabled for Secure AgentCore V1. Provisioning must be implemented with
Terraform modules and environment stacks. This guard prevents accidental use of
imperative lab deployment code during the migration.
"""

from __future__ import annotations


LEGACY_ERROR = (
    "deploy-agentcore/deploy-agentcore.py is legacy workshop code and must not "
    "be used for Secure AgentCore V1. Use Terraform-managed deployment."
)


def main() -> None:
    raise RuntimeError(LEGACY_ERROR)


if __name__ == "__main__":
    main()
