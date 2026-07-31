# V2-ADR-012 — Modèles Bedrock, profils d'inférence et stratégie de fallback

- **Statut :** Accepted
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-005` (l'adapter reçoit le modèle en paramètre), `V2-ADR-011` (règle de
  bascule vis-à-vis du flux), `V2-ADR-008` (signaux de throttling et de coût)
- **Préconditions à prouver avant implémentation :** identifiants d'invocation effectivement
  disponibles en `eu-west-3` et liste nominative des régions de destination du profil EU (voir
  « Préconditions »).
- **Documents impactés :** `V2-LLD-003` §3.2, §5.2.1, §5.4, §8.1, §9.1, §12.1, §13.1 ;
  `V2-ADR-011` (événement `done`) ; `V2-LLD-007` (attribution des coûts) ; Charte ou `V2-ADR-006`
  (exigence de résidence des données, point ouvert) — voir « Écarts à corriger dans le corpus ».

## Contexte

`V2-ADR-005` a fixé une exigence structurante : le modèle et sa configuration sont des paramètres
de l'adapter, jamais des constantes du domaine. `V2-LLD-003` en a dérivé un champ
`AgentConfig.model_id`, une dérivation de `maxTokens` depuis la fenêtre de contexte du modèle
(§5.2.1), et une mitigation temporaire du throttling explicitement présentée comme révisable
(§5.4). Trois sections portent le marqueur `⚠ ADR MANQUANT` en attente de cet ADR.

Cet ADR tranche quatre questions distinctes que le corpus traite aujourd'hui comme une seule :

1. **quel identifiant** le domaine passe à Bedrock pour invoquer un modèle ;
2. **comment les coûts** de cette invocation sont attribués à un environnement et à un tenant ;
3. **quelle stratégie de repli** en cas de throttling ou d'indisponibilité, et sur quel signal ;
4. **comment le cycle de vie** des modèles est gouverné, puisqu'il est imposé de l'extérieur.

La confusion entre ces quatre questions est la raison pour laquelle `model_id` est aujourd'hui un
`str` sans contrat : le corpus suppose qu'un modèle se désigne par son nom. En `eu-west-3`, ce
n'est pas le cas.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-005` | le modèle est un paramètre injecté, jamais une constante du domaine |
| `V2-LLD-003 §5.2.1` | `maxTokens` est dérivé de la fenêtre de contexte du modèle effectif |
| `V2-LLD-003 §5.4` | une `ThrottlingException` isolée ne doit pas casser une conversation |
| `V2-LLD-003 §8.2` | toute sortie hors budget produit un `AgentResult` structuré, jamais une exception |
| `V2-ADR-011` | le flux SSE déclare le mode servi et se termine par `done`, `cancelled` ou `error` |
| (point ouvert) | aucune exigence formelle de résidence des données dans l'UE n'est documentée dans le corpus ; l'interdiction du profil global en `staging` et `production` est donc une précaution, pas une conséquence — voir « Option C » |
| `V2-ADR-008` | le throttling et le coût par invocation sont observables et corrélés |

## Le fait technique déterminant — un modèle récent ne s'invoque pas par son nom

En région européenne, l'appel de `Converse` ou `ConverseStream` avec l'identifiant de modèle de
fondation d'un modèle Anthropic récent échoue :

```text
ValidationException: Invocation of model ID anthropic.claude-<modèle>-<version>:0
with on-demand throughput isn't supported. Retry your request with the ID or ARN of
an inference profile that contains this model.
```

Ce n'est pas une limite de quota ni une erreur de configuration : les modèles récents ne sont
**pas offerts en débit à la demande sur une région unique**. Leur capacité est mutualisée entre
plusieurs régions, et l'identifiant qui donne accès à cette capacité est un **profil d'inférence**,
pas un modèle.

Il en résulte cinq familles d'identifiants d'invocation, et non une :

| Identifiant | Forme | Débit à la demande | Portée des données |
|---|---|---|---|
| Modèle de fondation régional | `anthropic.<modèle>:0` | selon le modèle et la région | région d'appel |
| Profil géographique EU | `eu.anthropic.<modèle>:0` | oui | régions UE du profil |
| Profil global | `global.anthropic.<modèle>:0` | oui | non borné géographiquement |
| Profil applicatif | ARN `inference-profile/<id>` | hérité de ce qu'il encapsule | héritée |
| Débit provisionné | ARN `provisioned-model/<id>` | non — capacité réservée | région d'appel |

**Conséquence directe sur le corpus.** `V2-LLD-003 §3.2` donne pour exemple de `model_id` un
identifiant de modèle de fondation nu, et `§12.1` fait de même pour `AGENT_MODEL_ID`. Appliqués
littéralement en `eu-west-3`, ces deux exemples produisent l'échec ci-dessus **au premier appel**.
Le défaut est de la même nature que celui identifié par `V2-ADR-011` sur le type d'API Gateway :
une prémisse plausible, jamais confrontée à la contrainte régionale.

Le champ est également mal nommé. Ce que le domaine transporte n'est pas un modèle mais un
**identifiant d'invocation**, dont la forme est un détail d'infrastructure que le domaine ne doit
pas interpréter.

## Choix de l'identifiant d'invocation

### Option A — Modèle de fondation régional

Conserver `anthropic.<modèle>:0` et appeler le point de terminaison `bedrock-runtime` de
`eu-west-3`.

Ne fonctionne pas pour les modèles récents, qui sont précisément ceux que la V2 cible. Contraindrait
la V2 à une génération de modèles antérieure pour une raison purement contingente. Le seul avantage
— une seule région traverse le plan de données — est réel mais insuffisant.

### Option B — Profil d'inférence géographique EU

Utiliser `eu.anthropic.<modèle>:0`. Bedrock répartit la charge entre les régions UE du profil.

Débit supérieur à une région unique, quota de *cross-Region inference* distinct du quota régional,
toutes les régions de destination sont dans l'Union. Le plan de données peut traverser plusieurs
régions UE, ce qui doit être assumé explicitement plutôt que découvert.

### Option C — Profil d'inférence global

Utiliser `global.anthropic.<modèle>:0`. Débit maximal et tarif inférieur d'environ 10 % sur les
tokens d'entrée et de sortie par rapport au profil géographique.

Le routage n'est pas borné géographiquement : les invites et les réponses peuvent être traitées
hors de l'Union, et les données conservées pour la détection d'abus le sont dans la région de
destination. Cette exposition est de deux ordres :

- **exposition CLOUD Act directe** : le traitement en région US place les données sous portée
  immédiate de la loi américaine, sans la friction procédurale que confère un traitement en
  région EU ;
- **risque de perte de base légale** : si l'EU-US Data Privacy Framework était invalidé (scénario
  « Schrems III »), tout transfert vers une région non-EU deviendrait sans base légale
  immédiatement.

**Option C est autorisée en environnement `dev` et `test`**, où les données traitées ne sont pas
des données personnelles de production et où l'avantage économique (~10 %) et la capacité accrue
justifient le compromis. Attention : les métriques de latence collectées dans ces environnements
sont non représentatives de la production (TTFT variable selon la région de destination effective).

**Option C est interdite en `staging` et `production`** par précaution opérationnelle, en
l'absence d'exigence formelle de résidence dans le corpus. Cette exigence est à instruire dans
la Charte ou dans `V2-ADR-006` — point ouvert reporté.

### Option D — Débit provisionné

Réserver de la capacité. Supprime le throttling par construction, mais impose un engagement ferme
et un coût plancher indépendant de l'usage — disproportionné pour une V2 dont le trafic n'est pas
encore mesuré.

## Décision — identifiant d'invocation

**Option B, encapsulée dans un profil d'inférence applicatif.**

L'identifiant nominal est un **profil d'inférence applicatif** dont la cible est le **profil
géographique EU** du modèle retenu. Le domaine reçoit un ARN opaque ; il n'interprète jamais sa
forme.

Le champ `AgentConfig.model_id` est renommé **`invocation_id`** et documenté comme identifiant
d'invocation Bedrock — modèle de fondation, profil géographique, profil applicatif ou débit
provisionné. Cela vaut décision sur trois points :

- le domaine ne teste pas le préfixe de l'identifiant et ne dérive aucune logique de sa forme ;
- passer du profil géographique au débit provisionné est un changement de configuration SSM,
  sans modification du domaine ni du contrat ;
- l'Option C reste techniquement accessible par un simple changement de valeur. Elle est
  **autorisée en `dev` et `test`**, et **interdite en `staging` et `production`** — voir
  « Option C » dans les choix ci-dessus. Cette distinction doit être un contrôle sur la valeur
  SSM par environnement, pas une convention.

L'Option D n'est pas retenue en V2 mais n'est pas fermée : elle devient la réponse au cas où le
throttling deviendrait structurel plutôt qu'occasionnel, et sa condition de déclenchement est une
mesure, pas une intuition — voir « Preuves attendues ».

## Attribution des coûts

Le profil applicatif porte des étiquettes de répartition de coûts qui remontent dans Cost Explorer
et dans les rapports de coût et d'usage. Deux propriétés en découlent, et une limite.

**Un profil applicatif est une enveloppe de facturation, pas une réservation de capacité.** Il
n'ouvre pas de quota distinct de celui du profil système qu'il encapsule. Multiplier les profils
applicatifs n'augmente donc pas le débit disponible, et ne constitue jamais une réponse au
throttling.

**Granularité retenue : un profil applicatif par environnement et par rôle d'usage** (conversation,
et le cas échéant ingestion ou évaluation), et non un profil par tenant. Un profil par tenant ne
passe pas l'échelle : il crée une ressource par tenant, à provisionner, étiqueter et détruire au
rythme des tenants.

**Le coût par tenant est donc dérivé, pas facturé.** `V2-LLD-003 §3.2` expose déjà
`input_tokens` et `output_tokens` par invocation, et `§10.2` prévoit une table `modèle → tarifs`.
Le coût par tenant est calculé à partir de ces compteurs, avec deux conséquences à assumer : c'est
une **estimation**, réconciliable avec la facture au niveau de l'environnement mais pas au niveau du
tenant ; et le champ `requestMetadata` de `Converse` n'y contribue pas, puisqu'il n'est pas une
étiquette de répartition de coûts et n'apparaît ni dans Cost Explorer ni dans les rapports d'usage.
Il reste utile pour la corrélation, pas pour la facturation.

## Choix de la stratégie de fallback

Le throttling Bedrock est fréquent en production sur les modèles récents, et son quota est
**appliqué au niveau du compte pour un couple modèle et région** — donc partagé par tous les
appelants du compte, y compris des charges de travail qui ne relèvent pas de ce système.

### Option A — Aucun fallback (statu quo de `V2-LLD-003 §5.4`)

Deux tentatives exponentielles bornées par la deadline, puis `MODEL_THROTTLED`. Simple, sans
dégradation cachée. Insuffisant lorsque le quota est saturé pendant plusieurs secondes.

### Option B — Modèle de repli déclaré

Un second identifiant d'invocation, sur un modèle distinct, donc sur un **quota distinct**. C'est
la seule option qui ouvre réellement de la capacité, puisque le quota est indexé sur le modèle.

Elle change la qualité de la réponse, ce qui ne peut pas rester silencieux, et impose une
contrainte de compatibilité de capacité examinée plus bas.

### Option C — Second chemin de quota sur le même modèle

Le même modèle par un autre profil. Le seul autre profil existant est le profil global, écarté par
la décision sur la résidence. Sans objet ici.

### Option D — Rejet contrôlé

Erreur typée immédiate et signal de réessai au client, sans dégradation. Honnête et peu coûteux,
mais n'apporte aucune disponibilité par lui-même.

## Décision — fallback

**Option B comme repli nominal, Option D comme état terminal, jamais de bascule en cours de flux.**

La séquence est bornée et déterministe :

1. `ThrottlingException` sur l'identifiant primaire : jusqu'à deux tentatives exponentielles avec
   jitter, chacune conditionnée par `deadlineEpochMs` — reprise de `V2-LLD-003 §5.4` sans
   modification ;
2. échec des tentatives et **aucun token de sortie encore émis** : une tentative unique sur
   l'identifiant de repli, si celui-ci est configuré et compatible ;
3. échec du repli, ou repli non configuré, ou **au moins un token déjà émis** : `AgentResult.error =
   AgentError(MODEL_THROTTLED, …)`, `degraded = true` — Option D ;
4. aucun autre code d'erreur Bedrock ne déclenche de repli. Une erreur de validation ou
   d'autorisation est un défaut de configuration : la masquer par un repli la rend indétectable.

### La règle du premier token

**Le repli est interdit dès qu'un token de sortie a été émis vers le client.** Deux modèles
différents produisant chacun un fragment de la même réponse produisent une réponse incohérente,
qu'aucun test ne rattrape et qu'aucun utilisateur ne peut interpréter. Cette règle est une
conséquence directe du streaming décidé par `V2-ADR-011` : elle rend le repli invisible quand il
réussit, et strictement borné quand il est trop tard.

### La contrainte de compatibilité de capacité

Un identifiant de repli n'est admissible que s'il satisfait, **vérifié au démarrage et non à
l'exécution** :

- `Converse` et `ConverseStream` supportés — sans quoi `V2-ADR-011` ne tient plus ;
- appel de tools supporté — sans quoi `V2-LLD-003 §6` ne tient plus ;
- fenêtre de contexte **supérieure ou égale** à celle du modèle primaire.

Le troisième point est le plus facile à manquer. `maxTokens` est dérivé au démarrage de la fenêtre
de contexte du modèle primaire (`V2-LLD-003 §5.2.1`). Un repli à fenêtre plus petite rend ce budget
invalide : l'invocation de repli serait rejetée par Bedrock pour dépassement de contexte, au moment
précis où le système tente de préserver la conversation. Deux réponses seulement sont acceptables :
refuser un repli à fenêtre inférieure au démarrage — c'est la règle retenue — ou redériver
`maxTokens` par identifiant, ce qui déplace le budget d'une constante de démarrage vers un état
d'exécution et complique la traçabilité. La première est retenue.

### Le repli doit être exercé

Le cycle de vie Bedrock prévoit qu'un client existant peut **perdre l'accès à un modèle en état
`Legacy` après quinze jours sans invocation**. Un modèle de repli n'est, par définition, presque
jamais appelé : il est donc le candidat naturel à cette perte d'accès, et elle se manifesterait
exactement lorsqu'il est nécessaire.

Le repli fait donc l'objet d'une **invocation de contrôle périodique**, à intervalle strictement
inférieur à ce seuil, hors chemin de requête, dont l'échec est une alerte et non un incident
silencieux. Un repli non exercé n'est pas un repli.

### Signal de déclenchement

Le déclenchement est **réactif** en V2 : il part de la `ThrottlingException` reçue. Les métriques
CloudWatch de consommation estimée de quota et de latence du premier token permettent un
déclenchement **préventif**, avant rejet ; ce n'est pas retenu en V2 — cela suppose une base de
mesure que le système n'a pas encore — mais c'est la trajectoire, et les métriques nécessaires sont
celles que `V2-ADR-008` instrumente déjà.

### Le repli est déclaré au client

Le modèle effectivement servi est **déclaré**, jamais deviné. L'événement `done` de `V2-ADR-011`
transporte un champ supplémentaire identifiant l'invocation servie, et `degraded` vaut `true`
lorsque la réponse provient du repli. Un repli non déclaré est une dégradation silencieuse de
qualité, ce que `V2-LLD-003 §8.2` interdit.

## Cycle de vie des modèles et gouvernance de la configuration

Le cycle de vie d'un modèle est imposé par le fournisseur, pas par le système : état `Active`, puis
`Legacy` avec un préavis d'au moins six mois avant la fin de vie, une phase d'accès étendu pour les
modèles dont la fin de vie est postérieure au 1er février 2026, puis échec des appels.

Trois conséquences de gouvernance :

- **l'identité du modèle est une donnée de configuration, pas une décision d'architecture.** Cet
  ADR ne nomme volontairement aucune version de modèle : toute liste figée ici serait périmée avant
  la fin de la V2. Les identifiants vivent dans SSM Parameter Store, conformément à
  `V2-LLD-003 §12.1` ;
- **l'état de cycle de vie est vérifié automatiquement**, par une sonde périodique interrogeant
  l'état du modèle configuré. Le passage en `Legacy` du modèle primaire **ou** du modèle de repli
  produit une alerte. Un préavis de six mois n'est utile que s'il est reçu ;
- **la table `modèle → fenêtre_contexte` de `V2-LLD-003 §5.2.1` est indexée sur l'identifiant
  d'invocation**, pas sur un nom de modèle, et couvre le primaire et le repli.

## Contrat IAM

Un profil d'inférence géographique impose une politique **strictement plus large** qu'un modèle
régional, ce que `V2-LLD-003 §9.1` ne prévoit pas en ne mentionnant que « l'ARN du modèle » :

| Ressource à autoriser | Forme | Raison |
|---|---|---|
| Profil d'inférence | `arn:aws:bedrock:<région>:<compte>:inference-profile/<id>` | porte le compte et la région |
| Modèle, région source | `arn:aws:bedrock:<région>::foundation-model/<modèle>` | appel local |
| Modèle, chaque région de destination | `arn:aws:bedrock:<dest>::foundation-model/<modèle>` | exécution déportée |

Trois points en découlent :

- **toutes les régions de destination du profil doivent être énumérées.** Une région absente de la
  politique produit un échec intermittent, dépendant du routage — le mode de panne le plus coûteux
  à diagnostiquer ;
- **la liste des destinations appartient à AWS, pas au système.** Son élargissement ultérieur peut
  invalider une politique correcte au moment de sa rédaction. La politique doit être maintenue et
  sa dérive détectée ;
- **le repli ajoute ses propres ressources** : profil et modèle de repli dans toutes ses régions de
  destination. Un repli sans permission est un repli inexistant, et son test de contrôle périodique
  est ce qui le révèle.

Les actions d'invocation restent `bedrock:InvokeModel` et `bedrock:InvokeModelWithResponseStream` —
`Converse` et `ConverseStream` s'y ramènent.

Deux actions de lecture s'y ajoutent, qu'aucune invocation ne couvre :

| Action | Ressource | Raison |
|---|---|---|
| `bedrock:GetInferenceProfile` | le profil applicatif configuré | résoudre le profil vers les modèles qu'il encapsule |
| `bedrock:GetFoundationModel` | chaque modèle ainsi résolu | lire son état de cycle de vie |

Elles sont la conséquence directe de deux décisions de cet ADR. L'identifiant d'invocation est
**opaque** : la sonde de cycle de vie ne peut donc pas déduire de sa forme quel modèle surveiller,
elle doit résoudre le profil. Et le cycle de vie est **vérifié automatiquement** : sans ces deux
lectures, la sonde décidée plus bas n'est pas implémentable, et le préavis de six mois n'est reçu
par personne. Ces actions appartiennent à l'identité de la sonde, non à celle du chemin de
requête — le domaine ne les utilise jamais.

## Écarts à corriger dans le corpus

À corriger dans le même lot que l'acceptation de cet ADR :

| Document | Passage | Correction attendue |
|---|---|---|
| `V2-LLD-003 §3.2` | `model_id: str` avec un modèle de fondation nu en exemple, et le marqueur `⚠ ADR MANQUANT` sur `inference_profile_id` / `fallback_model_id` | renommer en `invocation_id`, ajouter `fallback_invocation_id: Optional[str]`, retirer le marqueur |
| `V2-LLD-003 §5.4` | mitigation temporaire présentée comme révisable | remplacer par la séquence décidée, dont la règle du premier token |
| `V2-LLD-003 §8.1` | ligne « Bedrock throttling : voir ADR-012 (backlog) » | renseigner le comportement et la déclaration au client |
| `V2-LLD-003 §5.2.1` | table `modèle → fenêtre_contexte` | indexer sur l'identifiant d'invocation ; couvrir le repli et la règle de refus |
| `V2-LLD-003 §9.1` | « restreindre chaque action par `Resource` (ARN du modèle) » | ajouter le profil et les modèles des régions de destination |
| `V2-LLD-003 §12.1` | `AGENT_MODEL_ID` avec un modèle de fondation nu | renommer, corriger l'exemple, ajouter l'identifiant de repli |
| `V2-LLD-003 §13.1` | deux lignes bloquantes sur `V2-ADR-012 (backlog)` | lever le blocage |
| `V2-ADR-011` | contrat de l'événement `done` | ajouter l'identifiant d'invocation servie (extension additive) |
| `LLD-V2-INDEX-FR.md` | `V2-LLD-007` dépend de `V2-ADR-012` | aucune correction ; la dépendance devient satisfaite |
| Charte, ou `V2-ADR-006` | aucune exigence de résidence des données n'est documentée, alors que l'interdiction du profil global en `staging` et `production` s'y adosse | instruire l'exigence : soit elle est formalisée et l'interdiction en devient une conséquence, soit elle est écartée et l'interdiction reste une précaution explicitement non fondée. Sans cette instruction, la distinction par environnement décidée ici repose sur une règle dont aucun document n'est propriétaire |

La granularité d'attribution des coûts décidée ici est une **entrée** pour `V2-LLD-007`, qui n'est
pas encore rédigé : aucune correction n'y est requise, mais la contrainte doit y être reprise.

## Préconditions

La décision est prise ; son activation dépend de faits à prouver avant implémentation :

- **liste nominative des régions de destination** du profil géographique EU pour le modèle retenu,
  au moment de l'implémentation — la politique IAM en dépend directement ;
- confirmation que le modèle primaire **et** le modèle de repli sont tous deux invocables depuis
  `eu-west-3` comme région source, et non seulement présents comme régions de destination ;
- confirmation qu'un profil d'inférence applicatif encapsulant un profil géographique est accepté
  par `ConverseStream` et **n'ouvre pas** de quota distinct ;
- confirmation que l'appel traverse le point de terminaison `bedrock-runtime` de la région source
  sans exiger de point de terminaison VPC supplémentaire par région de destination — à défaut,
  `V2-LLD-001` doit provisionner ce que `V2-ADR-007` n'a pas prévu ;
- valeurs de quota effectives du compte pour le modèle retenu, primaire et repli.

Tant que ces preuves ne sont pas produites, le repli est la mitigation actuelle de
`V2-LLD-003 §5.4` — deux tentatives puis erreur typée — sans nouvel ADR. Cette mitigation reste
correcte ; elle est seulement incomplète.

## Périmètre exclu

- **Le point de terminaison `bedrock-mantle`** et ses API compatibles OpenAI : hors périmètre.
  `V2-ADR-005` a retenu `Converse` sur `bedrock-runtime`, et son modèle de quotas diffère.
- **Le choix des modèles d'embedding** : traité par `V2-ADR-013`, dont les contraintes de
  versionnement sont d'une autre nature — un changement d'embedding invalide un index, pas une
  réponse.
- **L'évaluation comparative de qualité entre modèles** : relève de `V2-ADR-018` et de
  `V2-LLD-009`. Cet ADR décide un mécanisme de sélection, pas un classement.

## Conséquences

- le domaine gagne un contrat explicite là où il avait un `str` : `invocation_id` est opaque, et
  cette opacité est ce qui rend le débit provisionné accessible plus tard sans réécriture ;
- une invocation peut traverser plusieurs régions UE. C'est une décision de résidence assumée, à
  refléter dans le registre de traitement, pas un détail d'implémentation ;
- la politique IAM devient dépendante d'une liste de régions détenue par AWS : elle exige une
  surveillance de dérive, pas seulement une rédaction correcte ;
- le coût par tenant est une estimation dérivée des compteurs de tokens, réconciliable avec la
  facture par environnement mais pas par tenant. `V2-LLD-007` doit énoncer cette limite plutôt que
  de la découvrir ;
- le modèle de repli introduit une ressource qui doit être exercée pour rester disponible : c'est
  une charge d'exploitation permanente, faible mais non nulle ;
- la règle du premier token rend le repli inefficace sur les réponses longues, qui sont précisément
  celles dont l'échec est le plus visible. C'est la limite acceptée de ce choix : préserver la
  cohérence plutôt que la disponibilité ;
- le tarif inférieur du profil global (environ 10 %) est écarté en production par précaution
  opérationnelle (exposition CLOUD Act, risque de perte de base légale RGPD). L'écart doit être
  chiffré dans `V2-LLD-007` pour que le compromis reste un choix documenté et non un coût
  invisible ;
- trois marqueurs `⚠ ADR MANQUANT` de `V2-LLD-003` sont levés ; le LLD peut viser `Approved` sur
  ces sections.

## Preuves attendues

- **appel avec un identifiant de modèle de fondation nu depuis `eu-west-3`** : la
  `ValidationException` attendue est observée. Cette preuve négative valide le fait technique
  fondant l'ADR ; son absence l'invalide ;
- appel nominal par profil applicatif : succès, en `Converse` et en `ConverseStream` ;
- **repli déclenché avant le premier token** : la réponse est complète, cohérente, et `done`
  déclare l'identifiant de repli avec `degraded = true` ;
- **throttling déclenché après le premier token** : aucun repli n'est tenté, le flux se termine par
  `error` — vérifié par un test, la règle du premier token n'étant pas observable autrement ;
- **identifiant de repli à fenêtre de contexte inférieure** : refus au démarrage, avec un message
  actionnable — pas un échec à la première invocation de repli ;
- politique IAM privée d'une région de destination : l'échec est observé et diagnosticable, et le
  test documente ce mode de panne intermittent ;
- **invocation de contrôle du repli** : exécutée, tracée, et son échec produit une alerte ;
- sonde de cycle de vie : la résolution du profil applicatif vers les modèles qu'il encapsule
  aboutit, et le passage simulé en `Legacy` du primaire ou du repli produit une alerte ;
- étiquettes de coût du profil applicatif visibles dans Cost Explorer, en tenant compte du délai
  de propagation et du fait qu'elles ne sont pas rétroactives ;
- réconciliation entre le coût dérivé des compteurs de tokens et la facture de l'environnement, avec
  un écart mesuré et borné ;
- tentative d'usage d'un profil global en `staging` ou `production` : refusée par le contrôle
  (valeur SSM par environnement), et non seulement absente de la configuration ;
- en environnement `dev` ou `test` avec profil global : TTFT mesuré sur plusieurs appels,
  distribution documentée comme non représentative de la production.

## Références AWS

- Amazon Bedrock — *Set up a model invocation resource using inference profiles* ;
- Amazon Bedrock — *Increase throughput with cross-Region inference* ;
- Amazon Bedrock — *Geographic cross-Region inference* et *Global cross-Region inference* ;
- Amazon Bedrock — *Supported Regions and models for inference profiles* ;
- Amazon Bedrock — *Application inference profiles* et étiquettes de répartition de coûts ;
- Amazon Bedrock — *Per-request metadata tagging* (`requestMetadata`) ;
- Amazon Bedrock — *Model lifecycle* (`Active`, `Legacy`, accès étendu, fin de vie) et
  `FoundationModelLifecycle` ;
- Amazon Bedrock — *Quotas for the bedrock-runtime endpoint* et *How tokens are counted* ;
- Amazon Bedrock — *Identity-based policy examples* (cross-Region inference) ;
- Amazon Bedrock — métriques CloudWatch de latence du premier token et de consommation estimée de
  quota ;
- Amazon Bedrock — `Converse` et `ConverseStream`.
