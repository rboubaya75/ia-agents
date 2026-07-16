# Catalogue des LLD — Secure AgentCore V2

- **Version :** 0.1
- **Branche :** `migration/secure-agentcore-v2`
- **Statut :** Draft
- **HLD de référence :** `docs/hld/HLD-Secure-AgentCore-V2-FR.md`

## 1. Objet

Ce document définit les Low-Level Designs obligatoires de la V2, leur contenu minimal, leurs dépendances et leurs gates. Il ne remplace pas les LLD de domaine ; il sert de contrat de complétude et de gouvernance.

## 2. Règle de gouvernance

Un composant structurant ne peut être implémenté que si :

1. le HLD V2 est `Approved` ;
2. les ADR qui gouvernent le composant sont décidés ;
3. le LLD du domaine est `Approved` ;
4. les exigences et critères de test sont traçables ;
5. les risques résiduels sont acceptés ou associés à un plan de traitement.

## 3. Catalogue obligatoire

| ID | LLD | Portée | Dépendances principales | Statut |
|---|---|---|---|---|
| V2-LLD-001 | Plateforme AWS, réseau, EKS et FastAPI | VPC, EKS, compute, ingress, DNS, IAM workload, Helm, secrets | ADR ingress, EKS, identité | À créer |
| V2-LLD-002 | RAG et ingestion documentaire | S3, parsing, chunking, embeddings, S3 Vectors, DynamoDB, suppression | ADR RAG, ingestion, données | À créer |
| V2-LLD-003 | Agents et orchestration | `/agents`, adapter, Converse API, prompts, budgets, fallback | ADR orchestration, responsabilités Runtime | À créer |
| V2-LLD-004 | AgentCore Gateway MCP et tools | catalogue, schémas, IAM, confirmation, idempotence, retry | ADR Runtime, Gateway, identité | À créer |
| V2-LLD-005 | Identité, sécurité et conformité | Cognito, autorisation, tenant, KMS, WAF, threat model, audit | ADR ingress, identité, réseau | À créer |
| V2-LLD-006 | Données, mémoire, rétention et restauration | modèles, cycle de vie, TTL, backup, effacement, réhydratation | ADR données, Memory, DR | À créer |
| V2-LLD-007 | Observabilité, SLO et FinOps | OTel, CloudWatch, corrélation, alertes, coûts, SLO | ADR observabilité, identité | À créer |
| V2-LLD-008 | CI/CD, Terraform, Helm et promotion | GitLab CI, OIDC, artefacts, scans, plan, rollback | ADR CI/CD, environnements | À créer |
| V2-LLD-009 | Stratégie de tests et preuves | pyramide, datasets, E2E, sécurité, charge, chaos, DR | Tous les ADR et LLD | À créer |
| V2-LLD-010 | Frontend React V2 | streaming, uploads, citations, auth, reprise, accessibilité | ADR ingress, APIs et sécurité | À créer |

## 4. Structure minimale d’un LLD

Chaque LLD doit contenir les sections suivantes.

### 4.1 Métadonnées

- version ;
- statut ;
- branche ;
- HLD et ADR de référence ;
- périmètre ;
- exclusions ;
- dépendances.

### 4.2 Architecture détaillée

- composants ;
- responsabilités ;
- diagrammes de déploiement ;
- diagrammes de séquence ;
- flux synchrones et asynchrones ;
- zones de confiance.

### 4.3 Contrats

- OpenAPI, événements ou schémas MCP ;
- formats d’identifiants ;
- règles de validation ;
- versionnement et compatibilité ;
- codes d’erreur ;
- idempotence.

### 4.4 Configuration

- variables ;
- secrets ;
- feature flags ;
- limites ;
- timeouts ;
- retries ;
- quotas ;
- paramètres de capacité.

### 4.5 Sécurité

- authentification et autorisation ;
- IAM exact ;
- chiffrement ;
- resource policies ;
- contrôle réseau ;
- données sensibles ;
- redaction ;
- menaces et contrôles associés.

### 4.6 Résilience

- dépendances critiques ;
- comportement en panne ;
- circuit breakers ;
- reprise ;
- rollback ;
- sauvegarde et restauration ;
- RTO/RPO lorsque pertinent.

### 4.7 Observabilité et coûts

- logs structurés ;
- métriques ;
- traces ;
- attributs de corrélation ;
- dashboards ;
- alertes ;
- métriques de coûts et capacité.

### 4.8 Tests et preuves

- exigences couvertes ;
- tests unitaires ;
- contrats ;
- intégration ;
- E2E ;
- sécurité négative ;
- performance ;
- restauration ;
- preuves et rétention.

### 4.9 Exploitation

- runbooks ;
- procédures de déploiement ;
- rollback ;
- diagnostic ;
- opérations de maintenance ;
- responsabilités techniques sans inventer d’organisation réelle.

## 5. Attendus par LLD

### V2-LLD-001 — Plateforme AWS, réseau, EKS et FastAPI

Doit définir :

- topologie VPC et subnets ;
- endpoints AWS ;
- accès internet et egress ;
- choix de calcul EKS ;
- namespaces ;
- identités de workloads ;
- Network Policies et Pod Security ;
- ingress et intégration API Gateway ;
- DNS et certificats ;
- autoscaling et disruption ;
- charts Helm ;
- health, readiness et graceful shutdown FastAPI.

### V2-LLD-002 — RAG et ingestion

Doit définir :

- formats et tailles ;
- upload et quarantaine ;
- validation et antivirus ;
- parsing ;
- chunking versionné ;
- embeddings Bedrock configurables ;
- schéma S3 Vectors ;
- métadonnées DynamoDB ;
- idempotence et état d’ingestion ;
- suppression, réindexation et réhydratation ;
- filtres d’isolation ;
- citations ;
- dataset et métriques d’évaluation.

### V2-LLD-003 — Agents et orchestration

Doit définir :

- arborescence `/agents` ;
- interfaces du domaine ;
- adapter Strands/LangGraph ;
- orchestrateur ;
- agents spécialisés ;
- Bedrock Converse API ;
- prompts versionnés ;
- budgets de temps, tokens et tours ;
- fallback ;
- contrôle des tools ;
- traitement du retrieval et de Memory comme données non fiables.

### V2-LLD-004 — MCP et tools

Doit définir :

- catalogue et versionnement ;
- schémas stricts ;
- IAM et resource policies ;
- identité injectée côté serveur ;
- lecture versus mutation ;
- confirmation liée à une commande ;
- ledger d’idempotence ;
- retry avant effet de bord uniquement ;
- circuit breaker ;
- gestion des versions MCP ;
- logs redacted et preuves.

### V2-LLD-005 — Sécurité

Doit définir :

- modèle d’identité et de tenant ;
- scopes et rôles ;
- threat model ;
- WAF ;
- KMS et Secrets Manager ;
- sécurité EKS ;
- contrôle de l’egress ;
- sécurité des uploads ;
- prompt injection, data poisoning et exfiltration ;
- audit trail ;
- rétention et effacement.

### V2-LLD-006 — Données et restauration

Doit définir :

- modèles DynamoDB ;
- clés, index et transactions ;
- catégories de données ;
- TTL et conservation ;
- versioning S3 ;
- PITR ;
- Memory ;
- suppression utilisateur ;
- restauration ;
- réhydratation S3 Vectors ;
- cohérence entre sources, métadonnées et index.

### V2-LLD-007 — Observabilité et FinOps

Doit définir :

- instrumentation OpenTelemetry ;
- propagation du contexte ;
- schémas de logs ;
- métriques applicatives, RAG et agents ;
- SLO et error budgets ;
- dashboards et alarmes ;
- calcul des coûts estimés ;
- politique de redaction ;
- rétention des preuves.

### V2-LLD-008 — CI/CD

Doit définir :

- GitLab CI ;
- OIDC AWS ;
- stratégie de branches ;
- builds immuables ;
- SBOM et signature ;
- Terraform plan/apply contrôlé ;
- Helm lint/template/deploy ;
- promotions ;
- secrets ;
- rollback ;
- parité avant retrait de GitHub Actions.

### V2-LLD-009 — Tests

Doit définir :

- identifiants de risques ;
- matrice de traçabilité ;
- unitaires, contrats et intégration ;
- E2E ;
- datasets RAG ;
- tests adversariaux ;
- charge, soak et chaos ;
- tests de restauration ;
- politique de mocks ;
- preuves redacted et rétention.

### V2-LLD-010 — Frontend

Doit définir :

- architecture React ;
- streaming ;
- citations ;
- upload ;
- suivi d’ingestion ;
- historique et préférences ;
- renouvellement de token ;
- reprise des opérations ambiguës ;
- confirmations ;
- sécurité navigateur ;
- accessibilité et tests.

## 6. Ordre de production recommandé

1. V2-LLD-001 Plateforme ;
2. V2-LLD-005 Sécurité ;
3. V2-LLD-006 Données ;
4. V2-LLD-002 RAG ;
5. V2-LLD-003 Agents ;
6. V2-LLD-004 MCP et tools ;
7. V2-LLD-007 Observabilité ;
8. V2-LLD-008 CI/CD ;
9. V2-LLD-010 Frontend ;
10. V2-LLD-009 Tests, consolidé au fil des domaines.

Les LLD peuvent progresser en parallèle lorsque leurs ADR et dépendances sont stables.

## 7. Critère de sortie de la gate V2-G2

- les LLD de la tranche à implémenter sont `Approved` ;
- aucun contrat critique ne reste implicite ;
- les contrôles IAM, réseau, données et sécurité sont détaillés ;
- les tests sont identifiés avant le code ;
- les procédures de rollback et d’exploitation existent ;
- les coûts et limites sont documentés ;
- les divergences avec le HLD sont résolues par amendement ou ADR.
