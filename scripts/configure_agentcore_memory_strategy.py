#!/usr/bin/env python3
"""Idempotently configure the V1 AgentCore user-preference memory strategy.

The AWS provider currently provisions the Memory resource but does not expose its
``MemoryStrategies`` property. This helper is invoked by Terraform through
``terraform_data`` provisioners so the provider gap remains explicit, auditable,
and fail-closed during the reviewed apply.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
import re
import sys
import time
from typing import Any, Protocol

import boto3

EXPECTED_BOTO3_VERSION = "1.43.46"
EXPECTED_STRATEGY_TYPE = "USER_PREFERENCE"
EXPECTED_STRATEGY_STATUS = "ACTIVE"
STRATEGY_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
DEFAULT_DESCRIPTION = (
    "Extract durable travel preferences explicitly stated by authenticated users."
)


class MemoryControlClient(Protocol):
    def get_memory(self, **kwargs: Any) -> dict[str, Any]: ...

    def update_memory(self, **kwargs: Any) -> dict[str, Any]: ...


def emit(event: str, **details: Any) -> None:
    payload = {"event": event, **details}
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def aws_error_code(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return "unknown"
    error = response.get("Error")
    if not isinstance(error, dict):
        return "unknown"
    code = error.get("Code")
    return str(code) if code else "unknown"


def validate_sdk_version() -> None:
    try:
        installed = version("boto3")
    except PackageNotFoundError as exc:
        raise RuntimeError("boto3 is required for AgentCore Memory configuration") from exc
    if installed != EXPECTED_BOTO3_VERSION:
        raise RuntimeError(
            "AgentCore Memory configuration requires "
            f"boto3=={EXPECTED_BOTO3_VERSION}; found {installed}"
        )


def validate_client_contract(client: Any) -> None:
    """Fail before AWS calls if Botocore lacks the required Memory API fields."""

    service_model = getattr(getattr(client, "meta", None), "service_model", None)
    if service_model is None:
        raise RuntimeError("AgentCore control client exposes no Botocore service model")

    update_input = service_model.operation_model("UpdateMemory").input_shape
    strategies = update_input.members.get("memoryStrategies")
    if strategies is None:
        raise RuntimeError("Botocore UpdateMemory lacks memoryStrategies")
    add_list = strategies.members.get("addMemoryStrategies")
    modify_list = strategies.members.get("modifyMemoryStrategies")
    if add_list is None or modify_list is None:
        raise RuntimeError("Botocore UpdateMemory lacks strategy add/modify support")

    preference = add_list.member.members.get("userPreferenceMemoryStrategy")
    required_preference_fields = {"name", "description", "namespaceTemplates"}
    if preference is None or not required_preference_fields.issubset(preference.members):
        raise RuntimeError("Botocore lacks the required user preference strategy fields")

    required_modify_fields = {
        "memoryStrategyId",
        "description",
        "namespaceTemplates",
    }
    if not required_modify_fields.issubset(modify_list.member.members):
        raise RuntimeError("Botocore lacks the required strategy modification fields")

    get_output = service_model.operation_model("GetMemory").output_shape
    memory_shape = get_output.members.get("memory")
    strategy_list = memory_shape.members.get("strategies") if memory_shape else None
    strategy_shape = strategy_list.member if strategy_list is not None else None
    required_response_fields = {
        "strategyId",
        "name",
        "type",
        "status",
        "namespaceTemplates",
    }
    if strategy_shape is None or not required_response_fields.issubset(
        strategy_shape.members
    ):
        raise RuntimeError("Botocore GetMemory lacks required strategy status fields")


def validate_strategy_name(value: str) -> str:
    if not STRATEGY_NAME_PATTERN.fullmatch(value):
        raise ValueError(
            "strategy name must start with a letter and contain at most 48 "
            "letters, digits, or underscores"
        )
    return value


def validate_namespace_template(value: str) -> str:
    if not value.startswith("/"):
        raise ValueError("namespace template must start with '/'")
    if value.count("{actorId}") != 1:
        raise ValueError("namespace template must contain {actorId} exactly once")
    if ".." in value or len(value) > 256:
        raise ValueError("namespace template is invalid")
    return value


def memory_snapshot(client: MemoryControlClient, memory_id: str) -> dict[str, Any]:
    response = client.get_memory(memoryId=memory_id, view="full")
    memory = response.get("memory")
    if not isinstance(memory, dict):
        raise RuntimeError("AgentCore get_memory returned no memory object")
    return memory


def matching_strategies(memory: dict[str, Any], strategy_name: str) -> list[dict[str, Any]]:
    strategies = memory.get("strategies") or []
    if not isinstance(strategies, list):
        raise RuntimeError("AgentCore memory strategies response is invalid")
    return [
        strategy
        for strategy in strategies
        if isinstance(strategy, dict) and strategy.get("name") == strategy_name
    ]


def validate_strategy_type(strategy: dict[str, Any]) -> None:
    strategy_type = strategy.get("type")
    if strategy_type != EXPECTED_STRATEGY_TYPE:
        raise RuntimeError(
            "Existing AgentCore Memory strategy has unexpected type: "
            f"{strategy_type or 'unknown'}"
        )


def strategy_is_compliant(strategy: dict[str, Any], namespace_template: str) -> bool:
    return (
        strategy.get("type") == EXPECTED_STRATEGY_TYPE
        and strategy.get("status") == EXPECTED_STRATEGY_STATUS
        and strategy.get("description") == DEFAULT_DESCRIPTION
        and strategy.get("namespaceTemplates") == [namespace_template]
    )


def wait_until_memory_active(
    client: MemoryControlClient,
    memory_id: str,
    timeout_seconds: int,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        memory = memory_snapshot(client, memory_id)
        status = str(memory.get("status", "UNKNOWN"))
        if status == "ACTIVE":
            return memory
        if status == "FAILED":
            raise RuntimeError("AgentCore Memory entered FAILED state")
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for AgentCore Memory to become ACTIVE")
        time.sleep(poll_seconds)


def wait_until_strategy_active(
    client: MemoryControlClient,
    memory_id: str,
    strategy_name: str,
    timeout_seconds: int,
    poll_seconds: float = 2.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        memory = memory_snapshot(client, memory_id)
        memory_status = str(memory.get("status", "UNKNOWN"))
        if memory_status == "FAILED":
            raise RuntimeError("AgentCore Memory entered FAILED state")

        matches = matching_strategies(memory, strategy_name)
        if len(matches) > 1:
            raise RuntimeError(
                "Multiple AgentCore Memory strategies share the configured name"
            )
        if matches:
            strategy = matches[0]
            validate_strategy_type(strategy)
            status = str(strategy.get("status", "UNKNOWN"))
            if memory_status == "ACTIVE" and status == EXPECTED_STRATEGY_STATUS:
                return strategy
            if status == "FAILED":
                raise RuntimeError("AgentCore Memory strategy entered FAILED state")
            if status == "DELETING":
                raise RuntimeError("AgentCore Memory strategy is being deleted")

        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Timed out waiting for AgentCore Memory strategy to become ACTIVE"
            )
        time.sleep(poll_seconds)


def ensure_strategy(
    client: MemoryControlClient,
    memory_id: str,
    strategy_name: str,
    namespace_template: str,
    timeout_seconds: int,
) -> str:
    memory = wait_until_memory_active(client, memory_id, timeout_seconds)
    matches = matching_strategies(memory, strategy_name)
    if len(matches) > 1:
        raise RuntimeError("Multiple AgentCore Memory strategies share the configured name")

    if not matches:
        client.update_memory(
            memoryId=memory_id,
            memoryStrategies={
                "addMemoryStrategies": [
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": strategy_name,
                            "description": DEFAULT_DESCRIPTION,
                            "namespaceTemplates": [namespace_template],
                        }
                    }
                ]
            },
        )
        action = "added"
    else:
        strategy = matches[0]
        validate_strategy_type(strategy)
        if strategy.get("status") != EXPECTED_STRATEGY_STATUS:
            strategy = wait_until_strategy_active(
                client, memory_id, strategy_name, timeout_seconds
            )
        if strategy_is_compliant(strategy, namespace_template):
            emit(
                "agentcore_memory_strategy_compliant",
                action="unchanged",
                memory_id=memory_id,
                strategy_name=strategy_name,
                namespace_template=namespace_template,
            )
            return "unchanged"
        strategy_id = strategy.get("strategyId")
        if not isinstance(strategy_id, str) or not strategy_id:
            raise RuntimeError("Existing AgentCore Memory strategy has no strategyId")
        client.update_memory(
            memoryId=memory_id,
            memoryStrategies={
                "modifyMemoryStrategies": [
                    {
                        "memoryStrategyId": strategy_id,
                        "description": DEFAULT_DESCRIPTION,
                        "namespaceTemplates": [namespace_template],
                    }
                ]
            },
        )
        action = "modified"

    strategy = wait_until_strategy_active(
        client, memory_id, strategy_name, timeout_seconds
    )
    if not strategy_is_compliant(strategy, namespace_template):
        raise RuntimeError("AgentCore Memory strategy did not converge to the V1 contract")
    emit(
        "agentcore_memory_strategy_compliant",
        action=action,
        memory_id=memory_id,
        strategy_name=strategy_name,
        namespace_template=namespace_template,
    )
    return action


def check_strategy(
    client: MemoryControlClient,
    memory_id: str,
    strategy_name: str,
    namespace_template: str,
    timeout_seconds: int,
) -> None:
    strategy = wait_until_strategy_active(
        client, memory_id, strategy_name, timeout_seconds
    )
    if not strategy_is_compliant(strategy, namespace_template):
        raise RuntimeError("AgentCore Memory preference strategy is not compliant")
    emit(
        "agentcore_memory_strategy_compliant",
        action="checked",
        memory_id=memory_id,
        strategy_name=strategy_name,
        namespace_template=namespace_template,
    )


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("action", choices=("ensure", "check"))
    value.add_argument("--memory-id", required=True)
    value.add_argument("--strategy-name", required=True)
    value.add_argument("--namespace-template", required=True)
    value.add_argument("--region", required=True)
    value.add_argument("--timeout-seconds", type=int, default=300)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        validate_sdk_version()
        strategy_name = validate_strategy_name(args.strategy_name)
        namespace_template = validate_namespace_template(args.namespace_template)
        if args.timeout_seconds < 10 or args.timeout_seconds > 900:
            raise ValueError("timeout-seconds must be between 10 and 900")
        client = boto3.client("bedrock-agentcore-control", region_name=args.region)
        validate_client_contract(client)
        if args.action == "ensure":
            ensure_strategy(
                client,
                args.memory_id,
                strategy_name,
                namespace_template,
                args.timeout_seconds,
            )
        else:
            check_strategy(
                client,
                args.memory_id,
                strategy_name,
                namespace_template,
                args.timeout_seconds,
            )
        return 0
    except Exception as exc:  # pragma: no cover - exercised by CLI integration
        emit(
            "agentcore_memory_strategy_failed",
            error_type=type(exc).__name__,
            aws_error_code=aws_error_code(exc),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
