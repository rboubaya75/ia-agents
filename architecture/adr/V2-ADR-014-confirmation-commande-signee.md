# V2-ADR-014 — Confirmation forte et objet de commande

- **Statut :** Draft (propositions — en attente de revue et de validation)
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** `V2-ADR-006` (identité de confiance et autorisation), `V2-ADR-002` (répartition
  FastAPI/Runtime), `V2-ADR-005` (agents et contrôle des tools), `V2-ADR-011` (annulation et effets
  de bord), `V2-ADR-010` (ledger et restauration)
- **Préconditions à prouver avant implémentation :** capacité d'AgentCore Gateway MCP à exposer un
  tool en deux appels distincts et capacité transactionnelle du magasin de commandes (voir
  « Préconditions »).
- **Documents impactés :** `V2-ADR-006`, `V2-ADR-011` ; `architecture/hld` §6.3 et §6.4 ;
  `capability-allocation-matrix.md` Domaines 5 et 7 ; `V2-LLD-006` §5 ; `LLD-V2-INDEX-FR.md`
  (portée `V2-LLD-004`) — voir « Écarts à corriger dans le corpus ».

## Contexte

La V1 a traité l'idempotence des mutations (`docs/adr/ADR-0006`) puis la confirmation
(`docs/adr/ADR-0007`). Ce second ADR a imposé un contrôle serveur : le Runtime vérifie que le
message utilisateur courant commence par une formulation contrôlée (« Je confirme la création… »),
injecte `confirmationVerified=true|false`, et la Lambda refuse toute mutation dont la valeur n'est
pas exactement `true`.

Ce contrôle a fermé la faille la plus visible — le modèle ne peut plus décider seul d'un effet de
bord. `ADR-0007` énonce toutefois lui-même ce qu'il ne couvre pas :

> « Elle ne remplace pas encore un workflow métier de confirmation signé et lié à un plan précis ;
> ce renforcement pourra être traité dans une phase dédiée. »

et, dans ses limites assumées :

> « la confirmation textuelle est liée au tour courant, mais pas encore à un objet de commande
> signé. »

Cet ADR est cette phase dédiée. Il tranche trois questions que le corpus V2 mentionne sans les
instruire — le HLD §6.3 se contente de « Confirmation vérifiée pour les mutations », et
`LLD-V2-INDEX-FR.md` annonce pour `V2-LLD-004` une « confirmation liée à une commande » dont
aucune décision ne fixe encore la forme :

1. **quelle est l'unité et la forme de l'autorisation** — ce qu'une confirmation atteste ;
2. **par quel canal la confirmation parvient au serveur**, et quels composants la voient passer ;
3. **où et quand la confirmation est vérifiée** par rapport à l'effet de bord.

## Exigences

| Référence | Exigence |
|---|---|
| `V2-ADR-006` | l'identité est résolue côté serveur et jamais produite par le modèle |
| `V2-ADR-006` | un refus est la valeur par défaut lorsqu'une information manque |
| `V2-ADR-002` | le contenu documentaire et Memory sont des données non fiables |
| `V2-ADR-005` | la sélection des tools appartient à Runtime, et le nombre d'appels est borné par `maxToolCalls` |
| `V2-ADR-011` | une annulation ne laisse jamais un effet de bord de tool à moitié appliqué |
| `V2-ADR-010` | aucune mutation n'est rejouée après démarrage confirmé de l'effet de bord |
| Charte §6 | défense contre prompt injection, data poisoning et exfiltration par tool |
| HLD §4 | les mutations sont confirmées, idempotentes et non rejouées après effet de bord |

## Le fait déterminant — un booléen atteste qu'une autorisation a eu lieu, pas ce qui a été autorisé

`confirmationVerified=true` est une **assertion sur un événement**, pas sur un contenu. Il établit
qu'à un instant donné, un message reconnu comme une confirmation a été reçu. Il n'établit rien sur
les arguments effectivement transmis au tool.

Or, entre la phrase de l'utilisateur et l'écriture en base, le payload métier est **produit par le
modèle**. Rien ne le relie à ce qui a été montré, ni à ce qui a été confirmé. Trois écarts en
découlent, de nature différente :

| Écart | Ce que la confirmation couvre | Ce qui est exécuté |
|---|---|---|
| **Portée** | un tour de conversation | une ou plusieurs mutations de ce tour |
| **Contenu** | une intention exprimée en langue naturelle | un payload structuré produit par le modèle |
| **Canal** | un message lu et interprété par le modèle | l'appel de tool dérivé de ce même message |

L'écart de **portée** est le plus simple : `ADR-0007` §2 prévoit explicitement plusieurs mutations
dans un même tour et leur dérive des identifiants distincts, mais le même
`confirmationVerified=true` les autorise toutes. Une confirmation, N effets de bord.

L'écart de **contenu** est le plus grave. L'utilisateur confirme « la création » ; le système
exécute `create_trip(payload)`. Que le `payload` corresponde à ce qui lui a été présenté ne repose
sur aucun mécanisme : cela repose sur le fait que le modèle soit resté cohérent entre deux tours.

L'écart de **canal** est celui qui rend les deux premiers exploitables. La confirmation transite par
le modèle : c'est le Runtime qui lit le message, donc le composant dont on cherche précisément à
borner l'autonomie qui se trouve sur le chemin de l'autorisation.

**Une confirmation qui n'est pas liée à un contenu n'autorise rien de précis.** Elle déplace la
responsabilité de l'utilisateur vers le modèle, sans le dire.

## Ce que le corpus décompose mal — confirmation et idempotence ne sont pas le même problème

`V2-LLD-006` §5 réunit dans un même ledger les clés d'idempotence des mutations `Trips`, des
uploads et des déclenchements d'ingestion. C'est correct pour l'idempotence. Mais le corpus traite
la confirmation comme un attribut de cette même mécanique, alors que les deux répondent à des
questions distinctes :

| Question | Mécanisme | Échec couvert |
|---|---|---|
| « cette action a-t-elle déjà été faite ? » | ledger d'idempotence, hash canonique | rejeu, double exécution |
| « cette action a-t-elle été autorisée, et laquelle ? » | **objet de commande** | effet de bord non voulu |

Un ledger d'idempotence parfait n'empêche pas d'exécuter **exactement une fois** une action que
personne n'a autorisée. Inversement, une confirmation parfaite n'empêche pas de l'exécuter deux
fois. Les deux sont nécessaires, et le corpus gagne à ne pas les confondre — d'autant que, comme
montré plus bas, un même objet peut servir les deux, à condition que ce soit une conséquence
décidée et non une coïncidence d'implémentation.

## Choix de la forme de l'autorisation

### Option A — Booléen de tour (statu quo `ADR-0007`)

Conserver `confirmationVerified` injecté par le Runtime et vérifié par le tool.

Les trois écarts ci-dessus subsistent intégralement. L'option n'est conservée que comme référence :
elle reste le comportement V1 en production tant que cet ADR n'est pas réalisé.

### Option B — Jeton signé portant le payload

Le serveur construit le payload, calcule une signature (HMAC ou KMS) sur sa forme canonique liée à
`actorId`, `tenantId` et une expiration, et transmet l'ensemble. Le tool vérifie la signature avant
d'exécuter.

L'écart de contenu est fermé : le payload exécuté est celui qui a été signé. Deux défauts
subsistent, dont un rédhibitoire.

D'abord, **une signature ne borne pas le nombre d'usages**. Un jeton valide rejoué deux fois est
vérifié deux fois avec succès. Rendre le jeton à usage unique impose un état partagé — donc le
magasin que l'option prétendait éviter.

Ensuite, la vérification est **disjointe de l'écriture**. Entre le contrôle de signature et l'effet
de bord subsiste une fenêtre pendant laquelle deux exécutions concurrentes du même jeton passent
toutes deux le contrôle. C'est le mode d'échec que `ADR-0007` §4 avait déjà résolu pour
l'idempotence par une transaction, et que cette option réintroduit pour l'autorisation.

### Option C — Objet de commande matérialisé côté serveur, confirmé par référence

Le serveur matérialise une **commande** : un enregistrement durable décrivant exactement l'action à
exécuter, portant un `commandId`, l'identité qui pourra la confirmer et un état. La confirmation
porte sur ce `commandId`. L'exécution charge la commande depuis le magasin et applique **son**
contenu.

Le payload ne voyage plus : il est écrit une fois, par le serveur, et lu au moment de l'exécution.
L'usage unique est obtenu par une transition d'état conditionnelle, atomique, dans la transaction
qui porte l'effet de bord.

## Décision — Forme de l'autorisation

**Option C.**

Une commande est un objet du domaine, pas un jeton. Trois règles la définissent :

- **la commande est matérialisée par le serveur, jamais par le modèle.** Le modèle fournit une
  intention et des paramètres ; le tool de proposition les valide, les normalise et écrit la
  commande. Ce qui n'a pas passé la validation n'existe pas comme commande ;
- **seul le `commandId` circule.** Le contenu de la commande ne transite ni par le modèle, ni par
  le client, ni par la Gateway MCP. À l'exécution, le tool charge la commande stockée et **ignore
  tout argument métier transmis par le modèle** ;
- **une commande est à usage unique**, garanti par une transition d'état conditionnelle et non par
  une convention d'appel.

La conséquence de la deuxième règle mérite d'être explicitée, parce qu'elle change la nature de la
garantie : une divergence entre ce qui a été confirmé et ce qui est exécuté n'est pas *détectée*,
elle est **impossible à produire** — les deux désignent le même enregistrement.

C'est aussi la raison pour laquelle la décision retenue ne comporte pas de signature, contrairement
à ce que le titre initial du backlog (« objet de commande signé ») laissait attendre. Une signature
protège un contenu qui voyage. Ici, le contenu ne voyage pas : le seul élément transporté est une
référence opaque, inexploitable sans le magasin qui la résout et sans l'identité qui l'a créée.
**L'écart avec l'intitulé du backlog est délibéré** et doit y être reporté.

## Choix du canal de confirmation

### Option A — Message conversationnel analysé (statu quo `ADR-0007`)

Le Runtime reconnaît une formulation contrôlée dans le message utilisateur.

Deux objections. La première est que l'autorisation emprunte le canal du modèle : elle est lue,
interprétée et transmise par le composant dont l'ADR cherche à borner l'autonomie. La seconde est
que la reconnaissance repose sur des préfixes en langue naturelle, donc sensible à la formulation,
à la langue et au contexte — un utilisateur peut prononcer la formule sans intention d'autoriser
l'action que le système s'apprête à exécuter.

### Option B — Action authentifiée dédiée, hors du chemin du modèle

La confirmation est un appel HTTP distinct vers FastAPI, portant le `commandId`, authentifié par le
même jeton Cognito que le reste de la session et validé par API Gateway (`V2-ADR-001`).

Le modèle n'est pas sur ce chemin : il ne voit pas la confirmation, ne la produit pas et ne peut pas
la simuler. La reconnaissance d'intention disparaît de la chaîne d'autorisation — il n'y a plus de
texte à interpréter, seulement un identifiant et une identité à comparer.

## Décision — Canal de confirmation

**Option B — appel authentifié dédié.**

Ce choix est cohérent avec `V2-ADR-011`, qui a déjà sorti l'annulation du flux conversationnel pour
en faire un appel dédié : une action de contrôle ne se transmet pas dans le même canal que le
contenu qu'elle contrôle.

La conséquence pour l'interface est assumée : une action mutante n'est pas confirmable par un
message. Elle est confirmable par un geste explicite portant sur une commande affichée. Le détail
de présentation relève de `V2-LLD-010`, mais une contrainte est fixée ici, parce qu'elle est de
nature architecturale :

**le résumé présenté à l'utilisateur est rendu par le serveur à partir de la commande stockée,
jamais rédigé par le modèle.** Sans cette règle, le modèle pourrait décrire une action et en faire
matérialiser une autre : la confirmation serait de nouveau une autorisation portant sur autre chose
que ce qui s'exécute, avec un mécanisme plus coûteux pour la même faille.

## La séquence d'une action mutante

Les deux décisions ci-dessus se composent en une séquence de quatre temps. Elle est énoncée ici
parce qu'elle est la référence dont `V2-LLD-004` (contrat des tools), `V2-LLD-010` (interface) et
la CAM dérivent leurs contrats respectifs.

```text
1. Matérialisation
     modèle ──► Gateway MCP ──► tool de proposition
       le tool valide, normalise, écrit la commande [ pending ] et retourne le commandId
       aucun effet de bord métier

2. Présentation
     FastAPI lit la commande stockée et rend le résumé, transmis au client dans le flux SSE
       le modèle ne rédige pas ce résumé

3. Confirmation
     utilisateur ──► API Gateway ──► FastAPI (endpoint dédié, commandId)
       identité vérifiée, transition [ pending ] ─► [ confirmed ]
       le modèle n'est pas sur ce chemin

4. Exécution
     modèle ──► Gateway MCP ──► tool d'exécution (commandId seul)
       le tool charge la commande, applique [ confirmed ] ─► [ executed ]
       et l'effet de bord dans la même transaction
```

Deux points de cette séquence ne sont pas de simples détails de réalisation.

**La matérialisation et l'exécution sont deux tools distincts**, et non deux modes d'un même tool.
Cette séparation permet des politiques d'autorisation distinctes au niveau de la Gateway
(`V2-ADR-006`) et rend l'absence d'effet de bord de la matérialisation vérifiable par inspection du
catalogue plutôt que par lecture du code.

**FastAPI n'appelle aucun tool** : conformément à la CAM Domaine 7, la Gateway est le seul point
d'entrée et les tools sont appelés depuis Runtime. Le rôle de FastAPI se limite ici à lire le
magasin de commandes pour rendre le résumé (temps 2) et à porter l'endpoint de confirmation
(temps 3). Cette séquence n'introduit donc aucun chemin d'appel nouveau dans l'architecture.

## Le point de vérification — atomicité avec l'effet de bord

Vérifier une confirmation « avant » l'appel du tool ne suffit pas : entre le contrôle et l'écriture,
l'état peut changer. C'est le même raisonnement qui a conduit `ADR-0007` §4 à placer la mise à jour
du voyage et la création de l'entrée de ledger dans une transaction unique.

La règle retenue est donc : **la transition d'état de la commande et l'effet de bord sont appliqués
dans la même transaction**. Le tool ne « vérifie puis écrit » pas ; il écrit sous condition que la
commande soit encore dans l'état attendu, et l'échec de la condition annule l'effet de bord.

Il en résulte que la vérification appartient au **tool**, au point exact où l'effet se produit — et
non au Runtime, ni à FastAPI, ni à la Gateway. Les contrôles en amont restent utiles pour échouer
tôt et donner un message clair, mais ils ne sont pas la garantie. La garantie est la condition
transactionnelle.

## Cycle de vie d'une commande

```text
   matérialisation (tool de proposition via Gateway MCP, depuis l'intention du modèle)
                                   │
                                   ▼
                              [ pending ] ──── expiration TTL ────► [ expired ]
                                   │
              confirmation (appel authentifié, identité vérifiée)
                                   │
                                   ▼
                             [ confirmed ] ─── expiration TTL ────► [ expired ]
                                   │
        exécution : transition conditionnelle + effet de bord, même transaction
                                   │
                                   ▼
                             [ executed ]  (état terminal, rejeu refusé)
```

Les propriétés que cet ADR impose, indépendamment du magasin retenu :

- **deux fenêtres d'expiration distinctes** : une commande jamais confirmée expire ; une commande
  confirmée mais jamais exécutée expire également. Une autorisation ancienne n'autorise plus rien,
  et la seconde fenêtre est nettement plus courte que la première ;
- **la confirmation vérifie l'identité**, et pas seulement la connaissance du `commandId` : seule
  l'identité de confiance (`V2-ADR-006`) qui a fait matérialiser la commande peut la confirmer ;
- **`executed` est terminal** : un rejeu ne produit pas un second effet de bord et ne renvoie pas
  une erreur d'autorisation, mais le résultat de l'exécution initiale ;
- **l'état `executed` tient lieu d'enregistrement d'idempotence** pour la mutation qu'il porte.
  C'est la réponse à la question laissée ouverte plus haut : le même objet sert l'autorisation et
  l'idempotence, et c'est une conséquence décidée. Une mutation passée par une commande **n'écrit
  pas d'entrée dans le ledger** de `V2-LLD-006` §5, qui reste réservé aux opérations sans commande
  — uploads documentaires et déclenchements d'ingestion ;
- **la rétention d'une commande `executed` ne peut pas être inférieure à la fenêtre d'idempotence
  exigée pour la mutation qu'elle porte.** C'est la contrepartie du point précédent : dès lors que
  l'état `executed` est le seul enregistrement d'idempotence de cette mutation, sa purge rouvre la
  possibilité d'un second effet de bord. Cette borne ne se déduit pas des deux TTL ci-dessus — ceux-là
  bornent l'autorisation, celle-ci borne la garantie de non-rejeu, et les deux fenêtres n'ont ni la
  même durée ni le même objet ;
- **aucune transition ne remonte** : une commande n'est pas modifiable. Un changement d'avis
  produit une nouvelle commande, la précédente expirant sans effet ;
- **une annulation ne transitionne pas la commande** : elle la laisse dans son état courant, où
  l'expiration la rend inexécutable. Aucun état `cancelled` n'est introduit — il n'apporterait rien
  qu'une expiration ne garantisse déjà, et sa propagation exigerait de coupler le registre
  d'opérations de `V2-ADR-011` au magasin de commandes.

Le choix du magasin, la valeur des TTL et la forme des clés sont délégués à `V2-LLD-006`, qui
possède les modèles de données, et le contrat du tool à `V2-LLD-004`. Cet ADR n'impose que les
propriétés ci-dessus.

## Ce que le modèle ne peut plus obtenir

Le corpus traite le contenu documentaire et Memory comme des données non fiables (`V2-ADR-002`,
HLD §4) et la Charte §9 identifie l'injection documentaire comme risque : un document ingéré peut
contenir des instructions que le modèle suivra.

Avec la décision ci-dessus, l'injection indirecte conserve un pouvoir et en perd un autre. Un
document peut amener le modèle à faire **matérialiser** une commande — c'est un appel sans effet de
bord, borné par la validation serveur et par l'autorisation `V2-ADR-006`. Il ne peut pas amener le
modèle à la **confirmer**, parce que la confirmation n'est pas un appel dont le modèle dispose :
elle arrive par un canal authentifié auquel il n'a pas accès.

La conséquence est nette et vaut d'être énoncée comme telle : **une injection réussie produit au
pire une proposition d'action visible par l'utilisateur, jamais un effet de bord.** C'est le
résultat que la seule mesure de « filtrage des actions » mentionnée par la Charte §9 ne peut pas
garantir, parce qu'un filtre porte sur la forme d'un appel, pas sur son origine.

Cette propriété suppose que la matérialisation reste sans effet observable. Un tool de préparation
qui réserverait une ressource, enverrait une notification ou consommerait un quota externe
romprait la garantie : la contrainte « la matérialisation n'a pas d'effet de bord » est donc une
règle de conception des tools, vérifiable en revue, et non une propriété acquise.

## Classification des actions

Le mécanisme n'a de valeur que si aucune action mutante ne peut y échapper par omission. La règle
est donc déclarative et **fail-closed** :

- chaque tool déclare sa classe dans le catalogue : `read` (aucun effet de bord) ou `mutating` ;
- **un tool qui ne déclare pas sa classe est traité comme `mutating`.** Un oubli de déclaration
  rend le tool inutilisable sans commande confirmée, jamais exécutable sans confirmation ;
- la classe est une propriété du **catalogue de tools**, pas un paramètre d'appel : le modèle ne
  peut pas la produire, la surcharger ni l'inférer.

Les actions concernées sont celles dont **les paramètres sont produits par le modèle**. Une mutation
déclenchée directement par l'utilisateur via une API REST (suppression d'un document depuis
l'interface, par exemple) n'entre pas dans ce périmètre : elle est déjà l'expression d'une intention
utilisateur explicite, et aucun mandataire ne s'interpose. Y appliquer le même mécanisme
ajouterait une étape sans fermer d'écart.

## Ce que l'objet de commande remplace

`ADR-0007` §2 dérive, pour chaque mutation, un UUID v5 à partir du `requestOperationId`, du nom
canonique du tool, du hash canonique du payload et du **rang d'occurrence** dans le tour. Cette
dérivation existe parce qu'aucun objet durable ne portait l'identité d'une mutation : il fallait la
reconstruire par calcul, et la reproduire à l'identique en cas de rejeu.

Une commande matérialisée porte cette identité par construction. La dérivation devient inutile, et
avec elle la limite que `ADR-0007` reconnaissait :

> « la stabilité d'un replay agentique suppose que le modèle reproduise le même ordre et le même
> payload métier. »

Cette hypothèse disparaît : le rejeu porte sur un `commandId` déjà écrit, pas sur une valeur que le
modèle doit reproduire. C'est une simplification nette du mécanisme V1, à reporter dans
`V2-LLD-004` et `V2-LLD-006`.

## Interaction avec l'annulation

`V2-ADR-011` a établi qu'une annulation n'est jamais évaluée **pendant** l'exécution d'un tool
porteur d'effet de bord, et renvoie explicitement à cet ADR pour la garantie d'idempotence. La
décision retenue améliore cette situation sur deux plans.

La **fenêtre non annulable se réduit** : la matérialisation est sans effet de bord, donc librement
annulable ; seule l'exécution est atomique et non interruptible, et elle est nettement plus courte
qu'un appel de tool réalisant validation, décision et écriture en une fois.

L'**annulation entre confirmation et exécution devient sûre** : la commande reste `confirmed` et
expire sans effet. Aucun état partiel n'existe, puisque l'effet de bord et la transition sont
indissociables.

Une commande confirmée mais non exécutée à l'issue d'une annulation ne doit pas pouvoir être
exécutée par une reprise ultérieure de la conversation : la fenêtre d'expiration courte de l'état
`confirmed` est ce qui borne ce risque.

## Réalisation par phase

| Aspect | Phase V2 | Phase V3 |
|---|---|---|
| Actions concernées | tools Trips (`create`, `update`) repris de la V1 | tools Trips et actions documentaires agentiques |
| Matérialisation | tool de proposition derrière Gateway MCP, sans effet de bord | inchangée |
| Présentation du résumé | FastAPI, depuis la commande stockée (`V2-LLD-010`) | inchangée |
| Magasin de commandes | table dédiée (`V2-LLD-006`) | inchangé |
| Confirmation | endpoint FastAPI dédié (`V2-LLD-001`, `V2-LLD-010`) | inchangée |
| Exécution | tool d'exécution derrière Gateway MCP | inchangée |

Le mécanisme est indépendant du phasage RAG de `V2-ADR-019` : il porte sur les actions métier, non
sur l'ingestion documentaire. Il est en revanche **à réaliser dès la V2**, parce que la V1 expose
déjà des tools mutants et que la confirmation actuelle est le contrôle qui les protège.

## Écarts à corriger dans le corpus

À corriger dans le même lot que l'acceptation de cet ADR :

| Document | Passage | Correction attendue |
|---|---|---|
| `V2-ADR-BACKLOG-FR.md` | intitulé « Confirmation forte et objet de commande signé » | retirer « signé » ; le contenu ne circule pas, seule la référence circule |
| `V2-ADR-006` | « Modèle d'autorisation », points 1 à 6 | ajouter la commande confirmée comme fondement d'autorisation des actions mutantes |
| `V2-ADR-011` | renvoi « la garantie d'idempotence des tools relève de `V2-ADR-014` » | préciser que la fenêtre non annulable est l'exécution, et non l'appel de tool entier |
| HLD §6.3 | « 3. Confirmation vérifiée pour les mutations » | remplacer par la séquence matérialisation → confirmation hors modèle → exécution atomique |
| HLD §6.4 | « Tool Selection, confirmation si mutation » | distinguer les deux appels et situer la confirmation hors du chemin du modèle |
| `capability-allocation-matrix.md` Domaine 5 | capacités du Runtime | énoncer que le Runtime ne porte pas la vérification de confirmation |
| `capability-allocation-matrix.md` Domaine 7 | capacités MCP | ajouter la classe de tool (`read`/`mutating`) au catalogue, avec défaut `mutating` |
| `V2-LLD-006` §5 | ledger d'idempotence, portée « mutations `Trips` » | retirer les mutations via commande de la portée du ledger ; ajouter le magasin de commandes, ses clés et les TTL des deux fenêtres ; borner la rétention d'une commande `executed` par la fenêtre d'idempotence de la mutation qu'elle porte |
| `LLD-V2-INDEX-FR.md` | portée `V2-LLD-004` : « confirmation liée à une commande » | aligner sur la décision : deux appels, exécution par référence, classe de tool |
| `LLD-V2-INDEX-FR.md` | portée `V2-LLD-010` | ajouter le rendu serveur du résumé de commande et le geste de confirmation |

## Préconditions

La décision est prise ; son activation dépend de faits à prouver avant implémentation :

- **capacité d'AgentCore Gateway MCP à exposer deux tools distincts** pour la matérialisation et
  l'exécution, avec des politiques d'autorisation distinctes — faute de quoi la séparation repose
  sur la seule discipline d'implémentation du tool ;
- **capacité transactionnelle du magasin de commandes** : la transition conditionnelle et l'effet de
  bord doivent tenir dans une transaction unique. Le pattern `TransactWriteItems` de `ADR-0007` §4
  est le candidat, sous réserve que la commande et la cible métier soient dans la même région et
  compatibles avec la limite d'items par transaction ;
- **rétention d'une commande `executed`** : renvoyer le résultat initial suppose que ce résultat soit
  conservé, ce qui doit être arbitré avec la politique de rétention de `V2-LLD-006`. L'enjeu dépasse
  le confort du rejeu — l'état `executed` tenant lieu d'enregistrement d'idempotence, sa purge rouvre
  la possibilité d'un second effet de bord. Si la rétention retenue ne peut pas couvrir la fenêtre
  d'idempotence exigée, la réponse conforme est de conserver au-delà une entrée réduite valant
  enregistrement de non-rejeu ; jamais de laisser la commande disparaître en silence ;
- **budget temps de la transaction d'exécution** : la transition conditionnelle et l'effet de bord
  étant indissociables, leur latence cumulée s'impute au tour en cours et doit tenir dans la
  deadline propagée par `operationContext` (`V2-ADR-011`). L'appel de confirmation, lui, est un
  appel court sans enjeu de ce point de vue.

Tant que ces preuves ne sont pas produites, le contrôle `confirmationVerified` de `ADR-0007` reste
en vigueur. Il est insuffisant au sens de cet ADR, mais il n'est pas nul : il continue d'empêcher
une décision autonome du modèle, et son retrait avant réalisation dégraderait la posture.

## Périmètre exclu

- **Les mutations déclenchées directement par l'utilisateur** via une API REST : déjà l'expression
  d'une intention explicite, sans mandataire interposé.
- **La suppression de compte et l'exercice du droit à l'effacement** : relèvent de `V2-ADR-015`,
  qui peut réutiliser le mécanisme sans que cet ADR préempte sa politique.
- **La protection contre l'injection directe** dans le message utilisateur : l'utilisateur est
  authentifié et agit dans son propre périmètre ; l'enjeu est le mandataire, pas l'auteur.
- **Le contenu de l'interface de confirmation** (formulation, mise en forme, accessibilité) :
  relève de `V2-LLD-010`. Cet ADR n'en fixe que l'origine serveur du résumé.
- **Les quotas et la limitation d'abus** sur la matérialisation de commandes : relèvent de
  `V2-ADR-016`.

## Conséquences

- une action mutante cesse d'être un appel de tool unique : elle devient une séquence en deux temps
  séparée par une décision utilisateur, ce qui allonge le parcours et le rend explicite ;
- le modèle sort du chemin d'autorisation : il propose, il n'autorise pas — et cette propriété est
  structurelle, pas obtenue par instruction de prompt ;
- une injection indirecte réussie ne peut plus produire d'effet de bord, seulement une proposition
  visible, à condition que la matérialisation reste sans effet observable ;
- un magasin de commandes s'ajoute au modèle de données et **reprend le rôle du ledger
  d'idempotence pour les mutations via commande**, le ledger restant en usage pour les opérations
  qui n'en ont pas — la clarification de `V2-LLD-006` §5 est un préalable, pas un ajustement ;
- une action mutante consomme **deux appels de tool au lieu d'un**, ce qui s'impute au budget
  `maxToolCalls` de `V2-ADR-005` : son calibrage doit en tenir compte, faute de quoi une
  conversation comportant plusieurs mutations épuiserait le budget plus tôt qu'en V1 ;
- la dérivation d'identifiants de mutation de `ADR-0007` §2 devient inutile, et avec elle
  l'hypothèse de reproductibilité du payload par le modèle en cas de rejeu ;
- la fenêtre non annulable de `V2-ADR-011` se réduit à l'exécution, ce qui améliore la sémantique
  d'annulation sans la modifier ;
- le défaut `mutating` sur classe non déclarée rend un oubli de catalogue bloquant à l'usage plutôt
  que silencieux — c'est un coût d'exploitation assumé, préféré à une exécution non confirmée ;
- une confirmation ne peut plus être exprimée par un message : c'est une rupture d'usage par rapport
  à la V1, à traiter explicitement dans `V2-LLD-010`.

## Preuves attendues

- **exécution sans commande confirmée** : refusée par le tool, y compris lorsque le Runtime
  transmet une identité valide et un payload bien formé. Cette preuve négative est la plus
  importante de l'ADR ;
- **divergence entre le payload proposé et le payload exécuté** : impossible à produire, l'exécution
  ne lisant que la commande stockée — vérifié en transmettant délibérément des arguments métier
  différents à l'exécution ;
- **confirmation par une identité autre que celle qui a fait matérialiser la commande** : refusée,
  y compris avec un `commandId` valide ;
- **rejeu d'une commande `executed`** : aucun second effet de bord, résultat initial renvoyé ;
- **rétention d'une commande `executed`** : la commande reste résoluble pendant toute la fenêtre
  d'idempotence de la mutation qu'elle porte, et un rejeu en fin de fenêtre ne produit pas un second
  effet de bord ;
- **deux exécutions concurrentes du même `commandId`** : une seule aboutit, l'autre échoue sur la
  condition transactionnelle sans effet partiel ;
- **expiration** : une commande `pending` non confirmée et une commande `confirmed` non exécutée
  deviennent inexécutables à l'issue de leurs fenêtres respectives ;
- **injection documentaire demandant une mutation** : le modèle peut au plus faire matérialiser une
  commande ; aucune confirmation n'est produite et aucun effet de bord ne survient
  (prolonge les preuves de `V2-ADR-002` sur le contenu non fiable) ;
- **tool sans classe déclarée** : traité comme `mutating` et refusé sans commande confirmée ;
- **annulation entre confirmation et exécution** (`V2-ADR-011`) : la commande expire sans effet, et
  une reprise ultérieure de la conversation ne l'exécute pas ;
- **résumé présenté à l'utilisateur** : rendu à partir de la commande stockée, et non modifiable par
  une sortie du modèle.

## Références

- `docs/adr/ADR-0006-idempotency-deadline-mcp-lifecycle.md` — idempotence, deadline et cycle de vie
  MCP en V1 ;
- `docs/adr/ADR-0007-durable-mutation-idempotency-confirmation.md` — idempotence durable et
  confirmation contrôlée en V1, dont cet ADR lève les limites déclarées ;
- Amazon DynamoDB — `TransactWriteItems`, écritures conditionnelles et `ClientRequestToken` ;
- Amazon DynamoDB — TTL et lectures fortement cohérentes ;
- Amazon Bedrock AgentCore Gateway — exposition et autorisation des tools MCP ;
- Amazon API Gateway — autorisation JWT et timeout d'intégration.
