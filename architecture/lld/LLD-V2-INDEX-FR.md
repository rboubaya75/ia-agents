# Catalogue des LLD — Secure AgentCore V2

- **Version :** 0.5
- **Branche cible :** `migration/secure-agentcore-v2`
- **Statut :** Draft
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md`
- **Backlog ADR :** `architecture/adr/V2-ADR-BACKLOG-FR.md`

## 1. Objet

Ce document définit les dix Low-Level Designs canoniques de la V2, leur contenu minimal, leurs dépendances ADR exactes et leurs gates. Il ne remplace pas les LLD de domaine ; il constitue le contrat de complétude et de traçabilité.

## 2. Règles de gouvernance

Un composant structurant ne peut être implémenté que si :

1. le HLD V2 est `Approved` ;
2. les ADR applicables au composant sont décidés ;
3. le LLD du domaine est `Approved` ;
4. les exigences, risques et critères de test sont traçables ;
5. les risques résiduels sont acceptés ou associés à un plan de traitement.

Une dépendance ADR marquée dans ce catalogue est bloquante lorsqu'elle affecte la tranche considérée. Un ADR complémentaire non applicable doit être explicitement marqué `Non applicable` dans le LLD, avec justification.

## 3. Catalogue canonique et dépendances ADR

| ID | LLD | Portée | Dépendances ADR exactes | Statut |
|---|---|---|---|---|
| V2-LLD-001 | Plateforme AWS, réseau, ECS et FastAPI | VPC, ECS, compute, ingress, type d'API Gateway et transport du streaming, ancrage de confiance de l'identité et validation JWKS, chemin unique et attachement du WAF, DNS, IAM workload, secrets, politique de clé des groupes de journaux | V2-ADR-001, V2-ADR-006, V2-ADR-007, V2-ADR-008, V2-ADR-009, V2-ADR-011, V2-ADR-016, V2-ADR-019, V2-ADR-020 | v0.3 (Draft) |
| V2-LLD-002 | RAG et ingestion documentaire | S3, ingestion KB (V2) / applicative (V3), chunking, embeddings, S3 Vectors, DynamoDB, suppression | V2-ADR-019, V2-ADR-003, V2-ADR-004, V2-ADR-006, V2-ADR-010, V2-ADR-013, V2-ADR-014, V2-ADR-017, V2-ADR-018 | v0.5 (Draft) |
| V2-LLD-003 | Agents et orchestration | `/agents`, adapter, Converse API, prompts, budgets, streaming, annulations, fallback | V2-ADR-002, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-011, V2-ADR-012 | v0.5 (Draft) |
| V2-LLD-004 | AgentCore Gateway MCP et tools | catalogue, schémas, IAM, confirmation, idempotence, retry | V2-ADR-002, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-014 | À créer |
| V2-LLD-005 | Identité, sécurité et conformité | Cognito, contrat de validation du token (JWKS, cache, borne de tolérance, claims requis, politique de refus), autorisation, tenant, KMS, WAF et mécanisme de chemin unique, threat model, audit, rétention du journal d'effacement et rejeu après restauration, autorisation sur lecture directe par niveau de classification | V2-ADR-001, V2-ADR-006, V2-ADR-007, V2-ADR-008, V2-ADR-010, V2-ADR-014, V2-ADR-015, V2-ADR-016, V2-ADR-017, V2-ADR-020 | v0.1 (Draft) |
| V2-LLD-006 | Données, mémoire, rétention et restauration | modèles, cycle de vie, TTL, backup, effacement et fenêtre résiduelle, journal d'audit d'effacement, rejeu après restauration, espace d'embedding, réhydratation | V2-ADR-019, V2-ADR-003, V2-ADR-004, V2-ADR-006, V2-ADR-010, V2-ADR-013, V2-ADR-014, V2-ADR-015, V2-ADR-017 | v0.4 (Draft) |
| V2-LLD-007 | Observabilité, SLO et FinOps | OTel, CloudWatch, corrélation, alertes, coûts, SLO | V2-ADR-002, V2-ADR-003, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-009, V2-ADR-012, V2-ADR-013 | À créer |
| V2-LLD-008 | CI/CD, Terraform et promotion | GitLab CI, OIDC, artefacts, scans, plan, rollback | V2-ADR-007, V2-ADR-008, V2-ADR-009, V2-ADR-010 | À créer |
| V2-LLD-009 | Stratégie de tests et preuves | pyramide, datasets, E2E, sécurité, charge, chaos, DR | V2-ADR-001 à V2-ADR-019 selon applicabilité, avec V2-ADR-018 obligatoire pour le RAG | À créer |
| V2-LLD-010 | Frontend React V2 | streaming, uploads, citations, auth, reprise, accessibilité | V2-ADR-001, V2-ADR-002, V2-ADR-006, V2-ADR-008, V2-ADR-011, V2-ADR-014, V2-ADR-016 | À créer |

## 4. Structure minimale d'un LLD

### 4.1 Métadonnées

- version, statut et branche ;
- HLD et ADR de référence ;
- exigences et risques couverts ;
- périmètre, exclusions et dépendances ;
- décision explicite sur chaque ADR applicable ou non applicable.

### 4.2 Architecture détaillée

- composants et responsabilités ;
- diagrammes de déploiement et de séquence ;
- flux synchrones et asynchrones ;
- zones de confiance ;
- dépendances internes et externes.

### 4.3 Contrats

- OpenAPI, événements ou schémas MCP ;
- formats d'identifiants ;
- validation et champs interdits ;
- versionnement et compatibilité ;
- codes d'erreur ;
- idempotence et sémantique de retry.

### 4.4 Configuration

- variables et feature flags ;
- secrets ;
- limites, quotas et paramètres de capacité ;
- timeouts et retries ;
- configuration par environnement.

### 4.5 Sécurité

- authentification et autorisation ;
- IAM exact et resource policies ;
- chiffrement ;
- contrôles réseau et egress ;
- classification des données ;
- redaction ;
- menaces et contrôles associés.

### 4.6 Résilience

- dépendances critiques ;
- comportement en panne ;
- circuit breakers ;
- reprise et idempotence ;
- rollback ;
- sauvegarde, restauration et réhydratation ;
- RTO/RPO lorsque pertinent.

### 4.7 Observabilité et coûts

- logs structurés ;
- métriques et traces ;
- attributs de corrélation ;
- dashboards et alertes ;
- SLO et error budgets ;
- métriques de coûts et capacité.

### 4.8 Tests et preuves

- exigences et risques couverts ;
- tests unitaires, contrats, intégration et E2E ;
- sécurité négative ;
- performance, charge et résilience ;
- restauration ;
- preuves redacted, versionnées et conservées.

### 4.9 Exploitation

- runbooks ;
- procédures de déploiement et rollback ;
- diagnostic et maintenance ;
- responsabilités techniques sans inventer d'organisation réelle.

## 5. Attendus par LLD

### V2-LLD-001 — Plateforme AWS, réseau, ECS et FastAPI

Doit définir : topologie VPC et subnets, endpoints AWS, egress, dimensionnement du calcul ECS, services, identités de workloads (Task IAM Roles), Security Groups, ingress/API Gateway, DNS, certificats, autoscaling, déploiements contrôlés, health, readiness et graceful shutdown.

Conformément à `V2-ADR-011`, la route conversationnelle est servie par un API Gateway **REST API Regional** en mode `responseTransferMode = STREAM` via **VPC Link V2** vers l'ALB interne. L'`idle_timeout` de l'ALB et l'intervalle de keep-alive SSE sont liés par un invariant vérifié au plan, et l'ALB est délibérément la contrainte la plus serrée de la chaîne.

Conformément à `V2-ADR-020`, l'identité n'est pas ce que la passerelle affirme mais ce que FastAPI vérifie : l'authorizer Cognito rejette le trafic non authentifié, et FastAPI établit l'identité en validant elle-même la signature du token contre le **JWKS Cognito**. Aucun en-tête d'identité n'est lu — les familles `X-Amzn-Oidc-*` et `X-Claims-*` sont retirées du corpus. La frontière du token est **FastAPI, exactement** : `Authorization` est transmis sur le seul segment passerelle → FastAPI, et jamais journalisé. L'indisponibilité du JWKS **refuse** au-delà d'une borne de tolérance déclarée en heures ; elle n'hérite pas de l'exception au refus par défaut que `V2-ADR-016` borne au compteur de quota.

Conformément à `V2-ADR-016`, le LLD porte l'exigence de **chemin unique** CloudFront → API Gateway et statue sur l'**attachement du WAF** au type d'API retenu — deux préconditions bloquantes. Le type d'API est unifié sur REST API pour disposer d'un point d'attachement WAF unique, l'identité étant désormais invariante au type d'API.

La politique de clé KMS des groupes de journaux couvre explicitement le journal d'audit d'effacement de `V2-LLD-006 §8.6`, qui ne vit pas sous le préfixe `/ecs/` : son omission ferait échouer la création du groupe et vaudrait précondition P3 non satisfaite.

### V2-LLD-002 — RAG et ingestion

Doit définir : formats et tailles, upload et quarantaine, validation et antivirus, parsing, chunking versionné, embeddings Bedrock configurables, schéma S3 Vectors, métadonnées DynamoDB, idempotence, suppression, réindexation, réhydratation, filtres d'isolation, citations, dataset et métriques d'évaluation.

Conformément à `V2-ADR-019`, la phase V2 délègue l'ingestion et l'indexation à Bedrock Knowledge Bases adossé à S3 Vectors (FastAPI conservant l'API `Retrieve` uniquement, le post-filtrage tenant/ACL, le `retrievalContext` et les citations) ; le pipeline applicatif SQS + worker ECS de `V2-ADR-003`/`V2-ADR-004` reste la cible V3, réversible via un adapter de magasin vectoriel unique.

### V2-LLD-003 — Agents et orchestration

Doit définir : arborescence `/agents`, interfaces du domaine, adapter Strands/LangGraph, orchestrateur, agents spécialisés, Bedrock Converse API, prompts versionnés, budgets de temps/tokens/tours, fallback, contrôle des tools et traitement du retrieval/Memory comme données non fiables.

### V2-LLD-004 — MCP et tools

Doit définir : catalogue et versionnement, schémas stricts, IAM et resource policies, identité injectée côté serveur, séparation lecture/mutation, confirmation liée à une commande, ledger d'idempotence, retry avant effet de bord uniquement, circuit breaker, versions MCP, logs redacted et preuves.

### V2-LLD-005 — Identité, sécurité et conformité

Doit définir : modèle utilisateur/tenant, claims, scopes, rôles, threat model, WAF, KMS, Secrets Manager, sécurité ECS, egress, sécurité des uploads, prompt injection, data poisoning, exfiltration, audit trail, rétention et effacement.

Doit également couvrir : le contrat complet de validation du token JWKS (algorithme RS256 only, `iss`/`aud` comparés à des valeurs de configuration, `token_use`, cache TTL/borne de tolérance/anti-amplification, comportement en cas d'indisponibilité du JWKS), le mécanisme de chemin unique CloudFront → API Gateway tel que statué en `V2-LLD-001 §7.4`, et l'attachement du WAF avec ses règles de contenu (le LLD-001 ne porte que le point d'attachement).

Réalisé en `V2-LLD-005` v0.1. Le mécanisme de **chemin unique** est un secret injecté par CloudFront, vérifié en **deux points** — une règle WAF sur le stage REST API, et une vérification applicative par FastAPI. Seul le second ne dépend d'aucune précondition : le mécanisme naturel du chemin unique s'attachant au même point que le WAF, les deux préconditions bloquantes de `V2-ADR-016` tomberaient ensemble alors que cet ADR compte sur la seconde pour compenser la première. Le **magasin de compteurs** de quota est DynamoDB, l'admission portant les invocations en vol avec leur échéance plutôt qu'un compteur scalaire, afin qu'une tâche interrompue ne consomme pas définitivement du quota. Le **registre d'autorisation serveur**, indexé par le claim `sub`, est la seule source du `tenantId`, des rôles et de l'état du compte ; il devient de ce fait la **borne de révocation effective** du système, plus courte que la durée de vie du jeton.

Ce LLD relève trois écarts de corpus qu'il tranche, et dont la propagation est portée par des commits distincts du même lot : le `HLD §7.5` et `capability-allocation-matrix.md` Domaine 1 décrivent encore la propagation de claims par en-têtes annulée par `V2-ADR-020` ; `custom:tenantId` en claim obligatoire (`V2-LLD-001 §7.1.3`) contredit la résolution serveur de `V2-ADR-006` et force le jeton d'identité là où l'ADR nomme le jeton d'accès ; la formule de namespace Memory (`V2-LLD-003 §2.5`) reposerait sur un condensat tronqué à 48 bits, adapté aux journaux mais non à une frontière d'isolation. La correction du Domaine 1 amende `V2-ADR-002` (CAM v0.3) ; celle de `V2-LLD-003` retire `roles`/`scopes` de `TrustedIdentity` (v0.6), le filtre d'exposition des tools consommant la `tool_allowlist` résolue par FastAPI.

### V2-LLD-006 — Données et restauration

Doit définir : modèles DynamoDB, clés/index/transactions, catégories de données, TTL, conservation, versioning S3, PITR, Memory sous ses deux natures (session et longue durée), suppression utilisateur, restauration, réhydratation S3 Vectors et cohérence source/métadonnées/index.

Conformément à `V2-ADR-015`, l'effacement utilisateur est logique et immédiat, borné par une fenêtre résiduelle déclarée égale au maximum des fenêtres PITR ; la mémoire longue durée est une donnée personnelle dont la suppression est explicite, vérifiée et bloquante ; le journal d'audit d'effacement est porté par un magasin append-only hors du périmètre PITR, et toute restauration est suivie du rejeu des effacements postérieurs à son instant cible.

Conformément à `V2-ADR-013`, l'index est l'unité de l'espace d'embedding : `embeddingSpaceId` est immuable par index, une reconstruction se fait dans l'espace déclaré par l'index restauré et jamais dans celui de la configuration courante, et un changement d'espace suit la séquence d'index parallèle avec période de grâce.

Conformément à `V2-ADR-019`, la réhydratation S3 Vectors en V2 s'exécute par resynchronisation de la data source Knowledge Bases (`StartIngestionJob`) ; le pipeline applicatif SQS + worker ECS de `V2-ADR-004` reste la cible V3 pour la ré-ingestion massive.

### V2-LLD-007 — Observabilité et FinOps

Doit définir : instrumentation OpenTelemetry, propagation du contexte, schémas de logs, métriques applicatives/RAG/agents, SLO, error budgets, dashboards, alarmes, calcul des coûts estimés, redaction et rétention des preuves.

### V2-LLD-008 — CI/CD

Doit définir : GitLab CI, OIDC AWS, stratégie de branches V2, builds immuables, SBOM, signature, Terraform plan/apply contrôlé, promotion (task definition ECS, retag d'image), secrets, rollback et parité avant retrait de GitHub Actions.

### V2-LLD-009 — Tests

Doit définir : identifiants de risques, matrice de traçabilité, tests unitaires/contrats/intégration/E2E, datasets RAG, tests adversariaux, charge/soak/chaos, restauration, politique de mocks, preuves redacted et rétention.

### V2-LLD-010 — Frontend

Doit définir : architecture React, streaming, citations, upload, suivi d'ingestion, historique, préférences, renouvellement de token, reprise des opérations ambiguës, confirmations, sécurité navigateur, accessibilité et tests.

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
10. `V2-LLD-009` Tests, consolidé au fil de tous les domaines.

Les LLD peuvent progresser en parallèle lorsque leurs ADR et dépendances sont stables.

## 7. Critère de sortie de la gate V2-G2

- les LLD nécessaires à la tranche sont `Approved` ;
- les dix LLD sont suivis dans le catalogue ;
- aucun contrat critique ne reste implicite ;
- les contrôles IAM, réseau, données et sécurité sont détaillés ;
- les tests sont identifiés avant le code ;
- les procédures de rollback et d'exploitation existent ;
- les coûts et limites sont documentés ;
- chaque dépendance ADR est identifiée par son ID exact ;
- les divergences avec le HLD sont résolues par amendement ou ADR.
