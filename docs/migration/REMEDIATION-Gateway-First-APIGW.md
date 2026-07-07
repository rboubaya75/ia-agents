# Remédiation — Gateway-first avec Amazon API Gateway conservé

## Objectif

Aligner le repo WildRydes sur la cible corrigée :

```text
Browser -> Amazon API Gateway HTTP API -> AgentCore Gateway -> HTTP Target Runtime
Runtime -> AgentCore Gateway MCP -> Lambda/API Gateway REST/OpenAPI tools -> DynamoDB
```

La Lambda Facade n’est plus le chemin nominal.

---

## P0 — Validation d’architecture

1. Valider l’intégration Amazon API Gateway HTTP API vers AgentCore Gateway.
2. Valider l’authorizer AgentCore Gateway retenu.
3. Valider la transmission ou reconstruction de `actorId = Cognito sub`.
4. Valider AgentCore Gateway -> HTTP Target Runtime.
5. Valider Runtime -> AgentCore Gateway MCP -> tool minimal.
6. Valider les tests négatifs d’identité.
7. Valider la redaction logs.

Livrable P0 : un rapport court avec la décision définitive sur le contrat d’identité et d’invocation.

---

## P1 — Documentation

- Mettre à jour `README.md`.
- Mettre à jour `docs/hld/HLD-WildRydes-Agentic-AI-FR.md`.
- Mettre à jour `docs/lld/LLD-WildRydes-Agentic-AI-FR.md`.
- Ajouter `docs/adr/ADR-0002-agentcore-gateway-first-with-api-gateway.md`.
- Conserver les anciens éléments Lambda Facade en legacy/fallback uniquement.

---

## P2 — Terraform

Ajouter ou renommer les modules :

- `api_gateway_web_ingress` ;
- `agentcore_gateway` ;
- `agentcore_gateway_http_runtime_target` ;
- `agentcore_gateway_mcp_tools_target` ;
- `agentcore_memory` ;
- `agentcore_runtime` ;
- `lambda_trip_tools` ou `api_gateway_trip_tools_optional` ;
- `iam_api_gateway_integration_role` si requis ;
- `iam_gateway_role` ;
- `iam_runtime_role` ;
- `iam_trip_tools_role`.

Déprécier ou isoler :

- `lambda_agent_facade` ;
- `iam_facade_role` ;
- tout pipeline `activate_facade`.

---

## P3 — Runtime

Mettre à jour le déploiement Runtime pour injecter :

```text
AWS_REGION
MODEL_ID
MEMORY_ID
GATEWAY_URL
GATEWAY_AUTH_MODE
SECRET_NAME
LOG_LEVEL
ENABLE_RAG=false
```

Corriger `phase_4.py` pour :

- supprimer tout fallback `sessionId` comme identité ;
- rejeter `actorId`, `userId`, `tenantId`, `trustedIdentity` client-side ;
- utiliser `actorId = Cognito sub` depuis le contrat validé ;
- utiliser `travel/{actorId}/preferences` pour Memory ;
- appeler les tools via AgentCore Gateway MCP.

---

## P4 — Pipeline GitHub Actions

Modifier `.github/workflows/test-application-deploy.yml` :

- supprimer ou déprécier `activate_facade` ;
- ajouter création/mise à jour AgentCore Gateway ;
- ajouter création/mise à jour HTTP Target Runtime ;
- ajouter création/mise à jour MCP Targets tools ;
- injecter `MEMORY_ID` et `GATEWAY_URL` dans Runtime ;
- garder `VITE_API_BASE_URL` pointant vers Amazon API Gateway ;
- ajouter gates :
  - API Gateway -> Gateway -> Runtime ;
  - Runtime -> Gateway -> tool ;
  - negative identity tests ;
  - log redaction tests.

---

## P5 — Tests d’acceptation

Tests obligatoires :

- sans JWT => rejet ;
- JWT invalide => rejet ;
- mauvais audience => rejet ;
- `actorId` dans body => rejet ;
- `userId` dans body => rejet ;
- `trustedIdentity` dans body => rejet ;
- Runtime sans identité de confiance => rejet ;
- User A ne lit pas les trips de User B ;
- User A ne lit pas la Memory de User B ;
- aucun JWT, secret, prompt brut, actorId brut ou sessionId brut dans les logs.

---

## P6 — Critère de sortie

La remédiation est terminée quand :

- Amazon API Gateway est le seul endpoint public appelé par le frontend ;
- AgentCore Gateway est visible en console ;
- AgentCore Gateway a un HTTP Target Runtime ;
- AgentCore Gateway a au moins un MCP Target tool ;
- Runtime utilise Memory et Gateway avec des variables non vides ;
- Lambda Facade n’est plus dans le chemin nominal ;
- les gates end-to-end et sécurité passent.
