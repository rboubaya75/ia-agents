# V2-ADR-002 — Répartition FastAPI et AgentCore Runtime

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-001, V2-ADR-003, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-011

## Contexte

La V2 ajoute un backend FastAPI sur EKS tout en conservant AgentCore Runtime comme runtime d’exécution des agents custom. Une séparation explicite est nécessaire pour éviter la duplication de l’orchestration, du retrieval, des sessions et des contrôles de sécurité.

## Principes

- FastAPI porte les responsabilités applicatives et non agentiques ;
- AgentCore Runtime porte l’exécution bornée de l’agent ;
- le domaine métier ne dépend directement ni de Strands ni de LangGraph ;
- les contrats entre FastAPI et Runtime sont versionnés ;
- le retrieval et les documents restent des capacités applicatives, pas des Knowledge Bases managées.

## Options

### Option A — Orchestration complète dans FastAPI

FastAPI appelle directement Bedrock Converse API et les tools, Runtime devenant marginal.

**Rejet proposé :** incompatible avec le rôle retenu pour AgentCore Runtime et risque de dupliquer les capacités d’exécution agentique.

### Option B — Orchestration complète dans Runtime

FastAPI transmet seulement le message et Runtime réalise retrieval, autorisation, modèle et tools.

**Rejet proposé :** mélange les responsabilités applicatives, documentaires et agentiques ; complique les APIs d’administration et la testabilité.

### Option C — Orchestration en deux niveaux

FastAPI décide du parcours, réalise l’autorisation et le retrieval, puis invoque Runtime avec un contexte contrôlé. Runtime exécute l’agent, le modèle, Memory et les tools MCP autorisés.

## Décision proposée

Retenir **l’option C**.

### Responsabilités FastAPI

- API conversation, documents, ingestion et administration ;
- validation du contrat externe ;
- identité et autorisation ;
- gestion des quotas, deadlines et annulations ;
- sélection du parcours applicatif ;
- retrieval S3 Vectors et résolution des sources ;
- construction d’un contexte RAG borné et marqué comme non fiable ;
- invocation IAM de Runtime ;
- streaming vers le navigateur et normalisation des erreurs ;
- persistance des états non agentiques et observabilité distribuée.

### Responsabilités AgentCore Runtime

- chargement de l’agent custom sous `/agents` ;
- adapter Strands ou LangGraph ;
- boucle agentique bornée ;
- Bedrock Converse API ;
- usage contrôlé d’AgentCore Memory ;
- sélection des tools dans une allowlist ;
- appels AgentCore Gateway MCP signés IAM ;
- injection serveur de l’identité et du contexte d’opération ;
- retour d’événements et résultats structurés.

### Responsabilités interdites dans Runtime

- ingestion documentaire ;
- administration des documents ;
- calcul de l’autorisation tenant ;
- exposition directe au navigateur ;
- stockage transactionnel des données métier dans Memory ;
- dépendance à Bedrock Knowledge Bases ou managed Agents.

## Contrat interne minimal

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
    "chunks": [],
    "policy": "v1"
  }
}
```

Le contrat final sera défini dans les LLD et ne doit contenir aucun token Cognito.

## Dégradation contrôlée

- RAG indisponible : réponse sans retrieval uniquement pour les parcours explicitement autorisés ;
- Memory indisponible : poursuite sans mémoire durable ;
- Gateway MCP indisponible : réponse sans mutation et erreur explicite pour les actions requises ;
- Runtime indisponible : FastAPI retourne une erreur normalisée et ne tente aucun replay ambigu de mutation.

## Conséquences

- deux niveaux d’orchestration existent, mais avec responsabilités différentes ;
- le contexte RAG doit être limité en taille et versionné ;
- le tracing W3C doit être propagé jusqu’au Runtime et aux tools ;
- les tests doivent pouvoir remplacer Runtime, Bedrock, S3 Vectors et MCP par des adapters de test.

## Preuves attendues

- tests de contrats FastAPI/Runtime ;
- absence de dépendance framework dans le domaine ;
- budgets de tours, tokens, outils et temps ;
- test de dégradation pour RAG, Memory et Gateway ;
- absence de token ou identité client dans le payload Runtime ;
- traçabilité d’une conversation jusqu’aux sources et tools.
