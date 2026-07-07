# LLD — WildRydes Agentic AI Application Landing Zone

**Version :** 2.0 — Gateway-first avec Amazon API Gateway conservé  
**Langue :** Français  
**Branche test par défaut :** `migration/secure-agentcore-v1`  
**Branche future prod :** `main`  
**Périmètre :** environnement `test`  
**IaC :** Terraform  
**CI/CD :** GitHub Actions avec OIDC  
**Runtime cible :** `phase_4.py`

---

## 1. Objectif

Ce LLD remplace le design **Lambda-Facade-first** par un design **Gateway-first avec Amazon API Gateway conservé**.

La cible nominale devient :

```text
Frontend React
  -> Amazon API Gateway HTTP API
  -> Amazon Bedrock AgentCore Gateway
  -> HTTP Target: AgentCore Runtime
```

Et pour les tools :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP endpoint
  -> MCP Targets: Lambda / API Gateway REST API / OpenAPI tools
  -> DynamoDB
```

La Lambda Agent Invocation Facade n’est plus une dépendance nominale. Elle peut être conservée temporairement comme fallback uniquement si un ADR explicite démontre qu’un besoin d’identité, d’audit ou de quota n’est pas couvert par les briques natives.

---

## 2. Structure repository cible

```text
ia-agents/
├── README.md
├── docs/
│   ├── hld/
│   ├── lld/
│   ├── adr/
│   ├── runbooks/
│   ├── specifications/
│   ├── migration/
│   └── legacy/
├── infra/
│   ├── environments/
│   │   └── test/
│   └── modules/
├── lambda/
│   └── trip_tools/
├── tests/
│   ├── integration/
│   ├── security/
│   ├── smoke/
│   └── latency/
├── scripts/
├── frontend/
├── deploy-agentcore/
└── .github/workflows/
```

Les dossiers legacy contenant l’ancienne Lambda Facade peuvent être conservés temporairement, mais ne doivent plus être appelés par le chemin nominal.

---

## 3. Modules Terraform cibles

```text
infra/modules/
├── cognito_web_auth/
├── frontend_static_site/
├── api_gateway_web_ingress/
├── agentcore_gateway/
├── agentcore_gateway_http_runtime_target/
├── agentcore_gateway_mcp_tools_target/
├── ecr_agent/
├── agentcore_runtime/
├── agentcore_memory/
├── lambda_trip_tools/
├── api_gateway_trip_tools_optional/
├── dynamodb_trips/
├── secrets_manager_app/
├── iam_api_gateway_integration_role/
├── iam_runtime_role/
├── iam_gateway_role/
├── iam_trip_tools_role/
├── observability/
├── budgets/
└── agent_rag_knowledge_base/
```

| Module | Responsabilité | Statut |
|---|---|---|
| `cognito_web_auth` | User Pool, app client SPA sans secret, groupes | V1 |
| `frontend_static_site` | S3 privé, CloudFront, OAC, SPA fallback | V1 |
| `api_gateway_web_ingress` | HTTP API externe, JWT authorizer, CORS, throttling | V1 |
| `agentcore_gateway` | AgentCore Gateway central | V1 |
| `agentcore_gateway_http_runtime_target` | HTTP target vers AgentCore Runtime | V1 P0 |
| `agentcore_gateway_mcp_tools_target` | MCP targets Lambda/OpenAPI/API Gateway REST | V1 |
| `ecr_agent` | Repository image Runtime | V1 |
| `agentcore_runtime` | Runtime containerisé `phase_4.py` | V1 |
| `agentcore_memory` | Memory preferences namespace `travel/{actorId}/preferences` | V1 |
| `lambda_trip_tools` | Opérations `create/get/update` trips | V1 |
| `dynamodb_trips` | Table `userId`/`tripId`, PITR, SSE | V1 |
| `secrets_manager_app` | Secrets Gateway/Runtime sans hardcoding | V1 |
| `observability` | Logs, metrics, dashboard, alarms | V1 |
| `lambda_agent_facade` | Ancienne façade | Fallback uniquement |

---

## 4. Delivery frontend CloudFront -> S3

### 4.1 Objectif

Servir l’application React / TypeScript / Vite depuis un bucket S3 privé via Amazon CloudFront.

### 4.2 Flux cible

```text
User Browser
  -> Amazon CloudFront Distribution
  -> Origin Access Control
  -> Amazon S3 private frontend bucket
  -> React / Vite static assets
```

### 4.3 Règles de sécurité

- le bucket S3 ne doit pas être public ;
- `Block Public Access` activé ;
- accès S3 autorisé uniquement depuis CloudFront ;
- HTTPS obligatoire côté utilisateur ;
- pas de secret dans les fichiers buildés ;
- pas de `VITE_AGENT_ARN` côté frontend ;
- pas d’AgentCore Gateway URL exposée au navigateur ;
- seul `VITE_API_BASE_URL` doit pointer vers Amazon API Gateway.

---

## 5. Contrat Frontend -> Amazon API Gateway

### 5.1 Endpoint cible

```http
POST /agent/invoke
Authorization: Bearer <cognito_access_token>
Content-Type: application/json
```

### 5.2 Payload accepté

```json
{
  "prompt": "Plan a trip to Tokyo",
  "sessionId": "uuid-or-runtime-compatible-session-id"
}
```

### 5.3 Champs interdits

```json
{
  "actorId": "forbidden",
  "userId": "forbidden",
  "tenantId": "forbidden",
  "trustedIdentity": "forbidden",
  "groups": "forbidden"
}
```

La présence d’un champ d’identité client-side doit retourner une erreur 400 ou une erreur équivalente normalisée au plus tôt dans la chaîne. Si API Gateway ne peut pas appliquer seul cette validation, elle doit être appliquée dans AgentCore Gateway ou Runtime, mais le test négatif reste obligatoire.

---

## 6. Module `api_gateway_web_ingress`

### 6.1 Type

Amazon API Gateway HTTP API.

### 6.2 Routes V1

| Route | Méthode | Intégration nominale | Auth |
|---|---|---|---|
| `/agent/invoke` | POST | AgentCore Gateway endpoint / HTTP integration selon capacité validée P0 | Cognito JWT |
| `/health` | GET | mock ou endpoint statique | optionnel test |

### 6.3 Responsabilités

- valider le JWT Cognito ;
- transmettre les claims validés ou le contexte requis ;
- appliquer CORS limité au domaine CloudFront test ;
- limiter taille payload ;
- limiter taux d’appel ;
- journaliser sans données sensibles ;
- préparer WAF et custom domain pour V2 ;
- ne pas exposer Runtime ARN ni AgentCore Gateway URL au frontend.

### 6.4 Outputs

- `api_id` ;
- `api_endpoint` ;
- `agent_invoke_url` ;
- `authorizer_id` ;
- `stage_name` ;
- `access_log_group_name`.

### 6.5 Critères d’acceptation

- JWT invalide rejeté ;
- requête sans token rejetée ;
- route `/agent/invoke` protégée ;
- CORS limité au frontend CloudFront connu ;
- aucun Runtime ARN exposé ;
- aucun AgentCore Gateway secret exposé ;
- logs sans JWT ni payload sensible.

---

## 7. Module `agentcore_gateway`

### 7.1 Objectif

Créer AgentCore Gateway comme brique centrale de médiation agentique.

### 7.2 Configuration cible

| Élément | Cible |
|---|---|
| Gateway name | `wildrydes-test-agentcore-gateway` |
| Inbound auth | À confirmer P0 : OAuth/JWT, IAM SigV4, authenticate-only ou autre mode supporté |
| Targets | HTTP Runtime target + MCP tool targets |
| Credentials | AgentCore credential provider / Secrets Manager selon target |
| Outputs | `gateway_id`, `gateway_arn`, `gateway_url`, `target_ids` |

### 7.3 Règles

- AgentCore Gateway n’est pas Amazon API Gateway ;
- AgentCore Gateway ne remplace pas CloudFront ;
- AgentCore Gateway ne doit pas être exposé directement au navigateur si API Gateway reste l’ingress web ;
- les targets doivent être explicitement déclarés et limités ;
- les credentials de target doivent être stockés hors Git.

---

## 8. HTTP Target vers AgentCore Runtime

### 8.1 Flux

```text
Amazon API Gateway HTTP API
  -> AgentCore Gateway
      -> HTTP Target: AgentCore Runtime endpoint
```

### 8.2 Décisions

| Décision | Description |
|---|---|
| Purpose | Router le trafic utilisateur validé vers Runtime sans Lambda Facade |
| Protocol | HTTP target / passthrough target selon capacité AgentCore Gateway |
| Identity | Contrat à valider : transmission claims/sub, token exchange ou contexte vérifié |
| Fallback | Lambda Facade uniquement si le contrat d’identité est impossible nativement |

### 8.3 Critères d’acceptation

- AgentCore Gateway visible en console ;
- HTTP Target Runtime visible en console ;
- invocation API Gateway -> Gateway -> Runtime réussie ;
- Runtime reçoit ou reconstruit l’identité de confiance ;
- Runtime rejette les payloads legacy ;
- logs redacted.

---

## 9. MCP Targets vers tools

### 9.1 Flux

```text
Runtime phase_4.py
  -> AgentCore Gateway MCP endpoint
      -> Target A: Lambda Trip Tools
      -> Target B: API Gateway REST API + OpenAPI specification
      -> Target C: future enterprise API / Smithy / MCP server
```

### 9.2 Tools V1

| Tool | Backend V1 | Notes |
|---|---|---|
| `create_trip` | Lambda Trip Tools ou REST API Trips | écrit DynamoDB avec `userId = actorId` |
| `get_trips` | Lambda Trip Tools ou REST API Trips | query partition `userId` |
| `get_trip` | Lambda Trip Tools ou REST API Trips | get item `userId`/`tripId` |
| `update_trip` | Lambda Trip Tools ou REST API Trips | update conditionné sur `userId`/`tripId` |

### 9.3 Règles

- le navigateur ne doit jamais appeler les tools ;
- les tools reçoivent une identité déjà validée ;
- les tools ne doivent pas accepter un `userId` arbitraire ;
- les erreurs tools sont normalisées ;
- chaque target doit avoir un IAM limité.

---

## 10. AgentCore Runtime

### 10.1 Cible

```text
phase_4.py
```

### 10.2 Responsabilités

- lire l’identité de confiance selon le contrat P0 ;
- refuser de faire confiance à `actorId` issu du body client ;
- orchestrer modèle Bedrock ;
- appeler AgentCore Memory ;
- appeler AgentCore Gateway MCP ;
- exécuter le raisonnement agentique ;
- retourner une réponse normalisée.

### 10.3 Configuration externe attendue

| Variable / secret | Usage | Obligatoire |
|---|---|---|
| `AWS_REGION` | Région runtime | Oui |
| `MODEL_ID` | modèle Bedrock par défaut | Oui |
| `MEMORY_ID` | AgentCore Memory | Oui quand Memory créée |
| `GATEWAY_URL` | endpoint MCP Gateway | Oui pour tools |
| `GATEWAY_AUTH_MODE` | mode auth vers Gateway | Oui |
| `SECRET_NAME` | secret applicatif | Oui si secrets externes |
| `LOG_LEVEL` | niveau de logs | Oui |
| `ENABLE_RAG` | future capability | Non, false par défaut |

### 10.4 Critères d’acceptation

- Runtime exécute bien `phase_4.py` ;
- `actorId` provient d’un chemin de confiance ;
- Runtime n’utilise jamais `sessionId` comme `actorId` ;
- Memory namespace correct ;
- Gateway tools accessibles ;
- aucun secret n’est loggé ;
- modèle configurable ;
- image agent reproductible.

---

## 11. AgentCore Memory

### 11.1 Namespace V1

```text
travel/{actorId}/preferences
```

### 11.2 Usage

- préférences utilisateur ;
- contexte durable léger ;
- informations conversationnelles utiles.

### 11.3 Non-usage

Memory ne doit pas stocker :

- secrets ;
- données de paiement ;
- données métier transactionnelles ;
- données cross-user ;
- contenu web brut comme vérité fiable.

---

## 12. DynamoDB Trips

### 12.1 Modèle V1 simple

| Champ | Rôle |
|---|---|
| `userId` | partition key |
| `tripId` | sort key |
| `createdAt` | audit fonctionnel |
| `updatedAt` | audit fonctionnel |
| `status` | état du trip |
| `destination` | destination |
| `startDate` | début |
| `endDate` | fin |

### 12.2 Sécurité

- table par environnement ;
- chiffrement activé ;
- PITR activé ;
- IAM scoped ;
- pas de scan global côté tools sauf besoin justifié ;
- accès cross-user impossible.

---

## 13. IAM cible

| Rôle | Permissions positives | Interdictions |
|---|---|---|
| `api_gateway_integration_role` | appel vers AgentCore Gateway si intégration IAM/SigV4 retenue | pas de DynamoDB, pas de Bedrock InvokeModel |
| `agentcore_gateway_role` | invoke Lambda tools, accès credential provider, target auth | pas de wildcard Lambda global, pas d’AdministratorAccess |
| `runtime_role` | Bedrock InvokeModel, Memory scoped, read app secrets, call Gateway | pas de DynamoDB direct, pas de wildcard Secrets |
| `trip_tools_role` | DynamoDB Get/Query/Put/Update sur table trips | pas de Memory, pas de Bedrock, pas d’AdministratorAccess |
| `github_actions_test_role` | déploiement test limité | pas d’accès prod |

Règles communes :

- least privilege ;
- pas de `AdministratorAccess` ;
- pas de wildcard large non justifié ;
- séparation test/prod ;
- conditions IAM si possible ;
- CloudTrail pour actions CI/CD.

---

## 14. Secrets Manager

Secrets attendus :

- secrets Gateway/targets : `CLIENT_SECRET`, API keys, OAuth credentials si nécessaires ;
- configuration Runtime sensible ;
- future configuration RAG si nécessaire.

Règles :

- aucun secret dans Git ;
- aucun secret dans `variables.txt` commité ;
- rotation à prévoir si secret exposé ;
- accès IAM limité par ARN ;
- aucune valeur de secret dans logs ou outputs.

---

## 15. Observabilité

### 15.1 Logs

- CloudFront logs ou métriques selon besoin test ;
- S3 access posture validation ;
- API Gateway access logs ;
- AgentCore Gateway logs/metrics si disponibles ;
- Runtime logs ;
- tools logs ;
- pipeline logs.

### 15.2 Redaction obligatoire

Ne jamais logger :

- JWT ;
- Authorization header ;
- secrets ;
- prompt complet ;
- user profile complet ;
- actorId brut ;
- sessionId brut ;
- données sensibles.

### 15.3 Métriques cibles

- CloudFront requests/errors/cache behavior ;
- API Gateway 4xx/5xx/latency/throttling ;
- AgentCore Gateway target latency/tool counts/auth failures ;
- Runtime invocations/errors/latency ;
- Trip tools errors ;
- DynamoDB throttles ;
- coût estimé.

---

## 16. CI/CD test corrigée

### 16.1 Workflow Terraform

Workflow :

```text
.github/workflows/test-terraform-stack.yml
```

Modes :

| Mode | Déclencheur | Effet |
|---|---|---|
| Validate | push / PR | fmt, validate, scans |
| Plan | workflow_dispatch | plan Terraform test |
| Apply | workflow_dispatch | apply test avec reviewer |
| Destroy Plan | workflow_dispatch | plan de destruction |
| Destroy | workflow_dispatch | destroy test avec `confirm_destroy=true` |

### 16.2 Workflow applicatif

Workflow :

```text
.github/workflows/test-application-deploy.yml
```

Le workflow doit évoluer vers :

```text
1. terraform output
2. build/push image Runtime
3. deploy/update AgentCore Gateway
4. deploy/update Gateway HTTP Runtime Target
5. deploy/update Gateway MCP Tool Targets
6. deploy/update AgentCore Runtime
7. inject MEMORY_ID, GATEWAY_URL, SECRET_NAME, MODEL_ID
8. build frontend with VITE_API_BASE_URL = Amazon API Gateway invoke URL
9. deploy frontend to S3 and invalidate CloudFront
10. run gates
```

L’ancien input `activate_facade` doit être supprimé ou déprécié au profit d’une activation Gateway/targets.

---

## 17. Tests obligatoires

### 17.1 Smoke tests

- frontend accessible via CloudFront ;
- S3 direct public access refusé ;
- login contrôlé ;
- appel `/agent/invoke` après API Gateway/Gateway/Runtime ;
- réponse agent minimale après full redeploy ;
- health check.

### 17.2 Integration tests

- CloudFront -> S3 privé ;
- Browser app -> API Gateway ;
- API Gateway -> AgentCore Gateway ;
- AgentCore Gateway -> Runtime ;
- Runtime -> Memory ;
- Runtime -> Gateway MCP ;
- Gateway -> Tools ;
- Tools -> DynamoDB.

### 17.3 Security tests

- S3 frontend non public ;
- token absent ;
- token invalide ;
- token expiré ;
- mauvais audience ;
- `actorId` injecté par client ;
- `userId` injecté par client ;
- `trustedIdentity` injecté par client ;
- tentative cross-user ;
- logs redacted.

### 17.4 Latency tests

- CloudFront response time ;
- API Gateway latency ;
- AgentCore Gateway target latency ;
- Runtime latency ;
- tool latency ;
- p50 ;
- p95 ;
- p99 ;
- timeout.

---

## 18. Dépendances de déploiement

Ordre cible V1 test :

```text
0. Lockfile + pipeline Terraform verte
1. Apply base Terraform : DynamoDB + Cognito + S3 frontend privé + CloudFront/OAC
2. API Gateway HTTP API + Cognito JWT authorizer
3. Frontend static deploy via GitHub Actions
4. ECR agent image
5. Lambda trip tools + IAM DynamoDB ou API REST tools
6. AgentCore Gateway
7. AgentCore Gateway HTTP Target vers Runtime
8. AgentCore Gateway MCP Targets vers tools
9. AgentCore Memory
10. AgentCore Runtime
11. Runtime configuration update avec MEMORY_ID/GATEWAY_URL/SECRET_NAME/MODEL_ID
12. Frontend full redeploy avec VITE_API_BASE_URL réel
13. Post-deploy validation end-to-end
14. Observability / cost hardening
```

Le frontend statique ne doit pas attendre AgentCore Runtime pour être servi par CloudFront. En revanche, le parcours agentique complet doit attendre API Gateway, AgentCore Gateway, Runtime, Memory et targets.

---

## 19. Remédiation du repo actuel

| Constat | Correction |
|---|---|
| Documentation encore Lambda Facade first | Remplacer HLD/LLD/README par Gateway-first avec API Gateway conservé |
| Terraform test ne câble que frontend, DynamoDB, Cognito | Ajouter modules API Gateway, AgentCore Gateway, Runtime, Memory, tools |
| Lambda Facade avec InvokeAgentRuntime wildcard | Retirer du chemin nominal ou isoler en fallback avec ADR |
| Runtime deploy laisse `GATEWAY_URL` et `MEMORY_ID` vides | Injecter outputs Gateway/Memory après création |
| Pipeline active facade vers runtime | Remplacer par activation Gateway targets + runtime config |

---

## 20. Critères d’acceptation LLD

Le LLD est accepté si :

- Amazon API Gateway reste explicitement dans le chemin utilisateur ;
- AgentCore Gateway est créé avec au moins un HTTP Target Runtime ;
- AgentCore Gateway expose au moins un MCP Target tool visible ;
- Frontend utilise `VITE_API_BASE_URL` vers Amazon API Gateway ;
- Lambda Facade n’est plus requise pour le chemin nominal ;
- l’identité `actorId = Cognito sub` est prouvée par test contractuel ;
- Runtime n’utilise jamais `sessionId` comme identité ;
- tests négatifs identité, isolation données et logs passent ;
- le pipeline test est aligné avec la branche par défaut ;
- la séparation test/prod est claire ;
- RAG est documenté comme future capability.
