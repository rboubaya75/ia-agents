"""Legacy workshop utilities.

This file is intentionally neutralized for Secure AgentCore V1.

The original workshop version contained imperative AWS provisioning helpers,
hardcoded test credentials, sensitive token/secret logging, and broad IAM
permissions. Those patterns are not compatible with the Terraform-based V1
application landing zone.

Do not use this module for Secure AgentCore V1 deployments.
Use Terraform modules under infra/modules and environment stacks under
infra/environments/test instead.
"""

from __future__ import annotations

from typing import Any


LEGACY_ERROR = (
    "deploy-agentcore/utils.py is legacy workshop code and must not be used "
    "for Secure AgentCore V1. Use Terraform-managed modules instead."
)


def _blocked_legacy_call(*_: Any, **__: Any) -> None:
    """Fail fast if legacy imperative provisioning code is called."""
    raise RuntimeError(LEGACY_ERROR)


# Function names kept only to make accidental legacy calls fail explicitly.
setup_cognito_user_pool = _blocked_legacy_call
get_or_create_user_pool = _blocked_legacy_call
get_or_create_resource_server = _blocked_legacy_call
get_or_create_m2m_client = _blocked_legacy_call
get_token = _blocked_legacy_call
create_agentcore_role = _blocked_legacy_call
create_agentcore_gateway_role = _blocked_legacy_call
create_agentcore_gateway_role_s3_smithy = _blocked_legacy_call
create_gateway_lambda = _blocked_legacy_call
delete_gateway = _blocked_legacy_call
delete_all_gateways = _blocked_legacy_call
