#!/usr/bin/env python3
"""Run redacted V1 negative-security probes against the test ingress.

The runner never writes JWTs, request bodies, prompts, actor identifiers, or raw
AWS errors to its evidence file. Authenticated probes read tokens only from
environment variables so they do not appear in command-line arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib import error, parse, request

FORBIDDEN_FIELDS: tuple[tuple[str, Any], ...] = (
    ("actorId", "security-probe-actor"),
    ("userId", "security-probe-user"),
    ("trustedIdentity", {"actorId": "security-probe-actor"}),
    ("requestId", "security-probe-request"),
    ("deadlineEpochMs", 9_999_999_999_999),
    ("groups", ["security-probe-group"]),
    ("modelOverride", "security-probe-model"),
    ("systemPrompt", "security-probe-system"),
    ("toolName", "security-probe-tool"),
)
ACCESS_DENIED_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "ForbiddenException",
    "UnauthorizedException",
}


class RuntimeClient(Protocol):
    def invoke_agent_runtime(self, **kwargs: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class ProbeResult:
    case: str
    level: str
    status: str
    observed_status: int | None = None
    request_id_hash: str | None = None
    cors_allow_origin: str | None = None
    detail: str | None = None


Transport = Callable[[str, str, Mapping[str, str], bytes | None, float], HttpResponse]


def safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def catalog() -> list[dict[str, str]]:
    cases = [
        ("http_no_jwt", "E2E HTTP", "401/403"),
        ("http_malformed_jwt", "E2E HTTP", "401/403"),
        ("http_id_token", "E2E HTTP", "401/403"),
        ("cors_allowed_preflight", "E2E CORS", "origin CloudFront autorisée"),
        ("cors_forbidden_preflight", "E2E CORS", "origine arbitraire non autorisée"),
        ("runtime_direct_invoke_denied", "E2E IAM", "AccessDenied"),
    ]
    cases.extend(
        (f"inject_{field}", "E2E HTTP", "400") for field, _ in FORBIDDEN_FIELDS
    )
    return [
        {"case": case, "level": level, "expected": expected}
        for case, level, expected in cases
    ]


def _lower_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _bounded_body(stream: Any, limit: int = 8192) -> bytes:
    data = stream.read(limit + 1)
    return data[:limit]


def urllib_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
) -> HttpResponse:
    req = request.Request(url=url, data=body, headers=dict(headers), method=method)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return HttpResponse(
                status=int(response.status),
                headers=_lower_headers(response.headers),
                body=_bounded_body(response),
            )
    except error.HTTPError as exc:
        return HttpResponse(
            status=int(exc.code),
            headers=_lower_headers(exc.headers or {}),
            body=_bounded_body(exc),
        )
    except (error.URLError, TimeoutError, OSError):
        # Keep network failure evidence deterministic and redacted. Status 0 can
        # never satisfy an HTTP contract, so the corresponding probe is a FAIL.
        return HttpResponse(status=0, headers={}, body=b"")


def _request_id_hash(body: bytes) -> str | None:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    request_id = value.get("requestId")
    return safe_hash(request_id) if isinstance(request_id, str) and request_id else None


def _base_body() -> dict[str, Any]:
    return {
        "prompt": "security contract probe",
        "sessionId": str(uuid.uuid4()),
        "operationId": str(uuid.uuid4()),
    }


def _post(
    transport: Transport,
    api_url: str,
    token: str | None,
    payload: Mapping[str, Any],
    origin: str | None,
    timeout: float,
) -> HttpResponse:
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    if origin:
        headers["origin"] = origin
    return transport(
        "POST",
        api_url,
        headers,
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        timeout,
    )


def _result_for_status(
    case: str,
    level: str,
    response: HttpResponse,
    expected: Iterable[int],
    detail: str,
) -> ProbeResult:
    expected_set = set(expected)
    return ProbeResult(
        case=case,
        level=level,
        status="PASS" if response.status in expected_set else "FAIL",
        observed_status=response.status,
        request_id_hash=_request_id_hash(response.body),
        detail=detail,
    )


def run_http_probes(
    *,
    api_url: str,
    allowed_origin: str,
    forbidden_origin: str,
    access_token: str | None,
    id_token: str | None,
    timeout: float = 15.0,
    require_authenticated_cases: bool = False,
    require_id_token: bool = False,
    transport: Transport = urllib_transport,
) -> list[ProbeResult]:
    parsed = parse.urlparse(api_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("api_url must be an absolute HTTPS URL")
    for name, origin in (
        ("allowed_origin", allowed_origin),
        ("forbidden_origin", forbidden_origin),
    ):
        origin_parts = parse.urlparse(origin)
        if (
            origin_parts.scheme != "https"
            or not origin_parts.netloc
            or origin_parts.path not in ("", "/")
        ):
            raise ValueError(f"{name} must be an HTTPS origin without a path")

    if require_authenticated_cases and not access_token:
        raise ValueError(
            "Authenticated cases require the access-token environment variable"
        )
    if require_id_token and not id_token:
        raise ValueError(
            "The ID-token rejection case requires the ID-token environment variable"
        )

    results: list[ProbeResult] = []
    payload = _base_body()
    results.append(
        _result_for_status(
            "http_no_jwt",
            "E2E HTTP",
            _post(transport, api_url, None, payload, None, timeout),
            {401, 403},
            "request without Authorization is rejected",
        )
    )
    results.append(
        _result_for_status(
            "http_malformed_jwt",
            "E2E HTTP",
            _post(transport, api_url, "not-a-jwt", payload, None, timeout),
            {401, 403},
            "malformed bearer token is rejected",
        )
    )

    preflight_headers = {
        "origin": allowed_origin,
        "access-control-request-method": "POST",
        "access-control-request-headers": "authorization,content-type",
    }
    allowed = transport("OPTIONS", api_url, preflight_headers, None, timeout)
    allowed_headers = _lower_headers(allowed.headers)
    allowed_value = allowed_headers.get("access-control-allow-origin")
    allowed_methods = allowed_headers.get("access-control-allow-methods", "")
    allowed_passed = (
        allowed.status in {200, 204}
        and allowed_value == allowed_origin
        and "POST" in allowed_methods.upper()
    )
    results.append(
        ProbeResult(
            case="cors_allowed_preflight",
            level="E2E CORS",
            status="PASS" if allowed_passed else "FAIL",
            observed_status=allowed.status,
            cors_allow_origin=allowed_value,
            detail="CloudFront origin must be echoed exactly and POST must be allowed",
        )
    )

    forbidden_headers = dict(preflight_headers)
    forbidden_headers["origin"] = forbidden_origin
    forbidden = transport("OPTIONS", api_url, forbidden_headers, None, timeout)
    forbidden_value = _lower_headers(forbidden.headers).get(
        "access-control-allow-origin"
    )
    forbidden_passed = forbidden_value not in {forbidden_origin, "*"}
    results.append(
        ProbeResult(
            case="cors_forbidden_preflight",
            level="E2E CORS",
            status="PASS" if forbidden_passed else "FAIL",
            observed_status=forbidden.status,
            cors_allow_origin=forbidden_value,
            detail="arbitrary origin must not be echoed or wildcarded",
        )
    )

    if id_token:
        results.append(
            _result_for_status(
                "http_id_token",
                "E2E HTTP",
                _post(transport, api_url, id_token, payload, allowed_origin, timeout),
                {401, 403},
                "Cognito ID token is not accepted as an access token",
            )
        )
    else:
        results.append(
            ProbeResult(
                case="http_id_token",
                level="E2E HTTP",
                status="SKIP",
                detail="ID-token environment variable not provided",
            )
        )

    if access_token:
        for field, value in FORBIDDEN_FIELDS:
            injected = _base_body()
            injected[field] = value
            results.append(
                _result_for_status(
                    f"inject_{field}",
                    "E2E HTTP",
                    _post(
                        transport,
                        api_url,
                        access_token,
                        injected,
                        allowed_origin,
                        timeout,
                    ),
                    {400},
                    "client-supplied identity or execution-control field is rejected",
                )
            )
    else:
        results.extend(
            ProbeResult(
                case=f"inject_{field}",
                level="E2E HTTP",
                status="SKIP",
                detail="access-token environment variable not provided",
            )
            for field, _ in FORBIDDEN_FIELDS
        )

    return results


def run_runtime_deny_probe(
    *,
    runtime_client: RuntimeClient,
    runtime_arn: str,
    endpoint_name: str,
) -> ProbeResult:
    if not runtime_arn:
        return ProbeResult(
            case="runtime_direct_invoke_denied",
            level="E2E IAM",
            status="SKIP",
            detail="Runtime ARN not provided",
        )
    try:
        runtime_client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            qualifier=endpoint_name,
            runtimeSessionId=str(uuid.uuid4()),
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(
                {
                    "prompt": "security contract probe",
                    "sessionId": str(uuid.uuid4()),
                    "operationId": str(uuid.uuid4()),
                },
                separators=(",", ":"),
            ).encode("utf-8"),
        )
    except Exception as exc:
        response = getattr(exc, "response", {})
        code = ""
        if isinstance(response, dict):
            error_value = response.get("Error", {})
            if isinstance(error_value, dict):
                code = str(error_value.get("Code", ""))
        return ProbeResult(
            case="runtime_direct_invoke_denied",
            level="E2E IAM",
            status="PASS" if code in ACCESS_DENIED_CODES else "FAIL",
            detail=(
                "Runtime resource policy denied the non-facade principal"
                if code in ACCESS_DENIED_CODES
                else "Runtime invocation failed with an unexpected safe error code"
            ),
        )
    return ProbeResult(
        case="runtime_direct_invoke_denied",
        level="E2E IAM",
        status="FAIL",
        detail="non-facade principal invoked the Runtime successfully",
    )


def build_evidence(
    *,
    results: list[ProbeResult],
    api_url: str,
    allowed_origin: str,
    code_sha: str,
) -> dict[str, Any]:
    parsed = parse.urlparse(api_url)
    counts = {
        name: sum(result.status == name for result in results)
        for name in ("PASS", "FAIL", "SKIP")
    }
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "codeSha": code_sha or "unknown",
        "target": {
            "apiHost": parsed.netloc,
            "apiPathHash": safe_hash(parsed.path or "/"),
            "allowedOrigin": allowed_origin,
        },
        "summary": {
            "total": len(results),
            **{key.lower(): value for key, value in counts.items()},
        },
        "results": [asdict(result) for result in results],
    }


def ensure_redacted(
    evidence: Mapping[str, Any], sensitive_values: Iterable[str]
) -> None:
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    for value in sensitive_values:
        if value and len(value) >= 16 and value in serialized:
            raise RuntimeError("Evidence contains sensitive authentication material")


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--api-url")
    parser.add_argument("--allowed-origin")
    parser.add_argument("--forbidden-origin", default="https://unauthorized.invalid")
    parser.add_argument("--access-token-env", default="V1_ACCESS_TOKEN")
    parser.add_argument("--id-token-env", default="V1_ID_TOKEN")
    parser.add_argument("--require-authenticated-cases", action="store_true")
    parser.add_argument("--require-id-token", action="store_true")
    parser.add_argument("--runtime-arn", default="")
    parser.add_argument("--runtime-endpoint", default="default")
    parser.add_argument("--require-runtime-deny", action="store_true")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "eu-west-3"))
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.catalog_only:
        write_json(
            args.output,
            {
                "schemaVersion": 1,
                "generatedAt": utc_now(),
                "status": "DEFINED",
                "cases": catalog(),
            },
        )
        return 0

    if not args.api_url or not args.allowed_origin:
        raise SystemExit(
            "--api-url and --allowed-origin are required outside --catalog-only"
        )

    access_token = os.getenv(args.access_token_env, "")
    id_token = os.getenv(args.id_token_env, "")
    results = run_http_probes(
        api_url=args.api_url,
        allowed_origin=args.allowed_origin,
        forbidden_origin=args.forbidden_origin,
        access_token=access_token or None,
        id_token=id_token or None,
        timeout=args.timeout,
        require_authenticated_cases=args.require_authenticated_cases,
        require_id_token=args.require_id_token,
    )

    if args.runtime_arn:
        try:
            import boto3
        except ImportError as exc:
            raise SystemExit("boto3 is required for the Runtime IAM probe") from exc
        runtime_client = boto3.client("bedrock-agentcore", region_name=args.region)
        results.append(
            run_runtime_deny_probe(
                runtime_client=runtime_client,
                runtime_arn=args.runtime_arn,
                endpoint_name=args.runtime_endpoint,
            )
        )
    else:
        results.append(
            ProbeResult(
                case="runtime_direct_invoke_denied",
                level="E2E IAM",
                status="SKIP",
                detail="Runtime ARN not provided",
            )
        )

    evidence = build_evidence(
        results=results,
        api_url=args.api_url,
        allowed_origin=args.allowed_origin,
        code_sha=os.getenv("GITHUB_SHA", "unknown"),
    )
    ensure_redacted(evidence, (access_token, id_token))
    write_json(args.output, evidence)

    failures = [result for result in results if result.status == "FAIL"]
    skips = [result for result in results if result.status == "SKIP"]
    if args.require_runtime_deny and any(
        result.case == "runtime_direct_invoke_denied" for result in skips
    ):
        failures.append(
            ProbeResult(
                case="runtime_direct_invoke_denied",
                level="E2E IAM",
                status="FAIL",
                detail="required Runtime IAM probe was skipped",
            )
        )
    print(
        json.dumps(
            {
                "event": "v1_security_negative_validation",
                "passed": sum(result.status == "PASS" for result in results),
                "failed": len(failures),
                "skipped": len(skips),
                "evidence": str(args.output),
            },
            separators=(",", ":"),
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
