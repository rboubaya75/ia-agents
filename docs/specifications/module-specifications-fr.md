# Spécifications modules — WildRydes Secure AgentCore V1

**Version :** 1.1 — à réaligner avec ADR-0002  
**Périmètre :** environnement `test`  
**Branche par défaut phase test :** `migration/secure-agentcore-v1`  
**Branche future prod :** `main`

---

## Note de cadrage

Ce document était initialement aligné avec une architecture `API Gateway -> Lambda Facade -> AgentCore Runtime`.

La décision d’architecture corrigée est documentée dans :

```text
docs/adr/ADR-0002-agentcore-gateway-first-with-api-gateway.md
```

La cible V1 corrigée conserve Amazon API Gateway comme ingress web externe et place Amazon Bedrock AgentCore Gateway au centre du chemin agentique.

Chemin utilisateur nominal :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
  -> AgentCore Gateway
  -> HTTP Target: AgentCore Runtime
```

Chemin tools nominal :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP endpoint
  -> Lambda / API Gateway REST API / OpenAPI tools
  -> DynamoDB
```

La Lambda Agent Invocation Facade n’est plus un module nominal. Elle doit être considérée comme legacy/fallback uniquement si un spike P0 démontre qu’un besoin d’identité, d’audit ou de quota n’est pas couvert par API Gateway + AgentCore Gateway.

---

## Catalogue cible à implémenter

| Domaine | Module cible | Statut |
|---|---|---|
| Identity | `cognito_web_auth` | V1 |
| Frontend | `frontend_static_site` | V1 |
| Web ingress | `api_gateway_web_ingress` | V1 |
| AgentCore | `agentcore_gateway` | V1 |
| AgentCore | `agentcore_gateway_http_runtime_target` | V1 P0 |
| AgentCore | `agentcore_gateway_mcp_tools_target` | V1 |
| Agent packaging | `ecr_agent` | V1 |
| AgentCore | `agentcore_runtime` | V1 |
| AgentCore | `agentcore_memory` | V1 |
| Tools | `lambda_trip_tools` | V1 |
| Tools option | `api_gateway_trip_tools_optional` | Option |
| Data | `dynamodb_trips` | V1 |
| Configuration | `secrets_manager_app` | V1 |
| IAM | `iam_api_gateway_integration_role` | Si requis |
| IAM | `iam_runtime_role` | V1 |
| IAM | `iam_gateway_role` | V1 |
| IAM | `iam_trip_tools_role` | V1 |
| Observability | `observability` | V1 |
| Cost | `budgets` | V1 |
| Legacy | `lambda_agent_facade` | Fallback uniquement |

---

## Critères de mise à jour du document

La prochaine révision complète de ce fichier doit :

1. retirer `lambda_agent_facade` du catalogue nominal ;
2. ajouter `api_gateway_web_ingress` ;
3. ajouter les modules AgentCore Gateway targets ;
4. décrire les outputs `gateway_url`, `runtime_target_id`, `mcp_target_ids` ;
5. aligner les tests sur `API Gateway -> Gateway -> Runtime` et `Runtime -> Gateway -> tools` ;
6. conserver `VITE_API_BASE_URL` pointant vers Amazon API Gateway ;
7. documenter la Lambda Facade uniquement comme fallback ADR-driven ;
8. mettre à jour le workflow applicatif pour remplacer l’activation façade par l’activation Gateway/targets.
