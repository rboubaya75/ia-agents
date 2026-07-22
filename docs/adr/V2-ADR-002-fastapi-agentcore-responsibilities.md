# V2-ADR-002 — Répartition FastAPI et AgentCore Runtime

- **Version :** 0.3
- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-001, V2-ADR-003, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-011

## Contexte

La V2 ajoute un backend FastAPI sur EKS tout en conservant AgentCore Runtime comme runtime
d'exécution des agents custom. Une séparation explicite est nécessaire pour éviter la duplication
de l'orchestration, du retrieval, des sessions et des contrôles de sécurité.

Cet ADR introduit une **Capability Allocation Matrix (CAM)** comme référentiel d'autorité pour
l'attribution des capacités. La CAM remplace les listes de responsabilités narratives et devient
le document de référence cité dans les LLD, les tests d'architecture et les analyses d'impact.
Toute modification d'un propriétaire de capacité constitue un amendement à cet ADR.

## Principes d'architecture (non négociables)

Ces principes gouvernent la construction et l'évolution de la CAM. Tout changement qui les viole
exige un nouvel ADR explicitement approuvé.

| ID | Principe | Règle d'application |
|---|---|---|
| P-01 | **Single Capability Ownership** | Chaque capacité est attribuée à un seul propriétaire. En cas de litige, le propriétaire est déterminé par l'ADR, pas par l'implémentation en place. |
| P-02 | **No Capability Duplication** | Aucune capacité ne peut être implémentée par deux composants. La duplication détectée en revue de code est un blocant. |
| P-03 | **Explicit Contracts** | Toutes les interactions entre composants passent par des contrats versionnés (OpenAPI, schéma d'événement ou contrat MCP). Aucune dépendance implicite sur un comportement interne n'est autorisée. |
| P-04 | **Technology Independence** | Les capacités sont décrites indépendamment de leur implémentation technique. Un changement de technologie (Lambda → FastAPI, Strands → LangGraph) n'impose pas de réécriture de la CAM si le propriétaire reste identique. |
| P-05 | **Traceability** | Chaque capacité est reliée aux ADR, au HLD, aux LLD, aux tests et aux exigences métier qui la justifient. Une capacité non traçable est un écart de gouvernance bloquant. |

## Hiérarchie de traçabilité

La CAM occupe un niveau intermédiaire dans la chaîne de traçabilité V2. Elle traduit les principes
d'architecture en attributions concrètes, et ces attributions alimentent directement les ADR, le
HLD et les LLD.

```text
Business Requirements
        │
        ▼
Architecture Principles          (P-01 à P-05 ci-dessus)
        │
        ▼
Capability Model                 (domaines fonctionnels)
        │
        ▼
Capability Allocation Matrix     (ce document — ADR-002 v0.3)
        │
        ├──► Architecture Decision Records   (V2-ADR-001 à V2-ADR-018)
        │
        ├──► High Level Design               (HLD-Secure-AgentCore-V2-FR.md)
        │
        ├──► Low Level Design par domaine    (V2-LLD-001 à V2-LLD-010)
        │
        ├──► Implementation
        │
        ├──► Industrial Test Suite
        │
        └──► Acceptance Evidence
```

Chaque LLD doit référencer les capacités de la CAM dont il est la conception détaillée. Chaque
test d'architecture doit vérifier qu'un composant n'implémente pas une capacité dont il n'est pas
propriétaire.

## Options

### Option A — Orchestration complète dans FastAPI

FastAPI appelle directement Bedrock Converse API et les tools, Runtime devenant marginal.

**Rejet proposé :** incompatible avec le rôle retenu pour AgentCore Runtime et risque de dupliquer
les capacités d'exécution agentique (violation de P-02).

### Option B — Orchestration complète dans Runtime

FastAPI transmet seulement le message et Runtime réalise retrieval, autorisation, modèle et tools.

**Rejet proposé :** mélange les responsabilités applicatives, documentaires et agentiques ;
complique les APIs d'administration et la testabilité ; concentre trop de propriétés dans un
composant non testable sans service externe (violation de P-01 et P-02).

### Option C — Orchestration en deux niveaux

FastAPI décide du parcours, réalise l'autorisation et le retrieval, puis invoque Runtime avec un
contexte contrôlé. Runtime exécute l'agent, le modèle, Memory et les tools MCP autorisés.

## Décision proposée

Retenir **l'option C**. La CAM ci-dessous est l'expression formelle de cette décision.

---

## Capability Allocation Matrix (CAM)

La CAM liste les capacités par domaine fonctionnel, désigne un unique propriétaire par capacité et
indique les consommateurs déclarés. Le propriétaire est l'unique composant autorisé à implémenter
la capacité. Les consommateurs sont les composants autorisés à l'invoquer via un contrat explicite.

> **Convention :** `—` indique que les consommateurs seront précisés dans le LLD du domaine
> concerné. Une capacité sans consommateurs déclarés est interne à son propriétaire.

---

### Domaine 1 — Identity & Access Management

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| User Authentication | Cognito | API Gateway |
| MFA | Cognito | Utilisateur |
| Identity Federation | Cognito | API Gateway |
| JWT Signature Validation | Cognito Authorizer | API Gateway |
| JWT Expiration Validation | Cognito Authorizer | API Gateway |
| JWT Audience Validation | Cognito Authorizer | API Gateway |
| JWT Issuer Validation | Cognito Authorizer | API Gateway |
| Claims Extraction | API Gateway | FastAPI |
| Claims Propagation | API Gateway | FastAPI |
| Business Authorization (RBAC/ABAC) | FastAPI | AgentCore Runtime |
| Actor Identity Resolution | FastAPI | AgentCore Runtime |
| Tenant Resolution | FastAPI | AgentCore Runtime |

**Note d'architecture :** aucun token Cognito ne doit être transmis au-delà de FastAPI. Les
revendications sensibles (actorId, tenantId, rôles) sont résolues par FastAPI et propagées via
la `trustedIdentity` du contrat interne. AgentCore Runtime ne reçoit jamais de JWT.

**Claims Extraction vs Claims Propagation :** Extraction désigne le parsing du JWT validé et la
lecture des claims Cognito (`sub`, `custom:tenantId`, rôles) par API Gateway. Propagation désigne
le forwarding de ces claims vers FastAPI via des en-têtes HTTP dédiés injectés côté serveur
(distincts de l'en-tête `Authorization`), jamais dans le corps de la requête. FastAPI ne fait donc
jamais confiance à un claim porté par le payload applicatif — seuls les en-têtes injectés par API
Gateway sont une source valide (P-03). Le format exact des en-têtes est défini en LLD-005.

---

### Domaine 2 — API Platform

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| REST API | FastAPI | — |
| Streaming API | FastAPI | — |
| Request Validation | FastAPI | — |
| Response Validation | FastAPI | — |
| API Versioning | FastAPI | — |
| OpenAPI Documentation | FastAPI | — |
| Error Translation | FastAPI | — |
| Pagination | FastAPI | — |
| Rate Limiting Configuration | API Gateway | — |

**LLD de référence :** V2-LLD-001 (plateforme), V2-LLD-010 (frontend).

---

### Domaine 3 — Business Layer

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Trip Management | FastAPI | — |
| User Profile | FastAPI | — |
| Business Rules | FastAPI | — |
| Domain Validation | FastAPI | — |
| Workflow Coordination | FastAPI | — |
| DTO Mapping | FastAPI | — |

**Note d'architecture :** les données métier transactionnelles restent exclusivement sous FastAPI
et DynamoDB. AgentCore Memory n'est pas un store de données métier (P-01, P-02).

**LLD de référence :** V2-LLD-001 (plateforme AWS, réseau, EKS et FastAPI), V2-LLD-006 (données).

---

### Domaine 4 — Retrieval

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Document Ingestion | FastAPI | — |
| Metadata Extraction | FastAPI | — |
| Embedding Generation | FastAPI | — |
| S3 Vectors Indexing | FastAPI | — |
| Retrieval Pipeline | FastAPI | — |
| Metadata Filtering | FastAPI | — |
| Context Construction | FastAPI | — |
| Prompt Context Assembly | FastAPI | AgentCore Runtime |

**Note d'architecture :** l'ensemble du pipeline RAG est une capacité applicative portée par
FastAPI. AgentCore Runtime reçoit un contexte RAG borné et préassemblé — il ne réalise ni
retrieval ni indexation (P-01). Le contenu documentaire est traité comme donnée non fiable à tous
les niveaux.

**LLD de référence :** V2-LLD-002 (RAG).

---

### Domaine 5 — Agentic AI

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Conversation Orchestration | AgentCore Runtime | FastAPI |
| Planning | AgentCore Runtime | — |
| Reasoning | AgentCore Runtime | — |
| Agent Routing | AgentCore Runtime | — |
| Multi-Agent Coordination | AgentCore Runtime | — |
| Tool Selection | AgentCore Runtime | — |
| Tool Retry | AgentCore Runtime | — |
| Prompt Construction | AgentCore Runtime | — |
| Bedrock Converse Invocation | AgentCore Runtime | — |

**Note d'architecture :** la boucle agentique, le raisonnement et la sélection des tools sont
exclusivement sous AgentCore Runtime. FastAPI ne peut pas contourner Runtime pour appeler
directement Bedrock Converse API sur le chemin conversationnel (P-01, P-02).

**LLD de référence :** V2-LLD-003 (agents et orchestration).

---

### Domaine 6 — Memory

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Conversation Memory | AgentCore Runtime | — |
| Session State | AgentCore Runtime | — |
| Conversation Summary | AgentCore Runtime | — |
| Preference Extraction | AgentCore Runtime | — |
| Memory Retrieval | AgentCore Runtime | — |
| Memory Persistence | AgentCore Runtime | — |

**Note d'architecture :** AgentCore Memory est utilisé uniquement pour les préférences et
l'état conversationnel isolés par acteur et tenant. Memory ne stocke pas les données métier
transactionnelles (violation de P-02 avec DynamoDB). L'isolation multi-tenant des namespaces
Memory doit être vérifiée par les tests industriels.

**LLD de référence :** V2-LLD-006 (données, mémoire, rétention).

---

### Domaine 7 — MCP

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Tool Discovery | MCP Gateway | AgentCore Runtime |
| Tool Authentication | MCP Gateway | — |
| Tool Authorization | MCP Gateway | — |
| Tool Transport | MCP Gateway | — |
| Tool Registration | MCP Gateway | — |
| Tool Version Negotiation | MCP Gateway | — |

**Note d'architecture :** AgentCore Gateway MCP est le seul point d'entrée des tools. Aucun
tool ne peut être appelé directement par FastAPI ou par le code agent sans passer par la Gateway.
L'identité injectée côté Runtime écrase tout contexte produit par le modèle avant l'appel à la
Gateway.

**LLD de référence :** V2-LLD-004 (AgentCore Gateway MCP et tools).

---

### Domaine 8 — Data Platform

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Object Storage | Amazon S3 | FastAPI |
| Vector Storage | S3 Vectors | FastAPI |
| Operational Data | DynamoDB | FastAPI |
| Secrets | Secrets Manager | — |
| Identity Store | Cognito | — |
| Configuration | Parameter Store | — |

**Note d'architecture :** chaque store a un rôle exclusif. Aucune capacité d'un store ne peut
être substituée par un autre sans ADR explicite. En particulier, DynamoDB n'est pas un vecteur
et S3 Vectors n'est pas un store transactionnel.

**LLD de référence :** V2-LLD-006 (données).

---

### Domaine 9 — Observability

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| Metrics | OpenTelemetry | — |
| Distributed Tracing (traceId, spanId) | OpenTelemetry | — |
| Business Correlation IDs (operationId, requestId) | FastAPI | AgentCore Runtime |
| Structured Logging | CloudWatch | — |
| Audit Logs | CloudWatch | — |
| Dashboards | CloudWatch | — |
| Alerts | CloudWatch | — |

**Note d'architecture :** deux familles d'identifiants coexistent et ne doivent pas être
confondues. Le **Distributed Tracing** (`traceId`, `spanId`, W3C Trace Context) est propriété
d'OpenTelemetry : il est généré par l'instrumentation, propagé automatiquement de FastAPI jusqu'à
AgentCore Runtime et aux tools MCP, et sert la corrélation technique inter-services. Les
**Business Correlation IDs** (`operationId`, `requestId` du contrat interne) sont propriété de
FastAPI : ils identifient une opération métier (une requête utilisateur, une mutation) et
persistent au-delà d'une trace technique unique — par exemple pour retrouver toutes les traces
liées à une même opération après un retry. AgentCore Runtime consomme les deux sans en générer
aucun. Aucun de ces identifiants (`traceId`, `operationId`, `requestId`, `sessionId`) ne doit
exposer de données en clair dans les logs ; ils sont hashés avant écriture (Domaine 9 —
Structured Logging).

**LLD de référence :** V2-LLD-007 (observabilité, SLO et FinOps).

---

### Domaine 10 — Security

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| TLS Termination | CloudFront | — |
| DDoS Protection | AWS Shield | — |
| WAF Rules | AWS WAF | — |
| Network Isolation | Amazon VPC | — |
| Pod Identity | EKS | — |
| IAM Authorization | IAM | — |

**Note d'architecture :** les contrôles de sécurité sont en défense en profondeur. Aucune couche
ne suppose que la précédente a filtré entièrement. FastAPI valide les contrats même si API Gateway
a déjà validé le JWT. Les tools valident l'identité injectée même si Runtime l'a déjà construite.

**LLD de référence :** V2-LLD-005 (identité, sécurité et conformité).

---

## Contrat interne FastAPI → AgentCore Runtime

Le contrat est dérivé directement des capacités de la CAM. Il ne contient aucune capacité que
Runtime n'est pas propriétaire de traiter. Le token Cognito est absent par construction (P-03).

```json
{
  "message": "...",
  "runtimeSessionId": "...",
  "trustedIdentity": {
    "actorId": "...",
    "tenantId": "..."
  },
  "operationContext": {
    "operationId": "...",
    "requestId": "...",
    "deadlineEpochMs": 0
  },
  "retrievalContext": {
    "status": "ok",
    "chunks": [],
    "chunkCount": 0,
    "policy": "v1",
    "trust": "untrusted"
  }
}
```

`retrievalContext.status` distingue explicitement les scénarios que `chunks: []` seul ne permet
pas de discriminer : `ok` (retrieval exécuté, résultat éventuellement vide), `degraded` (RAG
indisponible, réponse sans retrieval au sens du tableau de dégradation) ou `skipped` (retrieval
non requis pour ce parcours). Runtime adapte le comportement agentique — notamment le message
renvoyé à l'utilisateur en cas d'absence de documents — selon cette valeur plutôt que sur le seul
`chunkCount`. `retrievalContext.chunkCount` est une valeur dérivée de `chunks.length` fournie pour
permettre à Runtime d'appliquer les budgets de contexte (LLD-003) sans désérialiser `chunks` ;
elle n'introduit aucune capacité nouvelle et doit rester strictement égale à la taille du tableau.

Champs interdits dans ce contrat : `cognitoToken`, `authorizationHeader`, `modelOverride`,
`systemPromptOverride`, `toolName`, `actorIdRaw`, `tenantIdRaw`.

Le contrat final, y compris les limites de taille de `retrievalContext.chunks`, sera défini
dans les LLD V2-LLD-003 et V2-LLD-005.

## Responsabilités interdites dans AgentCore Runtime

Ces interdictions sont la traduction directe des principes P-01 et P-02 appliqués à la CAM.
Elles constituent des violations de gouvernance bloquantes en revue de code.

- Ingestion documentaire (propriétaire : FastAPI — Domaine 4) ;
- administration des documents (propriétaire : FastAPI — Domaine 3) ;
- calcul de l'autorisation tenant (propriétaire : FastAPI — Domaine 1) ;
- exposition directe au navigateur (propriétaire : API Gateway / FastAPI — Domaines 1 et 2) ;
- stockage transactionnel des données métier dans Memory (propriétaire : DynamoDB — Domaine 8) ;
- dépendance directe à Bedrock Knowledge Bases ou managed Agents (exclus par V2-CHARTER) ;
- retrieval ou indexation vectorielle (propriétaire : FastAPI — Domaine 4).

## Dégradation contrôlée

| Composant indisponible | Comportement attendu | Capacités impactées (CAM) |
|---|---|---|
| API Gateway | Aucune requête n'atteint FastAPI ; échec au niveau CloudFront/client, aucun état applicatif partiel | Domaine 1 — Claims Extraction, Claims Propagation ; Domaine 2 — Rate Limiting Configuration |
| RAG (S3 Vectors) | Réponse sans retrieval pour les parcours explicitement autorisés (`retrievalContext.status = degraded`) | Domaine 4 — Retrieval Pipeline, Context Construction |
| AgentCore Memory | Poursuite sans mémoire durable | Domaine 6 — tous |
| Gateway MCP | Réponse sans mutation, erreur explicite pour les actions requises | Domaine 7 — tous |
| AgentCore Runtime | FastAPI retourne une erreur normalisée, aucun replay de mutation | Domaine 5 et 6 — tous |

**Note :** l'indisponibilité d'API Gateway est un incident d'infrastructure hors contrôle
applicatif — elle est traitée par les mécanismes AWS (health checks, failover) documentés en
LLD-001, pas par une logique de dégradation FastAPI/Runtime.

## Conséquences

- la CAM est le référentiel d'autorité pour l'attribution des capacités ; les LLD en découlent ;
- toute capacité hors CAM découverte en implémentation doit être soumise à amendement ADR ;
- le contexte RAG dans le contrat interne doit être limité en taille (à définir en LLD-003) ;
- le tracing W3C doit être propagé de FastAPI jusqu'aux tools via Runtime ;
- les tests doivent pouvoir remplacer Runtime, Bedrock, S3 Vectors et MCP par des adapters de
  test (P-04 : Technology Independence) ;
- un test d'architecture automatisé doit détecter toute violation de propriété de capacité (P-05).

## Preuves attendues

- tests de contrats FastAPI/Runtime avec les champs interdits refusés ;
- absence de dépendance framework agentique dans le code du domaine métier (P-04) ;
- budgets de tours, tokens, outils et temps définis et vérifiés en test ;
- test de dégradation pour RAG, Memory et Gateway (tableau ci-dessus) ;
- absence de token ou identité client dans le payload Runtime (P-03) ;
- traçabilité d'une conversation jusqu'aux sources et tools via les IDs de corrélation ;
- test d'architecture : aucun composant n'implémente une capacité dont il n'est pas propriétaire
  dans la CAM (P-01, P-02) ;
- chaque LLD référence explicitement les capacités CAM qu'il conçoit en détail (P-05).
