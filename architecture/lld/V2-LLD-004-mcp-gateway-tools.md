# V2-LLD-004 — AgentCore Gateway MCP et tools

- **Version :** 0.1.1
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G2
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§6.3, §6.4)
- **Dépendances ADR :** V2-ADR-002, V2-ADR-005, V2-ADR-006, V2-ADR-008, V2-ADR-014

> **Ce que ce LLD possède.** Le contrat des tools : catalogue, classe, schémas d'arguments,
> injection d'identité, séquence d'une action mutante, régime d'idempotence, politique de retry et
> disjoncteur. `V2-ADR-014` lui délègue nommément « le contrat du tool » et `V2-ADR-011` « la
> garantie d'idempotence des tools ».

> **Ce qu'il ne possède pas.** Le **magasin de commandes** — table, clés, TTL — appartient à
> `V2-LLD-006`, qui possède les modèles de données. Ce LLD énonce les invariants que ce magasin doit
> satisfaire ; il n'en écrit pas le schéma. La règle de non-duplication est énoncée en §1.6 et vaut
> pour l'ensemble du document.

> **Quatre écarts de corpus sont relevés ici** (§1.7). Le premier est structurel : le magasin de
> commandes exigé par `V2-ADR-014` n'est possédé par aucun document — `V2-ADR-014` le délègue à
> `V2-LLD-006`, qui le renvoie à `V2-LLD-004` et `V2-LLD-005`. Une boucle de délégation ne produit
> pas un propriétaire. Les corrections sont nommées ici et livrées dans le même lot, par des commits
> distincts de celui qui porte ce LLD.

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD/Charte | Libellé |
|---|---|
| HLD §4 | Les mutations sont confirmées, idempotentes et non rejouées après effet de bord |
| HLD §6.3 | Séquence matérialisation → confirmation hors modèle → exécution atomique |
| HLD §6.4 | La confirmation est hors du chemin du modèle ; la classe de tool est déclarée |
| Charte §6 | Défense contre prompt injection, data poisoning et exfiltration par tool |
| Charte §9 | Risque d'injection documentaire conduisant à une action non voulue |
| ADR-002 | P-01 et P-02 : la Gateway est propriétaire de `Tool Authorization` ; nul autre ne l'implémente |
| ADR-005 | Le nombre d'appels de tool est borné par `maxToolCalls` |
| ADR-006 | L'identité est injectée côté serveur ; les tools écrasent toute identité produite par le modèle |
| ADR-008 | Propagation du contexte de trace jusqu'aux tools ; redaction des identifiants |
| ADR-014 | Objet de commande, deux tools distincts, exécution par référence, classe fail-closed |
| CAM Domaine 7 | La Gateway est le seul point d'entrée des tools ; classe de tool au catalogue |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-002 | La Gateway MCP est propriétaire de `Tool Authorization` (CAM Domaine 7). Le filtre d'exposition de `V2-LLD-003 §6.2` n'en est pas une seconde implémentation (§9.3). Aucun tool n'est appelable hors de la Gateway, ni par FastAPI, ni par le code agent |
| V2-ADR-005 | Une action mutante consomme **deux** appels de tool, imputés à `maxToolCalls` dont la valeur appartient à `V2-LLD-003 §5` (§11.1) |
| V2-ADR-006 | Identité injectée côté serveur et écrasant tout argument homonyme (§4.3) ; aucun jeton Cognito n'atteint un tool (§4.2) ; resource policies IAM entre Runtime et Gateway (§2.3) |
| V2-ADR-008 | Propagation `traceparent` jusqu'aux tools et repli par `operationId` (§13.1) ; aucun argument métier brut journalisé (§13.2) |
| V2-ADR-014 | **Contrat du tool** — délégation explicite. Deux tools distincts pour matérialiser et exécuter (§5) ; exécution par référence, arguments métier ignorés (§5.4) ; transition d'état et effet de bord dans la même transaction (§6.3) ; classe de tool au catalogue avec défaut `mutating` (§3.3) ; l'état `executed` tient lieu d'enregistrement d'idempotence (§7.1) |

### 1.3 Préconditions bloquantes héritées des ADR

`V2-ADR-014` prend sa décision et nomme quatre faits à établir avant implémentation. Ce ne sont pas
des questions de conception ouvertes : ce sont des vérifications sur le service.

| # | Précondition | Origine | Conséquence si non satisfaite |
|---|---|---|---|
| P1 | AgentCore Gateway MCP peut exposer **deux tools distincts** — matérialisation et exécution — avec des **politiques d'autorisation distinctes** | `V2-ADR-014` précondition 1 | **Non bloquante pour la séparation.** §9.2 retient deux cibles à rôles IAM distincts comme mécanisme principal, quelle que soit l'issue de P1 ; les politiques Gateway s'y ajoutent en défense supplémentaire si P1 est satisfaite |
| P2 | Le magasin de commandes porte la **transition conditionnelle et l'effet de bord dans une transaction unique** — région commune et limite d'items compatible | `V2-ADR-014` précondition 2 | **Levée par décision de conception** (`V2-LLD-006 §5.3.3`) : `${env}-commands` est colocalisée avec la cible métier en `eu-west-3`, et une commande porte une mutation — les deux conditions de `TransactWriteItems` sont donc satisfaites par construction, et une règle de garde bloque tout plan qui les romprait. Il n'y avait aucun repli acceptable : sans atomicité, deux exécutions concurrentes du même `commandId` passeraient toutes deux le contrôle (§6.3) |
| P3 | La rétention d'une commande `executed` peut couvrir la **fenêtre d'idempotence** de la mutation qu'elle porte | `V2-ADR-014` précondition 3 | Repli nommé par l'ADR : conserver au-delà une **entrée réduite valant enregistrement de non-rejeu**. Jamais laisser la commande disparaître en silence (§7.4) |
| P4 | La latence cumulée de la transaction d'exécution tient dans la **deadline propagée** par `operationContext` | `V2-ADR-014` précondition 4 | Le tour expire pendant une transaction indissociable. Traitement en §8.4 : l'expiration ne produit pas de retry mais une résolution par lecture d'état |

Une cinquième précondition est propre à ce LLD et n'est pas héritée :

| # | Précondition | Origine | Conséquence si non satisfaite |
|---|---|---|---|
| P5 | Le catalogue de la Gateway peut porter un **attribut de classe** par tool, lisible à l'invocation sans être un paramètre d'appel | ce LLD §3.3 | La classe est portée par le **manifeste de catalogue** versionné (§3.1), dont le service dérive sa configuration. La garantie devient une conformité vérifiée en CI plutôt qu'une propriété du service (§3.3) |

**État des préconditions.** P2 est **levée** par la décision de colocalisation de
`V2-LLD-006 §5.3.3`, prise après la rédaction initiale de ce tableau. P1, P3, P4 et P5 restent à
établir.

La distinction importe pour §1.8 : P2 était la seule sans repli, et sa levée retire l'obstacle
structurel au mécanisme. Les quatre autres ont chacune un repli nommé dans la colonne ci-dessus — le
mécanisme est donc **activable**, et ce qui reste conditionné est la qualité de la défense en
profondeur, non son existence.

### 1.4 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-001 | Ingress et frontière de sécurité : `V2-LLD-001`. Aucun tool n'est exposé par la passerelle publique — le chemin d'un tool part de Runtime, jamais du navigateur |
| V2-ADR-003, V2-ADR-004, V2-ADR-013, V2-ADR-017, V2-ADR-018, V2-ADR-019 | RAG, ingestion, espace d'embedding, classification, évaluation : `V2-LLD-002` et `V2-LLD-006`. Le pipeline documentaire n'emprunte pas le chemin des tools en V2 (§3.5) |
| V2-ADR-007 | Plateforme réseau : consommée telle quelle. La posture egress des cibles de tool est portée par `V2-LLD-001` ; ce LLD en énonce l'invariant (§12.3) |
| V2-ADR-009 | CI/CD : `V2-LLD-008`. Ce LLD fixe **ce qui doit être vérifié** sur le catalogue (§3.6), pas le pipeline qui le vérifie |
| V2-ADR-010 | Sauvegarde et restauration : `V2-LLD-006`. La rétention d'une commande `executed` est ici une **exigence d'idempotence** (§7.4), pas une politique de sauvegarde |
| V2-ADR-011 | Streaming et annulation : `V2-LLD-003`. Ce LLD porte la seule part que l'ADR lui délègue — la fenêtre non annulable et la garantie d'idempotence (§10) |
| V2-ADR-012 | Repli modèle : `V2-LLD-003`. Un repli de modèle ne change pas le contrat d'un tool |
| V2-ADR-015 | Mémoire et effacement : `V2-LLD-006`. Une demande d'effacement est une action mutante qui **emprunte** la séquence de ce LLD sans en modifier le contrat |
| V2-ADR-016 | WAF et quotas : `V2-LLD-005`. Le quota de commandes `pending` est porté par `V2-LLD-005 §7.2` ; ce LLD en consomme l'effet (§5.2) |
| V2-ADR-020 | Ancrage d'identité : `V2-LLD-005` et `V2-LLD-001`. Ce LLD consomme la `trustedIdentity` déjà résolue et ne relit aucun claim |

### 1.5 Périmètre et exclusions

**Inclus.** Position de la Gateway et chemin d'appel ; les trois identités du chemin ; manifeste de
catalogue, classe de tool et versionnement ; schémas d'arguments et champs interdits ; injection
d'identité ; séquence complète d'une action mutante et contrat des deux tools ; invariants exigés du
magasin de commandes ; régime d'idempotence et ce qu'il remplace ; politique de retry et disjoncteur ;
autorisation Gateway et son rapport au filtre d'exposition ; fenêtre non annulable ; imputation
budgétaire ; menaces propres au chemin tool ; événements et redaction.

**Exclus, avec leur propriétaire.**

- **Le magasin de commandes** — table, clés, TTL des deux fenêtres, rétention : `V2-LLD-006`. Ce LLD
  énonce les invariants (§6.1), jamais le schéma. C'est l'objet de l'écart 1 (§1.7).
- **L'endpoint de confirmation** et sa part autorisation : `V2-LLD-005 §4.6`. Ce LLD ne redécrit ni
  la route, ni ses contrôles ; il en consomme l'effet — une commande `confirmed` (§5.3).
- **Le quota de commandes `pending`** par identité : `V2-LLD-005 §7.2`.
- **Le filtre d'exposition** `tool_allowlist` et sa résolution : `V2-LLD-003 §6.2` et
  `V2-LLD-005 §4.7`. Ce LLD situe ce filtre par rapport à l'autorisation Gateway (§9.3).
- **Les budgets** `maxTurns`, `maxToolCalls`, `maxTokens` et leurs valeurs : `V2-LLD-003 §5`.
- **Le rendu du résumé de commande** et le geste de confirmation côté navigateur : `V2-LLD-010`.
- **La posture egress** des cibles de tool et leur placement réseau : `V2-LLD-001`.
- **L'instrumentation OpenTelemetry** : `V2-LLD-007`. Ce LLD nomme les événements attendus (§13.1),
  pas leur émission.
- **La pyramide de tests** : `V2-LLD-009`. Ce LLD fixe les preuves attendues (§15), pas leur
  ordonnancement.
- **Les tools documentaires agentiques** : hors périmètre V2 par `V2-ADR-014` §Réalisation par phase.

### 1.6 Règle de non-duplication

La règle établie par `V2-LLD-005 §1.6` s'applique ici sans exception :

> **Un paramètre a un seul propriétaire. Ce LLD énonce l'invariant qu'il doit satisfaire ; il ne
> reproduit pas sa valeur.**

| Contrôle | Contrat (invariant) | Réalisation (valeur) |
|---|---|---|
| Magasin de commandes | ce LLD §6.1 | `V2-LLD-006` — **propriétaire à rétablir** (§1.7 écart 1) |
| TTL des deux fenêtres d'expiration | ce LLD §6.1 | `V2-LLD-006` |
| Rétention d'une commande `executed` | ce LLD §7.4 | `V2-LLD-006` |
| Endpoint de confirmation | `V2-ADR-014` §Canal | `V2-LLD-005 §4.6` |
| Quota de commandes `pending` | `V2-ADR-016` | `V2-LLD-005 §7.2` |
| Budget `maxToolCalls` | ce LLD §11.1 (imputation) | `V2-LLD-003 §5` (valeur) |
| Filtre d'exposition | `V2-LLD-003 §6.1` | `V2-LLD-003 §6.2` |
| Ledger d'idempotence résiduel | ce LLD §7.3 (portée) | `V2-LLD-006 §5` (schéma) |
| Placement réseau et egress des cibles | ce LLD §12.3 | `V2-LLD-001` |

Lorsqu'une valeur apparaît dans ce document, c'est qu'elle n'existe nulle part ailleurs.

### 1.7 Écarts de corpus relevés par ce LLD

Quatre écarts sont apparus à la rédaction. Aucun n'est corrigé par ce document : les corrections sont
nommées ici et portées par des commits distincts du même lot.

> **État — les quatre sont traités.** L'analyse ci-dessous est conservée : elle porte la
> justification des corrections, que les documents corrigés ne répètent pas intégralement.
>
> | Écart | Corrigé dans |
> |---|---|
> | 1 — magasin de commandes sans propriétaire | `V2-LLD-006` v0.5 §1.2 et §5.3 (table, clés, GSI `by-operation`, trois durées, colocalisation transactionnelle) |
> | 2 — portée du ledger d'idempotence | `V2-LLD-006` v0.5 §5.1 et §5.2 (mutations `Trips` retirées, scope `trip-mutation` supprimé) |
> | 3 — route de confirmation non nommée | `V2-LLD-001` v0.4 §7.0 (confirmation et annulation nommées, `BUFFERED`) |
> | 4 — corrections `V2-ADR-014` non appliquées | `V2-ADR-006` §Modèle d'autorisation (septième intrant) ; `V2-ADR-011` §Décision — annulation (fenêtre réduite à la transaction) |

#### Écart 1 — le magasin de commandes n'a pas de propriétaire (bloquant)

`V2-ADR-014` conclut sa section « Cycle de vie d'une commande » ainsi :

> « Le choix du magasin, la valeur des TTL et la forme des clés sont délégués à `V2-LLD-006`, qui
> possède les modèles de données, et le contrat du tool à `V2-LLD-004`. »

`V2-LLD-006 §1.2` renvoie la délégation :

> « Le mécanisme de confirmation (matérialisation, ledger d'idempotence de commande) est implémenté
> dans `V2-LLD-004` et `V2-LLD-005` ; ce LLD n'en porte que le point d'entrée et
> l'`erasureOperationId` qui en est la trace. »

**Une boucle de délégation ne produit pas un propriétaire.** Le magasin de commandes — la table qui
porte l'autorisation de toute action mutante et, par `V2-ADR-014`, l'idempotence de cette même
action — n'est décrit nulle part : ni ses clés, ni ses deux TTL, ni sa rétention. Ce n'est pas une
omission de rédaction : c'est le seul objet durable dont dépend la garantie centrale de l'ADR.

L'arbitrage est déjà rendu par l'ADR, qui est l'autorité : le magasin appartient à `V2-LLD-006`.
Ce LLD énonce les invariants (§6.1) et s'arrête là.

**Correction attendue dans `V2-LLD-006` :** §1.2 rétablit `V2-ADR-014` comme **directement**
applicable pour le magasin de commandes ; §5 ajoute la table, ses clés, les TTL des deux fenêtres et
la borne de rétention de l'état `executed`.

#### Écart 2 — le ledger d'idempotence garde une portée que l'ADR lui a retirée

`V2-LLD-006 §5.1` liste dans la portée du ledger :

> « mutations `Trips` (V1, inchangé) »

`V2-ADR-014` a explicitement retiré ces mutations de cette portée :

> « Une mutation passée par une commande **n'écrit pas d'entrée dans le ledger** de `V2-LLD-006` §5,
> qui reste réservé aux opérations sans commande — uploads documentaires et déclenchements
> d'ingestion. »

Maintenues ensemble, les deux formulations produisent **deux enregistrements d'idempotence pour la
même mutation**, dont un seul est consulté à l'exécution. Le second n'est pas une redondance
inoffensive : il donne l'apparence d'une garantie à un enregistrement que rien ne lit, et sa purge
TTL — sept jours en `V2-LLD-006 §5.2` — ne dit rien de la fenêtre réellement protégée.

**Correction attendue dans `V2-LLD-006 §5.1` :** retirer les mutations `Trips` de la portée du
ledger, en renvoyant au magasin de commandes ; conserver uploads documentaires et déclenchements
d'ingestion, qui n'ont pas de commande.

#### Écart 3 — l'endpoint de confirmation n'est pas au tableau des routes

`V2-ADR-014` §Réalisation par phase attribue la confirmation à un « endpoint FastAPI dédié
(`V2-LLD-001`, `V2-LLD-010`) ». `V2-LLD-005 §4.6` en porte la part autorisation et nomme la route
`POST /api/v1/commands/{commandId}/confirm`. Le tableau des routes de `V2-LLD-001 §7.0` ne la
mentionne pas : elle ne relève littéralement que de la ligne fourre-tout « Routes documentaires et
d'administration ».

La conséquence est mineure mais réelle : `responseTransferMode` est un réglage **par méthode**, et
une route non nommée n'a pas de réglage vérifiable au plan. La confirmation est un appel court sans
diffusion — `BUFFERED` est correct, encore faut-il que ce soit écrit.

**Correction attendue dans `V2-LLD-001` :** nommer la route de confirmation au tableau des routes,
en mode `BUFFERED`.

#### Écart 4 — deux corrections demandées par `V2-ADR-014` non appliquées dans les ADR

`V2-ADR-014` §Écarts à corriger dans le corpus demande deux modifications qui n'avaient pas été
faites à la rédaction de ce LLD :

| Document | Passage | Correction demandée par `V2-ADR-014` | État |
|---|---|---|---|
| `V2-ADR-006` | « Modèle d'autorisation », points 1 à 6 | ajouter la commande confirmée comme fondement d'autorisation des actions mutantes | **appliquée** — septième intrant ajouté ; à la rédaction, l'ADR n'en portait que six, dont aucun ne mentionnait la commande |
| `V2-ADR-011` | renvoi « la garantie d'idempotence des tools relève de `V2-ADR-014` » | préciser que la fenêtre non annulable est l'**exécution**, et non l'appel de tool entier | **appliquée** — fenêtre réduite à la transaction ; à la rédaction, le texte disait encore « pendant l'exécution d'un tool porteur d'effet de bord » |

Le second écart demande une lecture attentive, parce que l'énoncé de `V2-ADR-011` n'est pas faux —
il est plus large que nécessaire. L'ADR écrit : « jamais **pendant** l'exécution d'un tool porteur
d'effet de bord […] l'annulation attend **la fin de l'appel en cours**, puis s'arrête. »

La première partie ne pose pas de problème : un tool de proposition n'est pas « porteur d'effet de
bord », donc l'annulation reste évaluable pendant une matérialisation. C'est la seconde qui décrit
une fenêtre trop large. Pour un tool d'exécution, l'appel comprend la résolution du `commandId`, la
lecture de la commande, la construction de la mutation, **puis** la transaction. Seule la dernière
est indissociable. Attendre « la fin de l'appel en cours » immobilise l'annulation pendant des
phases qui, elles, sont interruptibles sans laisser d'état partiel.

C'est exactement la réduction que `V2-ADR-014` revendique — « la fenêtre non annulable se réduit […]
seule l'exécution est atomique et non interruptible » — et que sa demande de correction visait
(§10.1).

**Corrections attendues :** `V2-ADR-006` §Modèle d'autorisation, ajout d'un septième intrant ;
`V2-ADR-011` §Sémantique d'annulation coopérative, restriction de la fenêtre à l'exécution.

### 1.8 Ce qui reste en vigueur pendant la bascule

`V2-ADR-014` est explicite sur ce point et ce LLD ne l'assouplit pas :

> « Tant que ces preuves ne sont pas produites, le contrôle `confirmationVerified` de `ADR-0007`
> reste en vigueur. Il est insuffisant au sens de cet ADR, mais il n'est pas nul. »

Le retrait de `confirmationVerified` (`deploy-agentcore/lambda_function_hardened.py`) n'est donc
**pas** un préalable à la réalisation de ce LLD : c'est sa conclusion. Les deux mécanismes coexistent
pendant la bascule, et le retrait du premier est conditionné par la preuve M1 (§15).

**Ce que la levée de P2 change, et ce qu'elle ne change pas.** P2 était la seule précondition sans
repli : tant qu'elle tenait, le mécanisme n'était pas activable et `confirmationVerified` restait le
seul contrôle. Elle est levée (§1.3), donc le mécanisme est réalisable. Cela **n'avance pas** pour
autant le retrait du contrôle V1, qui reste conditionné par une preuve — M1, exercée sur le
mécanisme déployé — et non par l'état des préconditions. Une précondition dit qu'un mécanisme *peut*
être construit ; une preuve dit qu'il *fonctionne*. Les confondre retirerait le filet avant d'avoir
vérifié ce qui le remplace.

---

## 2. AgentCore Gateway MCP — position et frontière

### 2.1 Ce que la Gateway est, et ce qu'elle n'est pas

La CAM Domaine 7 attribue à la Gateway sept capacités : découverte, authentification, autorisation,
transport, enregistrement, négociation de version et déclaration de classe de tool. Trois
conséquences en découlent, et la troisième est celle que le corpus a le plus de mal à tenir.

**La Gateway est le seul point d'entrée.** Aucun tool n'est appelable par FastAPI ni par le code du
domaine `/agents`. Cette règle n'a pas d'exception de commodité : un tool « appelé directement pour
les tests » est un tool dont l'autorisation n'a pas été exercée.

**La Gateway n'est pas un proxy transparent.** Elle décide. `Tool Authorization` est sa capacité, et
le refus d'un appel qu'elle n'autorise pas est un comportement nominal, pas une panne (§8.2).

**La Gateway n'est pas le lieu de la vérification de confirmation.** `V2-ADR-014` place cette
vérification dans le tool, au point exact où l'effet se produit, et la CAM Domaine 5 énonce
symétriquement que le Runtime ne la porte pas. La Gateway autorise l'**appel** ; elle n'atteste rien
sur ce que l'utilisateur a autorisé. Un contrôle de confirmation placé à la Gateway serait une
vérification disjointe de l'écriture — exactement le mode d'échec que l'option B de `V2-ADR-014` a
fait rejeter.

### 2.2 Chemin d'appel

```text
Runtime (/agents, adapter)
   │  ① filtre d'exposition — tool_allowlist (V2-LLD-003 §6.2)
   │     décide si le tool est PRÉSENTABLE au modèle
   ▼
   │  ② injection d'identité — trustedIdentity écrase tout homonyme (§4.3)
   ▼
AgentCore Gateway MCP
   │  ③ authentification IAM du Runtime (§2.3)
   │  ④ Tool Authorization — décide si l'appel est PERMIS (§9)
   │  ⑤ validation contre le schéma publié — premier des deux points (§4.1)
   ▼
Cible du tool (fonction)
   │  ⑥ résolution du nom du tool depuis le CONTEXTE, jamais du payload (§4.4)
   │  ⑦ validation stricte du schéma — second point, qui ne suppose rien de ⑤ (§4.1)
   │  ⑧ pour un tool d'exécution : chargement de la commande, transition
   │     conditionnelle et effet de bord dans la MÊME transaction (§6.3)
   ▼
Magasin métier + magasin de commandes (V2-LLD-006)
```

Les points ① et ④ sont deux contrôles distincts, pas deux implémentations d'un même contrôle : la
démonstration est en §9.3. Les points ⑤ et ⑦ sont le même contrôle exercé deux fois, ce que la CAM
Domaine 10 exige et que §3.7 justifie par un scénario concret. Le point ⑧ est la seule garantie du
mécanisme ; ① à ⑦ échouent tôt et donnent un message clair, mais aucun d'eux n'est la garantie.

### 2.3 Les trois identités du chemin

Le chemin porte trois identités de natures différentes. Les confondre est la source d'erreur la plus
fréquente sur ce type d'architecture, et le corpus V1 en porte déjà une trace (`V2-LLD-003 §9.1`
relève un `execute-api:Invoke` erroné hérité d'une confusion entre API Gateway et AgentCore Gateway).

| # | Identité | Nature | Ce qu'elle autorise | Propriétaire |
|---|---|---|---|---|
| 1 | Rôle IAM du Runtime | principal AWS | invoquer la Gateway | `V2-LLD-003 §9.1` |
| 2 | Rôle IAM de la Gateway vers la cible | principal AWS | invoquer la fonction cible | ce LLD §9.1 |
| 3 | `trustedIdentity` | identité applicative | **rien au niveau AWS** — elle est le sujet de la décision métier du tool | `V2-LLD-005 §3` |

**La troisième n'est pas un principal.** `trustedIdentity` ne donne aucun droit AWS : elle indique au
tool *pour le compte de qui* il agit, afin qu'il construise ses clés et filtre ses accès. Un tool qui
traiterait `trustedIdentity` comme une autorisation — « cette identité est présente, donc l'appel est
permis » — annulerait l'autorisation Gateway sans le dire.

**Aucun jeton Cognito ne circule sur ce chemin.** `V2-ADR-006` l'interdit et `runtime-contract.md §4`
liste `cognitoToken` et `authorizationHeader` parmi les champs refusés. Un tool n'a donc aucun moyen
— et aucun besoin — de revalider un jeton : l'identité lui parvient déjà résolue.

---

## 3. Catalogue de tools

### 3.1 Le manifeste est la source, la configuration en dérive

Le catalogue existe à deux endroits — la configuration de la Gateway et le code de la cible — et ces
deux endroits doivent dire la même chose. La règle retenue évite la duplication en nommant une
source unique :

> **Un manifeste versionné est la source de vérité du catalogue. La configuration Terraform de la
> Gateway et la table de dispatch de la cible en sont dérivées. Aucune des deux n'est écrite à la
> main.**

```text
tools/catalogue.yaml          ← source unique, revue en pull request
        │
        ├──► Terraform : cibles et schémas exposés par la Gateway
        │
        └──► cible : table de dispatch nom → handler, et classe par tool
```

Une divergence entre le manifeste et l'un de ses dérivés est un échec de CI, pas un avertissement
(§3.6). Ce n'est pas une préférence d'outillage : la classe d'un tool est le contrôle qui décide
si une confirmation est exigée, et un contrôle dont deux copies peuvent diverger n'est pas un
contrôle.

### 3.2 Déclaration d'un tool

```yaml
- name: get_trips
  version: 1
  class: read
  description: "Liste les voyages du périmètre de l'identité appelante."
  arguments:
    type: object
    additionalProperties: false
    properties:
      limit: { type: integer, minimum: 1, maximum: 50 }
      cursor: { type: string, maxLength: 512 }
    required: []

- name: propose_create_trip
  version: 1
  class: mutating
  role: proposition          # matérialise une commande, sans effet de bord
  executes: execute_create_trip
  arguments:
    type: object
    additionalProperties: false
    properties:
      destination: { type: string, maxLength: 120 }
      startDate:   { type: string, format: date }
      endDate:     { type: string, format: date }
    required: [destination, startDate, endDate]

- name: execute_create_trip
  version: 1
  class: mutating
  role: execution            # applique la commande, effet de bord
  arguments:
    type: object
    additionalProperties: false
    properties:
      commandId: { type: string, pattern: "^cmd_[0-9a-f]{32}$" }
    required: [commandId]
```

Trois propriétés de cette déclaration ne sont pas décoratives.

**`additionalProperties: false` est obligatoire.** Un schéma permissif rouvre le canal par lequel un
modèle transmet un champ que le tool n'attend pas mais qu'une bibliothèque quelconque interprétera.
La règle est reprise de `lambda_function_code._reject_unexpected`, déjà en vigueur en V1.

**Le schéma d'un tool d'exécution ne contient que `commandId`.** C'est la traduction structurelle de
la règle « seul le `commandId` circule » de `V2-ADR-014`. Un tool d'exécution dont le schéma
accepterait des arguments métier ne serait pas seulement contraire à la décision : il rendrait de
nouveau *possible* la divergence que l'ADR déclare impossible à produire.

**Aucun champ d'identité n'apparaît.** `actorId`, `tenantId`, `userId`, `subjectId` et leurs
variantes sont interdits au schéma (§4.2). L'identité est injectée, pas déclarée.

### 3.3 Classe de tool — `read` / `mutating`, défaut fail-closed

`V2-ADR-014` fixe trois propriétés que ce LLD réalise :

| Propriété de l'ADR | Réalisation |
|---|---|
| la classe est une propriété du catalogue, pas un paramètre d'appel | `class` est un champ du manifeste ; il n'existe dans aucun schéma d'arguments |
| un tool qui ne déclare pas sa classe est traité comme `mutating` | la cible résout la classe par `catalogue.get(name).class`, avec `mutating` en valeur par défaut de la résolution — jamais `read` |
| un tool `mutating` se décline en deux tools distincts | `role: proposition` / `role: execution`, et le contrôle de conformité §3.6 refuse un `mutating` isolé |

**Ce que « traité comme `mutating` » produit concrètement.** Un tool sans classe déclarée est résolu
en `mutating` sans `role`. La cible refuse alors l'appel : un `mutating` de rôle inconnu n'a ni
chemin de matérialisation, ni chemin d'exécution. Le tool devient **inutilisable**, ce qui est
exactement l'intention de l'ADR — « un oubli de déclaration rend le tool inutilisable sans commande
confirmée, jamais exécutable sans confirmation ».

**Pourquoi le défaut ne peut pas être `read`.** Un défaut `read` transformerait un oubli de
déclaration en exécution non confirmée : le mode d'échec le plus coûteux du système obtenu par la
faute la plus banale. Le coût du choix inverse est un tool cassé jusqu'à correction du manifeste ;
il est assumé, et `V2-ADR-014` §Conséquences le nomme comme tel.

**La classe n'est pas dérivable du nom.** Une convention de nommage (`propose_*`, `execute_*`) est
une aide à la lecture, pas un contrôle : rien n'empêche un tool `do_the_thing` d'écrire. La classe
est déclarée et vérifiée (§3.6) ; le nom ne fait que la rendre lisible.

### 3.4 Nommage et versionnement

| Règle | Valeur |
|---|---|
| Forme du nom | `snake_case`, préfixé par `propose_` ou `execute_` pour la classe `mutating` |
| Unicité | un nom est unique dans le catalogue, toutes versions confondues |
| Version | entier monotone par tool, porté par le manifeste |
| Compatibilité | un changement de schéma **rétro-incompatible** exige un nouveau nom, pas un incrément de version |

**Un incrément de version n'autorise pas un changement incompatible.** La raison n'est pas
esthétique : le modèle sélectionne un tool par son nom, à partir de la description exposée par la
Gateway. Changer la signature sous le même nom fait échouer les appels que le modèle produit à
partir d'une description mémorisée dans le contexte de la conversation en cours. Un nouveau nom rend
la rupture visible et laisse l'ancien tool retirable par étapes.

**Versions de protocole MCP.** `Tool Version Negotiation` est une capacité de la Gateway (CAM
Domaine 7) : ce LLD ne réimplémente pas la négociation, mais il en fixe les contraintes
applicatives, faute de quoi la capacité resterait sans contrat.

| Règle | Valeur |
|---|---|
| Version de protocole | **une seule est acceptée par environnement**, déclarée en configuration (§14) |
| Négociation avec repli silencieux | **refusée** — un repli non déclaré change le contrat sans le dire |
| Échec de négociation | erreur explicite, classée « indisponibilité transitoire » (§8.2), jamais dégradation muette |
| Montée de version | déploiement contrôlé, et non conséquence d'une négociation à l'exécution |

**Pourquoi refuser le repli silencieux.** Une négociation qui retombe sur une version antérieure
peut retirer des propriétés du protocole — mode de transport, forme des erreurs, structure des
métadonnées d'appel. Le système continuerait de fonctionner en apparence, sur un contrat qui n'est
plus celui décrit ici. C'est le même raisonnement que `V2-LLD-003 §8.2` sur le repli modèle :
un repli est acceptable, un repli non déclaré ne l'est pas.

**Version de protocole et version de tool sont indépendantes.** La première porte sur le dialogue
Runtime ↔ Gateway, la seconde sur la signature d'un tool (tableau ci-dessus). Un changement de l'une
n'implique rien sur l'autre, et les confondre conduirait à figer le catalogue sur les montées de
protocole.

### 3.5 Inventaire V2

`V2-ADR-014` §Réalisation par phase borne le périmètre V2 aux « tools Trips (`create`, `update`)
repris de la V1 ».

| Tool | Classe | Rôle | Origine | Effet |
|---|---|---|---|---|
| `get_trips` | `read` | — | V1 (`lambda_function_code`) | lecture du périmètre de l'identité |
| `get_trip` | `read` | — | V1 | lecture d'un voyage du périmètre |
| `propose_create_trip` | `mutating` | proposition | **nouveau** (V1 : `create_trip` en un appel) | écrit une commande `pending` |
| `execute_create_trip` | `mutating` | exécution | **nouveau** | crée le voyage, transition `confirmed` → `executed` |
| `propose_update_trip` | `mutating` | proposition | **nouveau** (V1 : `update_trip`) | écrit une commande `pending` |
| `execute_update_trip` | `mutating` | exécution | **nouveau** | met à jour le voyage, transition `confirmed` → `executed` |

**Hors périmètre V2.** Aucun tool documentaire — ingestion, suppression, reclassification — n'est
exposé à la Gateway. Le pipeline documentaire est déclenché par FastAPI sur intention utilisateur
explicite (`V2-LLD-002`), pas par le modèle. `V2-ADR-014` classe les actions documentaires
agentiques en V3, et `V2-ADR-014` §Classification des actions donne la raison : une mutation
déclenchée directement par l'utilisateur via une API REST n'a pas de mandataire interposé, donc pas
d'écart à fermer.

**Ce que le passage de deux à quatre tools mutants coûte.** Deux appels par mutation au lieu d'un
(§11.1), et deux entrées de catalogue au lieu d'une. C'est le prix de la vérifiabilité par
inspection : l'absence d'effet de bord d'une matérialisation se lit dans le catalogue, sans lire le
code.

### 3.6 Contrôle de conformité du catalogue

Le manifeste est vérifié à chaque modification. Les règles ci-dessous sont bloquantes ; leur
implémentation dans le pipeline relève de `V2-LLD-008`.

| # | Règle | Motif |
|---|---|---|
| C1 | Tout tool déclare une `class` parmi `read` et `mutating` | un oubli casse le tool (§3.3) ; le détecter en CI évite de le découvrir en production |
| C2 | Tout tool `mutating` déclare un `role` parmi `proposition` et `execution` | un `mutating` isolé n'a pas de chemin d'appel |
| C3 | Tout `role: proposition` référence par `executes` un tool existant de `role: execution` | une proposition sans exécution produit des commandes que rien ne consomme |
| C4 | Tout `role: execution` a un schéma dont les propriétés sont exactement `{commandId}` | traduction structurelle de « seul le `commandId` circule » |
| C5 | Aucun schéma ne déclare `additionalProperties: true` ni ne l'omet | §4.1 |
| C6 | Aucun schéma ne déclare une propriété de la liste des champs interdits (§4.2) | l'identité est injectée, pas reçue |
| C7 | Le manifeste et la configuration Terraform dérivée sont identiques | §3.1 |
| C8 | Aucun nom de tool n'est réutilisé avec une signature incompatible | §3.4 |

C4 mérite un mot. C'est la règle qui rend l'écart de contenu de `V2-ADR-014` **structurellement**
impossible plutôt que défendu par une revue : un tool d'exécution qui accepterait `destination` ne
passe pas la CI, quelle que soit la discipline de son implémentation.

### 3.7 Ce que C7 ne couvre pas — la divergence par ordre de déploiement

C7 vérifie que le manifeste et la configuration Terraform disent la même chose. Elle le vérifie **au
plan**, sur un dépôt cohérent. Elle ne dit rien de l'état déployé.

Or le manifeste a deux consommateurs qui ne se déploient pas ensemble :

```text
manifeste  ──► Terraform ──► catalogue exposé par la Gateway     [ déploiement A ]
           └─► image ──────► table de dispatch de la cible        [ déploiement B ]
```

Entre A et B, les deux copies divergent en exécution alors que C7 passe. Deux fenêtres sont
possibles, et elles n'ont pas la même gravité :

| Ordre | Effet |
|---|---|
| A avant B | la Gateway expose un tool que la cible ne connaît pas encore — l'appel échoue proprement, le modèle reçoit une erreur |
| **B avant A** | la cible connaît un tool que la Gateway n'expose pas — sans effet **sauf** si le changement portait sur une **classe** ou un **schéma** : la cible applique alors des règles que le catalogue exposé ne reflète plus |

**La seconde fenêtre est celle qui compte.** Un tool dont la classe passe de `read` à `mutating` dans
le manifeste devient exigeant côté cible dès B, mais reste annoncé comme `read` par la Gateway
jusqu'à A. Le sens de cette divergence est heureusement le bon — la cible est plus stricte que le
catalogue, jamais l'inverse, puisque la résolution de classe est fail-closed (§3.3). C'est ce qui
rend l'ordre B → A **préférable** et non seulement acceptable.

D'où la règle d'exploitation, dont l'application appartient à `V2-LLD-008` :

> **La cible est déployée avant le catalogue Gateway. Un retrait de tool suit l'ordre inverse : le
> catalogue d'abord, la cible ensuite.**

La règle de garde B2 (§16.2) vérifie la cohérence du plan ; elle ne vérifie pas cet ordre, qui est
une propriété du pipeline et non du plan. C'est la raison pour laquelle la validation de schéma reste
présente **dans la cible** (§4.1) : elle est le filet de la fenêtre de divergence.

---

## 4. Schémas d'arguments et injection d'identité

### 4.1 Validation stricte, et où elle a lieu

La validation du schéma a lieu **en deux points**, et la seconde n'est pas une duplication de la
première : la Gateway valide ce qu'elle transporte contre le schéma publié, la cible valide ce
qu'elle exécute. La CAM Domaine 10 l'exige — « aucune couche ne suppose que la précédente a filtré
entièrement ».

| Contrôle | Effet d'un échec | Point qui refuse |
|---|---|---|
| Champ inconnu présent | refus — `_reject_unexpected`, repris de V1 | Gateway (`additionalProperties: false`), **et** cible |
| Champ requis absent | refus — `_require`, repris de V1 | Gateway, **et** cible |
| Type ou borne non respectés | refus | Gateway, **et** cible |
| Champ interdit présent (§4.2) | refus **et** événement de sécurité (§13.1) | idem — un champ interdit est un cas particulier de champ inconnu (C6) |

**La colonne de droite dit « et », jamais « ou ».** En nominal, un champ interdit est refusé par la
Gateway et n'atteint pas la cible ; c'est le chemin le plus probable et le plus rapide. La cible
refuse néanmoins le même champ, parce qu'elle ne peut pas supposer qu'elle a été appelée par une
Gateway correctement configurée. Un catalogue Gateway divergent du manifeste (§3.1, C7) est
précisément le scénario où la première validation manque — et §3.7 montre que ce scénario n'est pas
théorique.

La dernière ligne est la seule dont l'échec n'est pas une simple erreur de forme : un argument
d'identité dans un payload produit par le modèle est le symptôme d'une injection ou d'une dérive, et
il est journalisé comme tel — par celui des deux points qui l'a vu.

### 4.2 Champs interdits

Aucun schéma ne les déclare (C6), et leur présence à l'invocation est refusée.

```text
actorId, tenantId, subjectId, userId, ownerId,
roles, scopes, permissions,
cognitoToken, authorizationHeader, accessToken,
confirmationVerified,
toolName
```

Trois entrées demandent une justification.

**`confirmationVerified` est interdit — dans le catalogue V2.** C'est le mécanisme V1 que
`V2-ADR-014` remplace. Le laisser acceptable dans un tool V2 permettrait à un appel de porter une
attestation de confirmation dans son payload — précisément l'écart de canal que l'ADR ferme.

L'interdiction ne s'applique **pas rétroactivement aux tools V1** encore en service pendant la
bascule : `create_trip` et `update_trip` continuent d'exiger `confirmationVerified` jusqu'à leur
retrait, conformément à §1.8. Les deux régimes coexistent parce qu'ils portent sur des tools
différents — les tools V2 du §3.5 n'ont jamais accepté ce champ, les tools V1 ne l'ont jamais cessé.
Le retrait des seconds suit la preuve M1 (§15), jamais l'inverse.

**`toolName` est interdit** et l'est déjà par `runtime-contract.md §4`. La raison est en §4.4.

**`roles` et `scopes` sont interdits** en cohérence avec `V2-LLD-003 §3.2` : ils ne traversent pas la
frontière FastAPI → Runtime, ils ne traversent donc pas non plus Runtime → tool. Un tool qui aurait
besoin d'un rôle pour décider aurait besoin de le résoudre lui-même à partir de `trustedIdentity`,
ce que le périmètre V2 n'exige pas.

### 4.3 Injection d'identité — écrasement, pas fusion

`V2-ADR-006` l'exige : « Runtime et les tools écrasent toute identité présente dans les arguments du
modèle ». L'adapter injecte avant l'appel (`V2-LLD-003 §6.3`), et la cible relit l'identité depuis
le canal d'injection, jamais depuis les arguments métier.

```text
args produits par le modèle          {destination: "Lisbonne", actorId: "attaquant"}
        │
        │  ① injection : identité placée hors du dictionnaire d'arguments métier,
        │     écrasant tout homonyme — la valeur produite par le modèle est perdue
        ▼
        │  ② refus au schéma — actorId est un champ interdit (§4.2)
        │     refusé par la Gateway en nominal, par la cible sinon (§4.1)
        │     événement tool_forbidden_field émis par le point qui refuse
        ▼
cible                                identité = canal d'injection, exclusivement
```

**Écraser et refuser ne sont pas équivalents, et les deux sont retenus.** L'écrasement seul suffit à
la sûreté : la valeur produite par le modèle est perdue. Mais il est silencieux, et une tentative
d'injection d'identité est un signal qu'il serait dommage de perdre. Le refus au schéma rend
l'événement observable ; l'écrasement reste la garantie si un champ non listé apparaissait un jour.

### 4.4 Le nom du tool n'est pas un argument

La cible résout le tool appelé depuis le **contexte d'invocation**, jamais depuis le payload. Le
mécanisme existe déjà en V1 :

```python
# lambda_function_code.py — repris tel quel en V2
def _extract_tool_name(context: Any) -> str:
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    extended_name = custom.get("bedrockAgentCoreToolName", "")
    delimiter = "___"
    return (
        extended_name.split(delimiter, 1)[1]
        if delimiter in extended_name
        else extended_name
    )
```

**Pourquoi c'est structurant.** Si le nom du tool était un argument, une cible unique servant
plusieurs tools déciderait de la classe — donc de l'exigence de confirmation — à partir d'une valeur
produite par le modèle. Le modèle choisirait alors s'il doit être confirmé. En le lisant du contexte,
la cible tient son identité de la Gateway, qui la tient de sa propre configuration.

C'est la raison pour laquelle `toolName` figure aux champs interdits de `runtime-contract.md §4`, et
ce LLD ne fait que réaliser cette interdiction jusqu'à la cible.

---

## 5. La séquence d'une action mutante

### 5.1 Les quatre temps

`V2-ADR-014` fixe la séquence. Ce LLD en porte les contrats.

```text
1. Matérialisation                                          [ tool, ce LLD §5.2 ]
   modèle → Gateway → propose_create_trip
     valide, normalise, écrit la commande [ pending ], retourne commandId
     AUCUN effet de bord métier

2. Présentation                                    [ FastAPI, V2-LLD-010 pour le rendu ]
   FastAPI lit la commande stockée et rend le résumé, transmis en SSE
     le modèle ne rédige pas ce résumé

3. Confirmation                                             [ FastAPI, V2-LLD-005 §4.6 ]
   utilisateur → API Gateway → POST /api/v1/commands/{commandId}/confirm
     identité vérifiée, transition [ pending ] → [ confirmed ]
     le modèle n'est pas sur ce chemin

4. Exécution                                                [ tool, ce LLD §5.3 ]
   modèle → Gateway → execute_create_trip(commandId)
     charge la commande, applique [ confirmed ] → [ executed ]
     ET l'effet de bord, dans la MÊME transaction
```

Les temps 2 et 3 n'appartiennent pas à ce LLD. Ils sont reproduits parce que le contrat des temps 1
et 4 n'a de sens que dans leur enchaînement — et parce que le temps 3 est ce qui rend le mécanisme
non contournable par le modèle.

### 5.2 Tool de proposition — contrat

| Aspect | Règle |
|---|---|
| Entrée | arguments métier, schéma strict (§3.2) |
| Identité | injectée ; la commande porte l'identité qui l'a fait matérialiser |
| Sortie | `{ commandId }` — et rien d'autre |
| Effet de bord métier | **aucun** |
| État écrit | commande `pending` |
| Échec de validation | refus ; **aucune commande n'est écrite** |
| Quota | soumis au plafond de commandes `pending` par identité (`V2-LLD-005 §7.2`) |

**« Aucun effet de bord » est une règle de conception, pas une propriété acquise.** `V2-ADR-014` le
dit explicitement : un tool de préparation qui réserverait une ressource, enverrait une notification
ou consommerait un quota externe romprait la garantie centrale du mécanisme — celle qui veut qu'une
injection documentaire réussie produise au pire une proposition visible. La liste des effets interdits
à la matérialisation :

- aucune écriture dans un magasin métier ;
- aucune réservation, aucun verrou, aucun décompte de stock ;
- aucune notification, aucun message sortant ;
- aucun appel à un service tiers facturé à l'usage.

L'écriture de la commande elle-même n'est pas un effet de bord métier : elle est l'objet du tool, et
elle est bornée par le quota `pending` — ce qui empêche qu'une matérialisation en boucle devienne un
effet observable par saturation.

**Ce que « normalise » signifie.** Le tool ne se contente pas de valider : il produit la forme
canonique qui sera exécutée. Dates normalisées, chaînes coupées à leur borne, valeurs par défaut
appliquées. C'est cette forme qui est écrite dans la commande, et c'est elle qui sera présentée au
temps 2. Le résumé montré à l'utilisateur décrit donc ce qui s'exécutera, pas ce que le modèle a
proposé.

### 5.3 Tool d'exécution — contrat

| Aspect | Règle |
|---|---|
| Entrée | `{ commandId }` — seul argument accepté (C4) |
| Identité | injectée ; **doit** correspondre à celle qui porte la commande |
| Lecture | commande chargée en **lecture fortement cohérente** |
| État requis | `confirmed` ; tout autre état refuse, sauf `executed` (§7.2) |
| Transition | `confirmed` → `executed`, **conditionnelle**, dans la transaction de l'effet de bord |
| Sortie | résultat de l'effet de bord |
| Rejeu sur `executed` | résultat initial renvoyé, **aucun second effet de bord** |

**La lecture fortement cohérente n'est pas une optimisation de confort.** Une lecture éventuellement
cohérente peut renvoyer `pending` pour une commande confirmée il y a quelques millisecondes, et
produire un refus incompréhensible pour l'utilisateur qui vient de cliquer. Le pattern est repris de
V1 (`_read_idempotency(..., ConsistentRead=True)`), où il servait déjà à résoudre un rejeu sans
ambiguïté.

**Le contrôle d'identité à l'exécution est distinct de celui de la confirmation.** `V2-LLD-005 §4.6`
vérifie, au temps 3, que l'identité qui confirme est celle qui a matérialisé. Ce LLD vérifie, au
temps 4, que l'identité qui exécute est cette même identité. Les deux contrôles portent sur des
moments différents et aucun ne rend l'autre superflu : entre confirmation et exécution, la
conversation peut avoir changé de session, et rien n'établit *a priori* que l'identité injectée au
temps 4 est la même qu'au temps 1.

### 5.4 Ce que le tool d'exécution ignore

C'est la règle qui porte la garantie centrale de `V2-ADR-014`, et elle mérite d'être énoncée comme
une contrainte d'implémentation vérifiable :

> **Le tool d'exécution lit le contenu de l'action dans la commande stockée. Il n'existe aucun
> chemin par lequel un argument transmis à l'appel puisse influencer l'effet de bord.**

Le schéma ne laisse passer que `commandId` (C4), donc il n'y a rien d'autre à ignorer. La règle est
formulée malgré tout, parce qu'elle est ce qui doit rester vrai si le schéma évoluait : un
`commandId` plus un champ « pour information » suffirait à rouvrir l'écart si ce champ atteignait la
logique métier.

La conséquence, telle que l'ADR la formule : une divergence entre ce qui a été confirmé et ce qui est
exécuté n'est pas *détectée*, elle est **impossible à produire** — les deux désignent le même
enregistrement. La preuve M2 (§15) l'exerce en transmettant délibérément des arguments métier
différents à l'exécution ; le résultat attendu n'est pas « les arguments sont ignorés » mais « l'appel
est refusé au schéma », ce qui est strictement plus fort.

### 5.5 Comment FastAPI apprend qu'une commande existe

`V2-ADR-014` décrit le temps 2 — « FastAPI lit la commande stockée et rend le résumé » — sans dire
par quel moyen FastAPI apprend **quelle** commande lire. La question n'est pas de détail : elle
décide si le modèle est, ou non, sur le chemin de la présentation.

Deux chemins existent, et un seul est acceptable.

| Chemin | Verdict |
|---|---|
| Le modèle relaie le `commandId` dans sa réponse, FastAPI l'y lit | **refusé** |
| FastAPI interroge le magasin pour les commandes matérialisées sous l'opération courante | **retenu** |

**Pourquoi le premier chemin est refusé.** Il remet le modèle sur le chemin de l'autorisation, que
`V2-ADR-014` a précisément voulu lui retirer. Un modèle qui relaie un `commandId` peut relayer
**celui d'une commande antérieure** encore `pending` : l'utilisateur confirmerait alors une action
qu'il a bien matérialisée un jour, mais pas celle que le résumé du tour courant lui laisse attendre.
Le contrôle d'identité (I1) ne l'arrête pas — c'est la même identité. Le rendu serveur du résumé ne
l'arrête pas non plus, puisqu'il rendrait fidèlement la commande désignée. La substitution est
invisible.

**Le chemin retenu.** La commande porte l'`operationId` qui l'a matérialisée (invariant I9, §6.1).
`operationId` est un Business Correlation ID produit par FastAPI (`runtime-contract.md §3`), propagé
à Runtime et jamais produit par le modèle. À l'issue de l'invocation, FastAPI interroge le magasin
sur cet `operationId` :

```text
FastAPI génère operationId ──► Runtime ──► propose_* écrit la commande
                                              avec cet operationId
       ◄──────────────────────────────────────────┘
FastAPI relit le magasin par operationId
   0 commande  ⇒ rien à présenter
   1 commande  ⇒ résumé rendu depuis la commande stockée
   n commandes ⇒ n résumés, dans l'ordre de matérialisation
```

Le modèle n'intervient à aucun point de cette boucle : il a fait écrire la commande, il n'en
transmet pas la référence.

**La sortie du tool reste `{ commandId }`** (§5.2). Elle sert au modèle à enchaîner l'exécution au
temps 4, ce qui est légitime — au temps 4, une substitution de `commandId` échoue sur l'état
`pending` de la commande substituée, puisque seule la commande réellement confirmée est `confirmed`.
La différence entre les deux temps est là : au temps 2, une substitution est indétectable ; au temps
4, elle est refusée par l'état.

**Ce que ce LLD ne décide pas.** L'index par `operationId`, son coût et sa forme appartiennent à
`V2-LLD-006`, comme le reste du schéma (§6.2).

---

## 6. Le magasin de commandes — contrat consommé

### 6.1 Les invariants exigés

Ce LLD ne décrit pas la table. Il énonce ce qu'elle doit garantir pour que les contrats de §5 tiennent.
La réalisation appartient à `V2-LLD-006` — voir l'écart 1 (§1.7).

| # | Invariant | Origine | Conséquence si non tenu |
|---|---|---|---|
| I1 | Une commande porte l'identité qui l'a matérialisée, et cette identité est comparable à `trustedIdentity` | `V2-ADR-014` | La confirmation par un tiers connaissant le `commandId` devient possible |
| I2 | Une commande porte le tenant, et le tenant est vérifié à la confirmation comme à l'exécution | `V2-ADR-006` | Escalade horizontale entre tenants par référence de commande |
| I3 | La transition d'état est **conditionnelle** et atomique avec l'effet de bord | `V2-ADR-014` | Deux exécutions concurrentes aboutissent toutes deux (§6.3) |
| I4 | Deux fenêtres d'expiration distinctes : `pending` et `confirmed`, la seconde nettement plus courte, **portées par un horodatage explicite** et non par le seul TTL du magasin | `V2-ADR-014`, ce LLD | Une autorisation ancienne autorise encore (§6.4) |
| I5 | `executed` est terminal ; aucune transition n'en repart et aucune ne remonte | `V2-ADR-014` | Un rejeu produit un second effet de bord |
| I6 | Le résultat de l'exécution initiale est conservé et renvoyable | `V2-ADR-014` | Un rejeu ne peut pas répondre sans réexécuter |
| I7 | La rétention d'une commande `executed` couvre la fenêtre d'idempotence de la mutation portée | `V2-ADR-014`, précondition P3 | La purge rouvre la possibilité d'un second effet de bord (§7.4) |
| I8 | Le `commandId` est **opaque et non devinable** | ce LLD | Un identifiant énumérable transforme I1 en seul rempart |
| I9 | Une commande porte l'**`operationId`** qui l'a matérialisée, et est retrouvable par cette valeur | ce LLD §5.5 | FastAPI ne peut apprendre la commande à présenter que par le modèle — le temps 2 redevient contournable |

**I8 et I9 ne sont pas dans l'ADR** et méritent chacun leur justification.

L'ADR décrit le `commandId` comme « une référence opaque, inexploitable sans le magasin qui la résout
et sans l'identité qui l'a créée ». L'identité est le contrôle ; l'opacité est ce qui évite que ce
contrôle soit exercé des milliers de fois par énumération. Le format `cmd_` suivi de 32 caractères
hexadécimaux issus d'une source aléatoire cryptographique satisfait I8 ; sa réalisation appartient à
`V2-LLD-006`.

I9 est la conséquence de §5.5 : le temps 2 de la séquence n'est réalisable sans le modèle que si la
commande est retrouvable par une valeur que FastAPI possède déjà. `operationId` est cette valeur —
produit par FastAPI, propagé par `operationContext`, jamais produit par le modèle.

### 6.2 Ce que ce LLD ne décide pas

Table, clés de partition et de tri, attributs, index, valeurs des deux TTL, durée de rétention de
`executed`, chiffrement et sauvegarde : tout cela appartient à `V2-LLD-006`. La règle de §1.6
s'applique — les invariants ci-dessus sont le contrat, et ils ne portent aucune valeur.

### 6.3 Transition conditionnelle et effet de bord dans la même transaction

C'est le point de vérification du mécanisme, et la seule garantie du système.

```text
transaction unique
   ├── condition : commande[commandId].state == "confirmed"
   │                ET commande[commandId].actorId == identité injectée
   │                ET commande[commandId].tenantId == tenant injecté
   │                ET commande[commandId] non expirée
   │
   ├── écriture 1 : commande[commandId].state ← "executed"
   │                commande[commandId].result ← résultat
   │
   └── écriture 2 : EFFET DE BORD MÉTIER
                    (création ou mise à jour du voyage)

   échec de la condition ⇒ AUCUNE des deux écritures n'est appliquée
```

**« Vérifier puis écrire » n'est pas équivalent et n'est pas retenu.** Entre un contrôle et une
écriture subsiste une fenêtre pendant laquelle deux exécutions concurrentes du même `commandId`
passent toutes deux le contrôle. C'est le mode d'échec que `ADR-0007` §4 avait déjà résolu pour
l'idempotence par une transaction, et que `V2-ADR-014` refuse de réintroduire pour l'autorisation.
Le tool n'écrit donc pas *après avoir vérifié* : il écrit *sous condition*, et l'échec de la condition
annule l'effet de bord.

Le pattern candidat est `TransactWriteItems` avec `ConditionExpression`, déjà employé en V1
(`lambda_function_hardened.py`, `update_trip`). Sa disponibilité pour cette combinaison de tables est
la précondition P2 — la seule sans repli acceptable, levée depuis par la colocalisation décidée en
`V2-LLD-006 §5.3.3` (§1.3).

**Ce que l'échec de condition doit distinguer.** Un refus transactionnel ne dit pas *pourquoi* il a
échoué. Le tool relit donc l'état après échec, en lecture fortement cohérente, pour produire un code
d'erreur exploitable :

| État relu | Code | Sens pour l'utilisateur |
|---|---|---|
| `executed` | — | rejeu : le résultat initial est renvoyé (§7.2), pas une erreur |
| `pending` | `COMMAND_NOT_CONFIRMED` | l'action n'a pas été confirmée |
| `expired` | `COMMAND_EXPIRED` | l'autorisation a expiré ; il faut refaire la proposition |
| absent | `COMMAND_NOT_FOUND` | référence inconnue ou purgée |
| identité différente | `COMMAND_FORBIDDEN` | ne distingue pas « pas à vous » de « n'existe pas » |

La dernière ligne est délibérée : distinguer les deux cas donnerait à un appelant un oracle
d'existence sur les `commandId` d'autrui. Le code est le même, et seul le journal serveur porte la
distinction.

### 6.4 Le TTL fait le ménage, il n'applique pas la fenêtre

C'est l'erreur la plus facile à commettre sur ce mécanisme, et elle serait silencieuse.

Un TTL de magasin — celui de DynamoDB comme celui de la plupart des magasins — est une **suppression
différée**, pas une garantie d'invisibilité à l'échéance. L'élément reste lisible entre son échéance
et sa purge effective, et rien ne borne utilement ce délai à l'échelle d'une autorisation.

Il en résulte la règle suivante, portée par I4 :

> **L'expiration d'une commande est appliquée par une condition sur un horodatage explicite, évaluée
> dans la transaction d'exécution. Le TTL du magasin ne fait que supprimer les enregistrements
> devenus inutiles.**

```text
condition d'exécution (§6.3)
   ├── state == "confirmed"
   ├── actorId, tenantId == identité injectée
   └── confirmedExpiresAt > maintenant      ← l'expiration est ICI

TTL du magasin                              ← purge, sans effet sur l'autorisation
```

**Ce qu'une expiration reposant sur le TTL produirait.** Une commande `confirmed` dont la fenêtre
courte est écoulée resterait exécutable jusqu'à sa purge. La fenêtre réellement offerte serait celle
de la purge, pas celle de la configuration — et la propriété que `V2-ADR-014` attend de la fenêtre
courte, borner l'exécution après une annulation (§10.2), ne tiendrait plus.

L'état `expired` du §6.3 est donc un état **déduit** de l'horodatage à la relecture, pas
nécessairement un état écrit. Sa réalisation — attribut, index, écriture ou déduction — appartient à
`V2-LLD-006`.

---

## 7. Idempotence

### 7.1 Deux régimes, et pourquoi ils ne fusionnent pas

`V2-ADR-014` sépare deux questions que le corpus confondait :

| Question | Mécanisme | Portée V2 |
|---|---|---|
| « cette action a-t-elle été autorisée, et laquelle ? » | **commande** | mutations `Trips` par tool |
| « cette action a-t-elle déjà été faite ? » | commande (état `executed`) **ou** ledger | commande pour les mutations par tool ; ledger pour le reste |

L'ADR décide que l'état `executed` **tient lieu d'enregistrement d'idempotence** pour la mutation
qu'il porte. Ce n'est pas une coïncidence d'implémentation : c'est une conséquence assumée du fait
qu'une commande est déjà l'objet durable qui identifie la mutation.

Il en résulte une règle nette, qui est l'objet de l'écart 2 (§1.7) :

> **Une mutation passée par une commande n'écrit aucune entrée dans le ledger d'idempotence.**

### 7.2 Rejeu d'une commande `executed`

Un rejeu n'est pas une erreur. `V2-ADR-014` le formule sans ambiguïté : « un rejeu ne produit pas un
second effet de bord et ne renvoie pas une erreur d'autorisation, mais le résultat de l'exécution
initiale ».

```text
execute_create_trip(commandId)
   │
   ├── transaction conditionnelle → échec (state == "executed", pas "confirmed")
   │
   ├── relecture fortement cohérente → state == "executed"
   │
   └── retour : commande.result          ← résultat initial, aucun nouvel effet
```

**Pourquoi renvoyer le résultat plutôt qu'une erreur.** Le rejeu le plus fréquent n'est pas une
attaque : c'est un retry légitime après un timeout côté appelant, où la première tentative a
peut-être abouti. Répondre par une erreur d'autorisation forcerait l'appelant à traiter comme un
échec une opération réussie. C'est le comportement que le pattern V1 avait déjà retenu, et il est
reconduit.

### 7.3 Le ledger d'idempotence résiduel

Le ledger de `V2-LLD-006 §5` reste en usage pour les opérations **sans commande** :

| Opération | Pourquoi elle n'a pas de commande |
|---|---|
| Upload documentaire | déclenché par l'utilisateur via API REST, sans mandataire interposé (`V2-ADR-014` §Classification des actions) |
| Déclenchement d'ingestion KB | conséquence serveur d'un upload, jamais une intention du modèle |

Ce sont les deux seules portées qui subsistent. Le maintien des mutations `Trips` dans cette liste est
l'écart 2.

### 7.4 Rétention — la borne que les deux TTL ne donnent pas

`V2-ADR-014` distingue trois durées qu'il serait facile de confondre :

| Durée | Ce qu'elle borne | Ordre de grandeur relatif |
|---|---|---|
| TTL `pending` | la validité d'une proposition non confirmée | la plus longue des deux fenêtres d'autorisation |
| TTL `confirmed` | la validité d'une autorisation non exécutée | **nettement plus courte** que la précédente |
| Rétention `executed` | la garantie de non-rejeu | ne se déduit ni de l'une ni de l'autre |

**La troisième est celle qu'on oublie.** Les deux premières bornent l'autorisation : passé le délai,
plus rien ne s'exécute, et c'est la posture sûre. La troisième borne une garantie de sens inverse :
tant que la commande `executed` est résoluble, un rejeu est refusé ; dès qu'elle est purgée, le même
`commandId` devient inconnu — et si l'appelant réessaie encore, plus rien n'atteste que l'effet a
déjà eu lieu.

D'où l'invariant I7, et le repli nommé par la précondition P3 : si la rétention retenue ne peut pas
couvrir la fenêtre d'idempotence exigée, la réponse conforme est de conserver au-delà une **entrée
réduite valant enregistrement de non-rejeu** — identité, état terminal, horodatage, sans le contenu
de la commande ni son résultat. Cette entrée réduite ne permet plus de renvoyer le résultat initial :
elle permet de refuser un second effet de bord, ce qui est la propriété à préserver.

**Ce qui n'est jamais acceptable :** laisser la commande disparaître en silence. `V2-ADR-014` le dit
en ces termes, et la preuve M5 (§15) l'exerce en fin de fenêtre.

---

## 8. Retry et disjoncteur

### 8.1 Retry avant effet de bord uniquement

La règle du catalogue LLD (`LLD-V2-INDEX-FR.md`, portée `V2-LLD-004`) est « retry avant effet de bord
uniquement ». Elle se réalise ainsi :

```text
   propose_*                     execute_*
      │                              │
      │  retry libre                 │  retry AVANT soumission de la transaction : OUI
      │  (aucun effet de bord)       │  retry APRÈS soumission : JAMAIS
      │                              │
      ▼                              ▼
   commande pending            transaction conditionnelle
                                     │
                                     └── issue inconnue ⇒ RÉSOUDRE, ne pas réessayer (§8.4)
```

**Un tool de proposition est librement rejouable.** Il n'a aucun effet de bord ; au pire un rejeu
crée une seconde commande `pending`, que l'expiration nettoie et que le quota borne. Ce n'est pas
gratuit, mais ce n'est pas dangereux.

**Un tool d'exécution ne se rejoue pas après soumission.** Non parce que ce serait dangereux — la
transition conditionnelle le rend sûr — mais parce que ce serait *inutile et trompeur* : la
transaction a peut-être abouti, et un second appel renverrait le résultat initial en donnant
l'impression d'une seconde tentative. La résolution correcte est en §8.4.

### 8.2 Classification des erreurs

Toutes les erreurs ne sont pas des pannes, et la distinction gouverne à la fois le retry et le
disjoncteur.

| Classe | Exemples | Retry | Compte pour le disjoncteur |
|---|---|---|---|
| **Refus d'autorisation** | Gateway refuse l'appel ; `COMMAND_FORBIDDEN` | non | **non** |
| **Refus de validation** | champ inconnu, borne dépassée, champ interdit | non | **non** |
| **Refus d'état** | `COMMAND_NOT_CONFIRMED`, `COMMAND_EXPIRED` | non | **non** |
| **Indisponibilité transitoire** | throttling, timeout de la cible, erreur 5xx | oui, borné | oui |
| **Issue inconnue** | timeout après soumission de la transaction | **non** (§8.4) | oui |

**Un refus d'autorisation n'ouvre jamais le disjoncteur.** C'est l'erreur de conception classique sur
ce type de mécanisme : un utilisateur qui déclenche dix refus légitimes ferait basculer le tool en
panne pour tout le monde. Un refus est un fonctionnement nominal de la Gateway ; seule une
indisponibilité est une panne.

### 8.3 Disjoncteur

| Aspect | Règle |
|---|---|
| Granularité | **par tool**, pas par Gateway — un tool défaillant n'éteint pas les autres |
| Ouverture | après N échecs consécutifs de classe « indisponibilité » ou « issue inconnue » |
| État ouvert | l'appel échoue immédiatement, sans atteindre la Gateway |
| Demi-ouvert | un appel de sonde après un délai ; succès ⇒ fermeture, échec ⇒ réouverture |
| Portée temporelle | l'état est propre à une instance de service, non partagé |

**L'état n'est pas partagé, et c'est un choix.** Un disjoncteur distribué exigerait un magasin
partagé sur le chemin chaud de chaque appel de tool — un coût de latence et une dépendance
supplémentaire pour protéger un chemin déjà borné par la deadline. Chaque instance apprend
séparément ; la convergence est plus lente et acceptée.

**Ce que le disjoncteur ne protège pas.** Il protège la latence du tour en cours, pas l'intégrité :
celle-ci est portée par la transition conditionnelle. Un disjoncteur ouvert pendant qu'une commande
est `confirmed` laisse simplement cette commande expirer — sans effet, par I4.

Les valeurs de N, du délai de sonde et du timeout par appel sont des paramètres de configuration
(§14), jamais des constantes du code — reprise de l'exigence de `V2-ADR-005` sur les budgets.

### 8.4 Issue inconnue — résoudre, pas réessayer

C'est le cas le plus délicat du chemin, et la précondition P4 le rend probable plutôt que théorique :
la transaction d'exécution est soumise, et la réponse n'arrive pas avant la deadline propagée.

```text
   transaction soumise, pas de réponse
            │
            │   ✗ retry            ← produirait un appel dont l'issue est
            │                         indiscernable de la première
            │
            └── ✓ résolution par lecture fortement cohérente de la commande
                     │
                     ├── state == "executed"  ⇒ la transaction a abouti
                     │                            → renvoyer commande.result
                     │
                     └── state == "confirmed" ⇒ la transaction n'a pas commis
                                                  → un nouvel appel est sûr
```

**La lecture d'état est la réponse, parce que la commande est le seul témoin fiable.** Ni le code de
retour, ni un timeout, ni un journal applicatif ne disent si l'écriture a été appliquée. L'état de la
commande le dit, et il le dit de manière atomique avec l'effet de bord — c'est précisément ce que I3
garantit.

Si la deadline est déjà dépassée au moment de la résolution, le tour se termine sans réponse et la
commande reste dans son état réel. Une reprise ultérieure de la conversation ne l'exécute pas : la
fenêtre courte de `confirmed` (I4) la rend inexécutable, conformément à `V2-ADR-014` §Interaction avec
l'annulation.

---

## 9. Autorisation Gateway

### 9.1 Ce que la Gateway décide

`Tool Authorization` est sa capacité (CAM Domaine 7). Ce LLD n'en implémente rien — il en fixe la
forme attendue.

| Élément | Règle |
|---|---|
| Principal | le rôle IAM du Runtime (identité 1 de §2.3) |
| Ressource | la cible du tool, désignée par la configuration de la Gateway |
| Décision | par tool, pas par catalogue entier |
| Ce qui n'entre pas dans la décision | `trustedIdentity` — elle n'est pas un principal (§2.3) |

**La Gateway autorise un appelant à invoquer un tool ; elle n'autorise pas un utilisateur à agir sur
une ressource.** La seconde décision appartient au tool, qui construit ses clés à partir de
`trustedIdentity` et applique le partitionnement de `V2-LLD-005 §4.8`. Confondre les deux
conduirait à une Gateway qui devrait connaître le modèle d'autorisation métier — une violation de
P-01 par accumulation.

**Droits attendus par principal.** Le détail des politiques appartient à `V2-LLD-001` (inventaire
IAM de la plateforme) ; ce LLD fixe ce que chaque rôle doit et ne doit **pas** pouvoir, parce que
c'est de ces interdictions que dépendent les propriétés du §5.

| Principal | Doit pouvoir | Ne doit **pas** pouvoir |
|---|---|---|
| Rôle du Runtime | invoquer la Gateway | invoquer une cible de tool directement (S1) ; lire ou écrire le magasin de commandes ; lire le magasin métier |
| Rôle de la cible de **proposition** | lire le magasin métier pour valider ; **écrire dans le magasin de commandes** | **toute écriture dans le magasin métier** — c'est ce qui rend l'absence d'effet de bord vérifiable par l'IAM (§9.2) |
| Rôle de la cible d'**exécution** | lire et transitionner une commande ; écrire dans le magasin métier, dans la même transaction | créer une commande — la matérialisation n'est pas son rôle |
| Rôle de FastAPI | lire le magasin de commandes (temps 2) ; transitionner `pending` → `confirmed` (temps 3) | invoquer un tool ni la Gateway (CAM Domaine 7) ; transitionner vers `executed` |

La dernière colonne porte l'essentiel. Trois interdictions y sont structurantes : le Runtime sans
accès direct aux cibles rend S1 vérifiable par l'IAM plutôt que par revue ; la proposition sans droit
d'écriture métier rend la garantie de §5.2 impossible à violer ; FastAPI sans droit de transition
vers `executed` garantit que l'idempotence de §7.1 ne peut être court-circuitée hors de la
transaction du tool.

**Resource policy de la Gateway.** Elle n'autorise que le rôle du Runtime comme principal. Aucun
principal humain, aucun rôle de CI et aucun rôle de FastAPI n'y figure — un accès de dépannage
consenti « le temps d'un incident » est un contournement permanent de l'autorisation.

### 9.2 Politiques distinctes proposition / exécution

`V2-ADR-014` justifie la séparation en deux tools notamment par la possibilité de « politiques
d'autorisation distinctes au niveau de la Gateway ». C'est la précondition P1.

**Si P1 est satisfaite,** les deux tools portent des politiques distinctes à la Gateway : la
matérialisation peut être ouverte plus largement que l'exécution, et un retrait d'urgence de la
capacité d'exécution ne prive pas le système de sa capacité à proposer.

**Si P1 n'est pas satisfaite,** le repli déplace la distinction vers l'IAM de la cible : deux
fonctions cibles distinctes, deux rôles d'exécution, la fonction de proposition n'ayant aucun droit
d'écriture sur le magasin métier. Le repli est plus lourd — deux artefacts de déploiement au lieu
d'un — mais il a une propriété que la politique Gateway n'a pas : l'absence d'effet de bord de la
matérialisation devient **prouvable par l'IAM**, pas seulement par inspection du catalogue.

**Le « repli » est en réalité la meilleure option, et il est retenu comme cible.** Une politique
Gateway distingue deux tools par configuration ; deux cibles à rôles distincts les distinguent par
capacité. Dans le second cas, l'absence d'effet de bord de la matérialisation cesse d'être une
propriété à faire respecter et devient une propriété **impossible à violer** — la fonction de
proposition n'a aucun droit d'écriture sur le magasin métier, quelle que soit son implémentation.
C'est le même raisonnement que celui de C4 sur le schéma d'exécution (§3.6), appliqué à l'IAM.

La décision est donc : **deux cibles distinctes, quelle que soit l'issue de P1.** Si P1 est
satisfaite, les politiques Gateway s'y ajoutent en défense supplémentaire ; si elle ne l'est pas, la
séparation tient sans elles. P1 cesse ainsi d'être bloquante pour la séparation — elle ne
conditionne plus qu'un contrôle additionnel.

Le coût est un second artefact de déploiement. Il est assumé : c'est le prix d'un contrôle vérifiable
par l'IAM plutôt que par la lecture d'une configuration.

### 9.3 Autorisation Gateway et filtre d'exposition — deux contrôles, pas deux implémentations

`V2-LLD-003 §6.1` a déjà établi la distinction ; ce LLD la reprend du côté aval pour que les deux
documents ne divergent pas.

| Contrôle | Question | Propriétaire | Ce qu'il ne fait pas |
|---|---|---|---|
| Filtre d'exposition (`tool_allowlist`) | « ce tool est-il **présentable** au modèle pour ce parcours ? » | Runtime — `V2-LLD-003 §6.2` | il ne décide aucune autorisation |
| `Tool Authorization` | « cet appelant peut-il **invoquer** ce tool ? » | Gateway — ce LLD §9.1 | elle ne restreint pas ce que le modèle voit |

**Le filtre est la première ligne, l'autorisation est la dernière.** Un filtre d'exposition contourné
— par dérive du modèle ou par injection dans le contenu documentaire — rencontre encore
l'autorisation Gateway. Une autorisation Gateway permissive rencontre encore la transition
conditionnelle du §6.3 si le tool est mutant. La CAM Domaine 10 exige cette superposition : « aucune
couche ne suppose que la précédente a filtré entièrement ».

La preuve S4 (§15) exerce précisément ce point : un appel de tool émis **en contournant le filtre
d'exposition** doit rencontrer l'autorisation Gateway, et non aboutir.

---

## 10. Annulation

### 10.1 La fenêtre non annulable est l'exécution, pas l'appel de tool

`V2-ADR-011` renvoie ici pour la garantie d'idempotence. La décision de `V2-ADR-014` réduit la
fenêtre que l'ADR-011 décrivait :

| Phase | Annulable ? | Motif |
|---|---|---|
| Avant `propose_*` | oui | point d'annulation avant émission d'un appel de tool (`V2-ADR-011`) |
| Pendant `propose_*` | **oui** | aucun effet de bord ; au pire une commande `pending` orpheline, que l'expiration nettoie |
| Entre proposition et confirmation | oui | rien n'est engagé |
| Entre confirmation et exécution | oui | la commande reste `confirmed` et expire sans effet |
| `execute_*`, **avant** soumission de la transaction | **oui** | résolution, lecture et construction n'écrivent rien |
| `execute_*`, **pendant** la transaction | **non** | transition et effet de bord indissociables |

C'est l'objet de l'écart 4 (§1.7). `V2-ADR-011` prescrit que « l'annulation attend la fin de
**l'appel en cours** » : appliquée à `execute_*`, cette règle immobilise l'annulation pendant les
deux dernières lignes du tableau, alors que seule la dernière l'exige. La fenêtre réelle est la
transaction — nettement plus courte qu'un appel de tool réalisant validation, décision et écriture en
une fois, et c'est la réduction que `V2-ADR-014` revendique.

**Ce que l'avant-dernière ligne coûte si on la traite comme non annulable.** Rien de dangereux : une
fenêtre décrite trop large est une posture conservatrice. Mais elle est payée en latence perçue —
l'utilisateur qui annule attend la fin d'un appel dont l'essentiel n'écrit rien — et elle rend le
raisonnement d'`V2-ADR-014` sur la réduction de fenêtre inapplicable en l'état.

### 10.2 Annulation entre confirmation et exécution

C'est le cas que `V2-ADR-014` traite explicitement, et il ne demande aucun mécanisme nouveau.

```text
commande [ confirmed ]
      │
      │   annulation de l'opération (V2-ADR-011, registre d'opérations)
      │
      ├── la commande N'EST PAS transitionnée — aucun état `cancelled`
      │
      └── la fenêtre courte de `confirmed` (I4) la rend inexécutable
```

**Aucun état `cancelled` n'est introduit.** L'ADR en donne la raison : il n'apporterait rien qu'une
expiration ne garantisse déjà, et sa propagation exigerait de coupler le registre d'opérations de
`V2-ADR-011` au magasin de commandes — un couplage entre deux mécanismes qui n'ont aujourd'hui aucune
dépendance.

**Ce qui doit rester vrai :** une commande confirmée mais non exécutée à l'issue d'une annulation ne
doit pas pouvoir être exécutée par une reprise ultérieure de la conversation. C'est la fenêtre courte
de `confirmed` qui borne ce risque, et c'est la raison pour laquelle I4 exige qu'elle soit
« nettement plus courte » — une exigence qualitative que `V2-LLD-006` traduira en valeur.

La preuve M8 (§15) l'exerce : annulation après confirmation, puis reprise de la conversation ; aucun
effet de bord ne survient.

---

## 11. Budgets

### 11.1 Imputation à `maxToolCalls`

`V2-ADR-014` §Conséquences le pose : « une action mutante consomme **deux appels de tool au lieu
d'un**, ce qui s'impute au budget `maxToolCalls` de `V2-ADR-005` : son calibrage doit en tenir
compte, faute de quoi une conversation comportant plusieurs mutations épuiserait le budget plus tôt
qu'en V1 ».

Ce LLD énonce l'imputation ; la **valeur** de `maxToolCalls` appartient à `V2-LLD-003 §5` (règle
§1.6).

| Événement | Coût imputé |
|---|---|
| Appel `read` | 1 |
| `propose_*` | 1 |
| `execute_*` | 1 |
| **Mutation complète** | **2** |
| `propose_*` dont la commande n'est jamais confirmée | **1** — le budget est consommé, l'effet ne l'est pas |
| Rejeu d'une commande `executed` | 1 — un appel reste un appel, même sans effet de bord |

**La quatrième ligne est celle qui surprend.** Une conversation où l'utilisateur hésite et laisse
expirer trois propositions a consommé trois appels de tool sans qu'aucune mutation n'ait eu lieu.
C'est correct : le budget borne le travail du système, pas le nombre d'effets produits. Mais cela
signifie qu'un budget calibré sur « N mutations » doit être calibré sur « N propositions plus N
exécutions plus les abandons ».

### 11.2 Deadline de la transaction d'exécution

La précondition P4 porte sur ce point : la latence cumulée de la transition conditionnelle et de
l'effet de bord s'impute au tour en cours et doit tenir dans `deadlineEpochMs`
(`runtime-contract.md §3`).

| Appel | Enjeu de deadline |
|---|---|
| `propose_*` | faible — validation, normalisation, une écriture |
| Confirmation (temps 3) | **aucun** — appel court hors du tour conversationnel |
| `execute_*` | **le seul enjeu réel** — transaction indissociable, dont l'interruption n'est pas une option |

Le comportement en cas de dépassement est en §8.4 : résolution par lecture d'état, jamais retry.
La valeur du budget résiduel minimal avant émission d'un appel de tool — le pendant V2 de
`MIN_TOOL_DEADLINE_REMAINING_MS` de la V1 — appartient à `V2-LLD-003 §5`.

---

## 12. Sécurité du chemin tool

### 12.1 Menaces propres à ce chemin

| # | Menace | Contrôle | Section |
|---|---|---|---|
| T1 | Le modèle produit une identité dans les arguments | champ interdit au schéma **et** écrasement à l'injection | §4.2, §4.3 |
| T2 | Le modèle nomme lui-même le tool appelé | le nom vient du contexte d'invocation, jamais du payload | §4.4 |
| T3 | Injection documentaire demandant une mutation | le modèle peut matérialiser, jamais confirmer | §12.2 |
| T4 | Divergence entre le contenu confirmé et le contenu exécuté | impossible à produire — le schéma d'exécution n'accepte que `commandId` | §5.4 |
| T5 | Confirmation par un tiers connaissant le `commandId` | identité vérifiée à la confirmation et à l'exécution ; `commandId` opaque | §5.3, I1, I8 |
| T6 | Rejeu d'une mutation déjà appliquée | transition conditionnelle ; `executed` terminal | §6.3, §7.2 |
| T7 | Deux exécutions concurrentes du même `commandId` | atomicité — une seule aboutit | §6.3 |
| T8 | Oubli de déclaration de classe rendant un tool exécutable sans confirmation | défaut `mutating`, contrôle C1 en CI | §3.3, §3.6 |
| T9 | Saturation du magasin par matérialisation en boucle | quota de commandes `pending` par identité | `V2-LLD-005 §7.2` |
| T10 | Exfiltration par egress d'une cible de tool | aucun egress sortant non contrôlé (E1) | §12.3 |
| T11 | Exfiltration par sur-restitution : un tool renvoie plus que ce que l'identité peut lire | partitionnement appliqué au retour du tool (E2) | §12.3 |
| T12 | Divergence de catalogue par ordre de déploiement | cible déployée avant le catalogue ; validation de schéma conservée dans la cible | §3.7, §4.1 |

### 12.2 Injection indirecte — ce qui est fermé, et ce qui ne l'est pas

`V2-ADR-014` énonce la propriété obtenue : « une injection réussie produit au pire une proposition
d'action visible par l'utilisateur, jamais un effet de bord ». Ce LLD précise ce qui la porte et ce
qui la romprait.

**Ce qui la porte.** La confirmation n'est pas un appel dont le modèle dispose : elle arrive par un
canal authentifié auquel il n'a pas accès (`V2-LLD-005 §4.6`). Aucun tool du catalogue ne l'atteint,
et l'inventaire §3.5 est exhaustif — c'est ce qui rend l'affirmation vérifiable plutôt que déclarative.

**Ce qui la romprait.**

- Un tool de proposition avec un effet observable (§5.2). C'est la faille la plus discrète : le
  mécanisme paraîtrait intact alors que la matérialisation aurait déjà produit l'effet recherché.
- Un tool exposé à la Gateway qui atteindrait l'endpoint de confirmation. Le catalogue §3.5 ne
  contient rien de tel, et l'ajouter serait un changement à traiter comme un amendement d'ADR.
- Un résumé de commande rédigé par le modèle. `V2-ADR-014` l'interdit et `V2-LLD-010` en porte la
  réalisation : le résumé est rendu par le serveur depuis la commande stockée.

**Ce qui n'est pas fermé.** Le modèle reste influençable : un document peut le conduire à proposer
une action absurde ou hostile. L'utilisateur voit alors une proposition qu'il n'a pas demandée. C'est
un problème d'expérience et de confiance, pas d'intégrité — et il est traité par le rendu serveur du
résumé, qui garantit que ce que l'utilisateur lit est ce qui s'exécuterait.

### 12.3 Exfiltration et egress

`V2-ADR-002` et la Charte §6 nomment l'exfiltration par tool. Deux invariants sont énoncés ici ; leur
réalisation appartient à `V2-LLD-001` (placement réseau) et `V2-LLD-005` (posture egress).

> **E1 — Aucune cible de tool n'a d'egress sortant non contrôlé.** Un tool qui pourrait joindre un
> hôte arbitraire transformerait tout argument transmis par le modèle en canal d'exfiltration, quel
> que soit le contenu de son schéma.

> **E2 — Un tool ne retourne que ce que l'identité appelante est autorisée à lire.** Le
> partitionnement de `V2-LLD-005 §4.8` s'applique aux tools comme à toute autre voie d'accès ; un
> tool n'est pas un contournement de l'autorisation métier au motif qu'il s'exécute côté serveur.

E2 mérite d'être souligné : le résultat d'un tool retourne au modèle, donc au contexte de la
conversation, donc potentiellement à l'utilisateur. Un tool trop généreux dans ce qu'il renvoie est
une fuite, même sans intention.

---

## 13. Observabilité

### 13.1 Événements

Le catalogue d'événements V1 est **étendu, pas remplacé** (`V2-ADR-008` §Conséquences).

| Événement | Émis quand | Attributs |
|---|---|---|
| `tool_invocation` | tout appel de tool | nom, classe, rôle, version, durée, issue |
| `tool_denied_exposure` | refus du filtre d'exposition | nom demandé — signal de dérive ou d'injection (`V2-LLD-003 §6.2`) |
| `tool_denied_authorization` | refus de la Gateway | nom demandé |
| `tool_schema_rejected` | champ inconnu ou borne dépassée | nom du champ, jamais sa valeur (§13.2) |
| `tool_forbidden_field` | **champ interdit présent** (§4.2) | nom du champ — **événement de sécurité** |
| `command_materialized` | commande écrite en `pending` | `commandId` hashé, tool |
| `command_execution_conflict` | échec de la condition transactionnelle | état relu, code d'erreur (§6.3) |
| `command_replayed` | rejeu d'une commande `executed` | `commandId` hashé |
| `command_unknown_outcome` | issue inconnue résolue par lecture (§8.4) | état résolu |
| `tool_circuit_opened` / `tool_circuit_closed` | changement d'état du disjoncteur | nom du tool |

`tool_forbidden_field` est le seul de niveau sécurité : les autres refus sont des fonctionnements
nominaux, celui-ci est le symptôme d'une identité produite par le modèle.

**Propagation de trace.** `traceparent` est propagé de FastAPI jusqu'aux tools (`V2-ADR-008`). Si la
propagation native à travers Runtime n'est pas supportée — question ouverte renvoyée à `V2-LLD-007`
par l'ADR et reprise par `V2-LLD-003 §10` — la corrélation de repli s'appuie sur `operationId` et
`requestId`, portés par `operationContext`.

### 13.2 Redaction

`V2-ADR-008` §Redaction s'applique intégralement. Deux règles propres au chemin tool s'y ajoutent :

| Valeur | Journalisée ? |
|---|---|
| Nom du tool, classe, rôle, version | oui, en clair |
| Nom d'un champ refusé | oui |
| **Valeur** d'un argument métier | **non** — jamais, quel que soit le niveau de log |
| `commandId` | hashé (`safe_hash`, `V2-LLD-005 §3.2`) |
| Contenu de la commande | **non** |
| Résultat d'un tool | **non** |

**Pourquoi le contenu de la commande n'est jamais journalisé.** Il porte l'intention métier de
l'utilisateur — destination, dates, préférences. Le journaliser ferait du journal d'exploitation un
second magasin de données personnelles, hors du périmètre d'effacement de `V2-LLD-006 §8.4`. Le
`commandId` hashé suffit à corréler ; la commande elle-même est lisible dans son magasin, sous
autorisation.

---

## 14. Configuration

Aucune de ces valeurs n'est une constante du code — reprise de l'exigence de `V2-ADR-005`.

| Paramètre | Portée | Propriétaire de la valeur |
|---|---|---|
| `tool_call_timeout_ms` | par appel de tool | ce LLD, §16.1 |
| `tool_retry_max_attempts` | classe « indisponibilité » uniquement (§8.2) | ce LLD, §16.1 |
| `circuit_breaker_failure_threshold` | N échecs consécutifs (§8.3) | ce LLD, §16.1 |
| `circuit_breaker_probe_delay_ms` | délai avant sonde demi-ouverte | ce LLD, §16.1 |
| `mcp_protocol_version` | version de protocole acceptée, sans repli silencieux (§3.4) | ce LLD, §16.1 |
| `command_pending_window_minutes` | fenêtre `pending` (I4) | **`V2-LLD-006 §5.3.2`** |
| `command_confirmed_window_seconds` | fenêtre `confirmed` (I4) | **`V2-LLD-006 §5.3.2`** |
| `command_executed_retention_days` | rétention de non-rejeu (I7) | **`V2-LLD-006 §5.3.2`** |
| `max_pending_commands_per_actor` | quota (T9) | **`V2-LLD-005 §7.2`** |
| `maxToolCalls` | budget d'invocation | **`V2-LLD-003 §5`** |

Les quatre premières lignes sont les seules valeurs que ce LLD possède. Les cinq suivantes sont
listées pour rendre le contrat lisible d'un seul endroit, et **leur valeur n'est pas reproduite ici**
(§1.6).

**Invariant inter-paramètres.** La fenêtre `confirmed` doit être strictement inférieure à la fenêtre
`pending` (I4). Les deux paramètres ne portant pas la même unité — `command_confirmed_window_seconds`
et `command_pending_window_minutes` — la comparaison se fait après conversion dans une unité commune,
et non entre les valeurs brutes. La vérification appartient à la règle de garde de `V2-LLD-006` ;
elle est énoncée ici parce que c'est ce LLD qui en porte le motif — une autorisation ancienne
n'autorise plus rien.

Les noms ci-dessus sont ceux que `V2-LLD-006 §5.3.2` déclare. Une rédaction antérieure de ce tableau
en portait d'autres (`command_pending_ttl_seconds`, `command_confirmed_ttl_seconds`,
`command_executed_retention_seconds`), avec des unités différentes de celles du propriétaire : deux
jeux de noms pour trois paramètres uniques, dont un seul existe au plan.

---

## 15. Tests et preuves

Les preuves `M*` portent sur le mécanisme de commande, les `S*` sur le contrat de tool. Leur
ordonnancement dans la pyramide appartient à `V2-LLD-009`.

| # | Preuve | Origine |
|---|---|---|
| M1 | **Exécution sans commande confirmée refusée**, y compris avec identité valide et payload bien formé. Vérifie aussi que `confirmationVerified` dans le payload ne change rien (§4.2) | `V2-ADR-014` — preuve principale |
| M2 | Arguments métier transmis à l'exécution : **refusés au schéma** (C4), a fortiori sans effet | `V2-ADR-014` |
| M3 | Confirmation par une identité autre que celle qui a matérialisé : refusée, `commandId` valide | `V2-ADR-014` |
| M4 | Rejeu d'une commande `executed` : aucun second effet de bord, **résultat initial renvoyé** | `V2-ADR-014`, §7.2 |
| M5 | Rejeu **en fin de fenêtre de rétention** : toujours pas de second effet de bord (I7, repli P3) | `V2-ADR-014`, §7.4 |
| M6 | Deux exécutions **concurrentes** du même `commandId` : une seule aboutit, aucun état partiel | `V2-ADR-014`, §6.3 |
| M7 | Expiration : `pending` non confirmée et `confirmed` non exécutée deviennent inexécutables | `V2-ADR-014`, I4 |
| M8 | Annulation entre confirmation et exécution : la commande expire sans effet ; une reprise de conversation ne l'exécute pas | `V2-ADR-011`, §10.2 |
| M9 | Injection documentaire demandant une mutation : au plus une commande `pending`, jamais d'effet de bord | `V2-ADR-014`, §12.2 |
| M10 | Tool sans classe déclarée : traité comme `mutating`, refusé — **et** rejeté en CI par C1 | `V2-ADR-014`, §3.3 |
| M11 | Issue inconnue simulée (timeout après soumission) : résolution par lecture d'état, jamais retry ; aucun double effet | §8.4 |
| M12 | Matérialisation : **aucune écriture métier** observée, vérifié par inspection du magasin après appel | §5.2 |
| M13 | **Le résumé du temps 2 ne dépend pas du modèle** : la commande est retrouvée par `operationId` ; une réponse de modèle mentionnant un `commandId` d'une commande antérieure ne change pas ce qui est présenté | §5.5, I9 |
| M14 | **Expiration non purgée** : une commande `confirmed` dont l'horodatage est dépassé mais dont le TTL n'a pas encore purgé l'enregistrement est **refusée** à l'exécution | §6.4, I4 |
| M15 | Le rôle de la cible de proposition **ne peut pas écrire** dans le magasin métier — vérifié par simulation de politique IAM, pas par test applicatif | §9.1, §9.2 |
| M16 | Le rôle de FastAPI ne peut transitionner une commande que vers `confirmed`, jamais vers `executed` | §9.1 |
| S1 | Aucun tool n'est appelable hors de la Gateway — ni depuis FastAPI, ni depuis le domaine `/agents` | CAM Domaine 7 |
| S2 | Argument d'identité (`actorId`, `tenantId`, …) : refusé au schéma **et** événement `tool_forbidden_field` émis | §4.2, §4.3 |
| S3 | Identité produite par le modèle : écrasée par l'identité injectée, y compris pour un champ non listé | `V2-ADR-006`, §4.3 |
| S4 | Appel émis **en contournant le filtre d'exposition** : rencontre l'autorisation Gateway et échoue | §9.3 |
| S5 | Nom de tool transmis dans le payload : ignoré ; la cible résout depuis le contexte | §4.4 |
| S6 | Aucun jeton Cognito n'atteint un tool, vérifié par inspection du payload reçu | `V2-ADR-006`, §2.3 |
| S7 | Conformité du catalogue : C1 à C8 vérifiées, chacune avec un cas négatif dédié | §3.6 |
| S8 | Refus d'autorisation répétés : le disjoncteur **ne s'ouvre pas** | §8.2 |
| S9 | Indisponibilité répétée : le disjoncteur s'ouvre, puis se ferme après sonde réussie | §8.3 |
| S10 | Budget `maxToolCalls` : une mutation complète en consomme 2, une proposition abandonnée en consomme 1 | §11.1 |
| S11 | Journaux : aucune valeur d'argument métier, aucun contenu de commande, `commandId` hashé | §13.2 |
| S12 | Un tool ne retourne rien que l'identité appelante ne soit autorisée à lire (E2) | §12.3 |
| S13 | **Divergence de catalogue simulée** : cible portant un manifeste plus récent que le catalogue Gateway — la cible refuse ce que son manifeste refuse, sans se fier au catalogue exposé | §3.7, §4.1 |
| S14 | Le rôle du Runtime **ne peut pas** invoquer une cible de tool directement — vérifié par simulation de politique IAM (complète S1, qui est applicatif) | §9.1 |
| S15 | Version de protocole MCP non supportée : erreur explicite, **aucun repli silencieux** vers une version antérieure | §3.4 |

**M1 est la preuve principale de l'ADR** et doit être traitée comme telle : c'est une preuve négative,
et une preuve négative qui passe pour une mauvaise raison — parce que le tool est cassé, par exemple —
ne prouve rien. Elle est donc encadrée par M12, qui établit que la matérialisation fonctionne, et par
M4, qui établit que l'exécution fonctionne sur une commande légitime.

---

## 16. Terraform

### 16.1 Variables

| Variable | Portée |
|---|---|
| `tool_call_timeout_ms` | timeout par appel de tool |
| `tool_retry_max_attempts` | tentatives sur indisponibilité transitoire |
| `circuit_breaker_failure_threshold` | seuil d'ouverture |
| `circuit_breaker_probe_delay_ms` | délai de sonde |
| `tool_catalogue_manifest_path` | chemin du manifeste, source de la configuration dérivée (§3.1) |
| `mcp_protocol_version` | version de protocole acceptée (§3.4) |

Les paramètres du magasin de commandes et le quota `pending` ne sont **pas** déclarés ici : ils
appartiennent à `V2-LLD-006` et `V2-LLD-005` (§14).

### 16.2 Règles de garde

À ajouter à `scripts/terraform_plan_guard.py` (`V2-LLD-008` porte l'intégration au pipeline).

| # | Règle | Type |
|---|---|---|
| B1 | Aucune cible de tool exposée directement — toute invocation passe par la Gateway | bloquante |
| B2 | La configuration Gateway du plan est identique au manifeste dérivé (C7) | bloquante |
| B3 | Tout tool `mutating` du plan a ses deux rôles présents (C2, C3) | bloquante |
| B4 | Aucun schéma du plan ne déclare `additionalProperties: true` (C5) | bloquante |
| B5 | Aucun schéma du plan ne déclare un champ interdit (C6) | bloquante |
| B6 | Le rôle de la cible de proposition ne porte **aucune** action d'écriture sur le magasin métier (§9.1) | bloquante |
| B7 | La resource policy de la Gateway ne déclare **que** le rôle du Runtime comme principal (§9.1) | bloquante |
| B8 | Le rôle de FastAPI ne porte aucune action permettant la transition vers `executed` (§9.1) | bloquante |
| N1 | `tool_call_timeout_ms` laisse une marge sous le budget résiduel minimal de `V2-LLD-003 §5` | non bloquante |
| N2 | `circuit_breaker_failure_threshold` est strictement supérieur à `tool_retry_max_attempts` | non bloquante |

N2 évite une configuration où le disjoncteur s'ouvre avant que les retries d'un seul appel soient
épuisés — le tool serait alors coupé par sa propre politique de reprise.

---

## 17. Critères de sortie

- [ ] Préconditions P1, P3, P4 et P5 (§1.3) **vérifiées sur le service** — P1 ne conditionne plus que
      la défense supplémentaire (§9.2) ; P2 est levée par conception (`V2-LLD-006 §5.3.3`) et sa tenue
      relève de la règle de garde du plan, non d'une vérification sur le service ;
- [ ] écarts de corpus 1 à 4 (§1.7) corrigés dans `V2-LLD-006`, `V2-LLD-001`, `V2-ADR-006` et
      `V2-ADR-011` ;
- [ ] magasin de commandes conçu dans `V2-LLD-006` — table, clés, deux TTL portées par un horodatage
      explicite (§6.4), rétention `executed`, retrouvabilité par `operationId` (I9) ;
- [ ] manifeste de catalogue écrit et contrôles C1 à C8 automatisés ;
- [ ] ordre de déploiement cible → catalogue tenu par le pipeline (§3.7, `V2-LLD-008`) ;
- [ ] deux cibles distinctes provisionnées, avec les interdictions IAM du §9.1 vérifiées par
      simulation de politique (M15, M16, S14) ;
- [ ] preuves M1 à M16 et S1 à S15 exécutées, M1, M6 et M14 sur environnement réel ;
- [ ] `confirmationVerified` retiré des tools V1 **après** M1, jamais avant (§1.8, §4.2) ;
- [ ] règles de garde B1 à B8 et N1 à N2 en place ;
- [ ] `V2-LLD-003 §5` recalibré si le budget `maxToolCalls` ne couvre pas le doublement des appels
      mutants (§11.1).

## 18. Trajectoire V2 → V3

| Aspect | V2 | V3 |
|---|---|---|
| Tools exposés | Trips uniquement (§3.5) | Trips **et actions documentaires agentiques** (`V2-ADR-014`) |
| Matérialisation | tool de proposition sans effet de bord | inchangée |
| Magasin de commandes | table dédiée (`V2-LLD-006`) | inchangé |
| Confirmation | endpoint FastAPI dédié | inchangée |
| Séparation proposition / exécution | deux cibles à rôles IAM distincts (§9.2) | inchangée |
| Politique Gateway par rôle de tool | ajoutée si P1 est satisfaite | inchangée |
| Disjoncteur | état par instance (§8.3) | état partagé si le volume le justifie |

**Ce qui ne change pas en V3, et pourquoi c'est le point important.** La séquence en quatre temps, la
règle « seul le `commandId` circule » et l'atomicité de la transition sont indépendantes du périmètre
des tools. Étendre le catalogue aux actions documentaires n'est donc pas un changement de mécanisme :
c'est l'ajout de deux entrées au manifeste par action, sous les mêmes contrôles C1 à C8. C'est
précisément ce que la séparation proposition/exécution achète — une extension du périmètre qui ne
rouvre aucune décision d'architecture.
