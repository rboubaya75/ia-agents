# Catalogue des LLD — Secure AgentCore V2

- **Version :** 0.2
- **Branche :** `migration/secure-agentcore-v2`
- **Statut :** Draft
- **HLD de référence :** `docs/hld/HLD-Secure-AgentCore-V2-FR.md`
- **Backlog ADR :** `docs/adr/V2-ADR-BACKLOG-FR.md`

## 1. Objet

Ce document constitue la source canonique des Low-Level Designs V2, de leurs identifiants, dépendances ADR et critères de validation.

## 2. Règle de gouvernance

Un composant structurant ne peut être implémenté que lorsque le HLD, les ADR applicables et le LLD du domaine sont `Approved`, que les exigences et tests sont traçables et que les risques résiduels sont acceptés ou planifiés.

## 3. Catalogue canonique et dépendances

| ID | LLD | Dépendances ADR obligatoires | ADR complémentaires selon périmètre | Statut |
|---|---|---|---|---|
| V2-LLD-001 | Plateforme AWS, réseau, EKS et FastAPI | `V2-ADR-001`, `V2-ADR-002`, `V2-ADR-006`, `V2-ADR-007` | `V2-ADR-011`, `V2-ADR-016` | À créer |
| V2-LLD-002 | RAG et ingestion documentaire | `V2-ADR-003`, `V2-ADR-004`, `V2-ADR-006`, `V2-ADR-010` | `V2-ADR-013`, `V2-ADR-017`, `V2-ADR-018` | À créer |
| V2-LLD-003 | Agents et orchestration | `V2-ADR-002`, `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-008` | `V2-ADR-012`, `V2-ADR-015` | À créer |
| V2-LLD-004 | AgentCore Gateway MCP et tools | `V2-ADR-002`, `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-008` | `V2-ADR-014`, `V2-ADR-016` | À créer |
| V2-LLD-005 | Identité, sécurité et conformité | `V2-ADR-001`, `V2-ADR-006`, `V2-ADR-007`, `V2-ADR-008` | `V2-ADR-014`, `V2-ADR-015`, `V2-ADR-016`, `V2-ADR-017` | À créer |
| V2-LLD-006 | Données, mémoire, rétention et restauration | `V2-ADR-003`, `V2-ADR-004`, `V2-ADR-006`, `V2-ADR-010` | `V2-ADR-013`, `V2-ADR-015`, `V2-ADR-017` | À créer |
| V2-LLD-007 | Observabilité, SLO et FinOps | `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-007`, `V2-ADR-008` | `V2-ADR-012`, `V2-ADR-013` | À créer |
| V2-LLD-008 | CI/CD, Terraform, Helm et promotion | `V2-ADR-007`, `V2-ADR-008`, `V2-ADR-009`, `V2-ADR-010` | Aucun par défaut | À créer |
| V2-LLD-009 | Stratégie de tests et preuves | `V2-ADR-001` à `V2-ADR-010` | `V2-ADR-011` à `V2-ADR-018` selon la tranche | À créer |
| V2-LLD-010 | Frontend React V2 | `V2-ADR-001`, `V2-ADR-002`, `V2-ADR-006`, `V2-ADR-008` | `V2-ADR-011`, `V2-ADR-014`, `V2-ADR-016` | À créer |

Toute dépendance ajoutée ou retirée doit être justifiée dans le LLD ou par amendement du backlog ADR.

## 4. Structure minimale d’un LLD

Chaque LLD doit contenir :

1. métadonnées, périmètre, exclusions et dépendances ;
2. architecture détaillée et séquences ;
3. contrats OpenAPI, événements ou MCP ;
4. configuration, secrets, limites, timeouts, retries et quotas ;
5. authentification, autorisation, IAM, chiffrement, réseau et redaction ;
6. résilience, comportement en panne, reprise, rollback et RTO/RPO ;
7. logs, métriques, traces, dashboards, alertes et coûts ;
8. tests, critères d’acceptation, preuves et rétention ;
9. runbooks et opérations de maintenance ;
10. risques résiduels et écarts HLD.

## 5. Attendus spécifiques

### V2-LLD-001 — Plateforme

VPC, subnets, endpoints, egress, EKS, compute, namespaces, IAM workloads, Network Policies, Pod Security, ingress, DNS, certificats, autoscaling, Helm et FastAPI.

### V2-LLD-002 — RAG et ingestion

Formats, quarantaine, antivirus, parsing, chunking, embeddings, S3 Vectors, DynamoDB, idempotence, suppression, réindexation, isolation, citations, dataset et métriques.

### V2-LLD-003 — Agents

Arborescence `/agents`, interfaces métier, adapter, orchestrateur, agents spécialisés, Converse API, prompts, budgets, fallback et contrôle des tools.

### V2-LLD-004 — MCP et tools

Catalogue, schémas, IAM, identité injectée, lecture/mutation, confirmation, ledger d’idempotence, retry avant effet de bord, circuit breaker et compatibilité MCP.

### V2-LLD-005 — Sécurité

Identité, tenant, scopes, threat model, WAF, KMS, Secrets Manager, sécurité EKS, egress, uploads, prompt injection, data poisoning, exfiltration, audit et effacement.

### V2-LLD-006 — Données et restauration

Modèles DynamoDB, catégories de données, TTL, conservation, S3 versioning, PITR, Memory, suppression utilisateur, restauration, réhydratation et cohérence source/index/métadonnées.

### V2-LLD-007 — Observabilité et FinOps

OpenTelemetry, propagation, logs, métriques RAG/agents, SLO, error budgets, dashboards, alarmes, coûts, redaction et rétention.

### V2-LLD-008 — CI/CD

GitLab CI, OIDC, branches, builds immuables, SBOM, signature, Terraform, Helm, promotions, secrets, rollback et parité GitHub Actions.

### V2-LLD-009 — Tests

Matrice de traçabilité, tests unitaires, contrats, intégration, E2E, datasets RAG, adversarial, charge, soak, chaos, restauration, mocks et preuves.

### V2-LLD-010 — Frontend

Architecture React, streaming, citations, upload, suivi d’ingestion, historique, préférences, tokens, reprise, confirmations, sécurité navigateur, accessibilité et tests.

## 6. Ordre de production recommandé

1. `V2-LLD-001` Plateforme ;
2. `V2-LLD-005` Sécurité ;
3. `V2-LLD-006` Données ;
4. `V2-LLD-002` RAG ;
5. `V2-LLD-003` Agents ;
6. `V2-LLD-004` MCP et tools ;
7. `V2-LLD-007` Observabilité ;
8. `V2-LLD-008` CI/CD ;
9. `V2-LLD-010` Frontend ;
10. `V2-LLD-009` Tests, consolidé au fil des domaines.

## 7. Gate V2-G2

Les LLD requis pour la tranche sont `Approved`, aucun contrat critique n’est implicite, IAM/réseau/données/sécurité sont détaillés, les tests précèdent le code, les procédures de rollback existent et les divergences avec le HLD sont résolues par amendement ou ADR.
