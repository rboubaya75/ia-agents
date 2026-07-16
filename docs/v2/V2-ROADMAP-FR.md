# Roadmap de transition — Secure AgentCore V2

- **Version :** 0.2
- **Branche :** `migration/secure-agentcore-v2`
- **Statut :** Draft
- **Principe :** aucune implémentation structurante avant validation du HLD et du LLD correspondant

## 1. Vue d’ensemble

```text
V2-G0 Baseline et cadrage
  -> V2-G1 ADR structurants et HLD
  -> V2-G2 LLD par domaine
  -> V2-G3 Socle plateforme
  -> V2-G4 RAG et ingestion
  -> V2-G5 Agents et MCP
  -> V2-G6 Frontend et expérience
  -> V2-G7 Sécurité, observabilité et CI/CD
  -> V2-G8 Tests industriels et réception
  -> V2-G9 Documentation As-Built et clôture
```

Les gates sont cumulatives.

## 2. Phase 0 — Baseline et cadrage

Travaux : figer la baseline V1, documenter l’As-Is, définir le périmètre, les exclusions, les exigences initiales, la branche V2, le backlog ADR et la gouvernance documentaire.

**Gate V2-G0 :** charte, roadmap, HLD initial, catalogue des dix LLD et backlog ADR disponibles ; aucun changement applicatif actif.

## 3. Phase 1 — Exigences et ADR structurants

Les ADR bloquants sont :

1. `V2-ADR-001` ingress et frontière de sécurité ;
2. `V2-ADR-002` répartition FastAPI / AgentCore Runtime ;
3. `V2-ADR-003` RAG S3 Vectors ;
4. `V2-ADR-004` ingestion documentaire ;
5. `V2-ADR-005` agents et orchestration ;
6. `V2-ADR-006` identité, autorisation et isolation ;
7. `V2-ADR-007` réseau et calcul EKS ;
8. `V2-ADR-008` observabilité et contexte distribué ;
9. `V2-ADR-009` GitLab CI et promotion ;
10. `V2-ADR-010` sauvegarde, restauration et réhydratation.

**Gate :** aucun ADR critique sans décision ou expérimentation bornée assortie de critères.

## 4. Phase 2 — HLD V2

Le HLD doit couvrir architecture logique et physique, flux d’identité et de données, ingestion, retrieval, agents, tools, zones de confiance, EKS, stockage, disponibilité, reprise, observabilité, coûts, CI/CD, analyse As-Is / To-Be et trajectoire de migration.

**Gate V2-G1 :** HLD `Approved`, responsabilités non ambiguës, risques majeurs associés à des contrôles et aucune implémentation structurante autorisée avant validation.

## 5. Phase 3 — LLD par domaine

Les dix LLD canoniques sont :

1. `V2-LLD-001` Plateforme AWS, réseau, EKS et FastAPI ;
2. `V2-LLD-002` RAG et ingestion documentaire ;
3. `V2-LLD-003` Agents et orchestration ;
4. `V2-LLD-004` AgentCore Gateway MCP et tools ;
5. `V2-LLD-005` Identité, sécurité et conformité ;
6. `V2-LLD-006` Données, mémoire, rétention et restauration ;
7. `V2-LLD-007` Observabilité, SLO et FinOps ;
8. `V2-LLD-008` CI/CD, Terraform, Helm et promotion ;
9. `V2-LLD-009` Stratégie de tests et preuves ;
10. `V2-LLD-010` Frontend React V2.

Chaque LLD couvre périmètre, dépendances ADR exactes, composants, séquences, contrats, IAM, secrets, timeouts, retries, capacité, coûts, observabilité, tests, rollback et risques résiduels.

**Gate V2-G2 :** tous les LLD requis pour la tranche sont `Approved`, avec exigences et tests traçables.

## 6. Phase 4 — Socle EKS et FastAPI

- Terraform, réseau, endpoints, EKS, namespaces et identités de workloads ;
- ECR, Secrets Manager, KMS, Helm et FastAPI ;
- WAF, API Gateway et ingress selon ADR ;
- observabilité minimale et gates CI.

**Gate V2-G3 :** plan Terraform revu, charts testés, contrats FastAPI validés, IAM et réseau testés hors ligne.

## 7. Phase 5 — RAG et ingestion

- S3 source, quarantaine, parsing, chunking et embeddings ;
- S3 Vectors et métadonnées DynamoDB ;
- idempotence, suppression, réindexation et isolation ;
- citations, provenance et dataset d’évaluation ;
- protections adversariales.

**Gate V2-G4 :** ingestion rejouable, suppression cohérente, métriques de retrieval et citations vérifiables.

## 8. Phase 6 — Agents et MCP

- agents sous `/agents`, adapter, Converse API et orchestrateur minimal ;
- budgets de tours, tokens, temps et tools ;
- Gateway MCP, catalogue versionné, confirmation, idempotence et non-rejeu ;
- résilience et circuit breaker.

**Gate V2-G5 :** agents testables hors ligne, aucun tool non gouverné et mutations protégées.

## 9. Phase 7 — Frontend V2

- streaming, citations, upload et suivi d’ingestion ;
- historique, préférences, confirmations et reprise après erreur ;
- sécurité navigateur, accessibilité et tests.

**Gate V2-G6 :** aucune URL Runtime exposée, parcours nominaux et erreurs testés.

## 10. Phase 8 — Sécurité, observabilité, FinOps et CI/CD

- threat model, WAF, Pod Security, Network Policies et contrôle egress ;
- SBOM, scans et signature d’images ;
- OpenTelemetry, CloudWatch, SLO, alertes et coûts ;
- GitLab CI OIDC et parité avec les gates existantes.

**Gate V2-G7 :** sécurité négative, corrélation, coûts, parité CI et rollback démontrés.

## 11. Phase 9 — Tests industriels et réception

- unitaires, contrats, intégration et E2E ;
- isolation, tests adversariaux, charge, soak, chaos et restauration ;
- mesure SLO et preuves redacted.

**Gate V2-G8 :** aucune exigence critique sans test, résultats reproductibles et rapport de réception disponible.

## 12. Phase 10 — As-Built et clôture

- mise à jour HLD/LLD ;
- clôture ou supersession des ADR ;
- runbooks, matrice de coûts, rapport de réception, release et tag V2.

**Gate V2-G9 :** documentation As-Built, preuves archivées, risques résiduels acceptés et release explicitement autorisée.

## 13. Règles de passage

Plan avant modification, périmètre limité, fichiers résumés, validations exécutées, échecs signalés et validation explicite avant la phase suivante. Aucun `terraform apply`, déploiement, merge ou destroy implicite.
