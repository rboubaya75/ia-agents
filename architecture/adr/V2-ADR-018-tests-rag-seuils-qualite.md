# V2-ADR-018 — Stratégie de tests RAG et seuils de qualité

- **Statut :** Draft (propositions — en attente de revue et de validation)
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-003` (métriques nommées, dataset versionné), `V2-ADR-010` (index
  vectoriel comme état dérivé, DR drill), `V2-ADR-012` (cycle de vie du modèle juge, délégation de
  la comparaison entre modèles), `V2-ADR-013` (`embeddingSpaceId`, `chunkerVersion`, bascule
  conditionnée à une mesure), `V2-ADR-017` (classification dans la chaîne de post-filtrage),
  `V2-ADR-019` (phasage KB en V2, post-filtrage côté FastAPI)
- **Préconditions non bloquantes :** déterminisme du `Retrieve` KB à index constant ; disponibilité
  d'un corpus de fixtures représentatif ; coût d'une exécution complète (voir « Préconditions »).
- **Documents impactés :** `V2-ADR-003` ; `V2-ADR-012` ; `V2-ADR-013` ; `V2-LLD-002` §1.1, §1.2,
  §15.1, §16 ; `V2-LLD-006` §14.2, §16, §17.1, §17.2 ; `LLD-V2-INDEX-FR.md` (portée `V2-LLD-009`)
  — voir « Écarts à corriger dans le corpus ».

## Contexte

`V2-ADR-003` a fixé une liste de métriques — recall@k, precision@k, groundedness, couverture des
citations, taux de refus — calculées « hors ligne » sur un « dataset d'évaluation versionné », et
a renvoyé à cet ADR. Quatre documents en ont ensuite dérivé des engagements opérationnels :

| Document | Engagement pris | Régime supposé |
|---|---|---|
| `V2-LLD-002` §16 | « métriques de qualité calculées sur le dataset versionné » | **Gate** |
| `V2-ADR-013` étape 3 | comparaison « aux valeurs de référence de l'index courant » | écart vs référence |
| `V2-LLD-006` §14.2 | « métriques dans la marge d'écart tolérée » après réhydratation | écart vs baseline |
| `V2-LLD-006` §16 | `run_rag_eval.py --dataset --baseline` → `PASS`/`FAIL` | verdict binaire |
| `V2-ADR-012` | l'évaluation comparative entre modèles « relève de `V2-ADR-018` » | classement |

Ces engagements ne décrivent pas le même mécanisme, et aucun document ne dit lequel s'applique.
`V2-ADR-013` va plus loin : il déclare la bascule d'embedding **interdite** sans cette mesure, ce
qui fait de cet ADR un bloquant de capacité et non seulement un ADR de qualité.

Cet ADR ne se limite pas à fixer des valeurs. La vérification montre que trois des grandeurs
promises ne sont pas mesurables dans le régime que le corpus leur suppose.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-003` | la qualité du retrieval est mesurée sur un dataset d'évaluation versionné |
| `V2-ADR-003` | chaque citation renvoyée est résolvable vers une source réelle et autorisée |
| `V2-ADR-013` | un écart au-delà du seuil interdit la bascule d'un index d'embedding |
| `V2-ADR-013` | deux stratégies de chunking doivent être évaluables dans le même espace |
| `V2-ADR-010` | l'index vectoriel est un état dérivé, dont la reconstruction est vérifiée |
| `V2-ADR-017` | la classification décide sur `documents` ; `restricted` n'entre dans aucun contexte |
| `V2-ADR-019` | le post-filtrage tenant et ACL est appliqué côté FastAPI, après retrieval |
| `V2-ADR-002` | le contenu documentaire est une donnée non fiable |
| Charte §4.2 | aucune organisation ni gouvernance client inventée n'entre dans le périmètre |

## Le fait déterminant — un seuil absolu sur un dataset que l'on écrit soi-même ne mesure rien

Le dataset d'évaluation est rédigé par l'équipe : elle choisit les questions et déclare les sources
attendues. Un seuil absolu — « recall@5 ≥ 0,8 » — appliqué à un tel dataset ne mesure pas la
qualité du système. Il mesure **la difficulté que l'auteur du dataset a choisi de se donner**.

La conséquence est mécanique et sans mauvaise foi nécessaire : un seuil non atteint se corrige en
reformulant une question ambiguë, ce qui est un geste légitime en soi. Le seuil est alors toujours
franchi, et il ne détecte plus aucune régression. Une gate qui ne peut pas échouer n'est pas une
gate ; c'est un rituel qui produit un artefact.

**Ce qui est mesurable est un écart, pas un niveau.** À dataset figé et corpus figé, une variation
de recall@k entre deux exécutions est imputable au seul changement du système — index, espace
d'embedding, chunker, ordre de la chaîne de filtrage. C'est cette variation qui porte
l'information, et c'est exactement ce que `V2-ADR-013` et `V2-LLD-006` demandent déjà sans le
distinguer d'un seuil absolu.

## Le second fait — les cinq métriques ne se mesurent pas sur le même chemin

`V2-ADR-003` énumère cinq grandeurs dans une seule phrase. Elles se répartissent en deux natures
qui n'ont ni le même coût, ni le même déterminisme, ni le même verdict possible.

| Métrique | Chemin mesuré | Appel de génération | Déterminisme à index constant |
|---|---|---|---|
| recall@k | retrieval | non | oui |
| precision@k | retrieval | non | oui |
| couverture des citations | retrieval + résolution | non | oui |
| taux de refus | génération | **oui** | **non** |
| groundedness | génération | **oui** | **non**, et exige un juge |

Les trois premières sont des fonctions de l'index et de la chaîne de filtrage : à index constant,
deux exécutions donnent le même résultat. Elles sont exécutables en intégration continue, sans
appel Bedrock de génération, à coût quasi nul.

Les deux dernières portent sur la réponse produite. Elles exigent un appel au modèle de génération,
dont la sortie varie d'une exécution à l'autre, et la groundedness exige en outre **un juge** :
quelqu'un ou quelque chose qui décide si une affirmation est étayée par les sources fournies.

`V2-ADR-013` conditionne une bascule d'index à « l'évaluation de `V2-ADR-018` ». Si cette
évaluation englobe les deux natures, la bascule dépend d'une mesure non déterministe : deux
exécutions successives peuvent rendre deux verdicts opposés sur le même index. **Un gate non
déterministe n'est pas un gate.** La séparation des deux natures n'est donc pas une commodité de
présentation, c'est ce qui rend l'engagement de `V2-ADR-013` tenable.

## Le troisième fait — une baseline adossée au corpus de production expire à chaque ingestion

`V2-LLD-006` §14.2 et §17.2 demandent de rejouer le dataset après une réhydratation et de comparer
à une baseline. Cette comparaison n'a de sens que si le corpus interrogé est **le même** qu'au
moment où la baseline a été établie.

Or le corpus de production change à chaque upload. Un document ajouté modifie les voisins d'une
requête, donc le classement, donc recall@k — sans qu'aucun changement du système soit en cause. La
baseline devient invalide, et l'écart mesuré au DR drill ne distingue plus une régression du
pipeline d'une simple évolution du corpus.

Le dataset d'évaluation exige donc **son propre corpus, figé et versionné**, indépendant du corpus
de production. Sans cette indépendance, l'engagement de `V2-LLD-006` §17.2 n'est pas réalisable.

## Le quatrième fait — sur un petit corpus, recall@k sature et ne détecte rien

Le corpus applicatif est celui d'un portfolio, et la Charte §4.2 interdit d'inventer une
volumétrie client. Sur un corpus de fixtures de quelques dizaines de chunks interrogé avec un
`topK` de 5 à 10, une requête pertinente retourne presque toujours le chunk attendu : recall@k
plafonne au voisinage de 1 et **cesse de discriminer**. La métrique n'est pas fausse, elle est
inerte — elle ne peut plus baisser, donc elle ne signale plus rien.

Ce qui reste discriminant sur un petit corpus, ce sont les cas dont la réponse attendue est
**l'absence de résultat** :

- une question dont la réponse n'est dans aucun document : le système doit refuser, pas produire
  une réponse plausible à partir de chunks faiblement similaires ;
- une question dont la réponse est dans un document d'un autre tenant : aucun candidat ne doit
  survivre au post-filtrage ;
- une question dont la réponse est dans un document `restricted` : aucun chunk ne doit entrer dans
  le `retrievalContext`, y compris pour le propriétaire (`V2-ADR-017`).

Ces cas ne saturent pas : ils produisent un verdict binaire qui échoue franchement lorsque la
chaîne de filtrage régresse. Sur ce corpus, **ils portent l'essentiel du pouvoir de détection**.

## Ce qu'aucun ADR n'a décidé

| ADR | Ce qu'il décide | Ce qu'il laisse ouvert |
|---|---|---|
| `V2-ADR-003` | cinq métriques et un dataset versionné | leur nature, leur chemin, leur régime de verdict |
| `V2-ADR-013` | la bascule est conditionnée à une mesure | quelle mesure, quel écart, quel déterminisme |
| `V2-ADR-010` | l'index est reconstruit et vérifié | contre quelle référence la reconstruction est admise |
| `V2-ADR-012` | le fallback de modèle est un mécanisme | comment deux modèles se comparent |

## Options — nature du verdict

### Option A — Seuils absolus par métrique

Fixer dans l'ADR des valeurs planchers (recall@5, precision@5, groundedness).

**Rejet.** C'est le défaut établi plus haut : sur un dataset auto-rédigé, le plancher mesure la
difficulté choisie. S'y ajoute que toute valeur inscrite ici serait arbitraire — aucun corpus de
référence public ne permet de la justifier, et la Charte interdit d'inventer une exigence client
pour l'étayer.

### Option B — Non-régression contre une baseline versionnée

Le verdict est un écart maximal toléré entre l'exécution courante et une baseline établie sur le
même dataset et le même corpus de fixtures.

**Avantages :** mesure ce qui est imputable au système. Répond littéralement à ce que
`V2-ADR-013`, `V2-LLD-006` §14.2 et `run_rag_eval.py --baseline` demandent déjà. Le verdict est
reproductible sur les métriques déterministes.

**Limites :** ne dit rien de la qualité absolue du système. Une baseline médiocre reste médiocre,
et sa dégradation seule est détectée. Exige un régime d'amorçage : la première exécution n'a rien
à quoi se comparer.

### Option C — Verdict humain sur rapport publié

Publier les métriques sans verdict automatique, la décision revenant au relecteur.

**Rejet.** `V2-LLD-006` §16 spécifie un statut `PASS`/`FAIL` produit par un script, et `V2-ADR-013`
fait de l'écart une condition d'exécution d'une bascule. Un verdict humain ne peut pas conditionner
une étape automatisée, et la revue reste possible en complément d'un verdict mécanique.

## Décision — nature du verdict

Retenir **l'option B**.

> **Le gate est la non-régression contre une baseline versionnée. Aucun seuil absolu de qualité
> n'est inscrit dans le corpus.**

Trois précisions en découlent.

**Les seuls seuils absolus admis portent sur des propriétés binaires de sûreté** — zéro chunk
cross-tenant, zéro chunk `restricted` dans un `retrievalContext`, zéro citation non résolvable.
Ce ne sont pas des métriques de qualité mais des preuves déjà exigées par `V2-ADR-006`,
`V2-ADR-017` et `V2-ADR-003` : leur valeur admissible est zéro, et elle n'est pas négociable par
une baseline. Une baseline ne peut jamais entériner une violation d'isolation.

**L'écart toléré est une donnée de configuration versionnée**, pas une constante de cet ADR. Il est
déclaré avec la baseline et évolue avec elle, sous revue. Cet ADR décide qu'un écart existe et
qu'il est appliqué ; sa valeur initiale est fixée en `V2-LLD-009` à partir de la dispersion
observée sur les premières exécutions, non postulée.

**Le régime d'amorçage est explicite.** La première exécution sur un couple (dataset, corpus de
fixtures, espace d'embedding) **établit** la baseline et ne peut pas échouer sur les métriques de
qualité — elle reste soumise aux propriétés binaires de sûreté. Sans ce régime, le gate serait
inapplicable au jour de sa création, et l'engagement de `V2-LLD-002` §16 serait vide.

## Décision — deux datasets, deux régimes

Le corpus parle d'« un dataset ». La séparation des natures impose d'en distinguer deux, portés
par un même corpus de fixtures.

| | Dataset de retrieval | Dataset de génération |
|---|---|---|
| Entrée | question | question + contexte figé |
| Sortie observée | liste de références de chunk | texte de réponse |
| Métriques | recall@k, precision@k, couverture des citations | taux de refus, groundedness |
| Appel de génération | non | oui |
| Déterminisme | oui, à index constant | non |
| Exécution | intégration continue, à chaque changement du pipeline | planifiée, hors CI bloquante |
| Verdict | **bloquant** (non-régression + propriétés binaires) | **publié, non bloquant** |

Le dataset de génération fournit son contexte **figé** plutôt que de l'obtenir par retrieval : sans
cela, une variation de la réponse ne serait pas imputable — elle pourrait venir du retrieval comme
du modèle. Figer le contexte isole la génération, au prix de ne pas mesurer la chaîne complète ;
cette mesure de bout en bout relève des tests E2E de `V2-LLD-009`, avec son propre régime.

C'est cette séparation qui rend l'engagement de `V2-ADR-013` exécutable : la bascule d'un index est
conditionnée au **seul** dataset de retrieval, déterministe et reproductible.

## Décision — le juge de groundedness

La groundedness demande de décider si une affirmation est étayée par les sources fournies. Trois
mécanismes sont possibles, et ils n'ont pas le même statut.

| Mécanisme | Automatisable | Coût | Validité |
|---|---|---|---|
| Relecture humaine | non | élevé, ne passe pas à l'échelle | référence, mais non rejouable |
| Modèle juge | oui | un appel par cas | **le juge est lui-même à valider** |
| Couverture des citations | oui | nul | mécanique, mais partielle |

> **La couverture des citations est bloquante ; la groundedness sémantique est mesurée et publiée,
> jamais bloquante.**

La couverture des citations est vérifiable sans jugement sémantique : chaque référence citée
existe, appartient au tenant, pointe vers un document autorisé et vers un chunk effectivement
présent dans le `retrievalContext`. C'est une propriété mécanique, déterministe, et elle est déjà
exigée comme preuve par `V2-ADR-003`.

La groundedness est mesurée par un modèle juge, et son verdict n'est pas rendu bloquant parce que
**le juge n'est pas validé** : rien n'établit sa concordance avec un jugement humain sur ce corpus,
et il subit le même cycle de vie de modèle que `V2-ADR-012` décrit. Rendre bloquante une mesure
dont l'instrument n'est pas étalonné remplacerait une incertitude par une fausse certitude. Le juge
est étalonné par échantillonnage humain sur un sous-ensemble ; tant que cette concordance n'est pas
mesurée, la métrique informe sans arbitrer.

Le modèle juge est un modèle Bedrock distinct de celui qui produit la réponse évaluée. Un modèle
qui juge sa propre sortie n'apporte pas d'information indépendante.

Étant un modèle Bedrock, le juge subit les statuts de cycle de vie de `V2-ADR-012` : son
indisponibilité est un état prévu, pas une panne. Dans ce cas la groundedness est **absente du
rapport et explicitement marquée non mesurée**, et l'exécution conserve le verdict de ses autres
métriques. Un juge indisponible ne produit jamais de `FAIL` : ce serait faire dépendre un verdict
d'un instrument dont cet ADR a déjà écarté le caractère bloquant.

## Décision — composition du dataset de retrieval

Quatre familles de cas sont obligatoires. Les deux dernières sont ce qui rend le dataset utile sur
un corpus de faible volumétrie.

| Famille | Entrée | Attendu | Ce qu'elle détecte |
|---|---|---|---|
| Positive | question dont la réponse est dans le corpus | le chunk attendu figure dans les `k` premiers | régression de rappel, dérive d'espace |
| Négative de corpus | question sans réponse dans le corpus | `status = skipped`, `reason = no_match` | production d'une réponse sans source |
| Négative d'autorisation | question dont la réponse est dans un document d'un autre tenant, ou non partagé | aucun candidat retenu, `reason = filtered_out` | régression du post-filtrage |
| Négative d'indexabilité | question dont la réponse est dans un document `restricted` | aucun chunk dans le `retrievalContext`, y compris pour le propriétaire ; `reason` selon la sous-famille (ci-dessous) | régression de `V2-ADR-017` |

Les deux dernières familles s'appuient sur la distinction `no_match` / `filtered_out` que
`V2-LLD-002` §6.2.1 a déjà établie : elle cesse d'être un simple signal d'observabilité pour
devenir **l'attendu d'un cas de test**. Un cas d'autorisation qui produirait `no_match` au lieu de
`filtered_out` échoue, même si aucun contenu n'a fuité — le filtre n'a pas travaillé, et la
prochaine régression passerait inaperçue.

La famille négative d'indexabilité se décline pour la même raison en deux sous-familles, toutes
deux obligatoires, dont l'attendu diffère :

- un document `restricted` **dès son ingestion**, donc jamais indexé : le retrieval ne produit aucun
  candidat, `reason = no_match` ;
- un document indexé puis **reclassifié en `restricted`** (`V2-ADR-017`) : le retrieval produit un
  candidat que le post-filtrage écarte, `reason = filtered_out`.

C'est la seconde qui porte la détection. Elle seule établit que le post-filtrage a travaillé sur un
chunk réellement présent dans le résultat brut du retrieval ; la première ne vaut que tant que
l'indexation reste correcte, et deviendrait silencieusement vide si un défaut d'indexation la
satisfaisait pour la mauvaise raison.

Le corpus de fixtures doit donc contenir au moins deux tenants, un document non partagé, un document
`restricted` dès son ingestion et un document reclassifié en `restricted` après indexation. Cette
composition est une contrainte de fixtures, pas de production.

## Décision — ce à quoi une baseline est attachée

Une baseline n'est comparable qu'à identité de ce qui la conditionne. Elle est un artefact
versionné portant, au minimum :

```text
datasetVersion       version du dataset de cas
fixturesVersion      version du corpus de fixtures indexé
embeddingSpaceId     espace d'embedding de l'index évalué   (V2-ADR-013)
chunkerVersion       stratégie de découpage                 (V2-ADR-013)
topK                 profondeur de retrieval évaluée
metrics              valeurs mesurées par métrique
```

Chacun des cinq champs d'identification a un effet tranché sur la comparabilité.

| Champ modifié | Effet | Raison |
|---|---|---|
| `datasetVersion` | **invalide** | les cas mesurés changent ; la nouvelle exécution établit une baseline sous le régime d'amorçage |
| `fixturesVersion` | **invalide** | le corpus interrogé change ; même régime |
| `topK` | **invalide** | la grandeur change — `recall@5` et `recall@10` ne sont pas deux valeurs d'une même métrique ; la comparaison n'a lieu qu'à `topK` égal |
| `embeddingSpaceId` | **n'invalide pas** | c'est précisément l'écart que l'étape 3 de `V2-ADR-013` veut mesurer |
| `chunkerVersion` | **n'invalide pas** | c'est l'écart que `V2-ADR-013` veut mesurer entre deux stratégies de découpage |

La comparaison entre deux espaces d'embedding, à dataset et fixtures identiques, est exactement
l'étape 3 de la séquence de bascule de `V2-ADR-013`.

Cette asymétrie est la raison d'être de la structure : elle rend impossible de masquer une
régression du pipeline en modifiant le dataset, la profondeur de retrieval ou les fixtures, tout en
autorisant la comparaison qu'une migration d'embedding exige.

## Décision — comparaison entre modèles

`V2-ADR-012` renvoie ici l'évaluation comparative entre modèles de génération. La réponse est que
cet ADR **ne produit pas de classement de modèles**.

Le dataset de génération mesure des propriétés d'une réponse — refus lorsque les sources sont
insuffisantes, ancrage dans les sources citées — sur un contexte figé. Ces propriétés sont
comparables entre deux modèles, et cette comparaison est publiée. Elle ne constitue pas un
classement : un modèle n'est pas retenu parce qu'il obtient un meilleur score sur un dataset
interne de quelques dizaines de cas. `V2-ADR-012` décide un mécanisme de sélection et de fallback ;
cet ADR lui fournit une mesure, pas une décision.

## Décision — réalisation par phase

`V2-ADR-019` a délégué l'ingestion et le retrieval à Knowledge Bases pour la phase V2. La stratégie
d'évaluation ne change pas de nature, mais deux points d'application diffèrent.

| Aspect | Phase V2 (KB) | Phase V3 (applicatif) |
|---|---|---|
| Indexation des fixtures | data source KB dédiée à l'évaluation | pipeline d'ingestion (`V2-ADR-004`) |
| Point d'appel évalué | `Retrieve` via l'adapter, puis post-filtrage FastAPI | requête S3 Vectors via l'adapter |
| Isolation du corpus de fixtures | **base de connaissances distincte** de celle de production | index distinct |
| `embeddingSpaceId` de la baseline | celui de la base de connaissances d'évaluation | celui de l'index évalué |

L'isolation du corpus de fixtures dans une base de connaissances distincte est une conséquence du
troisième fait établi plus haut : partager la base de production ferait varier les fixtures à
chaque ingestion réelle. C'est une ressource supplémentaire à provisionner, dont le coût est celui
du stockage vectoriel des fixtures et des ingestions d'évaluation — faible, et à chiffrer dans
`V2-LLD-007`.

L'évaluation s'exécute **à travers l'adapter et le post-filtrage FastAPI**, jamais contre
`Retrieve` directement. Une évaluation qui court-circuiterait le post-filtrage ne pourrait pas
porter les familles négatives d'autorisation et d'indexabilité, qui sont précisément celles dont
dépend le pouvoir de détection sur ce corpus.

## Ce que cette décision ne change pas

- **Les métriques nommées par `V2-ADR-003`.** Les cinq sont conservées. Cet ADR les répartit en
  deux chemins et fixe lesquelles arbitrent.
- **La propriété du post-filtrage.** Il reste côté FastAPI (`V2-ADR-019`) ; l'évaluation le
  traverse au lieu de le contourner.
- **La séquence de bascule de `V2-ADR-013`.** Son étape 3 est conservée telle quelle ; cet ADR
  précise qu'elle porte sur le seul dataset de retrieval.
- **Les preuves de sûreté existantes.** Isolation cross-tenant, absence de résidu, résolution des
  citations restent des preuves à part entière, indépendantes de toute baseline.
- **L'interdiction de `RetrieveAndGenerate`.** Elle est renforcée : sans point de filtrage FastAPI
  entre retrieval et modèle, les familles négatives ne seraient pas observables.

## Écarts à corriger dans le corpus

Ces corrections découlent de l'acceptation de l'ADR et ne sont pas appliquées par lui.

| Document | Écart | Correction attendue |
|---|---|---|
| `V2-ADR-003` | « Qualité » : cinq métriques dans une même liste, régime de verdict absent | distinguer les métriques de retrieval des métriques de génération ; renvoyer le régime de verdict à cet ADR |
| `V2-ADR-013` | `V2-ADR-018` figure dans ses dépendances alors que cet ADR dépend de lui — **cycle** | retirer `V2-ADR-018` des dépendances de `V2-ADR-013` ; le sens 018 → 013 est le bon, la mention « bascule conditionnée à l'existence d'une mesure » restant dans le corps du texte |
| `V2-ADR-013` | étape 3 : « exécution du dataset d'évaluation » sans préciser lequel | préciser : dataset de retrieval uniquement, à `datasetVersion` et `fixturesVersion` constants |
| `V2-ADR-012` | l'évaluation comparative « relève de `V2-ADR-018` » | préciser qu'elle fournit une mesure publiée, non un classement de modèles |
| `V2-LLD-002` §1.1 et §1.2 | `ADR-018` résumé en une liste de cinq métriques | remplacer par les deux datasets, le régime de non-régression et les quatre familles de cas |
| `V2-LLD-002` §15.1 | les métriques de qualité sont listées comme un bloc « hors ligne » | séparer les métriques déterministes (CI) des métriques de génération (planifiées) |
| `V2-LLD-002` §16 | « métriques de qualité calculées » en statut `Gate`, sans critère | énoncer le critère : non-régression vs baseline, plus propriétés binaires à zéro ; ajouter le régime d'amorçage |
| `V2-LLD-006` §14.2 | « métriques dans la marge d'écart tolérée » sans définition de la marge | renvoyer à l'écart configuré avec la baseline ; préciser que la comparaison exige `fixturesVersion` constant |
| `V2-LLD-006` §16 | `run_rag_eval.py` produit `PASS`/`FAIL` sans régime d'amorçage | ajouter le mode d'établissement de baseline et les cinq champs d'attachement, avec leur effet respectif sur l'invalidation |
| `V2-LLD-006` §17.1 | « métriques qualité post-réhydratation dans marge d'éval » : bloquant `Oui` | préciser que seules les métriques déterministes sont bloquantes |
| `V2-LLD-006` §17.2 | le DR drill rejoue « le dataset d'éval » | préciser : dataset de retrieval sur le corpus de fixtures, indépendant du corpus restauré |
| `LLD-V2-INDEX-FR.md` | portée de `V2-LLD-009` : « pyramide, datasets, E2E… » | ajouter : valeur initiale de l'écart toléré, étalonnage du modèle juge, cadence des deux datasets |

## Préconditions

Quatre points doivent être établis avant implémentation. Aucun n'est bloquant pour la décision ;
chacun énonce sa conséquence s'il n'est pas satisfait.

1. **Déterminisme du `Retrieve` KB à index constant.** Vérifier que deux appels identiques sur un
   index inchangé retournent le même classement. Si le service introduit une variabilité, l'écart
   toléré doit absorber cette dispersion propre, mesurée sur des exécutions répétées avant tout
   changement du système — faute de quoi le gate produirait des échecs sans cause.
2. **Isolation du corpus de fixtures.** Vérifier qu'une base de connaissances d'évaluation distincte
   est provisionnable en `eu-west-3` sans coût fixe significatif. Si elle ne l'est pas, la solution
   conforme est un préfixe et une data source dédiés dans la base existante, avec un filtre de
   tenant d'évaluation — jamais le partage du corpus de production, qui invaliderait la baseline.
3. **Coût d'une exécution complète.** Mesurer le coût et la durée d'une exécution du dataset de
   retrieval, pour établir sa cadence en intégration continue. Si le coût interdit une exécution à
   chaque changement, le levier conforme est la réduction du nombre de cas positifs, jamais celle
   des familles négatives.
4. **Concordance du modèle juge.** Mesurer l'accord entre le verdict du modèle juge et un jugement
   humain sur un échantillon. Tant que cette concordance n'est pas établie, la groundedness reste
   publiée sans arbitrer ; si elle s'avère faible, la métrique est conservée comme indicateur et
   l'étalonnage devient une dette explicite.

## Périmètre exclu

- **La pyramide de tests, les tests E2E, de charge, de chaos et de sécurité** : `V2-LLD-009`. Cet
  ADR ne traite que l'évaluation de la qualité du RAG.
- **La valeur initiale de l'écart toléré** : fixée en `V2-LLD-009` à partir de la dispersion
  observée. Cet ADR décide qu'un écart existe et comment il est attaché, pas sa valeur.
- **Le contenu du dataset** — les questions et les documents de fixtures : artefact versionné,
  relevant de `V2-LLD-009`. Cet ADR en fixe la composition obligatoire, pas les cas.
- **Le choix des modèles** d'embedding et de génération : `V2-ADR-013` et `V2-ADR-012`. Cet ADR
  fournit une mesure ; il ne sélectionne pas.
- **Le reranking et la recherche hybride** : hors périmètre. Ils seraient évaluables par ce même
  mécanisme, à espace constant, s'ils étaient introduits.
- **La détection de contenu sensible dans les réponses** : `V2-ADR-008` pour les journaux,
  `V2-ADR-017` pour la classification des sources.
- **Les métriques d'exploitation du retrieval** — latence, taux de `degraded`, taux de `skipped` :
  `V2-LLD-002` §15.1. Ce sont des signaux de production, mesurés sur le corpus réel, distincts de
  l'évaluation de qualité sur fixtures.

## Conséquences

- Le corpus perd la promesse implicite d'un seuil de qualité absolu, et gagne un critère qui peut
  effectivement échouer. C'est le seul changement qui rend la gate de `V2-LLD-002` §16 opérante.
- Deux datasets et deux cadences remplacent un dataset unique. Le coût d'intégration continue est
  porté par le seul dataset déterministe ; la génération est évaluée sur une cadence planifiée.
- Un corpus de fixtures figé et versionné devient un artefact de premier rang, provisionné et
  indexé séparément du corpus de production. C'est une ressource et un coût nouveaux, faibles mais
  réels.
- La distinction `no_match` / `filtered_out` de `V2-LLD-002` §6.2.1 change de statut : d'un signal
  d'observabilité, elle devient l'attendu de deux familles de cas de test.
- Le corpus de fixtures porte une contrainte d'historique et non seulement de contenu : il doit
  contenir un document reclassifié en `restricted` après indexation. Son établissement comporte donc
  une étape de reclassification, et `fixturesVersion` identifie un état atteint par une séquence
  d'opérations, pas un simple jeu de fichiers.
- `V2-ADR-013` obtient une condition de bascule exécutable et déterministe, ce que sa formulation
  actuelle ne garantissait pas.
- La groundedness cesse d'être présentée comme un critère et devient un indicateur dont
  l'instrument est explicitement non étalonné. C'est une perte de garantie apparente et un gain
  d'honnêteté vérifiable.
- Le régime d'amorçage rend la première exécution non bloquante sur la qualité. C'est une fenêtre
  assumée : elle ne suspend aucune propriété binaire de sûreté.
- Un cycle de dépendances existant est mis au jour : `V2-ADR-013` dépend de `V2-ADR-018`, qui
  dépend de lui. Il est corrigé dans le sens 018 → 013, comme les quatre autres cycles du corpus.

## Preuves attendues

- **une régression injectée dans la chaîne de post-filtrage fait échouer le dataset de retrieval** —
  preuve centrale : sans elle, rien n'établit que le gate peut échouer ;
- deux exécutions consécutives du dataset de retrieval sur un index inchangé produisent des
  métriques identiques, ou une dispersion bornée et mesurée ;
- une exécution sur un couple (dataset, fixtures, espace) inédit établit une baseline et rend
  `PASS` sans comparaison, tout en échouant si une propriété binaire de sûreté est violée ;
- un changement de `datasetVersion` invalide la baseline et déclenche le régime d'amorçage, sans
  qu'un écart de qualité soit rapporté ;
- un changement de `topK` invalide la baseline et n'est jamais comparé à une baseline d'un `topK`
  différent ;
- un changement d'`embeddingSpaceId` **n'invalide pas** la baseline et produit un écart mesuré,
  conformément à l'étape 3 de `V2-ADR-013` ;
- un cas de la famille négative d'autorisation produit `reason = filtered_out` et non `no_match` ;
  l'inversion des deux fait échouer le cas ;
- les deux sous-familles négatives d'indexabilité sont couvertes : un document `restricted` dès son
  ingestion produit `reason = no_match`, un document indexé puis reclassifié en `restricted` produit
  `reason = filtered_out` ; dans les deux cas aucun chunk n'entre dans le `retrievalContext`, y
  compris pour son propriétaire (`V2-ADR-017`) ;
- un cas de la famille négative de corpus vérifie qu'aucune réponse n'est produite sans source, et
  que le refus est bien celui de `no_match` ;
- la couverture des citations est vérifiée mécaniquement : chaque référence citée existe, appartient
  au tenant et pointe vers un chunk présent dans le `retrievalContext` ;
- une baseline entérinant une violation d'isolation est impossible : le cas de sûreté échoue
  indépendamment de toute comparaison ;
- l'évaluation s'exécute à travers le post-filtrage FastAPI, vérifié par le fait qu'une
  désactivation du post-filtrage fait échouer les familles négatives ;
- le corpus de fixtures est indexé dans une ressource distincte du corpus de production, vérifié
  par le fait qu'une ingestion de production ne modifie aucune métrique de baseline ;
- la concordance du modèle juge avec un jugement humain est mesurée et publiée sur un échantillon,
  et la groundedness ne produit aucun `FAIL` tant que cette concordance n'est pas établie ;
- l'indisponibilité du modèle juge — statut de fin de vie au sens de `V2-ADR-012` — laisse la
  groundedness marquée non mesurée dans le rapport, sans `FAIL` et sans effet sur le verdict des
  métriques déterministes ;
- le DR drill de `V2-LLD-006` §17.2 rejoue le dataset de retrieval sur les fixtures et non sur le
  corpus restauré, et son verdict est indépendant du volume restauré.

## Références

- `V2-ADR-003` — métriques nommées, dataset versionné, citations résolvables ;
- `V2-ADR-006` — isolation cross-tenant, métadonnées filtrables obligatoires ;
- `V2-ADR-010` — index vectoriel comme état dérivé, DR drill ;
- `V2-ADR-012` — cycle de vie des modèles, fallback, absence de classement ;
- `V2-ADR-013` — `embeddingSpaceId`, `chunkerVersion`, séquence de bascule et son étape 3 ;
- `V2-ADR-017` — classification décidée sur `documents`, niveau `restricted` non indexable ;
- `V2-ADR-019` — post-filtrage tenant et ACL côté FastAPI, interdiction de `RetrieveAndGenerate` ;
- `V2-LLD-002` §6.2, §6.2.1, §15.1, §16 — chaîne de retrieval, causes de `skipped`, métriques ;
- `V2-LLD-006` §14.2, §16, §17.1, §17.2 — réhydratation, outillage d'évaluation, DR drill ;
- Amazon Bedrock Knowledge Bases — `Retrieve`, data source par préfixe S3, base de connaissances
  comme unité de configuration d'embedding ;
- Amazon Bedrock — modèles de génération, variabilité de sortie et cycle de vie.
