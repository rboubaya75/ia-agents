#!/usr/bin/env python3
"""Idempotently configure the V1 AgentCore user-preference memory strategy.

The AWS provider currently provisions the Memory resource but does not expose its
``MemoryStrategies`` property. This helper is invoked by Terraform through a
``terraform_data`` provisioner so the provider gap remains explicit, auditable,
and fail-closed during the reviewed apply.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from typing import Any, Protocol

import boto3

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


def strategy_is_compliant(strategy: dict[str, Any], namespace_template: str) -> bool:
    templates = strategy.get("namespaceTemplates") or []
    return templates == [namespace_template]


def wait_until_active(
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


def ensure_strategy(
    client: MemoryControlClient,
    memory_id: str,
    strategy_name: str,
    namespace_template: str,
    timeout_seconds: int,
) -> str:
    memory = wait_until_active(client, memory_id, timeout_seconds)
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

    memory = wait_until_active(client, memory_id, timeout_seconds)
    matches = matching_strategies(memory, strategy_name)
    if len(matches) != 1 or not strategy_is_compliant(matches[0], namespace_template):
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
    memory = wait_until_active(client, memory_id, timeout_seconds)
    matches = matching_strategies(memory, strategy_name)
    if len(matches) != 1 or not strategy_is_compliant(matches[0], namespace_template):
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
        strategy_name = validate_strategy_name(args.strategy_name)
        namespace_template = validate_namespace_template(args.namespace_template)
        if args.timeout_seconds < 10 or args.timeout_seconds > 900:
            raise ValueError("timeout-seconds must be between 10 and 900")
        client = boto3.client("bedrock-agentcore-control", region_name=args.region)
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
