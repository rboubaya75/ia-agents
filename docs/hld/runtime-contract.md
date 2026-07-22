# Contrat interne FastAPI → AgentCore Runtime — Secure AgentCore V2

- **Version :** 0.1
- **Branche cible :** `migration/secure-agentcore-v2`
- **Décision de référence :** [`V2-ADR-002`](../adr/V2-ADR-002-fastapi-agentcore-responsibilities.md)
- **CAM de référence :** [`capability-allocation-matrix.md`](capability-allocation-matrix.md)
- **Statut :** Draft

## 1. Objet

Ce contrat est dérivé directement des capacités de la
[CAM](capability-allocation-matrix.md). Il ne contient aucune capacité que AgentCore Runtime
n'est pas propriétaire de traiter. Le token Cognito est absent par construction (P-03 — Explicit
Contracts). Le contrat final, y compris les limites de taille de `retrievalContext.chunks`, sera
défini dans les LLD `V2-LLD-003` et `V2-LLD-005` ; ce document fixe l'intention structurelle
tracée par l'ADR, pas le schéma d'implémentation.

## 2. Forme actuelle

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

## 3. Champs

### `trustedIdentity`

Résolu par FastAPI (Domaine 1 de la CAM — Actor Identity Resolution, Tenant Resolution). Ne
contient jamais de claim brut ni de token : uniquement les identifiants internes déjà validés et
autorisés.

### `operationContext`

Porte les Business Correlation IDs (`operationId`, `requestId`, Domaine 9 de la CAM), distincts
des identifiants de Distributed Tracing (`traceId`, `spanId`) propagés séparément par
OpenTelemetry. `deadlineEpochMs` borne le temps d'exécution disponible pour Runtime.

### `retrievalContext`

- `status` distingue explicitement les scénarios que `chunks: []` seul ne permet pas de
  discriminer : `ok` (retrieval exécuté, résultat éventuellement vide), `degraded` (RAG
  indisponible, réponse sans retrieval au sens du tableau de dégradation de la CAM) ou `skipped`
  (retrieval non requis pour ce parcours). Runtime adapte le comportement agentique — notamment
  le message renvoyé à l'utilisateur en cas d'absence de documents — selon cette valeur plutôt
  que sur le seul `chunkCount`.
- `chunkCount` est une valeur dérivée de `chunks.length`, fournie pour permettre à Runtime
  d'appliquer les budgets de contexte (LLD-003) sans désérialiser `chunks`. Elle n'introduit
  aucune capacité nouvelle et doit rester strictement égale à la taille du tableau.
- `trust` marque le contenu documentaire comme donnée non fiable, quel que soit `status`.

## 4. Champs interdits

`cognitoToken`, `authorizationHeader`, `modelOverride`, `systemPromptOverride`, `toolName`,
`actorIdRaw`, `tenantIdRaw`.

Un test de contrat doit refuser toute requête où l'un de ces champs est présent.

## 5. Preuves attendues

- tests de contrats FastAPI/Runtime avec les champs interdits refusés ;
- absence de token ou identité client dans le payload Runtime (P-03) ;
- test vérifiant `chunkCount === chunks.length` et la cohérence de `status` avec l'état réel du
  retrieval.
