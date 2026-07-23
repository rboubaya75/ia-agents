# HLD — Secure AgentCore V2

- **Version :** 0.3
- **Branche :** `migration/secure-agentcore-v2`
- **Baseline :** Secure AgentCore V1 au commit `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut :** Draft — architecture cible à instruire par ADR
- **Environnement initial :** `test`

## 1. Résumé exécutif

La V2 étend la plateforme agentique V1 avec un backend applicatif FastAPI sur ECS/Fargate, un RAG applicatif fondé sur S3 Vectors, un pipeline d’ingestion documentaire, des agents custom découplés de leur framework et une observabilité distribuée OpenTelemetry/CloudWatch.

Le HLD ne remplace pas les ADR. Les points structurants encore ouverts sont explicitement listés et doivent être décidés avant passage du document au statut `Approved`.

## 2. Baseline As-Is V1

```text
Browser / React
  -> CloudFront / S3 privé
  -> Cognito
  -> API Gateway HTTP API
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
       -> Bedrock
       -> AgentCore Memory
       -> AgentCore Gateway MCP
            -> Trip Tools Lambda
            -> DynamoDB Trips
```

Garanties à préserver :

- identité de confiance construite côté serveur ;
- Runtime non exposé au navigateur ;
- IAM least privilege ;
- Gateway MCP réservée aux tools ;
- confirmation et idempotence des mutations ;
- logs redacted ;
- tests de contrats et qualité industrielle.

## 3. Architecture To-Be V2 — vue logique initiale

```text
Utilisateurs
  -> Route 53 / domaine applicatif
  -> CloudFront + WAF
       -> S3 privé : frontend React
       -> API Gateway : front-door API
            -> couche de sécurité et routage à décider par ADR
                 -> FastAPI sur ECS/Fargate
                      -> services conversation, documents et administration
                      -> orchestrateur applicatif
                      -> pipeline d’ingestion
                      -> retrieval applicatif
                 -> AgentCore Runtime IAM-only
                      -> agents custom sous /agents
                      -> Bedrock Converse API
                      -> AgentCore Memory
                      -> AgentCore Gateway MCP AWS_IAM
                           -> tools métier

Données
  -> S3 : documents sources et artefacts d’ingestion
  -> S3 Vectors : index vectoriel
  -> DynamoDB : métadonnées, états d’ingestion, idempotence et données métier
  -> CloudWatch : logs, métriques et traces exportées via OpenTelemetry
  -> Secrets Manager / KMS : secrets et chiffrement
```

## 4. Principes d’architecture

1. Le navigateur reste une zone non fiable.
2. L’identité de confiance est dérivée et reconstruite côté serveur.
3. AgentCore Runtime est uniquement le runtime d’exécution des agents custom.
4. Bedrock managed Agents et Bedrock Knowledge Bases ne sont pas utilisés.
5. Le retrieval est une capacité applicative contrôlée.
6. Les contenus documentaires et Memory sont traités comme données non fiables.
7. Les frameworks d’agents sont encapsulés derrière un adapter.
8. Les mutations sont confirmées, idempotentes et non rejouées après effet de bord.
9. Les flux sont observables de bout en bout sans exposer les données sensibles.
10. L’infrastructure et les déploiements sont déclaratifs et reproductibles.

## 5. Composants et responsabilités

| Composant | Responsabilité cible V2 |
|---|---|
| React / TypeScript / Vite | Interface, streaming, documents, citations, préférences et confirmations |
| S3 privé | Assets frontend et documents sources selon buckets séparés |
| CloudFront | Distribution, TLS, OAC, cache et headers de sécurité |
| WAF | Protection L7, limitation et règles managées/custom selon risques |
| Cognito | Authentification et émission des tokens |
| API Gateway | Front-door API, JWT, CORS, throttling, logs et routage |
| Couche d’ingress sécurisée | Reconstruction de l’identité, schémas, quotas et normalisation ; forme à décider par ADR |
| FastAPI sur ECS/Fargate | APIs applicatives, documents, orchestration, administration et contrôles métier |
| ECS (Fargate) | Runtime des services applicatifs non agentiques et workers |
| AgentCore Runtime | Exécution des agents custom et intégration modèle/Memory/tools |
| Bedrock Converse API | Invocation des modèles configurables |
| AgentCore Memory | Préférences et mémoire autorisée, isolée par acteur |
| AgentCore Gateway MCP | Exposition gouvernée des tools |
| S3 Vectors | Recherche vectorielle applicative |
| DynamoDB | Métadonnées documentaires, états, idempotence et données métier |
| OpenTelemetry | Instrumentation standard des traces, métriques et logs |
| CloudWatch | Centralisation, dashboards, alarmes et investigations |
| Terraform | Provisionnement AWS, y compris définitions de tâches et services ECS |
| GitLab CI | Qualité, sécurité, plan, build, promotion et déploiement via OIDC AWS |

## 6. Flux principaux

### 6.1 Conversation avec retrieval

```text
1. Browser -> API Gateway : token Cognito + message + session + operationId
2. Ingress sécurisé : validation, identité de confiance, quotas et deadline
3. FastAPI : politique de parcours et contexte applicatif
4. Retrieval : recherche S3 Vectors avec filtres d’autorisation
5. DynamoDB/S3 : résolution des métadonnées et extraits sources
6. AgentCore Runtime : contexte contrôlé, références et identité de confiance
7. Agent custom -> Bedrock Converse API
8. Agent custom -> Gateway MCP si tool autorisé
9. Réponse : contenu, citations, operationId et référence de corrélation
10. Streaming ou réponse synchrone selon ADR et LLD
```

### 6.2 Ingestion documentaire

```text
1. Browser -> API : demande d’upload autorisée
2. Document -> S3 source privé
3. Événement d’ingestion -> worker ECS ou service asynchrone à décider
4. Validation de sécurité et détection du type
5. Parsing et normalisation
6. Chunking versionné
7. Embeddings Bedrock
8. Écriture S3 Vectors
9. Écriture métadonnées et état DynamoDB
10. Publication du statut et des métriques
```

L’ingestion doit être idempotente, reprenable et capable de supprimer ou réindexer un document sans laisser d’éléments orphelins.

### 6.3 Mutation via tool MCP

```text
1. Agent sélectionne un tool autorisé
2. Runtime écrase l’identité et le contexte d’opération
3. Confirmation vérifiée pour les mutations
4. Appel Gateway MCP signé IAM
5. Tool valide le schéma et la deadline
6. Ledger d’idempotence vérifié
7. Effet de bord atomique
8. Résultat redacted et corrélé
9. Aucun replay de l’agent après démarrage confirmé de la mutation
```

### 6.4 Diagramme de flux de données (question → réponse)

Vue de bout en bout du flux 6.1, avec embranchement vers le flux 6.3 lorsqu'un tool est requis.

```text
Question utilisateur
        │  FastAPI : validation du contrat, sélection du parcours
        ▼
Retrieval (S3 Vectors, filtres d'autorisation par tenant/acteur)
        │  DynamoDB / S3 : résolution des métadonnées et extraits sources
        ▼
Prompt Context Assembly (FastAPI)
        │  retrievalContext borné, trust=untrusted, status ∈ {ok, degraded, skipped}
        ▼
Contrat interne FastAPI → AgentCore Runtime
        ▼
AgentCore Runtime : Prompt Construction + Bedrock Converse Invocation
        │
        ├─ pas de tool requis ─────────────────────► Réponse : contenu, citations
        │                                             operationId, référence de
        │                                             corrélation
        │
        └─ tool requis (flux 6.3)
                │  Tool Selection, confirmation si mutation
                ▼
        AgentCore Gateway MCP (identité injectée par Runtime)
                ▼
        Tool métier : lecture ou mutation confirmée et idempotente
                ▼
        Résultat structuré, redacted, corrélé
                ▼
        Réponse finale : contenu, citations, operationId, référence de corrélation
```

Chaque étape correspond à une capacité attribuée par la
[CAM](capability-allocation-matrix.md) : Retrieval (Domaine 4), Prompt Context Assembly
(Domaine 4), Prompt Construction et Bedrock Converse Invocation (Domaine 5), Tool Selection
(Domaine 5), exécution du tool (Domaine 7).

## 7. Identité et zones de confiance

### 7.1 Diagramme des zones de confiance

```text
┌──────────────── Zone non fiable ────────────────┐
│ Browser / React                                  │
└───────────────────────┬───────────────────────────┘
                         │ HTTPS + JWT Cognito
                         ▼
┌──────────────── Zone périmétrique ──────────────┐
│ CloudFront + WAF                                  │
└───────────────────────┬───────────────────────────┘
                         ▼
┌──────────────── Zone contrôlée (edge) ──────────┐
│ API Gateway                                       │
│  - validation JWT (signature, exp, aud, iss)      │
│  - extraction des claims                          │
└───────────────────────┬───────────────────────────┘
                         │ claims propagés par en-têtes serveur
                         │ (jamais le JWT lui-même au-delà de ce point)
                         ▼
┌──────────────── Zone applicative ───────────────┐
│ FastAPI sur ECS/Fargate                           │
│  - autorisation métier (RBAC/ABAC)                │
│  - retrieval, construction du contexte RAG        │
└───────────────────────┬───────────────────────────┘
                         │ contrat interne (trustedIdentity, sans JWT)
                         ▼
┌──────────────── Zone agentique (IAM-only) ──────┐
│ AgentCore Runtime                                 │
│  - boucle agentique, Memory, sélection de tools   │
└──────┬─────────────────────────────────┬──────────┘
       │ SigV4                           │ SigV4
       ▼                                 ▼
┌─────────────────┐              ┌─────────────────────┐
│ Bedrock          │              │ AgentCore Gateway     │
│ Converse API     │              │ MCP                   │
└─────────────────┘              └──────────┬───────────┘
                                             ▼
                                  ┌─────────────────────┐
                                  │ Tools métier           │
                                  │ (ex. Trip Tools)       │
                                  └─────────────────────┘
```

Aucune zone ne fait confiance à la validation réalisée par la zone amont (défense en profondeur,
cf. Domaine 10 — Security de la [CAM](capability-allocation-matrix.md)) : FastAPI revalide les
contrats même si API Gateway a déjà validé le JWT, et les tools valident l'identité injectée même
si Runtime l'a déjà construite.

### 7.2 Zone non fiable

- navigateur ;
- prompt utilisateur ;
- documents ingérés ;
- contenu Memory ;
- réponses de services externes ;
- paramètres fournis aux tools avant écrasement serveur.

### 7.3 Zone contrôlée

- API Gateway après validation JWT ;
- couche d’ingress sécurisée ;
- workloads ECS identifiés ;
- AgentCore Runtime avec resource policy ;
- Gateway MCP avec resource policy ;
- tools autorisés et données filtrées par identité.

### 7.4 Règle d’identité

Le principe V1 reste la baseline : l’acteur provient d’un claim Cognito validé et n’est jamais accepté depuis le payload métier. Le modèle multi-tenant, les scopes et la représentation interne de l’identité doivent être décidés par ADR.

### 7.5 Diagramme des flux d'identité

```text
JWT Cognito (id_token)
        │  Cognito Authorizer : signature, expiration, audience, issuer
        ▼
Claims (sub, custom:tenantId, rôles)
        │  API Gateway : extraction, puis propagation par en-têtes serveur
        │  dédiés (jamais dans le corps de la requête, jamais l'en-tête
        │  Authorization au-delà de ce point)
        ▼
FastAPI : Actor Identity Resolution + Tenant Resolution
        │  + Business Authorization (RBAC/ABAC)
        ▼
trustedIdentity { actorId, tenantId }
        │  contrat interne FastAPI -> AgentCore Runtime (sans JWT, sans claim brut)
        ▼
AgentCore Runtime : injection serveur de l'identité
        │  écrase tout contexte d'identité produit par le modèle ou l'agent
        ▼
Tool Identity (identité injectée, jamais fournie par l'agent ou l'utilisateur)
        │  appel signé IAM (SigV4)
        ▼
IAM Role scoping : resource policy Gateway -> rôle Runtime -> tool exact
```

Chaque flèche correspond à une capacité de la [CAM](capability-allocation-matrix.md) (Domaine 1 —
Identity & Access Management) : ce diagramme est la vue dynamique de ce que la CAM attribue de
façon statique.

## 8. Architecture ECS initiale

La cible prévoit :

- plusieurs zones de disponibilité ;
- launch type Fargate (`V2-ADR-007`) ;
- services ECS séparés par fonction ;
- rôles IAM de tâche par workload (Task IAM Roles) ;
- Security Groups par tâche (réseau `awsvpc` natif à Fargate) ;
- ingress interne contrôlé ;
- autoscaling (ECS Service Auto Scaling) ;
- déploiements contrôlés (`minimumHealthyPercent`, circuit breaker ECS) ;
- probes de santé (health checks conteneur et cible du load balancer) ;
- graceful shutdown ;
- images ECR immuables et scannées ;
- secrets récupérés depuis Secrets Manager.

Le LLD plateforme doit définir les choix réseau, calcul, endpoints privés, DNS, certificats, contrôleurs et règles d’egress.

## 9. Architecture RAG

### Stockages

- S3 source : document original, version, hash et état de conservation ;
- S3 Vectors : embeddings et références de chunks ;
- DynamoDB : document, version, statut, propriétaire, classification, métadonnées et clés d’idempotence.

### Contrôles

- allowlist des formats ;
- limites de taille ;
- validation de contenu ;
- extraction bornée ;
- chunking versionné ;
- modèle d’embedding configurable ;
- filtres obligatoires par identité/tenant ;
- citations issues de sources autorisées ;
- suppression coordonnée ;
- protections contre prompt injection et empoisonnement.

### Qualité

La réception RAG exige un dataset versionné et des métriques telles que recall@k, precision@k, groundedness, couverture des citations et taux de refus lorsque les sources sont insuffisantes.

## 10. Architecture agents

- code sous `/agents` ;
- logique métier indépendante de Strands ou LangGraph ;
- adapter explicite ;
- orchestrateur minimal par défaut ;
- agent spécialisé uniquement avec responsabilité et bénéfice démontrés ;
- prompts versionnés ;
- Bedrock Converse API ;
- budgets de tokens, tours, temps et tools ;
- tool allowlists ;
- traces de décision sans chaîne de pensée sensible ;
- fallback et dégradation contrôlée.

## 11. Données et cycle de vie

Les catégories suivantes sont séparées :

- documents sources ;
- chunks et vecteurs ;
- métadonnées et états d’ingestion ;
- conversations et sessions ;
- préférences Memory ;
- données métier ;
- traces et preuves.

Chaque catégorie doit disposer d’un propriétaire technique, d’une politique de rétention, d’un chiffrement, d’un mécanisme de suppression, d’une stratégie de sauvegarde et d’un test de restauration.

## 12. Sécurité

Le HLD impose au minimum :

- WAF ;
- JWT Cognito et autorisation applicative ;
- IAM least privilege et resource policies ;
- KMS ;
- Secrets Manager ;
- segmentation réseau ECS (Security Groups par tâche) ;
- contrôle de l’egress ;
- images signées et SBOM ;
- validation des uploads ;
- défense contre prompt injection, data poisoning et exfiltration ;
- redaction centralisée ;
- audit des appels modèles, retrieval et tools ;
- tests négatifs multi-utilisateur ou multi-tenant.

## 13. Observabilité et FinOps

La corrélation cible couvre :

```text
Browser -> API Gateway -> FastAPI -> Retrieval -> AgentCore Runtime
        -> Bedrock -> Gateway MCP -> Tools -> Données
```

Attributs de corrélation :

- `traceId` ;
- `requestId` ;
- `operationId` hashé ;
- `sessionId` hashé ;
- identité ou tenant hashé ;
- version du document, modèle, prompt système et agent ;
- tool et statut ;
- durée et nombre de retries.

Métriques :

- time-to-first-token ;
- latence totale et par composant ;
- tokens entrée/sortie ;
- coût estimé ;
- embeddings générés ;
- qualité et latence du retrieval ;
- saturation ECS ;
- throttling ;
- erreurs, refus et dégradations ;
- volume et coût de stockage.

## 14. Disponibilité, sauvegarde et reprise

- architecture ECS multi-AZ ;
- autoscaling et déploiements contrôlés (`minimumHealthyPercent`) ;
- retries bornés avec jitter pour opérations sûres ;
- idempotence des traitements asynchrones ;
- PITR DynamoDB ;
- versioning S3 ;
- procédure de réhydratation S3 Vectors ;
- sauvegarde des configurations ;
- stratégie de rollback applicative (nouvelle révision de task definition) ;
- tests périodiques de restauration ;
- RTO/RPO à décider selon cas d’usage.

## 15. CI/CD cible

```text
Commit
  -> lint, typecheck, unit tests
  -> secret scan, SAST, dépendances, SBOM
  -> build image immutable et signature
  -> Terraform fmt/init/validate/plan
  -> déploiement contrôlé par environnement (nouvelle révision de task definition ECS)
  -> tests smoke et E2E
  -> preuves archivées
  -> promotion du même artefact
```

GitLab CI avec OIDC AWS est la cible. Les workflows GitHub Actions V1 ne sont retirés qu’après démonstration de parité fonctionnelle et sécuritaire.

## 16. Transition V1 vers V2

### Réutilisé initialement

- frontend et identité Cognito ;
- API Gateway comme front-door ;
- principes de la façade sécurisée ;
- AgentCore Runtime IAM-only ;
- Memory ;
- Gateway MCP ;
- tools Trips ;
- DynamoDB ;
- contrôles de tests V1.

### Ajouté

- ECS et FastAPI ;
- RAG S3 Vectors ;
- ingestion ;
- agents custom structurés ;
- OpenTelemetry ;
- WAF ;
- cible GitLab CI.

### À décider

- maintien exact de la Lambda Security Facade ;
- chemin synchrone ou streaming ;
- placement de l’orchestration entre FastAPI et Runtime ;
- mécanisme d’événement d’ingestion ;
- modèle utilisateur ou tenant ;
- dimensionnement fin du calcul ECS (tailles de tâche, capacité) ;
- migration des données et préférences.

## 17. Décisions ouvertes bloquantes

- V2-ADR-001 : ingress et frontière de sécurité ;
- V2-ADR-002 : responsabilités FastAPI versus AgentCore Runtime ;
- V2-ADR-003 : architecture RAG S3 Vectors ;
- V2-ADR-004 : pipeline d’ingestion et reprise ;
- V2-ADR-005 : orchestration agents et adapter ;
- V2-ADR-006 : modèle d’identité et isolation ;
- V2-ADR-007 : réseau et calcul ECS ;
- V2-ADR-008 : observabilité et propagation du contexte ;
- V2-ADR-009 : GitLab CI et promotion ;
- V2-ADR-010 : sauvegarde, restauration et réhydratation.

## 18. Critère de validation du HLD

Le HLD peut passer en statut `Approved` lorsque :

- les exigences majeures sont traçables ;
- les ADR bloquants sont décidés ;
- les flux et frontières de confiance sont complets ;
- l’analyse As-Is / To-Be est validée ;
- les choix de disponibilité, sécurité, coûts et exploitation sont cohérents ;
- le catalogue LLD couvre tous les domaines nécessaires ;
- les risques résiduels sont explicitement acceptés ou planifiés.
