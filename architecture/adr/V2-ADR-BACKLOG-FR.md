# Backlog des Architecture Decision Records — Secure AgentCore V2

- **Version :** 0.1
- **Branche :** `migration/secure-agentcore-v2`
- **Statut :** Draft
- **HLD :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md`

## 1. Objet

Ce backlog identifie les décisions structurantes à instruire avant validation du HLD et des LLD V2. Il ne préjuge pas des décisions finales. Chaque ADR devra comparer des options réalistes, documenter les compromis, les impacts de migration, les coûts, les risques et les conséquences opérationnelles.

## 2. Règles de décision

Chaque ADR doit contenir :

- contexte et problème ;
- exigences concernées ;
- options évaluées ;
- critères de comparaison ;
- décision ;
- conséquences positives et négatives ;
- impacts sécurité, disponibilité, coûts et exploitation ;
- impacts Terraform, CI/CD et tests ;
- stratégie de migration et rollback ;
- preuves nécessaires ;
- statut `Proposed`, `Accepted`, `Superseded` ou `Rejected`.

Une expérimentation peut être exigée avant décision, mais elle doit être bornée et ne pas être confondue avec une implémentation de production.

## 3. ADR bloquants pour le HLD

| ID | Décision à instruire | Questions principales | Gate |
|---|---|---|---|
| V2-ADR-001 | Ingress et frontière de sécurité | API Gateway, façade Lambda, FastAPI/ECS, streaming, identité de confiance | V2-G1 |
| V2-ADR-002 | Répartition FastAPI / AgentCore Runtime | orchestration, retrieval, sessions, responsabilités et contrats | V2-G1 |
| V2-ADR-003 | RAG applicatif avec S3 Vectors | index, filtres, métadonnées, citations, suppression et qualité | V2-G1 |
| V2-ADR-004 | Pipeline d’ingestion documentaire | événement, workers, état, idempotence, reprise et quarantaine | V2-G1 |
| V2-ADR-005 | Agents et framework d’orchestration | mono/multi-agent, adapter Strands/LangGraph, budgets et fallback | V2-G1 |
| V2-ADR-006 | Identité, autorisation et isolation | utilisateur/tenant, claims, scopes, clés de partition et audit | V2-G1 |
| V2-ADR-007 | Architecture réseau et calcul ECS | subnets, endpoints, egress, EC2/Fargate, autoscaling et coûts | V2-G1 |
| V2-ADR-008 | Observabilité et contexte distribué | OpenTelemetry, propagation, redaction, SLO et coûts | V2-G1 |
| V2-ADR-009 | GitLab CI et promotion | OIDC, artefacts, environnements, parité et retrait GitHub Actions | V2-G1 |
| V2-ADR-010 | Sauvegarde, restauration et réhydratation | S3, DynamoDB, S3 Vectors, Memory, RTO/RPO et tests | V2-G1 |

## 4. Détail des premières décisions

### V2-ADR-001 — Ingress et frontière de sécurité

#### Options initiales

1. conserver API Gateway et Lambda Security Facade devant AgentCore Runtime, FastAPI étant appelé pour les capacités applicatives ;
2. API Gateway vers FastAPI/ECS, qui devient la frontière applicative et invoque AgentCore Runtime ;
3. routage hybride API Gateway vers façade Lambda pour la conversation et vers FastAPI pour les documents ;
4. autre variante uniquement si elle conserve une identité de confiance serveur et n’expose pas Runtime au navigateur.

#### Critères

- sécurité de l’identité ;
- streaming ;
- latence ;
- coûts ;
- complexité opérationnelle ;
- testabilité ;
- compatibilité V1 ;
- rollback.

### V2-ADR-002 — Répartition FastAPI / Runtime

#### Questions

- où vit l’orchestrateur applicatif ;
- qui exécute le retrieval ;
- qui construit le contexte modèle ;
- qui gère les sessions et deadlines ;
- comment éviter les responsabilités dupliquées ;
- quel contrat unit FastAPI et Runtime ;
- quelles capacités restent disponibles si Runtime ou RAG est indisponible.

### V2-ADR-003 — RAG S3 Vectors

#### Questions

- schéma des vecteurs et références de chunks ;
- stratégie de filtres d’autorisation ;
- métadonnées DynamoDB ;
- versionnement du modèle d’embedding et du chunking ;
- suppression et réindexation ;
- citations ;
- dataset et métriques de qualité ;
- stratégie de réhydratation.

### V2-ADR-004 — Ingestion

#### Options initiales

- worker ECS déclenché par file ou événement ;
- orchestration AWS managée non agentique si justifiée ;
- traitement synchrone uniquement pour petits documents, avec bascule asynchrone ;
- autre mécanisme démontrant idempotence, visibilité et reprise.

L’ingestion ne doit pas être implémentée dans AgentCore Runtime.

### V2-ADR-005 — Agents et orchestration

#### Questions

- un orchestrateur unique suffit-il ;
- quels agents spécialisés ont une responsabilité distincte ;
- quel adapter commun expose les interfaces applicatives ;
- comment limiter les boucles, tokens et tools ;
- comment tester sans dépendance Bedrock ;
- quelles règles de fallback modèle.

Le choix ne peut pas conduire à utiliser Bedrock managed Agents.

### V2-ADR-006 — Identité et isolation

#### Questions

- utilisateur simple ou tenant + utilisateur ;
- claims Cognito autorisés ;
- représentation interne et hash ;
- partitionnement S3, S3 Vectors, DynamoDB et Memory ;
- propagation vers Runtime et tools ;
- suppression et audit ;
- tests cross-user/cross-tenant.

### V2-ADR-007 — ECS

#### Questions

- VPC et subnets ;
- endpoints privés ;
- stratégie egress ;
- launch type EC2, Fargate ou combinaison ;
- identités IAM par workload ;
- contrôleurs nécessaires ;
- autoscaling ;
- coûts permanents ;
- disponibilité multi-AZ.

### V2-ADR-008 — Observabilité

#### Questions

- propagation W3C Trace Context ;
- corrélation avec requestId et operationId ;
- instrumentation FastAPI, agents, Bedrock, retrieval et MCP ;
- redaction ;
- échantillonnage ;
- rétention ;
- SLO et error budgets ;
- coûts CloudWatch.

### V2-ADR-009 — GitLab CI

#### Questions

- structure des pipelines ;
- OIDC et rôles par environnement ;
- promotion du même artefact ;
- Terraform plan/apply ;
- SBOM et signature ;
- secrets ;
- preuves ;
- stratégie de coexistence avec GitHub Actions.

### V2-ADR-010 — Reprise

#### Questions

- versioning S3 ;
- PITR DynamoDB ;
- export/import et restauration ;
- réhydratation S3 Vectors ;
- sauvegarde de configuration ;
- cohérence des documents, métadonnées et vecteurs ;
- RTO/RPO ;
- fréquence et preuves des tests.

## 5. ADR complémentaires prévus

| ID | Sujet | Dépendance |
|---|---|---|
| V2-ADR-011 | Streaming des réponses et gestion des annulations — **rédigé, `Draft` en attente de revue** (`V2-ADR-011-streaming-annulations.md`) | V2-ADR-001, V2-ADR-002 |
| V2-ADR-012 | Modèles Bedrock, profils d’inférence et fallback — **rédigé, `Draft` en attente de revue** (`V2-ADR-012-modeles-bedrock-fallback.md`) | V2-ADR-005, V2-ADR-011 |
| V2-ADR-013 | Embeddings Bedrock et stratégie de versionnement — **rédigé, `Draft` en attente de revue** (`V2-ADR-013-embeddings-versionnement.md`) | V2-ADR-003, V2-ADR-010, V2-ADR-012, V2-ADR-019 |
| V2-ADR-014 | Confirmation forte et objet de commande — **rédigé, `Draft` en attente de revue** (`V2-ADR-014-confirmation-commande-signee.md`). L'intitulé initial disait « objet de commande signé » ; la décision retenue ne transporte pas le contenu de la commande, donc ne le signe pas | V2-ADR-002, V2-ADR-005, V2-ADR-006, V2-ADR-010, V2-ADR-011 |
| V2-ADR-015 | Politique de mémoire et droit à l’effacement — **rédigé, `Draft` en attente de revue** (`V2-ADR-015-memoire-droit-effacement.md`) | V2-ADR-002, V2-ADR-005, V2-ADR-006, V2-ADR-010, V2-ADR-014 |
| V2-ADR-016 | WAF, quotas et protection contre les abus — **rédigé, `Draft` en attente de revue** (`V2-ADR-016-waf-quotas-protection-abus.md`) | V2-ADR-001, V2-ADR-006, V2-ADR-011, V2-ADR-012, V2-ADR-014 |
| V2-ADR-017 | Classification documentaire et conservation | V2-ADR-003, V2-ADR-006 |
| V2-ADR-018 | Stratégie de tests RAG et seuils de qualité | V2-ADR-003, V2-ADR-013 |

## 6. Priorité d’instruction

### Lot A — Frontière et responsabilités

- V2-ADR-001 ;
- V2-ADR-002 ;
- V2-ADR-006.

### Lot B — Plateforme et données

- V2-ADR-007 ;
- V2-ADR-003 ;
- V2-ADR-004 ;
- V2-ADR-010.

### Lot C — Agents et exploitation

- V2-ADR-005 ;
- V2-ADR-008 ;
- V2-ADR-009.

L’instruction peut être parallèle, mais les dépendances doivent être respectées avant acceptation.

## 7. Critère de sortie

Le backlog initial est considéré traité lorsque les dix ADR bloquants sont `Accepted`, `Rejected` avec alternative acceptée, ou associés à une expérimentation courte dont les critères de décision sont définis. Le HLD ne peut pas passer en statut `Approved` tant qu’un ADR bloquant reste ambigu.
