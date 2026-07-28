# V2-ADR-016 — WAF, quotas et protection contre les abus

- **Statut :** Draft (propositions — en attente de revue et de validation)
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-001` (chemin d'ingress et placement des contrôles), `V2-ADR-006`
  (identité résolue côté serveur), `V2-ADR-011` (streaming — la grandeur à borner), `V2-ADR-012`
  (quota Bedrock de compte et repli), `V2-ADR-014` (matérialisation de commandes)
- **Préconditions bloquantes :** attachement effectif d'AWS WAF au type d'API Gateway retenu, et
  existence d'un mécanisme rendant CloudFront le seul chemin d'accès (voir « Préconditions »).
- **Documents impactés :** `V2-ADR-001`, `V2-ADR-006`, `V2-ADR-012` ; `HLD` §6.3, §11 ;
  `capability-allocation-matrix.md` Domaine 10 ; `V2-LLD-001` §7 ; `V2-LLD-003` §5.2, §9.2 ;
  `LLD-V2-INDEX-FR.md` (portée `V2-LLD-005`) — voir « Écarts à corriger dans le corpus ».

## Contexte

Le corpus mentionne les quotas à sept endroits sans jamais les décider. La Charte §8 demande des
« quotas et limites configurables » ; le HLD §6.3 attribue à la couche d'ingress « quotas et
normalisation » ; `V2-ADR-001` exige que FastAPI « applique quotas et limites de taille » ;
`V2-ADR-014` renvoie explicitement la limitation d'abus sur la matérialisation de commandes à cet
ADR ; la CAM Domaine 10 se contente d'une ligne `WAF Rules | AWS WAF | —`.

Aucun de ces énoncés ne dit **quelle grandeur est bornée, à quelle couche, ni pourquoi cette
couche-là**. Le placement de la limitation dans FastAPI apparaît ainsi comme une préférence de
rédaction, alors qu'il est, on le verra, une contrainte.

Le titre du backlog associe deux sujets — « WAF » et « quotas et protection contre les abus » — que
cet ADR sépare, parce qu'ils ne s'appliquent pas à la même population et ne sont pas deux couches
d'un même contrôle.

## Exigences

| Référence | Exigence |
|---|---|
| Charte §8 FinOps | quotas et limites configurables ; limitation des tours et appels de tools |
| Charte §9 Risques | la dérive des coûts Bedrock/ECS appelle « quotas, télémétrie de coût et tests de charge » |
| Charte §4.2 | aucune organisation ni gouvernance client inventée n'entre dans le périmètre |
| `V2-ADR-001` | FastAPI applique quotas et limites de taille ; le chemin supporte WAF et throttling |
| `V2-ADR-006` | `tenantId`, rôles et scopes sont résolus côté serveur, jamais fournis par le client |
| `V2-ADR-011` | un flux conversationnel dure jusqu'à 15 minutes ; une déconnexion client n'arrête pas la facturation |
| `V2-ADR-012` | le quota Bedrock est appliqué au compte pour un couple modèle/région, partagé hors du système |
| `V2-ADR-014` | la matérialisation d'une commande est sans effet de bord — et donc sans coût dissuasif |
| CAM Domaine 10 | défense en profondeur : aucune couche ne suppose que la précédente a filtré |

## Le fait déterminant — la ressource rare est un quota de compte, pas une bande passante

`V2-ADR-012` établit un fait dont il tire une conséquence de disponibilité, sans en tirer celle
d'abus :

> « son quota est **appliqué au niveau du compte pour un couple modèle et région** — donc partagé
> par tous les appelants du compte, y compris des charges de travail qui ne relèvent pas de ce
> système. »

Trois conséquences en découlent, qu'aucun document ne formule.

**La grandeur comptée à la porte n'a pas de rapport fixe avec la ressource rare.** Une requête sur
`/api/v1/conversations/{id}/messages` peut consommer jusqu'à `maxTokens` — dérivé de la fenêtre de
contexte du modèle à 75 % (`V2-LLD-003` §5.2.1) — répartis sur `maxTurns = 10` tours et
`maxToolCalls = 20` appels. Une requête `GET /api/v1/documents` ne consomme rien de comparable. Le
rapport de coût entre deux requêtes du même système dépasse trois ordres de grandeur. Une limite
exprimée en requêtes par fenêtre borne donc une quantité qui n'est pas celle qui est rare.

**Protéger la plateforme d'un appelant et protéger les appelants les uns des autres est le même
mécanisme.** Puisque le quota est au niveau du compte, l'excès d'une identité ne dégrade pas
« la plateforme » dans l'abstrait : il se matérialise directement en `ThrottlingException` chez les
autres identités. La limitation d'abus n'est pas ici un sujet de sécurité périmétrique, c'est un
contrôle d'admission sur une ressource partagée à plafond dur.

**Le repli de `V2-ADR-012` n'est pas une réponse à l'abus, et l'abus le consomme aussi.** Le repli
option B ouvre un second quota parce qu'il vise un modèle distinct. Il a été dimensionné pour
absorber un throttling **occasionnel**, provoqué par des voisins extérieurs au système. Un appelant
interne qui sature le quota primaire bascule sur le quota de repli et le sature à son tour : sans
contrôle d'admission **en amont** du repli, le repli devient la seconde file de l'abuseur au lieu
d'être la réserve des autres.

## Ce que chaque couche peut réellement voir

Le placement des contrôles n'est pas un choix de style. Il est déterminé par ce que chaque couche
connaît au moment où elle décide.

| Couche | Voit l'identité ? | Voit le coût ? | Grandeur qu'elle peut borner |
|---|---|---|---|
| CloudFront + AWS WAF | IP, en-têtes, URI, corps jusqu'à la limite d'inspection — **pas** `tenantId` | non | volumétrie, signatures L7, réputation |
| API Gateway | JWT validé ; ni `tenantId` ni rôles, qui sont résolus après | non | débit et rafale **globaux** de l'étape |
| FastAPI | identité complète : `actorId`, `tenantId`, rôles, scopes (`V2-ADR-006`) | oui, a posteriori (`V2-ADR-008`) | tout, mais après avoir été atteinte |

La ligne décisive est celle de `tenantId`. `V2-ADR-006` a décidé que le tenant est **résolu côté
serveur** à partir de claims autorisés et d'un registre d'autorisation, et interdit qu'il provienne
du client. Il n'existe donc pas encore lorsque WAF et API Gateway décident. Un contrôle par tenant
avant FastAPI supposerait un tenant transporté par le client — c'est-à-dire exactement l'option B
que `V2-ADR-006` a rejetée pour risque d'escalade horizontale.

**Le quota par identité ne peut pas être appliqué avant FastAPI. Ce n'est pas une commodité de
rédaction, c'est une conséquence de `V2-ADR-006`.** Le corpus posait la bonne conclusion sans
l'argument ; l'argument est ici.

## Le streaming déplace la grandeur à borner

`V2-ADR-011` a deux conséquences que la limitation classique ne supporte pas.

**Un flux compte pour une requête pendant quinze minutes.** La route conversationnelle est un
`text/event-stream` d'une durée maximale de 15 minutes. À la porte, c'est une requête. Une limite
de soixante requêtes par cinq minutes autorise donc soixante flux simultanés consommant du Bedrock
en continu. La grandeur qui borne réellement un flux n'est pas sa fréquence, c'est sa
**simultanéité**.

**La déconnexion du client n'arrête pas la consommation.** `V2-ADR-011` a retenu un endpoint
d'annulation explicite précisément parce que la fermeture de la connexion laisse courir la
facturation Bedrock. Un appelant qui ouvre des flux et se déconnecte immédiatement consomme du
quota en ne maintenant **aucune connexion ouverte**. Toute limitation qui compte des connexions
compte donc la mauvaise chose.

Il en résulte une contrainte de définition : la simultanéité à borner est le nombre d'**invocations
en vol côté serveur** — de la matérialisation de l'invocation jusqu'à son terme ou son annulation —
et non le nombre de connexions clientes établies.

## Choix de la couche d'application du quota par identité

### Option A — Règles rate-based AWS WAF agrégées sur un claim

AWS WAF sait agréger une règle rate-based sur autre chose que l'IP source — un en-tête, un
paramètre, une valeur extraite.

**Rejet.** La valeur qui compte, `tenantId`, n'existe pas à ce point du chemin (`V2-ADR-006`) ;
agréger sur `sub` bornerait l'utilisateur et non l'organisation, ce qui laisse un tenant saturer le
quota avec n utilisateurs. S'y ajoutent deux limites propres au mécanisme : le comptage est
approximatif et retardé — la documentation AWS admet des dépassements transitoires — et la fenêtre
d'évaluation est un ensemble discret de valeurs. Un contrôle de coût ne peut pas être approximatif
dans le sens permissif sur une ressource à plafond dur.

### Option B — Usage plans API Gateway

API Gateway sait appliquer un quota et un débit par consommateur, via un *usage plan*.

**Rejet.** Un usage plan s'indexe sur une **clé d'API**. Une clé d'API dans un frontend React est
un secret partagé publiquement, ce que `V2-ADR-006` interdit en substance : l'identité serait
portée par une valeur que le client détient. Le mécanisme est conçu pour des consommateurs
serveur-à-serveur identifiés hors JWT ; il n'est pas transposable à une SPA authentifiée par
Cognito.

### Option C — Quota appliqué par FastAPI sur l'identité résolue

FastAPI décide après résolution de l'identité et avant l'invocation Runtime.

**Avantages :** seule couche disposant simultanément de `tenantId`, des rôles, de la classe de
route et de la mesure de coût. Le refus y coûte une requête ECS et une lecture de compteur, soit
un ordre de grandeur en dessous de l'invocation qu'il évite.

**Limites :** le refus intervient après le VPC Link et l'ALB. FastAPI ne se protège donc pas
elle-même d'un flot volumétrique — c'est le rôle des couches amont, et la raison pour laquelle
elles ne disparaissent pas.

## Décision — Couche d'application

Retenir **l'option C**, avec un partage explicite des rôles qui n'est pas une redondance :

```text
CloudFront + WAF   population non identifiée  volumétrie, signatures, réputation
API Gateway        population authentifiée    plafond global de l'étape (protège le chemin privé)
FastAPI            identité résolue           quota par identité, dans la monnaie du coût
```

Chaque couche borne ce qu'elle est seule à pouvoir borner. Aucune ne rattrape le manque d'une
autre, contrairement à la lecture habituelle de la défense en profondeur : ici les trois couches
ne bornent pas la même grandeur.

## Choix de la grandeur bornée

### Option A — Requêtes par fenêtre glissante

Le contrôle usuel.

**Rejet.** Démontré plus haut : sans rapport fixe au coût, et neutralisé par le streaming, où une
requête vaut quinze minutes.

### Option B — Simultanéité seule

Borner le nombre d'invocations en vol par identité.

**Rejet comme contrôle unique.** La simultanéité borne le débit instantané, pas le cumul : une
identité respectant en permanence une invocation simultanée peut consommer sans limite sur la
durée. Elle est nécessaire, elle n'est pas suffisante.

### Option C — Tokens consommés par fenêtre

Borner la monnaie réelle.

**Rejet comme contrôle unique, pour une raison de causalité.** Le coût d'une invocation n'est connu
qu'**après** son exécution : `maxTokens` est un plafond, pas une prévision, et une invocation peut
s'arrêter au premier tour comme en consommer vingt. Un contrôle exprimé en tokens ne peut donc pas
décider d'une admission ; il ne peut que constater.

### Option D — Admission sur la simultanéité, règlement sur les tokens

Deux contrôles de natures distinctes, chacun placé là où son information existe.

**Avantages :** l'admission décide avec ce qui est connu a priori — le nombre d'invocations déjà en
vol ; le règlement impute a posteriori le coût réellement consommé, et c'est cette dette qui
conditionne les admissions suivantes. Aucune des deux décisions ne prétend connaître ce qu'elle ne
peut pas connaître.

**Limites :** deux compteurs au lieu d'un, dont l'un est mis à jour en fin d'invocation — donc une
fenêtre pendant laquelle une identité peut dépasser son budget de la valeur d'une invocation. Ce
dépassement est borné par `maxTokens`, qui est lui-même un paramètre du système.

## Décision — Grandeurs et dimensions

Retenir **l'option D**.

> **On ne peut pas tarifer une invocation avant de l'exécuter. L'admission porte donc sur la
> simultanéité, qui est connue, et le règlement sur les tokens, qui ne le sont qu'ensuite.**

Quatre dimensions sont bornées par identité, et elles ne sont pas interchangeables :

| Dimension | Monnaie | Moment de la décision | Motif |
|---|---|---|---|
| Invocations conversationnelles simultanées | invocations en vol | admission, avant Runtime | seule grandeur connue a priori sous streaming (`V2-ADR-011`) |
| Tokens consommés par fenêtre | tokens entrée + sortie | règlement, en fin d'invocation | monnaie réelle du quota Bedrock (`V2-ADR-012`) |
| Documents en cours d'ingestion | jobs non terminés | admission, à l'upload | le coût d'un upload est asynchrone (`V2-LLD-002` §5.1) |
| Commandes `pending` non résolues | items | admission, à la matérialisation | la matérialisation est sans effet de bord, donc sans coût dissuasif (`V2-ADR-014`) |

Les deux premières bornent le coût modèle, les deux dernières bornent des files. Une file non
bornée est un coût différé, pas un coût absent.

## La contrainte de cohérence — un quota par identité ne protège rien sans plafond de plateforme

C'est la contrepartie arithmétique de la décision, et le point où le corpus risquerait de se
contenter d'une valeur choisie.

Un quota par identité répartit une capacité ; il ne la crée pas. Si la somme des admissions
simultanées autorisées dépasse ce que le quota Bedrock du modèle peut servir, les quotas ne
protègent personne : ils déplacent seulement l'échec d'un refus contrôlé vers une
`ThrottlingException`, c'est-à-dire d'un message intelligible vers une dégradation subie.

```text
plafondPlateforme          = admissions simultanées servables par le quota Bedrock du modèle
quotaIdentité              = part du plafond de plateforme
tauxSursouscription        = somme(quotaIdentité) / plafondPlateforme
```

Le taux de sursouscription supérieur à 1 est légitime — toutes les identités ne sont pas actives
simultanément — mais il doit être un **paramètre déclaré**, pas le résultat non calculé d'une
somme. C'est le seul chiffre de cet ADR dont la valeur engage réellement le comportement du système
sous charge.

Il en découle une conséquence pour `V2-ADR-012` : son repli n'est admissible comme réserve que si
le plafond de plateforme est appliqué avant lui. Un plafond calculé sur le seul quota primaire, et
un repli ouvert sans contrôle, reviennent à doubler la capacité offerte à celui qui sature.

## WAF et quotas protègent deux populations disjointes

Le titre du backlog les associe ; ils ne se recouvrent pas.

Toutes les routes applicatives sont derrière l'authentification Cognito (`V2-ADR-001`). AWS WAF
n'a donc **aucune prise utile sur l'abus authentifié** : il ne distingue pas un utilisateur légitime
d'un utilisateur excessif, faute de voir l'identité et le coût. Symétriquement, les quotas de
FastAPI n'ont aucune prise sur la population **non identifiée** — trafic dirigé vers le point
d'authentification lui-même, exploration de surface, scan, flot volumétrique — puisqu'ils
s'appliquent après une identité qui n'existe pas dans ces cas.

| Population | Contrôle | Objet |
|---|---|---|
| Non identifiée | WAF sur CloudFront, Shield | volumétrie, signatures, protection du point d'authentification et du frontal statique |
| Authentifiée | quotas FastAPI par identité | équité de la ressource partagée et maîtrise du coût |
| Toutes | plafond global API Gateway | protection du chemin privé VPC Link → ALB → ECS |

Aucun de ces trois contrôles ne remplace un autre. Formuler « WAF et quotas » comme une seule
mesure conduirait à croire l'abus authentifié couvert par le WAF, ce qui est faux.

## L'exigence de chemin unique

Les contrôles portés par CloudFront — WAF, Shield, en-têtes de sécurité — ne valent que si
CloudFront est le **seul** chemin d'accès. `V2-ADR-001` et `V2-LLD-001` §7 décrivent le chemin
nominal sans énoncer que les autres sont fermés : en l'état, un appel direct au point de terminaison
API Gateway est un chemin non décrit qui contourne l'intégralité de la couche WAF.

**Règle retenue.** L'API Gateway n'accepte que le trafic provenant de la distribution CloudFront du
système, par un mécanisme vérifié au plan Terraform. Un point de terminaison joignable directement
rend le WAF consultatif, et rend fausse toute preuve qui l'exercerait par le chemin nominal.

Le mécanisme précis — secret partagé injecté par CloudFront et vérifié par une resource policy, ou
origine privée — relève de `V2-LLD-005` ; l'exigence, elle, est fixée ici, car elle conditionne la
valeur des contrôles décidés dans cet ADR.

## Le compteur indisponible — l'exception assumée au refus par défaut

`V2-ADR-006` pose que le refus est la valeur par défaut lorsqu'une information manque, et cet ADR
ne l'affaiblit nulle part ailleurs. Il en fait ici **une exception, explicitement argumentée**.

Si le magasin de compteurs est indisponible — connexion refusée, healthcheck échoué — ou si
l'opération atomique dépasse le SLA de latence déclaré (voir précondition 3), FastAPI ne connaît
plus la consommation de l'identité. Appliquer le refus par défaut refuserait alors tout le trafic :
une panne du compteur deviendrait une panne totale du service.

**Règle retenue.** Le compteur de quota n'est pas un contrôle d'autorisation. Son indisponibilité
ou son dépassement de SLA de latence ne refuse pas ; ils font retomber le système sur le plafond
global d'API Gateway, qui reste appliqué et qui existe précisément pour cela. L'événement est
journalisé et alerté comme une perte de contrôle d'équité, pas comme un incident de sécurité.

La justification tient en une phrase : **un contrôle de disponibilité appliqué en fail-closed
inverse sa propre finalité.** Un contrôle d'autorisation qui échoue doit refuser, parce que son
objet est d'empêcher ; un contrôle d'équité qui échoue ne doit pas transformer une dégradation
partagée en indisponibilité totale. La distinction est ce qui autorise l'exception, et elle vaut
pour ce compteur uniquement — aucune décision d'autorisation de `V2-ADR-006` n'est concernée.

**Comportement au retour du compteur.** Les invocations qui ont démarré pendant la période
d'indisponibilité ont consommé des tokens sans être comptées. Au retour du compteur, ces
invocations sont déjà terminées et leur trace est perdue pour le règlement — ce comportement est
assumé : le mode dégradé accepte cette perte de précision sur la fenêtre de panne. En revanche,
toute invocation terminée pendant l'indisponibilité mais dont le règlement de tokens n'a pas encore
été écrit doit tenter une écriture différée au retour : le règlement manqué est une dette, pas une
remise.

## Ce que les quotas ne protègent pas

Énoncer ces limites fait partie de la décision ; un contrôle dont on croit à tort qu'il couvre un
risque est pire qu'un contrôle absent.

- **Le coût d'une invocation légitime.** Les quotas bornent le nombre et le cumul, pas la
  pertinence. Une invocation coûteuse et utile consomme autant qu'une invocation coûteuse et
  inutile ; c'est aux budgets de `V2-LLD-003` §5.2 de borner l'unité.
- **Le throttling causé par des charges extérieures au compte partagé.** `V2-ADR-012` l'a déjà
  traité par le repli et le rejet contrôlé. Aucun quota interne ne réserve de capacité chez AWS.
- **L'injection indirecte.** `V2-ADR-014` en borne l'effet ; les quotas en bornent le volume. Une
  injection réussie produit au pire des propositions visibles — le quota de commandes `pending`
  borne combien.
- **L'exfiltration par requêtes légitimes répétées.** Un appelant autorisé qui interroge
  massivement ses propres données reste dans son périmètre `V2-ADR-006` ; la détection relève de
  l'audit, pas de la limitation.
- **La disponibilité du chemin privé sous flot authentifié massif.** Le plafond global d'API
  Gateway le borne ; le quota par identité arrive trop tard pour cela.

## Les valeurs sont des paramètres, pas une politique

La Charte §4.2 exclut du périmètre toute gouvernance client inventée. Fixer ici des paliers de
service, des classes d'abonnés ou des valeurs présentées comme contractuelles reviendrait à
inventer les besoins d'un client qui n'existe pas.

Cet ADR fixe donc les **dimensions**, la **monnaie** et la **couche** de chaque contrôle, ainsi que
la relation qui les lie au quota Bedrock. Il ne fixe aucune valeur. Toutes sont des paramètres
Terraform/SSM, au même titre que les budgets de `V2-LLD-003` §5.2, avec trois contraintes de
validation opposables :

```text
somme(quotaIdentité) / plafondPlateforme = tauxSursouscription, déclaré explicitement
plafondPlateforme <= admissions servables par le quota Bedrock du modèle configuré
tokenBudgetWindowDays déclaré, <= durée maximale d'une invocation conversationnelle (V2-ADR-011)
```

Trois paramètres doivent être déclarés — `tauxSursouscription`, `plafondPlateforme` et
`tokenBudgetWindowDays` — et leur cohérence est vérifiée par `terraform_plan_guard.py` en mode
numérique (nouveau contrôle, distinct du contrôle booléen et de la borne simple existants). Un
plan omettant l'un d'eux, ou fixant un plafond de plateforme supérieur à la capacité servable, est
refusé à la validation.

La vérification `plafondPlateforme <= admissions servables` requiert la capacité Bedrock réelle du
compte — une service quota AWS, pas une ressource Terraform. Elle entre dans la garde via un
paramètre SSM alimenté lors de la découverte de capacité (précondition 4) ; le plan échoue si ce
paramètre est absent ou nul.

## Réalisation par phase

| | V2 | Cible V3 |
|---|---|---|
| WAF | règles managées AWS, rate-based par IP, journalisation | ajout de règles dérivées des incidents observés |
| Plafond global | débit et rafale d'étape API Gateway | inchangé |
| Admission par identité | compteur d'invocations en vol, magasin partagé | inchangé |
| Règlement en tokens | imputation en fin d'invocation, fenêtre glissante | imputation incrémentale par tour |
| Quota d'ingestion | jobs non terminés par identité | file par tenant avec priorité |
| Quota de commandes | items `pending` par identité | inchangé |
| Chemin unique | secret partagé CloudFront → API Gateway, gardé au plan | origine privée si disponible |

Le règlement reste en fin d'invocation en V2 : l'imputation par tour supposerait un compteur écrit
à chaque tour de chaque flux, soit un coût d'écriture proportionnel au trafic pour une précision
dont la valeur n'est pas démontrée tant que `maxTokens` borne déjà l'unité. La cible V3 suppose en
outre un prérequis architectural non décidé : l'écriture du compteur doit s'intercaler dans le
gestionnaire SSE de `V2-ADR-011`, coordonnée avec la backpressure et l'annulation explicite — ce
couplage doit être décidé dans `V2-ADR-011` avant que l'imputation incrémentale puisse être
planifiée.

## Écarts à corriger dans le corpus

Ces corrections découlent de l'acceptation de l'ADR et ne sont pas appliquées par lui.

| Document | Écart | Correction attendue |
|---|---|---|
| `V2-ADR-001` et `V2-ADR-006` | tous deux listent `V2-ADR-016` en dépendance, que le backlog fait dépendre d'eux — deux cycles | retirer `V2-ADR-016` des deux lignes de dépendances ; le sens utile est 016 → 001 et 016 → 006 |
| `V2-ADR-001` | « FastAPI applique quotas et limites de taille » sans dire pourquoi cette couche | renvoyer à la contrainte `V2-ADR-006` établie ici |
| `V2-ADR-012` | le repli est présenté comme réserve sans condition d'admission en amont | ajouter : le repli n'est une réserve que si le plafond de plateforme est appliqué avant lui |
| `HLD` §6.3 | « quotas et normalisation » attribués à l'ingress sans grandeur ni couche | renvoyer aux quatre dimensions de cet ADR |
| `HLD` §11 | la catégorie « quotas » n'a ni mécanisme ni test | ajouter mécanisme, paramètre et preuve |
| `capability-allocation-matrix.md` Domaine 10 | la ligne `WAF Rules` n'a ni consommateur ni portée | préciser que le WAF ne couvre que la population non identifiée |
| `V2-LLD-001` §7 | le chemin nominal n'exclut pas l'accès direct à API Gateway | ajouter l'exigence de chemin unique et son mécanisme |
| `V2-LLD-001` §7 | l'ingress est décrit sur HTTP API, alors que `V2-ADR-011` bascule la route conversationnelle sur REST API | aligner, et statuer sur l'attachement du WAF selon le type retenu |
| `V2-LLD-003` §5.2 | les budgets bornent l'invocation, sans lien avec un quota par identité | énoncer l'emboîtement : budget d'invocation ⊂ quota d'identité ⊂ plafond de plateforme |
| `V2-LLD-003` §9.2 | le refus pour quota de commandes `pending` n'est pas dans les contrats d'erreur | ajouter le code de refus quota-commandes, distinct du refus d'autorisation et du `ThrottlingException` |
| `LLD-V2-INDEX-FR.md` | portée de `V2-LLD-005` sans le chemin unique ni le magasin de compteurs | ajouter les deux |

## Préconditions

Cinq points doivent être établis avant implémentation. Deux sont bloquants.

1. **Attachement du WAF au type d'API retenu — bloquante.** AWS WAF ne s'attache pas
   indifféremment à tous les types d'API Gateway ; `V2-LLD-001` §7 décrit un HTTP API et
   `V2-ADR-011` bascule la route conversationnelle sur un REST API. La même prudence que
   `V2-LLD-003` §9 applique aux préfixes IAM s'impose ici : la compatibilité doit être vérifiée
   nominativement sur le service, pas supposée. Si le WAF ne s'attache pas au type retenu, il ne
   subsiste que sur CloudFront — ce qui rend la précondition 2 non plus souhaitable mais
   indispensable.
2. **Mécanisme de chemin unique — bloquante.** Existence et vérifiabilité au plan Terraform d'un
   mécanisme rendant CloudFront le seul chemin joignable. Sans lui, tous les contrôles portés par
   CloudFront sont contournables et les preuves qui les exercent par le chemin nominal ne
   démontrent rien.
3. **Magasin de compteurs.** Choix d'un magasin partagé entre tâches ECS supportant un incrément
   atomique et une expiration. Le compteur est sur le chemin de chaque invocation conversationnelle ;
   sa latence doit être mesurée et un SLA de latence maximal déclaré (exemple : P99 ≤ 10 ms). Le
   dépassement de ce SLA est traité identiquement à l'indisponibilité totale : repli sur le plafond
   API Gateway, alerte, aucun refus.
4. **Capacité servable du quota Bedrock.** Déterminer combien d'invocations simultanées le quota du
   modèle configuré sert réellement, puisque c'est ce nombre, et non une valeur choisie, qui borne
   le plafond de plateforme.
5. **Observabilité du refus.** Vérifier que le refus pour quota est distinguable dans les métriques
   `V2-ADR-008` d'un refus d'autorisation et d'un `ThrottlingException` — trois causes de refus qui
   appellent trois réactions d'exploitation différentes.

## Périmètre exclu

- **Les valeurs de quota** et toute segmentation par classe d'utilisateur : paramètres
  d'exploitation, hors périmètre par la Charte §4.2.
- **La détection comportementale d'abus** — profils, scores, apprentissage : suppose une
  gouvernance et un volume de trafic que ce projet n'a pas.
- **Le contenu des règles WAF managées** et leur réglage : relève de `V2-LLD-005`.
- **La protection anti-DDoS au-delà de Shield Standard** : Shield Advanced est un engagement
  contractuel, hors périmètre projet.
- **Les budgets par invocation** — `maxTurns`, `maxToolCalls`, `maxTokens`, deadline : décidés par
  `V2-LLD-003` §5.2, consommés ici sans être redécidés.
- **Le repli modèle et le rejet contrôlé** : `V2-ADR-012`, appliqués tels quels.
- **La tarification et la refacturation** : `V2-ADR-012` a déjà établi que `requestMetadata` ne
  produit pas de répartition de coûts exploitable.

## Conséquences

- Le placement des quotas dans FastAPI cesse d'être une préférence de rédaction : il devient une
  conséquence démontrée de `V2-ADR-006`, et ne peut plus être déplacé sans rouvrir cette décision.
- `V2-ADR-012` acquiert une condition qu'il n'énonçait pas : son repli n'est une réserve que si un
  contrôle d'admission s'applique en amont, faute de quoi il double la capacité offerte à
  l'appelant qui sature.
- Le système gagne **trois paramètres structurants gardés** : `tauxSursouscription`, qui conditionne
  le comportement sous charge ; `plafondPlateforme`, borné par la capacité Bedrock réelle du compte
  (valeur externe, transmise via SSM) ; et `tokenBudgetWindowDays`, qui détermine la durée de
  mémoire du règlement en tokens. Les trois doivent être déclarés et sont vérifiés par
  `terraform_plan_guard.py` en mode numérique.
- Un compteur partagé apparaît sur le chemin de chaque invocation conversationnelle : c'est une
  dépendance de latence et de disponibilité qui n'existait pas, et la raison pour laquelle son
  indisponibilité doit dégrader et non refuser.
- L'exception au refus par défaut de `V2-ADR-006` est assumée et bornée à ce compteur. Elle
  suppose que la distinction entre contrôle d'autorisation et contrôle d'équité soit maintenue à
  l'implémentation, faute de quoi elle deviendrait un précédent.
- L'exigence de chemin unique ajoute une contrainte de déploiement et une garde de plan. Sans elle,
  la ligne WAF de la CAM Domaine 10 décrit un contrôle contournable.
- Le refus pour quota devient une réponse d'API à part entière, à distinguer d'un refus
  d'autorisation dans les contrats d'erreur de `V2-LLD-003` §9.2 et dans le frontend
  `V2-LLD-010`.

## Preuves attendues

- une identité atteignant sa limite d'invocations simultanées reçoit un refus typé **avant** toute
  invocation Runtime, vérifié par l'absence d'appel Bedrock associé ;
- une identité ayant épuisé son budget de tokens sur la fenêtre est refusée à l'admission suivante,
  et le dépassement constaté ne dépasse pas `maxTokens` — la borne du dépassement admis par la
  décision ;
- un flux ouvert puis abandonné par déconnexion client continue de compter dans la simultanéité
  jusqu'à son terme ou son annulation `V2-ADR-011`, démontrant que la grandeur comptée est
  l'invocation en vol et non la connexion ;
- **preuve d'équité, la plus significative de cet ADR :** sous une charge calibrée pour que
  l'identité abusante atteigne `plafondPlateforme × tauxSursouscription` — c'est-à-dire au niveau
  de saturation déclaré — une seconde identité conserve un temps de première réponse dans son
  enveloppe nominale ; la même charge, quotas désactivés, la dégrade. Le second volet n'est pas
  facultatif : sans lui, le test passe aussi lorsque la charge n'a jamais saturé quoi que ce soit ;
- une requête émise directement sur le point de terminaison API Gateway, hors CloudFront, est
  refusée ;
- l'indisponibilité simulée du magasin de compteurs (connexion refusée) ne refuse pas le trafic,
  lève l'alerte attendue, et le plafond global d'API Gateway reste appliqué ; la même preuve est
  rejouée en simulant un timeout de l'opération atomique au-delà du SLA déclaré — le comportement
  doit être identique dans les deux cas ;
- un plan omettant `tauxSursouscription`, `plafondPlateforme` ou `tokenBudgetWindowDays`, ou fixant
  un plafond de plateforme supérieur à la capacité servable du quota Bedrock, est refusé par
  `terraform_plan_guard.py` en mode numérique ;
- le nombre de commandes `pending` par identité est borné, et la matérialisation est refusée
  au-delà sans effet de bord observable ;
- le nombre de documents en cours d'ingestion par identité est borné, et l'upload est refusé
  au-delà avec un code distinct du rejet de taille ou de format de `V2-LLD-002` §3 ;
- les refus pour quota, pour autorisation et pour throttling Bedrock sont trois séries distinctes
  dans les métriques `V2-ADR-008`.

## Références

- `V2-ADR-001` — chemin d'ingress, CloudFront, API Gateway, contrôles obligatoires de FastAPI ;
- `V2-ADR-006` — identité et tenant résolus côté serveur, refus par défaut ;
- `V2-ADR-011` — streaming SSE, plafonds temporels, annulation explicite ;
- `V2-ADR-012` — quota Bedrock de compte par modèle et région, repli et rejet contrôlé ;
- `V2-ADR-014` — matérialisation sans effet de bord et renvoi explicite des quotas à cet ADR ;
- `V2-LLD-002` §3 et §5.1 — limites d'upload et ingestion asynchrone ;
- `V2-LLD-003` §5.2 — budgets par invocation ;
- AWS WAF — ressources protégeables, règles rate-based et clés d'agrégation personnalisées ;
- Amazon API Gateway — throttling d'étape, usage plans et clés d'API ;
- Amazon CloudFront — restriction de l'origine à la distribution.
