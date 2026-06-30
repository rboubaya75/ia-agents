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

- un point d’entrée applicatif via Amazon API Gateway ;
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

```text
Browser
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

## 3. Branching et environnements

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

## 4. Documentation

| Document | Objectif |
|---|---|
| `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` | Architecture de haut niveau |
| `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` | Design détaillé technique |
| `docs/specifications/module-specifications-fr.md` | Spécifications et critères d’acceptation par module |
| `docs/adr/` | Décisions d’architecture |
| `docs/runbooks/` | Procédures opérationnelles |
| `docs/legacy/` | Notes sur les éléments hérités du workshop |

---

## 5. Étapes de travail recommandées

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
lambda/
tests/
.github/workflows/
```

### Étape 3 — Validation Terraform locale

```bash
cd infra/environments/test
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

### Étape 4 — Exécution CI/CD automatique

Les workflows se déclenchent sur la branche `migration/secure-agentcore-v1` pour les changements dans :

```text
infra/environments/test/**
infra/modules/**
.github/workflows/**
```

### Étape 5 — Plan Terraform test

Depuis GitHub Actions :

```text
Actions -> Secure AgentCore Test — Terraform CI/CD -> Run workflow -> action=plan
```

Le plan doit utiliser le rôle AWS OIDC dédié à l’environnement `test`.

### Étape 6 — Apply Terraform test

Depuis GitHub Actions :

```text
Actions -> Secure AgentCore Test — Terraform CI/CD -> Run workflow -> action=apply
```

Conditions attendues :

- branche `migration/secure-agentcore-v1` ;
- environnement GitHub `test` ;
- reviewer obligatoire ;
- rôle AWS limité à test ;
- aucun accès prod.

### Étape 7 — Destroy Terraform test

Depuis GitHub Actions :

```text
Actions -> Secure AgentCore Test — Terraform CI/CD -> Run workflow -> action=destroy -> confirm_destroy=true
```

`destroy` est réservé au test et doit rester soumis à validation humaine.

---

## 6. Modules Terraform cibles

Les modules sont décrits dans `docs/specifications/module-specifications-fr.md`.

Vue synthétique :

| Domaine | Modules / sous-modules |
|---|---|
| Identity | `cognito_web_auth`, app client, groups, invited users |
| Frontend | `frontend_static_site`, S3, CloudFront, OAC |
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

## 7. Règles de sécurité

- Pas de secrets dans le dépôt.
- Pas de `AdministratorAccess` dans la cible.
- Pas de Runtime ARN exposé au frontend.
- Pas de `actorId` transmis par le navigateur.
- Pas de prompt brut, JWT ou secret dans les logs.
- OIDC GitHub limité à l’environnement `test`.
- Production hors périmètre de la branche de migration.

---

## 8. Critères globaux d’acceptation V1 test

La V1 test est acceptable si :

- Terraform `fmt`, `init -backend=false` et `validate` passent ;
- la pipeline CI/CD test s’exécute sur la branche de migration ;
- `apply` et `destroy` restent manuels et protégés par l’environnement `test` ;
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

## 9. Éléments hors périmètre V1

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

## 10. Promotion future vers production

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
