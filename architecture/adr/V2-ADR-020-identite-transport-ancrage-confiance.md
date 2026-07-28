# V2-ADR-020 — Transport et ancrage de confiance de l'identité

- **Statut :** Draft (propositions — en attente de revue et de validation)
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-001` (chemin d'ingress et validation JWT à la passerelle), `V2-ADR-006`
  (identité résolue côté serveur), `V2-ADR-008` (redaction des journaux), `V2-ADR-011` (type d'API
  Gateway de la route conversationnelle), `V2-ADR-016` (exigence de chemin unique et exception au
  refus par défaut)
- **Précondition non bloquante :** vérification nominative que l'API Gateway REST transmet
  l'en-tête `Authorization` à l'intégration VPC Link sans le consommer (voir « Préconditions »).
- **Documents impactés :** `V2-LLD-001` §7.1 et §7.2 ; `V2-ADR-008` ; `HLD` §6.3 ;
  `LLD-V2-INDEX-FR.md` (portée `V2-LLD-005`) — voir « Écarts à corriger dans le corpus ».

## Contexte

`V2-ADR-006` a décidé ce qu'est l'identité — `actorId` dérivé du claim `sub`, `tenantId` résolu
côté serveur, aucune de ces valeurs acceptée du client. Il a posé une règle de confiance en deux
temps : « API Gateway valide le JWT ; FastAPI relit uniquement les claims nécessaires ».

Il n'a pas dit **depuis quelle source FastAPI relit**. `V2-ADR-001` non plus, qui exige que FastAPI
« dérive l'identité depuis le contexte JWT validé » sans nommer le transport de ce contexte.
`V2-LLD-001` §7.1 a comblé le silence par un mécanisme concret, et ce mécanisme est inexact.

`V2-ADR-011` a signalé l'écart en le rapportant à son propre changement — la bascule de la route
conversationnelle sur un API Gateway REST — et a conclu que les en-têtes de `V2-LLD-001` §7.1
« doivent être revalidés pour REST API ». La vérification montre que le défaut est antérieur et
plus large : **ces en-têtes n'étaient pas davantage produits sur HTTP API**.

Cet ADR tranche la question laissée ouverte : par quel transport l'identité authentifiée parvient
à FastAPI, et sur quoi repose la confiance qu'on lui accorde.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-006` | `actorId`, `tenantId`, rôles et scopes ne sont jamais acceptés du client |
| `V2-ADR-006` | aucun token Cognito n'est transmis à Runtime, MCP ou aux tools |
| `V2-ADR-001` | le navigateur ne connaît jamais l'URL Runtime ; l'identité est construite côté serveur |
| `V2-ADR-011` | la route conversationnelle et les routes documentaires peuvent relever de deux types d'API Gateway distincts |
| `V2-ADR-016` | le chemin unique CloudFront → API Gateway est une précondition **bloquante non établie** |
| `V2-ADR-008` | aucun JWT en clair dans les journaux |
| CAM Domaine 10 | défense en profondeur : aucune couche ne suppose que la précédente a filtré |

## Le fait déterminant — les en-têtes décrits appartiennent à un autre service

`V2-LLD-001` §7.1 déclare que FastAPI extrait les claims de `X-Amzn-Oidc-Data`, et attribue cet
en-tête ainsi que `X-Amzn-Oidc-Identity` à « API Gateway (natif HTTP API) ».

Ces en-têtes sont ceux d'un **Application Load Balancer** configuré en authentification OIDC ou
Cognito sur une règle de listener. API Gateway ne les émet sur aucun type d'API.

| Mécanisme | Ce qu'il produit réellement | Transmission au backend |
|---|---|---|
| ALB avec `authenticate-cognito` | `x-amzn-oidc-identity`, `x-amzn-oidc-data`, `x-amzn-oidc-accesstoken` | native, injectée par l'ALB |
| API Gateway HTTP API + authorizer JWT | `$context.authorizer.jwt.claims.<nom>` | *parameter mapping* explicite |
| API Gateway REST API + authorizer Cognito | `$context.authorizer.claims.<nom>` | mapping de paramètre d'intégration explicite |

L'ALB interne de l'architecture ne les produit pas non plus : il reçoit du trafic depuis VPC Link
et n'exécute aucune authentification Cognito, puisque `V2-ADR-001` place la validation du JWT à
API Gateway. Aucun composant du chemin décidé n'émet ces en-têtes.

Trois conséquences en découlent.

**Le défaut précède `V2-ADR-011`.** Il ne s'agit pas d'un mécanisme valide qu'un changement de type
d'API aurait invalidé, mais d'un mécanisme qui n'a jamais correspondu à l'architecture retenue. Le
corriger n'est donc pas un alignement sur `V2-ADR-011` : c'est combler une décision absente.

**Aucune transmission de claims n'est native.** Sur les deux types d'API Gateway, la mise à
disposition des claims au backend est un mapping à écrire. Le corpus a supposé une gratuité qui
n'existe pas, et cette supposition est la raison pour laquelle la question n'a jamais été instruite.

**`V2-ADR-011` rend l'hétérogénéité durable.** Les routes se répartissent sur deux types d'API dont
les contextes d'autorisation ne portent ni le même nom ni la même structure. Tout mécanisme fondé
sur le mapping impose donc deux contrats d'identité maintenus en parallèle.

## Ce qu'aucun ADR n'a décidé

| ADR | Ce qu'il décide | Ce qu'il laisse ouvert |
|---|---|---|
| `V2-ADR-001` | chemin d'ingress ; FastAPI dérive l'identité du contexte JWT validé | par quel transport ce contexte parvient à FastAPI |
| `V2-ADR-006` | composition de l'identité ; FastAPI relit les claims nécessaires | la source depuis laquelle FastAPI relit |
| `V2-ADR-011` | REST API pour la route conversationnelle | constate l'écart, ne tranche pas |

« FastAPI relit les claims » ne dit pas d'où. Or le choix de la source **est** la décision de
sécurité : il détermine ce qu'un attaquant doit compromettre pour usurper une identité.

## Options

### Option A — Injection des claims en en-têtes par mapping de la passerelle

API Gateway mappe les claims du contexte d'autorisation vers des en-têtes applicatifs ; FastAPI
accorde sa confiance à ces en-têtes.

**Avantages :** aucune revalidation ; claims déjà extraits ; conserve l'intention de
`V2-LLD-001` §7.1 sans transmettre de token au-delà de la passerelle.

**Rejet, pour trois raisons dont deux structurelles.**

*Deux syntaxes à maintenir.* `V2-ADR-011` répartit les routes sur deux types d'API dont les
contextes d'autorisation diffèrent. Le contrat d'identité varierait selon la route, et la route la
plus sensible — conversationnelle — serait celle portée par la syntaxe la moins pratiquée.

*La confiance reposerait sur une précondition non établie.* Un en-tête n'est digne de confiance que
si aucun autre émetteur ne peut le produire. C'est exactement l'exigence de chemin unique de
`V2-ADR-016`, que ce même ADR classe en **précondition bloquante non démontrée**. Faire dépendre
l'identité d'un contrôle réseau dont l'existence n'est pas prouvée inverse l'ordre des garanties :
la valeur la plus critique du système reposerait sur le fait le moins établi.

*Contredit la CAM Domaine 10.* La règle énonce qu'aucune couche ne suppose que la précédente a
filtré. La confiance en en-tête est précisément cette supposition, appliquée à la valeur qui
gouverne toute l'isolation `V2-ADR-006`.

### Option B — FastAPI valide le JWT lui-même

La passerelle transmet l'en-tête `Authorization` ; FastAPI vérifie la signature, `iss`, `aud` et
`exp` contre le JWKS Cognito mis en cache, puis dérive l'identité des claims vérifiés.

**Avantages :** mécanisme invariant au type d'API — identique sur HTTP API et REST API, donc
insensible au découpage de `V2-ADR-011`. Identité ancrée dans une vérification cryptographique et
non dans une topologie réseau.

**Limites :** validation en apparence dupliquée avec la passerelle ; dépendance nouvelle au JWKS
Cognito, à mettre en cache et dont l'indisponibilité doit être traitée ; contredit explicitement
l'interdiction de `V2-LLD-001` §7.1 de transmettre `Authorization` au-delà de la passerelle.

### Option C — Authorizer Lambda produisant un contexte d'autorisation enrichi

Une Lambda valide le token et produit un contexte que la passerelle mappe vers le backend.

**Rejet.** Réintroduit une Lambda sur le chemin critique de chaque requête, alors que `V2-ADR-001`
l'a retirée comme frontière nominale au profit de FastAPI. Elle ajoute une latence et un composant
à exploiter sans offrir de garantie que l'option B ne fournit pas, et son contexte reste transmis
par mapping — elle hérite donc des limites de l'option A.

### Option D — Authorizer à la passerelle **et** validation par FastAPI

Les deux contrôles, avec des finalités distinctes et assumées comme telles.

**Avantages :** la passerelle rejette le trafic non authentifié avant le chemin privé, à bas coût ;
FastAPI établit l'identité sur une vérification qu'elle conduit elle-même. Chaque couche fait ce
qu'elle seule est placée pour faire.

**Limites :** la vérification de signature apparaît deux fois dans le chemin. Le coût réel est une
vérification asymétrique sur clés en cache.

## Décision

Retenir **l'option D**.

> **L'identité n'est pas ce que la couche précédente affirme, c'est ce que FastAPI vérifie.**
> La passerelle protège le chemin privé en rejetant le trafic non authentifié ; FastAPI dérive
> l'identité d'un token dont elle a elle-même vérifié la signature.

Le partage n'est pas une redondance, au même titre que les trois couches de quotas de
`V2-ADR-016` ne bornent pas la même grandeur :

```text
API Gateway   authorizer Cognito     rejette le non-authentifié      protège la disponibilité
FastAPI       vérification JWKS      établit l'identité de confiance protège l'isolation
```

Trois arguments fondent ce choix, par ordre de poids.

**C'est le seul mécanisme invariant au type d'API.** `V2-ADR-011` a créé une hétérogénéité durable
entre routes. La vérification de signature est rigoureusement identique des deux côtés, là où tout
mapping impose deux contrats à faire converger. Le mécanisme qui survit à `V2-ADR-011` sans y être
adapté est celui qu'il faut retenir.

**L'ancrage de confiance ne dépend d'aucune précondition non démontrée.** Si le chemin unique de
`V2-ADR-016` venait à faillir, une requête forgée atteignant l'ALB ne produirait aucune identité :
elle serait refusée faute de signature valide. L'échec d'un contrôle réseau reste un problème de
disponibilité et ne devient pas une usurpation.

**La duplication n'en est pas une.** Les deux validations ne servent pas le même objet. Celle de la
passerelle est un contrôle de disponibilité du chemin privé ; celle de FastAPI est le fondement de
l'isolation. Leur coût respectif se juge sur leur finalité, pas sur leur ressemblance.

## La frontière du token

`V2-ADR-006` interdit qu'un token Cognito soit transmis à Runtime, MCP ou aux tools. Il n'interdit
pas de le transmettre à FastAPI. C'est `V2-LLD-001` §7.1 qui a ajouté « jamais via l'en-tête
`Authorization` au-delà de ce point », une contrainte que l'ADR n'impose pas.

Cette décision lève cette contrainte pour un seul segment et la maintient partout ailleurs.

| Segment | Token présent | Fondement |
|---|---|---|
| Navigateur → CloudFront → API Gateway | oui | authentification |
| API Gateway → VPC Link → ALB → FastAPI | **oui — changement** | source de vérité de l'identité |
| FastAPI → AgentCore Runtime | non | `trustedIdentity` produite par FastAPI (`V2-ADR-006`) |
| Runtime → MCP, tools | non | `V2-ADR-006`, inchangé |

**La frontière du token devient FastAPI, exactement.** Elle n'est ni plus haute qu'avant — le token
ne va pas plus loin qu'auparavant vers Runtime — ni implicite : elle est désormais nommée.

Le segment ajouté est intégralement privé : VPC Link, ALB interne sans DNS public, tâches ECS en
subnets privés (`V2-LLD-001`). Le token n'y transite pas en clair au sens réseau — TLS est terminé
à chaque saut — mais il devient présent dans un périmètre où il ne l'était pas, ce qui appelle une
règle de redaction explicite plutôt qu'implicite.

## Le JWKS n'hérite pas de l'exception de `V2-ADR-016`

`V2-ADR-016` a posé une exception au refus par défaut de `V2-ADR-006` pour le compteur de quota,
au motif qu'un contrôle d'équité appliqué en fail-closed inverse sa propre finalité. L'exception y
est explicitement bornée à ce compteur. Il faut le redire ici, car la situation s'y apparente en
surface : une dépendance externe, sur le chemin de chaque requête, dont l'indisponibilité empêche
une décision.

**Règle retenue.** L'indisponibilité du JWKS **refuse**. La validation du token est un contrôle
d'autorisation ; son échec doit empêcher, conformément à `V2-ADR-006`. La distinction posée par
`V2-ADR-016` — un contrôle d'autorisation qui échoue refuse, un contrôle d'équité qui échoue
dégrade — s'applique ici dans son autre sens.

Le risque de disponibilité qui en découle se traite par le cache, pas par l'assouplissement :

- les clés de signature Cognito sont mises en cache avec un TTL déclaré comme paramètre ;
- une clé expirée du cache mais non renouvelable en raison d'une indisponibilité du JWKS reste
  utilisable jusqu'à une borne de tolérance déclarée, distincte du TTL nominal — le compromis est
  borné et explicite, il n'est pas laissé à l'implémentation ;
- au-delà de cette borne, le refus s'applique et l'événement est alerté comme un incident de
  sécurité, non comme une perte de contrôle d'équité.

## Ce que cette décision ne change pas

- **La composition de l'identité.** `actorId`, `subjectId`, `tenantId`, rôles et scopes restent
  définis par `V2-ADR-006`. Cet ADR décide du transport et de l'ancrage, pas du contenu.
- **La résolution du tenant.** Elle reste serveur, à partir de claims autorisés et d'un registre.
  Un `tenantId` présent dans un token resterait sans effet.
- **Le rôle de l'authorizer de la passerelle.** Il n'est pas affaibli : il continue d'empêcher le
  trafic non authentifié d'atteindre le chemin privé, ce que FastAPI ne peut pas faire pour
  elle-même — c'est la même limite que `V2-ADR-016` reconnaît à l'option C des quotas.
- **L'exigence de chemin unique de `V2-ADR-016`.** Elle reste nécessaire et bloquante pour les
  contrôles portés par CloudFront. Cette décision la rend seulement non nécessaire *à l'identité*.
- **Le placement des quotas.** `V2-ADR-016` a démontré que le quota par identité ne peut être
  appliqué qu'après résolution de l'identité. Cette décision confirme le point de résolution sans
  le déplacer.

## Écarts à corriger dans le corpus

Ces corrections découlent de l'acceptation de l'ADR et ne sont pas appliquées par lui.

| Document | Écart | Correction attendue |
|---|---|---|
| `V2-LLD-001` §7.1 | le tableau des trois en-têtes `X-Amzn-Oidc-*` décrit un mécanisme d'ALB-OIDC absent de l'architecture | remplacer par le contrat de validation JWKS et le tableau de frontière du token |
| `V2-LLD-001` §7.1 | « jamais via l'en-tête `Authorization` au-delà de ce point » | lever pour le segment passerelle → FastAPI, maintenir au-delà |
| `V2-LLD-001` §7 | le schéma nomme « API Gateway HTTP API » alors que `V2-ADR-011` bascule la route conversationnelle sur REST API | aligner, et préciser que le contrat d'identité est identique sur les deux types |
| `V2-ADR-008` | les règles de redaction ne nomment pas l'en-tête `Authorization` | l'ajouter nommément à la liste des valeurs jamais journalisées |
| `HLD` §6.3 | l'ingress est crédité de « validation JWT » sans dire où l'identité est établie | distinguer rejet du non-authentifié (passerelle) et établissement de l'identité (FastAPI) |
| `LLD-V2-INDEX-FR.md` | portée de `V2-LLD-005` sans le contrat de validation du token | ajouter : JWKS, cache, borne de tolérance, claims requis, politique de refus |

## Préconditions

Quatre points doivent être établis avant implémentation. Aucun n'est bloquant pour la décision.

1. **Transmission de `Authorization` par REST API.** Vérifier nominativement que l'API Gateway REST
   transmet l'en-tête à l'intégration VPC Link sans le consommer, la même prudence que
   `V2-ADR-016` applique à l'attachement du WAF s'imposant ici.
2. **Paramètres du cache JWKS.** TTL nominal et borne de tolérance en cas d'indisponibilité, tous
   deux déclarés comme paramètres et non laissés à la bibliothèque retenue.
3. **Claims requis et politique de refus.** Liste nominative des claims dont l'absence provoque un
   refus, et vérification que `aud` et `iss` sont contrôlés contre des valeurs de configuration et
   non seulement présents.
4. **Coût de validation mesuré.** Latence de la vérification de signature sur clés en cache, à
   comparer aux routes documentaires — c'est là qu'elle est proportionnellement la plus visible,
   la route conversationnelle l'amortissant sur une invocation de plusieurs minutes.

## Périmètre exclu

- **Le contenu du modèle d'identité** — claims, rôles, scopes, résolution du tenant : `V2-ADR-006`,
  consommé ici sans être redécidé.
- **La configuration Cognito** — pools, clients, flux d'authentification : `V2-LLD-005`.
- **Le choix de la bibliothèque de validation** et sa configuration : `V2-LLD-001`.
- **Le renouvellement de token côté navigateur** et la reprise après expiration : `V2-LLD-010`.
- **L'attachement du WAF et le chemin unique** : `V2-ADR-016`, dont cette décision réduit la portée
  sans la remplacer.
- **La révocation de session** : `V2-ADR-006` ne l'a pas traitée et cet ADR ne l'ouvre pas ; la
  durée de vie du token reste la borne effective.

## Conséquences

- Le corpus perd un mécanisme d'identité inexact qu'il décrivait depuis `V2-LLD-001` v0.1. La
  correction n'est pas un alignement sur `V2-ADR-011` mais la décision qui manquait.
- Le contrat d'identité devient **identique sur les deux types d'API Gateway**. `V2-ADR-011` peut
  répartir les routes sans que la sécurité varie d'une route à l'autre, ce qui retire un argument
  de coût à l'unification forcée sur REST API.
- FastAPI acquiert une dépendance externe nouvelle, le JWKS Cognito, sur le chemin de chaque
  requête. Elle est mise en cache, mais elle existe, et son indisponibilité prolongée refuse.
- L'exception au refus par défaut de `V2-ADR-016` est confirmée dans sa borne : elle ne s'étend pas
  au JWKS. Les deux ADR donnent ensemble le critère — c'est la nature du contrôle, non sa position
  sur le chemin, qui détermine le comportement en panne.
- La frontière du token est nommée pour la première fois. Elle était implicite et, dans
  `V2-LLD-001` §7.1, placée plus haut qu'il n'était nécessaire pour une raison qui n'était pas
  énoncée.
- `V2-LLD-005` gagne un contenu précis là où sa portée restait générale : le contrat de validation
  du token est un livrable identifié, pas une intention.

## Preuves attendues

- un en-tête de claims forgé — quel que soit son nom, y compris `X-Amzn-Oidc-Data` — n'a aucun
  effet sur l'identité résolue, démontré par l'absence de toute lecture d'en-tête d'identité dans
  le chemin de résolution ;
- un token de signature valide mais d'`aud` incorrect, d'`iss` incorrect ou expiré est refusé par
  FastAPI **alors que l'authorizer de la passerelle est désactivé** en environnement de test — sans
  ce volet, la preuve n'établit pas que FastAPI valide, seulement que la passerelle valide ;
- une requête forgée injectée directement sur l'ALB interne, hors du chemin API Gateway, ne produit
  aucune identité — preuve que l'ancrage ne dépend pas de la fermeture du chemin ;
- le comportement de résolution d'identité est identique sur une route servie par HTTP API et sur
  une route servie par REST API, mesuré sur les deux ;
- le JWKS rendu indisponible au-delà de la borne de tolérance provoque un refus, et ce refus forme
  une série de métrique distincte du refus de quota `V2-ADR-016` et du refus d'autorisation ;
- le JWKS rendu indisponible **en deçà** de la borne de tolérance ne provoque aucun refus, le cache
  restant servant les vérifications — les deux volets sont nécessaires, le second démontrant que la
  borne est effective et non décorative ;
- aucun en-tête `Authorization` n'apparaît dans les journaux d'aucune couche, vérifié sur un
  échantillon incluant les journaux d'erreur, qui sont le lieu habituel de la fuite ;
- aucun token Cognito n'atteint Runtime, MCP ou un tool — preuve `V2-ADR-006` inchangée, rejouée
  ici parce que le token circule désormais plus loin qu'auparavant.

## Références

- `V2-ADR-001` — chemin d'ingress, validation JWT à la passerelle, contrôles obligatoires FastAPI ;
- `V2-ADR-006` — composition de l'identité, règles de confiance, interdiction de token vers
  Runtime ;
- `V2-ADR-008` — redaction et interdiction de journaliser un JWT ;
- `V2-ADR-011` — bascule de la route conversationnelle sur API Gateway REST ;
- `V2-ADR-016` — chemin unique, et exception au refus par défaut bornée au compteur de quota ;
- `V2-LLD-001` §7 — chemin d'ingress détaillé et propagation des claims à corriger ;
- Elastic Load Balancing — authentification des utilisateurs par un Application Load Balancer et
  en-têtes `x-amzn-oidc-*` associés ;
- Amazon API Gateway — authorizers JWT (HTTP API), authorizers Cognito (REST API), variables de
  contexte `$context.authorizer` et mappings de paramètres ;
- Amazon Cognito — document de découverte OpenID Connect et point de terminaison JWKS.
