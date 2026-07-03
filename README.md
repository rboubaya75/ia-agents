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

## 3. Stratégie CI/CD rationalisée

La cible d’exploitation test repose sur **deux pipelines principales**.

### 3.1 Pipeline infrastructure

```text
.github/workflows/test-terraform-stack.yml
```

Rôle : gérer le socle Terraform de l’environnement `test`.

Actions disponibles :

```text
plan
apply
destroy-plan
destroy
```

Cette pipeline est responsable des ressources Terraform : Cognito, DynamoDB, S3/CloudFront, API Gateway, Lambda Facade, ECR, IAM et configuration d’exécution.

### 3.2 Pipeline applicative consolidée

```text
.github/workflows/test-application-deploy.yml
```

Rôle : déployer les composants applicatifs sans multiplier les workflows.

Modes disponibles :

```text
frontend-only
image-only
runtime-only
full
```

Le mode `full` exécute le parcours applicatif complet :

```text
1. Lire les outputs Terraform
2. Build/push l’image AgentCore vers ECR
3. Déployer ou mettre à jour AgentCore Runtime
4. Activer Lambda Facade -> Runtime
5. Rebuilder et redéployer le frontend avec l’API Gateway réelle
6. Invalider CloudFront
```

Les anciens workflows applicatifs séparés ont été supprimés ou dépréciés au profit de cette pipeline consolidée.

---

## 4. Stratégie de déploiement frontend

Le frontend est déployé via la pipeline applicative consolidée.

### 4.1 Déploiement statique initial

Dès que Terraform a créé Cognito, le bucket S3 privé et la distribution CloudFront, le frontend React/Vite peut être buildé et publié vers S3 via CloudFront.

Utiliser :

```text
Actions -> Test Application Deploy
mode = frontend-only
api_base_url = https://api-not-yet-deployed.invalid
confirm_deploy = true
```

Objectifs de ce déploiement initial :

- vérifier que CloudFront sert l’application ;
- vérifier que le bucket S3 reste privé ;
- vérifier que le fallback SPA fonctionne ;
- vérifier le rendu React ;
- préparer le socle de delivery web avant l’arrivée de l’API agentique.

### 4.2 Redéploiement complet

Après création d’API Gateway, Lambda Facade et AgentCore Runtime, utiliser :

```text
Actions -> Test Application Deploy
mode = full
image_tag = test
endpoint_name = default
activate_facade = true
confirm_deploy = true
```

Ce mode active le parcours applicatif complet :

```text
Browser -> CloudFront -> React App -> API Gateway -> Lambda Facade -> AgentCore Runtime
```

---

## 5. Branching et environnements

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

## 6. Documentation

| Document | Objectif |
|---|---|
| `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` | Architecture de haut niveau |
| `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` | Design détaillé technique |
| `docs/specifications/module-specifications-fr.md` | Spécifications et critères d’acceptation par module |
| `docs/adr/` | Décisions d’architecture |
| `docs/runbooks/` | Procédures opérationnelles |
| `docs/legacy/` | Notes sur les éléments hérités du workshop |

---

## 7. Étapes de travail recommandées

### Étape 1 — Préparation locale

```bash
git clone https://github.com/rboubaya75/ia-agents.git
cd ia-agents
git checkout migration/secure-agentcore-v1
git pull
```

### Étape 2 — Validation Terraform locale

```bash
cd infra/environments/test
terraform fmt -check -recursive
terraform init -backend=false -lockfile=readonly
terraform validate
```

### Étape 3 — Pipeline Terraform test

Depuis GitHub Actions :

```text
Actions -> Test Terraform Stack -> Run workflow -> action=plan
Actions -> Test Terraform Stack -> Run workflow -> action=apply
```

### Étape 4 — Déploiement applicatif test

Pour un déploiement complet :

```text
Actions -> Test Application Deploy -> Run workflow
mode = full
image_tag = test
endpoint_name = default
activate_facade = true
confirm_deploy = true
```

Pour un déploiement partiel :

```text
mode = frontend-only
mode = image-only
mode = runtime-only
```
