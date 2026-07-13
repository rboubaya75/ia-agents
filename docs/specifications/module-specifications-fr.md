# Spécifications modules — WildRydes Secure AgentCore V1

- **Version :** 3.0
- **Date :** 2026-07-13
- **Périmètre :** environnement `test`
- **Branche :** `migration/secure-agentcore-v1`
- **Architecture :** ADR-0005

## 1. Architecture

```text
Browser
  -> API Gateway JWT
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
  -> AgentCore Gateway MCP AWS_IAM
  -> Trip Tools Lambda
  -> DynamoDB
```

## 2. Catalogue

| Domaine | Module / ressource | Statut V1 |
|---|---|---|
| Identity | `cognito_web_auth` | implémenté |
| Frontend | `frontend_static_site` | implémenté et durci |
| Ingress | `api_gateway_agent_ingress` | implémenté |
| Security boundary | `agent_api_facade` | implémenté |
| ECR | `ecr_container_repository` | implémenté |
| Runtime | `aws_bedrockagentcore_agent_runtime` | IAM-only implémenté |
| Runtime policy | `aws_bedrockagentcore_resource_policy.agent_runtime_invocation_boundary` | implémenté |
| Memory | `aws_bedrockagentcore_memory` | implémenté |
| MCP Gateway | `aws_bedrockagentcore_gateway.tools_mcp` | implémenté |
| MCP policy | `tools_gateway_invocation_boundary` | implémenté |
| Tool target | `aws_bedrockagentcore_gateway_target.trip_tools` | implémenté |
| Tool backend | `trip_tools_lambda` | implémenté |
| Data | `dynamodb_trips` | implémenté |
| Tests | `tests/unit` | implémenté |
| CI qualité | `test-application-quality.yml` | implémenté |

## 3. API Gateway

- route : `POST /agent/invoke` ;
- authorizer : JWT Cognito ;
- intégration : Lambda AWS proxy payload 2.0 ;
- CORS : domaine CloudFront uniquement ;
- throttling : 5 req/s, burst 10 ;
- access logs : structurés et sans données sensibles.

## 4. Lambda Security Facade

Inputs acceptés :

```text
prompt
sessionId
```

Claims requis :

```text
token_use=access
client_id=<web-client-id>
sub=<actor-id>
```

Output interne :

```text
prompt
sessionId
trustedIdentity.actorId
```

Configuration : Python 3.12 ARM64, 256 MiB, timeout 28 s, concurrence 5.

## 5. Runtime

- image `linux/arm64` Python 3.12 ;
- modèle Claude Haiku 4.5 EU ;
- IAM-only ;
- resource policy limitée au rôle façade ;
- Memory isolée ;
- client MCP SigV4 ;
- tools MCP obligatoires en V1 ;
- logs hashés.

## 6. Gateway MCP

- authorizer `AWS_IAM` ;
- principal autorisé : rôle Runtime ;
- protocol MCP ;
- target Lambda avec `gateway_iam_role {}` ;
- rôle Gateway autorisé uniquement à invoquer la Lambda Trips.

## 7. Trip Tools Lambda

Tools :

```text
create_trip
get_trips
get_trip
update_trip
```

IAM : `GetItem`, `PutItem`, `Query`, `UpdateItem` sur la table exacte.

Validation : identifiants, tailles, dates ISO, ordre des dates, champs allowlistés et conditions d’existence.

## 8. Frontend

- S3 privé ;
- CloudFront OAC ;
- CSP ;
- HSTS ;
- anti-framing ;
- nosniff ;
- Referrer-Policy ;
- Permissions-Policy ;
- variable nominale `VITE_AGENT_INVOKE_URL`.

## 9. Outputs obligatoires

```text
service_url
agent_invoke_url
agent_api_facade_function_name
agent_api_facade_role_arn
agent_runtime_arn
agentcore_memory_id
agentcore_gateway_mcp_url
agentcore_trip_tools_target_id
trip_tools_lambda_function_name
secure_facade_ready
```

## 10. Validation

La conformité finale exige : qualité CI verte, Terraform fmt/validate/plan vert, déploiement full, smoke tests JWT/CORS, Runtime direct refusé, Memory A/B isolée, quatre tools MCP et logs redacted.
