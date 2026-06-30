"""Legacy workshop runtime deployment script.

Disabled for Secure AgentCore V1. Runtime deployment must be managed by
Terraform and must use the V1 runtime image and phase_4 entrypoint.
"""

from __future__ import annotations


LEGACY_ERROR = (
    "deploy-agentcore/deploy-runtime.py is legacy workshop code and must not be "
    "used for Secure AgentCore V1. Use Terraform-managed runtime deployment."
)


def main() -> None:
    raise RuntimeError(LEGACY_ERROR)


if __name__ == "__main__":
    main()
