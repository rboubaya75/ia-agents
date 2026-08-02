# V2-ADR-011 — Streaming des réponses et gestion des annulations

- **Statut :** Accepted
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-001` (chemin d'ingress), `V2-ADR-002` (responsabilités FastAPI /
  Runtime), `V2-ADR-006` (autorisation de l'annulation)
- **Préconditions à prouver avant implémentation :** disponibilité en `eu-west-3` du *response
  streaming* API Gateway REST et des VPC Links V2 vers ALB (voir « Préconditions »).
- **Documents impactés :** `HLD §6.5`, `V2-LLD-001 §7.2`, `V2-LLD-003 §7` (voir « Écarts à
  corriger dans le corpus »).

## Contexte

Le HLD §6.5 a retenu **Server-Sent Events (SSE)** comme protocole de streaming conversationnel, et
`V2-LLD-001 §7.2` en a dérivé deux modes (direct ≤ 25 s, asynchrone au-delà) sur un **API Gateway
HTTP API**. `V2-LLD-003 §7` marque la section `⚠ ADR MANQUANT` et retient par défaut SSE avec un
mode « émulé » si Runtime ne diffuse pas nativement.

Ces trois documents partagent une prémisse qui ne résiste pas à la vérification, et c'est l'objet
principal de cet ADR : **le choix du transport n'est pas libre, il est contraint par le type d'API
Gateway**, et le corpus a raisonné sur le type qui ne sait pas diffuser.

Cet ADR tranche trois questions liées :

1. quel transport de streaming, et à quelle condition d'infrastructure ;
2. quel mécanisme d'annulation, sachant que SSE n'offre aucun canal client → serveur ;
3. comment les plafonds temporels de la chaîne se réconcilient avec les budgets de `V2-LLD-003`.

## Exigences

- le flux conversationnel doit être perçu comme progressif par l'utilisateur (time-to-first-token
  utile, pas une attente opaque suivie d'un bloc) ;
- une conversation agentique multi-tours avec appels de tools doit pouvoir dépasser 29 secondes ;
- l'utilisateur doit pouvoir interrompre une génération en cours, et l'interruption doit **arrêter
  la consommation facturée**, pas seulement masquer l'affichage ;
- une annulation ne doit jamais laisser un effet de bord de tool à moitié appliqué ;
- le navigateur ne connaît jamais l'URL Runtime (`V2-ADR-001`) : le streaming est relayé par
  FastAPI, jamais exposé en direct ;
- aucune dégradation silencieuse : si le streaming progressif n'est pas disponible, le mode effectif
  est déclaré au client (`V2-LLD-003 §7`) ;
- l'annulation est une opération autorisée : seul le propriétaire de l'opération peut l'annuler
  (`V2-ADR-006`).

## Le fait technique déterminant — API Gateway ne diffuse pas par défaut

C'est le point pédagogique central de cet ADR, car il invalide une prémisse répétée dans trois
documents du corpus.

Écrire une `StreamingResponse` FastAPI ne suffit pas à obtenir un flux progressif côté navigateur.
Chaque intermédiaire du chemin peut **tamponner** (buffer) la réponse, c'est-à-dire l'accumuler
entièrement avant de la relayer. Le résultat est indiscernable d'une réponse non diffusée : le
client attend, puis reçoit tout d'un coup. Le code applicatif est correct, le protocole SSE est
correct, et pourtant il n'y a pas de streaming.

Sur le chemin décidé par `V2-ADR-001`, le comportement est le suivant :

| Composant | Diffuse progressivement ? | Condition |
|---|---|---|
| CloudFront | oui | cache désactivé sur `/api/*` |
| **API Gateway HTTP API** | **non — tampon systématique** | aucune option ne l'active |
| **API Gateway REST API** | **oui** | `responseTransferMode = STREAM` (défaut : `BUFFERED`) |
| ALB interne | oui | idle timeout > intervalle de keep-alive |
| FastAPI (uvicorn) | oui | `StreamingResponse` |
| AgentCore Runtime | oui | `InvokeAgentRuntime` retourne `text/event-stream` |

Deux conséquences directes :

- le « mode direct » de `V2-LLD-001 §7.2` **ne diffuse pas** : sur HTTP API, une réponse SSE de
  25 secondes arrive en un seul bloc à la 25ᵉ seconde. Ce n'est pas du streaming, c'est le mode
  « émulé » de `V2-LLD-003 §7` — obtenu involontairement, et donc non déclaré au frontend ;
- le « mode asynchrone » ne corrige rien : `GET /operations/{id}/stream` traverse le même HTTP API
  et subit le même tampon. Il résout la limite de durée, pas l'absence de progressivité.

Le HLD §6.5 justifie SSE en affirmant que le chemin API Gateway « a été retenu précisément pour sa
compatibilité avec le streaming HTTP ». Cette justification est inexacte pour HTTP API. Elle
devient exacte pour REST API depuis novembre 2025.

Par ailleurs, `V2-LLD-003 §7` conditionne son mode émulé à l'hypothèse « si Runtime ne stream pas
nativement ». Cette hypothèse est levée : `InvokeAgentRuntime` diffuse nativement en
`text/event-stream`. Le maillon faible n'était pas Runtime, c'était l'ingress.

## Choix du transport de streaming

### Option A — Renoncer au streaming en V2

Réponse synchrone JSON, spinner côté frontend.

**Avantages :** aucune contrainte d'infrastructure ; aucun keep-alive ; annulation triviale.

**Limites :** UX très dégradée sur des réponses agentiques multi-tours ; le plafond de 29 s
d'API Gateway devient un plafond fonctionnel dur, franchi dès qu'un tour appelle deux tools ; les
budgets de `V2-LLD-003` (`maxTurns = 10`) deviennent inatteignables en pratique.

### Option B — SSE sur API Gateway HTTP API (état actuel du corpus)

Conserver HTTP API et accepter le tampon.

**Avantages :** aucun changement d'infrastructure ; conserve les intégrations natives d'HTTP API.

**Limites :** ne satisfait pas l'exigence de progressivité — le streaming est émulé de fait. Impose
d'assumer publiquement le mode `emulated` de `V2-LLD-003 §7` comme mode **nominal** et non comme
repli. Le plafond de 29 s reste à contourner par le mode asynchrone.

### Option C — SSE sur API Gateway REST API en mode `STREAM`

Basculer la route conversationnelle sur un REST API avec `responseTransferMode = STREAM`,
intégration privée `HTTP_PROXY` via VPC Link vers l'ALB interne.

**Avantages :** streaming réellement progressif de bout en bout ; plafond de durée porté à
15 minutes sans demande de quota ; `text/event-stream` de Runtime relayé sans réencapsulation ;
le mode `emulated` redevient ce qu'il doit être, un repli exceptionnel.

**Limites :** REST API au lieu d'HTTP API sur cette route — coût par requête plus élevé, et les
en-têtes de propagation de claims de `V2-LLD-001 §7.1` doivent être reconstruits explicitement au
lieu de s'appuyer sur les mécanismes d'HTTP API. Nécessite VPC Link V2 pour viser l'ALB sans NLB
intermédiaire.

### Option D — WebSocket API

Canal bidirectionnel persistant.

**Avantages :** progressivité native ; canal d'annulation intégré ; pas de contrainte de durée de
réponse.

**Limites :** abandonne SSE décidé au HLD §6.5 ; impose une gestion d'état de connexion
(`$connect`/`$disconnect`, table de connexions) que ni `V2-LLD-001` ni `V2-LLD-010` ne prévoient ;
modèle de programmation différent côté FastAPI et frontend ; surcoût de complexité non justifié pour
un flux unidirectionnel serveur → client.

## Décision — transport

Retenir **l'option C**.

```text
Browser (EventSource)
  -> CloudFront (cache désactivé sur /api/*)
  -> API Gateway REST API, endpoint Regional, responseTransferMode = STREAM
  -> VPC Link V2
  -> ALB interne
  -> FastAPI sur ECS/Fargate (StreamingResponse)
  -> AgentCore Runtime (InvokeAgentRuntime, text/event-stream)
  -> Bedrock Converse (ConverseStream)
```

Points structurants de cette décision :

- **REST API, pas HTTP API, sur la route conversationnelle.** Les routes non conversationnelles
  (documents, administration) n'ont pas besoin de diffuser et peuvent rester sur HTTP API ; le choix
  d'unifier ou non les deux familles de routes revient à `V2-LLD-001`, cet ADR n'impose que la route
  conversationnelle.
- **Endpoint Regional, pas edge-optimized.** L'idle timeout d'un endpoint edge-optimized est de
  30 secondes, ce qui ruine l'intérêt du streaming. La distribution CloudFront de `V2-ADR-001` reste
  en frontal ; elle est distincte du CloudFront managé d'un endpoint edge-optimized.
- **Le mode `emulated` de `V2-LLD-003 §7` reste au contrat**, mais comme repli explicite si la
  précondition d'infrastructure n'est pas prouvée — pas comme mode nominal.
- Le mode asynchrone `operationId` + endpoint de reprise de `V2-LLD-001 §7.2` **reste utile**
  au-delà de 15 minutes et pour la reprise après déconnexion réseau. Il n'est plus le
  contournement d'une limite de 29 secondes.

## Plafonds temporels de la chaîne et réconciliation des budgets

Le streaming introduit des plafonds que les budgets de `V2-LLD-003 §5.2` doivent respecter — sinon
un budget nominalement valide est tué par l'infrastructure avant d'être atteint.

| Plafond | Valeur | Portée |
|---|---|---|
| Durée totale d'un flux (API Gateway `STREAM`) | 15 min | dur, non ajustable |
| Idle timeout API Gateway (Regional / privé) | 5 min | dur — silence maximal toléré |
| Idle timeout ALB | configurable, défaut 60 s | à aligner sur le keep-alive |
| Débit au-delà de 10 Mo de payload | 2 Mo/s | non contraignant pour du texte |

**Keep-alive obligatoire.** Un tour agentique qui appelle un tool lent peut rester silencieux
plusieurs dizaines de secondes. FastAPI doit émettre un commentaire SSE (`: ping`) à intervalle
régulier — proposition : **15 secondes**, soit une marge confortable sous l'idle timeout ALB par
défaut de 60 s et très en dessous des 5 minutes d'API Gateway. Sans keep-alive, un appel de tool de
70 secondes fait tomber le flux, et le symptôme observé sera une déconnexion inexpliquée.

**Plafond de `deadlineEpochMs`.** `V2-LLD-003` doit borner la deadline conversationnelle sous les
15 minutes de la chaîne. Proposition : valeur nominale **120 secondes**, plafond dur configurable
**600 secondes**. Une deadline supérieure à 15 minutes est une erreur de configuration et doit être
rejetée au démarrage, pas découverte en production.

## Choix du mécanisme d'annulation

SSE est unidirectionnel : `EventSource` ne peut rien envoyer au serveur. L'annulation exige donc un
mécanisme hors du flux.

### Option A — Détection de déconnexion seule

Le client ferme `EventSource` ; FastAPI détecte via `request.is_disconnected()`.

**Avantages :** aucune route supplémentaire ; aucun état partagé.

**Limites :** la propagation de la fermeture à travers CloudFront puis API Gateway n'est pas
garantie ni immédiate. Tant que la déconnexion n'est pas vue, la boucle agentique continue et **la
facturation Bedrock continue** — ce qui viole l'exigence d'arrêt de la consommation. Aucune trace
d'audit : on ne distingue pas une annulation d'un incident réseau.

### Option B — Endpoint d'annulation explicite et registre partagé

`POST /api/v1/operations/{operationId}/cancel` inscrit une marque d'annulation dans un registre
partagé ; la tâche qui exécute le flux consulte cette marque aux points d'annulation.

**Avantages :** fiable et observable ; fonctionne même si la requête d'annulation atterrit sur une
**autre tâche ECS** que celle qui diffuse — cas nominal derrière un ALB à plusieurs cibles ;
autorisable par `V2-ADR-006` ; auditable ; distingue annulation, deadline et incident.

**Limites :** une route et un registre partagé de plus ; une lecture du registre par point
d'annulation ; l'annulation est coopérative, donc non instantanée.

### Option C — WebSocket pour le canal d'annulation

**Avantages :** annulation immédiate et bidirectionnelle.

**Limites :** réintroduit toute la complexité de l'option D du transport pour un seul message. Non
retenu.

## Décision — annulation

Retenir **l'option B comme mécanisme nominal**, avec l'option A conservée comme **signal
complémentaire de meilleur effort** : les deux alimentent le même drapeau coopératif. La
déconnexion, quand elle est détectée, économise du temps de calcul ; elle n'est jamais la seule
garantie.

**Sémantique d'annulation coopérative.** Les points d'annulation sont évalués :

- avant l'invocation du modèle pour un nouveau tour ;
- avant l'émission d'un appel de tool ;
- jamais **pendant la transaction** qui applique l'effet de bord d'un tool. La fenêtre non annulable
  est cette transaction seule, **pas l'appel de tool entier** : la résolution de la référence de
  commande, sa lecture et la construction de la mutation la précèdent, et restent interruptibles —
  aucune ne laisse d'état partiel. Un tool de proposition, qui ne porte par construction aucun effet
  de bord (`V2-ADR-014`), reste annulable sur toute sa durée. La garantie d'idempotence des tools
  relève de `V2-ADR-014` et de `V2-LLD-004`.

Cette formulation remplace celle des rédactions antérieures — « l'annulation attend la fin de
l'appel en cours » — qui décrivait une fenêtre plus large que nécessaire. Immobiliser l'annulation
sur l'appel entier suspendrait le contrôle pendant des phases qui, elles, s'interrompent sans
conséquence. C'est la réduction que `V2-ADR-014` revendique en rendant l'exécution atomique : seule
la transaction est indissociable.

**Effets d'une annulation :**

- arrêt de la consommation du flux Converse ;
- **aucune écriture AgentCore Memory** — le contrat de `V2-LLD-003 §2.5` n'écrit qu'après le dernier
  tour réussi, et une invocation annulée n'est pas réussie ;
- émission d'un événement SSE `cancelled` portant les compteurs réellement consommés, pour que le
  coût engagé reste visible et non silencieux ;
- inscription d'un état terminal dans le registre, afin qu'une reprise ne ressuscite pas
  l'opération ;
- comptabilisation des tokens déjà consommés dans les métriques de coût de `V2-LLD-003 §10`. Une
  annulation réduit le coût, elle ne l'annule pas.

Le choix technique du registre partagé (table DynamoDB dédiée ou réutilisation d'une table
existante, TTL, forme des clés) est **délégué à `V2-LLD-006`**, qui possède les modèles de
données. Cet ADR n'impose que ses propriétés : partagé entre tâches, borné dans le temps,
autorisable par tenant et **lu en cohérence forte à chaque point d'annulation**.

La cohérence forte n'est pas un détail de réalisation délégable. Une lecture à cohérence éventuelle
peut ne pas voir une marque écrite quelques centaines de millisecondes plus tôt par une autre
tâche : le tour suivant ou l'appel de tool suivant partirait malgré l'annulation, et la
consommation facturée continuerait — précisément ce que l'exigence d'arrêt de la consommation
interdit. C'est aussi la condition sans laquelle la preuve d'annulation inter-tâches ne peut pas
être tenue.

## Contrat d'événements SSE

Le contrat détaillé revient à `V2-LLD-001` (transport) et `V2-LLD-010` (frontend). Cet ADR fixe le
jeu d'événements minimal, pour que les deux LLD ne divergent pas :

| Événement | Charge utile | Rôle |
|---|---|---|
| `meta` | `{"streaming": "native" ou "emulated", "operationId": "..."}` | premier événement, déclare le mode |
| `delta` | `{"text": "..."}` | fragment de réponse |
| `citation` | citations issues du `retrievalContext` | traçabilité RAG |
| `done` | compteurs de tours, tokens entrée/sortie, `degraded` | fin normale |
| `cancelled` | cause (`client`, `deadline` ou `operator`) et compteurs consommés | fin par annulation |
| `error` | `AgentErrorCode` de `V2-LLD-003 §3.2` | fin en erreur |
| `: ping` | commentaire SSE | keep-alive, sans sémantique applicative |

**Reprise après déconnexion.** SSE reconnecte automatiquement. En V2, une reconnexion **ne rejoue
pas** les fragments déjà émis : elle se rattache à l'opération par `operationId` et reçoit l'état
courant ou le résultat final persisté. Le rejeu token par token est hors périmètre V2.

## Écarts à corriger dans le corpus

Cette décision rend trois passages inexacts. Ils doivent être corrigés dans le même lot que
l'acceptation de cet ADR, sans quoi le corpus porte une contradiction :

| Document | Passage | Correction attendue |
|---|---|---|
| `HLD §6.5` | « API Gateway HTTP API applique un timeout dur de 29 secondes » comme seule contrainte, et justification de SSE par la compatibilité streaming du chemin | mentionner le tampon d'HTTP API et renvoyer à cet ADR pour le type d'API Gateway |
| `V2-LLD-001 §7.2` | « Mode direct (réponses ≤ 25 s) → streaming SSE direct » sur HTTP API | requalifier : le streaming progressif exige REST API en mode `STREAM` ; ajouter le keep-alive et l'alignement de l'idle timeout ALB |
| `V2-LLD-001 §7` | diagramme « API Gateway HTTP API » sur la route conversationnelle | refléter le type retenu et VPC Link V2 |
| `V2-LLD-003 §7` | `⚠ ADR MANQUANT` et hypothèse « si Runtime ne stream pas nativement » | lever le marqueur ; Runtime diffuse nativement, le mode `emulated` devient un repli d'infrastructure |

`V2-ADR-001` déclare `V2-ADR-011` dans ses dépendances (ligne 6) alors que cet ADR dépend de lui :
**c'est un cycle**, de même nature que celui déjà identifié entre `V2-ADR-001` et `V2-ADR-007`. La
relation n'est pas symétrique — `V2-ADR-001` décide la frontière et anticipait seulement le
streaming, tandis que cet ADR réalise le transport sur le chemin décidé. La référence à
`V2-ADR-011` doit être retirée de la ligne 6 de `V2-ADR-001`.

## Préconditions

Comme pour `V2-ADR-019`, la décision d'architecture est prise mais son activation dépend de faits à
prouver :

- disponibilité du *response streaming* API Gateway REST (`responseTransferMode = STREAM`) en
  `eu-west-3` ;
- disponibilité des **VPC Links V2** pour REST API vers ALB en `eu-west-3` — à défaut, un NLB
  intermédiaire est requis (VPC Link V1), ce qui ajoute un saut réseau et un coût que
  `V2-ADR-007` et `V2-LLD-001` n'ont pas provisionnés ;
- confirmation que CloudFront ne tamponne pas le flux avec la politique de cache retenue ;
- confirmation nominative des limites citées (15 min, 5 min d'idle) contre la documentation en
  vigueur au moment de l'implémentation.

Tant que ces preuves ne sont pas produites, le repli est le mode `emulated` déclaré de
`V2-LLD-003 §7`, sans nouvel ADR.

## Conséquences

- la route conversationnelle et les routes documentaires peuvent ne plus partager le même type
  d'API Gateway ; `V2-LLD-001` doit assumer soit deux configurations, soit une unification sur
  REST API, avec l'écart de coût par requête associé ;
- les en-têtes de propagation de claims de `V2-LLD-001 §7.1` doivent être revalidés pour REST API :
  les mécanismes natifs d'HTTP API ne s'y transposent pas tels quels ;
- l'idle timeout de l'ALB devient un paramètre critique et non plus un réglage par défaut ;
- un keep-alive absent ou mal réglé produit des déconnexions difficiles à diagnostiquer : il doit
  être couvert par un test, pas seulement par une valeur de configuration ;
- l'annulation devient une capacité de premier ordre, avec une route, une autorisation, un registre
  partagé et un état terminal — elle n'est pas un effet de bord de la fermeture du navigateur ;
- `V2-LLD-003 §7` et `§8` peuvent perdre leur marqueur `⚠ ADR MANQUANT` pour la partie streaming ;
  la partie fallback modèle reste ouverte sur `V2-ADR-012` ;
- le coût Bedrock d'une conversation annulée n'est pas nul et doit apparaître dans les métriques.

## Preuves attendues

- **progressivité mesurée**, pas déclarée : time-to-first-token observé côté navigateur
  significativement inférieur à la durée totale de la réponse, sur le chemin complet CloudFront →
  API Gateway → ALB → FastAPI. Une réponse arrivant en un bloc invalide la configuration ;
- conversation multi-tours dépassant 29 secondes puis 60 secondes, diffusée sans rupture ;
- appel de tool de plus de 60 secondes de silence : le flux survit grâce au keep-alive ;
- annulation depuis un onglet dont la requête `cancel` atterrit sur une **autre tâche ECS** que
  celle qui diffuse : l'annulation est effective ;
- annulation pendant un appel de tool à effet de bord : l'effet est soit complet, soit absent,
  jamais partiel ;
- vérification que les tokens consommés avant annulation apparaissent dans les métriques de coût ;
- tentative d'annulation d'une opération appartenant à un autre tenant : refusée ;
- déconnexion réseau brutale suivie d'une reconnexion : rattachement par `operationId` sans rejeu ni
  double facturation ;
- vérification que le mode annoncé dans l'événement `meta` correspond au comportement réel observé.

## Références AWS

- API Gateway — *Stream the integration response for your proxy integrations*
  (`responseTransferMode`, REST APIs uniquement, limites de durée et de débit) ;
- API Gateway — annonce du *response streaming* pour les REST APIs (novembre 2025) ;
- API Gateway — *Private integrations for REST APIs* et VPC Links V2 vers Application Load Balancer
  (novembre 2025) ;
- API Gateway — *Troubleshoot issues with response streaming* ;
- Amazon Bedrock AgentCore — `InvokeAgentRuntime` et *Stream agent responses*
  (`text/event-stream`) ;
- Amazon Bedrock — `ConverseStream` ;
- Elastic Load Balancing — idle timeout de l'Application Load Balancer.
