# V2-ADR-017 — Classification documentaire et conservation

- **Statut :** Accepted
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-003` (attribut `classification` de la table `documents`),
  `V2-ADR-004` (mécanique de désindexation pour la transition vers `restricted`), `V2-ADR-006`
  (modèle d'autorisation, intrants « type et classification de ressource » et « ownership ou
  partage explicite »), `V2-ADR-014` (une action élargissant un accès est une action mutante),
  `V2-ADR-015` (fenêtre résiduelle, PITR non rédactible), `V2-ADR-019` (métadonnées de chunk
  propagées par Knowledge Bases en V2)
- **Préconditions non bloquantes :** propagation effective de `classification` aux chunks par KB ;
  définition de la data source KB par préfixe S3 ; coût de la lecture de `documents` avant
  filtrage (voir « Préconditions »).
- **Documents impactés :** `V2-LLD-002` §4.1, §4.2, §5.3, §6.2, §6.2.1, §11.2 ; `V2-LLD-005`
  (autorisation sur lecture directe) ; `V2-LLD-006` §2, §4.3, §7.1, §7.2, §10 ; `V2-ADR-003` ;
  `V2-ADR-006` ; `HLD` §11 ; `LLD-V2-INDEX-FR.md` (portée `V2-LLD-005`) — voir « Écarts à corriger
  dans le corpus ».

## Contexte

`V2-ADR-003` a introduit un attribut `classification` dans la table `documents`. `V2-ADR-006` l'a
inscrit comme quatrième intrant de son modèle d'autorisation. `V2-LLD-002` §6.2 en a fait la
troisième étape de son post-filtrage, `V2-LLD-002` §5.3 le propage aux chunks via le fichier de
métadonnées KB, `V2-LLD-006` §4.3 le déclare « écrit par serveur (`V2-ADR-017`) », et
`V2-LLD-002` §11.2 en donne un exemple avec la valeur `internal`.

Six documents s'appuient donc sur un attribut dont **aucun ne définit les valeurs**, ni ce qu'elles
autorisent, ni comment elles se composent avec l'ACL, ni qui les fixe. `V2-LLD-006` §1.3 le
reconnaît explicitement et renvoie à cet ADR :

> « Taxonomie exacte, règles d'accès par niveau, workflow de reclassification »

L'attribut a été câblé dans un chemin d'autorisation avant que sa sémantique existe. Cet ADR ne
comble pas seulement ce vide : la vérification montre que le câblage lui-même est incorrect.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-006` | l'autorisation se fonde sur le type et la classification de la ressource, l'ownership et le partage explicite |
| `V2-ADR-006` | un refus est la valeur par défaut lorsqu'une information manque |
| `V2-ADR-006` | aucun accès public ; aucune clé de partition ni droit accepté du client |
| `V2-ADR-019` | FastAPI applique le post-filtrage tenant et ACL après retrieval, côté serveur |
| `V2-ADR-014` | une action mutante est matérialisée, confirmée hors du chemin du modèle, puis exécutée |
| `V2-ADR-015` | le PITR est table-wide et non rédactible ; la fenêtre résiduelle est une propriété du système |
| `V2-ADR-002` | le contenu documentaire est une donnée non fiable |
| HLD §11 | chaque catégorie de donnée dispose d'une rétention, d'un mécanisme de suppression et d'un test |
| Charte §4.2 | aucune organisation ni gouvernance client inventée n'entre dans le périmètre |

## Le fait déterminant — la valeur qui autorise est une copie dérivée, lue trop tard

`V2-LLD-002` §4.2 range `classification` dans les métadonnées **non filtrables** de S3 Vectors et
précise que « le post-filtrage classification se fait aussi côté FastAPI via `documents` ». Le
« aussi » ne dit pas laquelle des deux valeurs décide. La chaîne de retrieval de §6.2 répond, et
la réponse est mauvaise :

```text
1. candidats = adapter.retrieve(...)                  filtre KB : tenantId, status
2. post-filtrage : tenant, ACL, classification        <- décide ici
...
5. résoudre citations : lire documents                <- lit documents ici
```

La décision de classification est prise à l'étape 2 ; `documents` est lu à l'étape 5. À l'étape 2,
la seule valeur disponible est celle **portée par le chunk** — écrite dans le fichier de
métadonnées à l'upload (§5.3), figée par KB au moment de l'indexation.

Cette copie n'est pas synchrone avec sa source. `V2-LLD-002` §5.4 énonce déjà que KB ne permet pas
de reprendre finement une métadonnée sans resynchronisation. Une reclassification enregistrée dans
`documents` reste donc sans effet sur le filtre tant que le document n'est pas réindexé.

**Le sens de l'écart est le problème.** Une reclassification restrictive — un document dont on
resserre l'accès — est précisément celle qu'on attend immédiate. Elle est celle qui n'a aucun
effet : le chunk continue de porter l'ancien niveau, plus permissif, et le post-filtrage l'applique.
La fenêtre de sur-exposition dure jusqu'à la prochaine ré-ingestion, dont aucun document ne fixe
l'échéance.

Trois conséquences.

**L'attribut est un contrôle d'autorisation traité comme une donnée d'affichage.** `documents` est
lu à l'étape 5, avec le titre et la page, parce que le corpus a rangé `classification` parmi les
métadonnées de présentation. Il gouverne un refus : sa place est avant le filtre, pas après.

**Le vocabulaire manque, donc le contrôle est intestable.** `internal` apparaît en exemple dans
`V2-LLD-002` §11.2 sans qu'aucun document ne dise ce qu'il autorise, ni quelles autres valeurs
existent. Aucun test négatif ne peut être écrit contre un domaine de valeurs indéfini.

**La composition avec l'ACL est indéterminée.** §6.2 applique l'ACL puis la classification comme
deux filtres successifs, sans dire lequel prime. Si l'ACL peut autoriser au-delà de ce que la
classification permet, un partage explicite contourne la classification et l'attribut ne sert à
rien. Si elle ne peut pas, il faut l'écrire.

## Le second écart — deux vocabulaires de sensibilité sans lien déclaré

`V2-LLD-006` §2 porte une colonne « Sensibilité » dont les valeurs sont `utilisateur`, `tenant`,
`technique`, `identité`, `conversationnelle`, `public`, `critique`, `technique dérivée`. Elle
qualifie les **catégories de données du système** — un magasin, une table, un bucket.

`classification` qualifie **un document**. Les deux vocabulaires coexistent dans le même LLD sans
que leur relation soit énoncée, et la ligne « Contenu documentaire » de §2 porte la sensibilité
`tenant` pour l'ensemble du bucket, quelle que soit la classification des documents qu'il contient.

Les deux axes sont légitimes et distincts : l'un dimensionne la sauvegarde et le chiffrement par
magasin, l'autre décide l'accès par ressource. L'écart n'est pas qu'ils coexistent, c'est que rien
ne le dit — et qu'un lecteur peut raisonnablement croire que `classification` prend ses valeurs
dans la colonne « Sensibilité ».

## Ce qu'aucun ADR n'a décidé

| ADR | Ce qu'il décide | Ce qu'il laisse ouvert |
|---|---|---|
| `V2-ADR-003` | `classification` est un attribut de `documents` | ses valeurs, son effet, son écriture |
| `V2-ADR-006` | l'autorisation consomme la classification et le partage | comment ils se composent |
| `V2-ADR-019` | FastAPI post-filtre tenant et ACL après retrieval | la source de vérité du filtre de classification |
| `V2-ADR-015` | la rétention est uniforme et le résidu borné | si la classification module la conservation |

## Options — taxonomie

### Option A — Deux niveaux : privé et partagé au tenant

`confidential` (ownership ou partage explicite) et `internal` (tout membre du tenant).

**Avantages :** minimal ; n'ajoute aucune contrainte de stockage ; se réduit à formaliser les
intrants 4 et 5 déjà décidés par `V2-ADR-006`, sans capacité nouvelle.

**Limites :** tout document stocké est indexable, donc susceptible d'entrer dans un contexte
transmis à Bedrock. Aucun niveau ne permet de conserver un document sans l'exposer au RAG. La
lacune est réelle : elle n'existe pas parce qu'elle a été arbitrée, mais parce qu'elle n'a pas été
vue.

### Option B — Trois niveaux, dont un non indexable

`confidential`, `internal`, et `restricted` : accessible sur ownership ou partage, **jamais indexé,
jamais injecté dans un contexte modèle**.

**Avantages :** chaque niveau a un effet technique distinct et vérifiable par un test. Comble la
lacune de l'option A : le stockage devient dissociable de l'exposition au RAG, ce que `V2-ADR-002`
rend souhaitable en traitant le contenu documentaire comme non fiable.

**Limites :** le niveau `restricted` a un coût structurel, seul de la taxonomie. La data source KB
se définit par préfixe S3 : exclure un document de l'indexation exige un préfixe hors data source,
donc une propriété de classification portée par la clé de stockage.

### Option C — Taxonomie ouverte et configurable

Les niveaux et leurs droits sont déclarés en configuration, sans ensemble fermé dans l'ADR.

**Rejet.** Une taxonomie ouverte déplace une décision d'autorisation vers la configuration : le
domaine de valeurs devient non testable, et une valeur inconnue en production n'a pas de
comportement défini. Le refus par défaut de `V2-ADR-006` imposerait de rejeter toute valeur non
reconnue, ce qui revient à un ensemble fermé — mais fermé ailleurs que là où il est décidé. La
Charte §4.2 ajoute une raison : une taxonomie extensible anticipe une gouvernance client qui
n'existe pas.

## Décision — taxonomie

Retenir **l'option B**. Trois niveaux, ensemble fermé, ordonnés par restriction croissante.

| Niveau | Accès en lecture | Indexé | Injecté dans un contexte modèle |
|---|---|---|---|
| `internal` | tout membre du tenant | oui | oui, pour tout membre du tenant |
| `confidential` | ownership ou partage explicite | oui | oui, pour les seuls autorisés |
| `restricted` | ownership ou partage explicite | **non** | **non** |

`internal` est conservé comme nom parce que `V2-LLD-002` §11.2 l'emploie déjà : la taxonomie
s'aligne sur l'existant plutôt que de créer une correction supplémentaire.

**Aucun niveau `public`.** `V2-ADR-006` exclut tout accès public et ne prévoit aucun partage
anonyme. Un tel niveau serait une valeur sans mécanisme. Son absence est une décision, pas un
oubli — la colonne « Sensibilité » de `V2-LLD-006` §2 emploie `public` pour le bucket frontend, ce
qui relève de l'autre vocabulaire.

**La valeur par défaut est `confidential`**, et non le niveau le plus restrictif. Ce choix est une
décision indépendante de `V2-ADR-006` : le refus par défaut de cet ADR concerne l'absence
d'information sur l'autorisation, non le défaut d'un attribut dont toutes les valeurs produisent
un accès légitime différencié. La décision repose sur deux critères propres : l'upload documentaire
existe pour alimenter le RAG, et un défaut à `restricted` produirait un système où aucun document
n'est indexé sans geste explicite. `confidential` est donc la valeur fail-closed sur l'accès — seul
le propriétaire lit — et fonctionnelle sur l'indexation.

**Un document en quarantaine est traité comme `restricted`**, quelle que soit la valeur déclarée.
Son contenu n'a pas été validé ; il n'est ni lisible ni indexable. Le cycle de vie existant le
garantit déjà côté indexation — `quarantined` n'atteint jamais `indexed` (`V2-LLD-002` §4.3) — mais
la lecture, elle, n'était pas fermée.

**La reclassification d'un document `quarantined` est refusée.** Modifier `classification` sur un
document dont `status = quarantined` est sans effet tant que la validation n'a pas abouti : le
statut prime sur la valeur de l'attribut. Toute tentative de reclassification — dans un sens ou dans
l'autre — est refusée par la couche applicative (FastAPI) sans appel à `V2-ADR-014`, puisque
`quarantined` neutralise la classification déclarée.

## Options — point d'application du filtre

### Option A — Filtre `Retrieve` sur métadonnée filtrable

Rendre `classification` filtrable dans S3 Vectors et l'inclure dans le filtre KB.

**Rejet.** La valeur filtrée resterait la copie figée à l'indexation : le défaut identifié plus
haut n'est pas corrigé, il est déplacé plus tôt dans la chaîne. S'y ajoute que le filtre devrait
énumérer les niveaux autorisés pour l'utilisateur courant, faisant dépendre la requête KB d'une
décision d'autorisation — exactement ce que `V2-ADR-019` retire au magasin en imposant le
post-filtrage côté FastAPI.

### Option B — Post-filtrage sur la valeur portée par le chunk

Statu quo de `V2-LLD-002` §6.2.

**Rejet.** C'est le mécanisme dont le défaut est établi : une reclassification restrictive n'est
pas effective jusqu'à réindexation.

### Option C — Post-filtrage sur `documents`, lu avant le filtre

`documents` est lu pour chaque `documentId` distinct des candidats, avant l'étape de filtrage. La
valeur de `documents` est la seule qui autorise.

**Avantages :** la source de vérité de l'autorisation est le magasin qui la porte, et une
reclassification est effective immédiatement, sans réindexation.

**Limites :** déplace une lecture DynamoDB avant le filtre, donc sur tous les documents candidats
et non sur les seuls retenus.

## Décision — point d'application

Retenir **l'option C**.

> **La classification qui autorise est celle de `documents`, jamais celle du chunk.**

La copie portée par le chunk n'est pas retirée pour autant : elle devient un **filtre grossier**
appliqué avant la lecture de `documents`, à seule fin de défense en profondeur. Le partage n'est
pas une redondance, au même titre que les deux validations de `V2-ADR-020` :

```text
métadonnée de chunk   filtre grossier, peut être obsolète   défense en profondeur
documents             décision d'autorisation               source de vérité
```

Le sens de l'erreur possible est ce qui rend ce partage sûr. Le filtre grossier ne peut produire
que des **faux négatifs** : si le chunk porte un niveau plus restrictif que la source — cas d'une
reclassification assouplissante non encore réindexée — un chunk autorisé est écarté. La perte est
de rappel, non d'isolation, et elle se résorbe à la réindexation suivante. L'inverse — le chunk
plus permissif que la source — ne produit rien, puisque la décision finale est prise sur la source.

Ces faux négatifs sont observables sans mécanisme nouveau : ils alimentent le `reason =
filtered_out` que `V2-LLD-002` §6.2.1 distingue déjà de `no_match`, et dont il fait un seuil
d'alerte de configuration.

Le coût de la lecture est borné et chiffrable : au plus `topK` documents distincts, la
déduplication par `documentId` étant déjà prévue à l'étape 4 de §6.2, en une lecture groupée. Il
est assumé — un contrôle d'autorisation se juge sur sa justesse avant son coût.

## Décision — composition avec l'ACL

> **La classification est un plafond. L'ACL restreint en deçà, jamais au-delà.**

Un partage explicite ne fait pas franchir un niveau : il autorise un accès **dans** ce que le
niveau permet. Sans cette règle, un partage suffirait à contourner la classification et l'attribut
serait décoratif.

L'ordre d'évaluation en découle, et il est fail-closed à chaque étape :

```text
1. tenant          tenantId du document == tenant courant      sinon refus
2. classification  niveau lu dans documents                    détermine le socle
3. ownership/ACL   propriétaire, ou partage explicite           restreint le socle
4. indexabilité    restricted -> jamais dans retrievalContext   refus d'injection
```

L'étape 4 n'est pas une répétition de l'étape 2 : `restricted` interdit l'injection dans un contexte
modèle même à un utilisateur qui est autorisé à **lire** le document. La lecture directe et
l'injection dans un prompt ne sont pas le même acte — la seconde transmet le contenu à Bedrock et
l'expose à l'inférence.

**L'absence d'entrée `documents` pour un candidat produit un refus.** Si le BatchGetItem ne retourne
pas d'entrée pour un `documentId` — document supprimé dans la fenêtre entre le retrieve KB et la
lecture groupée — le fail-closed de `V2-ADR-006` s'applique : le candidat est écarté et compté en
`filtered_out`, sans erreur ni échec de la requête.

## Décision — reclassification

Une reclassification est immédiatement effective sur le chemin de lecture, par construction de la
décision précédente. Deux régimes s'appliquent selon son sens.

| Sens | Exemple | Régime |
|---|---|---|
| Restrictif | `internal` → `confidential` | pas de confirmation ; effet immédiat |
| Assouplissant | `confidential` → `internal` | action mutante `V2-ADR-014` : matérialisée, confirmée hors du chemin du modèle |

L'asymétrie suit `V2-ADR-014` sans l'étendre : une action qui élargit un accès est une action à
conséquence de sécurité, une action qui le resserre n'en est pas une. Un modèle ne déclenche jamais
un élargissement sur la seule foi d'un tour de conversation.

**La transition vers `restricted` est la seule reclassification à coût structurel.** Elle exige de
sortir l'objet du préfixe couvert par la data source KB, puis de désindexer les chunks existants.
La désindexation emprunte la mécanique de suppression de `V2-LLD-006` §8.2 — retrait de la source
puis resynchronisation — et elle est asynchrone.

Cette asynchronie est sans effet sur l'autorisation, et c'est le bénéfice direct de la décision
précédente : dès l'écriture dans `documents`, le post-filtrage refuse l'injection. Les chunks
survivants ne sont plus qu'un résidu à nettoyer, exactement comme `V2-ADR-015` distingue
l'effacement logique immédiat de la convergence différée des copies dérivées.

**Les versions S3 non-courantes à l'ancien préfixe doivent être purgées.** Sur un bucket versionné,
déplacer un objet est une opération copy + delete : la suppression de la clé source crée un delete
marker, mais les versions non-courantes restent accessibles par version ID à l'ancien emplacement.
Pour qu'aucun résidu ne soit atteignable hors du préfixe `restricted`, ces versions non-courantes
doivent être supprimées explicitement dans la même opération (hard delete des non-current versions
S3). Cette purge fait partie du coût structurel de la transition vers `restricted` et est attestée
par la preuve correspondante.

## La classification ne pilote pas la conservation

C'est la seconde question du titre de cet ADR, et la réponse est négative pour des raisons qui ne
sont pas de convenance.

**Le PITR est table-wide.** `V2-ADR-015` l'a établi : le PITR ne s'exprime pas par item et n'offre
aucune opération de rédaction. Une rétention par classification sur les métadonnées documentaires
n'est pas exprimable dans le mécanisme de durabilité que `V2-ADR-010` impose.

**Une rétention S3 par classification exigerait un préfixe par niveau.** Les cycles de vie S3 se
définissent par préfixe, pas par attribut. Porter les trois niveaux dans la clé rendrait **toute**
reclassification destructive — copie puis suppression, perte de l'historique de versions — alors
que la décision précédente les rend immédiates et non destructives, à la seule exception de
`restricted`.

**Une exception assumée, et son périmètre exact.** Le niveau `restricted` est bien porté par un
préfixe, ce qui ressemble à ce que le paragraphe précédent écarte. La différence est de nature : ce
préfixe encode l'**indexabilité**, c'est-à-dire dans quel service la donnée entre, et il est imposé
par la définition par préfixe des data sources KB — ce n'est pas un choix de conception. Il
n'encode pas de rétention, et les deux préfixes portent la même politique de conservation.

**La rétention uniforme est déjà déclarée et testée.** `V2-LLD-006` §10 fixe des rétentions par
catégorie de donnée, paramétrées en Terraform. Elles restent inchangées, et cette invariance est
désormais une décision au lieu d'un silence.

Ce que la classification pilote, côté conservation, est donc **rien** — et ce qu'elle ne pilote pas
est énoncé pour que l'absence soit vérifiable. Si une rétention différenciée devenait exigible, le
seul chemin conforme est un préfixe par niveau, avec le coût de reclassification destructive qui
l'accompagne ; il relèverait d'un nouvel ADR, pas d'un paramètre.

Deux points de conservation restent à fixer, qui n'établissent pas de rétention différenciée mais
comblent des silences :

- **le tombstone conserve la classification.** L'entrée `documents` en `status = deleted`, retenue
  30 jours (`V2-LLD-006` §10), conserve `classification` : une trace d'audit qui ne dirait pas à
  quel niveau le document supprimé était classé n'atteste rien d'exploitable ;
- **la classification n'est pas une donnée personnelle.** Elle qualifie la ressource, non la
  personne. Elle n'entre pas dans le périmètre d'effacement de `V2-ADR-015` autrement que par la
  suppression de l'entrée `documents` qui la porte.

## Ce que cette décision ne change pas

- **Le modèle d'autorisation.** `V2-ADR-006` reste la source des intrants ; cet ADR fixe le domaine
  de valeurs du quatrième et sa composition avec le cinquième.
- **La propriété du post-filtrage.** Il reste côté FastAPI, après retrieval (`V2-ADR-019`). Seul
  l'ordre interne de ses étapes change.
- **Les métadonnées filtrables obligatoires.** `tenantId`, `documentId`, `version`, `status`
  demeurent imposés par `V2-ADR-006`. `classification` reste non filtrable, et cette décision
  explique pourquoi cela suffit.
- **L'interdiction de `RetrieveAndGenerate`.** Elle est renforcée : le niveau `restricted` serait
  incontrôlable sans point de filtrage FastAPI entre retrieval et modèle.
- **Les rétentions de `V2-LLD-006` §10**, inchangées, et désormais explicitement indépendantes de
  la classification.

## Écarts à corriger dans le corpus

Ces corrections découlent de l'acceptation de l'ADR et ne sont pas appliquées par lui.

| Document | Écart | Correction attendue |
|---|---|---|
| `V2-LLD-002` §6.2 | la classification est filtrée à l'étape 2, `documents` est lu à l'étape 5 | remplacer la chaîne par la séquence : (0) KB retrieve → candidats avec métadonnées de chunk ; (1) filtre grossier sur `chunk.classification` (défense en profondeur) ; (2) lire `documents` en BatchGetItem groupé, dédupliqué par `documentId` ; (3) post-filtrage tenant, `documents.classification`, ownership/ACL, indexabilité ; les étapes suivantes sont inchangées |
| `V2-LLD-002` §4.2 | « le post-filtrage classification se fait aussi côté FastAPI » — ambigu sur la valeur qui décide | énoncer que la métadonnée de chunk est un filtre grossier et que `documents` décide |
| `V2-LLD-002` §6.2.1 | `filtered_out` ne mentionne pas les faux négatifs de reclassification | ajouter cette cause, avec sa résorption à la réindexation |
| `V2-LLD-002` §4.1 | un seul préfixe `sources/`, entièrement couvert par la data source KB | ajouter le préfixe des documents `restricted`, hors data source |
| `V2-LLD-002` §5.3 | le fichier de métadonnées porte `classification` sans dire que la valeur est un filtre grossier | préciser son statut et son obsolescence possible |
| `V2-LLD-002` §11.2 | l'exemple porte `internal` alors que le défaut décidé est `confidential` | aligner l'exemple, ou nommer l'élargissement qui l'a produit |
| `V2-LLD-006` §2 | la colonne « Sensibilité » et `classification` coexistent sans relation déclarée | énoncer que les deux axes sont distincts : magasin contre ressource |
| `V2-LLD-006` §4.3 | `classification` : « écrit par serveur (V2-ADR-017) », sans valeurs ni défaut | ajouter le domaine fermé, le défaut `confidential` et les deux régimes de reclassification |
| `V2-LLD-006` §7.1 et §7.2 | le bucket et ses cycles de vie ne connaissent qu'un préfixe de sources | ajouter le préfixe `restricted` avec la même politique de conservation |
| `V2-LLD-006` §10 | les rétentions ne disent pas si la classification les module | ajouter que la rétention est indépendante de la classification, et que le tombstone la conserve |
| `V2-ADR-003` | `classification` listé comme attribut sans taxonomie | renvoyer au domaine de valeurs de cet ADR |
| `V2-ADR-006` | `V2-ADR-017` figure dans ses dépendances alors que cet ADR dépend de lui — **cycle** | retirer `V2-ADR-017` des dépendances de `V2-ADR-006` ; le sens 017 → 006 est le bon |
| `HLD` §11 | les catégories de données n'ont pas d'axe de classification par ressource | mentionner la classification documentaire et son indépendance de la rétention |
| `V2-LLD-005` | la lecture directe de document ne mentionne pas de vérification de classification | ajouter que `GET /documents/{id}` suit les étapes 1–3 du modèle d'évaluation (tenant → `documents.classification` → ownership/ACL) ; l'étape 4 (indexabilité) ne s'applique pas à la lecture directe — un document `restricted` reste lisible par son propriétaire |
| `LLD-V2-INDEX-FR.md` | portée de `V2-LLD-005` : « classification des données » sans contenu | ajouter : domaine fermé, composition avec l'ACL, régimes de reclassification |

## Préconditions

Quatre points doivent être établis avant implémentation. Aucun n'est bloquant pour la décision ;
chacun énonce sa conséquence s'il n'est pas satisfait.

1. **Propagation de `classification` aux chunks par KB.** Vérifier que la valeur du fichier de
   métadonnées est bien portée par les chunks et retournée par `Retrieve`. Si elle ne l'est pas, le
   filtre grossier disparaît et la défense en profondeur se réduit à une couche — la décision tient,
   puisque l'autorisation ne repose pas sur cette valeur, mais l'absence doit être tracée comme un
   risque résiduel accepté plutôt que découverte à l'exploitation.
2. **Définition de la data source KB par préfixe.** Vérifier que la data source se restreint à un
   préfixe et que les objets hors préfixe ne sont pas ingérés. Si l'exclusion par préfixe n'est pas
   praticable, le niveau `restricted` doit être réalisé par un bucket distinct — plus coûteux, même
   sémantique — et non abandonné.
3. **Coût de la lecture avant filtrage.** Mesurer la latence de la lecture groupée de `documents`
   sur `topK` documents distincts, avant filtrage. Si elle dépasse le budget de retrieval, le levier
   conforme est la réduction de `topK` ou un cache court par `documentId`, jamais le retour à la
   décision sur la métadonnée de chunk.
4. **Désindexation d'un document existant.** Vérifier que le retrait d'une source suivi d'une
   resynchronisation retire effectivement ses chunks, comme `V2-LLD-006` §8.2 le suppose pour la
   suppression. Si la vérification échoue, elle invalide aussi la suppression documentaire déjà
   décidée — le défaut serait antérieur à cet ADR et de portée plus large.

## Périmètre exclu

- **Le régime juridique** de la confidentialité et toute qualification réglementaire : la Charte
  exclut la gouvernance client inventée. Cet ADR fixe un mécanisme et un domaine de valeurs.
- **Le modèle de partage explicite** — qui partage, avec qui, par quelle API : `V2-ADR-006` en pose
  le principe, `V2-LLD-005` en fixe la réalisation. Cet ADR en consomme le résultat.
- **La classification automatique par analyse de contenu** : elle supposerait un détecteur dont la
  qualité serait à instruire. La classification est déclarée à l'upload, avec un défaut fail-closed.
- **La détection de contenu sensible et la redaction** : `V2-ADR-008` pour les journaux.
- **La rétention des traces et des preuves** : `V2-ADR-008` et `V2-LLD-007`.
- **Le droit à l'effacement** et la fenêtre résiduelle : `V2-ADR-015`, consommé sans être redécidé.
- **Le chiffrement par niveau de classification** — une clé KMS par niveau : `V2-ADR-015` a écarté
  le chiffrement par sujet pour des raisons qui s'appliquent ici, et le chiffrement de bucket reste
  uniforme.

## Conséquences

- Le corpus perd un contrôle d'autorisation qui décidait sur une copie dérivée. La correction n'est
  pas une précision de taxonomie : elle change la source de vérité du filtre et l'ordre de la chaîne
  de retrieval.
- Une reclassification devient **immédiatement effective**, sans réindexation. C'est la propriété la
  plus visible de la décision, et elle n'était atteignable par aucun mécanisme fondé sur les
  métadonnées de chunk.
- La chaîne de retrieval acquiert une lecture DynamoDB avant filtrage, sur les candidats et non sur
  les retenus. Le coût est borné par `topK` et assumé.
- Le niveau `restricted` introduit un second préfixe S3 hors data source KB. C'est la seule
  contrainte de stockage de la taxonomie, et la seule reclassification destructive.
- L'injection dans un contexte modèle devient un acte distinct de la lecture, avec son propre refus.
  `V2-LLD-002` gagne une étape de filtrage que `V2-ADR-019` rendait possible sans la nommer.
- `V2-ADR-014` s'applique à un objet nouveau : l'élargissement d'accès par reclassification. Aucune
  extension de cet ADR n'est nécessaire, seulement son application.
- La conservation reste uniforme, et cette uniformité devient une décision testable au lieu d'un
  silence. Le coût d'une rétention différenciée est chiffré, ce qui rend l'arbitrage possible s'il
  était rouvert.
- Le tombstone (`status = deleted`, 30 jours) conserve `classification` : décision d'audit, pas de
  rétention différenciée.
- La classification ne relève pas du périmètre d'effacement de `V2-ADR-015` : elle qualifie la
  ressource, non la personne, et disparaît avec l'entrée `documents` qui la porte.
- Un cycle de dépendances existant est mis au jour : `V2-ADR-006` dépend de `V2-ADR-017`, qui dépend
  de lui. Il est corrigé dans le sens 017 → 006, comme les trois autres cycles du corpus.

## Preuves attendues

- un document reclassé de `internal` en `confidential` cesse d'être retourné à un utilisateur du
  tenant non propriétaire **sans réindexation** — preuve centrale : elle passe contre `V2-LLD-002`
  §6.2 *tel que corrigé par cet ADR*, et échoue contre le mécanisme actuel (ce contraste est la
  justification de la correction) ;
- un chunk portant une métadonnée `internal` obsolète, dont l'entrée `documents` porte
  `confidential`, n'est pas retourné à un utilisateur non autorisé — le filtre grossier ne décide
  pas ;
- un chunk portant `confidential` dont la source porte `internal` est écarté et compté en
  `filtered_out`, sans erreur ni refus de la requête — la perte est de rappel, et elle est mesurée ;
- un document `restricted` n'apparaît dans aucun `retrievalContext`, y compris pour son
  propriétaire, **et** son contenu reste lisible par lui en accès direct — les deux volets sont
  nécessaires : sans le second, la preuve ne distingue pas `restricted` d'une suppression ;
- aucun chunk d'un document `restricted` n'existe dans l'index, vérifié par un `Retrieve` non filtré
  en environnement de test ;
- un partage explicite sur un document `restricted` n'autorise pas son injection dans un contexte
  modèle — le plafond n'est pas franchi par l'ACL ;
- un document uploadé sans classification déclarée reçoit `confidential`, et n'est lisible par aucun
  autre membre du tenant ;
- un document en `quarantined` n'est ni lisible ni indexable, quelle que soit la classification
  déclarée à l'upload ;
- une valeur de classification hors du domaine fermé est refusée à l'écriture, et une entrée
  `documents` portant une valeur inconnue provoque un refus de lecture et non un accès par défaut ;
- un candidat dont `documentId` est absent de `documents` au moment du BatchGetItem est écarté sans
  erreur et compté en `filtered_out`, sans provoquer d'échec de la requête ;
- une tentative de reclassification sur un document `quarantined` est refusée, quelle que soit la
  direction du changement ;
- après une transition vers `restricted`, aucune version S3 non-courante ne subsiste à l'ancien
  préfixe et aucun chunk de l'ancien préfixe n'est ingéré par la data source KB ;
- une reclassification assouplissante sans confirmation `V2-ADR-014` est refusée ; une
  reclassification restrictive aboutit sans confirmation ;
- une entrée `documents` en `status = deleted` conserve `classification` pendant la durée du
  tombstone ;
- les rétentions mesurées sont identiques pour les trois niveaux, sur les deux préfixes S3 — preuve
  que la conservation est indépendante de la classification.

## Références

- `V2-ADR-003` — schéma de la table `documents`, attribut `classification`, métadonnées de chunk ;
- `V2-ADR-006` — modèle d'autorisation, intrants de décision, refus par défaut, absence d'accès
  public ;
- `V2-ADR-014` — matérialisation et confirmation des actions mutantes ;
- `V2-ADR-015` — PITR table-wide, fenêtre résiduelle, convergence différée des copies dérivées ;
- `V2-ADR-019` — post-filtrage tenant et ACL côté FastAPI, interdiction de `RetrieveAndGenerate` ;
- `V2-ADR-020` — partage d'un contrôle entre deux couches aux finalités distinctes ;
- `V2-LLD-002` §4 à §6 — stockage, métadonnées KB et chaîne de retrieval à corriger ;
- `V2-LLD-006` §2, §4.3, §7, §10 — catégories de données, attributs, buckets et rétentions ;
- Amazon Bedrock Knowledge Bases — data source définie par préfixe S3, fichier de métadonnées
  associé et propagation aux chunks ;
- Amazon S3 — configuration de cycle de vie par préfixe, versioning ;
- Amazon DynamoDB — lecture groupée `BatchGetItem` et Point-in-Time Recovery au niveau de la table.
