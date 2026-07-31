# HLD — Secure AgentCore V2

- **Version :** 0.6
- **Branche :** `migration/secure-agentcore-v2`
- **Baseline :** Secure AgentCore V1 au commit `20d4b12cb4666fe66eefbdf6b1605fe8f74daa03`
- **Statut :** Approved — les vingt ADR du corpus V2 sont `Accepted` (§17) ; six LLD restent à
  rédiger (§18) et dépendent de ce document.
- **Environnement initial :** `test`

## 1. Résumé exécutif

La V2 étend la plateforme agentique V1 avec un backend applicatif FastAPI sur ECS/Fargate, un RAG fondé sur S3 Vectors (via Bedrock Knowledge Bases en phase V2, pipeline applicatif en cible V3 — `V2-ADR-019`), un pipeline d’ingestion documentaire, des agents custom découplés de leur framework et une observabilité distribuée OpenTelemetry/CloudWatch.

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
            -> VPC Link (intégration privée) → ALB interne (`V2-ADR-001`)
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
4. Bedrock managed Agents ne sont pas utilisés. Bedrock Knowledge Bases, adossé à S3 Vectors, est retenu comme implémentation RAG de la phase V2 ; le pipeline applicatif reste la cible V3 (`V2-ADR-019`).
5. Le retrieval est une capacité applicative contrôlée : quelle que soit la phase, FastAPI reste propriétaire du filtrage tenant/ACL et de la construction du contexte, AgentCore Runtime ne faisant jamais de retrieval.
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
| API Gateway | Front-door API, JWT, CORS, throttling, logs et routage. La route conversationnelle est un **REST API en mode `STREAM`** ; les routes non diffusantes peuvent rester sur HTTP API (`V2-ADR-011`, §6.5) |
| Couche d’ingress sécurisée | Reconstruction de l’identité, schémas, quotas et normalisation ; VPC Link → ALB interne → FastAPI (`V2-ADR-001`) |
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
10. Streaming SSE des tokens Bedrock (cf. §6.5) ; les en-têtes de propagation des claims entre API Gateway et FastAPI sont définis en V2-LLD-001
```

### 6.2 Ingestion documentaire

```text
1. Browser -> API : demande d’upload autorisée
2. Document -> S3 source privé
3. Événement SQS -> worker ECS Fargate (service ingestion) (`V2-ADR-004`)
4. Validation de sécurité et détection du type
5. Parsing et normalisation
6. Chunking versionné
7. Embeddings Bedrock
8. Écriture S3 Vectors
9. Écriture métadonnées et état DynamoDB
10. Publication du statut et des métriques
```

L’ingestion doit être idempotente, reprenable et capable de supprimer ou réindexer un document sans laisser d’éléments orphelins.

> **Phasage (`V2-ADR-019`).** Le flux ci-dessus (étapes 3 à 9 : worker ECS, parsing, chunking,
> embeddings, écriture S3 Vectors) est la **cible V3**. En **phase V2**, ces étapes sont assurées
> par Bedrock Knowledge Bases adossé à S3 Vectors : FastAPI déclenche l’ingestion KB
> (`StartIngestionJob`) et interroge KB via l’API `Retrieve`, en conservant le filtrage tenant/ACL
> et la construction du contexte côté serveur. Le module SQS + worker ECS `ingestion` n’est pas
> provisionné en V2. La latence d’ingestion V2 est asynchrone (ordre de la minute) et reflétée dans
> le statut publié à l’étape 10.

### 6.3 Mutation via tool MCP

Une action mutante n’est pas un appel de tool unique : elle est une séquence de quatre temps,
séparée par une décision utilisateur qui n’emprunte pas le chemin du modèle (`V2-ADR-014`).

```text
Temps 1 — Matérialisation (aucun effet de bord)
  1. Agent sélectionne le tool de proposition, autorisé et déclaré `mutating` au catalogue
  2. Runtime écrase l’identité et le contexte d’opération
  3. Appel Gateway MCP signé IAM
  4. Le tool valide le schéma et la deadline, puis normalise les paramètres
  5. Écriture de la commande [ pending ] ; seul le commandId est retourné

Temps 2 — Présentation
  6. FastAPI lit la commande stockée et rend le résumé, transmis dans le flux SSE
     le modèle ne rédige pas ce résumé

Temps 3 — Confirmation (hors du chemin du modèle)
  7. Utilisateur -> API Gateway -> FastAPI, endpoint dédié portant le commandId
  8. Identité de confiance vérifiée ; transition [ pending ] -> [ confirmed ]

Temps 4 — Exécution
  9. Agent appelle le tool d’exécution via Gateway MCP, avec le commandId seul
 10. Le tool charge la commande stockée et ignore tout argument métier du modèle
 11. Transition [ confirmed ] -> [ executed ] et effet de bord dans la même transaction
 12. Résultat redacted et corrélé ; aucun replay après démarrage de la mutation
```

> **Décision de référence (`V2-ADR-014`).** La confirmation n’est plus un booléen de tour vérifié par
> le Runtime : elle porte sur un objet de commande matérialisé par le serveur, et parvient par un
> appel authentifié dont le modèle ne dispose pas. Seul le `commandId` circule — le contenu de la
> commande ne transite ni par le modèle, ni par le client, ni par la Gateway. Une divergence entre ce
> qui est confirmé et ce qui est exécuté n’est donc pas détectée, elle est impossible à produire.

Trois conséquences structurantes de cette séquence :

- **l’état `executed` tient lieu d’enregistrement d’idempotence** pour la mutation qu’il porte. Une
  mutation passée par une commande n’écrit pas d’entrée dans le ledger, qui reste en usage pour les
  opérations sans commande — uploads documentaires et déclenchements d’ingestion ;
- **la classe du tool est une propriété du catalogue**, pas un paramètre d’appel : un tool qui ne
  déclare pas sa classe est traité comme `mutating`, donc inexécutable sans commande confirmée ;
- **une action mutante consomme deux appels de tool au lieu d’un**, ce qui s’impute au budget
  `maxToolCalls` de `V2-ADR-005` et doit être pris en compte dans son calibrage.

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
                │  Tool Selection ; la classe du tool est lue au catalogue
                ▼
        AgentCore Gateway MCP (identité injectée par Runtime)
                │
                ├─ tool `read` ──────────────────────► Résultat structuré,
                │                                       redacted, corrélé
                │
                └─ tool `mutating` : matérialisation de la commande [ pending ]
                        │              aucun effet de bord ; commandId retourné
                        ▼
                Confirmation utilisateur — hors du chemin du modèle
                        │              (§6.3, temps 3 : endpoint FastAPI dédié)
                        ▼
                Tool d’exécution : commandId seul, transition et effet de
                bord dans la même transaction
                        ▼
                Résultat structuré, redacted, corrélé
                        ▼
        Réponse finale : contenu, citations, operationId, référence de corrélation
```

Chaque étape correspond à une capacité attribuée par la
[CAM](capability-allocation-matrix.md) : Retrieval (Domaine 4), Prompt Context Assembly
(Domaine 4), Prompt Construction et Bedrock Converse Invocation (Domaine 5), Tool Selection
(Domaine 5), déclaration de la classe de tool et exécution du tool (Domaine 7). La confirmation
n'est attribuée à aucune capacité du Runtime : elle relève de FastAPI pour l'endpoint et du tool
d'exécution pour la garantie (`V2-ADR-014`).

### 6.5 Streaming des réponses conversationnelles

Le protocole retenu est **Server-Sent Events (SSE)**, standard W3C (`EventSource`), sur HTTP
ordinaire. SSE est adapté car le flux conversationnel est unidirectionnel (serveur → client) : le
navigateur envoie une requête HTTP standard, FastAPI retourne une `StreamingResponse` dont le
contenu progresse au fil des tokens produits par Bedrock Converse API. Le rejet de Lambda par
`V2-ADR-001` reste fondé sur l’incompatibilité de son modèle d’exécution avec un processus serveur
persistant.

**Le protocole ne suffit pas : le type d’API Gateway le contraint (`V2-ADR-011`).** Une
`StreamingResponse` correcte ne produit pas un flux progressif si un intermédiaire du chemin
**tamponne** la réponse. C’est le cas d’**API Gateway HTTP API**, qui accumule la réponse entière
avant de la relayer, sans option pour l’en empêcher : le client reçoit un bloc unique à la fin. Le
streaming est alors émulé de fait, sans que rien ne le signale.

`V2-ADR-011` tranche ce point : la route conversationnelle passe par un **API Gateway REST API en
mode `responseTransferMode = STREAM`**, endpoint Regional, via VPC Link V2 vers l’ALB interne. Deux
conséquences portées par ce choix :

- le plafond de durée d’un flux passe de 29 secondes à **15 minutes**. Le mode asynchrone
  (`operationId` et endpoint de reprise) cesse d’être le contournement d’une limite pour devenir un
  mécanisme de reprise après déconnexion réseau ;
- un **keep-alive est obligatoire** : un tour agentique appelant un tool lent peut rester silencieux
  plusieurs dizaines de secondes et faire tomber le flux sans lui. L’idle timeout de l’ALB devient
  un paramètre critique, et non plus un réglage par défaut.

Le mode effectivement servi — `native` ou `emulated` — est **déclaré au client** dans le premier
événement du flux : aucune dégradation silencieuse. L’annulation, que SSE ne sait pas transporter
puisque son canal est unidirectionnel, est un **appel authentifié dédié** adossé à un registre
partagé lu en cohérence forte (`V2-ADR-011`).

Le format exact des en-têtes propageant les claims entre API Gateway et FastAPI est défini en
`V2-LLD-001` — les mécanismes natifs d’HTTP API ne s’y transposant pas tels quels. L’implémentation
frontend (`EventSource`) est couverte par `V2-LLD-010`.

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

Le principe V1 reste la baseline : l’acteur provient d’un claim Cognito validé et n’est jamais accepté depuis le payload métier. Le modèle multi-tenant, les scopes et la représentation interne de l’identité sont décidés par `V2-ADR-006` : résolution serveur contrôlée, compatible mono-tenant et multi-tenant.

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

### Décidé par ADR

- Lambda Security Facade remplacée par FastAPI sur ECS/Fargate pour la couche applicative (`V2-ADR-001`) ;
- streaming SSE sur API Gateway REST API en mode `STREAM`, avec keep-alive obligatoire et
  annulation par appel dédié (`V2-ADR-011`, cf. §6.5) ;
- orchestration : FastAPI coordonne les appels à Runtime, Runtime exécute les agents custom (`V2-ADR-002`) ;
- ingestion asynchrone via SQS → service ECS Fargate (`V2-ADR-004`) ;
- modèle d’identité : résolution serveur, mono-tenant compatible multi-tenant (`V2-ADR-006`) ;
- confirmation des mutations par objet de commande, hors du chemin du modèle (`V2-ADR-014`, cf. §6.3).

### À détailler en LLD

- dimensionnement fin du calcul ECS (tailles de tâche, capacité) — `V2-LLD-001` ;
- noms et format des en-têtes de propagation des claims entre API Gateway et FastAPI — `V2-LLD-001`.

### Non applicable

- migration des données V1 → V2 : la V2 démarre avec un état vide ; les données V1 (DynamoDB Trips, Memory) restent dans l’environnement V1 sans migration.

## 17. État des décisions architecturales

Les vingt ADR du corpus V2 sont `Accepted`. Aucune décision structurante ne reste ouverte.

### Gate V2-G1 — frontière, plateforme et données

- `V2-ADR-001` : ingress et frontière de sécurité ;
- `V2-ADR-002` : responsabilités FastAPI versus AgentCore Runtime ;
- `V2-ADR-003` : architecture RAG S3 Vectors (cible V3 ; volet implémentation V2 superseded par `V2-ADR-019`) ;
- `V2-ADR-004` : pipeline d’ingestion et reprise (cible V3 ; volet implémentation V2 superseded par `V2-ADR-019`) ;
- `V2-ADR-005` : orchestration agents et adapter ;
- `V2-ADR-006` : modèle d’identité et isolation ;
- `V2-ADR-007` : réseau et calcul ECS ;
- `V2-ADR-008` : observabilité et propagation du contexte ;
- `V2-ADR-009` : GitLab CI et promotion ;
- `V2-ADR-010` : sauvegarde, restauration et réhydratation ;
- `V2-ADR-019` : phasage de livraison du RAG (Knowledge Bases en V2, pipeline applicatif en V3).

### ADR complémentaires

- `V2-ADR-011` : streaming des réponses et gestion des annulations — REST API en mode `STREAM`,
  annulation par appel dédié et registre partagé lu en cohérence forte (voir §6.5) ;
- `V2-ADR-012` : modèles Bedrock, profils d’inférence et fallback — identifiant d’invocation
  opaque, profil géographique EU, règle du premier token ;
- `V2-ADR-013` : embeddings et versionnement — `embeddingSpaceId` comme unité d’espace, migration
  par index parallèle et bascule de pointeur ;
- `V2-ADR-014` : confirmation forte et objet de commande — matérialisation, confirmation hors du
  chemin du modèle, exécution atomique (voir §6.3) ;
- `V2-ADR-015` : politique de mémoire et droit à l’effacement ;
- `V2-ADR-016` : WAF, quotas et protection contre les abus ;
- `V2-ADR-017` : classification documentaire et conservation ;
- `V2-ADR-018` : stratégie de tests RAG — non-régression contre une baseline versionnée, dataset de
  retrieval déterministe et bloquant ;
- `V2-ADR-020` : transport et ancrage de confiance de l’identité.

### Préconditions à prouver avant implémentation

Plusieurs ADR acceptés portent des **préconditions** : la décision est prise, son activation dépend
de faits à vérifier au moment de l’implémentation — disponibilité du *response streaming* API
Gateway REST et des VPC Links V2 en `eu-west-3` (`V2-ADR-011`), liste nominative des régions de
destination du profil d’inférence EU (`V2-ADR-012`), immuabilité de la dimension d’un index
S3 Vectors (`V2-ADR-013`), capacité de la Gateway MCP à exposer deux tools distincts
(`V2-ADR-014`).

Chaque ADR énonce le repli qui s’applique tant que sa preuve n’est pas produite. Ces préconditions
**ne rouvrent pas les décisions** ; elles conditionnent leur mise en service.

## 18. Critère de validation du HLD

Le HLD peut passer en statut `Approved` lorsque les critères suivants sont tenus :

| Critère | État |
|---|---|
| les exigences majeures sont traçables | tenu |
| les ADR bloquants sont décidés | tenu — les vingt ADR sont `Accepted` (§17) |
| les flux et frontières de confiance sont complets | tenu — §6.3 et §6.5 alignés sur `V2-ADR-014` et `V2-ADR-011` |
| l’analyse As-Is / To-Be est validée | tenu |
| les choix de disponibilité, sécurité, coûts et exploitation sont cohérents | tenu |
| le catalogue LLD couvre tous les domaines nécessaires | tenu — `LLD-V2-INDEX-FR.md` couvre les dix domaines |
| les risques résiduels sont explicitement acceptés ou planifiés | tenu — préconditions énoncées par ADR (§17) |

Le critère de catalogue porte sur la **couverture des domaines**, non sur la rédaction de chaque
document : six LLD (`V2-LLD-004`, `005`, `007`, `008`, `009`, `010`) restent à écrire. Leur absence
ne rouvre aucune décision d’architecture — elle conditionne le passage des gates de réalisation,
pas l’approbation du présent document.

Le passage effectif en `Approved` reste une **décision de validation**, distincte du constat
ci-dessus.
