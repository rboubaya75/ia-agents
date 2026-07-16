# Roadmap de transition — Secure AgentCore V2

- **Version :** 0.1
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

Les gates sont cumulatives. Une phase ne doit pas masquer un écart ouvert dans une phase antérieure.

## 2. Phase 0 — Baseline V1 et cadrage V2

### Travaux

- figer la baseline V1 ;
- établir l’inventaire des composants réutilisés, remplacés et supprimés ;
- documenter l’As-Is ;
- définir le périmètre, les exclusions et les exigences initiales ;
- créer la branche V2 ;
- ouvrir le backlog ADR ;
- définir la gouvernance documentaire.

### Livrables

- `docs/v2/README.md` ;
- `docs/v2/V2-CHARTER-FR.md` ;
- `docs/v2/V2-ROADMAP-FR.md` ;
- baseline V1 référencée par SHA.

### Gate V2-G0

- documents disponibles ;
- exclusions techniques enregistrées ;
- aucun changement applicatif actif ;
- backlog ADR et catalogue LLD initialisés.

## 3. Phase 1 — Exigences détaillées et ADR structurants

### Travaux

- consolider les cas d’usage et parcours ;
- définir volumétrie, classification des données et contraintes de conservation ;
- définir SLO, RTO/RPO, performance et budgets de coût ;
- instruire les options d’ingress ;
- arbitrer le rôle FastAPI/EKS, AgentCore Runtime et Gateway MCP ;
- arbitrer mono-agent ou multi-agent ;
- arbitrer le workflow d’ingestion ;
- définir le modèle d’isolation utilisateur ou tenant ;
- définir la trajectoire GitHub Actions vers GitLab CI.

### Livrables

- catalogue d’exigences versionné ;
- ADR d’ingress ;
- ADR plateforme EKS/FastAPI ;
- ADR RAG/S3 Vectors ;
- ADR agents et orchestration ;
- ADR données et mémoire ;
- ADR CI/CD ;
- ADR observabilité et résilience.

### Gate

Aucun ADR structurant critique ne reste sans décision ou plan d’expérimentation.

## 4. Phase 2 — HLD V2

### Travaux

- architecture logique et physique To-Be ;
- flux d’identité, données, ingestion, retrieval, agents et tools ;
- zones de confiance ;
- architecture EKS ;
- stockage S3, S3 Vectors et DynamoDB ;
- haute disponibilité et reprise ;
- observabilité et FinOps ;
- CI/CD et environnements ;
- analyse As-Is / To-Be ;
- trajectoire de migration et rollback ;
- estimation des coûts et risques.

### Livrable

- `docs/hld/HLD-Secure-AgentCore-V2-FR.md` en statut `Approved`.

### Gate V2-G1

- HLD revu ;
- composants et responsabilités non ambigus ;
- flux sensibles et frontières de confiance couverts ;
- risques majeurs associés à des contrôles ;
- aucun développement structurant autorisé avant cette validation.

## 5. Phase 3 — LLD par domaine

### LLD obligatoires

1. plateforme AWS, réseau, EKS et FastAPI ;
2. RAG et ingestion documentaire ;
3. agents et orchestration ;
4. Gateway MCP et tools ;
5. identité, sécurité et conformité ;
6. données, mémoire, rétention et restauration ;
7. observabilité, SLO et FinOps ;
8. CI/CD, Terraform, Helm et promotion ;
9. stratégie de tests et preuves.

### Contenu minimal de chaque LLD

- périmètre et dépendances ;
- composants et responsabilités ;
- séquences détaillées ;
- contrats d’API ou d’événements ;
- configuration ;
- IAM et secrets ;
- erreurs, timeouts et retries ;
- capacité, performance et coûts ;
- logs, métriques et traces ;
- tests et critères d’acceptation ;
- rollback et exploitation ;
- risques résiduels.

### Gate V2-G2

- tous les LLD nécessaires à la première tranche sont `Approved` ;
- exigences et tests sont traçables ;
- les choix non tranchés sont bloquants ou explicitement différés.

## 6. Phase 4 — Socle plateforme EKS et FastAPI

### Travaux

- modules Terraform ;
- réseau et endpoints nécessaires ;
- cluster EKS ;
- namespaces, politiques et identités de workloads ;
- ECR ;
- Secrets Manager et KMS ;
- Helm charts ;
- FastAPI avec health, readiness et graceful shutdown ;
- WAF, API Gateway et intégration d’ingress selon ADR ;
- observabilité minimale ;
- gates CI de compilation, sécurité et plan.

### Gate V2-G3

- plan Terraform revu ;
- charts Helm testés ;
- contrats FastAPI validés ;
- contrôles réseau et IAM testés hors ligne ;
- aucun déploiement sans autorisation explicite.

## 7. Phase 5 — RAG et ingestion documentaire

### Travaux

- stockage source S3 ;
- validation, parsing et chunking ;
- embeddings Bedrock configurables ;
- index S3 Vectors ;
- métadonnées DynamoDB ;
- ingestion idempotente ;
- réindexation et suppression ;
- isolation ;
- citations et provenance ;
- protection contre prompt injection et data poisoning ;
- dataset d’évaluation versionné.

### Gate V2-G4

- ingestion rejouable sans doublon ;
- suppression cohérente source/index/métadonnées ;
- métriques de retrieval calculées ;
- citations vérifiables ;
- tests adversariaux disponibles.

## 8. Phase 6 — Agents custom et Gateway MCP

### Travaux

- structure `/agents` ;
- contrats applicatifs indépendants du framework ;
- adapter Strands ou LangGraph ;
- Bedrock Converse API ;
- orchestrateur minimal ;
- agents spécialisés justifiés ;
- budgets de tours et de tokens ;
- tool allowlists par agent ;
- Gateway MCP et tools versionnés ;
- confirmation, idempotence et non-rejeu ;
- resilience et circuit breaker.

### Gate V2-G5

- agents testables sans service externe ;
- aucun tool non gouverné ;
- mutation protégée et rejouable ;
- retrieval traité comme donnée non fiable ;
- appels modèle et tools traçables.

## 9. Phase 7 — Frontend V2

### Travaux

- streaming ;
- affichage des sources ;
- upload documentaire ;
- état d’ingestion ;
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

## 10. Phase 8 — Sécurité, observabilité, FinOps et CI/CD

### Travaux

- threat model ;
- WAF et règles de protection ;
- Pod Security et Network Policies ;
- SBOM, scans et signature d’images ;
- OpenTelemetry ;
- dashboards CloudWatch ;
- SLO, alertes et error budgets ;
- métriques de tokens, embeddings, stockage et calcul ;
- pipeline GitLab CI OIDC ;
- parité avec les gates existantes avant retrait de GitHub Actions.

### Gate V2-G7

- sécurité négative démontrée ;
- corrélation bout en bout ;
- coûts mesurables ;
- parité CI prouvée ;
- rollback documenté.

## 11. Phase 9 — Tests industriels et réception

### Travaux

- unitaires, contrats et intégration ;
- E2E ;
- isolation multi-utilisateur ou multi-tenant ;
- prompt injection et data poisoning ;
- charge et soak tests ;
- chaos contrôlé ;
- restauration ;
- mesure SLO ;
- preuves immuables et redacted.

### Gate V2-G8

- aucune exigence critique sans test ;
- résultats reproductibles ;
- échecs connus documentés ;
- restauration et rollback prouvés ;
- rapport de réception disponible.

## 12. Phase 10 — As-Built et clôture

### Travaux

- mettre à jour HLD et LLD selon l’implémentation ;
- clôturer ou superseder les ADR ;
- finaliser runbooks, standards et procédures ;
- produire la matrice de coûts ;
- produire le rapport de réception ;
- préparer release et tag V2.

### Gate V2-G9

- documentation en statut `As-Built` ;
- preuves archivées ;
- dette et risques résiduels acceptés ;
- release autorisée explicitement.

## 13. Règles de passage entre phases

- plan présenté avant chaque phase ;
- modification limitée au périmètre validé ;
- fichiers changés résumés ;
- lint, typecheck et tests exécutés ;
- tous les échecs signalés ;
- validation explicite avant la phase suivante ;
- aucun `terraform apply`, déploiement, merge ou destruction implicite.
