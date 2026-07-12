# Spécifications modules — WildRydes Secure AgentCore V1

- **Version :** 2.0
- **Date :** 2026-07-12
- **Périmètre :** environnement `test`
- **Branche par défaut :** `migration/secure-agentcore-v1`
- **Architecture de référence :** ADR-0004

## 1. Architecture cible

```text
Browser
  -> API Gateway HTTP API
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

Tools :

```text
Runtime
  -> AgentCore Gateway MCP
  -> targets tools
  -> DynamoDB / APIs métier
```

AgentCore Gateway ingress et Lambda Facade ne sont pas des composants nominaux.

## 2. Catalogue V1

| Domaine | Module / ressource | Statut | Responsabilité |
|---|---|---|---|
| Identity | `cognito_web_auth` | présent | User Pool, app client SPA, utilisateurs invités |
| Frontend | `frontend_static_site` | présent | S3 privé, CloudFront, OAC, SPA fallback |
| Web ingress | `api_gateway_agent_ingress` | à remédier | JWT, CORS, throttling, logs, proxy direct Runtime |
| ECR | `ecr_container_repository` | présent | image immutable, scan on push, lifecycle |
| Runtime | `aws_bedrockagentcore_agent_runtime` | présent | exécution `phase_4.py`, JWT natif |
| Runtime endpoint | `aws_bedrockagentcore_agent_runtime_endpoint` | présent | endpoint `default` |
| Memory | `aws_bedrockagentcore_memory` | présent | préférences utilisateur |
| Tools gateway | `aws_bedrockagentcore_gateway.tools_mcp` | présent, incomplet | endpoint MCP pour tools |
| MCP targets | `aws_bedrockagentcore_gateway_target` | à implémenter | target tool réel |
| Data | `dynamodb_trips` | présent | table trips SSE/PITR |
| IAM Runtime | `iam_agentcore_runtime.tf` / module historique | à durcir | permissions Runtime |
| IAM Gateway | `iam_agentcore_runtime.tf` | à durcir | permissions tools Gateway |
| Legacy | `agent_api_facade` | legacy | fallback uniquement avec ADR |
| Observability | ressources à compléter | à implémenter | logs, metrics, dashboards, alarms |
| RAG | aucune ressource nominale | hors V1 | future capability |

## 3. Spécification `api_gateway_agent_ingress`

### Inputs requis après remédiation

```text
name
jwt_issuer
jwt_audience
allowed_origins
runtime_direct_enabled
agentcore_runtime_invoke_url
tags
```

### Route

```text
POST /agent/invoke
```

### Auth

```text
JWT authorizer Cognito
```

### Intégration

```text
HTTP_PROXY -> AgentCore Runtime invoke URL
```

### CORS

```text
Origin: domaine CloudFront test
Methods: OPTIONS, POST
Headers:
  authorization
  content-type
  x-amzn-bedrock-agentcore-runtime-session-id
  x-correlation-id
```

### Outputs

```text
api_id
api_endpoint
execution_arn
stage_name
jwt_authorizer_id
agent_invoke_url
```

### Critères d’acceptation

- route active ;
- JWT invalide rejeté ;
- CORS valide ;
- headers Runtime transmis ;
- Runtime atteint ;
- logs sans token/prompt ;
- throttling configuré.

## 4. Spécification Runtime

### Variables

```text
AWS_REGION
AWS_DEFAULT_REGION
MODEL_ID
LOG_LEVEL
SESSION_DIR
ENABLE_RAG
MEMORY_ID
GATEWAY_URL
GATEWAY_AUTH_MODE
```

### Configuration JWT

```text
discovery_url = Cognito OIDC discovery
allowed_clients = Cognito web client ID
token_use = access
request_header_allowlist = Authorization
```

### Contrat

- `prompt` obligatoire ;
- `sessionId` 33+ caractères ;
- identité dérivée du JWT ;
- champs identité client-side rejetés ;
- logs hashés ;
- modèle configurable ;
- Memory isolée ;
- tools allowlistés.

## 5. Spécification AgentCore Gateway MCP

### Configuration actuelle

```text
authorizer_type = AWS_IAM
protocol_type = MCP
```

### Cible

- mode d’auth unique et cohérent avec le client Runtime ;
- au moins un target tool ;
- IAM limité ;
- session timeout contrôlé ;
- test list tools ;
- test tool call ;
- identité serveur injectée ;
- refus cross-user.

## 6. Spécification ECR

- `image_tag_mutability = IMMUTABLE` ;
- `scan_on_push = true` ;
- chiffrement ;
- lifecycle untagged 7 jours ;
- conservation des dernières images ;
- build `linux/arm64` ;
- utilisateur conteneur non root.

## 7. Spécification DynamoDB

```text
PK = userId
SK = tripId
billing = PAY_PER_REQUEST
PITR = true
SSE = true
```

Chaque tool doit utiliser le `userId` serveur et ne jamais accepter une identité arbitraire.

## 8. Spécification CI/CD

### Infrastructure

- Gitleaks ;
- lockfile ;
- fmt ;
- validate ;
- plan ;
- apply manuel ;
- destroy confirmé.

### Application

- build image unique ;
- push ECR ;
- apply control plane ;
- validation outputs ;
- build frontend avec `VITE_AGENT_INVOKE_URL` ;
- publication S3 ;
- invalidation CloudFront ;
- smoke tests CORS/JWT/Runtime/tools.

## 9. Critères globaux V1

- API Gateway endpoint nominal ;
- Runtime JWT final ;
- AgentCore Gateway uniquement tools ;
- Claude Haiku 4.5 streaming/tools ;
- Memory isolée ;
- tool MCP réel ;
- IAM least privilege ;
- logs redacted ;
- Terraform validate/plan ;
- frontend lint/build ;
- smoke test navigateur ;
- documentation alignée.
