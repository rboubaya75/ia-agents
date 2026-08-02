# V2-LLD-003 — Agents et orchestration

- **Version :** 0.6
- **Statut :** Draft (propositions — en attente de revue)
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§10)
- **CAM de référence :** `architecture/hld/capability-allocation-matrix.md` (Domaine 5 — Agentic AI)
- **Contrat de référence :** `architecture/hld/runtime-contract.md`
- **ADR de référence :** `V2-ADR-002`, `V2-ADR-005`, `V2-ADR-006`, `V2-ADR-008`, `V2-ADR-011`,
  `V2-ADR-012`
- **Gate :** V2-G2

> **Révision v0.6 (alignement sur `V2-ADR-020` et `V2-LLD-005`) :** `TrustedIdentity` revient aux
> deux champs de `runtime-contract.md` §2. `roles`/`scopes`, ajoutés en v0.3, sont **retirés** : la
> CAM Domaine 1 attribue `Business Authorization` à FastAPI et l'interdit à Runtime, et
> `V2-LLD-005 §3.6` en tire la conséquence — un composant qui reçoit des rôles finit par les
> évaluer. Le filtre d'exposition (§6.2) consomme la `tool_allowlist` résolue par FastAPI, qui est
> le **résultat** de la décision d'autorisation et non ses intrants ; le filtre ne perd aucune
> capacité. `actor_id` cesse d'être décrit comme un condensat : c'est le claim `sub` du jeton
> d'accès vérifié, transmis tel quel (`V2-LLD-005 §3.1`), le hachage produisant `subjectId` qui ne
> franchit pas ce contrat. Namespace Memory (§2.5) : `isolation_hash` (SHA-256 complet) remplace
> `hash`, la troncature à 48 bits étant réservée aux journaux (`V2-LLD-005 §3.2`).
>
> **Révision v0.5 (alignement sur `V2-ADR-011` et `V2-ADR-012` acceptés) :** les six marqueurs
> `⚠ ADR MANQUANT` sont levés. Streaming (`V2-ADR-011`) — le maillon faible n'était pas Runtime mais
> l'ingress : Runtime diffuse nativement, le transport exige REST API en mode `STREAM` et le mode
> `emulated` redevient un repli d'infrastructure (§7) ; contrat d'événements SSE, keep-alive et
> plafonds temporels intégrés (§5.2, §7.2) ; annulation coopérative par endpoint et registre partagé,
> avec ses points d'annulation et ses effets (§8.3). Modèles (`V2-ADR-012`) — `model_id` devient
> `invocation_id`, identifiant d'invocation opaque, et `fallback_invocation_id` apparaît (§3.2) ; la
> mitigation temporaire du throttling est remplacée par la séquence décidée, dont la **règle du
> premier token** (§5.4) ; compatibilité de capacité vérifiée au démarrage et table indexée sur
> l'identifiant d'invocation (§5.2.1) ; IAM élargi au profil d'inférence et aux régions de
> destination (§9.1) ; variables de configuration renommées et repli ajouté (§12.1) ; sonde de cycle
> de vie et invocation de contrôle du repli (§5.4.4, §10.2). Points ouverts et critères de gate mis à
> jour en conséquence (§13, §14).
>
> **Version 0.1 — Statut propositions :** document de propositions pédagogique destiné à aligner
> l'équipe sur la conception avant implémentation. Les sections alors marquées `⚠ ADR MANQUANT`
> dépendaient de `V2-ADR-011` (streaming + annulations) et `V2-ADR-012` (modèles + fallback), tous
> deux au backlog à cette date — décidés depuis, cf. révision v0.5.
>
> **Révision v0.2 (revue indépendante, bloquants) :** topologie d'exécution du code `/agents` sur
> AgentCore Runtime clarifiée et contradiction « orchestration FastAPI vs Runtime » résolue (§2.3,
> §2.4) ; permissions IAM corrigées et marquées à valider avec la doc AWS (§9.1) ; contrat d'usage
> d'AgentCore Memory ajouté (§2.5) ; budget `maxTokens` désambiguïsé (par invocation) et
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
>
> **Révision v0.4 (corrections revue PR #37) :** en-tête v0.2 corrigé — `maxTokens` désambiguïsé
> **par invocation** (non « par conversation ») ; valeur par défaut `AGENT_MAX_TOKENS` corrigée
> dans §12.1 — remplacée par la formule dérivée `floor(ctx_modèle × 0,75)` (§5.2.1) ; constante
> `8000` retirée, cohérente avec la suppression opérée en v0.2 (bloquant B4) ; commentaire de
> `AgentBudget.max_tool_calls` aligné sur « par invocation » (§3.2) — il restait la dernière
> occurrence de « par conversation » et portait la contradiction dans le contrat normatif lui-même,
> celui dont part l'implémentation ; ce LLD ajouté à la liste de validation Markdown de la CI
> (`.github/workflows/test-markdown-docs.yml`), avec LLD-001/002/006 et ADR-019 qui n'y figuraient
> pas non plus.

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
| V2-ADR-011 | Flux perçu comme progressif ; conversation multi-tours au-delà de 29 s ; l'annulation **arrête la consommation facturée**, pas seulement l'affichage ; aucun effet de tool à moitié appliqué ; aucune dégradation silencieuse — le mode servi est déclaré ; l'annulation est autorisée (`V2-ADR-006`) |
| V2-ADR-012 | Le modèle est un paramètre injecté ; `maxTokens` dérivé de la fenêtre du modèle effectif ; une `ThrottlingException` isolée ne casse pas une conversation ; toute sortie hors budget produit un `AgentResult` structuré ; throttling et coût par invocation observables |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-002 | Décision structurante : Runtime est l'unique propriétaire de la boucle agentique (CAM Domaine 5). FastAPI ne fait qu'initier l'appel via le contrat `runtime-contract.md`. Toute capacité agentique hors Runtime est une violation P-02. |
| V2-ADR-005 | Structure `/agents` (adapter / interface / domain). Strands confiné au module `adapter/`. Orchestrateur unique par défaut. Budgets `maxTurns`, `maxToolCalls`, `maxTokens`, `deadlineEpochMs` injectés par configuration, jamais codés en dur. |
| V2-ADR-006 | `trustedIdentity` construite par FastAPI et transmise au Runtime. Runtime et tools écrasent toute identité produite par le modèle. Aucun token Cognito en dehors de FastAPI. |
| V2-ADR-008 | Propagation `traceparent` W3C de FastAPI → Runtime → tools. Corrélation de repli via `operationId`/`requestId` si Runtime ne propage pas le header nativement. Hooks budget émettent des spans OTel. |
| V2-ADR-011 | Runtime **diffuse nativement** (`InvokeAgentRuntime` → `text/event-stream`) : le mode `emulated` n'est plus une hypothèse sur Runtime mais un repli d'infrastructure déclaré (§7). Jeu d'événements SSE minimal (`meta`, `delta`, `citation`, `done`, `cancelled`, `error`, `: ping`). Annulation **coopérative** par endpoint dédié et registre partagé, jamais par la seule détection de déconnexion ; points d'annulation évalués hors exécution d'un tool à effet de bord ; `deadlineEpochMs` borné sous les plafonds de la chaîne (§5.2, §8.3). |
| V2-ADR-012 | Le domaine transporte un **identifiant d'invocation opaque** (`invocation_id`), jamais un nom de modèle : en `eu-west-3` un modèle récent ne s'invoque que par profil d'inférence. Repli sur un **second identifiant à quota distinct**, interdit dès qu'un token de sortie a été émis (**règle du premier token**), déclaré au client. Compatibilité de capacité du repli vérifiée **au démarrage**. Cycle de vie des modèles surveillé par sonde ; repli exercé périodiquement. Profil global interdit en `staging`/`production` (§5.2.1, §5.4, §9.1, §12.1). |

### 1.3 Préconditions d'infrastructure héritées des ADR

`V2-ADR-011` et `V2-ADR-012` sont décidés, mais leur **activation** dépend de faits à prouver avant
implémentation. Ce LLD hérite de ces préconditions ; il ne les lève pas.

| Précondition | ADR | Repli sans nouvel ADR |
|---|---|---|
| *Response streaming* API Gateway REST (`responseTransferMode = STREAM`) et VPC Link V2 vers ALB disponibles en `eu-west-3` | `V2-ADR-011` | mode `emulated` **déclaré** (§7.3) — jamais masqué |
| Liste nominative des régions de destination du profil géographique EU | `V2-ADR-012` | aucune : la politique IAM en dépend directement (§9.1) |
| Modèle primaire **et** modèle de repli invocables depuis `eu-west-3` comme région source | `V2-ADR-012` | repli non configuré → séquence §5.4 s'arrête à l'étape 3 |
| Profil applicatif accepté par `ConverseStream` et n'ouvrant pas de quota distinct | `V2-ADR-012` | profil géographique EU en direct |

Ces préconditions sont de même nature que celle de `V2-LLD-002 §1.6` : la décision d'architecture est
prise, son activation est conditionnée à une vérification datée.

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
applicatif, agents spécialisés (si instanciés), prompts versionnés, budgets emboîtés et leur
réconciliation avec les plafonds de la chaîne, tool allowlists, contrat FastAPI → Runtime,
propagation d'identité, corrélation OTel, contrat de streaming côté domaine, **sémantique
d'annulation coopérative** (points d'annulation et effets), identifiant d'invocation et **séquence
de repli modèle**, dégradation.

**Exclus (autres LLD) :**
- Plateforme ECS, Task IAM Role, variables d'environnement → `V2-LLD-001`
- Transport SSE (type d'API Gateway, VPC Link, idle timeout ALB, route `cancel`) → `V2-LLD-001`
- Stockage du registre d'annulation (table, TTL, cohérence de lecture) → `V2-LLD-006`
- Rendu frontend du mode de streaming et de l'annulation → `V2-LLD-010`
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
│   ├── tool_allowlist.py     # validation de la tool allowlist du parcours (AgentConfig)
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
   │                      ├─ Bedrock Converse (invocation_id) │
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
| **Namespace** | Dérivé de `trustedIdentity` : `namespace = isolation_hash(tenantId + "#" + actorId)` — SHA-256 complet (64 hex), formule et nom définis en `V2-LLD-005 §3.3`. `safe_hash` (48 bits) est réservé aux journaux ; une collision de namespace est une violation d'isolation, pas une ambiguïté de log. Jamais dérivé d'un claim brut. |
| **Confiance du contenu** | Le contenu Memory (préférences saisies par l'utilisateur, résumés dérivés de conversations) est traité comme **donnée non fiable** au même titre que `retrievalContext` : le prompt système interdit d'exécuter une instruction qui y figurerait. |
| **Comptage tokens** | Les tokens injectés depuis Memory dans le prompt final **comptent** dans `agent.tokens_used` et dans le budget `maxTokens` (§5.2). |
| **Indisponibilité** | Si Memory est indisponible en lecture, l'invocation continue sans contexte mémorisé et `AgentResult.degraded = true` (voir §8.1). Une écriture échouée est journalisée et retentée hors chemin critique, sans casser la réponse. |

---

## 3. Contrats

### 3.1 Interface `AgentAdapter`

```python
from typing import Iterator, Protocol
from agents.models import AgentRequest, AgentResult, AgentStreamEvent

class AgentAdapter(Protocol):
    """
    Contrat d'abstraction du framework agentique (V2-ADR-005 — P-04).
    Le code domaine ne dépend que de cette interface, jamais de strands.* directement.
    """

    def invoke(self, request: AgentRequest) -> AgentResult:
        """Exécute une conversation agentique et retourne le résultat borné."""
        ...

    def invoke_stream(self, request: AgentRequest) -> Iterator[AgentStreamEvent]:
        """
        Variante streaming (V2-ADR-011). Retourne un itérateur d'événements de domaine,
        PAS de chaînes brutes : c'est FastAPI qui les sérialise en SSE (§7.2).

        Le domaine ne connaît ni SSE ni son cadrage `event:`/`data:` — cette frontière
        est ce qui permet à V2-LLD-001 de changer de transport sans toucher au domaine.
        Le keep-alive `: ping` est émis par FastAPI, pas par l'adapter : il relève du
        transport et doit continuer même quand l'adapter est silencieux.

        L'itérateur se termine TOUJOURS par un événement terminal unique
        (Done | Cancelled | Error). Un itérateur épuisé sans terminal est un défaut
        de contrat, vérifié par test (§11.1).
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
    max_tool_calls: int         # nombre total d'appels tool par invocation
    max_tokens: int             # tokens cumulés entrée + sortie
    deadline_epoch_ms: int      # borne temporelle absolue (déjà existante en V1)

@dataclass(frozen=True)
class AgentConfig:
    invocation_id: str          # identifiant d'invocation Bedrock OPAQUE (V2-ADR-012).
                                # Modèle de fondation, profil géographique, profil applicatif
                                # ou débit provisionné : le domaine NE TESTE JAMAIS son préfixe
                                # et ne dérive aucune logique de sa forme.
                                # ex. ARN "arn:aws:bedrock:<région>:<compte>:inference-profile/<id>"
    fallback_invocation_id: Optional[str]   # repli à quota distinct (V2-ADR-012, §5.4).
                                # None = repli non configuré : la séquence §5.4 saute l'étape 2.
    prompt_version: str         # ex. "v1" (chargé depuis PromptRegistry)
    tool_allowlist: list[str]   # noms des tools MCP exposables pour ce parcours,
                                # résolus côté FastAPI à partir des rôles (V2-LLD-005 §4.7) :
                                # Runtime reçoit le résultat de la décision, pas les rôles

@dataclass(frozen=True)
class TrustedIdentity:
    actor_id: str               # claim sub du jeton d'accès vérifié, tel quel
                                # (V2-LLD-005 §3.1) — le hachage produit subjectId,
                                # destiné aux journaux, et ne franchit pas ce contrat
    tenant_id: str              # résolu côté serveur par le registre (V2-LLD-005 §3.4)
    # Deux champs, et deux seulement — conforme à runtime-contract.md §2.
    # roles/scopes ne franchissent PAS cette frontière (V2-LLD-005 §3.6) : la CAM
    # Domaine 1 attribue Business Authorization à FastAPI et l'interdit à Runtime ;
    # un composant qui reçoit des rôles finit par les évaluer. La décision est prise
    # avant l'invocation, et ce qui traverse est son résultat — la tool_allowlist
    # résolue de AgentConfig (§3.2, §6.2) — jamais ses intrants.

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

class CancellationCause(Enum):
    """V2-ADR-011 — une annulation N'EST PAS une erreur : elle a son propre
    événement terminal et sa propre cause. Les confondre rendrait indistinguables
    un geste utilisateur légitime et une panne dans les métriques."""
    CLIENT = "client"           # POST /operations/{id}/cancel, ou déconnexion détectée
    DEADLINE = "deadline"       # deadlineEpochMs atteint
    OPERATOR = "operator"       # annulation administrative

@dataclass
class AgentResult:
    answer: str
    turn_count: int
    input_tokens: int           # facturation Bedrock distincte entrée/sortie (voir §10.2)
    output_tokens: int
    tool_calls_count: int
    budget_exhausted: bool      # True si un budget a été atteint
    degraded: bool              # True si retrieval/Memory dégradé, tool en erreur,
                                # OU réponse produite par le repli (V2-ADR-012)
    served_invocation_id: str   # identifiant EFFECTIVEMENT servi (V2-ADR-012) :
                                # == config.invocation_id en nominal,
                                # == config.fallback_invocation_id après repli.
                                # Déclaré, jamais deviné — un repli non déclaré est
                                # une dégradation silencieuse de qualité (§8.2).
    error: Optional[AgentError] = None          # typé, plus un str libre
    cancelled: Optional[CancellationCause] = None   # renseigné => fin par annulation

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens
```

**Trois fins mutuellement exclusives.** Un `AgentResult` se termine par succès (`error` et
`cancelled` à `None`), par annulation (`cancelled` renseigné) ou par erreur (`error` renseigné) —
jamais par deux à la fois. Cette exclusivité est vérifiée par un test de contrat (§11.1) et se
projette exactement sur les trois événements terminaux SSE `done` / `cancelled` / `error` de
`V2-ADR-011`.

Les compteurs de tokens sont renseignés **dans les trois cas**. Une annulation réduit le coût
engagé, elle ne l'annule pas (`V2-ADR-011`) : des compteurs remis à zéro sur annulation rendraient
invisible une consommation réellement facturée.

### 3.2.1 Événements de streaming du domaine (`V2-ADR-011`)

L'adapter produit des événements de domaine ; leur cadrage SSE appartient à `V2-LLD-001` et leur
rendu à `V2-LLD-010`. Ce LLD fixe la charge utile côté domaine, pour que les trois documents ne
divergent pas.

```python
@dataclass(frozen=True)
class StreamMeta:
    streaming: str              # "native" | "emulated" — mode EFFECTIF, jamais souhaité (§7.3)
    operation_id: str

@dataclass(frozen=True)
class StreamDelta:
    text: str                   # fragment de réponse

@dataclass(frozen=True)
class StreamCitation:
    citations: tuple[dict, ...] # issues du retrievalContext, jamais générées par le modèle

@dataclass(frozen=True)
class StreamDone:
    result: AgentResult         # porte served_invocation_id et degraded (V2-ADR-012)

@dataclass(frozen=True)
class StreamCancelled:
    cause: CancellationCause
    result: AgentResult         # compteurs RÉELLEMENT consommés (V2-ADR-011)

@dataclass(frozen=True)
class StreamError:
    error: AgentError           # AgentErrorCode, jamais une trace brute

AgentStreamEvent = (
    StreamMeta | StreamDelta | StreamCitation
    | StreamDone | StreamCancelled | StreamError
)
```

| Événement domaine | Événement SSE (`V2-ADR-011`) | Position |
|---|---|---|
| `StreamMeta` | `meta` | **premier**, toujours — déclare le mode effectif |
| `StreamDelta` | `delta` | 0..n |
| `StreamCitation` | `citation` | 0..n |
| `StreamDone` | `done` | terminal |
| `StreamCancelled` | `cancelled` | terminal |
| `StreamError` | `error` | terminal |
| — | `: ping` | émis par **FastAPI**, hors flux domaine (§7.2) |

`StreamMeta` est émis **avant** le premier appel modèle : le client doit connaître le mode servi
avant d'adapter son UX, pas après avoir attendu. Le mode annoncé est le mode observé, ce qui en
fait une assertion testable (`V2-ADR-011`, preuves attendues).

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
| `deadlineEpochMs` | invocation | 120 s nominal, plafond dur 600 s (§5.2.2) | `DeadlineExceededError` → retour immédiat |

Les valeurs par défaut sont des paramètres Terraform/SSM — jamais des constantes dans le code.
Le dépassement de n'importe quel budget produit un `AgentResult` avec `budget_exhausted=True`,
jamais une exception non gérée.

#### 5.2.2 Réconciliation avec les plafonds de la chaîne (`V2-ADR-011`)

Un budget nominalement valide mais supérieur à un plafond d'infrastructure n'est pas un budget : il
est **tué par la chaîne avant d'être atteint**, et le symptôme observé est une déconnexion, pas un
dépassement de budget. Les deux doivent donc être réconciliés explicitement.

| Plafond de la chaîne | Valeur | Nature | Conséquence sur ce LLD |
|---|---|---|---|
| Durée totale d'un flux (API Gateway `STREAM`) | 15 min | dur, non ajustable | borne supérieure absolue de `deadlineEpochMs` |
| Idle timeout API Gateway | 5 min | dur | silence maximal toléré → keep-alive obligatoire |
| Idle timeout ALB | défaut 60 s, configurable | configurable (`V2-LLD-001`) | contrainte la plus serrée → dimensionne le keep-alive |

**`deadlineEpochMs` est borné et vérifié au démarrage.** Valeur nominale **120 secondes**, plafond
dur configurable **600 secondes** — sous les 15 minutes de la chaîne, avec la marge que consomment
CloudFront, API Gateway et l'ALB. Une valeur configurée au-delà du plafond de la chaîne est **un
refus de démarrage**, pas une découverte en production : le mode de panne qu'elle produit (flux
coupé à 15 minutes sans état terminal) est précisément celui qu'aucun code d'erreur ne signale.

Ce contrôle est le pendant, côté conversation, de la vérification de taille de chunk au démarrage de
`V2-LLD-002 §5.2` : dans les deux cas, une configuration incompatible est refusée au démarrage
plutôt que subie à l'exécution.

#### 5.2.1 Calibrage de `maxTokens`

`maxTokens` compte le **cumul entrée + sortie de tous les tours de l'invocation** — pas un tour
isolé. Il inclut : prompt système, message utilisateur, contexte Memory injecté (§2.5),
`retrievalContext.chunks`, l'historique inter-tours, les résultats de tools réinjectés, et toute
la sortie modèle produite.

Une constante fixe (l'ancien « 8 000 ») est **inadaptée** : un `retrievalContext` de 5 chunks à
~500 tokens consomme déjà ~2 500 tokens de seul contexte, ce qui saturerait une conversation RAG
dès le deuxième tour. `maxTokens` est donc **dérivé de la fenêtre de contexte de l'identifiant
d'invocation configuré** (`AgentConfig.invocation_id`), pas d'un nombre en dur :

```
maxTokens_défaut = floor(fenêtre_contexte_invocation × 0,75)
```

La marge de 25 % réserve de la place à la sortie finale et évite de heurter la limite dure du
modèle. La valeur effective est calculée au démarrage et peut être plafonnée plus bas par SSM pour
maîtriser le coût.

**La table est indexée sur l'identifiant d'invocation, pas sur un nom de modèle (`V2-ADR-012`).**
Un même modèle est joignable par plusieurs identifiants (modèle de fondation, profil géographique,
profil applicatif, débit provisionné) et le domaine ne sait pas — et ne doit pas savoir — lequel
désigne quoi : l'identifiant est opaque. Indexer sur un nom de modèle supposerait de parser
l'identifiant, ce que `V2-ADR-012` interdit explicitement.

| Clé | Valeur | Portée |
|---|---|---|
| `invocation_id` primaire | fenêtre de contexte, tarif entrée, tarif sortie | dérive `maxTokens` (§5.2.1) et `cost_estimate_usd` (§10.2) |
| `fallback_invocation_id` | idem | **obligatoire si le repli est configuré** — sinon la vérification §5.4.3 ne peut pas s'exécuter |

Une entrée manquante pour un identifiant configuré est un **refus de démarrage**. Sans elle,
`maxTokens` retomberait sur une valeur par défaut arbitraire — exactement la constante en dur que
cette section supprime.

La cohérence avec la taille maximale de `retrievalContext.chunks` (`V2-LLD-002` §6.2) est un point
ouvert (§13.2).

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

### 5.4 Identifiant d'invocation et repli modèle (`V2-ADR-012`)

#### 5.4.1 Le domaine transporte un identifiant, pas un modèle

`AgentConfig.invocation_id` est un paramètre opaque, jamais une constante (`V2-ADR-005`). Ce que le
domaine transporte n'est **pas un modèle** mais un identifiant d'invocation Bedrock, dont la forme
est un détail d'infrastructure.

Cette opacité n'est pas une élégance : elle est imposée par un fait régional. En `eu-west-3`, un
appel de `Converse` avec l'identifiant de modèle de fondation nu d'un modèle récent échoue —

```text
ValidationException: Invocation of model ID anthropic.<modèle>:0 with on-demand
throughput isn't supported. Retry your request with the ID or ARN of an inference
profile that contains this model.
```

— parce que la capacité de ces modèles est mutualisée entre régions et n'est joignable que par un
**profil d'inférence**. Les versions antérieures de ce LLD donnaient un identifiant de modèle de
fondation nu en exemple (`§3.2`, `§12.1`) : appliqués littéralement, ces exemples échouaient **au
premier appel**.

Le domaine **ne teste jamais le préfixe** de l'identifiant et n'en dérive aucune logique. Passer du
profil géographique au débit provisionné est alors un changement de valeur SSM, sans modification du
domaine ni du contrat.

**Résidence des données.** L'identifiant nominal est un profil applicatif ciblant le **profil
géographique EU** : l'invocation peut traverser plusieurs régions de l'Union, ce qui est assumé. Le
profil global (`global.*`), moins cher d'environ 10 %, est **autorisé en `dev` et `test`**, et
**interdit en `staging` et `production`** — exposition CLOUD Act directe et risque de perte de base
légale en cas d'invalidation du cadre de transfert. `V2-ADR-012` exige que cette distinction soit un
**contrôle sur la valeur SSM par environnement, pas une convention** : le contrôle est vérifié au
démarrage et couvert par un test (§11.4).

#### 5.4.2 Séquence de repli — bornée et déterministe

```text
1. ThrottlingException sur l'identifiant primaire
     -> jusqu'à 2 tentatives exponentielles avec jitter (≈ 500 ms puis 1 s),
        chacune CONDITIONNÉE par deadlineEpochMs

2. Tentatives épuisées ET AUCUN TOKEN DE SORTIE ENCORE ÉMIS
     -> une tentative UNIQUE sur fallback_invocation_id,
        si configuré et déclaré compatible au démarrage (§5.4.3)
     -> si elle aboutit : degraded = true, served_invocation_id = repli

3. Repli échoué, OU repli non configuré, OU AU MOINS UN TOKEN DÉJÀ ÉMIS
     -> AgentResult.error = AgentError(MODEL_THROTTLED, …), degraded = true

4. Tout autre code d'erreur Bedrock : AUCUN repli.
   Une erreur de validation ou d'autorisation est un défaut de configuration ;
   la masquer par un repli la rend indétectable.
```

**La règle du premier token.** Le repli est interdit dès qu'un token de sortie a été émis vers le
client. Deux modèles produisant chacun un fragment de la même réponse produisent une réponse
incohérente — qu'aucun test ne rattrape et qu'aucun utilisateur ne peut interpréter. C'est une
conséquence directe du streaming décidé par `V2-ADR-011` : le repli est invisible quand il réussit,
et strictement borné quand il est trop tard.

La limite est assumée : **le repli est inefficace sur les réponses longues**, précisément celles
dont l'échec est le plus visible. `V2-ADR-012` tranche en faveur de la cohérence plutôt que de la
disponibilité.

#### 5.4.3 Compatibilité de capacité — vérifiée au démarrage

Un identifiant de repli n'est admissible que s'il satisfait trois conditions, **vérifiées au
démarrage et non à l'exécution** :

| Condition | Défaut si non vérifiée |
|---|---|
| `Converse` **et** `ConverseStream` supportés | `V2-ADR-011` ne tient plus — le flux ne peut pas être servi |
| Appel de tools supporté | §6 ne tient plus — l'agent perd ses tools au moment du repli |
| Fenêtre de contexte **≥** celle du primaire | `maxTokens` (§5.2.1) devient invalide |

Le troisième point est le plus facile à manquer. `maxTokens` est dérivé au démarrage de la fenêtre
du primaire : un repli à fenêtre plus petite rendrait ce budget invalide, et l'invocation de repli
serait rejetée par Bedrock pour dépassement de contexte **au moment précis où le système tente de
préserver la conversation**. Deux réponses étaient possibles — refuser au démarrage, ou redériver
`maxTokens` par identifiant. La seconde déplace le budget d'une constante de démarrage vers un état
d'exécution et complique la traçabilité ; `V2-ADR-012` retient la première.

Un repli incompatible est donc un **refus de démarrage avec message actionnable**, pas un échec à la
première invocation de repli.

#### 5.4.4 Un repli non exercé n'est pas un repli

Le cycle de vie Bedrock prévoit qu'un client existant peut **perdre l'accès à un modèle en état
`Legacy` après quinze jours sans invocation**. Un modèle de repli n'est, par définition, presque
jamais appelé : il est le candidat naturel à cette perte d'accès, et elle se manifesterait
exactement lorsqu'il devient nécessaire.

Deux contrôles permanents en découlent :

- **invocation de contrôle périodique** du repli, à intervalle strictement inférieur à ce seuil,
  **hors chemin de requête**, dont l'échec est une alerte et non un incident silencieux ;
- **sonde de cycle de vie** interrogeant l'état du modèle configuré : le passage en `Legacy` du
  primaire **ou** du repli produit une alerte. Un préavis de six mois n'est utile que s'il est reçu.

Ces deux contrôles sont une charge d'exploitation permanente, faible mais non nulle. Ils sont le
pendant, côté génération, de la sonde de cycle de vie du modèle d'embedding de `V2-LLD-002 §5.5`.

#### 5.4.5 Le repli est déclaré, jamais deviné

Le modèle effectivement servi est porté par `AgentResult.served_invocation_id`, et `degraded` vaut
`true` lorsque la réponse provient du repli. L'événement terminal `done` le transporte au client
(§3.2.1). Un repli non déclaré serait une dégradation silencieuse de qualité, ce que §8.2 interdit.

**Le déclenchement est réactif en V2** : il part de la `ThrottlingException` reçue. Un déclenchement
préventif — sur métrique de consommation de quota, avant rejet — suppose une base de mesure que le
système n'a pas encore ; c'est la trajectoire, pas la V2.

**Un profil applicatif n'ouvre pas de quota.** C'est une enveloppe de facturation, pas une
réservation de capacité : multiplier les profils applicatifs n'augmente pas le débit et ne constitue
**jamais** une réponse au throttling. Seul un identifiant portant sur un **modèle distinct** ouvre un
quota distinct — c'est la raison d'être du repli.

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
    Elle est résolue côté FastAPI à partir des rôles (V2-LLD-005 §4.7) : ce filtre
    consomme le résultat d'une décision d'autorisation, il n'en prend aucune.
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

## 7. Streaming (`V2-ADR-011`)

### 7.1 Le maillon faible n'était pas Runtime

Les versions antérieures de ce LLD conditionnaient le mode émulé à l'hypothèse « si Runtime ne
stream pas nativement ». **Cette hypothèse est levée** : `InvokeAgentRuntime` diffuse nativement en
`text/event-stream`, et `ConverseStream` en amont également. Le maillon faible était ailleurs.

Écrire une `StreamingResponse` FastAPI ne suffit pas à obtenir un flux progressif côté navigateur :
chaque intermédiaire du chemin peut **tamponner** la réponse, c'est-à-dire l'accumuler entièrement
avant de la relayer. Le résultat est indiscernable d'une réponse non diffusée — le client attend,
puis reçoit tout d'un coup. Le code applicatif est correct, le protocole SSE est correct, et il n'y
a pourtant pas de streaming.

| Composant du chemin | Diffuse progressivement ? | Condition |
|---|---|---|
| CloudFront | oui | cache désactivé sur `/api/*` |
| **API Gateway HTTP API** | **non — tampon systématique** | aucune option ne l'active |
| **API Gateway REST API** | **oui** | `responseTransferMode = STREAM` |
| ALB interne | oui | idle timeout > intervalle de keep-alive |
| FastAPI (uvicorn) | oui | `StreamingResponse` |
| AgentCore Runtime | oui | `InvokeAgentRuntime` → `text/event-stream` |
| Bedrock | oui | `ConverseStream` |

Le transport retenu par `V2-ADR-011` est donc **REST API en mode `STREAM`, endpoint Regional, via
VPC Link V2 vers l'ALB interne**. Le choix du type d'API Gateway et son provisionnement appartiennent
à `V2-LLD-001` ; ce LLD en dépend sans le décider.

### 7.2 Frontière domaine / transport

Le domaine produit des `AgentStreamEvent` (§3.2.1) ; FastAPI les sérialise en SSE. Cette séparation
est ce qui permet à `V2-LLD-001` de changer de transport sans toucher au code agent.

```text
Runtime : orchestrator.invoke_stream() -> Iterator[AgentStreamEvent]
   │  StreamMeta (toujours en premier)
   │  StreamDelta / StreamCitation ...
   │  StreamDone | StreamCancelled | StreamError  (terminal unique)
   ▼
FastAPI : sérialisation SSE + KEEP-ALIVE ": ping" toutes les 15 s
   │      (le ping est émis par FastAPI, PAS par l'adapter : il doit
   │       continuer précisément quand l'adapter est silencieux)
   ▼
ALB (idle timeout aligné) -> API Gateway REST STREAM -> CloudFront -> EventSource
```

**Le keep-alive est un contrôle, pas un réglage.** Un tour agentique qui appelle un tool lent peut
rester silencieux plusieurs dizaines de secondes. Sans `: ping`, un appel de tool de 70 secondes
fait tomber le flux sur l'idle timeout ALB par défaut (60 s), et le symptôme observé est une
déconnexion inexpliquée — jamais une erreur interprétable. L'intervalle retenu est **15 secondes** :
marge confortable sous les 60 s de l'ALB, très en deçà des 5 minutes d'API Gateway. `V2-ADR-011`
exige qu'il soit **couvert par un test, pas seulement par une valeur de configuration** (§11.3).

### 7.3 Le mode `emulated` est un repli d'infrastructure, déclaré

Le mode `emulated` **reste au contrat**, mais il change de statut : il n'est plus l'hypothèse d'un
Runtime non diffusant, il est le repli si la précondition d'infrastructure de `V2-ADR-011` (§1.3)
n'est pas levée — REST API `STREAM` ou VPC Link V2 indisponibles en `eu-west-3`.

- `StreamMeta.streaming` porte le mode **effectif**, jamais le mode souhaité, et est émis en premier ;
- le frontend adapte l'UX en conséquence (`V2-LLD-010`) : « génération en cours » en `native`,
  « préparation de la réponse » en `emulated`. **Pas de fausse animation token-par-token sur une
  réponse déjà complète** ;
- la métrique `time-to-first-token` (§10.2) distingue les deux modes : en `emulated` elle mesure la
  latence réelle de la réponse complète, jamais un premier token fictif.

> **Note de revue (M3), toujours valable :** feindre un stream token-par-token sur une réponse déjà
> complète est une anti-UX — attente longue, puis fausse animation, `time-to-first-token` mensongère.
> Un défaut d'infrastructure ne doit pas être caché derrière une animation. `V2-ADR-011` renforce ce
> point : la progressivité est **mesurée, pas déclarée**, et une réponse arrivant en un bloc alors
> que `meta` annonce `native` invalide la configuration (§11.3).

### 7.4 Reprise après déconnexion

SSE reconnecte automatiquement. En V2, une reconnexion **ne rejoue pas** les fragments déjà émis :
elle se rattache à l'opération par `operationId` et reçoit l'état courant ou le résultat final
persisté. Le rejeu token par token est hors périmètre V2 (`V2-ADR-011`).

Conséquence côté domaine : une reconnexion ne doit produire **ni double invocation ni double
facturation**. Le rattachement se fait sur l'opération existante, jamais sur une nouvelle.

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
| Bedrock throttling, **avant** le premier token, repli configuré et compatible | Repli tenté une fois (§5.4.2 étape 2) ; si succès, réponse complète et cohérente | `true` | Transparent — `done` déclare `served_invocation_id` |
| Bedrock throttling, **après** le premier token | **Aucun repli** (règle du premier token) → `error(MODEL_THROTTLED)` | `true` | « Service temporairement indisponible » |
| Bedrock throttling, repli absent ou échoué | `error(MODEL_THROTTLED)` après 2 tentatives bornées par la deadline | `true` | « Service temporairement indisponible » |
| Autre erreur Bedrock (validation, autorisation) | **Aucun repli** — défaut de configuration, jamais masqué (§5.4.2 étape 4) | `true` | Erreur applicative standard |
| Annulation client ou opérateur (§8.3) | Arrêt au prochain point d'annulation, `cancelled` renseigné | `false` — **une annulation n'est pas une dégradation** | Événement `cancelled` avec compteurs consommés |
| AgentCore Runtime indisponible | FastAPI retourne HTTP 503 | — | Erreur applicative standard |

### 8.2 Règle fondamentale

**La boucle agentique ne doit jamais boucler de façon incontrôlée.** Toute sortie hors des budgets
produit un `AgentResult` structuré. Aucune exception non gérée ne doit atteindre FastAPI.

### 8.3 Annulation (`V2-ADR-011`)

#### 8.3.1 Pourquoi la détection de déconnexion ne suffit pas

SSE est unidirectionnel : `EventSource` ne peut rien envoyer au serveur. La proposition antérieure de
ce LLD — « le client ferme la connexion, FastAPI détecte la déconnexion » — a deux défauts qui la
disqualifient comme mécanisme nominal :

- la propagation de la fermeture à travers CloudFront puis API Gateway **n'est ni garantie ni
  immédiate**. Tant que la déconnexion n'est pas vue, la boucle agentique continue et **la
  facturation Bedrock continue** — ce qui viole l'exigence d'arrêt de la consommation ;
- elle ne laisse **aucune trace d'audit** : rien ne distingue une annulation délibérée d'un incident
  réseau.

S'ajoute un fait de topologie : derrière un ALB à plusieurs cibles, la requête d'annulation atterrit
en général sur une **autre tâche ECS** que celle qui diffuse. Un mécanisme purement local à un
processus ne peut pas fonctionner.

#### 8.3.2 Mécanisme retenu — coopératif, sur registre partagé

```text
POST /api/v1/operations/{operationId}/cancel   (FastAPI, autorisé par V2-ADR-006)
   -> inscription d'une marque d'annulation dans un REGISTRE PARTAGÉ
   -> 202 (l'annulation est coopérative, donc non instantanée)

Boucle agentique (code /agents) :
   consulte la marque AUX POINTS D'ANNULATION uniquement (§8.3.3)

Détection de déconnexion : signal COMPLÉMENTAIRE de meilleur effort.
   Elle alimente le même drapeau ; elle économise du calcul quand elle
   fonctionne, elle n'est JAMAIS la seule garantie.
```

Le **choix technique du registre** (table dédiée ou réutilisée, TTL, cohérence de lecture) est
**délégué à `V2-LLD-006`**, qui possède les modèles de données. Ce LLD n'en consomme que les
propriétés : partagé entre tâches, borné dans le temps, autorisable par tenant.

Côté domaine, le registre est vu par un port, selon le même idiome que `AgentAdapter` :

```python
class CancellationPort(Protocol):
    """Lecture de l'état d'annulation d'une opération (V2-ADR-011).
    Le stockage est possédé par V2-LLD-006 ; le domaine n'en connaît que ce contrat."""

    def is_cancelled(self, operation_id: str) -> Optional[CancellationCause]:
        """None si l'opération n'est pas annulée. Appelé UNIQUEMENT aux points
        d'annulation (§8.3.3) — jamais dans une boucle serrée."""
        ...
```

**Seul le propriétaire de l'opération peut l'annuler** (`V2-ADR-006`). Une tentative d'annulation
d'une opération appartenant à un autre tenant est refusée — preuve négative attendue (§11.4).

#### 8.3.3 Points d'annulation — et le seul endroit interdit

La marque est évaluée :

| Point | Évalué ? |
|---|---|
| Avant l'invocation du modèle pour un nouveau tour | **oui** |
| Avant l'émission d'un appel de tool | **oui** |
| **Pendant** l'exécution d'un tool porteur d'effet de bord | **jamais** |

Interrompre un tool en vol laisserait un effet **partiellement appliqué**. L'annulation attend donc
la fin de l'appel en cours, puis s'arrête : l'effet est soit complet, soit absent, jamais partiel.
La garantie d'idempotence des tools eux-mêmes relève de `V2-ADR-014` et de `V2-LLD-004`.

C'est ce qui rend l'annulation **coopérative et non instantanée** — une propriété assumée, pas une
limite subie.

#### 8.3.4 Effets d'une annulation

| Effet | Détail |
|---|---|
| Arrêt de la consommation | le flux `Converse` n'est plus consommé — c'est l'exigence centrale |
| **Aucune écriture Memory** | le contrat §2.5 n'écrit qu'après le dernier tour **réussi** ; une invocation annulée n'est pas réussie |
| Événement terminal `cancelled` | porte `CancellationCause` et les compteurs **réellement consommés** |
| État terminal dans le registre | une reprise ne ressuscite jamais l'opération (§7.4) |
| Comptabilisation des tokens | les tokens déjà consommés entrent dans les métriques de coût (§10.2) |

**Une annulation réduit le coût, elle ne l'annule pas.** Des compteurs remis à zéro rendraient
invisible une consommation réellement facturée — c'est pourquoi `AgentResult` porte ses compteurs
dans les trois fins possibles (§3.2).

`degraded` reste `false` sur annulation : un geste utilisateur délibéré n'est pas une dégradation du
service, et les confondre pollue le taux de dégradation surveillé en §10.2.

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
| Invocation modèle en streaming | `bedrock:InvokeModelWithResponseStream` | **requis** — `V2-ADR-011` retient le streaming ; `ConverseStream` s'y ramène |
| Lecture/écriture AgentCore Memory | `bedrock-agentcore:*` (Memory) — **à confirmer** | remplace l'ancien `bedrock-agent-runtime:InvokeAgent` (faux) |
| Appel des tools via AgentCore Gateway MCP | `bedrock-agentcore:*` (Gateway) — **à confirmer** | remplace l'ancien `execute-api:Invoke` (faux) |
| Logs applicatifs | `logs:CreateLogStream`, `logs:PutLogEvents` | — |
| Traces | `xray:PutTraceSegments`, `xray:PutTelemetryRecords` | déjà provisionnées en V1 (ADR-008) |

Les permissions `s3vectors:*`, `bedrock-agent:*IngestionJob` et `dynamodb:*` appartiennent à la
tâche ECS **FastAPI** (`V2-LLD-001`), pas à l'exécution agent.

#### 9.1.1 Un profil d'inférence exige une politique strictement plus large (`V2-ADR-012`)

La formulation antérieure — « restreindre chaque action par `Resource` (ARN du modèle) » — est
**insuffisante** dès lors que l'identifiant nominal est un profil d'inférence. Un profil
géographique exécute l'invocation dans plusieurs régions, et chacune doit être autorisée.

| Ressource à autoriser | Forme | Raison |
|---|---|---|
| Profil d'inférence | `arn:aws:bedrock:<région>:<compte>:inference-profile/<id>` | porte le compte et la région |
| Modèle, région source | `arn:aws:bedrock:<région>::foundation-model/<modèle>` | appel local |
| Modèle, **chaque** région de destination | `arn:aws:bedrock:<dest>::foundation-model/<modèle>` | exécution déportée |

Trois conséquences, dont deux sont des charges permanentes :

- **toutes les régions de destination doivent être énumérées.** Une région absente de la politique
  produit un échec **intermittent, dépendant du routage** — le mode de panne le plus coûteux à
  diagnostiquer, parce qu'il est reproductible une fois sur dix ;
- **la liste des destinations appartient à AWS, pas au système.** Son élargissement ultérieur peut
  invalider une politique correcte au moment de sa rédaction : la politique exige une **surveillance
  de dérive**, pas seulement une rédaction correcte ;
- **le repli ajoute ses propres ressources** — profil et modèle de repli dans toutes ses régions de
  destination. Un repli sans permission est un repli inexistant, et c'est son invocation de contrôle
  périodique (§5.4.4) qui le révèle avant l'incident.

Le détail de provisionnement reste porté par `V2-LLD-001` ; ce LLD fixe l'étendue fonctionnelle
requise.

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
| `agent.invocation_id` | `AgentConfig.invocation_id` (opaque, non parsé) | `"arn:aws:bedrock:…:inference-profile/…"` |
| `agent.served_invocation_id` | `AgentResult.served_invocation_id` — diffère du précédent **si et seulement si** le repli a servi | `"arn:…/fallback"` |
| `agent.fallback_used` | booléen dérivé (`served != configured`) | `false` |
| `agent.cancelled_cause` | `AgentResult.cancelled` — absent si fin normale | `"client"` |
| `agent.streaming_mode` | `StreamMeta.streaming` — mode **effectif** | `"native"` |
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
| `bedrock.throttled.rate` | % appels Converse | > 1 % (déclenche la séquence §5.4.2) |
| `agent.time_to_first_token` | ms (P95) | ventilée par `agent.streaming_mode` (§7.3) — jamais agrégée entre `native` et `emulated` |
| `agent.fallback_used.rate` | % invocations | > 1 % — un repli fréquent signale un throttling **structurel**, condition de bascule vers le débit provisionné (`V2-ADR-012`) |
| `agent.fallback_probe.failure` | événements | **> 0 = alerte** — l'invocation de contrôle du repli a échoué (§5.4.4) : le repli est présumé indisponible |
| `agent.model_lifecycle.legacy` | événements | **> 0 = alerte** — primaire **ou** repli passé en `Legacy` (§5.4.4) |
| `agent.cancelled.rate` | % invocations | pas d'alerte — mesure d'usage, ventilée par `CancellationCause` |

Les tarifs input/output proviennent de la même table indexée sur l'**identifiant d'invocation** que
le calibrage de `maxTokens` (§5.2.1). Le HLD §13 exige explicitement la métrique de coût estimé ;
fusionner input et output la rendrait inexploitable (Bedrock facture la sortie ~5× l'entrée).

**Le coût par tenant est dérivé, pas facturé (`V2-ADR-012`).** L'attribution native passe par les
étiquettes du **profil applicatif**, dont la granularité retenue est **un profil par environnement et
par rôle d'usage** — jamais un profil par tenant, qui créerait une ressource à provisionner,
étiqueter et détruire au rythme des tenants. Le coût par tenant est donc calculé à partir des
compteurs `input_tokens`/`output_tokens` exposés en §3.2, avec deux limites à assumer plutôt qu'à
découvrir :

- c'est une **estimation**, réconciliable avec la facture au niveau de l'environnement mais **pas au
  niveau du tenant** ;
- le champ `requestMetadata` de `Converse` n'y contribue pas : ce n'est pas une étiquette de
  répartition de coûts et il n'apparaît ni dans Cost Explorer ni dans les rapports d'usage. Il reste
  utile pour la corrélation, jamais pour la facturation.

Ces deux limites sont une **entrée pour `V2-LLD-007`**, qui doit les énoncer explicitement.

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
| Test de contrat | `AgentResult` : `error` et `cancelled` jamais renseignés ensemble (§3.2) | Oui |
| Test de contrat | `invoke_stream` se termine toujours par un événement terminal unique, et `StreamMeta` est toujours premier (§3.2.1) | Oui |
| Lint | Aucune comparaison ni parsing du préfixe de `invocation_id` dans le domaine (`V2-ADR-012`) | Oui |

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
- changement de `AGENT_INVOCATION_ID` → aucun fichier domaine modifié (test P-04)
- annulation marquée avant un tour → arrêt au point d'annulation, `cancelled = CLIENT`, compteurs
  non nuls, **aucune écriture Memory** (§8.3.4)
- annulation marquée pendant un tool à effet de bord → l'appel en cours **va à son terme**, l'arrêt
  survient après (§8.3.3)

#### 11.2.1 Contrôles au démarrage (`V2-ADR-011`, `V2-ADR-012`)

Ces cas vérifient des **refus de démarrage**, pas des comportements d'exécution. Ils sont
unitaires parce que leur objet est une configuration, pas un appel réseau.

| Cas | Attendu |
|---|---|
| `deadlineEpochMs` configuré au-delà du plafond de la chaîne (§5.2.2) | refus de démarrage, message actionnable |
| Repli à fenêtre de contexte **inférieure** au primaire | refus de démarrage — **pas** un échec à la première invocation de repli |
| Repli ne supportant pas `ConverseStream` ou les tools | refus de démarrage (§5.4.3) |
| Entrée absente de la table pour un identifiant configuré | refus de démarrage (§5.2.1) |
| Profil global (`global.*`) configuré en `staging` ou `production` | **refusé par le contrôle**, et non seulement absent de la configuration (§5.4.1) |

### 11.3 Tests d'intégration

- Appel complet FastAPI → Runtime (stub ou sandbox) avec contrat complet
- Vérification que la `trustedIdentity` est bien transmise et non overridable
- Test cross-tenant : deux utilisateurs ne partagent jamais de contexte Memory ou retrieval

**Streaming et annulation (`V2-ADR-011`) — progressivité mesurée, jamais déclarée :**

| Preuve attendue | Nature |
|---|---|
| `time-to-first-token` observé côté navigateur **significativement inférieur** à la durée totale, sur le chemin complet CloudFront → API Gateway → ALB → FastAPI | une réponse arrivant en un bloc **invalide la configuration** |
| Conversation multi-tours dépassant 29 s puis 60 s, diffusée sans rupture | lève l'ancien plafond supposé |
| Appel de tool de **plus de 60 s de silence** : le flux survit | valide le keep-alive (§7.2) — non couvert par une simple valeur de config |
| Annulation dont la requête `cancel` atterrit sur une **autre tâche ECS** que celle qui diffuse | valide le registre partagé (§8.3.2) |
| Annulation pendant un tool à effet de bord : l'effet est **complet ou absent, jamais partiel** | valide §8.3.3 |
| Tokens consommés avant annulation présents dans les métriques de coût | valide §8.3.4 |
| Déconnexion brutale puis reconnexion : rattachement par `operationId`, **sans rejeu ni double facturation** | valide §7.4 |
| Le mode annoncé dans `meta` correspond au comportement réellement observé | rend §7.3 testable |

**Repli modèle (`V2-ADR-012`) :**

| Preuve attendue | Nature |
|---|---|
| Appel avec un identifiant de **modèle de fondation nu** depuis `eu-west-3` : la `ValidationException` attendue est observée | **preuve négative fondant l'ADR** — son absence l'invalide |
| Appel nominal par profil applicatif : succès en `Converse` **et** `ConverseStream` | valide §5.4.1 |
| Repli déclenché **avant** le premier token : réponse complète et cohérente, `done` déclare le repli avec `degraded = true` | valide §5.4.2 étape 2 |
| Throttling **après** le premier token : **aucun repli tenté**, fin par `error` | la règle du premier token n'est pas observable autrement |
| Politique IAM privée d'une région de destination : l'échec est observé et diagnosticable | documente ce mode de panne intermittent (§9.1.1) |
| Invocation de contrôle du repli : exécutée, tracée, échec → alerte | valide §5.4.4 |
| Sonde de cycle de vie : passage simulé en `Legacy` du primaire **ou** du repli → alerte | valide §5.4.4 |
| Réconciliation coût dérivé / facture d'environnement : écart mesuré et borné | valide la limite énoncée en §10.2 |

### 11.4 Tests de sécurité négative

- Injection de prompt dans un chunk RAG : vérifier que le tool demandé par le chunk est refusé
  par `ToolAllowlist`
- Tentative d'override d'identité dans le payload : champ rejeté par le validateur de contrat
- Tentative de `modelOverride` dans le payload : rejeté par le validateur
- **Annulation d'une opération appartenant à un autre tenant : refusée** (`V2-ADR-006`, §8.3.2)

### 11.5 Preuves attendues (gate V2-G2)

- aucun fichier hors `adapter/` n'importe `strands.*` (CI vert) ;
- un dépassement de budget produit un `AgentResult` structuré, sans exception non gérée ;
- les tests unitaires s'exécutent sans appel réseau (mock `AgentAdapter`) ;
- un changement de `AGENT_INVOCATION_ID` ne modifie aucun fichier domaine ;
- le mode de streaming annoncé correspond au mode observé, et la progressivité est **mesurée** ;
- une annulation arrête la consommation facturée et ne laisse aucun effet de tool partiel ;
- un repli, quand il survient, est **déclaré** dans `done` avec `degraded = true` ;
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
| `AGENT_MAX_TOKENS` | dérivé : `floor(ctx_invocation × 0,75)` — voir §5.2.1 | SSM Parameter Store (cap optionnel) |
| `AGENT_DEADLINE_MS` | `120000` (nominal), plafond dur `600000` — §5.2.2 | SSM Parameter Store |
| `AGENT_INVOCATION_ID` | ARN de **profil d'inférence applicatif** ciblant le profil géographique EU — jamais un modèle de fondation nu (§5.4.1) | SSM Parameter Store |
| `AGENT_FALLBACK_INVOCATION_ID` | identifiant de repli à **quota distinct**, vide si non configuré (§5.4.2) | SSM Parameter Store |
| `AGENT_TOOL_ALLOWLIST` | liste JSON | SSM Parameter Store |
| `AGENT_STREAM_KEEPALIVE_MS` | `15000` — §7.2 | SSM Parameter Store |
| `AGENT_FALLBACK_PROBE_INTERVAL` | strictement < 15 jours — §5.4.4 | SSM Parameter Store |

Toutes les valeurs sont injectées par Terraform via SSM — jamais hardcodées dans l'image.

> **`AGENT_MODEL_ID` est renommé `AGENT_INVOCATION_ID` (`V2-ADR-012`).** L'ancien nom, et surtout
> l'ancien exemple — un identifiant de modèle de fondation nu — produisaient une `ValidationException`
> **au premier appel** en `eu-west-3` (§5.4.1). Le renommage n'est pas cosmétique : il porte le fait
> que la valeur est un identifiant d'invocation opaque, dont la forme n'est jamais interprétée par le
> domaine.

> **Contrôle par environnement (`V2-ADR-012`).** La valeur de `AGENT_INVOCATION_ID` est vérifiée au
> démarrage : un profil global (`global.*`) est **refusé en `staging` et `production`**, autorisé en
> `dev` et `test`. C'est un contrôle, pas une convention (§5.4.1, §11.2.1). En `dev`/`test` sous
> profil global, les métriques de latence sont **non représentatives** de la production — le TTFT
> varie selon la région de destination effective.

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
| Task IAM Role Runtime | `V2-LLD-001` (Plateforme) | Permissions Bedrock, profil d'inférence et régions de destination (§9.1.1) |
| Transport SSE (type d'API Gateway, VPC Link V2, idle timeout ALB, route `cancel`) | `V2-LLD-001` | `V2-ADR-011` — le domaine produit les événements, le transport les sert (§7.2) |
| Registre d'annulation (table, TTL, cohérence de lecture) | `V2-LLD-006` | `V2-ADR-011` délègue le stockage ; ce LLD n'en consomme que le contrat (§8.3.2) |

### 13.2 Points ouverts (à résoudre avant `Approved`)

| Point | Origine | Impact |
|---|---|---|
| Préconditions d'infrastructure `V2-ADR-011` / `V2-ADR-012` (§1.3) | vérification datée | conditionnent l'activation, pas la décision |
| Liste nominative des régions de destination du profil EU | `V2-ADR-012` | la politique IAM §9.1.1 en dépend directement |
| Taille maximale des chunks dans `retrievalContext` | `V2-LLD-002` §6.2 | impacte le budget `maxTokens` (§5.2.1) |
| Support natif `traceparent` par AgentCore Runtime SDK | `V2-LLD-007` | détermine si corrélation directe ou via `operationId` |
| Exigence formelle de résidence des données | Charte ou `V2-ADR-006` | `V2-ADR-012` interdit le profil global en production **par précaution**, faute d'exigence formelle — point reporté, non tranché ici |

Les trois points ouverts des versions antérieures — protocole de streaming, fallback modèle, profils
d'inférence — sont **fermés** par `V2-ADR-011` et `V2-ADR-012` (§7, §5.4).

---

## 14. Critères de sortie (gate V2-G2)

**Le contrat de mise à jour post-ADR est honoré.** Les versions antérieures pouvaient viser
`Approved` avec les sections streaming et fallback ouvertes, sous réserve de les réviser dès
`V2-ADR-011` et `V2-ADR-012` décidés. Ces deux ADR sont `Accepted` et la révision v0.5 les intègre :
les six marqueurs `⚠ ADR MANQUANT` sont levés, et le contrat de mise à jour est **soldé**.

Ce qui subsiste n'est pas une décision manquante mais une **vérification datée** : les préconditions
d'infrastructure de §1.3, de même nature que celle de `V2-LLD-002 §1.6`. Elles conditionnent
l'activation, pas la conception.

Critères bloquants pour `Approved` :

- [ ] Tests d'architecture (lint imports, contrats, non-parsing de `invocation_id`) verts en CI
- [ ] Tests unitaires domaine sans dépendance réseau Bedrock
- [ ] Budgets d'invocation vérifiés : chaque dépassement produit un `AgentResult` structuré
- [ ] `maxTokens` dérivé de la fenêtre de contexte de l'**identifiant d'invocation**, pas d'une constante (§5.2.1)
- [ ] `deadlineEpochMs` borné sous les plafonds de la chaîne, vérifié au démarrage (§5.2.2)
- [ ] Contrôles de démarrage §11.2.1 implémentés : repli compatible, table complète, profil global refusé en `staging`/`production`
- [ ] Contrat d'usage Memory (§2.5) implémenté : lecture avant 1er tour, écriture après dernier tour, namespace dérivé de `trustedIdentity`
- [ ] Tool allowlist active : tout tool hors liste est refusé et tracé
- [ ] Permissions IAM (§9.1) validées nominativement contre la doc AWS AgentCore en vigueur
- [ ] Politique IAM §9.1.1 couvrant profil, région source et **chaque** région de destination, primaire **et** repli
- [ ] Progressivité du streaming **mesurée** (§11.3), et mode annoncé == mode observé
- [ ] Keep-alive couvert par un test de silence > 60 s, pas seulement par une valeur de configuration
- [ ] Annulation effective depuis une **autre tâche ECS**, sans effet de tool partiel (§8.3)
- [ ] Repli déclaré dans `done` avec `degraded = true` ; règle du premier token vérifiée par test
- [ ] Invocation de contrôle du repli et sonde de cycle de vie actives, leurs échecs alertent (§5.4.4)
- [ ] Corrélation OTel bout en bout démontrée (traceId ou operationId)
- [ ] Aucun identifiant brut ni chunk sensible en clair dans les logs
- [ ] Dépendances `V2-LLD-001`, `V2-LLD-004`, `V2-LLD-005`, `V2-LLD-006` résolues pour les points listés en §13.1
- [ ] Préconditions d'infrastructure §1.3 levées, ou repli `emulated` déclaré et assumé
