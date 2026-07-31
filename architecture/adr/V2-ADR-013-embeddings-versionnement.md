# V2-ADR-013 — Embeddings Bedrock et stratégie de versionnement

- **Statut :** Draft (propositions — en attente de revue et de validation)
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-003` (schéma de chunk et index S3 Vectors), `V2-ADR-019` (phasage KB en
  V2), `V2-ADR-010` (restauration), `V2-ADR-012` (cycle de vie des modèles Bedrock)
- **Dépendance inverse :** `V2-ADR-018` dépend de cet ADR (`embeddingSpaceId`, `chunkerVersion`,
  séquence de bascule) et n'est donc pas listé ci-dessus — le sens est 018 → 013. Sa mesure reste
  **bloquante pour la capacité de migration** décidée ici, sans l'être pour l'acceptation de cet
  ADR : voir « Décision — Migration », étape 3.
- **Préconditions à prouver avant implémentation :** immuabilité de la dimension et de la métrique
  d'un index S3 Vectors, et immuabilité du modèle d'embedding d'une base de connaissances (voir
  « Préconditions »).
- **Documents impactés :** `V2-ADR-003`, `V2-ADR-010`, `V2-ADR-019` ; `V2-LLD-002` §4.2, §5.2, §5.4,
  §7.1, §12, §17.2 ; `V2-LLD-006` — voir « Écarts à corriger dans le corpus ».

## Contexte

`V2-ADR-003` a posé que les embeddings sont configurables (`embeddingModelId` en paramètre, jamais
codé en dur) et que trois champs sont tracés par chunk : `embeddingModelId`, `embeddingVersion` et
`chunkerVersion`. `V2-ADR-019` a délégué à Bedrock Knowledge Bases, pour la phase V2, le parsing,
le chunking, les embeddings et l'indexation, et a renvoyé à cet ADR la migration d'embeddings
reprise par l'équipe en V3. `V2-LLD-002` §5.4 en a dérivé une mitigation : un changement de modèle
se fait « par resynchronisation KB complète ».

Cet ADR tranche quatre questions que le corpus traite aujourd'hui comme des détails de
configuration :

1. **quelle est l'unité de versionnement** d'un embedding, et ce qu'elle rend comparable ;
2. **comment un changement de modèle est exécuté**, sans que l'index passe par un état incohérent ;
3. **comment la symétrie requête/document est garantie**, et par quel mécanisme elle est vérifiée ;
4. **quel délai** sépare l'annonce d'une fin de vie de la remise en service d'un index équivalent.

`V2-ADR-012` a traité le modèle de génération et énonçait déjà la différence de nature : un
changement de modèle de génération dégrade une réponse ; un changement de modèle d'embedding
**invalide un index**.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-003` | le modèle d'embedding est un paramètre, jamais une constante |
| `V2-ADR-003` | une réindexation ne duplique ni ne laisse orphelin aucun chunk |
| `V2-ADR-006` | les métadonnées filtrables obligatoires sont portées par chaque chunk |
| `V2-ADR-010` | l'index vectoriel est un état dérivé, reconstructible depuis S3 |
| `V2-ADR-019` | en V2 l'embedding est assuré par KB ; l'adapter est le seul point d'échange |
| `V2-ADR-012` | le cycle de vie d'un modèle Bedrock est subi, surveillé et alerté |
| `V2-ADR-018` | la bascule est conditionnée à une non-régression mesurée sur le dataset de retrieval, contre une baseline versionnée |

## Le fait technique déterminant — un embedding est un système de coordonnées

Un embedding n'est pas la sortie d'un modèle au sens où l'est une réponse : c'est la **projection
d'un texte dans un espace vectoriel propre au modèle qui l'a produit**. Deux conséquences, toutes
deux structurantes :

- **la similarité entre deux vecteurs issus de modèles différents n'a pas de sens.** Elle n'est pas
  « moins bonne » : elle est arbitraire. Le calcul aboutit, retourne un score plausible, et classe
  des chunks sans rapport avec la question. Aucune exception n'est levée, aucun code d'erreur n'est
  émis, aucune métrique technique ne bouge ;
- **la dimension et la métrique de distance appartiennent à l'espace, pas au chunk.** Un index
  S3 Vectors les fixe à sa création. Un modèle produisant 1 024 dimensions et un modèle en
  produisant 512 ne peuvent pas cohabiter dans un même index — non par convention, mais parce que
  l'index n'accepte pas les deux formes.

Il en résulte que **l'index est l'unité de l'espace d'embedding**, et qu'un changement de modèle
n'est pas une mise à jour d'index : c'est la création d'un index.

Le mode de panne à retenir est celui-ci : un index contenant des vecteurs de deux espaces répond
sans erreur, avec des scores crédibles, et des résultats faux. C'est la panne la plus coûteuse du
pipeline RAG, parce qu'elle est silencieuse pour la machine et visible seulement à l'usage.

## Ce que le corpus décompose mal

`V2-ADR-003` trace trois champs indépendants par chunk : `embeddingModelId`, `embeddingVersion` et
`chunkerVersion`. Cette décomposition mélange deux natures :

| Élément | Effet d'un changement | Portée |
|---|---|---|
| Modèle, dimension, métrique de distance | les vecteurs deviennent incomparables | **espace** — l'index entier |
| Stratégie de chunking (taille, recouvrement) | la granularité et le rappel changent | **qualité** — évaluable à espace constant |

Un changement de chunker ne rend rien incomparable : une requête n'est pas découpée. Il modifie ce
qui est indexé, donc la qualité, et il est réévaluable dans le même espace. Un changement de
modèle, de dimension ou de métrique, lui, rend l'index inutilisable.

Traiter ces deux natures avec trois chaînes de caractères de même rang laisse croire qu'un
changement de modèle et un changement de chunker se gèrent pareillement. Ce n'est pas le cas :
l'un impose un nouvel index, l'autre non.

## Choix de l'unité de versionnement

### Option A — Trois champs indépendants (statu quo `V2-ADR-003`)

Conserver `embeddingModelId`, `embeddingVersion` et `chunkerVersion` comme attributs distincts.

Aucun de ces champs ne dit à quel index un chunk appartient, ni si une requête lui est comparable.
La vérification de compatibilité doit alors être reconstruite par le code à chaque usage, à partir
de trois valeurs dont la sémantique n'est écrite nulle part. C'est précisément ainsi qu'un index
mixte se constitue sans que personne ne l'ait décidé.

### Option B — Un identifiant d'espace, le chunker restant distinct

Introduire **`embeddingSpaceId`**, identifiant unique et opaque liant le modèle, la dimension et la
métrique de distance. `chunkerVersion` reste un attribut séparé, puisqu'il ne conditionne pas la
comparabilité.

Un chunk et une requête sont comparables **si et seulement si** ils portent le même
`embeddingSpaceId`. La règle tient en une égalité, vérifiable mécaniquement.

### Option C — Un identifiant unique englobant le chunker

Un seul identifiant couvrant modèle, dimension, métrique et chunker.

Rend tout changement de chunker équivalent à un changement d'espace, donc impose un nouvel index
pour un ajustement de taille de fenêtre. Surcontraint : interdit d'évaluer deux chunkers dans le
même espace, ce que `V2-ADR-018` a précisément besoin de faire.

## Décision — Unité de versionnement

**Option B.**

`embeddingSpaceId` identifie un espace vectoriel et, par construction, **un index**. Il est opaque
au domaine, au même titre que `invocation_id` dans `V2-ADR-012` : le code ne dérive aucune logique
de sa forme, il ne fait que comparer des égalités. Le format (slug, UUID ou autre valeur stable) et
la procédure d'attribution sont définis dans `V2-LLD-002`.

Trois règles en découlent :

- **un index porte un et un seul `embeddingSpaceId`**, fixé à sa création et immuable ;
- **aucune écriture n'est admise dans un index dont l'espace diffère de celui du producteur** ;
  cette vérification est un contrôle au moment de l'écriture, pas une convention de nommage ;
- **`chunkerVersion` reste tracé par chunk** et permet la réévaluation ciblée déjà prévue par
  `V2-ADR-003`, à espace constant.

## Choix de la stratégie de migration

Changer de modèle d'embedding impose de recalculer l'intégralité des vecteurs du corpus. La
question n'est pas s'il faut réindexer, mais **dans quel ordre**, et ce que le système sert pendant
l'opération.

### Option A — Resynchronisation en place (statu quo `V2-LLD-002` §5.4)

Purger l'index et le reconstruire avec le nouveau modèle.

Deux défauts, dont un rédhibitoire. Pendant la reconstruction, le retrieval répond sur un corpus
partiel : la dégradation est progressive, silencieuse, et `retrievalContext.status` vaut `ok`
puisque des candidats sont bien retournés. Surtout, **une interruption en cours de route laisse
l'index dans l'état mixte** décrit plus haut — sans marqueur, sans erreur, sans moyen simple de
distinguer un index à moitié migré d'un index sain.

### Option B — Index parallèle et bascule de pointeur

Construire le nouvel index à côté de l'ancien, qui continue de servir. Évaluer le nouvel index sur
le dataset de `V2-ADR-018`. Basculer le pointeur applicatif lorsque le résultat est admis.

Aucun état intermédiaire n'est servi : à tout instant, l'index interrogé est complet et homogène.
La bascule est atomique au niveau du pointeur et le retour arrière est la bascule inverse, sans
reconstruction. Le coût est un doublement temporaire du stockage vectoriel et un recalcul complet
des embeddings du corpus.

### Option C — Double écriture et fusion des résultats

Maintenir deux espaces peuplés et fusionner les candidats des deux à l'interrogation.

**Rejet non négociable :** les scores de deux espaces ne sont pas comparables entre eux. Il n'existe
pas de classement correct d'une liste mêlant les deux. L'option est écartée pour une raison
mathématique, pas opérationnelle.

### Option D — Migration progressive par document

Migrer document par document, l'index contenant les deux espaces pendant la transition.

C'est l'état mixte, adopté volontairement. Écarté pour la même raison que l'Option C.

## Décision — Migration

**Option B — index parallèle, évaluation, bascule de pointeur.**

La séquence est bornée et son point de non-retour est explicite :

1. création d'un index cible portant le nouvel `embeddingSpaceId` ; l'index courant continue de
   servir sans modification ;
2. réindexation complète du corpus depuis S3, qui reste la source de vérité (`V2-ADR-010`) ;
3. **exécution du dataset de retrieval de `V2-ADR-018` sur l'index cible** — ce dataset seul, à
   l'exclusion du dataset de génération, parce qu'il est le seul déterministe et donc le seul dont
   le verdict est reproductible — à `datasetVersion` et `fixturesVersion` constants, puis
   comparaison à la baseline de l'index courant. Un changement d'`embeddingSpaceId` n'invalide pas
   cette baseline : c'est précisément l'écart que cette étape mesure. Un écart au-delà de la marge
   configurée avec la baseline interdit la bascule ;
4. bascule du pointeur applicatif — opération atomique, unique point de non-retour ;
5. conservation de l'index précédent pendant une période de grâce définie en `V2-LLD-006`, ce qui
   fait du retour arrière une bascule inverse et non une reconstruction ;
6. suppression de l'index précédent à l'issue de la période de grâce.

L'étape 3 est ce qui distingue cette décision d'un simple remplacement. Un modèle d'embedding plus
récent n'est pas meilleur sur un corpus donné par construction : le domaine, la langue et la taille
des chunks font varier le résultat. **Sans mesure, une migration d'embedding est un pari.**

### Les ingestions pendant la période de grâce

La séquence ci-dessus ne serait complète que si le corpus était figé pendant son déroulement. Il ne
l'est pas : un document peut être ingéré entre la bascule (étape 4) et la suppression de l'index
précédent (étape 6). Sans règle, ce document n'existerait que dans le nouvel index, et la bascule
inverse — présentée à l'étape 5 comme un retour arrière sans reconstruction — servirait un corpus
silencieusement incomplet. Ce serait la même classe de panne que celle que cet ADR combat : une
réponse crédible sur un index qui n'est plus celui que l'on croit.

La règle retenue est donc : **pendant la période de grâce, toute ingestion alimente les deux
index**, chacun dans son propre espace. Deux précisions en découlent.

Ce n'est pas l'état mixte écarté aux options C et D. Chaque index reste homogène — un seul
`embeddingSpaceId`, un seul jeu de vecteurs comparables entre eux. Ce qui est dupliqué est le
travail d'ingestion, jamais l'espace d'un index.

L'échec d'une ingestion sur l'index précédent **n'échoue pas l'ingestion**. Il retire la possibilité
du retour arrière et abrège de fait la période de grâce : c'est une alerte, pas un refus. Servir le
nouvel index, qui est l'index courant et complet, reste correct.

Cette double ingestion est ce qui rend l'étape 5 vraie plutôt que rassurante, et son coût est ce qui
borne la durée de la période de grâce — ingérer deux fois n'est acceptable que temporairement.

## L'invariant de symétrie requête/document

Une requête doit être projetée dans l'espace du corpus qu'elle interroge. La violation de cet
invariant est la panne silencieuse décrite plus haut, et elle a deux origines possibles :

- **une dérive de configuration** : le paramètre de modèle d'embedding est modifié alors que
  l'index, lui, n'a pas changé ;
- **une bascule incomplète** : le pointeur d'index est basculé mais la configuration d'embedding de
  requête ne l'est pas, ou l'inverse.

La réponse retenue est de **ne pas laisser la configuration être la source de vérité de l'espace**.
L'`embeddingSpaceId` est lu depuis les métadonnées de l'index interrogé, et l'embedding de requête
est produit dans cet espace. Une configuration divergente est alors détectée, et le comportement
est **fail-closed** : `retrievalContext.status = degraded` avec un motif explicite, jamais un
retrieval exécuté dans un espace non vérifié (conforme à `architecture/hld/runtime-contract.md`).

Servir une réponse sans sources est acceptable ; servir des sources fausses avec des scores
crédibles ne l'est pas.

## La contrainte de taille de chunk

Chaque modèle d'embedding impose une **limite d'entrée en tokens**, et ces limites diffèrent d'un
modèle à l'autre d'un ordre de grandeur. Un chunk dépassant cette limite est, selon le modèle,
rejeté ou **tronqué silencieusement**.

La troncature silencieuse est le cas dangereux : la fin de chaque chunk trop long n'est jamais
indexée, le document paraît indexé, `chunkCount` est correct, et le rappel est amputé d'une part
invisible du corpus.

La taille maximale de chunk est donc **dérivée de la limite d'entrée du modèle d'embedding** et
vérifiée **au démarrage**, exactement comme `maxTokens` est dérivé de la fenêtre de contexte du
modèle de génération (`V2-LLD-003` §5.2.1, confirmé par `V2-ADR-012`). Une configuration de
chunking incompatible avec le modèle configuré est un refus au démarrage, pas une perte de rappel
découverte à l'évaluation.

Cette dépendance contraint le couple (espace, chunker) dans un sens et un seul : le chunker doit
tenir dans le modèle. C'est ce qui justifie de tracer les deux, sans les confondre.

## Cycle de vie et délai de remise en service

`V2-ADR-012` a établi que le cycle de vie d'un modèle Bedrock est subi : `Active`, puis `Legacy`
avec un préavis d'au moins six mois, puis échec des appels. La sonde périodique qu'il décide
**couvre également le modèle d'embedding configuré**.

La conséquence diffère cependant de celle d'un modèle de génération. Perdre l'accès au modèle
d'embedding ne dégrade pas le retrieval : il l'arrête. Les vecteurs stockés restent lisibles, mais
plus aucune requête ne peut être projetée dans leur espace. **Un index dont le modèle est mort
n'est pas dégradé, il est inerte.**

Le préavis de six mois n'est donc utile que s'il excède le délai de remise en service, qui est la
somme du recalcul complet des embeddings du corpus, de l'évaluation `V2-ADR-018` et de la bascule.
Ce délai croît avec le corpus. Il est **mesuré, pas estimé** : la première migration réalisée en
fournit la valeur de référence, et cette valeur devient le seuil d'alerte de la sonde de cycle de
vie.

Enfin, la règle d'exercice de `V2-ADR-012` s'applique à un modèle d'embedding retenu comme cible de
migration mais pas encore en service : un modèle jamais invoqué est un modèle dont l'accès peut
être perdu avant d'avoir servi.

## Interaction avec la restauration

`V2-ADR-010` traite l'index vectoriel comme un **état dérivé**, reconstructible par ré-ingestion
depuis S3. C'est correct, et cela introduit une contrainte que l'ADR ne mentionne pas.

Une reconstruction produit des vecteurs **avec la configuration active au moment de la
reconstruction**. Si un changement d'espace est intervenu entre la sauvegarde et la restauration,
reconstruire une partie du corpus avec la configuration courante et laisser le reste dans l'ancien
espace produit exactement l'index mixte que cet ADR interdit.

La règle est donc : **une reconstruction est toujours totale à l'échelle d'un index, et se fait
dans l'espace déclaré par cet index**, jamais dans celui de la configuration courante. Restaurer
dans un espace différent n'est pas une restauration : c'est une migration, et elle suit la séquence
de bascule décidée plus haut, évaluation comprise.

## Réalisation par phase

`V2-ADR-019` a délégué l'embedding à Knowledge Bases pour la phase V2. La décision ci-dessus ne
change pas de nature selon la phase, mais son point d'application diffère.

| Aspect | Phase V2 (KB) | Phase V3 (applicatif) |
|---|---|---|
| Producteur des vecteurs | KB, via son rôle d'exécution | worker d'ingestion (`V2-ADR-004`) |
| Embedding de requête | KB, dans l'appel `Retrieve` | FastAPI, avant la requête S3 Vectors |
| Symétrie requête/document | garantie structurellement par KB | **à garantir par le contrôle ci-dessus** |
| Changement d'espace | nouvelle base de connaissances et nouvel index | nouvel index seul |
| Bascule | pointeur `KB_ID` / `KB_DATA_SOURCE_ID` (support défini dans `V2-LLD-002`) | pointeur d'index de l'adapter |

Deux points méritent d'être notés.

**En V2, la symétrie est acquise sans effort** : KB projette la requête et les documents avec le
même modèle, puisqu'il est fixé au niveau de la base de connaissances. Le contrôle décrit plus haut
n'est pas superflu pour autant — il devient nécessaire en V3, et l'écrire dès la V2 dans l'adapter
évite qu'il soit oublié au moment où il compte.

**En V2, un changement de modèle d'embedding impose une nouvelle base de connaissances**, le modèle
étant fixé à sa création. Cette contrainte, à confirmer (voir « Préconditions »), n'est pas une
gêne : elle réalise mécaniquement la stratégie d'index parallèle décidée ici. La mitigation
actuelle de `V2-LLD-002` §5.4 — « resynchronisation KB complète » — décrit en revanche l'Option A,
écartée, et doit être corrigée.

## Écarts à corriger dans le corpus

À corriger dans le même lot que l'acceptation de cet ADR :

| Document | Passage | Correction attendue |
|---|---|---|
| `V2-ADR-003` | « Chunking et embeddings » : modèle et version tracés séparément | introduire `embeddingSpaceId` ; énoncer que dimension et métrique sont fixées à la création de l'index |
| `V2-ADR-003` | « Métadonnées de chunk » : `embeddingModelId`, `embeddingVersion` non filtrables | remplacer par `embeddingSpaceId` ; conserver `chunkerVersion` |
| `V2-ADR-003` | « un index partagé » | préciser que l'index est l'unité de l'espace d'embedding |
| `V2-ADR-010` | « ré-embedding lors de la ré-ingestion » | préciser que la reconstruction se fait dans l'espace déclaré par l'index, jamais dans celui de la configuration courante |
| `V2-ADR-019` | « migration d'embeddings … par resynchronisation » | renvoyer à la séquence de bascule décidée ici |
| `V2-LLD-002` §4.2 | métadonnées non filtrables incluant `embeddingModelId` | remplacer par `embeddingSpaceId` ; ajouter l'immuabilité de l'espace de l'index |
| `V2-LLD-002` §5.2 | table de configuration de la data source KB | ajouter dimension, métrique et la dérivation de la taille de chunk |
| `V2-LLD-002` §5.4 | « migration d'embeddings déléguée : resynchronisation KB complète » | remplacer par la séquence d'index parallèle, évaluation et bascule |
| `V2-LLD-002` §7.1 | contrat `VectorRetrievalPort` | exposer l'espace de l'index et le vérifier avant `retrieve` |
| `V2-LLD-002` §12 | `EMBEDDING_MODEL_ID` seul | ajouter l'identifiant d'espace et les paramètres qui le composent |
| `V2-LLD-002` §17.2 | réhydratation par resynchronisation complète | borner à l'espace déclaré par l'index restauré |
| `V2-LLD-006` | attributs `embeddingModelId` / `embeddingVersion` de `documents` | aligner sur `embeddingSpaceId` ; définir la période de grâce de l'index précédent et la double ingestion qui s'y applique |

Le coût d'un recalcul complet des embeddings et le doublement temporaire du stockage vectoriel sont
une **entrée** pour `V2-LLD-007`, qui n'est pas encore rédigé : aucune correction n'y est requise,
mais la contrainte doit y être reprise.

## Préconditions

La décision est prise ; son activation dépend de faits à prouver avant implémentation :

- **immuabilité de la dimension et de la métrique de distance d'un index S3 Vectors** après sa
  création — c'est le fondement de la règle « un index, un espace » ;
- **immuabilité du modèle d'embedding d'une base de connaissances** après sa création — détermine
  si un changement d'espace en V2 impose une nouvelle KB ou une reconfiguration ;
- liste des modèles d'embedding disponibles en `eu-west-3`, avec pour chacun les dimensions
  admises et la limite d'entrée en tokens — la dérivation de la taille de chunk en dépend ;
- **comportement du modèle retenu en cas de dépassement de la limite d'entrée** : rejet explicite
  ou troncature silencieuse. La réponse conditionne le caractère bloquant du contrôle au démarrage ;
- capacité de KB à exposer, dans les métadonnées de chunk, de quoi vérifier l'espace d'origine —
  faute de quoi le contrôle d'homogénéité repose en V2 sur la seule discipline de configuration.

Tant que ces preuves ne sont pas produites, la configuration d'embedding reste celle de
`V2-LLD-002` §5.2, sans changement de modèle. Cette configuration reste correcte ; elle est
seulement dépourvue de procédure de migration.

## Périmètre exclu

- **Le choix du modèle d'embedding** : c'est une donnée de configuration, et son classement relève
  de l'évaluation de `V2-ADR-018`. Cet ADR décide un mécanisme de versionnement, pas un modèle.
- **Le régime de verdict et la marge d'écart** autorisant ou interdisant une bascule : fixés par
  `V2-ADR-018`, qui a écarté tout seuil absolu de qualité au profit d'une non-régression contre une
  baseline versionnée, et renvoyé la valeur initiale de la marge à `V2-LLD-009`. Cet ADR décide que
  la bascule est conditionnée à une mesure, pas ce que cette mesure doit valoir.
- **Le reranking** et les stratégies de recherche hybride : hors périmètre, sans effet sur l'espace.
- **La stratégie de chunking elle-même** (taille, recouvrement, découpage sémantique) : relève de
  `V2-LLD-002`. Cet ADR n'en fixe que la borne supérieure, imposée par le modèle.

## Conséquences

- l'index cesse d'être un magasin indifférencié : il porte un espace, et cet espace est une
  contrainte d'écriture vérifiée, pas une convention ;
- un changement de modèle d'embedding devient une opération planifiée, mesurée et réversible, au
  lieu d'un changement de paramètre ;
- le stockage vectoriel double pendant la durée d'une migration, et le recalcul complet des
  embeddings du corpus a un coût proportionnel à sa taille — à chiffrer dans `V2-LLD-007` ;
- la bascule est conditionnée à l'existence du dataset de retrieval de `V2-ADR-018` **et de sa
  baseline** : sans les deux, aucune migration d'embedding n'est autorisée. C'est une dépendance
  assumée, et elle rend `V2-ADR-018` bloquant pour cette capacité, pas seulement pour la qualité ;
- pendant la période de grâce, chaque ingestion est exécutée deux fois : le coût d'embedding à
  l'ingestion double temporairement, en plus du stockage. C'est la contrepartie d'un retour arrière
  réellement disponible, et c'est ce qui borne la durée de cette période ;
- le comportement fail-closed sur divergence d'espace privilégie l'absence de réponse à une réponse
  fausse : une dérive de configuration se manifeste par une perte de retrieval visible, ce qui est
  l'objectif ;
- en V2, la contrainte est en grande partie portée par KB ; l'essentiel du coût d'implémentation
  est reporté en V3, mais le contrat de l'adapter doit être écrit dès la V2 pour que ce report ne
  devienne pas une réécriture ;
- le délai de remise en service après fin de vie d'un modèle devient une grandeur à mesurer et à
  surveiller, et non un implicite couvert par le préavis du fournisseur.

## Preuves attendues

- **requête projetée dans un espace différent de celui de l'index** : le contrôle détecte la
  divergence et renvoie `degraded`, au lieu d'exécuter la recherche. Cette preuve négative est la
  plus importante de l'ADR : sans elle, la panne silencieuse reste possible ;
- **écriture d'un vecteur d'un espace étranger dans un index** : refusée, et non acceptée puis
  détectée ultérieurement ;
- **chunk dépassant la limite d'entrée du modèle** : refus au démarrage sur configuration
  incompatible, et absence de troncature silencieuse à l'ingestion ;
- **migration complète en environnement de test** : index parallèle construit, dataset
  `V2-ADR-018` exécuté sur les deux index, écart mesuré, bascule effectuée ;
- **retour arrière après bascule** : effectué par bascule inverse du pointeur, sans reconstruction,
  et vérifié sur le même dataset ;
- **document ingéré pendant la période de grâce, puis retour arrière** : le document est présent dans
  l'index redevenu courant — la bascule inverse ne sert jamais un corpus arrêté à la date de la
  bascule ;
- **échec d'ingestion sur l'index précédent pendant la période de grâce** : l'ingestion aboutit sur
  l'index courant, une alerte est produite, et le retour arrière est marqué comme indisponible ;
- **délai de remise en service mesuré** sur cette migration de test, et enregistré comme valeur de
  référence du seuil d'alerte de cycle de vie ;
- **restauration après changement d'espace** : la reconstruction se fait dans l'espace déclaré par
  l'index restauré, et un mélange d'espaces est impossible à produire par la procédure ;
- sonde de cycle de vie : le passage simulé en `Legacy` du modèle d'embedding produit une alerte,
  au même titre que pour le modèle de génération (`V2-ADR-012`) ;
- coût du recalcul complet mesuré sur le corpus de test et extrapolé, pour alimenter `V2-LLD-007`.

## Références AWS

- Amazon S3 Vectors — création d'index, dimension et métrique de distance ;
- Amazon Bedrock — modèles d'embedding disponibles, dimensions admises et limites d'entrée ;
- Amazon Bedrock Knowledge Bases — configuration du modèle d'embedding d'une base de connaissances ;
- Amazon Bedrock Knowledge Bases — `StartIngestionJob` et resynchronisation d'une data source ;
- Amazon Bedrock — *Model lifecycle* (`Active`, `Legacy`, fin de vie), repris de `V2-ADR-012` ;
- Amazon Bedrock — tarification des modèles d'embedding (par token d'entrée).
