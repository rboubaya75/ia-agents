# V2-LLD-003 — Agents et orchestration

- **Version :** 0.3
- **Statut :** Draft (propositions — en attente de revue)
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§10)
- **CAM de référence :** `architecture/hld/capability-allocation-matrix.md` (Domaine 5 — Agentic AI)
- **Contrat de référence :** `architecture/hld/runtime-contract.md`
- **ADR de référence :** `V2-ADR-002`, `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-008`, `V2-ADR-011`
  (backlog), `V2-ADR-012` (backlog)
- **Gate :** V2-G2

> **Version 0.1 — Statut propositions :** document de propositions pédagogique destiné à aligner
> l'équipe sur la conception avant implémentation. Les sections marquées `⚠ ADR MANQUANT`
> dépendent de `V2-ADR-011` (streaming + annulations) et `V2-ADR-012` (modèles + fallback), tous
> deux au backlog.
>
> **Révision v0.2 (revue indépendante, bloquants) :** topologie d'exécution du code `/agents` sur
> AgentCore Runtime clarifiée et contradiction « orchestration FastAPI vs Runtime » résolue (§2.3,
> §2.4) ; permissions IAM corrigées et marquées à valider avec la doc AWS (§9.1) ; contrat d'usage
> d'AgentCore Memory ajouté (§2.5) ; budget `maxTokens` désambiguïsé (par conversation) et
> recalibré sur la fenêtre de contexte du modèle (§5.2, §5.3) ; séquencement de la gate V2-G2
> tranché — ce LLD peut passer `Approved` avec les sections streaming/fallback explicitement
> ouvertes, sous contrat de mise à jour dès ADR-011/012 décidés (§14).
>
> **Révision v0.3 (revue indépendante, majeurs + observations) :** filtre d'exposition tool
> distingué de l'autorisation MCP Gateway pour lever le risque P-02 (§6.1) ; `TrustedIdentity`
> complétée avec `roles`/`scopes` (§3.2, ADR-006) ; mode streaming émulé exposé au frontend au lieu
> d'être masqué (§7) ; mitigation temporaire du throttling Bedrock (retry exponentiel borné) en
> attendant ADR-012 (§5.4) ; lint d'imports rendu générique multi-framework (§2.1, §11.1) ;
> `RetrievalContext`/`AgentRequest` rendus `frozen`, `AgentResult.error` typé (`AgentError`/enum) et
> tokens séparés input/output (§3.2) ; chemin de migration V1→V2 ajouté (§12.4) ; métriques de coût
> et tokens input/output ajoutées (§10).

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
toute importation d'un **framework agentique** en dehors du répertoire `agents/adapter/`. La liste
des préfixes interdits est configurable (`strands`, `langgraph`, `autogen`, …) pour rester valable
si un second adapter est ajouté — elle n'est pas figée à `strands.*`. Ce test est bloquant.

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

### 2.3 Modèle d'exécution et flux d'invocation

**Où s'exécute le code `/agents` ?** AgentCore Runtime est un service AWS managé, pas un conteneur
que l'équipe opère directement. Le code du répertoire `/agents` n'est donc pas exécuté « à
l'intérieur » d'un composant AWS contrôlé : il est **packagé et déployé comme l'agent custom que
Runtime héberge et invoque**. Runtime fournit le processus hôte et le point d'entrée ; le code
`/agents` fournit la logique agentique (orchestrateur, budgets, adapter). Cette distinction
gouverne le packaging, l'injection du contrat et l'observabilité (voir ci-dessous).

**Packaging et déploiement :**

- Le code `/agents` (adapter Strands + domaine) est packagé sous la forme attendue par AgentCore
  Runtime (image conteneur ou artefact de déploiement selon le mode Runtime retenu). Le mode exact
  et la task definition sont **fixés par `V2-LLD-001`** (plateforme). Ce LLD fixe le contenu et les
  contrats du code déployé, pas son mode de packaging AWS.
- Le point d'entrée Runtime reçoit le payload `runtime-contract.md` (voir §3.3) et le désérialise
  en `AgentRequest` (§3.2) avant d'appeler `orchestrator.run(request)`.
- **Observabilité (renvoi ADR-008) :** ADR-008 décrit un collector ADOT en sidecar pour les tâches
  **ECS FastAPI**. Runtime étant managé, la faisabilité d'un sidecar y est incertaine : la
  stratégie d'export des traces depuis le code agent (SDK OTel exportant directement, ou
  corrélation de repli via `operationId`) est un **point ouvert tranché en `V2-LLD-007`** (§13.2).

Le schéma ci-dessous représente le chemin d'une requête conversationnelle de bout en bout. FastAPI
est le coordinateur applicatif ; le code `/agents`, exécuté par Runtime, est l'exécuteur agentique.

```
Utilisateur
    │
    ▼
API Gateway (JWT validé, claims extraits)
    │
    ▼
FastAPI  (workflow applicatif — coordinateur)
 ├─ 1. Autorisation (tenantId, actorId, rôles/scopes — V2-ADR-006)
 ├─ 2. Retrieval → retrievalContext borné (V2-LLD-002)
 ├─ 3. Assemblage contrat Runtime (runtime-contract.md)
 │       { message, runtimeSessionId, trustedIdentity,
 │         operationContext, retrievalContext }
 └─ 4. Invocation AgentCore Runtime ─────────────────────────┐
                                                             │
   ┌─────────────────────────────────────────────────────────┐
   │ AgentCore Runtime (service managé)                      │
   │   héberge et invoque le code /agents déployé :          │
   │                                                         │
   │   point d'entrée → désérialise AgentRequest             │
   │     └─ domain/orchestrator.py (boucle agentique)        │
   │          └─ AgentAdapter.invoke(request)                │
   │                └─ StrandsAdapter                        │
   │                      ├─ budget_guard (turns/tools/tokens)│
   │                      ├─ tool_allowlist (filtre exposition)│
   │                      ├─ AgentCore Memory (lecture, §2.5) │
   │                      ├─ Bedrock Converse API (claude-*)  │
   │                      ├─ AgentCore Gateway MCP (tools)    │
   │                      └─ AgentCore Memory (écriture, §2.5)│
   │   → AgentResult                                          │
   └─────────────────────────────────────────────────────────┘
                                                             │
FastAPI  ◀───────────────────────────────────────────────────┘
 └─ 5. Réponse client (stream ou bloc)
```

**Points critiques du flux :**

1. FastAPI ne fait jamais d'appel direct à Bedrock Converse API sur le chemin conversationnel —
   uniquement via l'invocation Runtime. Toute déviation est une violation P-02 bloquante.
2. Le contenu du `retrievalContext` est marqué `trust: "untrusted"` — le code agent ne peut pas le
   traiter comme une source d'autorité (règle V2-ADR-002).
3. `trustedIdentity` est construite par FastAPI ; le code agent et les tools écrasent toute
   identité produite par le modèle avant chaque appel tool (V2-ADR-006).

### 2.4 Deux sens du mot « orchestration » — levée d'ambiguïté

Le corpus V2 emploie « orchestration » dans deux acceptions distinctes qu'il faut séparer pour
éviter une fausse contradiction entre le HLD (« FastAPI … orchestration ») et la CAM (Domaine 5,
`Conversation Orchestration → AgentCore Runtime`).

| Terme | Propriétaire | Portée |
|---|---|---|
| **Workflow Coordination** (orchestration applicative) | FastAPI (CAM Domaine 3) | Décide du parcours : autorisation, retrieval, assemblage du contrat, appel Runtime, formatage de la réponse. Ne raisonne pas, n'appelle pas Converse API. |
| **Conversation Orchestration** (boucle agentique) | AgentCore Runtime via le code `/agents` (CAM Domaine 5) | Boucle tours modèle/tool, raisonnement, sélection de tools, invocation Converse API, gestion Memory. Ne décide pas du parcours applicatif. |

Il n'y a donc pas de double propriété : FastAPI coordonne *quand* invoquer l'agent ; le code
`/agents` orchestre *ce qui se passe* pendant l'invocation. Le contrat `runtime-contract.md` est la
frontière exacte entre les deux.

**Orchestrateur agentique (Domaine 5) — périmètre en V2 :** un orchestrateur unique est retenu
(`V2-ADR-005`), aucun multi-agent tant qu'un besoin concret n'est pas documenté ; l'ajout d'un
agent spécialisé exige un **amendement ADR ou une justification explicite dans ce LLD** (P-01/P-02).
Il gère :

- l'instanciation de l'adapter configuré ;
- l'application des budgets emboîtés avant chaque tour ;
- le filtrage d'exposition des tools (allowlist, §6) avant chaque tour ;
- la construction du message système depuis le `PromptRegistry` ;
- la lecture/écriture Memory selon le contrat §2.5 ;
- le retour structuré `AgentResult`.

### 2.5 AgentCore Memory — contrat d'usage

La **propriété** de Memory (stockage, TTL, rétention, effacement, isolation des namespaces) est
couverte par `V2-LLD-006`. Le présent LLD fixe seulement l'**usage** de Memory par le code agent,
qui relève du Domaine 5 (comportement agentique).

| Question | Décision V2 |
|---|---|
| **Quand lire ?** | Une seule lecture par invocation, **avant le premier tour**, pour hydrater le contexte (préférences + résumé conversationnel). Pas de relecture par tour (coût tokens + latence). |
| **Quand écrire ?** | Une seule écriture par invocation, **après le dernier tour réussi**, avec le résumé/préférences mis à jour. Aucune écriture si l'invocation échoue avant production d'un `AgentResult` valide. |
| **Namespace** | Dérivé de `trustedIdentity` : `namespace = hash(tenantId + "#" + actorId)`. Formule exacte et politique alignées sur `V2-LLD-005`/`V2-LLD-006`. Jamais dérivé d'un claim brut. |
| **Confiance du contenu** | Le contenu Memory (préférences saisies par l'utilisateur, résumés dérivés de conversations) est traité comme **donnée non fiable** au même titre que `retrievalContext` : le prompt système interdit d'exécuter une instruction qui y figurerait. |
| **Comptage tokens** | Les tokens injectés depuis Memory dans le prompt final **comptent** dans `agent.tokens_used` et dans le budget `maxTokens` (§5.2). |
| **Indisponibilité** | Si Memory est indisponible en lecture, l'invocation continue sans contexte mémorisé et `AgentResult.degraded = true` (voir §8.1). Une écriture échouée est journalisée et retentée hors chemin critique, sans casser la réponse. |

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
from enum import Enum
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
    roles: tuple[str, ...]      # rôles résolus côté serveur (ADR-006) — tuple = immuable
    scopes: tuple[str, ...]     # scopes autorisés (ADR-006)
    # roles/scopes permettent au filtre d'exposition tool (§6) de dépendre du rôle ;
    # ils ne remplacent pas l'autorisation MCP Gateway (P-01)

@dataclass(frozen=True)
class OperationContext:
    operation_id: str           # Business Correlation ID (propriété FastAPI — CAM Domaine 9)
    request_id: str
    deadline_epoch_ms: int      # propagé depuis opContext FastAPI

@dataclass(frozen=True)            # frozen : trust et status ne peuvent pas muter après construction
class RetrievalContext:
    status: str                 # "ok" | "degraded" | "skipped"
    chunks: tuple[dict, ...]     # tuple (immuable) plutôt que list
    chunk_count: int            # == len(chunks), vérifié par test de contrat
    policy: str                 # ex. "v1"
    trust: str = "untrusted"    # immuable par frozen — contenu = données non fiables

@dataclass(frozen=True)
class AgentRequest:
    message: str
    runtime_session_id: str
    trusted_identity: TrustedIdentity
    operation_context: OperationContext
    retrieval_context: RetrievalContext
    budget: AgentBudget
    config: AgentConfig

class AgentErrorCode(Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    TOOL_DENIED = "tool_denied"
    MODEL_THROTTLED = "model_throttled"
    TOOL_UNAVAILABLE = "tool_unavailable"
    MEMORY_UNAVAILABLE = "memory_unavailable"

@dataclass(frozen=True)
class AgentError:
    code: AgentErrorCode        # catégorie discriminable (observabilité, alerting)
    message: str                # détail humain, redacted

@dataclass
class AgentResult:
    answer: str
    turn_count: int
    input_tokens: int           # facturation Bedrock distincte entrée/sortie (voir §10.2)
    output_tokens: int
    tool_calls_count: int
    budget_exhausted: bool      # True si un budget a été atteint
    degraded: bool              # True si retrieval/Memory dégradé ou tool en erreur
    error: Optional[AgentError] = None   # typé, plus un str libre

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens
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

Tous les budgets sont comptés **par invocation** (une invocation = un appel Runtime traitant un
message utilisateur, potentiellement plusieurs tours modèle/tool). Aucun budget n'est « par tour » :
le tour est le grain qui *consomme* le budget, pas le grain qui le *porte*.

| Budget | Portée | Valeur V2 par défaut (configurable) | Comportement à dépassement |
|---|---|---|---|
| `maxTurns` | invocation | 10 | `BudgetExceededError` → réponse dégradée avec explication |
| `maxToolCalls` | invocation | 20 | `BudgetExceededError` → réponse partielle avec indication |
| `maxTokens` | invocation | voir §5.2.1 (dérivé du modèle) | `BudgetExceededError` → tronque et signale |
| `deadlineEpochMs` | invocation | hérité de `operationContext` | `DeadlineExceededError` → retour immédiat |

Les valeurs par défaut sont des paramètres Terraform/SSM — jamais des constantes dans le code.
Le dépassement de n'importe quel budget produit un `AgentResult` avec `budget_exhausted=True`,
jamais une exception non gérée.

#### 5.2.1 Calibrage de `maxTokens`

`maxTokens` compte le **cumul entrée + sortie de tous les tours de l'invocation** — pas un tour
isolé. Il inclut : prompt système, message utilisateur, contexte Memory injecté (§2.5),
`retrievalContext.chunks`, l'historique inter-tours, les résultats de tools réinjectés, et toute
la sortie modèle produite.

Une constante fixe (l'ancien « 8 000 ») est **inadaptée** : un `retrievalContext` de 5 chunks à
~500 tokens consomme déjà ~2 500 tokens de seul contexte, ce qui saturerait une conversation RAG
dès le deuxième tour. `maxTokens` est donc **dérivé de la fenêtre de contexte du modèle configuré**
(`AgentConfig.model_id`), pas d'un nombre en dur :

```
maxTokens_défaut = floor(fenêtre_contexte_modèle × 0,75)
```

La marge de 25 % réserve de la place à la sortie finale et évite de heurter la limite dure du
modèle. La valeur effective est calculée au démarrage à partir d'une table
`modèle → fenêtre_contexte` (maintenue avec `V2-ADR-012`) et peut être plafonnée plus bas par SSM
pour maîtriser le coût. La cohérence avec la taille maximale de `retrievalContext.chunks`
(`V2-LLD-002` §6.2) est un point ouvert (§13.2).

### 5.3 Emboîtement

Les budgets d'invocation bornent le déroulé interne : le compteur de tours borne le nombre
d'itérations, le compteur d'appels tool borne les effets de bord, le compteur de tokens cumulés
borne le contexte total. Un dépassement détecté en cours de boucle arrête proprement l'invocation
et produit un `AgentResult` partiel — la boucle ne « déborde » jamais silencieusement.

```
Invocation (deadlineEpochMs + maxTurns + maxToolCalls + maxTokens, cumulés)
  └─ Tour N   (consomme des tokens entrée + sortie, incrémente turn_count)
       └─ Tool call k (incrémente tool_calls_count, borné par maxToolCalls)
```

### 5.4 Modèle configuré

Le `model_id` est un paramètre de `AgentConfig`, pas une constante. Cela est requis par
`V2-ADR-005` pour que `V2-ADR-012` (backlog) puisse faire varier le modèle ou activer un profil
d'inférence Bedrock sans toucher au code domaine.

```
⚠ ADR MANQUANT (V2-ADR-012) : la stratégie de fallback (bascule automatique vers
un modèle alternatif en cas de throttling ou d'erreur Bedrock) n'est pas encore
décidée. Le choix "modèle de repli" reste ouvert.
```

**Mitigation temporaire (non préemptive d'ADR-012).** L'absence de fallback ne peut pas laisser
chaque `ThrottlingException` casser une conversation — le throttling Bedrock est fréquent en
production sur les modèles récents. En attendant ADR-012, l'adapter applique une mitigation
**locale et minimale**, qui ne présuppose aucun modèle de repli :

- retry exponentiel sur `ThrottlingException` **uniquement** : max 2 tentatives (≈ 500 ms puis
  1 s, avec jitter) ;
- chaque retry est **borné par `deadlineEpochMs`** — aucun retry si le budget temps est déjà
  dépassé ;
- aucun autre code d'erreur Bedrock ne déclenche de retry (échec immédiat, `AgentError` typée) ;
- si les retries échouent : `AgentResult.error = AgentError(MODEL_THROTTLED, …)`, `degraded = true`.

ADR-012 pourra remplacer cette mitigation par une vraie stratégie de fallback (modèle alternatif,
profil d'inférence). D'ici là, cette mitigation est un choix technique local, révisable.

---

## 6. Tool allowlists et contrôle

### 6.1 Deux contrôles distincts — pas de duplication de capacité

La CAM attribue `Tool Authorization` à **MCP Gateway** (Domaine 7). La `tool_allowlist` de ce LLD
n'est **pas** une seconde implémentation de cette capacité — ce serait une violation P-02. Les deux
contrôles ont des rôles différents et complémentaires :

| Contrôle | Question | Propriétaire | Principe |
|---|---|---|---|
| **Tool Exposure Filter** (allowlist, §6.2) | « Quels tools sont *exposables* au modèle pour ce parcours ? » | Orchestrateur `/agents` (ce LLD) | P-04 — restreint le catalogue présenté au modèle |
| **Tool Authorization** | « Cet appelant peut-il *exécuter* ce tool sur cette ressource ? » | MCP Gateway (CAM Dom.7, `V2-LLD-004`) | P-01 — contrôle d'accès effectif |

Le filtre d'exposition réduit la surface d'attaque en amont (le modèle ne « voit » que les tools
pertinents) ; l'autorisation MCP Gateway reste la ligne de défense qui décide réellement de
l'exécution, en aval, sur la base de l'identité injectée. Le filtre d'exposition ne dispense
**jamais** de l'autorisation Gateway (défense en profondeur — CAM Domaine 10).

**Pourquoi le filtre d'exposition est important :** sans lui, un modèle peut demander des tools non
prévus pour ce parcours, soit par dérive de raisonnement, soit par injection de prompt dans le
contenu documentaire. Le filtre `tool_allowlist` est la première ligne de défense ; l'autorisation
Gateway est la dernière.

### 6.2 Filtre d'exposition (allowlist)

```python
class ToolExposureFilter:
    """
    Filtre d'exposition (P-04) : restreint le catalogue de tools présenté au modèle
    pour un parcours donné. N'est PAS l'autorisation d'exécution (propriété MCP Gateway).
    La liste est injectée depuis AgentConfig, jamais construite par le modèle.
    """

    def check(self, tool_name: str) -> None:
        """
        Lève ToolDeniedError si tool_name n'est pas dans la liste exposée.
        Log un événement de sécurité (niveau WARNING) en cas de refus.
        Un refus ici signale une dérive du modèle ou une injection — pas une
        décision d'autorisation, qui reste du ressort de MCP Gateway en aval.
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

Mode émulé si Runtime ne stream pas nativement — EXPOSÉ, jamais masqué :
- FastAPI annonce le mode dans le premier événement SSE :
    event: meta
    data: {"streaming": "emulated"}   (vs "native")
- Le frontend adapte l'UX en conséquence : « génération en cours » (native)
  vs « préparation de la réponse » + spinner (emulated). Pas de fausse
  animation token-par-token sur une réponse déjà complète.
- La métrique time-to-first-token (§10.2) distingue les deux modes : en émulé
  elle mesure la latence réelle de la réponse complète, pas un premier token
  fictif. La valeur n'est donc jamais trompeuse.
```

> **Note de revue (M3) :** feindre un stream token-par-token sur une réponse déjà complète est une
> anti-UX (attente longue puis fausse animation, `time-to-first-token` mensongère). Le mode émulé
> est donc **exposé** au frontend via l'événement `meta`, jamais masqué : un défaut d'infrastructure
> ne doit pas être caché derrière une animation.

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
| Memory indisponible en lecture (§2.5) | Invocation sans contexte mémorisé | `true` | Transparent |
| Memory indisponible en écriture (§2.5) | Journalisé, retenté hors chemin critique | `false` | Transparent |
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

### 9.1 Rôle IAM de l'exécution agent (Runtime)

Le rôle IAM effectif est **défini et provisionné par `V2-LLD-001`** (plateforme) ; ce LLD ne fait
qu'énumérer les permissions dont le domaine agents a **fonctionnellement** besoin. Il ne fige pas
les noms d'actions : plusieurs préfixes AgentCore ci-dessous sont donnés à titre indicatif et
**doivent être validés contre la documentation AWS AgentCore en vigueur** avant implémentation
(les services AgentCore Runtime / Memory / Gateway sont récents et leurs préfixes IAM ont évolué).

> ⚠ **À valider avec la doc AWS (avant `Approved`).** La v0.1 listait
> `bedrock-agent-runtime:InvokeAgent` pour Memory et `execute-api:Invoke` pour Gateway MCP : ces
> deux actions étaient **incorrectes**. `bedrock-agent-runtime:InvokeAgent` cible l'invocation d'un
> **Bedrock Agent managé** (service distinct, non retenu — cf. CAM « pas de managed Agents »), et
> `execute-api:Invoke` ne s'applique qu'à un stage **API Gateway REST**, pas à un composant
> AgentCore Gateway. Les préfixes corrects relèvent de la famille `bedrock-agentcore:*` (Runtime,
> Memory, Gateway), à confirmer nominativement.

| Besoin fonctionnel | Action IAM (à confirmer) | Note |
|---|---|---|
| Invocation modèle (Converse) | `bedrock:InvokeModel` | plan d'exécution |
| Invocation modèle en streaming | `bedrock:InvokeModelWithResponseStream` | conditionnel — dépend d'ADR-011 |
| Lecture/écriture AgentCore Memory | `bedrock-agentcore:*` (Memory) — **à confirmer** | remplace l'ancien `bedrock-agent-runtime:InvokeAgent` (faux) |
| Appel des tools via AgentCore Gateway MCP | `bedrock-agentcore:*` (Gateway) — **à confirmer** | remplace l'ancien `execute-api:Invoke` (faux) |
| Logs applicatifs | `logs:CreateLogStream`, `logs:PutLogEvents` | — |
| Traces | `xray:PutTraceSegments`, `xray:PutTelemetryRecords` | déjà provisionnées en V1 (ADR-008) |

Les permissions `s3vectors:*`, `bedrock-agent:*IngestionJob` et `dynamodb:*` appartiennent à la
tâche ECS **FastAPI** (`V2-LLD-001`), pas à l'exécution agent. Le principe du moindre privilège
impose de restreindre chaque action par `Resource` (ARN du modèle, de la Memory, de la Gateway),
détail porté par `V2-LLD-001`.

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
| `agent.input_tokens` | tokens d'entrée cumulés | `1800` |
| `agent.output_tokens` | tokens de sortie cumulés | `650` |
| `agent.cost_estimate_usd` | coût estimé (input × tarif_in + output × tarif_out du modèle) | `0.0123` |
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
| `agent.cost_estimate_usd` | USD/conversation (P95) | seuil FinOps fixé en LLD-007 |
| `bedrock.converse.latency` | ms (P95) | > 5 000 ms |
| `bedrock.converse.error.rate` | % | > 2 % |
| `bedrock.throttled.rate` | % appels Converse | > 1 % (déclenche mitigation §5.4) |

Les tarifs input/output par modèle (`cost_estimate_usd`) proviennent de la même table
`modèle → tarifs` que le calibrage de `maxTokens` (§5.2.1), maintenue avec `V2-ADR-012`. Le HLD §13
exige explicitement la métrique de coût estimé ; fusionner input et output la rendrait inexploitable
(Bedrock facture la sortie ~5× l'entrée).

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
| Lint d'imports | Aucun fichier hors `agents/adapter/` n'importe un framework agentique (liste configurable : `strands`, `langgraph`, …) | Oui |
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

### 12.4 Migration V1 → V2

La V1 (`deploy-agentcore/agents/phase_4.py`, `phase_4_robust.py`) importe Strands directement au
niveau module (`from strands import Agent`, `BedrockModel`, `MCPClient`, `FileSessionManager`) et
mêle logique métier et SDK. La cible V2 isole tout le SDK derrière `AgentAdapter`. Le passage est
un **refactor incrémental**, pas une réécriture from-scratch, en quatre étapes vérifiables :

| Étape | Action | Point de rupture |
|---|---|---|
| 1 | Extraire l'interface `AgentAdapter` (§3.1) et `StrandsAdapter` en enveloppant l'usage V1 existant, sans changer le comportement | Aucun — le comportement reste identique |
| 2 | Déplacer la logique métier (budgets, hooks, sélection de prompt) de `phase_4*.py` vers `domain/`, en ne dépendant plus que de `interface.py` | Les imports `strands.*` disparaissent du domaine |
| 3 | Activer le lint d'imports (§2.1) en CI ; à ce stade il doit passer au vert | **Rupture dure** : tout import framework résiduel hors `adapter/` casse le build |
| 4 | Ajouter les budgets non temporels V2 (`maxTurns`, `maxToolCalls`, `maxTokens` §5) absents en V1, et le contrat Memory (§2.5) | Nouveau comportement — couvert par tests unitaires §11.2 |

Le moment où `strands.*` disparaît du domaine (étape 2→3) est le jalon de conformité P-04. Avant ce
jalon, le lint est en warning ; après, il est bloquant.

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

**Séquencement vis-à-vis des ADR au backlog.** `V2-ADR-011` (streaming) et `V2-ADR-012` (fallback)
ne sont **pas** des prérequis au passage `Approved` de ce LLD. Les décider n'est pas sous le
contrôle de ce LLD, et les capacités qu'ils couvrent (streaming, fallback modèle) sont
**isolées dans des sections explicitement marquées `⚠ ADR MANQUANT`** (§7, §8.3, §5.4) qui ne
bloquent aucune autre partie de la conception. Ce LLD peut donc être `Approved` avec ces sections
ouvertes, **sous contrat de mise à jour** : dès qu'ADR-011 ou ADR-012 est décidé, les sections
correspondantes sont révisées et une nouvelle version du LLD est produite. Ce contrat est lui-même
un critère de sortie (dernière case ci-dessous).

Critères bloquants pour `Approved` :

- [ ] Tests d'architecture (lint imports, contrats) verts en CI
- [ ] Tests unitaires domaine sans dépendance réseau Bedrock
- [ ] Budgets d'invocation vérifiés : chaque dépassement produit un `AgentResult` structuré
- [ ] `maxTokens` dérivé de la fenêtre de contexte du modèle configuré, pas d'une constante (§5.2.1)
- [ ] Contrat d'usage Memory (§2.5) implémenté : lecture avant 1er tour, écriture après dernier tour, namespace dérivé de `trustedIdentity`
- [ ] Tool allowlist active : tout tool hors liste est refusé et tracé
- [ ] Permissions IAM (§9.1) validées nominativement contre la doc AWS AgentCore en vigueur
- [ ] Corrélation OTel bout en bout démontrée (traceId ou operationId)
- [ ] Aucun identifiant brut ni chunk sensible en clair dans les logs
- [ ] Dépendances `V2-LLD-001`, `V2-LLD-004`, `V2-LLD-005` résolues pour les points listés en §13.1
- [ ] Contrat de mise à jour post-ADR acté : §7/§8.3/§5.4 révisées dès ADR-011/012 décidés (non bloquant pour `Approved`, bloquant pour clôture du suivi)
