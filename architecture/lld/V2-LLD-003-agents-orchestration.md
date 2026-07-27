# V2-LLD-003 — Agents et orchestration

- **Version :** 0.1
- **Statut :** Draft (propositions — en attente de revue)
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§10)
- **CAM de référence :** `architecture/hld/capability-allocation-matrix.md` (Domaine 5 — Agentic AI)
- **Contrat de référence :** `architecture/hld/runtime-contract.md`
- **ADR de référence :** `V2-ADR-002`, `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-008`, `V2-ADR-011`
  (backlog), `V2-ADR-012` (backlog)
- **Gate :** V2-G2

> **Version 0.1 — Statut propositions :** ce document est un draft pédagogique destiné à aligner
> l'équipe sur la conception avant implémentation. Les sections marquées
> `⚠ ADR MANQUANT` dépendent de `V2-ADR-011` (streaming + annulations) et `V2-ADR-012`
> (modèles + fallback), tous deux au backlog — ces sections proposeront un choix par défaut
> raisonnable mais resteront ouvertes jusqu'à décision formelle. Aucun élément de ce LLD n'est
> contractuellement opposable avant sa révision post-ADR et son passage en `Approved`.

---

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD / Charte | Libellé |
|---|---|
| HLD §10 | Architecture agents : adapter, orchestrateur minimal, prompts versionnés, budgets, allowlists, fallback |
| CAM Domaine 5 | Propriété exclusive AgentCore Runtime : boucle agentique, raisonnement, sélection de tools, invocation Bedrock Converse API |
| V2-ADR-002 P-01/P-02 | Single Capability Ownership — Runtime seul possède la boucle agentique ; FastAPI ne court-circuite jamais Converse API |
| V2-ADR-002 P-04 | Technology Independence — le code domaine ne doit jamais importer `strands.*` directement |
| V2-ADR-005 | Strands derrière adapter ; orchestrateur unique ; budgets `maxTurns`/`maxToolCalls`/`maxTokens` ; fallback modèle délégué à ADR-012 |
| V2-ADR-006 | Identité injectée côté serveur ; `trustedIdentity` seule acceptée par Runtime et tools |
| V2-ADR-008 | Propagation W3C Trace Context ; hooks budget émettent des événements OTel |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-002 | Décision structurante : Runtime est l'unique propriétaire de la boucle agentique (CAM Domaine 5). FastAPI ne fait qu'initier l'appel via le contrat `runtime-contract.md`. Toute capacité agentique hors Runtime est une violation P-02. |
| V2-ADR-005 | Structure `/agents` (adapter / interface / domain). Strands confiné au module `adapter/`. Orchestrateur unique par défaut. Budgets `maxTurns`, `maxToolCalls`, `maxTokens`, `deadlineEpochMs` injectés par configuration, jamais codés en dur. |
| V2-ADR-006 | `trustedIdentity` construite par FastAPI et transmise au Runtime. Runtime et tools écrasent toute identité produite par le modèle. Aucun token Cognito en dehors de FastAPI. |
| V2-ADR-008 | Propagation `traceparent` W3C de FastAPI → Runtime → tools. Corrélation de repli via `operationId`/`requestId` si Runtime ne propage pas le header nativement. Hooks budget émettent des spans OTel. |

### 1.3 ADR au backlog — impact sur ce LLD

| ADR | Sujet | Impact sur ce LLD |
|---|---|---|
| V2-ADR-011 | Streaming des réponses et gestion des annulations | §7 (streaming), §8.3 (annulation) — choix par défaut documentés, à stabiliser post-ADR |
| V2-ADR-012 | Modèles Bedrock, profils d'inférence et fallback | §5.4 (modèle configuré), §9.2 (fallback) — adapter expose un paramètre `modelConfig`, la stratégie de bascule reste ouverte |

### 1.4 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-001 | Ingress et frontière réseau : couvert par `V2-LLD-001` |
| V2-ADR-003/004 | Pipeline RAG et ingestion : couvert par `V2-LLD-002` ; ce LLD consomme uniquement le `retrievalContext` borné |
| V2-ADR-007 | Plateforme ECS : couvert par `V2-LLD-001` |
| V2-ADR-009/010 | CI/CD et backup : couverts par `V2-LLD-008` et `V2-LLD-006` |
| V2-ADR-019 | Phasage RAG KB/V3 : couvert par `V2-LLD-002` ; ce LLD reçoit le `retrievalContext` déjà construit |

### 1.5 Périmètre et exclusions

**Inclus :** structure du module `/agents`, `AgentAdapter` Protocol, `StrandsAdapter`, orchestrateur
applicatif, agents spécialisés (si instanciés), prompts versionnés, budgets emboîtés, tool
allowlists, contrat FastAPI → Runtime, propagation d'identité, corrélation OTel, dégradation et
fallback.

**Exclus (autres LLD) :**
- Plateforme ECS, Task IAM Role, variables d'environnement → `V2-LLD-001`
- Pipeline RAG, construction du `retrievalContext` → `V2-LLD-002`
- Catalogue MCP, schémas tools, ledger d'idempotence → `V2-LLD-004`
- Authentification Cognito, threat model, KMS → `V2-LLD-005`
- AgentCore Memory (namespaces, TTL, effacement) → `V2-LLD-006`
- Dashboards, SLO, FinOps → `V2-LLD-007`

---

## 2. Architecture détaillée

### 2.1 Vue d'ensemble et principes

Le domaine agents repose sur une séparation en trois couches décidée par `V2-ADR-005`. Cette
séparation permet de remplacer le framework (Strands, LangGraph…) sans toucher au code métier,
conformément au principe P-04 (Technology Independence) de la CAM.

```
┌──────────────────────────────────────────────────────────┐
│                        /agents                           │
│                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │  domain/     │   │  interface.py │   │  adapter/    │ │
│  │  (métier,    │──▶│  AgentAdapter │◀──│  strands_    │ │
│  │  budgets,    │   │  Protocol     │   │  adapter.py  │ │
│  │  prompts)    │   └──────────────┘   │  (seul à     │ │
│  └──────────────┘                      │  importer     │ │
│                                        │  strands.*)   │ │
│                                        └──────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Règle absolue (P-04) :** un test d'architecture (lint d'imports, exécuté en CI) doit détecter
toute importation de `strands.*` en dehors du répertoire `agents/adapter/`. Ce test est bloquant.

### 2.2 Arborescence `/agents`

```
agents/
├── interface.py          # AgentAdapter Protocol (contrat du domaine)
├── models.py             # AgentRequest, AgentResult, AgentBudget, AgentConfig
├── exceptions.py         # BudgetExceededError, ToolDeniedError, AgentFallbackError
│
├── adapter/
│   └── strands_adapter.py    # implémente AgentAdapter via Strands SDK
│
├── domain/
│   ├── orchestrator.py       # orchestrateur principal (instancie l'adapter, applique budgets)
│   ├── budget_guard.py       # vérification et propagation des budgets emboîtés
│   ├── tool_allowlist.py     # validation de la tool allowlist par tenant/rôle
│   ├── prompt_registry.py    # chargement et versionnement des prompts système
│   └── context_builder.py   # assemblage du contexte agent (identité + retrieval + memory policy)
│
└── prompts/
    ├── system_v1.md          # prompt système versionné
    └── system_v2.md          # future version (coexistence possible)
```

### 2.3 Flux d'invocation principal

Le schéma ci-dessous représente le chemin d'une requête conversationnelle de bout en bout.
FastAPI est le coordinateur ; Runtime est l'exécuteur.

```
Utilisateur
    │
    ▼
API Gateway (JWT validé, claims extraits)
    │
    ▼
FastAPI
 ├─ 1. Autorisation (tenantId, actorId, rôles — V2-ADR-006)
 ├─ 2. Retrieval → retrievalContext borné (V2-LLD-002)
 ├─ 3. Assemblage contrat Runtime (runtime-contract.md)
 │       { message, runtimeSessionId, trustedIdentity,
 │         operationContext, retrievalContext }
 └─ 4. Appel AgentCore Runtime ──────────────────────────────┐
                                                              │
                                         AgentCore Runtime   │
                                          ├─ domain/orchestrator.py
                                          │   └─ AgentAdapter.invoke(context)
                                          │         └─ StrandsAdapter
                                          │               ├─ budget_guard (maxTurns/maxToolCalls/maxTokens)
                                          │               ├─ tool_allowlist check
                                          │               ├─ Bedrock Converse API (claude-*)
                                          │               ├─ AgentCore Memory (lecture/écriture)
                                          │               └─ AgentCore Gateway MCP (tools)
                                          └─ AgentResult → FastAPI
FastAPI
 └─ 5. Réponse client (stream ou bloc)
```

**Points critiques du flux :**

1. FastAPI ne fait jamais d'appel direct à Bedrock Converse API sur le chemin conversationnel —
   uniquement via Runtime. Toute déviation est une violation P-02 bloquante.
2. Le contenu du `retrievalContext` est marqué `trust: "untrusted"` — Runtime ne peut pas le
   traiter comme une source d'autorité (règle V2-ADR-002).
3. `trustedIdentity` est construite par FastAPI ; Runtime et les tools écrasent toute identité
   produite par le modèle avant chaque appel tool (V2-ADR-006).

### 2.4 Orchestrateur par défaut

Un orchestrateur unique est retenu pour la V2 (`V2-ADR-005`) : aucun multi-agent tant qu'un besoin
concret n'est pas documenté. L'ajout d'un agent spécialisé exige un **amendement ADR ou une
justification explicite dans ce LLD** (P-01/P-02).

L'orchestrateur gère :
- l'instanciation de l'adapter configuré ;
- l'application des budgets emboîtés avant chaque tour ;
- la vérification de la tool allowlist avant chaque appel ;
- la construction du message système depuis le `PromptRegistry` ;
- le retour structuré `AgentResult` vers FastAPI.

---

## 3. Contrats

### 3.1 Interface `AgentAdapter`

```python
from typing import Protocol
from agents.models import AgentRequest, AgentResult

class AgentAdapter(Protocol):
    """
    Contrat d'abstraction du framework agentique (V2-ADR-005 — P-04).
    Le code domaine ne dépend que de cette interface, jamais de strands.* directement.
    """

    def invoke(self, request: AgentRequest) -> AgentResult:
        """Exécute une conversation agentique et retourne le résultat borné."""
        ...

    def invoke_stream(self, request: AgentRequest):
        """
        Variante streaming — retourne un itérateur de fragments de texte.
        ⚠ ADR MANQUANT : le contrat précis (SSE, WebSocket, chunks format) est défini
        par V2-ADR-011 (backlog). Par défaut : générateur Python de str.
        """
        ...
```

### 3.2 Modèles de données

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class AgentBudget:
    max_turns: int              # nombre maximum de tours modèle/tool (ADR-005)
    max_tool_calls: int         # nombre total d'appels tool par conversation
    max_tokens: int             # tokens cumulés entrée + sortie
    deadline_epoch_ms: int      # borne temporelle absolue (déjà existante en V1)

@dataclass(frozen=True)
class AgentConfig:
    model_id: str               # ex. "anthropic.claude-sonnet-4-5-20251001-v2:0"
    prompt_version: str         # ex. "v1" (chargé depuis PromptRegistry)
    tool_allowlist: list[str]   # noms des tools MCP autorisés pour ce parcours
    # ⚠ ADR MANQUANT : inference_profile_id et fallback_model_id → V2-ADR-012

@dataclass(frozen=True)
class TrustedIdentity:
    actor_id: str               # hash(sub Cognito) — jamais le sub brut
    tenant_id: str              # résolu côté serveur FastAPI

@dataclass(frozen=True)
class OperationContext:
    operation_id: str           # Business Correlation ID (propriété FastAPI — CAM Domaine 9)
    request_id: str
    deadline_epoch_ms: int      # propagé depuis opContext FastAPI

@dataclass
class RetrievalContext:
    status: str                 # "ok" | "degraded" | "skipped"
    chunks: list[dict]
    chunk_count: int            # == len(chunks), vérifié par test de contrat
    policy: str                 # ex. "v1"
    trust: str = "untrusted"    # immuable — contenu documentaire = données non fiables

@dataclass
class AgentRequest:
    message: str
    runtime_session_id: str
    trusted_identity: TrustedIdentity
    operation_context: OperationContext
    retrieval_context: RetrievalContext
    budget: AgentBudget
    config: AgentConfig

@dataclass
class AgentResult:
    answer: str
    turn_count: int
    tool_calls_count: int
    tokens_used: int
    budget_exhausted: bool      # True si un budget a été atteint
    degraded: bool              # True si retrieval dégradé ou tool en erreur
    error: Optional[str] = None
```

### 3.3 Contrat FastAPI → AgentCore Runtime (rappel)

Ce LLD **consomme** le contrat défini dans `architecture/hld/runtime-contract.md`.
Les champs interdits (`cognitoToken`, `authorizationHeader`, `modelOverride`,
`systemPromptOverride`, `toolName`, `actorIdRaw`, `tenantIdRaw`) sont rejetés par un test de
contrat automatisé. Ce test est bloquant en CI.

### 3.4 Champs interdits dans `AgentRequest`

Par symétrie avec le contrat Runtime, les champs suivants ne doivent jamais apparaître dans
`AgentRequest` ni dans les arguments fournis aux tools :

- tout token JWT ou header d'autorisation brut ;
- `actorIdRaw`, `tenantIdRaw` (valeurs Cognito non hashées) ;
- `systemPromptOverride` (le prompt est chargé depuis `PromptRegistry` uniquement) ;
- `modelOverride` (le modèle est configuré dans `AgentConfig`, jamais dans le payload).

---

## 4. Prompts versionnés

### 4.1 Principe

Les prompts système sont versionnés, stockés dans `agents/prompts/`, chargés par le
`PromptRegistry`. La version active est un paramètre de configuration (variable d'environnement
`AGENT_PROMPT_VERSION`), jamais une constante dans le code.

**Pourquoi c'est important :** un prompt peut faire varier le comportement de l'agent de façon
significative. Versionner les prompts permet de tracer quelle version a produit quelle réponse
(attribut de corrélation `promptVersion` dans les logs — CAM Domaine 9).

### 4.2 `PromptRegistry`

```python
class PromptRegistry:
    """
    Charge et met en cache les prompts système versionnés depuis agents/prompts/.
    Deux versions peuvent coexister pour permettre un déploiement progressif.
    """

    def get(self, version: str) -> str:
        """
        Retourne le contenu du prompt système pour la version demandée.
        Lève ValueError si la version est inconnue.
        """
        ...
```

### 4.3 Contenu minimal d'un prompt système

Un prompt système V2 doit inclure :

1. **Rôle et périmètre** — ce que l'agent peut et ne peut pas faire ;
2. **Traitement du contenu documentaire comme donnée non fiable** — instruction explicite de ne
   pas exécuter d'instructions présentes dans les chunks RAG (défense prompt injection) ;
3. **Contraintes de réponse** — format, langue, limites de longueur ;
4. **Comportement en dégradation** — comment répondre lorsque `retrievalContext.status = degraded`
   ou `skipped` ;
5. **Interdiction d'inventer des sources** — les citations doivent être issues de `chunks`,
   jamais générées.

---

## 5. Budgets emboîtés

### 5.1 Pourquoi des budgets

La V1 ne borne que le temps (`deadlineEpochMs`, `MAX_PROMPT_CHARS`). Cela laisse deux vecteurs
de dérive non contrôlés : une boucle agentique qui accumule des tours sans converger, et un agent
qui multiplie les appels tool sans limite. Les budgets V2 ajoutent ces deux dimensions manquantes.

### 5.2 Les quatre dimensions

| Budget | Valeur V2 par défaut (configurable) | Comportement à dépassement |
|---|---|---|
| `maxTurns` | 10 | `BudgetExceededError` → réponse dégradée avec explication |
| `maxToolCalls` | 20 | `BudgetExceededError` → réponse partielle avec indication |
| `maxTokens` | 8 000 (entrée + sortie cumulés) | `BudgetExceededError` → tronque et signale |
| `deadlineEpochMs` | hérité de `operationContext` | `DeadlineExceededError` → retour immédiat |

Les valeurs par défaut sont des paramètres Terraform/SSM — jamais des constantes dans le code.
Le dépassement de n'importe quel budget produit un `AgentResult` avec `budget_exhausted=True`,
jamais une exception non gérée.

### 5.3 Emboîtement

Les budgets sont emboîtés : le budget de la conversation borne chaque tour ; le budget d'un
tour borne chaque appel tool. Un dépassement au niveau inférieur est traité localement (réponse
partielle) sans faire exploser le niveau supérieur — la conversation se termine proprement.

```
Conversation (deadlineEpochMs + maxTurns + maxTokens)
  └─ Tour N (tokens d'entrée + sortie du tour)
       └─ Tool call k (tool_calls_count ≤ maxToolCalls)
```

### 5.4 Modèle configuré

Le `model_id` est un paramètre de `AgentConfig`, pas une constante. Cela est requis par
`V2-ADR-005` pour que `V2-ADR-012` (backlog) puisse faire varier le modèle ou activer un profil
d'inférence Bedrock sans toucher au code domaine.

```
⚠ ADR MANQUANT (V2-ADR-012) : la stratégie de fallback (bascule automatique vers
un modèle alternatif en cas de throttling ou d'erreur Bedrock) n'est pas encore
décidée. Par défaut : pas de fallback automatique ; le budget est épuisé et
AgentResult.error contient la raison. À stabiliser post-ADR-012.
```

---

## 6. Tool allowlists et contrôle

### 6.1 Principe

Chaque appel agentique reçoit une `tool_allowlist` explicite dans `AgentConfig`. L'orchestrateur
ne transmet à l'adapter que les tools présents dans cette liste. Tout appel à un tool absent
produit `ToolDeniedError` et est journalisé.

**Pourquoi c'est important :** sans allowlist explicite, un modèle peut demander des tools non
prévus pour ce parcours, soit par dérive de raisonnement, soit par injection de prompt dans le
contenu documentaire. L'allowlist est la première ligne de défense.

### 6.2 Vérification de l'allowlist

```python
class ToolAllowlist:
    """
    Vérifie qu'un tool est autorisé avant transmission à l'adapter.
    La liste est injectée depuis AgentConfig, jamais construite par le modèle.
    """

    def check(self, tool_name: str) -> None:
        """
        Lève ToolDeniedError si tool_name n'est pas dans la liste autorisée.
        Log un événement de sécurité (niveau WARNING) en cas de refus.
        """
        ...
```

### 6.3 Injection d'identité côté tool

Avant chaque appel tool via AgentCore Gateway MCP, l'adapter injecte `trustedIdentity` dans les
arguments, écrasant toute identité éventuellement produite par le modèle. C'est une exigence
absolue de `V2-ADR-006`.

```
modèle → demande tool("book_trip", args={...})
         ↓
         ToolAllowlist.check("book_trip")  → OK ou ToolDeniedError
         ↓
         args["_identity"] = trustedIdentity  # injection systématique
         ↓
         AgentCore Gateway MCP → tool
```

---

## 7. Streaming

```
⚠ ADR MANQUANT (V2-ADR-011) : le protocole de streaming (SSE, chunked HTTP,
WebSocket) et la gestion des annulations (signal d'annulation côté client,
drain de la boucle agentique) ne sont pas encore décidés.

Proposition par défaut retenue dans ce LLD jusqu'à décision ADR-011 :
- Transport : Server-Sent Events (SSE) via FastAPI StreamingResponse
- Granularité : fragment de texte dès qu'un token est disponible côté Runtime
- Annulation : le client ferme la connexion SSE ; FastAPI détecte la déconnexion
  et propage un signal d'annulation à Runtime via le contexte d'opération
  (deadline_epoch_ms mis à "maintenant")
- Partielle : si Runtime n'expose pas d'API streaming native, FastAPI retourne
  le bloc complet de AgentResult.answer en feignant un stream (mode dégradé
  transparent pour le client, tracé dans les logs)

Cette proposition devra être revue et stabilisée dès que V2-ADR-011 est décidé.
```

---

## 8. Dégradation et fallback

### 8.1 Tableau de dégradation

| Scénario | Comportement | `AgentResult.degraded` | Message client |
|---|---|---|---|
| `retrievalContext.status = degraded` | Réponse sans RAG, instruction du prompt | `true` | « Réponse sans accès aux documents » |
| `retrievalContext.status = skipped` | Réponse normale (pas de RAG requis) | `false` | — |
| Budget `maxTurns` ou `maxToolCalls` dépassé | Retour immédiat avec résultat partiel | `true` | « Réponse partielle, limite atteinte » |
| Budget `maxTokens` dépassé | Réponse tronquée | `true` | « Réponse abrégée » |
| `deadlineEpochMs` dépassé | Retour immédiat | `true` | « Délai dépassé » |
| Tool refusé (`ToolDeniedError`) | Tour sans tool, réponse au modèle | selon impact | Transparent sauf si bloquant |
| Tool en erreur (MCP retourne erreur) | Retry dans budget Tool → dégradé | `true` si non résolu | « Outil indisponible » |
| Bedrock throttling | ⚠ voir ADR-012 (backlog) | `true` | « Service temporairement indisponible » |
| AgentCore Runtime indisponible | FastAPI retourne HTTP 503 | — | Erreur applicative standard |

### 8.2 Règle fondamentale

**La boucle agentique ne doit jamais boucler de façon incontrôlée.** Toute sortie hors des budgets
produit un `AgentResult` structuré. Aucune exception non gérée ne doit atteindre FastAPI.

### 8.3 Annulation client

```
⚠ ADR MANQUANT (V2-ADR-011) : voir §7.
```

---

## 9. IAM et sécurité

### 9.1 Rôle IAM de la tâche ECS Runtime

Le rôle IAM associé à la tâche ECS AgentCore Runtime est défini dans `V2-LLD-001`. Ce LLD
liste uniquement les permissions applicables au domaine agents :

```hcl
# Droits Bedrock Converse API (plan d'exécution)
"bedrock:InvokeModel",
"bedrock:InvokeModelWithResponseStream",  # ⚠ conditionnel — à confirmer post-ADR-011

# Droits AgentCore Memory
"bedrock-agent-runtime:InvokeAgent",       # si Memory via AgentCore

# Droits AgentCore Gateway MCP
"execute-api:Invoke"                       # appels Gateway via IAM Sig v4

# Logs et traces
"logs:CreateLogStream",
"logs:PutLogEvents",
"xray:PutTraceSegments",
"xray:PutTelemetryRecords"
```

Les permissions `s3vectors:*`, `bedrock-agent:*IngestionJob` et `dynamodb:*` appartiennent à
la tâche ECS FastAPI (`V2-LLD-001`), pas à Runtime.

### 9.2 Défense contre le prompt injection

Le contenu documentaire (`retrievalContext.chunks`) est la principale surface d'attaque par
injection de prompt. La défense en profondeur comprend :

1. **Marquage `trust: "untrusted"`** dans `RetrievalContext` — Runtime ne peut pas oublier
   la nature des données (contrat) ;
2. **Instruction explicite dans le prompt système** — l'agent est instruit de ne pas exécuter
   d'instructions présentes dans les chunks ;
3. **Tool allowlist stricte** — même si une injection réussit à formuler une demande de tool
   non autorisé, `ToolAllowlist.check()` la bloque ;
4. **Identité injectée systématiquement** — l'identité ne peut pas être overridée par le modèle.

### 9.3 Traces de décision sans chaîne de pensée sensible

Les logs de décision agentique (quels tools ont été appelés, quels tours se sont produits)
sont émis avec les attributs de corrélation. Le contenu des `chunks` et le prompt brut ne sont
**jamais** loggués en clair — redaction obligatoire (V2-ADR-008).

---

## 10. Observabilité

### 10.1 Attributs de corrélation par span

Chaque span OTel émis par les hooks de l'adapter doit porter :

| Attribut | Source | Exemple |
|---|---|---|
| `agent.operation_id` | `operationContext.operation_id` (hashé) | `"a1b2c3"` |
| `agent.session_id` | `runtimeSessionId` (hashé) | `"d4e5f6"` |
| `agent.model_id` | `AgentConfig.model_id` | `"anthropic.claude-..."` |
| `agent.prompt_version` | `AgentConfig.prompt_version` | `"v1"` |
| `agent.turn_count` | compteur de tours | `3` |
| `agent.tool_calls_count` | compteur d'appels tool | `5` |
| `agent.tokens_used` | tokens cumulés | `2450` |
| `agent.budget_exhausted` | booléen | `false` |
| `agent.degraded` | booléen | `false` |
| `retrieval.status` | `retrievalContext.status` | `"ok"` |

### 10.2 Métriques minimales

| Métrique | Unité | Alerte |
|---|---|---|
| `agent.conversation.latency` | ms (P95) | > 8 000 ms |
| `agent.turns.count` | nombre | > 8 (approche budget) |
| `agent.tool_calls.count` | nombre | > 15 (approche budget) |
| `agent.budget_exceeded.rate` | % conversations | > 5 % |
| `agent.degraded.rate` | % conversations | > 10 % |
| `agent.tool_denied.count` | événements/min | > 0 (alerte sécurité) |
| `bedrock.converse.latency` | ms (P95) | > 5 000 ms |
| `bedrock.converse.error.rate` | % | > 2 % |

### 10.3 Propagation W3C

FastAPI injecte le header `traceparent` dans l'appel à Runtime. Si AgentCore Runtime ne propage
pas nativement ce header vers les tools MCP, la corrélation de repli s'appuie sur
`operationId`/`requestId` — les deux segments sont recoupés dans CloudWatch Logs Insights.
La preuve de corrélation bout en bout est un critère de sortie de gate (§14).

---

## 11. Tests et preuves

### 11.1 Tests d'architecture (bloquants en CI)

| Test | Vérification | Blocant |
|---|---|---|
| Lint d'imports | Aucun fichier hors `agents/adapter/` n'importe `strands.*` | Oui |
| Test de contrat | Champs interdits rejetés dans `AgentRequest` | Oui |
| Test de contrat | `chunkCount == len(chunks)` et cohérence de `status` | Oui |
| Test de contrat | `trust == "untrusted"` dans tout `RetrievalContext` | Oui |

### 11.2 Tests unitaires du domaine (sans Bedrock)

Les tests unitaires remplacent `AgentAdapter.invoke` par un mock — jamais les objets internes
Strands. Aucun appel réseau Bedrock ou MCP en test unitaire (`V2-ADR-005`).

Cas à couvrir :

- dépassement de `maxTurns` → `AgentResult.budget_exhausted = True`
- dépassement de `maxToolCalls` → idem
- dépassement de `maxTokens` → idem
- dépassement de `deadlineEpochMs` → retour immédiat
- tool refusé (`ToolDeniedError`) → log sécurité + réponse partielle
- `retrievalContext.status = degraded` → réponse sans RAG, `degraded = True`
- changement de `MODEL_ID` → aucun fichier domaine modifié (test P-04)

### 11.3 Tests d'intégration

- Appel complet FastAPI → Runtime (stub ou sandbox) avec contrat complet
- Vérification que la `trustedIdentity` est bien transmise et non overridable
- Test cross-tenant : deux utilisateurs ne partagent jamais de contexte Memory ou retrieval

### 11.4 Tests de sécurité négative

- Injection de prompt dans un chunk RAG : vérifier que le tool demandé par le chunk est refusé
  par `ToolAllowlist`
- Tentative d'override d'identité dans le payload : champ rejeté par le validateur de contrat
- Tentative de `modelOverride` dans le payload : rejeté par le validateur

### 11.5 Preuves attendues (gate V2-G2)

- aucun fichier hors `adapter/` n'importe `strands.*` (CI vert) ;
- un dépassement de budget produit un `AgentResult` structuré, sans exception non gérée ;
- les tests unitaires s'exécutent sans appel réseau (mock `AgentAdapter`) ;
- un changement de `MODEL_ID` ne modifie aucun fichier domaine ;
- un `traceId` W3C (ou `operationId` en repli) relie FastAPI → Runtime → tool dans X-Ray /
  CloudWatch Logs Insights ;
- aucun identifiant brut, JWT, prompt ou chunk sensible n'apparaît en clair dans les traces ;
- `ToolAllowlist` bloque tout tool non listé, avec log de sécurité.

---

## 12. Exploitation

### 12.1 Variables d'environnement et configuration SSM

| Variable | Valeur par défaut | Source |
|---|---|---|
| `AGENT_PROMPT_VERSION` | `"v1"` | SSM Parameter Store |
| `AGENT_MAX_TURNS` | `10` | SSM Parameter Store |
| `AGENT_MAX_TOOL_CALLS` | `20` | SSM Parameter Store |
| `AGENT_MAX_TOKENS` | `8000` | SSM Parameter Store |
| `AGENT_MODEL_ID` | `"anthropic.claude-sonnet-4-5-..."` | SSM Parameter Store |
| `AGENT_TOOL_ALLOWLIST` | liste JSON | SSM Parameter Store |

Toutes les valeurs sont injectées par Terraform via SSM — jamais hardcodées dans l'image.

### 12.2 Runbook — budget saturé en production

**Symptôme :** alerte `agent.budget_exceeded.rate > 5 %`

1. Interroger CloudWatch Logs Insights : `filter agent.budget_exhausted = true | stats count by agent.operation_id`
2. Identifier quelle dimension est saturée (turns / tool_calls / tokens) via les attributs de span
3. Si tokens : vérifier la taille des `chunks` dans `retrievalContext` (post-filtrage trop permissif ?)
4. Si turns/tool_calls : vérifier si un tool échoue systématiquement et force des retries
5. Ajuster le budget via SSM sans redéploiement (ECS relit SSM au démarrage de la tâche)

### 12.3 Runbook — tool refusé (alerte sécurité)

**Symptôme :** alerte `agent.tool_denied.count > 0`

1. Chercher dans CloudWatch : `filter event.type = "tool_denied" | fields tool_name, operation_id`
2. Vérifier si le tool demandé est légitime mais absent de l'allowlist (mise à jour de config)
3. Vérifier si le tool demandé est inattendu (potentiel prompt injection)
4. Si injection suspectée : escalader vers sécurité, conserver la trace (opération non destructive)

---

## 13. Dépendances et points ouverts

### 13.1 Dépendances bloquantes

| Composant | LLD ou ADR | Raison |
|---|---|---|
| Contrat FastAPI → Runtime | `runtime-contract.md` | Ce LLD l'implémente côté Runtime |
| Tool allowlist complète | `V2-LLD-004` (MCP) | La liste des tools disponibles est définie dans LLD-004 |
| `trustedIdentity` (format) | `V2-LLD-005` (Identité) | Le format exact de `actorId`/`tenantId` est fixé dans LLD-005 |
| Task IAM Role Runtime | `V2-LLD-001` (Plateforme) | Permissions Bedrock et MCP Gateway dans le rôle ECS |

### 13.2 Points ouverts (à résoudre avant `Approved`)

| Point | ADR concerné | Impact |
|---|---|---|
| Protocole streaming et annulations | V2-ADR-011 (backlog) | §7, §8.3 — proposition SSE en attente |
| Fallback modèle Bedrock (throttling) | V2-ADR-012 (backlog) | §5.4, §9.2 — pas de fallback automatique par défaut |
| Profils d'inférence Bedrock | V2-ADR-012 (backlog) | `inference_profile_id` dans `AgentConfig` |
| Taille maximale des chunks dans `retrievalContext` | V2-LLD-002 §6.2 | Impacte le budget `maxTokens` |
| Support natif `traceparent` par AgentCore Runtime SDK | V2-LLD-007 | Détermine si corrélation directe ou via `operationId` |

---

## 14. Critères de sortie (gate V2-G2)

- [ ] Tests d'architecture (lint imports, contrats) verts en CI
- [ ] Tests unitaires domaine sans dépendance réseau Bedrock
- [ ] Budgets emboîtés vérifiés : chaque dépassement produit un `AgentResult` structuré
- [ ] Tool allowlist active : tout tool hors liste est refusé et tracé
- [ ] Corrélation OTel bout en bout démontrée (traceId ou operationId)
- [ ] Aucun identifiant brut ni chunk sensible en clair dans les logs
- [ ] V2-ADR-011 et V2-ADR-012 décidés et sections §7/§8.3/§5.4 mises à jour
- [ ] Dépendances `V2-LLD-001`, `V2-LLD-004`, `V2-LLD-005` résolues pour les points listés en §13.1
