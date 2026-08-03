# V2-LLD-010 — Frontend React

- **Version :** 0.1
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G2
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§5, §6.3, §6.5, §9)
- **Dépendances ADR :** V2-ADR-001, V2-ADR-002, V2-ADR-006, V2-ADR-008, V2-ADR-011, V2-ADR-014,
  V2-ADR-016, V2-ADR-020

> **Ce que ce LLD possède.** L'application navigateur : architecture React, transport du flux
> conversationnel côté client, geste de confirmation d'une action mutante, renouvellement du jeton,
> reprise après déconnexion et après opération ambiguë, uploads et suivi d'ingestion, rendu des
> citations, sécurité navigateur, accessibilité, observabilité client. `V2-LLD-005 §1.5` lui délègue
> nommément « l'interface de confirmation, le renouvellement de token côté navigateur et la sécurité
> navigateur » ; `V2-ADR-014` lui délègue « la forme de présentation » du résumé de commande et
> `V2-ADR-011` la part client du contrat d'événements SSE.
>
> **Ce qu'il ne possède pas.** Le transport côté serveur (`V2-LLD-001`), l'autorisation
> (`V2-LLD-005`), le contrat des tools (`V2-LLD-004`), les budgets d'invocation (`V2-LLD-003`), le
> magasin de commandes (`V2-LLD-006 §5.3`). Ce LLD **consomme** ces contrats et n'en redécide aucun.

---

## 1. Métadonnées

### 1.1 Exigences couvertes

| # | Exigence | Origine |
|---|---|---|
| E1 | Le flux conversationnel est perçu comme progressif, et le mode effectif est déclaré au client | `V2-ADR-011` |
| E2 | L'utilisateur peut interrompre une génération, et l'interruption arrête la consommation facturée | `V2-ADR-011` |
| E3 | Une action mutante n'est exécutée qu'après un geste de confirmation portant sur un résumé rendu par le serveur | `V2-ADR-014` |
| E4 | Le navigateur ne connaît jamais l'URL Runtime et n'est autorité sur aucune donnée d'identité | `V2-ADR-001`, `V2-ADR-006` |
| E5 | Le jeton se renouvelle sans rupture de session, et son expiration ne perd aucune opération en cours | `V2-ADR-020` |
| E6 | Une déconnexion ne produit ni perte silencieuse, ni doublon d'effet de bord | `V2-ADR-011`, `V2-ADR-014` |
| E7 | Les refus pour quota, pour autorisation et pour throttling sont trois situations distinctes pour l'utilisateur | `V2-ADR-016` |
| E8 | Les citations sont traçables jusqu'à leur source | `V2-ADR-003`, HLD §9 |
| E9 | L'interface est utilisable au clavier et avec un lecteur d'écran, y compris pendant le streaming | **ce LLD** — voir ci-dessous |

**E9 n'a pas d'origine dans le corpus, et il faut le dire.** Les huit premières exigences dérivent
d'un ADR ou de la Charte. L'accessibilité, elle, n'est mentionnée nulle part : ni dans la Charte —
dont le §6 « Exigences non fonctionnelles » couvre sécurité, disponibilité, performance/FinOps et
exploitabilité, sans un mot sur l'accessibilité — ni dans le HLD, ni dans aucun ADR. E9 est donc une
exigence que **ce LLD ajoute de son propre chef**, au titre de la qualité attendue d'une interface,
et non une contrainte héritée.

La distinction a une conséquence de gouvernance : une exigence sans document supérieur ne peut pas
être invoquée comme bloquante à une revue d'architecture. Si l'accessibilité doit avoir ce statut,
elle relève d'un amendement de la Charte §6, pas d'une décision de LLD. En l'état, les preuves P18 et
P19 (§16) sont marquées bloquantes **par décision de ce LLD**, ce qui engage sa réalisation sans
engager le corpus.

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-001 | Le navigateur parle à CloudFront puis API Gateway, jamais à Runtime ; l'identité, les deadlines et les champs internes sont construits côté serveur ; `actorId`, `tenantId`, `trustedIdentity`, `modelOverride`, `systemPrompt` et `toolName` sont refusés côté client |
| V2-ADR-002 | FastAPI est la frontière applicative ; le client n'orchestre rien, il rend un flux et émet des gestes |
| V2-ADR-006 | Le tenant et les rôles sont résolus côté serveur ; le client ne les transmet ni ne les sélectionne |
| V2-ADR-008 | `operationId` et `requestId` sont des Business Correlation IDs produits par FastAPI ; le client les affiche et les renvoie, il ne les fabrique pas pour le flux conversationnel |
| V2-ADR-011 | SSE, mode déclaré par l'événement `meta`, jeu d'événements minimal, annulation par endpoint dédié, reprise par `operationId` sans rejeu des fragments |
| V2-ADR-014 | Séquence en quatre temps ; **le résumé présenté est rendu par le serveur depuis la commande stockée, jamais rédigé par le modèle** ; seule la référence circule |
| V2-ADR-016 | Le quota par identité produit un refus intelligible, distinct de l'autorisation et du throttling ; le nombre de commandes `pending` par identité est borné |
| V2-ADR-020 | FastAPI vérifie elle-même la signature du jeton et ne lit aucun en-tête de claims ; l'en-tête `Authorization` est le transport de l'identité sur le segment passerelle → FastAPI, et jamais au-delà |

### 1.3 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-003, V2-ADR-004, V2-ADR-013, V2-ADR-017, V2-ADR-018, V2-ADR-019 | RAG, ingestion, embeddings, classification et évaluation : le client en rend les résultats (citations, statut d'ingestion, niveau de classification) mais n'en décide aucun mécanisme |
| V2-ADR-005, V2-ADR-012 | Framework agentique et fallback modèle : invisibles du client, à l'exception du drapeau `degraded` qu'il affiche (§11.4) |
| V2-ADR-007, V2-ADR-009, V2-ADR-010 | Plateforme, CI/CD et sauvegarde : le build et le déploiement du bundle relèvent de `V2-LLD-008`, le bucket qui le porte de `V2-LLD-006 §7.3` |
| V2-ADR-015 | Effacement : le client en porte le point d'entrée, qui est une action mutante ordinaire au sens de `V2-ADR-014` (§7.8) — aucune mécanique propre |

### 1.4 Périmètre et exclusions

**Dans le périmètre.** L'application `frontend/`, son bundle, sa configuration d'exécution, ses
contrats de consommation d'API, ses tests.

**Hors périmètre.** Le bucket qui porte le bundle (`V2-LLD-006 §7.3`) ; le contenu des règles WAF
(`V2-LLD-005`) ; le pipeline de build et de déploiement (`V2-LLD-008`) ; toute interface
d'administration au-delà de la gestion documentaire d'un utilisateur — les écrans `platform_admin`
sont V3.

> **Écart mineur relevé au passage.** La **distribution CloudFront qui sert le frontend** et sa
> politique de cache n'ont pas de propriétaire nommé. `V2-LLD-001 §1.4` exclut explicitement le
> frontend de son périmètre, et son §7 ne décrit CloudFront que comme frontal de l'API. `V2-LLD-006
> §7.3` porte le bucket, pas la distribution. Ce LLD ne se l'attribue pas — il n'a pas la compétence
> plateforme — mais le §17.1 en dépend pour la règle de cache de l'`index.html` et du fichier de
> configuration d'exécution (§15.1), et le §12.2 pour l'en-tête de CSP. Le propriétaire naturel est
> `V2-LLD-001`, qui devrait lever l'exclusion pour cette seule ressource.

### 1.5 Ce dont ce LLD hérite de la V1

L'application V1 (`frontend/`) est **conservée et étendue**, non réécrite. Sa pile — React 19,
TypeScript, Vite, Tailwind, `amazon-cognito-identity-js`, `react-markdown` — reste celle de la V2
(§2.1). Trois de ses mécanismes sont repris avec leur intention et redressés dans leur réalisation :

| Mécanisme V1 | Ce qui est conservé | Ce qui change en V2 |
|---|---|---|
| Carte `fingerprint → operationId` en `sessionStorage` (`ChatContainer.tsx`) | l'intention : ne jamais réémettre une mutation dont l'issue est inconnue | l'`operationId` vient du serveur par l'événement `meta`, plus d'une empreinte calculée par le client (§10) |
| Confirmation par formule contrôlée (« Je confirme la création… ») | l'intention : un geste utilisateur explicite avant tout effet de bord | remplacée par le geste sur commande de `V2-ADR-014` ; les deux coexistent pendant la bascule (§7.7) |
| Jeton d'accès porté en `Authorization` par `fetch` | le transport | le stockage du jeton et son renouvellement sont repris (§4) |

### 1.6 Règle de rédaction

Ce LLD ne réénonce aucune valeur appartenant à un autre document. Lorsqu'une durée, un seuil ou un
code d'erreur est cité, il l'est **par référence** au document qui le décide. Les seules valeurs
fixées ici concernent le comportement du navigateur et rien d'autre.

### 1.7 Écarts de corpus relevés par ce LLD

Trois écarts sont apparus à la rédaction.

> **État.** L'écart 1 est **corrigé dans le même lot** que ce LLD (`V2-ADR-011`, trois passages).
> L'écart 2 attend une correction dans `V2-LLD-001`. L'écart 3 est tranché ici et ne demande de
> correction nulle part ailleurs.

#### Écart 1 — `V2-ADR-011` prête au protocole SSE des propriétés de l'API `EventSource` (bloquant, corrigé)

`V2-ADR-011` §Contrat d'événements SSE écrivait :

> « **Reprise après déconnexion.** SSE reconnecte automatiquement. En V2, une reconnexion **ne
> rejoue pas** les fragments déjà émis : elle se rattache à l'opération par `operationId` et reçoit
> l'état courant ou le résultat final persisté. »

La seconde phrase est une décision, et elle est reprise telle quelle (§5.5). **La première est une
propriété de l'API `EventSource`, et `EventSource` n'est pas utilisable ici.**

`EventSource` n'accepte aucun en-tête de requête personnalisé. Or `V2-ADR-020` fait de l'en-tête
`Authorization` le transport de l'identité sur le segment passerelle → FastAPI. Le seul moyen de
présenter un jeton à `EventSource` est donc de le placer dans l'URL — exactement ce que
`V2-LLD-005 §2.2` a refusé en interdisant le flux `implicit`, au motif qu'il « expose le token dans
l'URL, donc dans l'historique, le `Referer` et les journaux d'accès ». Le motif ne dépend pas du flux
OAuth : il vaut identiquement pour une URL de flux SSE, avec les journaux d'accès CloudFront et API
Gateway cette fois. Les trois issues sont :

| Voie | Verdict |
|---|---|
| Jeton en paramètre de requête | **refusée** — reproduit l'exposition que `V2-LLD-005 §2.2` refuse |
| Cookie de session | **refusée en V2** — impose un endpoint d'échange et une défense CSRF que ni `V2-ADR-001` ni `V2-ADR-020` n'ont décidés |
| `fetch` + `ReadableStream` + analyseur SSE | **retenue** (§5.2) |

La conséquence est que **la reconnexion automatique disparaît et doit être réimplémentée** (§5.5).
Ce n'est pas une régression : le comportement de `EventSource` — reconnexion silencieuse avec
`Last-Event-ID` — aurait de toute façon dû être encadré, puisque `V2-ADR-011` refuse le rejeu des
fragments. Mais le corpus le présente comme acquis, et il ne l'est pas.

**Le diagramme de la décision portait la même erreur.** Le §Décision — transport de `V2-ADR-011`
commençait par « `Browser (EventSource)` », c'est-à-dire qu'il nommait l'API navigateur dans le
chemin retenu — alors que cet ADR décide le transport *réseau* et non le client qui le consomme. Ce
n'est pas une redite de l'écart : c'est le même présupposé, à un endroit plus visible, et il aurait
survécu à une correction du seul paragraphe de reprise.

**Correction — appliquée dans le même lot que ce LLD.** `V2-ADR-011` porte désormais :

| Passage | Avant | Après |
|---|---|---|
| §Décision — transport | `Browser (EventSource)` | `Browser (client SSE — l'API navigateur retenue relève de V2-LLD-010)` |
| §Contrat d'événements SSE | « SSE reconnecte automatiquement » | la phrase est retirée ; la stratégie de reconnexion est renvoyée à ce LLD, avec le motif |
| §Choix du mécanisme d'annulation | « `EventSource` ne peut rien envoyer au serveur » | formulation neutre : le flux ne porte aucun canal client → serveur, quelle que soit l'API |

L'ADR ne préjuge plus du client. La décision de transport réseau — REST API en mode `STREAM` — est
inchangée : elle n'a jamais dépendu du choix d'API navigateur.

#### Écart 2 — le jeu d'événements SSE n'a pas d'événement de commande

`V2-ADR-011` fixe sept événements : `meta`, `delta`, `citation`, `done`, `cancelled`, `error`,
`: ping`. Aucun ne porte le résumé de commande qu'exige `V2-ADR-014` §La séquence d'une action
mutante, dont le temps 2 est nommé « Présentation ».

Le temps 2 de la séquence de `V2-ADR-014` dit pourtant : « FastAPI lit la commande stockée et rend
le résumé, **transmis au client dans le flux SSE** ». Sans événement dédié, ce résumé ne peut
arriver que dans les `delta` — c'est-à-dire dans le même canal que le texte du modèle, indistinguable
de lui à la lecture (§7.2 montre pourquoi c'est disqualifiant).

Ce LLD ajoute l'événement `command` (§5.4), ce qui relève de son autorité : `V2-ADR-011` qualifie
son jeu de « minimal » et délègue « le contrat détaillé » à `V2-LLD-001` et à ce LLD. L'écart n'est
donc pas une contradiction, mais une lacune qu'il faut nommer pour que `V2-LLD-001` déclare le même
événement.

**Correction attendue dans `V2-LLD-001` :** déclarer `command` au contrat SSE côté transport.

#### Écart 3 — le stockage du jeton n'est arbitré nulle part

`V2-LLD-005 §2.2` décide le type de client Cognito, ses flux et ses durées de vie, et renvoie le
renouvellement à ce LLD. Aucun document ne dit **où le jeton réside dans le navigateur**. La V1
utilise le comportement par défaut d'`amazon-cognito-identity-js`, qui est `localStorage`.

Ce n'est pas un détail d'implémentation : `localStorage` est lisible par tout script de l'origine et
survit à la fermeture de l'onglet ; c'est la surface qu'une faille XSS transforme en vol de session
de trente jours (durée du jeton de rafraîchissement, `V2-LLD-005 §2.3`). Ce LLD tranche en §4.2,
parce que la question est de sa compétence — mais elle aurait dû être posée par le corpus, et non
héritée d'un défaut de bibliothèque.

**Correction attendue :** aucune dans un autre document. L'écart est signalé pour mémoire, la
décision étant prise ici.

---

## 2. Architecture de l'application

### 2.1 Pile technique — reconduite, et pourquoi

| Choix | Valeur | Motif |
|---|---|---|
| Framework | React 19 | continuité V1 ; aucun besoin V2 n'appelle un changement |
| Langage | TypeScript strict | les contrats d'API sont typés et vérifiés au build (§15.3) |
| Build | Vite | continuité V1 ; produit un bundle statique, seul artefact que ce LLD livre |
| Styles | Tailwind | continuité V1 |
| Auth | `amazon-cognito-identity-js` | continuité V1, avec un `Storage` personnalisé (§4.2) |
| Markdown | `react-markdown` | continuité V1, **sans** `rehype-raw` (§12.3) |
| Routage | à introduire | la V1 est mono-écran ; la V2 ajoute la gestion documentaire |

**Aucun état global partagé au-delà des contextes React existants.** La V1 porte `AuthContext` et
`ChatContext` ; la V2 ajoute `DocumentContext` et `OperationContext` (§2.3). Une bibliothèque de
gestion d'état externe n'est pas introduite : le nombre d'états réellement partagés ne le justifie
pas, et chaque dépendance supplémentaire élargit la surface décrite au §12.4.

### 2.2 Structure cible

```text
frontend/src/
  components/
    Auth/            Login, Register            (V1, conservé)
    Chat/            ChatContainer, ChatMessages, Message, ChatInput
                     CommandCard                (V2 — geste de confirmation, §7)
                     CitationList               (V2 — §9)
                     StreamStatus               (V2 — mode, annulation, §5.6)
    Documents/       UploadZone, DocumentList, IngestionStatus   (V2 — §8)
    Layout/          AppLayout
  contexts/          AuthContext, ChatContext
                     DocumentContext, OperationContext           (V2)
  services/
    authService      session, renouvellement, stockage           (§4)
    streamService    fetch streaming + analyseur SSE             (§5.2)
    commandService   confirmation                                (§7)
    documentService  upload, suivi                               (§8)
  lib/
    sseParser        analyseur de flux d'événements              (§5.3)
    resume           reprise des opérations ambiguës             (§10)
  types/             contrats d'API, générés ou vérifiés (§15.3)
```

### 2.3 Les deux contextes ajoutés

**`OperationContext`** porte l'état d'une invocation conversationnelle : `operationId`, mode de
streaming déclaré, état (`streaming`, `awaiting_confirmation`, `done`, `cancelled`, `error`),
compteurs reçus, commande en attente le cas échéant. Il existe parce que trois composants distincts
en dépendent — le flux, la carte de commande et le bouton d'annulation — et qu'aucun n'est parent
des deux autres.

**`DocumentContext`** porte la liste des documents de l'utilisateur et l'état d'ingestion de chacun.
Il est séparé du précédent parce que son cycle de vie ne suit pas celui d'une conversation : un
document reste en cours d'ingestion après la fin du tour qui l'a déclenchée (§8.4).

---

## 3. La frontière de confiance vue du navigateur

### 3.1 Le principe

`V2-ADR-001` et `V2-ADR-006` posent que l'identité, l'autorisation et la configuration d'exécution
sont construites côté serveur. Vu du client, cela se traduit par une règle unique et vérifiable :

> **Le navigateur n'est autorité sur rien. Il rend ce que le serveur lui envoie, et transmet des
> gestes. Toute donnée qu'il produirait et qui influencerait une décision serveur est un défaut.**

### 3.2 Ce que le client n'envoie jamais

| Champ | Pourquoi le client ne peut pas le produire | Refus attendu |
|---|---|---|
| `actorId`, `tenantId`, `subjectId` | résolus côté serveur depuis le jeton (`V2-ADR-006`) | 400, code dédié (`V2-LLD-005 §4.1`) |
| `roles`, `scopes`, `trustedIdentity` | l'autorisation est calculée, pas déclarée | 400 |
| `modelOverride`, `systemPrompt` | la configuration de génération appartient à `V2-LLD-003` | 400 |
| `toolName` | la sélection d'outil appartient au modèle sous contrôle Gateway (`V2-LLD-004`) | 400 |
| `classification` sur un chemin qui ne la modifie pas | `V2-ADR-017` | 400 |
| Toute clé de partition | `V2-ADR-006` | 400 |
| Contenu ou paramètre d'une commande à la confirmation | `V2-ADR-014` ; le corps est **vide** (`V2-LLD-005 §4.6`) | 400 |

**Le refus est un 400, pas un 403, et cette distinction est portée jusqu'à l'interface.** Un champ
interdit est une erreur de contrat du client, pas un refus d'autorisation : les confondre à
l'affichage inviterait l'utilisateur à croire qu'il lui manque un droit, et masquerait un défaut
d'implémentation derrière un message de sécurité plausible.

### 3.3 Ce que le client produit légitimement

| Donnée | Nature | Contrainte |
|---|---|---|
| Texte du message | contenu utilisateur | borné en taille côté serveur (`V2-ADR-001`) ; le client applique la même borne pour ne pas soumettre un envoi voué au refus |
| Fichier à téléverser | contenu utilisateur | même règle (§8.2) |
| `commandId` à la confirmation | **référence reçue du serveur**, réémise telle quelle | jamais fabriquée, jamais dérivée (§7.4) |
| `operationId` à la reprise et à l'annulation | idem | jamais fabriquée (§10.2) |
| `creationOperationId` d'un upload | identifiant d'idempotence, généré client **ou** serveur (`V2-LLD-006 §5.2`) | seul identifiant que ce LLD autorise le client à générer, et seulement pour cet usage (§8.3) |

La dernière ligne est la seule exception, et elle mérite d'être dite explicitement plutôt que
laissée implicite : un upload n'a pas de commande (`V2-LLD-006 §5.1`), son idempotence repose sur le
ledger, et le ledger accepte une clé d'origine client parce qu'elle n'autorise rien — elle
dédoublonne. Une valeur fabriquée par un client malveillant ne lui donne aucun droit ; elle lui
permet au pire de faire échouer son propre second upload.

### 3.4 Ce que le client rend sans jamais l'interpréter

| Donnée | Règle |
|---|---|
| Résumé de commande | rendu tel que reçu, dans un composant dédié, jamais reconstruit ni reformulé (§7.2) |
| Citations | rendues depuis la charge utile structurée de l'événement `citation`, jamais extraites du texte (§9.2) |
| Codes d'erreur | traduits par une table close côté client ; un code inconnu affiche un message générique, jamais le code brut (§11.2) |
| Drapeau `degraded` | affiché, jamais masqué (§11.4) |

---

## 4. Identité côté navigateur

### 4.1 Ce que le client fait de l'authentification

`V2-LLD-005 §2.2` décide le client Cognito : pas de secret, PKCE S256, `implicit` interdit, SRP
activé, rafraîchissement activé. Ce LLD en dérive le comportement de l'application.

**V2 conserve l'authentification SRP par le SDK**, comme la V1, et n'introduit pas de redirection
vers l'interface hébergée Cognito. Le flux `code` + PKCE reste configuré et disponible : il est la
voie d'une éventuelle fédération d'identité, qui n'est pas un besoin V2. Ce choix est reconduit, pas
redécidé — le noter évite qu'une lecture de `V2-LLD-005 §2.2` conclue à tort qu'une interface hébergée
est attendue.

Le jeton présenté à l'API est le **jeton d'accès**, jamais le jeton d'identité — `V2-ADR-020` en fait
la règle et `V2-LLD-005` la reprend comme un écart corrigé. Le jeton d'identité reste décodé côté
client pour l'affichage du profil, et pour rien d'autre.

### 4.2 Où le jeton réside — la décision de l'écart 3

`amazon-cognito-identity-js` accepte un objet `Storage` personnalisé à la construction du pool. Ce
point d'extension est le mécanisme de la décision.

| Jeton | Emplacement | Motif |
|---|---|---|
| **Accès** | **mémoire du module uniquement** | c'est le jeton qui autorise ; il ne survit ni au rechargement, ni à la fermeture de l'onglet, et aucun script ne le lit par une API de stockage |
| **Rafraîchissement** | **`sessionStorage`** | il doit survivre à un rechargement de page, sans quoi tout `F5` déconnecte ; `sessionStorage` borne sa vie à l'onglet |
| **Identité** | `sessionStorage` | affichage seul |

**Pourquoi pas `localStorage`.** Il survit à la fermeture du navigateur et est partagé par tous les
onglets de l'origine. Avec un jeton de rafraîchissement de trente jours (`V2-LLD-005 §2.3`), une
faille XSS y prélève une session d'un mois sur une machine partagée. `sessionStorage` ne supprime pas
le risque XSS — il en borne le produit à la durée d'un onglet.

**Pourquoi pas un cookie `httpOnly`.** C'est la seule option qui soustrait réellement le jeton au
script, et c'est pour cela qu'elle est nommée ici plutôt que passée sous silence. Elle exige un
endpoint d'échange côté FastAPI, une défense CSRF sur toutes les routes mutantes, et une décision sur
le domaine du cookie face à CloudFront. Ni `V2-ADR-001` ni `V2-ADR-020` ne les ont tranchées : les
introduire depuis un LLD de frontend serait décider à leur place. **C'est la trajectoire V3
nommée en §18**, pas un renoncement.

**Ce que cette décision suppose du reste.** Le jeton d'accès en mémoire ne vaut que si aucun script
tiers ne s'exécute dans l'origine — c'est l'objet de la CSP du §12.2 — et que si le rendu markdown
n'ouvre pas d'injection — §12.3. Les trois décisions se tiennent ; prises isolément, chacune est
insuffisante.

### 4.3 Renouvellement

| Déclencheur | Action |
|---|---|
| Jeton d'accès expirant dans moins d'une marge configurable | renouvellement silencieux avant l'appel |
| Appel refusé en 401 | un seul renouvellement, puis réémission de l'appel ; un second 401 déconnecte |
| Jeton de rafraîchissement invalide ou révoqué | déconnexion immédiate et retour à l'écran de connexion, sans réessai |

**Le renouvellement est déclenché par l'échéance, pas par l'échec.** Attendre le 401 signifie qu'un
appel sur deux échoue au voisinage de l'expiration, et surtout qu'un appel **non rejouable** peut
échouer — la confirmation d'une commande en est un (§7.5). La marge est un paramètre (§15.2).

**Un seul renouvellement par appel, jamais de boucle.** Deux 401 consécutifs signifient que le
problème n'est pas l'expiration ; réessayer indéfiniment produirait une boucle d'appels sur une
session morte, que le quota par identité de `V2-ADR-016` finirait par compter contre l'utilisateur.

### 4.4 Expiration pendant un flux en cours

C'est le cas que l'exigence E5 vise, et il se traite en distinguant deux choses que l'on confond
facilement.

**La connexion de streaming n'est pas réauthentifiée en cours de route.** FastAPI a vérifié le jeton
à l'établissement ; le flux qui suit appartient à une opération déjà autorisée, bornée par sa
`deadline` (`V2-LLD-003`). Un jeton qui expire pendant la diffusion n'interrompt pas le flux et ne
doit pas le faire : l'autorisation portait sur le démarrage de l'opération.

**Les appels émis pendant ce flux, eux, sont réauthentifiés.** L'annulation (§6) et la confirmation
(§7) sont des requêtes distinctes, avec leur propre vérification. Le client renouvelle donc son jeton
**avant** de les émettre, selon la règle du §4.3, et non au moment où le flux a commencé.

```text
t0   POST /messages          jeton vérifié ─────────► flux SSE ouvert
                                                       │
t0+n                                                   │  expiration du jeton d'accès
                                                       │  le flux continue — l'opération est autorisée
                                                       │
t0+m  geste de confirmation                            │
      renouvellement d'abord (§4.3), puis
      POST /commands/{id}/confirm   jeton vérifié ──────┘
```

---

## 5. Streaming conversationnel

### 5.1 Ce que le client attend du serveur

`V2-ADR-011` décide REST API en mode `STREAM` et `V2-LLD-001 §7.0` l'a réalisé. Le client n'a aucune
prise sur ce chemin ; il en constate le résultat. Deux constats lui sont demandés :

- **le mode déclaré**, porté par l'événement `meta` — `native` ou `emulated` ;
- **la progressivité observée**, mesurée par le time-to-first-token côté navigateur (§14.2).

Les deux sont nécessaires, et le second n'est pas redondant. `V2-ADR-011` a montré qu'un chemin peut
déclarer diffuser et tamponner en réalité — c'était précisément le défaut de la rédaction antérieure
du corpus. Un mode `native` déclaré avec un premier fragment reçu à la fin de la réponse est une
**dégradation silencieuse**, et le client est le seul point d'où elle est observable.

### 5.2 Le transport — `fetch` et non `EventSource`

C'est la conséquence de l'écart 1 (§1.7). Le client ouvre le flux par `fetch` en `POST`, avec
l'en-tête `Authorization`, et lit `response.body` comme un `ReadableStream`.

```text
POST /api/v1/conversations/{id}/messages
  Authorization: Bearer <jeton d'accès>
  Accept: text/event-stream
      │
      ▼
  response.body : ReadableStream
      │  décodage UTF-8 incrémental
      ▼
  analyseur SSE (§5.3) ──► événements typés ──► OperationContext
```

Trois propriétés de ce choix méritent d'être notées, parce qu'elles sont ce que `EventSource` aurait
fourni gratuitement et qu'il faut donc écrire.

| Propriété | `EventSource` | Ce que ce LLD décide |
|---|---|---|
| En-têtes personnalisés | impossibles | `fetch` les porte — c'est le motif du choix |
| Méthode | `GET` seulement | `POST` — le message n'a pas à tenir dans une URL |
| Reconnexion | automatique | réimplémentée et **encadrée** (§5.5) |
| Découpage des événements | fait par le navigateur | analyseur explicite (§5.3) |
| `AbortController` | non | oui — le lien avec l'annulation (§6.2) |

### 5.3 L'analyseur

Le format SSE est simple mais l'écrire à la main expose à deux erreurs classiques, que ce LLD nomme
pour qu'elles soient couvertes par un test et non par la vigilance.

**Un fragment réseau ne coïncide pas avec un événement.** Un `chunk` peut contenir un demi-événement,
trois événements, ou couper une séquence UTF-8 multi-octets en deux. L'analyseur maintient donc un
tampon de texte, découpe sur `\n\n`, et le décodeur est incrémental (`TextDecoder` avec
`{ stream: true }`). Un décodage par fragment produirait des caractères de remplacement au milieu
d'un mot accentué — défaut visible, rare, et impossible à reproduire à la demande sans test dédié.

**Un événement inconnu ne doit pas interrompre le flux.** Le jeu d'événements est amené à s'étendre
(§5.4 en ajoute un). Un client qui échoue sur un `event:` qu'il ne connaît pas rendrait toute
extension serveur incompatible. La règle est donc : **ignorer et journaliser**, jamais rompre.

### 5.4 Contrat d'événements consommé

Les sept événements de `V2-ADR-011`, plus `command` que ce LLD ajoute (écart 2, §1.7).

| Événement | Effet client |
|---|---|
| `meta` | enregistre `operationId` et le mode ; démarre la mesure de time-to-first-token |
| `delta` | ajoute le fragment au message en cours de rendu |
| `citation` | ajoute une citation à la liste structurée (§9) |
| `command` | **ouvre la carte de confirmation** (§7.2) — ne touche pas au texte du message |
| `done` | fige le message, affiche les compteurs et le drapeau `degraded` |
| `cancelled` | fige le message, affiche la cause et les compteurs consommés (§6.3) |
| `error` | fige le message, affiche l'erreur traduite (§11.2) |
| `: ping` | réarme le détecteur d'inactivité (§5.5), aucun effet visible |

**`done`, `cancelled` et `error` sont trois terminaisons distinctes et le client ne les fusionne
pas.** `V2-LLD-003 §3.2` le dit pour le serveur — « une annulation n'est pas une erreur » — et la
raison vaut identiquement à l'écran : présenter une interruption voulue comme une panne apprend à
l'utilisateur à se méfier d'un geste qui a fonctionné.

### 5.5 Reconnexion et fin anormale

Sans `EventSource`, trois situations doivent être distinguées, là où le navigateur en confondait
deux.

| Situation | Détection | Réponse |
|---|---|---|
| Flux terminé normalement | événement terminal reçu, puis fin de flux | rien |
| Flux coupé **après** un événement terminal | fin de flux sans octets supplémentaires | rien — l'opération est close |
| Flux coupé **sans** événement terminal | fin de `ReadableStream`, ou absence de `: ping` au-delà de la borne d'inactivité | **rattachement**, jamais réémission (§10) |

Le rattachement suit `V2-ADR-011` : il se fait par `operationId` sur la route de flux dédiée, et il
**ne rejoue pas** les fragments déjà reçus — il reçoit l'état courant ou le résultat final persisté.
Le texte déjà affiché est conservé ; s'il diverge du résultat final reçu, c'est le résultat final qui
fait foi et remplace l'affichage.

**La borne d'inactivité est dérivée du keep-alive, pas choisie indépendamment.** `V2-LLD-001 §7.3`
fixe l'intervalle de `: ping` et l'idle timeout de l'ALB. Le client attend un multiple de cet
intervalle avant de conclure à une coupure ; une valeur inférieure produirait des rattachements sur
un flux vivant, une valeur trop grande laisserait l'utilisateur devant une interface figée. C'est un
paramètre (§15.2), pas une constante.

**Le nombre de rattachements est borné.** Au-delà, l'interface bascule sur l'état « issue inconnue »
du §10.3 plutôt que de boucler.

### 5.6 Ce que l'utilisateur voit du transport

| État | Rendu |
|---|---|
| Mode `emulated` déclaré | mention discrète et permanente, pas une alerte — c'est un repli assumé (`V2-ADR-011`), pas un incident |
| Mode `native` mais premier fragment tardif | aucun rendu spécifique ; l'écart est **mesuré et remonté** (§14.2), pas affiché |
| Rattachement en cours | indicateur explicite, distinct du chargement initial |
| Rattachements épuisés | état « issue inconnue » (§10.3) |

La deuxième ligne est un choix. Afficher « le streaming ne fonctionne pas comme annoncé » n'aide
aucun utilisateur et n'aide aucun exploitant ; la métrique, elle, déclenche l'alerte prévue par
`V2-ADR-008`.

---

## 6. Annulation

### 6.1 Ce que l'annulation est, et n'est pas

`V2-ADR-011` a rendu l'annulation « une capacité de premier ordre, avec une route, une autorisation,
un registre partagé et un état terminal — elle n'est pas un effet de bord de la fermeture du
navigateur ». Côté client, cela impose une règle simple et une conséquence qui l'est moins.

**La règle : annuler, c'est appeler `POST /api/v1/operations/{operationId}/cancel`.** Fermer l'onglet
ou abandonner le `fetch` n'annule rien de garanti — c'est le « signal complémentaire de meilleur
effort » de l'ADR, qui économise du calcul quand il est détecté et ne garantit rien quand il ne l'est
pas.

**La conséquence : l'interface n'affiche pas « annulé » avant l'événement `cancelled`.** Abandonner
le flux localement puis afficher l'annulation donnerait à l'utilisateur la certitude que la
consommation s'est arrêtée, alors que l'exigence de `V2-ADR-011` est précisément que l'interruption
« arrête la consommation facturée, pas seulement l'affichage ». L'état intermédiaire est
« annulation demandée », et il est distinct.

### 6.2 Séquence

```text
geste utilisateur
   │
   ├─► renouvellement du jeton si nécessaire (§4.3)
   ├─► POST /operations/{operationId}/cancel
   │      202 ─► état « annulation demandée », bouton désactivé
   │      403 ─► l'opération n'est pas la vôtre (§11.2)
   │      404 ─► opération inconnue ou déjà close ─► rattachement (§5.5)
   │
   └─► le flux SSE reste ouvert et attendu
          │
          └─► événement `cancelled` ─► état terminal, cause et compteurs affichés
```

L'`AbortController` du `fetch` n'est utilisé **qu'après** réception de l'événement terminal, ou au
démontage du composant. L'utiliser au moment du geste couperait le canal par lequel l'annulation doit
être confirmée.

### 6.3 Rendu de la terminaison

L'événement `cancelled` porte une cause (`client`, `deadline`, `operator`) et les compteurs
réellement consommés. Les trois causes ne se présentent pas de la même façon :

| Cause | Rendu |
|---|---|
| `client` | « interrompu à votre demande », compteurs affichés |
| `deadline` | « interrompu : durée maximale atteinte » — ce n'est pas un geste de l'utilisateur, le présenter comme tel serait faux |
| `operator` | « interrompu par l'exploitant » |

**Les compteurs sont affichés dans les trois cas.** `V2-ADR-011` l'exige — « pour que le coût engagé
reste visible et non silencieux ». Une annulation réduit le coût, elle ne l'annule pas, et
l'interface ne doit pas suggérer l'inverse.

### 6.4 Ce qui n'est pas annulable

`V2-ADR-011`, tel que corrigé par `V2-ADR-014`, réduit la fenêtre non annulable à **la transaction
d'exécution** d'un tool mutant. Cette fenêtre est de l'ordre d'un aller-retour de base de données :
elle n'est pas observable à l'écran et n'appelle aucun rendu particulier.

Ce qui doit en revanche être rendu, c'est le cas où l'annulation arrive après cette transaction : le
flux se termine par `cancelled`, mais l'effet de bord **a eu lieu**. Le client ne peut pas le déduire
de la cause ; il l'apprend de la relecture de l'état de la commande (§10.4). C'est le motif pour
lequel la carte de commande porte son propre état terminal, distinct de celui du flux.

---

## 7. Confirmation d'une action mutante

C'est la raison d'être principale de ce LLD. `V2-ADR-014` décide le mécanisme et lui délègue « la
forme de présentation », en fixant une seule contrainte, de nature architecturale :

> « **le résumé présenté à l'utilisateur est rendu par le serveur à partir de la commande stockée,
> jamais rédigé par le modèle.** Sans cette règle, le modèle pourrait décrire une action et en faire
> matérialiser une autre. »

### 7.1 Le temps 2 vu du client

Le client n'intervient qu'aux temps 2 et 3 de la séquence de `V2-ADR-014`. Les temps 1 et 4 se
déroulent entre le modèle, la Gateway MCP et les tools, sans qu'aucune information n'en transite par
le navigateur autrement que sous forme de résumé et de référence.

```text
1. Matérialisation      modèle ──► tool de proposition ──► commande [ pending ]
                                              (le client ne voit rien)
2. Présentation         FastAPI ──► événement SSE `command` ──► CommandCard
                                              ▲
                                              │  résumé rendu par le serveur
3. Confirmation         CommandCard ──► POST /commands/{commandId}/confirm (corps vide)
                                              │
4. Exécution            modèle ──► tool d'exécution ──► [ executed ] + effet de bord
                                              (le client l'apprend par le flux)
```

**Le client ne connaît que le résumé et le `commandId`.** Il ne reçoit ni le `payload` de la
commande, ni le nom du tool, ni la cible métier. Cette pauvreté est délibérée : elle est ce qui rend
impossible la reconstruction locale d'une action à partir de ce que le navigateur détient.

### 7.2 Pourquoi la carte est hors du flux markdown

C'est le point de conception le plus important de cette section, et il ne se réduit pas à une
préférence d'ergonomie.

`V2-ADR-014` interdit que le modèle rédige le résumé. Le serveur le rend. Mais **si ce résumé rendu
par le serveur est inséré dans le même canal que le texte du modèle — les événements `delta` — la
garantie est perdue en pratique**, pour une raison simple : le modèle peut produire du texte qui
imite un résumé de commande, y compris un bouton en markdown, y compris une phrase de confirmation.
L'utilisateur n'a alors aucun moyen de distinguer le rendu serveur d'une imitation, parce que les
deux arrivent par le même chemin et se rendent avec le même moteur.

La règle est donc structurelle, et non déclarative :

> **Le résumé de commande arrive par un événement SSE dédié (`command`), est porté par un état
> distinct du texte du message, et est rendu par un composant qui ne prend jamais de markdown en
> entrée. Aucun `delta` ne peut produire une carte de commande.**

| Ce que le modèle peut produire | Ce que cela donne |
|---|---|
| Du texte décrivant une action | du texte, dans le message — sans carte, sans bouton actif |
| Du markdown imitant un bouton | un élément inerte : le rendu markdown n'émet aucun lien actionnable vers l'API (§12.3) |
| Une chaîne ressemblant à un `commandId` | du texte ; le `commandId` utilisé par la carte vient de l'événement `command`, jamais du corps du message |

**La séparation des canaux est ce qui rend la contrainte de l'ADR vérifiable.** Elle se teste : un
flux ne contenant que des `delta`, quel qu'en soit le contenu, ne doit produire aucune carte
actionnable (preuve P4, §16).

### 7.3 Anatomie de la carte

| Élément | Source | Règle |
|---|---|---|
| Résumé de l'action | charge utile de `command` | rendu en **texte brut**, jamais en markdown (§12.3) |
| Échéance | charge utile de `command` | affichée en compte à rebours ; c'est la fenêtre `pending` de `V2-LLD-006 §5.3.2` |
| Bouton « Confirmer » | — | action primaire, désactivé dès le premier clic (§7.5) |
| Bouton « Refuser » | — | ferme la carte localement ; **n'appelle aucune API** (§7.6) |
| État | `OperationContext` | `pending`, `confirming`, `confirmed`, `expired`, `refused`, `error` |

**L'échéance est affichée parce qu'elle est réelle.** La commande expire (`V2-LLD-006 §5.3.4`), et
une carte laissée ouverte sans indication produirait un refus incompréhensible au moment du clic. Le
compte à rebours est une information, pas une pression : à l'expiration, la carte bascule en
`expired` avec un message expliquant qu'il faut redemander l'action.

### 7.4 Le geste

```text
POST /api/v1/commands/{commandId}/confirm
  Authorization: Bearer <jeton renouvelé si nécessaire, §4.3>
  (corps vide)
```

Le `commandId` transmis est **exactement celui reçu dans l'événement `command`**. Il n'est ni
recomposé, ni lu depuis le texte du message, ni conservé au-delà de la vie de la carte. Le corps est
vide : `V2-LLD-005 §4.6` en fait une règle d'autorisation, et le client n'a de toute façon rien à y
mettre puisqu'il ne détient pas le contenu de la commande.

### 7.5 Les issues, et celles qui n'en sont pas

| Issue | Cause | Rendu |
|---|---|---|
| `204` / succès | transition `pending` → `confirmed` | carte en `confirmed` ; l'exécution suit et son résultat arrive par le flux |
| Déjà `confirmed` | **double-clic de l'utilisateur** | traité comme un **succès**, pas comme une erreur (voir ci-dessous) |
| `COMMAND_EXPIRED` | fenêtre `pending` écoulée | carte en `expired` ; message invitant à redemander l'action |
| `COMMAND_FORBIDDEN` | identité ou tenant différents | message générique de refus — le client ne distingue pas « pas à vous » de « n'existe pas », `V2-LLD-004 §6.3` ayant délibérément confondu les deux |
| `COMMAND_NOT_FOUND` | référence inconnue ou purgée | même message que ci-dessus |
| Refus pour quota de commandes `pending` | `V2-ADR-016` | message distinct des trois précédents (§11.3) |
| Réseau / issue inconnue | — | état « issue inconnue » (§10.3) — **jamais de réessai automatique** |

**Le double-clic n'est pas une erreur, et le traiter comme telle serait un défaut.** L'utilisateur
qui clique deux fois a fait un geste, pas deux : la machine à états côté serveur refusera la seconde
transition, et c'est correct. Mais afficher un échec à quelqu'un dont l'action a réussi l'amènerait
à recommencer, c'est-à-dire à demander une nouvelle proposition pour une action déjà autorisée. La
carte est donc désactivée au premier clic, et un refus « la commande n'est plus `pending` alors
qu'elle est `confirmed` » est rendu comme un succès.

**Aucun réessai automatique sur issue inconnue.** C'est la transposition côté client de la règle de
`V2-LLD-004 §8.4` : la commande est le seul témoin fiable de ce qui a été appliqué. Un client qui
réémettrait la confirmation après un timeout ne créerait pas de second effet de bord — la machine à
états l'en empêche — mais il produirait un message d'erreur trompeur sur une opération réussie. La
réponse conforme est de **relire l'état**, pas de rejouer le geste (§10.3).

### 7.6 « Refuser » n'appelle rien, et c'est une décision

Le bouton de refus ferme la carte côté client sans émettre de requête. Trois raisons :

- **il n'existe pas d'endpoint de refus**, et `V2-ADR-014` n'en décide pas. Une commande non
  confirmée expire ; c'est le mécanisme prévu ;
- **ne rien confirmer produit exactement le résultat attendu** — aucun effet de bord — au plus tard
  à l'échéance de la fenêtre `pending` ;
- **inventer un endpoint depuis un LLD de frontend serait décider à la place de l'ADR.**

La limite de ce choix est nommée : la commande reste `pending` jusqu'à expiration et continue de
compter dans le quota de commandes `pending` de `V2-ADR-016`. Un utilisateur qui refuse plusieurs
propositions d'affilée peut atteindre ce quota. Un endpoint de refus explicite libérerait le quota
immédiatement ; c'est une évolution qui relève d'un amendement de `V2-ADR-014`, notée en §18.

### 7.7 Coexistence avec le contrôle V1 pendant la bascule

`V2-ADR-014` est explicite : « Tant que ces preuves ne sont pas produites, le contrôle
`confirmationVerified` de `ADR-0007` reste en vigueur. Il est insuffisant au sens de cet ADR, mais il
n'est pas nul. » `V2-LLD-004 §1.8` le reprend.

Côté client, cela signifie que **les deux mécanismes coexistent** pendant la transition, sans que
l'utilisateur ait à connaître lequel s'applique :

| Chemin | Rendu client |
|---|---|
| Tool V2 (`propose_*` / `execute_*`) | carte de commande (§7.3) |
| Tool V1 encore en place | formule contrôlée dans le message, comme en V1 |

L'interface ne demande jamais les deux pour une même action. Le retrait de la formule V1 est
conditionné par la preuve M1 de `V2-LLD-004 §15`, pas par une décision de frontend.

### 7.8 Effacement — une action mutante ordinaire

`V2-ADR-015` et `V2-LLD-006 §8.4` font de la demande d'effacement une action mutante matérialisée
puis confirmée. Côté client, **elle n'a aucune mécanique propre** : même événement `command`, même
carte, même geste, même endpoint.

Deux différences de présentation, et elles ne sont pas mécaniques :

- le résumé rendu par le serveur porte la **fenêtre résiduelle** (`erasureDurableAt`,
  `V2-LLD-006 §6.3`) — l'utilisateur est informé que l'effacement est immédiat en logique et borné en
  durabilité, ce que `V2-ADR-015` exige d'annoncer ;
- la carte n'a pas de compte à rebours plus court ni de double confirmation. Ajouter une friction
  spécifique donnerait à penser que le mécanisme est moins sûr pour cette action, alors qu'il est
  identique.

---

## 8. Documents — téléversement et suivi d'ingestion

### 8.1 Ce qui relève du client

Le client téléverse, suit l'état, et rend la classification. Il ne décide ni le chunking, ni
l'espace d'embedding, ni la classification par défaut — `V2-LLD-002` et `V2-ADR-017` les portent.

### 8.2 Bornes appliquées avant l'envoi

Le serveur borne la taille et le format (`V2-ADR-001`, `V2-LLD-002 §3`). Le client applique **les
mêmes bornes**, avant l'envoi, pour une raison qui n'est pas la sécurité : téléverser plusieurs
mégaoctets pour recevoir un refus consomme la bande passante de l'utilisateur et le quota de
`V2-ADR-016` sans rien produire.

**Cette vérification client n'est pas un contrôle.** Elle est un confort. Le contrôle est côté
serveur, et le client ne suppose jamais qu'il a filtré correctement — même règle qu'entre la Gateway
et la cible en `V2-LLD-004 §4.1`. Les bornes client sont donc **lues depuis la configuration**
(§15.2), pas codées en dur, pour qu'un durcissement serveur ne laisse pas un client plus permissif.

### 8.3 Idempotence de l'upload

Un upload n'a pas de commande (`V2-LLD-006 §5.1`) : son idempotence repose sur le ledger, par
`creationOperationId`. C'est la seule valeur que ce LLD autorise le client à générer (§3.3).

| Règle | Motif |
|---|---|
| Généré une fois par fichier sélectionné, avant le premier envoi | un identifiant régénéré à chaque tentative annulerait la déduplication |
| Conservé en `sessionStorage` tant que l'upload n'a pas abouti | un rechargement de page pendant l'envoi ne doit pas produire un doublon |
| Réémis tel quel à chaque tentative | c'est ce qui fait qu'une seconde tentative après timeout est déduplicable |
| Purgé au succès confirmé ou à l'abandon explicite | sinon la clé survit à son usage |

### 8.4 Suivi d'ingestion

Le cycle de vie du `status` appartient à `V2-LLD-006 §4.4`. Le client le rend, et **ne le déduit
jamais** :

| `status` | Rendu |
|---|---|
| `uploaded` | « reçu, en attente d'indexation » |
| `indexed` | disponible pour la conversation |
| `quarantined` | motif affiché ; l'utilisateur sait que le document ne sera pas interrogeable |
| `failed` | motif affiché, action de reprise proposée |
| `superseded` | version remplacée, non proposée par défaut |
| `deleted` | absent des listes ; le tombstone n'est pas une entrée visible |

**Le suivi se fait par interrogation périodique, pas par SSE.** L'ingestion se poursuit après la fin
du tour conversationnel qui l'a déclenchée (§2.3) ; l'attacher au flux imposerait de maintenir une
connexion ouverte pour un événement qui peut arriver plusieurs minutes plus tard, ce que
`V2-ADR-016` §sur les connexions maintenues invite précisément à éviter. La période d'interrogation
est un paramètre (§15.2) et s'espace après plusieurs cycles sans changement.

### 8.5 Classification

`V2-ADR-017` fixe le domaine fermé — `internal`, `confidential`, `restricted` — et le défaut
`confidential`. Le client :

- **affiche** le niveau de chaque document ;
- **propose** le changement de niveau, qui est une action mutante lorsqu'il assouplit
  (`V2-LLD-006 §4.3.2`) et passe donc par une carte de commande (§7) ;
- **n'invente aucune valeur par défaut** : un document sans classification affichée est un défaut de
  contrat serveur, pas une occasion d'afficher `internal`.

Un document `restricted` est signalé comme non interrogeable en conversation — il est hors data
source KB (`V2-ADR-017`) — pour que son absence des citations ne soit pas interprétée comme un défaut
de recherche.

---

## 9. Citations

### 9.1 Ce qu'une citation doit permettre

L'exigence E8 et le HLD §9 — « citations issues de sources autorisées » — demandent que la réponse
soit traçable jusqu'à ses sources. Une citation est donc un objet, pas une mention textuelle : elle
porte une référence de document, une version, et de quoi remonter à l'extrait.

### 9.2 Rendu depuis la charge utile, jamais depuis le texte

Les citations arrivent par l'événement `citation`, avec une charge utile structurée issue du
`retrievalContext`. Le client les accumule dans une liste, séparée du texte du message.

**Aucune citation n'est extraite du texte du modèle.** Si le modèle écrit « selon le document X », ce
n'est que du texte : cela ne produit ni entrée dans la liste, ni lien. La raison est la même qu'au
§7.2 — un canal qui mélange l'assertion du modèle et le fait établi par le serveur ne permet plus de
les distinguer, et c'est exactement ce que la traçabilité doit établir.

**Un `delta` référençant une citation absente de la liste n'est pas corrigé.** Le texte est affiché
tel quel ; la liste reste ce qu'elle est. Réécrire la réponse du modèle pour la faire coïncider avec
les citations produirait une réponse que personne n'a générée.

### 9.3 Rendu

| Élément | Règle |
|---|---|
| Liste | sous la réponse, dans l'ordre de réception, dédoublonnée par document et version |
| Renvoi vers le document | lien vers la fiche document, jamais une URL présignée conservée — celles-ci sont courtes et liées à une opération (`V2-ADR-006`) |
| Extrait | affiché s'il est fourni ; jamais reconstruit depuis le contenu local |
| Version | toujours affichée — deux versions d'un même document ne sont pas la même source |
| Absence de citation | mention explicite « réponse sans source documentaire », jamais un silence |

La dernière ligne est un choix : une réponse sans citation dans une interface qui en affiche
habituellement est indiscernable d'une réponse dont les citations se seraient perdues. Le dire évite
que l'utilisateur accorde à une réponse non sourcée le crédit d'une réponse sourcée.

---

## 10. Reprise des opérations dont l'issue est inconnue

### 10.1 Le problème, et pourquoi la V1 l'avait déjà rencontré

Un appel qui se termine sans réponse ne dit pas s'il a été traité. La V1 avait répondu par une carte
`fingerprint → operationId` en `sessionStorage` (`ChatContainer.tsx`), avec une empreinte SHA-256 du
couple session/message. L'intention était juste ; sa réalisation reposait sur une valeur calculée par
le client, ce que la V2 n'a plus besoin de faire.

### 10.2 Ce que la V2 conserve, et ce qu'elle change

| V1 | V2 |
|---|---|
| Empreinte calculée par le client | `operationId` **reçu du serveur** dans l'événement `meta` |
| Carte `fingerprint → operationId` | carte `operationId → état`, alimentée par le flux |
| Réémission du message en cas de doute | **rattachement** par `operationId`, jamais réémission (§5.5) |

Le changement n'est pas cosmétique. Une empreinte calculée par le client suppose que le client sache
ce qui rend deux envois équivalents — c'est une règle métier, et elle n'est pas de sa compétence. Le
`operationId` produit par FastAPI (`V2-ADR-008`) porte cette équivalence là où elle est décidée.

L'`operationId` est enregistré **dès l'événement `meta`**, c'est-à-dire avant tout `delta`. C'est ce
qui rend une coupure survenant au milieu de la réponse rattachable ; une coupure survenant avant
`meta` ne l'est pas, et relève du §10.3.

### 10.3 L'état « issue inconnue »

C'est l'état dans lequel le client se place lorsqu'il ne peut pas conclure : coupure avant `meta`,
rattachements épuisés (§5.5), ou confirmation dont la réponse n'est jamais arrivée (§7.5).

**Sa règle est de ne rien réémettre.**

| Ce que le client fait | Ce qu'il ne fait pas |
|---|---|
| Affiche que l'issue est indéterminée, sans prétendre à un succès ni à un échec | conclure à l'échec |
| Propose de **rafraîchir l'état** — relecture de l'opération ou de la commande | rejouer le message ou la confirmation |
| Conserve le texte déjà reçu, marqué comme incomplet | effacer ce qui a été affiché |

**Pourquoi ne pas rejouer.** Pour la conversation, un rejeu produirait un second tour facturé pour
une réponse peut-être déjà produite. Pour la confirmation, il produirait un message d'erreur sur une
opération réussie (§7.5). Dans les deux cas, la relecture d'état est disponible et suffit — c'est la
même règle que `V2-LLD-004 §8.4` applique côté serveur, et il serait incohérent que le client, moins
bien informé, soit plus agressif.

### 10.4 Ce que la relecture donne

| Objet relu | Réponse possible | Rendu |
|---|---|---|
| Opération | terminée avec résultat | le résultat remplace l'affichage incomplet |
| Opération | encore en cours | rattachement au flux (§5.5) |
| Opération | annulée ou en erreur | état terminal correspondant |
| Commande | `executed` | l'action a eu lieu — y compris si le flux s'est terminé par `cancelled` (§6.4) |
| Commande | `confirmed` | la confirmation a abouti, l'exécution reste attendue |
| Commande | `pending` | la confirmation n'a pas abouti ; le geste peut être refait |

La ligne `executed` est celle qui justifie l'existence de ce tableau : c'est le seul moyen par lequel
l'utilisateur apprend qu'une action a été appliquée alors que la conversation s'est interrompue.

---

## 11. Erreurs, refus et dégradations

### 11.1 Trois familles, jamais confondues

L'exigence E7 vient de `V2-ADR-016`, qui impose que « les refus pour quota, pour autorisation et pour
throttling Bedrock » soient trois séries distinctes dans les métriques. La raison vaut à l'écran :
ces trois situations appellent trois conduites différentes de la part de l'utilisateur.

| Famille | Ce qui s'est passé | Ce que l'utilisateur peut faire |
|---|---|---|
| **Autorisation** | l'action n'est pas permise à cette identité | rien — réessayer ne changera rien |
| **Quota d'identité** | la capacité allouée à cette identité est consommée | attendre ; l'interface indique la nature de la limite |
| **Throttling / dégradation** | la plateforme est sous contrainte | réessayer plus tard a un sens |
| **Contrat** (400) | le client a envoyé un champ interdit (§3.2) | rien — c'est un défaut applicatif, remonté (§14.3) |

Les fusionner en « une erreur est survenue » supprimerait l'information la plus utile de chacune.

### 11.2 Traduction des codes

Le client tient une **table close** de codes connus. Un code absent de la table produit un message
générique et **une trace** (§14.3) — jamais l'affichage du code brut, qui n'apprend rien à
l'utilisateur et expose une information de structure interne.

| Origine | Codes | Source du contrat |
|---|---|---|
| Invocation agentique | `budget_exceeded`, `deadline_exceeded`, `tool_denied`, `model_throttled`, `tool_unavailable`, `memory_unavailable` | `V2-LLD-003 §3.2` |
| Commande | `COMMAND_NOT_CONFIRMED`, `COMMAND_EXPIRED`, `COMMAND_NOT_FOUND`, `COMMAND_FORBIDDEN` | `V2-LLD-004 §6.3` |
| Quota | refus de quota d'identité, refus de quota de commandes `pending`, refus de quota de documents en ingestion | `V2-ADR-016` |
| Contrat | champ interdit | `V2-LLD-005 §4.1` |

**`COMMAND_FORBIDDEN` et `COMMAND_NOT_FOUND` reçoivent le même message.** `V2-LLD-004 §6.3` les a
délibérément rendus indistinguables côté serveur pour ne pas offrir d'oracle d'existence ; les
distinguer à l'affichage annulerait cette précaution.

### 11.3 Les trois refus de quota ne sont pas le même refus

`V2-ADR-016` borne trois choses distinctes, et les trois se rencontrent dans cette interface :

| Quota | Déclencheur | Message |
|---|---|---|
| Tokens par fenêtre | conversation | la capacité conversationnelle allouée est atteinte |
| Commandes `pending` | trop de propositions non confirmées | **indique la sortie** : confirmer ou laisser expirer les propositions en attente (§7.6) |
| Documents en ingestion | trop d'uploads en cours | attendre la fin des ingestions en cours |

La deuxième ligne est la seule où l'utilisateur détient la solution, et l'interface doit le dire —
sans quoi il fait face à un blocage dont la cause est à l'écran et dont il ignore le lien.

### 11.4 Dégradation n'est pas erreur

Le drapeau `degraded` de l'événement `done` signale que le retrieval, la mémoire ou un tool a été
dégradé sans que la réponse échoue (`V2-LLD-003`).

**Il est affiché, discrètement et systématiquement.** Le masquer donnerait à une réponse produite
sans contexte documentaire le même crédit qu'une réponse complète. Le transformer en erreur
supprimerait une réponse utilisable. C'est la même logique qu'au §9.3 sur l'absence de citation.

---

## 12. Sécurité navigateur

### 12.1 Ce que cette section couvre

`V2-LLD-005 §1.5` délègue « la sécurité navigateur » à ce LLD. Le contenu des règles WAF et les
contrôles serveur restent chez lui ; ce qui suit concerne l'origine, le document et le bundle.

### 12.2 CSP

La politique est servie par CloudFront en en-tête de réponse (`V2-LLD-001` porte le mécanisme
d'en-têtes, ce LLD porte la valeur).

| Directive | Valeur | Motif |
|---|---|---|
| `default-src` | `'none'` | tout est refusé par défaut, chaque capacité est ouverte explicitement |
| `script-src` | `'self'` | **aucun `unsafe-inline`, aucun `unsafe-eval`, aucun CDN** — c'est ce qui protège le jeton en mémoire (§4.2) |
| `style-src` | `'self'` | Tailwind produit une feuille statique ; aucun style en ligne n'est requis |
| `connect-src` | `'self'` + origine de l'API | le flux SSE et les appels d'API, rien d'autre |
| `img-src` | `'self'` `data:` | — |
| `font-src` | `'self'` | aucune police distante |
| `frame-ancestors` | `'none'` | anti-clickjacking ; plus fiable que `X-Frame-Options` |
| `form-action` | `'none'` | l'application n'émet aucune soumission de formulaire native |
| `base-uri` | `'none'` | empêche la réécriture de la base des URL relatives |
| `object-src` | `'none'` | — |

**`script-src 'self'` sans exception est la clef de voûte.** La décision de garder le jeton d'accès
en mémoire (§4.2) ne vaut que si aucun script étranger ne s'exécute dans l'origine. Une seule
tolérance — un `unsafe-inline` ajouté pour faire fonctionner une bibliothèque — la rend caduque sans
qu'aucun autre document ne le signale. C'est un point de vérification au plan (§16).

### 12.3 Markdown et XSS

`react-markdown` est utilisé pour rendre les réponses du modèle. C'est la principale surface
d'injection de l'application, parce que le contenu rendu est produit par un système que l'on ne
contrôle pas et qu'une injection indirecte peut orienter (`V2-LLD-005 §11.3`).

| Règle | Motif |
|---|---|
| **Aucun `rehype-raw`**, aucun HTML brut | c'est le mécanisme par lequel `react-markdown` deviendrait dangereux ; par défaut il ne l'est pas, et ce défaut est une décision à préserver |
| Aucun `dangerouslySetInnerHTML` dans l'application | interdit et vérifié par règle de lint (§15.3) |
| Protocoles de lien restreints à `https:` | un lien `javascript:` ou `data:` produit par le modèle est neutralisé |
| Liens externes en `rel="noopener noreferrer"`, ouverture contrôlée | — |
| **Le résumé de commande n'est jamais rendu en markdown** (§7.3) | il est affiché en texte brut : un résumé rendu par le serveur n'a aucun besoin de mise en forme, et le rendre en markdown rouvrirait la surface là où elle importe le plus |
| Les extraits de citation sont rendus en texte brut | même motif |

### 12.4 Dépendances

| Règle | Motif |
|---|---|
| Aucun script tiers chargé à l'exécution | conséquence directe de la CSP ; toute analytique ou télémétrie externe est exclue |
| `package-lock.json` versionné, installation reproductible | `V2-LLD-008` en fait un artefact de build |
| Analyse de composition et SBOM | portés par `V2-LLD-008`, cités ici pour traçabilité |
| Ajout de dépendance = décision | chaque paquet élargit la surface que §12.2 et §12.3 protègent |

### 12.5 Ce que le client ne journalise ni ne stocke

| Valeur | Règle |
|---|---|
| Jeton d'accès, jeton de rafraîchissement | jamais journalisés, jamais en `localStorage` (§4.2) |
| `commandId`, `operationId` | affichables pour le support, **jamais** journalisés en clair vers un service externe — il n'y a d'ailleurs aucun service externe (§12.4) |
| Contenu des messages | jamais persisté au-delà de la session courante côté client |
| Contenu documentaire | jamais conservé après envoi |

---

## 13. Accessibilité

### 13.1 Le cas particulier du streaming

C'est le point qui distingue cette interface d'une application ordinaire, et il est facile de le
manquer.

Une région `aria-live="polite"` dont le contenu change à chaque fragment fait annoncer par le lecteur
d'écran chaque fragment, ou provoque une file d'annonces que l'utilisateur ne peut plus interrompre.
Le résultat est une interface **moins** utilisable qu'une réponse non diffusée.

| Zone | Traitement |
|---|---|
| Texte en cours de diffusion | `aria-busy="true"`, **pas** de `aria-live` |
| Fin de réponse | la région passe `aria-busy="false"` et est annoncée **une fois**, complète |
| Statut du flux (mode, rattachement, annulation) | région `aria-live="polite"` distincte et courte |
| Erreur ou refus | `role="alert"` — interruption justifiée |
| Carte de commande | `role="dialog"` non modal, focus déplacé à l'ouverture, échéance annoncée |

**Le focus se déplace sur la carte de commande à son ouverture.** C'est un geste qui engage un effet
de bord : il ne doit pas être atteignable seulement après avoir parcouru toute la réponse au clavier.
À la fermeture, le focus revient à l'élément qui l'avait avant.

### 13.2 Le reste

| Exigence | Règle |
|---|---|
| Navigation clavier complète | tout geste — envoyer, annuler, confirmer, téléverser — est atteignable sans souris |
| Ordre de tabulation | suit l'ordre visuel ; aucun `tabindex` positif |
| Contraste | AA au minimum, y compris sur les états désactivés |
| Cibles de pointeur | taille minimale respectée sur les boutons d'action |
| Mouvement | le curseur de frappe et les animations respectent `prefers-reduced-motion` |
| Libellés | tout contrôle a un nom accessible ; aucune icône seule sans libellé |
| Langue | `lang` déclaré sur le document |

### 13.3 Ce qui est vérifié, et comment

L'accessibilité n'est pas déclarée : elle est testée (§16). Les deux points qui ne se testent pas
automatiquement — l'annonce du streaming et le parcours de confirmation au lecteur d'écran — font
l'objet d'une vérification manuelle documentée, parce qu'un audit automatique les déclarerait
conformes dans les deux cas.

---

## 14. Observabilité côté client

### 14.1 Ce que le client peut observer et que le serveur ne peut pas

`V2-ADR-008` attribue le tracing à OpenTelemetry et les Business Correlation IDs à FastAPI. Le client
n'introduit pas de collecteur : il n'y a aucun service externe (§12.4). Ce qu'il remonte passe par
l'API, et se limite à ce que le serveur ne peut pas mesurer lui-même.

### 14.2 Time-to-first-token observé

C'est la métrique dont §5.1 a établi la nécessité : le serveur peut déclarer diffuser, seul le
navigateur constate qu'il diffuse.

| Mesure | Définition |
|---|---|
| `ttft_client` | délai entre l'émission de la requête et le premier `delta` reçu |
| `total_client` | délai jusqu'à l'événement terminal |
| Mode déclaré | `native` ou `emulated`, tel que reçu dans `meta` |

Un mode `native` dont le `ttft_client` s'approche du `total_client` est le signe d'un tampon sur le
chemin. C'est exactement le défaut que `V2-ADR-011` a corrigé au niveau de la décision, et cette
mesure est ce qui l'empêche de revenir sans être vu. L'alerte associée relève de `V2-LLD-007`.

### 14.3 Ce qui est remonté

| Événement | Motif |
|---|---|
| `ttft_client`, `total_client`, mode déclaré | §14.2 |
| Code d'erreur inconnu de la table close (§11.2) | signale une divergence de contrat client/serveur |
| Refus 400 pour champ interdit (§3.2) | c'est un défaut applicatif, pas un incident utilisateur |
| Rattachement de flux, et échec de rattachement | mesure la stabilité réelle du chemin SSE |
| Confirmation aboutie / expirée / en issue inconnue | mesure l'usage réel du mécanisme de `V2-ADR-014` |

**Aucune donnée de contenu.** Les mesures portent des durées, des codes et des identifiants de
corrélation — jamais un message, un extrait, un nom de fichier. La règle de redaction de
`V2-ADR-008` s'applique au client comme au serveur.

---

## 15. Configuration et build

### 15.1 Ce qui est configuré à la construction, et ce qui l'est à l'exécution

Un bundle statique ne lit pas de variables d'environnement à l'exécution. Deux mécanismes coexistent
donc, et les confondre produit des déploiements dont la configuration est fausse sans être visible.

| Nature | Mécanisme | Exemple |
|---|---|---|
| Constant pour un environnement | injecté au build par Vite (`import.meta.env`) | origine de l'API, identifiants du pool Cognito |
| Susceptible de changer sans rebuild | **fichier de configuration servi**, lu au démarrage | bornes de taille d'upload, périodes d'interrogation, marges de renouvellement |

**La seconde ligne est une décision, pas une commodité.** Le §8.2 exige que les bornes client soient
alignées sur les bornes serveur ; si elles sont figées dans le bundle, un durcissement serveur laisse
un client plus permissif jusqu'au prochain déploiement de frontend. Le fichier est servi avec les
mêmes en-têtes de cache que l'`index.html`, pas ceux des artefacts versionnés.

### 15.2 Paramètres

| Paramètre | Portée | Défini par |
|---|---|---|
| Origine de l'API | build | `V2-LLD-001` |
| Pool et client Cognito | build | `V2-LLD-005 §2.2` |
| Marge de renouvellement du jeton | exécution | ce LLD (§4.3) |
| Borne d'inactivité du flux | exécution | dérivée du keep-alive de `V2-LLD-001 §7.3` (§5.5) |
| Nombre maximal de rattachements | exécution | ce LLD (§5.5) |
| Bornes de taille et formats d'upload | exécution | alignées sur `V2-LLD-002 §3` (§8.2) |
| Période d'interrogation d'ingestion | exécution | ce LLD (§8.4) |

Aucune de ces valeurs n'est codée en dur dans les composants.

### 15.3 Vérifications au build

| Contrôle | Ce qu'il empêche |
|---|---|
| TypeScript `strict`, aucun `any` implicite | qu'un contrat d'API dérive sans être vu |
| Types d'API dérivés du contrat serveur | qu'un champ renommé côté FastAPI passe inaperçu |
| Règle de lint interdisant `dangerouslySetInnerHTML` | la réintroduction de la surface XSS du §12.3 |
| Règle de lint interdisant `localStorage` | la réintroduction du stockage écarté au §4.2 |
| Vérification de la CSP sur l'artefact déployé | qu'un `unsafe-inline` s'introduise (§12.2) |
| Budget de taille de bundle | une dérive de dépendances non remarquée (§12.4) |

Les deux règles de lint sont la forme exécutable de deux décisions de ce LLD. Une décision de sécurité
qui ne repose que sur la relecture est une décision qui sera annulée par mégarde.

---

## 16. Tests et preuves

| # | Preuve attendue | Type | Bloquant |
|---|---|---|---|
| P1 | Le premier fragment est reçu significativement avant la fin de la réponse, sur le chemin complet | E2E navigateur | **Oui** |
| P2 | Le mode déclaré par `meta` est affiché ; un mode `emulated` est visible sans être présenté comme une panne | E2E | **Oui** |
| P3 | Une coupure de flux après `meta` produit un **rattachement**, jamais une réémission du message | E2E, coupure injectée | **Oui** |
| P4 | **Un flux ne contenant que des `delta`, quel que soit leur contenu — y compris du markdown imitant un bouton ou un `commandId` — ne produit aucune carte de commande actionnable** | intégration composant | **Oui** |
| P5 | La confirmation envoie un corps vide et le `commandId` reçu ; aucun autre champ n'est émis | contrat | **Oui** |
| P6 | Un double-clic sur « Confirmer » produit un seul appel, et l'état affiché est un succès | intégration | **Oui** |
| P7 | Une confirmation dont la réponse n'arrive jamais **ne déclenche aucun réessai** et bascule en « issue inconnue » | intégration négative | **Oui** |
| P8 | Une commande expirée affiche `expired` et invite à redemander l'action, sans appel supplémentaire | intégration | **Oui** |
| P9 | Le jeton d'accès n'est présent dans aucun stockage navigateur ; le jeton de rafraîchissement n'est pas en `localStorage` | statique + E2E | **Oui** |
| P10 | Un 401 déclenche un seul renouvellement puis une seule réémission ; un second 401 déconnecte | intégration | **Oui** |
| P11 | L'expiration du jeton pendant un flux n'interrompt pas le flux ; la confirmation qui suit renouvelle d'abord | E2E | **Oui** |
| P12 | L'annulation n'affiche « annulé » qu'après l'événement `cancelled`, et les compteurs consommés sont affichés | E2E | **Oui** |
| P13 | Les quatre familles de refus (§11.1) produisent quatre rendus distincts | intégration | **Oui** |
| P14 | Un code d'erreur inconnu produit un message générique et une trace, jamais le code brut | intégration | Oui |
| P15 | Aucun HTML brut n'est rendu depuis le markdown ; un lien `javascript:` produit par le modèle est neutralisé | sécurité | **Oui** |
| P16 | La CSP déployée ne contient ni `unsafe-inline` ni `unsafe-eval` ni origine tierce en `script-src` | statique sur l'artefact | **Oui** |
| P17 | Le résumé de commande est rendu en texte brut, pas en markdown | intégration | **Oui** |
| P18 | Pendant la diffusion, aucune annonce de lecteur d'écran par fragment ; une annonce unique à la fin | manuelle documentée | **Oui** |
| P19 | Le parcours envoyer → confirmer → résultat est réalisable entièrement au clavier | E2E clavier | **Oui** |
| P20 | Un upload rejoué après timeout avec le même `creationOperationId` ne crée pas de doublon | intégration | Oui |
| P21 | Les bornes d'upload appliquées côté client proviennent de la configuration servie, pas du bundle | statique | Oui |
| P22 | Aucune donnée de contenu n'apparaît dans les mesures remontées | statique | **Oui** |

---

## 17. Exploitation

### 17.1 Déploiement

Le bundle est un artefact statique déposé sur le bucket `frontend` (`V2-LLD-006 §7.3`) et servi par
CloudFront — dont la propriété reste à attribuer (§1.4). Le pipeline relève de `V2-LLD-008`. Deux
règles concernent directement ce LLD :

- **l'`index.html` et le fichier de configuration d'exécution ne sont pas mis en cache
  agressivement**, sinon un changement de configuration met un temps indéterminé à s'appliquer
  (§15.1) ;
- **les artefacts versionnés le sont**, puisque leur nom change à chaque build.

### 17.2 Retour arrière

Le retour arrière consiste à redéployer l'artefact précédent et à invalider l'`index.html`. Il est
sans effet de bord : le frontend ne détient aucun état durable. Une seule précaution — si la version
précédente ne connaît pas l'événement `command`, elle l'ignorera silencieusement (§5.3) et les cartes
de confirmation disparaîtront, sans que l'action soit exécutable. Le comportement est sûr (rien ne
s'exécute sans confirmation) mais il doit être connu de l'exploitant.

### 17.3 Diagnostic

| Symptôme | Première vérification |
|---|---|
| Réponse qui arrive d'un bloc | mode déclaré et `ttft_client` (§14.2) — le défaut est sur le chemin, pas dans le client |
| Déconnexions répétées | intervalle de `: ping` et idle timeout ALB (`V2-LLD-001 §7.3`) |
| Carte de confirmation absente | l'événement `command` est-il émis (`V2-LLD-001`), et la version déployée le connaît-elle (§17.2) |
| Confirmation systématiquement refusée | état et fenêtre de la commande (`V2-LLD-006 §5.3.2`) |
| Déconnexions au bout d'une heure | marge de renouvellement (§4.3) face à la durée de vie du jeton (`V2-LLD-005 §2.3`) |

---

## 18. Trajectoire V2 → V3

| Sujet | V2 | V3 |
|---|---|---|
| Stockage du jeton | accès en mémoire, rafraîchissement en `sessionStorage` (§4.2) | cookie `httpOnly` + endpoint d'échange et défense CSRF — exige une décision de `V2-ADR-001`/`V2-ADR-020`, pas du frontend |
| Refus d'une commande | fermeture locale, expiration naturelle (§7.6) | endpoint de refus explicite libérant le quota — amendement de `V2-ADR-014` |
| Reprise du flux | rattachement sans rejeu (`V2-ADR-011`) | rejeu token par token, explicitement hors périmètre V2 |
| Écrans d'administration | absents | consoles `platform_admin` (`V2-LLD-005 §4.7`) |
| Suivi d'ingestion | interrogation périodique (§8.4) | notification poussée, si un mécanisme existe sans connexion maintenue |
| Fédération d'identité | non utilisée ; `code` + PKCE reste configuré (§4.1) | interface hébergée ou fournisseur externe |

Aucune de ces évolutions n'invalide une décision de ce LLD : chacune remplace un mécanisme par un
autre dont la précondition n'est pas satisfaite en V2.
