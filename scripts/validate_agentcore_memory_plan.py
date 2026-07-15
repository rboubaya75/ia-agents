#!/usr/bin/env python3
"""Validate that a Terraform plan really covers the AgentCore Memory V1 path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REQUIRED_PLANNED_ADDRESSES = {
    "aws_bedrockagentcore_memory.agent[0]",
    "terraform_data.agentcore_memory_preferences_strategy[0]",
    "terraform_data.agentcore_memory_preferences_verification[0]",
    "aws_bedrockagentcore_agent_runtime.agent[0]",
}
REQUIRED_CHANGED_ADDRESSES = {
    "terraform_data.agentcore_memory_preferences_strategy[0]",
    "terraform_data.agentcore_memory_preferences_verification[0]",
}


def module_resource_addresses(module: dict[str, Any] | None) -> set[str]:
    if not isinstance(module, dict):
        return set()
    addresses = {
        str(resource.get("address"))
        for resource in module.get("resources", [])
        if isinstance(resource, dict) and resource.get("address")
    }
    for child in module.get("child_modules", []) or []:
        addresses.update(module_resource_addresses(child))
    return addresses


def validate_plan(plan: dict[str, Any]) -> None:
    planned_values = plan.get("planned_values")
    root_module = (
        planned_values.get("root_module")
        if isinstance(planned_values, dict)
        else None
    )
    planned_addresses = module_resource_addresses(root_module)
    missing_planned = sorted(REQUIRED_PLANNED_ADDRESSES - planned_addresses)
    if missing_planned:
        raise RuntimeError(
            "AgentCore Memory resources are absent from planned values: "
            + ", ".join(missing_planned)
        )

    changes = {
        str(change.get("address")): change
        for change in plan.get("resource_changes", []) or []
        if isinstance(change, dict) and change.get("address")
    }
    missing_changes = sorted(REQUIRED_CHANGED_ADDRESSES - changes.keys())
    if missing_changes:
        raise RuntimeError(
            "AgentCore Memory deployment checks are absent from resource changes: "
            + ", ".join(missing_changes)
        )

    for address in sorted(REQUIRED_CHANGED_ADDRESSES):
        change = changes[address].get("change")
        actions = change.get("actions", []) if isinstance(change, dict) else []
        if "create" not in actions:
            raise RuntimeError(
                f"{address} must be created or replaced for the PR deployment revision; "
                f"actions={actions}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-json", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        with args.plan_json.open(encoding="utf-8") as stream:
            plan = json.load(stream)
        if not isinstance(plan, dict):
            raise RuntimeError("Terraform plan JSON must be an object")
        validate_plan(plan)
        print(
            json.dumps(
                {
                    "event": "agentcore_memory_plan_validated",
                    "required_planned_resources": len(REQUIRED_PLANNED_ADDRESSES),
                    "required_changed_resources": len(REQUIRED_CHANGED_ADDRESSES),
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "event": "agentcore_memory_plan_validation_failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
