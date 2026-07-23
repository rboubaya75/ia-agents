# Roadmap de transition — Secure AgentCore V2

- **Version :** 0.2
- **Branche cible :** `migration/secure-agentcore-v2`
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

Les gates sont cumulatives. Une phase ne masque jamais un écart ouvert dans une phase antérieure.

## 2. Règle de branches

- la baseline V1 reste sur `migration/secure-agentcore-v1` ;
- la branche d’intégration V2 est `migration/secure-agentcore-v2` ;
- chaque lot V2 utilise une branche de travail créée depuis la V2 ;
- chaque pull request V2 cible la V2 et jamais la V1.

## 3. Phase 0 — Baseline V1 et cadrage V2

### Travaux

- figer la baseline V1 ;
- inventorier les composants réutilisés, remplacés et supprimés ;
- documenter l’As-Is ;
- définir le périmètre, les exclusions et les exigences initiales ;
- créer la branche V2 ;
- ouvrir le backlog ADR ;
- définir la gouvernance documentaire et des branches.

### Livrables

- `architecture/README.md` ;
- `architecture/governance/V2-CHARTER-FR.md` ;
- `architecture/governance/V2-ROADMAP-FR.md` ;
- baseline V1 référencée par SHA ;
- catalogue canonique des dix LLD ;
- backlog ADR.

### Gate V2-G0

- documents disponibles et revus ;
- exclusions techniques enregistrées ;
- aucun changement applicatif actif ;
- branche V1 préservée ;
- backlog ADR et catalogue LLD initialisés.

## 4. Phase 1 — Exigences détaillées et ADR structurants

### Travaux

- consolider les cas d’usage et parcours ;
- définir volumétrie, classification et conservation ;
- définir SLO, RTO/RPO, performance et budgets de coût ;
- instruire les options d’ingress ;
- arbitrer les responsabilités FastAPI, Runtime et Gateway MCP ;
- arbitrer mono-agent ou multi-agent ;
- arbitrer le workflow d’ingestion ;
- définir le modèle d’isolation utilisateur ou tenant ;
- définir la trajectoire GitHub Actions vers GitLab CI.

### Livrables

- catalogue d’exigences versionné ;
- ADR `V2-ADR-001` à `V2-ADR-010` ;
- plans d’expérimentation bornés lorsque nécessaires.

### Gate

Aucun ADR structurant critique ne reste ambigu, sans décision ou sans expérimentation assortie de critères de sortie.

## 5. Phase 2 — HLD V2

### Travaux

- architecture logique et physique To-Be ;
- flux d’identité, données, ingestion, retrieval, agents et tools ;
- zones de confiance ;
- architecture ECS ;
- stockage S3, S3 Vectors et DynamoDB ;
- haute disponibilité et reprise ;
- observabilité et FinOps ;
- CI/CD et environnements ;
- analyse As-Is / To-Be ;
- trajectoire de migration et rollback ;
- estimation des coûts et risques.

### Gate V2-G1

- HLD en statut `Approved` ;
- composants et responsabilités non ambigus ;
- flux sensibles et frontières de confiance couverts ;
- risques majeurs associés à des contrôles ;
- aucun développement structurant autorisé avant validation.

## 6. Phase 3 — LLD par domaine

### Catalogue canonique

1. `V2-LLD-001` — plateforme AWS, réseau, ECS et FastAPI ;
2. `V2-LLD-002` — RAG et ingestion documentaire ;
3. `V2-LLD-003` — agents et orchestration ;
4. `V2-LLD-004` — AgentCore Gateway MCP et tools ;
5. `V2-LLD-005` — identité, sécurité et conformité ;
6. `V2-LLD-006` — données, mémoire, rétention et restauration ;
7. `V2-LLD-007` — observabilité, SLO et FinOps ;
8. `V2-LLD-008` — CI/CD, Terraform et promotion ;
9. `V2-LLD-009` — stratégie de tests et preuves ;
10. `V2-LLD-010` — frontend React V2.

### Contenu minimal

Chaque LLD couvre : périmètre, dépendances ADR exactes, architecture détaillée, contrats, configuration, IAM, secrets, timeouts, retries, capacité, coûts, observabilité, tests, rollback, exploitation et risques résiduels.

### Gate V2-G2

- tous les LLD nécessaires à la tranche sont `Approved` ;
- les dix LLD sont suivis dans le catalogue, même lorsqu’ils ne sont pas encore applicables à la tranche ;
- exigences, risques, ADR et tests sont traçables ;
- les choix non tranchés sont bloquants ou explicitement différés.

## 7. Phase 4 — Socle plateforme ECS et FastAPI

### Travaux

- modules Terraform ;
- réseau et endpoints ;
- ECS, services, politiques et identités de workloads ;
- ECR, Secrets Manager et KMS ;
- FastAPI avec health, readiness et graceful shutdown ;
- WAF, API Gateway et ingress selon ADR ;
- observabilité minimale ;
- gates CI de compilation, sécurité et plan.

### Gate V2-G3

- plan Terraform revu ;
- définitions de tâches ECS validées ;
- contrats FastAPI validés ;
- contrôles réseau et IAM testés hors ligne ;
- aucun déploiement sans autorisation explicite.

## 8. Phase 5 — RAG et ingestion documentaire

### Travaux

- stockage source S3 ;
- validation, parsing et chunking ;
- embeddings Bedrock configurables ;
- S3 Vectors ;
- métadonnées DynamoDB ;
- ingestion idempotente ;
- réindexation et suppression ;
- isolation ;
- citations et provenance ;
- protections contre prompt injection et data poisoning ;
- dataset d’évaluation versionné.

### Gate V2-G4

- ingestion rejouable sans doublon ;
- suppression cohérente source, index et métadonnées ;
- métriques de retrieval calculées ;
- citations vérifiables ;
- tests adversariaux disponibles.

## 9. Phase 6 — Agents custom et Gateway MCP

### Travaux

- structure `/agents` ;
- contrats applicatifs indépendants du framework ;
- adapter Strands ou LangGraph ;
- Bedrock Converse API ;
- orchestrateur minimal ;
- agents spécialisés justifiés ;
- budgets de tours et tokens ;
- allowlists de tools ;
- Gateway MCP et tools versionnés ;
- confirmation, idempotence, non-rejeu et circuit breaker.

### Gate V2-G5

- agents testables sans service externe ;
- aucun tool non gouverné ;
- mutations protégées et rejouables ;
- retrieval traité comme donnée non fiable ;
- appels modèle et tools traçables.

## 10. Phase 7 — Frontend V2

### Travaux

- streaming ;
- sources et citations ;
- upload et suivi d’ingestion ;
- historique et préférences ;
- confirmations ;
- reprise après 401 et erreur ambiguë ;
- accessibilité ;
- tests navigateur.

### Gate V2-G6

- aucune URL technique Runtime exposée ;
- tokens et prompts absents des stockages non autorisés ;
- parcours nominaux et erreurs testés ;
- sources et confirmations compréhensibles.

## 11. Phase 8 — Sécurité, observabilité, FinOps et CI/CD

### Travaux

- threat model ;
- WAF, Pod Security et Network Policies ;
- SBOM, scans et signature d’images ;
- OpenTelemetry et CloudWatch ;
- SLO, alertes et error budgets ;
- métriques de tokens, embeddings, stockage et calcul ;
- GitLab CI OIDC ;
- parité avec les gates existantes avant retrait de GitHub Actions.

### Gate V2-G7

- sécurité négative démontrée ;
- corrélation bout en bout ;
- coûts mesurables ;
- parité CI prouvée ;
- rollback documenté.

## 12. Phase 9 — Tests industriels et réception

### Travaux

- tests unitaires, contrats, intégration et E2E ;
- isolation multi-utilisateur ou multi-tenant ;
- prompt injection et data poisoning ;
- charge, soak et chaos contrôlé ;
- restauration ;
- mesure des SLO ;
- preuves immuables et redacted.

### Gate V2-G8

- aucune exigence critique sans test ;
- résultats reproductibles ;
- échecs connus documentés ;
- restauration et rollback prouvés ;
- rapport de réception disponible.

## 13. Phase 10 — As-Built et clôture

### Travaux

- mettre à jour HLD et LLD selon l’implémentation ;
- clôturer ou superseder les ADR ;
- finaliser runbooks, standards et procédures ;
- produire la matrice de coûts et le rapport de réception ;
- préparer release et tag V2.

### Gate V2-G9

- documentation en statut `As-Built` ;
- preuves archivées ;
- dette et risques résiduels acceptés ;
- release autorisée explicitement.

## 14. Règles de passage entre phases

- plan présenté avant chaque phase ;
- modification limitée au périmètre validé ;
- fichiers changés résumés ;
- lint, typecheck et tests pertinents exécutés ;
- tous les échecs signalés ;
- validation explicite avant la phase suivante ;
- aucun `terraform apply`, déploiement, merge ou destruction implicite.
