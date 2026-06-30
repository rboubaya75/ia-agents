# LLD — WildRydes Agentic AI Application Landing Zone

**Version :** 1.0 complète  
**Langue :** Français  
**Branche test par défaut :** `migration/secure-agentcore-v1`  
**Branche future prod :** `main`  
**Périmètre :** environnement `test`  
**IaC :** Terraform  
**CI/CD :** GitHub Actions avec OIDC  
**Runtime cible :** `phase_4.py`

---

## 1. Objectif

Ce LLD décrit l’implémentation technique cible pour industrialiser WildRydes AgentCore en environnement `test`.

Il complète le HLD avec :

- la structure repository ;
- le découpage Terraform ;
- les contrats API ;
- les responsabilités Lambda ;
- le modèle IAM ;
- les flux d’identité ;
- les tests ;
- les critères d’acceptation techniques ;
- les dépendances entre modules.

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
│   └── legacy/
├── infra/
│   ├── environments/
│   │   └── test/
│   └── modules/
├── lambda/
│   ├── agent_facade/
│   └── trip_tools/
├── tests/
│   ├── integration/
│   ├── security/
│   ├── smoke/
│   └── latency/
├── scripts/
├── frontend/
├── deploy-agentcore/
├── Cfn/
└── .github/workflows/
```

Les dossiers `deploy-agentcore/` et `Cfn/` sont conservés temporairement comme legacy/reference tant que la migration Terraform n’est pas complète.

---

## 3. Stratégie branches et environnements

| Élément | Valeur V1 test |
|---|---|
| Branche par défaut | `migration/secure-agentcore-v1` |
| Environnement GitHub | `test` |
| Reviewer | obligatoire |
| Branche production future | `main` |
| Promotion vers prod | manuelle |
| Rôle AWS OIDC | test-only |

Règle :

```text
Aucune ressource prod ne doit être accessible depuis la pipeline test.
```

---

## 4. Modules Terraform cibles

```text
infra/modules/
├── cognito_web_auth/
├── frontend_static_site/
├── api_gateway_agent_ingress/
├── lambda_agent_facade/
├── ecr_agent/
├── agentcore_runtime/
├── agentcore_memory/
├── agentcore_gateway/
├── lambda_trip_tools/
├── dynamodb_trips/
├── secrets_manager_app/
├── iam_facade_role/
├── iam_runtime_role/
├── iam_gateway_role/
├── iam_trip_tools_role/
├── observability/
├── budgets/
└── agent_rag_knowledge_base/
```

Les spécifications détaillées de chaque module sont dans :

```text
docs/specifications/module-specifications-fr.md
```

---

## 5. Contrat Frontend -> API Gateway

### Endpoint cible

```http
POST /agent/invoke
Authorization: Bearer <cognito_access_token>
Content-Type: application/json
```

### Payload accepté

```json
{
  "prompt": "I want to book a trip",
  "sessionId": "uuid-or-runtime-session-compatible-id"
}
```

### Champs interdits

```json
{
  "actorId": "forbidden",
  "userId": "forbidden",
  "tenantId": "forbidden",
  "trustedIdentity": "forbidden"
}
```

La présence d’un champ d’identité client-side doit retourner une erreur 400.

---

## 6. API Gateway

### Type

Amazon API Gateway HTTP API.

### Routes V1

| Route | Méthode | Intégration | Auth |
|---|---|---|---|
| `/agent/invoke` | POST | Lambda Facade | Cognito JWT |
| `/health` | GET | Lambda Facade ou mock | optionnel test |

### Responsabilités

- valider le JWT ;
- transmettre les claims validés ;
- appliquer CORS ;
- limiter taille payload ;
- limiter taux d’appel ;
- journaliser sans données sensibles.

### Critères d’acceptation

- JWT invalide rejeté ;
- requête sans token rejetée ;
- route `/agent/invoke` protégée ;
- CORS limité au frontend connu ;
- aucun Runtime ARN exposé.

---

## 7. Lambda Agent Invocation Facade

### Responsabilités

- parser la requête API Gateway ;
- extraire les claims JWT validés ;
- dériver `actorId` depuis `claims.sub` ;
- valider `prompt` et `sessionId` ;
- rejeter les champs d’identité fournis par le client ;
- construire le payload Runtime ;
- invoquer AgentCore Runtime ;
- normaliser la réponse ;
- mapper les erreurs ;
- logger avec redaction.

### Payload Runtime cible

```json
{
  "prompt": "...",
  "sessionId": "...",
  "trustedIdentity": {
    "actorId": "cognito-sub"
  },
  "correlationId": "..."
}
```

### Mapping erreurs

| Cas | HTTP |
|---|---|
| JWT absent/invalide | 401 |
| champ identité interdit | 400 |
| payload invalide | 400 |
| Runtime timeout | 504 |
| Runtime throttling | 429 |
| erreur Runtime | 502 |
| erreur interne | 500 |

### Timeout cible

| Composant | Timeout indicatif |
|---|---|
| API Gateway | limite service |
| Lambda Facade | inférieur au timeout API Gateway |
| SDK Runtime read timeout | inférieur au timeout Lambda |
| Runtime/agent | borné par configuration |

---

## 8. AgentCore Runtime

### Cible

```text
phase_4.py
```

### Responsabilités

- lire `trustedIdentity.actorId` ;
- refuser de faire confiance à `actorId` issu du body client ;
- orchestrer modèle Bedrock ;
- appeler AgentCore Memory ;
- appeler AgentCore Gateway ;
- exécuter le raisonnement agentique ;
- retourner une réponse normalisée.

### Configuration externe attendue

| Variable / secret | Usage |
|---|---|
| `MODEL_ID` | modèle Bedrock par défaut |
| `MEMORY_ID` | AgentCore Memory |
| `GATEWAY_URL` | endpoint MCP Gateway |
| `GATEWAY_CLIENT_ID` | client auth Gateway |
| `GATEWAY_CLIENT_SECRET` | secret auth Gateway |
| `LOG_LEVEL` | niveau de logs |
| `ENABLE_RAG` | future capability |

### Critères d’acceptation

- Runtime exécute bien `phase_4.py` ;
- `actorId` provient de `trustedIdentity` ;
- Memory namespace correct ;
- Gateway tools accessibles ;
- aucun secret n’est loggé ;
- modèle configurable ;
- image agent reproductible.

---

## 9. AgentCore Memory

### Namespace V1

```text
travel/{actorId}/preferences
```

### Usage

- préférences utilisateur ;
- contexte durable léger ;
- informations conversationnelles utiles.

### Non-usage

Memory ne doit pas stocker :

- secrets ;
- données de paiement ;
- données métier transactionnelles ;
- données cross-user.

### Critères d’acceptation

- un utilisateur ne lit pas la Memory d’un autre ;
- namespace construit côté serveur ;
- logs sans contenu sensible ;
- actions Memory IAM limitées.

---

## 10. AgentCore Gateway et tools MCP

### Tools V1

| Tool | Description |
|---|---|
| `create_trip` | créer un trip |
| `get_trips` | lister les trips de l’utilisateur |
| `get_trip` | lire un trip |
| `update_trip` | mettre à jour un trip |

### Règles

- le Gateway est interne ;
- le navigateur ne l’appelle pas ;
- les tools reçoivent une identité déjà validée ;
- les tools ne doivent pas accepter un `userId` arbitraire.

### Critères d’acceptation

- chaque tool est testé positivement ;
- chaque tool est testé avec tentative d’usurpation d’identité ;
- les erreurs tools sont normalisées ;
- les IAM des tools sont limités à DynamoDB test.

---

## 11. DynamoDB Trips

### Modèle V1 simple

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

### Sécurité

- table par environnement ;
- chiffrement activé ;
- PITR activé ;
- IAM scoped ;
- pas de scan global côté tools sauf besoin justifié.

### Critères d’acceptation

- CRUD trip fonctionne ;
- un utilisateur ne peut pas lire les trips d’un autre ;
- update protégé par condition key ;
- PITR activé ;
- tags environnement présents.

---

## 12. Secrets Manager

### Secrets attendus

- client secret Gateway si nécessaire ;
- configuration Runtime sensible ;
- future configuration RAG si nécessaire.

### Règles

- aucun secret dans Git ;
- aucun secret dans `variables.txt` commité ;
- rotation à prévoir si secret exposé ;
- accès IAM limité par ARN.

---

## 13. IAM

### Rôles cibles

| Rôle | Usage |
|---|---|
| `iam_facade_role` | Lambda Facade |
| `iam_runtime_role` | AgentCore Runtime |
| `iam_gateway_role` | AgentCore Gateway |
| `iam_trip_tools_role` | Lambda Trip Tools |
| `github_actions_test_role` | CI/CD test OIDC |

### Principes

- least privilege ;
- pas de `AdministratorAccess` ;
- pas de wildcard large sans justification ;
- séparation test/prod ;
- conditions IAM si possible ;
- CloudTrail pour actions CI/CD.

---

## 14. Observabilité

### Logs

- API Gateway access logs ;
- Lambda Facade logs ;
- Runtime logs ;
- tools logs ;
- pipeline logs.

### Redaction obligatoire

Ne jamais logger :

- JWT ;
- secrets ;
- prompt complet ;
- user profile complet ;
- données sensibles.

### Métriques cibles

- invocations ;
- erreurs ;
- latence ;
- rejets sécurité ;
- tool calls ;
- throttling ;
- coût estimé.

---

## 15. CI/CD test

Workflow :

```text
.github/workflows/secure-agentcore-test-deploy.yml
```

Modes :

| Mode | Déclencheur | Effet |
|---|---|---|
| Validate | push / PR | fmt, validate, scans |
| Plan | workflow_dispatch | plan Terraform test |
| Apply | workflow_dispatch | apply test avec reviewer |
| Destroy | workflow_dispatch | destroy test avec confirmation |

### Critères d’acceptation CI/CD

- workflow visible sur la branche par défaut ;
- OIDC fonctionne ;
- `apply` passe par environment `test` ;
- `destroy` demande `confirm_destroy=true` ;
- aucun job ne cible `main` pendant la phase test ;
- rôle AWS limité à test.

---

## 16. Tests

### Smoke tests

- login contrôlé ;
- appel `/agent/invoke` ;
- réponse agent minimale ;
- health check.

### Integration tests

- API Gateway -> Lambda Facade ;
- Lambda Facade -> Runtime ;
- Runtime -> Memory ;
- Runtime -> Gateway ;
- Gateway -> Tools ;
- Tools -> DynamoDB.

### Security tests

- token absent ;
- token invalide ;
- `actorId` injecté par client ;
- `userId` injecté par client ;
- tentative cross-user ;
- logs redacted.

### Latency tests

- p50 ;
- p95 ;
- p99 ;
- timeout ;
- cold start.

---

## 17. RAG future capability

Module futur :

```text
agent_rag_knowledge_base
```

Variable :

```hcl
enable_rag = false
```

Le module ne doit créer aucune ressource si `enable_rag = false`.

Activation future conditionnée à :

- corpus validé ;
- stratégie d’ingestion ;
- classification documentaire ;
- metadata filters ;
- tests de retrieval ;
- citations ;
- sécurité prompt injection documentaire ;
- coût validé.

---

## 18. Dépendances de déploiement

Ordre cible :

```text
1. IAM et secrets
2. Cognito
3. DynamoDB
4. Lambda tools
5. AgentCore Gateway
6. AgentCore Memory
7. ECR agent image
8. AgentCore Runtime
9. Lambda Facade
10. API Gateway
11. Frontend
12. Observability
13. Tests
```

---

## 19. Critères d’acceptation LLD

Le LLD est accepté si :

- chaque composant a une responsabilité claire ;
- les contrats API sont définis ;
- les champs interdits sont explicités ;
- les erreurs sont mappées ;
- l’identité server-side est décrite ;
- les modules Terraform sont listés ;
- les critères de test sont présents ;
- le pipeline test est aligné avec la branche par défaut ;
- la séparation test/prod est claire ;
- RAG est documenté comme future capability.
