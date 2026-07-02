#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

READY = "READY"
FAILED = {"CREATE_FAILED", "UPDATE_FAILED", "DELETING"}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--image-uri", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--endpoint-name", default="default")
    parser.add_argument("--wait-seconds", type=int, default=900)
    return parser.parse_args()


def find_runtime(client: Any, name: str) -> Optional[Dict[str, Any]]:
    token = None
    while True:
        request: Dict[str, Any] = {"maxResults": 50}
        if token:
            request["nextToken"] = token
        response = client.list_agent_runtimes(**request)
        for runtime in response.get("agentRuntimes", []):
            if runtime.get("agentRuntimeName") == name:
                return runtime
        token = response.get("nextToken")
        if not token:
            return None


def wait_runtime(client: Any, runtime_id: str, wait_seconds: int) -> Dict[str, Any]:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        runtime = client.get_agent_runtime(agentRuntimeId=runtime_id)
        status = runtime.get("status")
        print(f"runtime_status={status}")
        if status == READY:
            return runtime
        if status in FAILED:
            raise RuntimeError(json.dumps(runtime, default=str))
        time.sleep(15)
    raise TimeoutError(f"Runtime {runtime_id} did not become READY")


def request_payload(options: argparse.Namespace) -> Dict[str, Any]:
    return {
        "agentRuntimeArtifact": {"containerConfiguration": {"containerUri": options.image_uri}},
        "roleArn": options.role_arn,
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "protocolConfiguration": {"serverProtocol": "HTTP"},
        "environmentVariables": {
            "AWS_REGION": options.region,
            "AWS_DEFAULT_REGION": options.region,
            "MODEL_ID": options.model_id,
            "LOG_LEVEL": "INFO",
            "SESSION_DIR": "/tmp/sessions",
            "MEMORY_ID": "",
            "GATEWAY_URL": "",
            "CLIENT_ID": "",
            "TOKEN_URL": "",
            "SCOPE_STRING": "",
            "GUARDRAILS_ID": "",
            "GUARDRAILS_VERSION": "1",
        },
        "description": "Secure WildRydes AgentCore Runtime managed by the test deployment workflow.",
    }


def deploy_runtime(client: Any, options: argparse.Namespace) -> Dict[str, Any]:
    payload = request_payload(options)
    existing = find_runtime(client, options.name)
    if existing:
        runtime_id = existing["agentRuntimeId"]
        print(f"Updating runtime {options.name} ({runtime_id})")
        client.update_agent_runtime(agentRuntimeId=runtime_id, **payload)
    else:
        print(f"Creating runtime {options.name}")
        response = client.create_agent_runtime(
            agentRuntimeName=options.name,
            tags={"Project": "wildrydes", "Environment": "test", "ManagedBy": "GitHubActions"},
            **payload,
        )
        runtime_id = response["agentRuntimeId"]
    return wait_runtime(client, runtime_id, options.wait_seconds)


def find_endpoint(client: Any, runtime_id: str, endpoint_name: str) -> Optional[Dict[str, Any]]:
    response = client.list_agent_runtime_endpoints(agentRuntimeId=runtime_id, maxResults=50)
    for endpoint in response.get("runtimeEndpoints", []):
        if endpoint.get("name") == endpoint_name:
            return endpoint
    return None


def wait_endpoint(client: Any, runtime_id: str, endpoint_name: str, wait_seconds: int) -> Dict[str, Any]:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        endpoint = client.get_agent_runtime_endpoint(agentRuntimeId=runtime_id, endpointName=endpoint_name)
        status = endpoint.get("status")
        print(f"endpoint_status={status}")
        if status == READY:
            return endpoint
        if status in FAILED:
            raise RuntimeError(json.dumps(endpoint, default=str))
        time.sleep(15)
    raise TimeoutError(f"Endpoint {endpoint_name} did not become READY")


def ensure_endpoint(client: Any, runtime: Dict[str, Any], options: argparse.Namespace) -> Dict[str, Any]:
    runtime_id = runtime["agentRuntimeId"]
    version = runtime["agentRuntimeVersion"]
    if find_endpoint(client, runtime_id, options.endpoint_name):
        print(f"Updating endpoint {options.endpoint_name}")
        client.update_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            endpointName=options.endpoint_name,
            agentRuntimeVersion=version,
        )
    else:
        print(f"Creating endpoint {options.endpoint_name}")
        client.create_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            name=options.endpoint_name,
            agentRuntimeVersion=version,
        )
    return wait_endpoint(client, runtime_id, options.endpoint_name, options.wait_seconds)


def output(values: Dict[str, str]) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    options = args()
    client = boto3.client("bedrock-agentcore-control", region_name=options.region)
    try:
        runtime = deploy_runtime(client, options)
        endpoint = ensure_endpoint(client, runtime, options)
    except (ClientError, RuntimeError, TimeoutError) as error:
        print(str(error), file=sys.stderr)
        return 1

    values = {
        "runtime_id": runtime["agentRuntimeId"],
        "runtime_arn": runtime["agentRuntimeArn"],
        "runtime_version": runtime["agentRuntimeVersion"],
        "endpoint_arn": endpoint["agentRuntimeEndpointArn"],
        "endpoint_name": endpoint["name"],
    }
    output(values)
    print(json.dumps(values, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
