# WildRydes — Secure AgentCore V1 Landing Zone

Ce dépôt porte la migration de WildRydes vers une **application landing zone AWS sécurisée** pour un agent IA basé sur **Amazon Bedrock AgentCore**.

La branche de travail par défaut pendant la phase de test est :

```text
migration/secure-agentcore-v1
```

La branche `main` est conservée pour la future phase production. La bascule vers `main` sera réalisée manuellement après validation client.

---

## 1. Objectif du projet

L’objectif est d’industrialiser l’ancien workshop WildRydes AgentCore vers une cible exploitable en environnement `test`, avec une trajectoire claire vers la production.

La cible V1 met en place :

- un frontend statique servi par **Amazon CloudFront** depuis un bucket **Amazon S3 privé** ;
- un point d’entrée applicatif via **Amazon API Gateway** ;
- une authentification web via Amazon Cognito ;
- une Lambda Facade entre le frontend et AgentCore Runtime ;
- un Runtime AgentCore exécutant `phase_4.py` ;
- AgentCore Memory pour les préférences utilisateur ;
- AgentCore Gateway pour les tools MCP ;
- des Lambda tools pour la gestion des trips ;
- DynamoDB pour la persistance ;
- Terraform pour l’IaC ;
- GitHub Actions avec OIDC pour la CI/CD test ;
- une base documentaire HLD, LLD, ADR, runbooks et spécifications modules.

---

## 2. Architecture cible V1

La V1 distingue deux flux :

1. **Delivery du frontend statique** ;
2. **Flux applicatif agentique sécurisé**.

### 2.1 Delivery du frontend

```text
User Browser
  -> Amazon CloudFront
  -> Amazon S3 private bucket
  -> React / TypeScript / Vite static assets
```

CloudFront est l’intermédiaire entre l’utilisateur et le bucket S3 privé. Le bucket S3 ne doit pas être public. L’accès au bucket doit passer par CloudFront via Origin Access Control.

### 2.2 Flux applicatif agentique

```text
React App loaded in Browser
  -> Amazon API Gateway HTTP API
  -> Cognito JWT Authorizer
  -> Lambda Agent Invocation Facade
  -> AgentCore Runtime
  -> phase_4.py
  -> Bedrock model
  -> AgentCore Memory
  -> AgentCore Gateway MCP
  -> Lambda Trip Tools
  -> DynamoDB Trips Table
```

Règle clé : le navigateur ne doit jamais appeler directement AgentCore Runtime et ne doit jamais fournir `actorId`, `userId`, `tenantId` ou `trustedIdentity`.

---

## 3. Stratégie de déploiement frontend

Le frontend est déployé en **deux temps**.

### 3.1 Déploiement statique initial

Dès que Terraform a créé Cognito, le bucket S3 privé et la distribution CloudFront, le frontend React/Vite peut être buildé et publié vers S3 via CloudFront.

Objectifs de ce déploiement initial :

- vérifier que CloudFront sert l’application ;
- vérifier que le bucket S3 reste privé ;
- vérifier que le fallback SPA fonctionne ;
- vérifier le rendu React ;
- préparer le socle de delivery web avant l’arrivée de l’API agentique.

Limite assumée : le parcours agent `/agent/invoke` ne fonctionne pas encore tant qu’API Gateway, Lambda Facade et AgentCore Runtime ne sont pas déployés.

### 3.2 Redéploiement frontend complet

Après création d’API Gateway, Lambda Facade et AgentCore Runtime, le frontend doit être rebuildé avec le vrai endpoint applicatif :

```text
VITE_API_BASE_URL=https://<api-id>.execute-api.eu-west-3.amazonaws.com
```

Ce second déploiement active le parcours applicatif complet :

```text
Browser -> CloudFront -> React App -> API Gateway -> Lambda Facade -> AgentCore Runtime
```

### 3.3 Pipeline officielle

Le déploiement officiel du frontend test passe par GitHub Actions :

```text
.github/workflows/frontend-static-deploy.yml
```

Ce workflow est manuel et protégé par l’environnement GitHub `test`.

Il exécute :

```text
checkout
configure AWS credentials via OIDC
terraform init -lockfile=readonly
terraform output
npm ci
npm run build
aws s3 sync dist/ s3://<frontend_bucket>
cloudfront invalidation
```

Le paramètre `api_base_url` peut être :

- `https://api-not-yet-deployed.invalid` pour un static preview ;
- l’endpoint API Gateway réel pour le redéploiement complet.

---

## 4. Branching et environnements

| Branche | Rôle | Statut |
|---|---|---|
| `migration/secure-agentcore-v1` | Branche par défaut pendant la phase test | Active |
| `main` | Future branche production | Réservée |

Pendant la phase test :

```text
migration/secure-agentcore-v1 = test only
main                         = future prod only
```

Le switch vers `main` sera réalisé manuellement après :

- validation fonctionnelle ;
- validation sécurité ;
- validation coûts ;
- validation observabilité ;
- validation client ;
- gel de version.

---

## 5. Documentation

| Document | Objectif |
|---|---|
| `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` | Architecture de haut niveau |
| `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` | Design détaillé technique |
| `docs/specifications/module-specifications-fr.md` | Spécifications et critères d’acceptation par module |
| `docs/adr/` | Décisions d’architecture |
| `docs/runbooks/` | Procédures opérationnelles |
| `docs/legacy/` | Notes sur les éléments hérités du workshop |

---

## 6. Étapes de travail recommandées

### Étape 1 — Préparation locale

```bash
git clone https://github.com/rboubaya75/ia-agents.git
cd ia-agents
git checkout migration/secure-agentcore-v1
git pull
```

### Étape 2 — Vérification de la structure

```bash
ls docs infra lambda tests scripts .github/workflows
```

Vérifier la présence de :

```text
docs/hld/
docs/lld/
docs/specifications/
infra/environments/test/
infra/modules/
frontend/
lambda/
tests/
.github/workflows/
```

### Étape 3 — Validation Terraform locale

```bash
cd infra/environments/test
terraform fmt -check -recursive
terraform init -backend=false -lockfile=readonly
terraform validate
```

### Étape 4 — Pipeline Terraform test

Depuis GitHub Actions :

```text
Actions -> Test Terraform Stack -> Run workflow -> action=plan
Actions -> Test Terraform Stack -> Run workflow -> action=apply
```

Conditions attendues :

- branche `migration/secure-agentcore-v1` ;
- fichier `infra/environments/test/.terraform.lock.hcl` commité ;
- environnement GitHub `test` ;
- reviewer obligatoire ;
- rôle AWS OIDC limité à test ;
- aucun accès prod.

### Étape 5 — Déploiement frontend statique

Après apply de la base Terraform :

```text
Actions -> Frontend Static Deploy -> Run workflow
```

Paramètres pour un static preview :

```text
stack_path = infra/environments/test
api_base_url = https://api-not-yet-deployed.invalid
confirm_deploy = true
```

Paramètres pour le redéploiement complet après API Gateway :

```text
stack_path = infra/environments/test
api_base_url = https://<api-id>.execute-api.eu-west-3.amazonaws.com
confirm_deploy = true
```

### Étape 6 — Destroy Terraform test

Depuis GitHub Actions :

```text
Actions -> Test Terraform Stack -> Run workflow -> action=destroy -> confirm_destroy=true
```

`destroy` est réservé au test et doit rester soumis à validation humaine.

---

## 7. Modules Terraform cibles

Les modules sont décrits dans `docs/specifications/module-specifications-fr.md`.

Vue synthétique :

| Domaine | Modules / sous-modules |
|---|---|
| Identity | `cognito_web_auth`, app client, groups, invited users |
| Frontend | `frontend_static_site`, S3 privé, CloudFront, OAC, cache policy, SPA fallback |
| Ingress | `api_gateway_agent_ingress`, JWT authorizer, routes |
| Facade | `lambda_agent_facade`, request validation, runtime invocation |
| Agent | `ecr_agent`, image build, runtime package |
| AgentCore | `agentcore_runtime`, `agentcore_memory`, `agentcore_gateway` |
| Tools | `lambda_trip_tools`, tool schemas, MCP target |
| Data | `dynamodb_trips`, PITR, SSE, IAM conditions |
| Security | IAM roles, Secrets Manager, log redaction |
| Observability | CloudWatch logs, metrics, X-Ray, dashboards |
| Cost | budgets, alarms, model choice, retention |
| Tests | smoke, integration, security, latency |
| Future | `agent_rag_knowledge_base` disabled by default |

---

## 8. Règles de sécurité

- Pas de secrets dans le dépôt.
- Pas de `AdministratorAccess` dans la cible.
- Pas de Runtime ARN exposé au frontend.
- Pas de `actorId` transmis par le navigateur.
- Bucket S3 frontend privé, non exposé directement à Internet.
- Accès au frontend via CloudFront.
- Pas de prompt brut, JWT ou secret dans les logs.
- OIDC GitHub limité à l’environnement `test`.
- Production hors périmètre de la branche de migration.

---

## 9. Critères globaux d’acceptation V1 test

La V1 test est acceptable si :

- Terraform `fmt`, `init -backend=false -lockfile=readonly` et `validate` passent ;
- la pipeline CI/CD test s’exécute sur la branche de migration ;
- `.terraform.lock.hcl` est commité pour la stack test ;
- `apply` et `destroy` restent manuels et protégés par l’environnement `test` ;
- CloudFront sert le frontend depuis un bucket S3 privé ;
- le bucket S3 frontend n’est pas public ;
- le frontend statique est déployé par pipeline dédiée ;
- API Gateway valide le JWT Cognito ;
- Lambda Facade dérive `actorId` côté serveur ;
- AgentCore Runtime exécute `phase_4.py` ;
- Memory utilise `travel/{actorId}/preferences` ;
- DynamoDB isole les données par utilisateur ;
- les logs sont redacted ;
- les tests négatifs d’identité passent ;
- les coûts test sont visibles ;
- aucun accès prod n’est possible.

---

## 10. Éléments hors périmètre V1

- production go-live ;
- multi-tenant B2B avancé ;
- RAG actif ;
- WAF actif ;
- Bedrock Guardrails actifs ;
- custom domain ;
- admin portal ;
- streaming/WebSocket ;
- promotion automatique vers `main`.

---

## 11. Promotion future vers production

La promotion vers `main` devra faire l’objet d’une étape séparée :

```text
validation test complète
-> revue client
-> gel de version
-> PR ou merge manuel vers main
-> adaptation pipeline prod
-> rôle AWS prod séparé
-> environnement GitHub prod séparé
-> tests pré-prod/prod
```

Aucune promotion automatique vers `main` n’est autorisée pendant la phase test.
