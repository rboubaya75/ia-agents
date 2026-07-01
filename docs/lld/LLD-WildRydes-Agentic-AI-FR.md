# LLD — WildRydes Agentic AI Application Landing Zone

**Version :** 1.2 — alignée Terraform + frontend pipeline  
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
- le delivery frontend via CloudFront et S3 privé ;
- la stratégie de déploiement frontend en deux temps ;
- les contrats API ;
- les responsabilités Lambda ;
- le modèle IAM ;
- les flux d’identité ;
- la CI/CD test ;
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

## 5. Delivery frontend CloudFront -> S3

### 5.1 Objectif

Servir l’application React / TypeScript / Vite depuis un bucket S3 privé via Amazon CloudFront.

### 5.2 Flux cible

```text
User Browser
  -> Amazon CloudFront Distribution
  -> Origin Access Control
  -> Amazon S3 private frontend bucket
  -> React / Vite static assets
```

### 5.3 Composants

| Composant | Rôle |
|---|---|
| S3 frontend bucket | stockage privé des assets buildés |
| CloudFront distribution | point d’accès public HTTPS |
| Origin Access Control | restriction d’accès S3 à CloudFront |
| Error responses | fallback SPA vers `index.html` |
| Terraform outputs | bucket, distribution, domaine CloudFront, Cognito IDs |
| Frontend deploy pipeline | build React, sync S3, invalidation CloudFront |

### 5.4 Règles de sécurité

- le bucket S3 ne doit pas être public ;
- `Block Public Access` activé ;
- accès S3 autorisé uniquement depuis CloudFront ;
- HTTPS obligatoire côté utilisateur ;
- pas de secret dans les fichiers buildés ;
- pas de `VITE_AGENT_ARN` côté frontend ;
- seul `VITE_API_BASE_URL` doit pointer vers API Gateway ou vers un placeholder de static preview.

### 5.5 Critères d’acceptation

- CloudFront sert l’application web ;
- S3 direct public access est impossible ;
- la distribution pointe vers le bucket frontend privé ;
- le fallback SPA fonctionne ;
- le build frontend ne contient aucun ARN Runtime ;
- le déploiement frontend est réalisé par pipeline GitHub Actions dédiée.

---

## 6. Stratégie de déploiement frontend en deux temps

Le frontend V1 est déployé en deux temps pour découpler la delivery web du parcours agentique complet.

### 6.1 Phase A — Frontend static preview

Cette phase est possible dès que la base Terraform est appliquée :

```text
DynamoDB
Cognito
S3 frontend privé
CloudFront distribution
Origin Access Control
```

La pipeline frontend build l’application React/Vite, synchronise `dist/` vers S3 et invalide CloudFront.

Objectifs :

- valider CloudFront ;
- valider que S3 reste privé ;
- valider le rendu React ;
- valider le fallback SPA ;
- valider les paramètres Cognito côté build si l’écran login est prêt.

Limite assumée : le chat agentique ne fonctionne pas encore car API Gateway, Lambda Facade et AgentCore Runtime ne sont pas encore disponibles.

Dans cette phase, `VITE_API_BASE_URL` peut utiliser le placeholder :

```text
https://api-not-yet-deployed.invalid
```

### 6.2 Phase B — Frontend full redeploy

Cette phase intervient après création de :

```text
API Gateway HTTP API
Lambda Agent Invocation Facade
AgentCore Runtime
```

Le frontend est rebuildé avec :

```text
VITE_API_BASE_URL=https://<api-id>.execute-api.eu-west-3.amazonaws.com
```

Le parcours complet devient alors :

```text
Browser
  -> CloudFront
  -> React App
  -> API Gateway HTTP API
  -> Lambda Facade
  -> AgentCore Runtime
  -> phase_4.py
```

### 6.3 Pipeline officielle frontend

Workflow :

```text
.github/workflows/frontend-static-deploy.yml
```

Mode :

```text
workflow_dispatch only
```

Inputs :

| Input | Usage |
|---|---|
| `stack_path` | stack Terraform à lire, par défaut `infra/environments/test` |
| `api_base_url` | valeur build-time de `VITE_API_BASE_URL` |
| `confirm_deploy` | confirmation obligatoire avant sync S3 et invalidation CloudFront |

Le workflow :

```text
checkout
configure AWS credentials via OIDC
terraform init -lockfile=readonly
terraform output
setup Node.js
npm ci
npm run build
aws s3 sync dist/ s3://<frontend_bucket>
aws cloudfront create-invalidation
```

Le workflow doit référencer l’environnement GitHub `test`, afin de bénéficier des reviewers requis.

---

## 7. Contrat Frontend -> API Gateway

### 7.1 Endpoint cible

```http
POST /agent/invoke
Authorization: Bearer <cognito_access_token>
Content-Type: application/json
```

### 7.2 Payload accepté

```json
{
  "prompt": "I want to book a trip",
  "sessionId": "uuid-or-runtime-session-compatible-id"
}
```

### 7.3 Champs interdits

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

## 8. API Gateway

### 8.1 Type

Amazon API Gateway HTTP API.

### 8.2 Routes V1

| Route | Méthode | Intégration | Auth |
|---|---|---|---|
| `/agent/invoke` | POST | Lambda Facade | Cognito JWT |
| `/health` | GET | Lambda Facade ou mock | optionnel test |

### 8.3 Responsabilités

- valider le JWT ;
- transmettre les claims validés ;
- appliquer CORS limité au domaine CloudFront test ;
- limiter taille payload ;
- limiter taux d’appel ;
- journaliser sans données sensibles.

### 8.4 Critères d’acceptation

- JWT invalide rejeté ;
- requête sans token rejetée ;
- route `/agent/invoke` protégée ;
- CORS limité au frontend CloudFront connu ;
- aucun Runtime ARN exposé.

---

## 9. Lambda Agent Invocation Facade

### 9.1 Responsabilités

- parser la requête API Gateway ;
- extraire les claims JWT validés ;
- dériver `actorId` depuis `claims.sub` ;
- valider `prompt` et `sessionId` ;
- rejeter les champs d’identité fournis par le client ;
- construire le payload Runtime ;
- invoquer AgentCore Runtime avec IAM/SigV4 ;
- normaliser la réponse ;
- mapper les erreurs ;
- logger avec redaction.

### 9.2 Payload Runtime cible

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

### 9.3 Mapping erreurs

| Cas | HTTP |
|---|---|
| JWT absent/invalide | 401 |
| champ identité interdit | 400 |
| payload invalide | 400 |
| Runtime timeout | 504 |
| Runtime throttling | 429 |
| erreur Runtime | 502 |
| erreur interne | 500 |

### 9.4 Timeout cible

| Composant | Timeout indicatif |
|---|---|
| API Gateway | limite service |
| Lambda Facade | inférieur au timeout API Gateway |
| SDK Runtime read timeout | inférieur au timeout Lambda |
| Runtime/agent | borné par configuration |

---

## 10. AgentCore Runtime

### 10.1 Cible

```text
phase_4.py
```

### 10.2 Responsabilités

- lire `trustedIdentity.actorId` ;
- refuser de faire confiance à `actorId` issu du body client ;
- orchestrer modèle Bedrock ;
- appeler AgentCore Memory ;
- appeler AgentCore Gateway ;
- exécuter le raisonnement agentique ;
- retourner une réponse normalisée.

### 10.3 Configuration externe attendue

| Variable / secret | Usage |
|---|---|
| `MODEL_ID` | modèle Bedrock par défaut |
| `MEMORY_ID` | AgentCore Memory |
| `GATEWAY_URL` | endpoint MCP Gateway |
| `GATEWAY_CLIENT_ID` | client auth Gateway |
| `GATEWAY_CLIENT_SECRET` | secret auth Gateway |
| `LOG_LEVEL` | niveau de logs |
| `ENABLE_RAG` | future capability |

### 10.4 Critères d’acceptation

- Runtime exécute bien `phase_4.py` ;
- `actorId` provient de `trustedIdentity` ;
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
- données cross-user.

### 11.4 Critères d’acceptation

- un utilisateur ne lit pas la Memory d’un autre ;
- namespace construit côté serveur ;
- logs sans contenu sensible ;
- actions Memory IAM limitées.

---

## 12. AgentCore Gateway et tools MCP

### 12.1 Tools V1

| Tool | Description |
|---|---|
| `create_trip` | créer un trip |
| `get_trips` | lister les trips de l’utilisateur |
| `get_trip` | lire un trip |
| `update_trip` | mettre à jour un trip |

### 12.2 Règles

- le Gateway est interne ;
- le navigateur ne l’appelle pas ;
- les tools reçoivent une identité déjà validée ;
- les tools ne doivent pas accepter un `userId` arbitraire.

### 12.3 Critères d’acceptation

- chaque tool est testé positivement ;
- chaque tool est testé avec tentative d’usurpation d’identité ;
- les erreurs tools sont normalisées ;
- les IAM des tools sont limités à DynamoDB test.

---

## 13. DynamoDB Trips

### 13.1 Modèle V1 simple

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

### 13.2 Sécurité

- table par environnement ;
- chiffrement activé ;
- PITR activé ;
- IAM scoped ;
- pas de scan global côté tools sauf besoin justifié.

### 13.3 Critères d’acceptation

- CRUD trip fonctionne ;
- un utilisateur ne peut pas lire les trips d’un autre ;
- update protégé par condition key ;
- PITR activé ;
- tags environnement présents.

---

## 14. Secrets Manager

### 14.1 Secrets attendus

- client secret Gateway si nécessaire ;
- configuration Runtime sensible ;
- future configuration RAG si nécessaire.

### 14.2 Règles

- aucun secret dans Git ;
- aucun secret dans `variables.txt` commité ;
- rotation à prévoir si secret exposé ;
- accès IAM limité par ARN.

---

## 15. IAM

### 15.1 Rôles cibles

| Rôle | Usage |
|---|---|
| `iam_facade_role` | Lambda Facade |
| `iam_runtime_role` | AgentCore Runtime |
| `iam_gateway_role` | AgentCore Gateway |
| `iam_trip_tools_role` | Lambda Trip Tools |
| `github_actions_test_role` | CI/CD test OIDC |

### 15.2 Principes

- least privilege ;
- pas de `AdministratorAccess` ;
- pas de wildcard large sans justification ;
- séparation test/prod ;
- conditions IAM si possible ;
- CloudTrail pour actions CI/CD.

---

## 16. Observabilité

### 16.1 Logs

- CloudFront logs ou métriques selon besoin test ;
- S3 access posture validation ;
- API Gateway access logs ;
- Lambda Facade logs ;
- Runtime logs ;
- tools logs ;
- pipeline logs.

### 16.2 Redaction obligatoire

Ne jamais logger :

- JWT ;
- secrets ;
- prompt complet ;
- user profile complet ;
- données sensibles.

### 16.3 Métriques cibles

- CloudFront requests/errors/cache behavior ;
- invocations ;
- erreurs ;
- latence ;
- rejets sécurité ;
- tool calls ;
- throttling ;
- coût estimé.

---

## 17. CI/CD test

### 17.1 Workflow Terraform

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

Garde-fous :

- `.terraform.lock.hcl` obligatoire ;
- `terraform init -lockfile=readonly` ;
- `errored.tfstate` uploadé en artifact si apply/destroy échoue ;
- `destroy` sans confirmation échoue explicitement ;
- `apply` et `destroy` passent par l’environnement GitHub `test`.

### 17.2 Workflow frontend

Workflow :

```text
.github/workflows/frontend-static-deploy.yml
```

Modes :

| Mode | `api_base_url` | Effet |
|---|---|---|
| Static preview | `https://api-not-yet-deployed.invalid` | déploie l’app statique CloudFront/S3 sans parcours agent complet |
| Full redeploy | endpoint API Gateway réel | redéploie l’app avec `/agent/invoke` opérationnel |

Critères d’acceptation frontend pipeline :

- workflow manuel uniquement ;
- `confirm_deploy=true` obligatoire ;
- environnement GitHub `test` utilisé ;
- outputs Terraform lus depuis `infra/environments/test` ;
- `npm ci` et `npm run build` passent ;
- `dist/` synchronisé vers S3 ;
- invalidation CloudFront créée ;
- aucun secret ou Runtime ARN injecté dans le build.

---

## 18. Tests

### 18.1 Smoke tests

- frontend accessible via CloudFront ;
- S3 direct public access refusé ;
- login contrôlé ;
- appel `/agent/invoke` après API Gateway/Facade/Runtime ;
- réponse agent minimale après full redeploy ;
- health check.

### 18.2 Integration tests

- CloudFront -> S3 privé ;
- Browser app -> API Gateway ;
- API Gateway -> Lambda Facade ;
- Lambda Facade -> Runtime ;
- Runtime -> Memory ;
- Runtime -> Gateway ;
- Gateway -> Tools ;
- Tools -> DynamoDB.

### 18.3 Security tests

- S3 frontend non public ;
- token absent ;
- token invalide ;
- `actorId` injecté par client ;
- `userId` injecté par client ;
- tentative cross-user ;
- logs redacted.

### 18.4 Latency tests

- CloudFront response time ;
- p50 ;
- p95 ;
- p99 ;
- timeout ;
- cold start suivi comme signal secondaire, sans le considérer comme risque principal avant mesure.

---

## 19. RAG future capability

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

## 20. Dépendances de déploiement

Ordre cible V1 test :

```text
0. Lockfile + pipeline Terraform verte
1. Apply base Terraform : DynamoDB + Cognito + S3 frontend privé + CloudFront/OAC
2. Frontend static deploy via GitHub Actions
3. ECR agent image
4. Lambda trip tools + IAM DynamoDB
5. AgentCore Gateway + Gateway Target
6. AgentCore Memory
7. AgentCore Runtime IAM/SigV4
8. Lambda Agent Invocation Facade
9. API Gateway HTTP API + Cognito JWT authorizer
10. Frontend full redeploy avec VITE_API_BASE_URL réel
11. Post-deploy validation end-to-end
12. Observability / cost hardening
```

Règle : le frontend statique ne doit pas attendre AgentCore Runtime pour être servi par CloudFront. En revanche, le parcours agentique complet doit attendre API Gateway, Lambda Facade et Runtime.

---

## 21. Critères d’acceptation LLD

Le LLD est accepté si :

- chaque composant a une responsabilité claire ;
- le flux CloudFront -> S3 privé est documenté ;
- le frontend static deploy et le full redeploy sont distingués ;
- la pipeline frontend dédiée est documentée ;
- le flux API Gateway -> Lambda Facade -> Runtime est documenté ;
- les contrats API sont définis ;
- les champs interdits sont explicités ;
- les erreurs sont mappées ;
- l’identité server-side est décrite ;
- les modules Terraform sont listés ;
- les critères de test sont présents ;
- le pipeline test est aligné avec la branche par défaut ;
- la séparation test/prod est claire ;
- RAG est documenté comme future capability.
