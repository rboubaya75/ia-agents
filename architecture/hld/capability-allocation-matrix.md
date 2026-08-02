# Capability Allocation Matrix — Secure AgentCore V2

- **Version :** 0.3
- **Branche cible :** `migration/secure-agentcore-v2`
- **Décision de référence :** [`V2-ADR-002`](../adr/V2-ADR-002-fastapi-agentcore-responsibilities.md) — principes P-01 à P-05
- **Amendements :** [`V2-ADR-014`](../adr/V2-ADR-014-confirmation-commande-signee.md) — Domaines 5 et 7 ;
  [`V2-ADR-020`](../adr/V2-ADR-020-identite-transport-ancrage-confiance.md) — Domaine 1
- **Contrat associé :** [`runtime-contract.md`](runtime-contract.md)
- **Statut :** Draft

## 1. Objet

La CAM liste les capacités du système par domaine fonctionnel, désigne un unique propriétaire par
capacité et indique les consommateurs déclarés. Le propriétaire est l'unique composant autorisé à
implémenter la capacité. Les consommateurs sont les composants autorisés à l'invoquer via un
contrat explicite.

Ce document traduit en attributions concrètes les principes d'architecture non négociables
décidés par [`V2-ADR-002`](../adr/V2-ADR-002-fastapi-agentcore-responsibilities.md) (P-01 Single
Capability Ownership à P-05 Traceability). Toute modification d'un propriétaire de capacité
constitue un amendement à cet ADR.

> **Convention :** `—` indique que les consommateurs seront précisés dans le LLD du domaine
> concerné. Une capacité sans consommateurs déclarés est interne à son propriétaire.

## 2. Domaines

### Domaine 1 — Identity & Access Management

| Capacité | Propriétaire | Consommateurs |
|---|---|---|
| User Authentication | Cognito | API Gateway |
| MFA | Cognito | Utilisateur |
| Identity Federation | Cognito | API Gateway |
| Unauthenticated Traffic Rejection | Cognito Authorizer | API Gateway |
| Identity Establishment (JWT/JWKS) | FastAPI | — |
| Business Authorization (RBAC/ABAC) | FastAPI | AgentCore Runtime |
| Actor Identity Resolution | FastAPI | AgentCore Runtime |
| Tenant Resolution | FastAPI | AgentCore Runtime |

**Note d'architecture :** aucun token Cognito ne doit être transmis au-delà de FastAPI. Les
revendications sensibles (actorId, tenantId, rôles) sont résolues par FastAPI et propagées via
la `trustedIdentity` du contrat interne (voir [`runtime-contract.md`](runtime-contract.md)).
AgentCore Runtime ne reçoit jamais de JWT.

**Ancrage d'identité — décision `V2-ADR-020` :** Les deux capacités ci-dessus sont distinctes et
ont chacune un propriétaire unique (P-01) ; elles ne sont pas deux implémentations d'un même
contrôle.

`Unauthenticated Traffic Rejection` est ce que l'authorizer Cognito apporte au système : il
rejette le trafic non authentifié — par vérification de signature, d'expiration, d'audience et
d'émetteur — et **ne propage aucun claim** au-delà.

`Identity Establishment` est ce que FastAPI apporte : l'identité n'est pas ce que la passerelle
affirme, mais ce que FastAPI vérifie, en validant elle-même la signature du **jeton d'accès**
contre le **JWKS Cognito**. FastAPI ne lit aucun en-tête d'identité, quel qu'en soit le nom — les
familles `X-Amzn-Oidc-*` et `X-Claims-*` ne sont ni lues ni évaluées. L'`actorId` est le claim
`sub` du jeton vérifié, transmis tel quel à `trustedIdentity` ; le `tenantId` est résolu par le
registre serveur indexé par `sub`, sans claim personnalisé (P-03 — `V2-ADR-020`,
`V2-LLD-005 §3`). FastAPI ne fait donc jamais confiance à un claim porté par le payload
applicatif.

La conservation des deux capacités est la défense en profondeur de la CAM Domaine 10 : la seconde
ne suppose pas que la première a filtré, et la preuve `V2-LLD-005 §16` S2 l'exerce **authorizer
désactivé**.

**LLD de référence :** V2-LLD-005 (identité, sécurité et conformité).

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

**LLD de référence :** V2-LLD-001 (plateforme AWS, réseau, ECS et FastAPI), V2-LLD-006 (données).

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

**Le Runtime ne porte pas la vérification de confirmation (`V2-ADR-014`).** Il n'est propriétaire
d'aucune capacité d'autorisation des mutations : la confirmation parvient par un appel authentifié
dédié auquel il n'a pas accès, et sa vérification appartient au tool d'exécution, au point exact où
l'effet de bord se produit. Le Runtime sélectionne et invoque le tool ; il n'atteste rien sur ce que
l'utilisateur a autorisé.

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
| Tool Class Declaration (`read` / `mutating`) | MCP Gateway | AgentCore Runtime |

**Note d'architecture :** AgentCore Gateway MCP est le seul point d'entrée des tools. Aucun
tool ne peut être appelé directement par FastAPI ou par le code agent sans passer par la Gateway.
L'identité injectée côté Runtime écrase tout contexte produit par le modèle avant l'appel à la
Gateway.

**Classe de tool (`V2-ADR-014`).** Chaque tool déclare sa classe dans le catalogue : `read` (aucun
effet de bord) ou `mutating`. Trois propriétés en découlent :

- la classe est une propriété du **catalogue**, pas un paramètre d'appel : le modèle ne peut ni la
  produire, ni la surcharger, ni l'inférer ;
- **un tool qui ne déclare pas sa classe est traité comme `mutating`** — un oubli de déclaration
  rend le tool inutilisable sans commande confirmée, jamais exécutable sans confirmation ;
- un tool `mutating` se décline en deux tools distincts, proposition et exécution, afin que
  l'absence d'effet de bord de la matérialisation soit vérifiable par inspection du catalogue
  plutôt que par lecture du code.

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
| IAM Task Role | ECS | — |
| IAM Authorization | IAM | — |

**Note d'architecture :** les contrôles de sécurité sont en défense en profondeur. Aucune couche
ne suppose que la précédente a filtré entièrement. FastAPI valide les contrats même si API Gateway
a déjà validé le JWT. Les tools valident l'identité injectée même si Runtime l'a déjà construite.

**LLD de référence :** V2-LLD-005 (identité, sécurité et conformité).

## 3. Responsabilités interdites dans AgentCore Runtime

Ces interdictions sont la traduction directe des principes P-01 et P-02 appliqués à la CAM.
Elles constituent des violations de gouvernance bloquantes en revue de code.

- Ingestion documentaire (propriétaire : FastAPI — Domaine 4) ;
- administration des documents (propriétaire : FastAPI — Domaine 3) ;
- calcul de l'autorisation tenant (propriétaire : FastAPI — Domaine 1) ;
- exposition directe au navigateur (propriétaire : API Gateway / FastAPI — Domaines 1 et 2) ;
- stockage transactionnel des données métier dans Memory (propriétaire : DynamoDB — Domaine 8) ;
- dépendance à Bedrock managed Agents (exclu par V2-CHARTER) ; usage de Bedrock Knowledge Bases via `RetrieveAndGenerate` ou tout accès qui contourne FastAPI (en phase V2, KB est autorisé par `V2-ADR-019` uniquement adossé à S3 Vectors et via l'API `Retrieve`, FastAPI conservant le filtrage tenant/ACL) ;
- retrieval ou indexation vectorielle échappant à la propriété FastAPI (Domaine 4) : en phase V2 l'indexation et le retrieval de bas niveau sont exécutés par Knowledge Bases, mais FastAPI reste propriétaire du filtrage d'autorisation et de la construction du contexte ; en cible V3 FastAPI exécute directement le retrieval sur S3 Vectors (`V2-ADR-019`).

## 4. Dégradation contrôlée

| Composant indisponible | Comportement attendu | Capacités impactées (CAM) |
|---|---|---|
| API Gateway | Aucune requête n'atteint FastAPI ; échec au niveau CloudFront/client, aucun état applicatif partiel | Domaine 1 — Unauthenticated Traffic Rejection ; Domaine 2 — Rate Limiting Configuration |
| RAG (S3 Vectors) | Réponse sans retrieval pour les parcours explicitement autorisés (`retrievalContext.status = degraded`) | Domaine 4 — Retrieval Pipeline, Context Construction |
| AgentCore Memory | Poursuite sans mémoire durable | Domaine 6 — tous |
| Gateway MCP | Réponse sans mutation, erreur explicite pour les actions requises | Domaine 7 — tous |
| AgentCore Runtime | FastAPI retourne une erreur normalisée, aucun replay de mutation | Domaine 5 et 6 — tous |

**Note :** l'indisponibilité d'API Gateway est un incident d'infrastructure hors contrôle
applicatif — elle est traitée par les mécanismes AWS (health checks, failover) documentés en
LLD-001, pas par une logique de dégradation FastAPI/Runtime.

## 5. Preuves attendues

- test de dégradation pour API Gateway, RAG, Memory et Gateway MCP (tableau ci-dessus) ;
- test d'architecture : aucun composant n'implémente une capacité dont il n'est pas propriétaire
  dans cette CAM (P-01, P-02) ;
- chaque LLD référence explicitement les capacités CAM qu'il conçoit en détail (P-05).
