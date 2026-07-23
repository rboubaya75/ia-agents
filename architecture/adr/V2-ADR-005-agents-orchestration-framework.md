# V2-ADR-005 — Agents et framework d'orchestration

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-002, V2-ADR-006, V2-ADR-008

## Contexte

La V1 utilise Strands (`deploy-agentcore/agents/phase_4.py`, `phase_4_robust.py`) mais **en
dépendance directe du code métier** : `from strands import Agent`, `BedrockModel`,
`HookProvider`/`HookRegistry`, `MCPClient`, `FileSessionManager` sont importés et utilisés
partout, sans couche d'abstraction. C'est exactement ce que la charte V2 interdit désormais
(« Strands ou LangGraph uniquement derrière un adapter optionnel »). La CAM (Domaine 5 — Agentic
AI, déjà décidée par `V2-ADR-002`) attribue la boucle agentique, le raisonnement et la sélection
des tools exclusivement à AgentCore Runtime ; cet ADR ne redécide pas cette propriété, il décide de
la structure interne de Runtime et des budgets qui l'encadrent.

Les budgets existants en V1 sont uniquement temporels (`MAX_PROMPT_CHARS = 4000`,
`MIN_TOOL_DEADLINE_REMAINING_MS`, deadline absolue propagée) — `docs/adr/ADR-0006-application-
budgets-and-trip-pagination.md` fixe une chaîne de budgets emboîtés par composant, mais **aucune
borne n'existe sur le nombre de tours agentiques ni sur le nombre d'appels de tools**. C'est un
gap réel à combler, pas seulement une reconduction de l'existant.

## Options

### Option A — Statu quo : Strands en dépendance directe

**Rejet proposé :** viole la charte, couple irréversiblement le domaine métier au framework, et
contredit le principe P-04 (Technology Independence) déjà acté par la CAM.

### Option B — Migrer vers LangGraph derrière un adapter

**Rejet proposé :** aucun bénéfice démontré ne justifie d'abandonner Strands, déjà validé en
production V1 (hooks, client MCP, gestion de session, intégration Bedrock fonctionnels). Une
réécriture de framework sans motif concret serait un risque non justifié.

### Option C — Strands derrière un adapter explicite

Strands reste le framework, mais toute son API est isolée derrière une interface d'adapter propre
au projet. Le code domaine (structure `/agents`, contrats applicatifs) n'importe jamais
`strands.*` directement.

## Décision proposée

Retenir **l'option C**.

```text
/agents
  ├── adapter/            # seul module autorisé à importer strands.*
  │     └── strands_adapter.py   (implémente l'interface AgentAdapter)
  ├── interface.py         # AgentAdapter (Protocol) : invoke(context) -> AgentResult
  └── domain/               # logique métier, budgets, hooks — dépend uniquement de interface.py
```

Un test d'architecture (lint d'imports) doit détecter toute importation de `strands.*` en dehors
du module `adapter/`.

## Orchestration

Un **orchestrateur unique par défaut**, cohérent avec le HLD (« orchestrateur minimal par défaut ;
agent spécialisé uniquement avec responsabilité et bénéfice démontrés »). Aucun multi-agent tant
qu'un besoin concret n'est pas documenté ; l'ajout d'un agent spécialisé exige un amendement ADR
ou une justification explicite en LLD, conformément à P-01/P-02 de la CAM.

## Budgets

Étendent le pattern de budgets temporels emboîtés déjà validé en V1
(`docs/adr/ADR-0006-application-budgets-and-trip-pagination.md`) avec des bornes non temporelles
absentes aujourd'hui :

- `maxTurns` — nombre de tours modèle/tool par conversation ;
- `maxToolCalls` — nombre total d'appels de tool par conversation ;
- `maxTokens` — tokens cumulés entrée + sortie ;
- `deadlineEpochMs` — déjà existant, réutilisé sans modification.

Ces budgets sont des paramètres de configuration injectés par l'adapter, jamais des constantes
codées en dur (contrairement à `MODEL_ID` aujourd'hui) — condition nécessaire pour que
`V2-ADR-012` (modèles Bedrock, profils d'inférence et fallback) puisse faire varier le modèle sans
réécriture du domaine.

## Tests sans dépendance Bedrock

Le principe déjà établi en V1 (`tests/README.md` §2.3 : « tester les frontières, pas les SDK »,
illustré par `tests/unit/test_runtime_behavior.py` qui remplace les fonctions module-level plutôt
que de simuler le SDK Strands/Bedrock) est reconduit avec l'interface `AgentAdapter` comme
frontière de mock explicite : les tests unitaires remplacent `AgentAdapter.invoke`, jamais les
objets internes de Strands. Aucun appel réseau réel vers Bedrock ou MCP en test unitaire.

## Fallback modèle

Le mécanisme précis (bascule de modèle, profils d'inférence) est traité par `V2-ADR-012`, qui
dépend de cet ADR. La seule exigence fixée ici : l'adapter doit accepter le modèle et sa
configuration en paramètre, jamais en valeur fixe dans le code du domaine.

## Justification des dépendances

- **V2-ADR-006** : l'agent reçoit l'identité de confiance injectée côté serveur et ne fait jamais
  confiance à une identité produite par le modèle — le contrat d'injection est fixé par ce
  dernier ;
- **V2-ADR-008** : les hooks et les budgets (tours/tools/tokens) émettent les événements et
  métriques de corrélation dont l'instrumentation est décidée par ce dernier.

## Conséquences

- création de la structure `/agents` avec séparation adapter/interface/domaine ;
- Strands reste une dépendance du projet mais confinée à un seul module ;
- un changement futur de framework (ou l'ajout d'un second adapter) ne modifie que le module
  `adapter/`, jamais le domaine ;
- les hooks `BeforeToolCallEvent`/`AfterInvocationEvent` déjà utilisés en V1 sont conservés mais
  réécrits derrière l'interface, avec les nouveaux budgets tours/tools/tokens ajoutés aux
  vérifications déjà en place (deadline, `MAX_PROMPT_CHARS`).

## Preuves attendues

- aucun fichier hors de `agents/adapter/` n'importe `strands.*` (test d'architecture automatisé) ;
- un dépassement de `maxTurns`, `maxToolCalls` ou `maxTokens` produit une erreur structurée, sans
  boucle incontrôlée ;
- les tests unitaires du domaine s'exécutent sans appel réseau Bedrock ou MCP réel ;
- un changement de `MODEL_ID` ne modifie aucun fichier du domaine, uniquement la configuration.

## Références AWS

- Amazon Bedrock AgentCore Runtime ;
- Amazon Bedrock Converse API ;
- AgentCore Gateway MCP avec authentification IAM.
