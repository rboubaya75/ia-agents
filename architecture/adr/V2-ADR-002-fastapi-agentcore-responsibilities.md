# V2-ADR-002 — Répartition FastAPI et AgentCore Runtime

- **Version :** 0.4
- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-001, V2-ADR-003, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-011
- **Artefacts dérivés :** [`../hld/capability-allocation-matrix.md`](../hld/capability-allocation-matrix.md), [`../hld/runtime-contract.md`](../hld/runtime-contract.md)

## Contexte

La V2 ajoute un backend FastAPI sur ECS/Fargate tout en conservant AgentCore Runtime comme runtime
d'exécution des agents custom. Une séparation explicite est nécessaire pour éviter la duplication
de l'orchestration, du retrieval, des sessions et des contrôles de sécurité.

Cette décision est portée par une **Capability Allocation Matrix (CAM)**, référentiel d'autorité
pour l'attribution des capacités, détaillée dans un document séparé afin que cet ADR reste centré
sur le *pourquoi* de la décision plutôt que sur le détail de conception (le *comment*). La CAM est
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
Capability Allocation Matrix     (../hld/capability-allocation-matrix.md — décidée par cet ADR)
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

Retenir **l'option C**. La [Capability Allocation Matrix](../hld/capability-allocation-matrix.md)
est l'expression formelle de cette décision : elle attribue chaque capacité du système à un
unique propriétaire sur dix domaines fonctionnels. Le [contrat interne FastAPI → AgentCore
Runtime](../hld/runtime-contract.md) qui matérialise cette frontière en découle directement.

En résumé : Runtime ne doit jamais assumer l'ingestion ou l'administration documentaire, le calcul
de l'autorisation tenant, l'exposition directe au navigateur, le stockage transactionnel des
données métier, ou une dépendance à Bedrock Knowledge Bases / managed Agents — le détail complet,
tracé par domaine CAM, est maintenu dans
[`capability-allocation-matrix.md`](../hld/capability-allocation-matrix.md).

## Conséquences

- la CAM est le référentiel d'autorité pour l'attribution des capacités ; les LLD en découlent ;
- toute capacité hors CAM découverte en implémentation doit être soumise à amendement ADR ;
- le contrat interne FastAPI → Runtime matérialise la frontière décidée par cet ADR et ne peut
  pas contenir de capacité dont Runtime n'est pas propriétaire ;
- le tracing W3C doit être propagé de FastAPI jusqu'aux tools via Runtime ;
- les tests doivent pouvoir remplacer Runtime, Bedrock, S3 Vectors et MCP par des adapters de
  test (P-04 : Technology Independence) ;
- un test d'architecture automatisé doit détecter toute violation de propriété de capacité (P-05).

## Preuves attendues

- tests de contrats FastAPI/Runtime avec les champs interdits refusés (voir
  [`runtime-contract.md`](../hld/runtime-contract.md)) ;
- absence de dépendance framework agentique dans le code du domaine métier (P-04) ;
- budgets de tours, tokens, outils et temps définis et vérifiés en test ;
- test de dégradation pour API Gateway, RAG, Memory et Gateway MCP (voir
  [`capability-allocation-matrix.md`](../hld/capability-allocation-matrix.md)) ;
- absence de token ou identité client dans le payload Runtime (P-03) ;
- traçabilité d'une conversation jusqu'aux sources et tools via les IDs de corrélation ;
- test d'architecture : aucun composant n'implémente une capacité dont il n'est pas propriétaire
  dans la CAM (P-01, P-02) ;
- chaque LLD référence explicitement les capacités CAM qu'il conçoit en détail (P-05).
