# V2-LLD-005 — Identité, sécurité et conformité

- **Version :** 0.1
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G2
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§6.3, §11, §12)
- **Dépendances ADR :** V2-ADR-001, V2-ADR-006, V2-ADR-007, V2-ADR-008, V2-ADR-010, V2-ADR-014,
  V2-ADR-015, V2-ADR-016, V2-ADR-017, V2-ADR-020

> **Ce que ce LLD possède, et ce qu'il ne possède pas.** Le corpus renvoie à `V2-LLD-005` sur onze
> points précis, répartis dans six ADR et quatre LLD. Ce document les traite tous et n'en ouvre
> aucun autre. En particulier, il **ne redécide pas** le mécanisme de validation du token — réalisé
> par `V2-LLD-001 §7.1` — mais il en porte le **contrat** : quels claims sont exigés, ce qu'ils
> autorisent, et ce qu'un refus signifie. La règle de non-duplication est énoncée en §1.6 et vaut
> pour l'ensemble du document.

> **Trois écarts de corpus sont relevés et tranchés ici** (§1.7). Ils ne sont pas des précisions de
> rédaction : chacun porte sur une valeur qui gouverne l'isolation. Les corrections qu'ils appellent
> dans `HLD §7.5`, `capability-allocation-matrix.md`, `V2-LLD-001 §7.1.3` et `V2-LLD-003 §2.5` sont
> nommées ici et **appliquées dans le même lot de livraison**, par des commits distincts de celui
> qui porte ce LLD — la décision et sa propagation restent séparées et relisibles l'une sans
> l'autre.

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD/Charte | Libellé |
|---|---|
| HLD §6.3 | Frontière de sécurité serveur ; rejet du non-authentifié distinct de l'établissement de l'identité |
| HLD §11 | Chaque catégorie de donnée dispose d'une rétention, d'un mécanisme de suppression et d'un test |
| HLD §12 | Segmentation réseau, contrôle de l'egress, secrets dans Secrets Manager |
| Charte §6 | Défense contre prompt injection, data poisoning et exfiltration par tool |
| Charte §8 | Quotas et limites configurables |
| Charte §9 | Risques : injection documentaire, dérive de coût, exfiltration |
| Charte §4.2 | Aucune organisation ni gouvernance client inventée n'entre dans le périmètre |
| ADR-006 | Identité et tenant résolus côté serveur ; refus par défaut ; isolation par magasin |
| ADR-016 | Chemin unique CloudFront → API Gateway ; contenu des règles WAF ; magasin de compteurs |
| ADR-017 | Lecture directe par niveau de classification ; modèle de partage explicite |
| ADR-015 | Rétention du journal d'audit d'effacement ; autorisation du rejeu après restauration |
| ADR-020 | Configuration Cognito : pools, clients, flux d'authentification |
| CAM Domaine 10 | Défense en profondeur : aucune couche ne suppose que la précédente a filtré |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-001 | La frontière applicative est FastAPI ; les champs d'identité fournis par le client sont refusés (§4.1). Le chemin d'ingress est réalisé par `V2-LLD-001` ; ce LLD porte les contrôles qui s'y appliquent |
| V2-ADR-006 | Composition de l'identité (`actorId`, `subjectId`, `tenantId`, rôles, scopes) — §3 ; modèle d'autorisation à sept intrants et refus par défaut — §4 ; partitionnement et filtres par magasin — §4.8 ; journalisation d'identifiants hashés — §12.4 |
| V2-ADR-007 | Contrôles réseau de la plateforme consommés tels quels ; ce LLD porte la politique de clé KMS (§8) et la posture egress au titre de l'exfiltration (§11.5) |
| V2-ADR-008 | Redaction : `Authorization` et tout JWT ne sont jamais journalisés (§12.4) ; les refus de sécurité forment des séries de métriques distinctes (§15) |
| V2-ADR-010 | Le journal d'audit d'effacement est hors du périmètre de restauration ; ce LLD fixe sa rétention comme exigence de sécurité et l'autorisation du rejeu (§12.2, §12.3) |
| V2-ADR-014 | La confirmation est un appel authentifié dédié, hors du chemin du modèle ; ce LLD porte l'endpoint, la vérification d'identité de la confirmation et le quota de commandes `pending` (§4.6, §7.2) |
| V2-ADR-015 | Rétention du journal d'effacement ≥ fenêtre PITR ; scope requis pour déclencher un effacement et un rejeu (§4.7, §12.2) |
| V2-ADR-016 | **Contenu des règles WAF** et leur réglage (§6) ; **mécanisme de chemin unique** (§5) ; **magasin de compteurs de quota** (§7). Trois délégations explicites de cet ADR |
| V2-ADR-017 | Domaine fermé de classification consommé tel quel ; ce LLD porte l'**autorisation sur lecture directe** (§4.5), le **modèle de partage explicite** (§4.4) et le régime de reclassification côté autorisation |
| V2-ADR-020 | **Configuration Cognito** — pools, clients, flux (§2). Le contrat de validation du token est porté ici (§3.5) et réalisé par `V2-LLD-001 §7.1` |

### 1.3 Préconditions bloquantes héritées des ADR

| # | Précondition | Source | Conséquence si non satisfaite |
|---|---|---|---|
| P1 | Attachement effectif d'AWS WAF au stage REST API | `V2-ADR-016` précondition 1 | Le WAF ne subsiste que sur CloudFront ; **et** le mécanisme de chemin unique perd son point d'application à la passerelle (§5.2 — ce couplage est un écart relevé en §1.7) |
| P2 | Existence d'un mécanisme rendant CloudFront le seul chemin joignable | `V2-ADR-016` précondition 2 | Tous les contrôles portés par CloudFront sont contournables ; les preuves qui les exercent par le chemin nominal ne démontrent rien |
| P3 | Journal d'audit d'effacement indépendant du périmètre de restauration | `V2-ADR-015` précondition 3 | **Aucun repli.** La restauration PITR devient interdite, pas dégradée (`V2-LLD-006 §13.5.3`) |

Les préconditions non bloquantes sont listées en §17.2 avec leur repli.

### 1.4 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-002 | Répartition FastAPI/Runtime : couvert par `V2-LLD-003`. Ce LLD en consomme la conséquence — le contenu documentaire et Memory sont des données non fiables (§11.3) — sans redécider la répartition |
| V2-ADR-003 | Schéma S3 Vectors : couvert par `V2-LLD-002`. Le filtre tenant obligatoire est ici une **exigence d'autorisation** (§4.8), pas un schéma |
| V2-ADR-004 | Pipeline d'ingestion applicatif : cible V3 (`V2-ADR-019`), non provisionné en V2 |
| V2-ADR-005 | Orchestration des agents : couvert par `V2-LLD-003` |
| V2-ADR-011 | Streaming et annulations : couvert par `V2-LLD-003` et `V2-LLD-001`. Ce LLD en consomme la grandeur à borner (§7.2) |
| V2-ADR-012 | Repli modèle : couvert par `V2-LLD-003`. La condition d'admission en amont du repli est portée en §7.4 |
| V2-ADR-013 | Espace d'embedding : couvert par `V2-LLD-006` |
| V2-ADR-018 | Datasets et seuils RAG : couvert par `V2-LLD-002` et `V2-LLD-009` |
| V2-ADR-019 | Phasage RAG : sans effet sur les contrôles de ce LLD, hormis l'inventaire IAM/KMS déjà porté par `V2-LLD-001` |

### 1.5 Périmètre et exclusions

**Inclus.** Configuration Cognito ; composition et formats de l'identité de confiance ; registre
d'autorisation serveur ; modèle d'autorisation et ordre d'évaluation ; partage explicite ; lecture
directe par classification ; mécanisme de chemin unique ; contenu des règles WAF ; magasin de
compteurs de quota ; politiques de clé KMS ; inventaire et rotation des secrets ; sécurité des
uploads ; threat model ; audit trail et sa rétention ; valeurs jamais journalisées.

**Exclus, avec leur propriétaire.**

- **Le mécanisme de validation du token** — bibliothèque, paramètres de cache, comportement en
  panne du JWKS : `V2-LLD-001 §7.1.3` et `§7.1.4`. Ce LLD en porte le contrat (§3.5), pas la
  réalisation.
- **Le point d'attachement du WAF** et l'exigence de chemin unique : `V2-LLD-001 §7.4`. Ce LLD
  porte le **mécanisme** (§5) et le **contenu des règles** (§6).
- **Les valeurs de quota** et toute segmentation par classe d'utilisateur : paramètres
  d'exploitation, hors périmètre par la Charte §4.2 et par `V2-ADR-016`.
- **Les modèles de données** — tables, clés, TTL, cycles de vie : `V2-LLD-006`. Ce LLD énonce des
  exigences de rétention, jamais des schémas.
- **La séquence d'effacement** et le rejeu : `V2-LLD-006 §8.4` et `§13.5`. Ce LLD porte
  l'autorisation d'y accéder et la contrainte de rétention du journal.
- **Le contrat des tools MCP** et le catalogue : `V2-LLD-004`.
- **L'interface de confirmation**, le renouvellement de token côté navigateur et la sécurité
  navigateur : `V2-LLD-010`.
- **L'instrumentation OpenTelemetry** et la rétention des preuves : `V2-LLD-007`.
- **Les tests de sécurité négative** dans leur pyramide complète : `V2-LLD-009`. Ce LLD fixe les
  preuves attendues (§16), pas leur ordonnancement.
- **La détection comportementale d'abus**, Shield Advanced, et le régime juridique de la
  confidentialité : hors périmètre par `V2-ADR-016` et `V2-ADR-017`.

### 1.6 Règle de non-duplication

Plusieurs contrôles de ce LLD sont **réalisés ailleurs**. Le corpus a déjà payé le prix d'une valeur
portée à deux endroits — `V2-LLD-003 §5.2.2` et `V2-LLD-001 §7.3` ont porté deux valeurs et deux
causalités contradictoires pour le même `idle_timeout`. La règle suivante s'applique sans exception
dans ce document :

> **Un paramètre a un seul propriétaire. Ce LLD énonce l'invariant qu'il doit satisfaire ; il ne
> reproduit pas sa valeur.**

| Contrôle | Contrat (invariant) | Réalisation (valeur) |
|---|---|---|
| Validation du token | ce LLD §3.5 | `V2-LLD-001 §7.1.3` |
| Cache JWKS et panne | ce LLD §3.6 | `V2-LLD-001 §7.1.4`, `§16.4` |
| Attachement du WAF | `V2-ADR-016` P1 | `V2-LLD-001 §7.4` |
| Contenu des règles WAF | ce LLD §6 | ce LLD §17.1 |
| Chemin unique | `V2-LLD-001 §7.4` (exigence) | ce LLD §5 (mécanisme) |
| Rétention du journal d'effacement | ce LLD §12.2 | `V2-LLD-006 §10`, `§16.2` |
| Politique de clé des journaux | `V2-LLD-001 §12.1.1` | `V2-LLD-001 §12.1.1` |
| Schéma du magasin de compteurs | ce LLD §7.1 | `V2-LLD-006` à l'implémentation |

Lorsqu'une valeur apparaît dans ce document, c'est qu'elle n'existe nulle part ailleurs.

### 1.7 Écarts de corpus relevés par ce LLD

Trois écarts sont apparus à la rédaction. Chacun porte sur une valeur qui gouverne l'isolation, et
aucun n'est corrigé par ce document — les corrections sont nommées et relèvent des documents
concernés.

#### Écart 1 — la CAM **et le HLD** décrivent un mécanisme d'identité annulé par `V2-ADR-020`

Deux documents portent le mécanisme rejeté, et le second prime sur le premier.

**`HLD-Secure-AgentCore-V2-FR.md §7.5`** — le diagramme des flux d'identité porte l'option A au
complet : `JWT Cognito (id_token)`, puis `Claims (sub, custom:tenantId, rôles)`, puis
« API Gateway : extraction, puis propagation par en-têtes serveur dédiés ». Les trois éléments que
`V2-ADR-020` a écartés — le jeton d'identité, le claim personnalisé et la propagation par
en-têtes — y figurent dans le document de référence de l'architecture.

**Correction attendue dans `HLD §7.5` :** le diagramme part du **jeton d'accès** ; l'authorizer
rejette le non-authentifié sans propager de claim ; `Authorization` est transmis à FastAPI et à
FastAPI seulement ; FastAPI vérifie elle-même la signature contre le JWKS et résout `tenantId` par
le registre indexé par `sub`.

**`capability-allocation-matrix.md` Domaine 1** porte encore :

> « Propagation désigne le forwarding de ces claims vers FastAPI via des en-têtes HTTP dédiés
> injectés côté serveur (distincts de l'en-tête `Authorization`) […] seuls les en-têtes injectés
> par API Gateway sont une source valide (P-03). **Le format exact des en-têtes est défini en
> LLD-005.** »

C'est exactement l'**option A de `V2-ADR-020`, rejetée**, et la délégation porte sur un format
qu'aucun document ne peut désormais définir : `V2-LLD-001 §7.1.3` énonce que le chemin de résolution
**ne lit aucun en-tête d'identité, quel que soit son nom**.

La gravité tient à la phrase « seuls les en-têtes injectés par API Gateway sont une source valide » :
elle **désigne une source de vérité** pour l'identité. Un lecteur de la CAM — qui est le document de
répartition des capacités, donc celui qu'on consulte avant d'implémenter — conclurait que FastAPI
doit lire des en-têtes. `V2-ADR-020` a établi que cette confiance repose sur la précondition
bloquante non démontrée P2 (§1.3).

**Correction attendue dans `capability-allocation-matrix.md` Domaine 1 :** remplacer le paragraphe
« Claims Extraction vs Claims Propagation » par la distinction de `V2-ADR-020` — l'authorizer de la
passerelle rejette le non-authentifié, FastAPI établit l'identité par vérification de signature — et
retirer la délégation de format vers ce LLD, qui n'a plus d'objet. La note d'architecture voisine
(« aucun token Cognito ne doit être transmis au-delà de FastAPI ») reste exacte et n'est pas touchée.

#### Écart 2 — `custom:tenantId` en claim obligatoire contredit la résolution serveur de `V2-ADR-006`

`V2-LLD-001 §7.1.3` exige `token_use = id` et fait de `custom:tenantId` un claim dont l'absence
provoque un refus. Trois conséquences, dont deux non voulues.

**Le choix du type de token est forcé, et il l'est dans le mauvais sens.** `V2-ADR-006` énonce
`actorId = Cognito access-token claim sub` : le token d'accès. Cognito ne place pas les attributs
personnalisés dans le token d'accès sans personnalisation de token — le corpus se trouve donc à
exiger le token d'identité pour disposer de `custom:tenantId`, alors que l'ADR nomme l'autre. Un
token d'identité présenté comme identifiant d'appel à une API est par ailleurs contraire à l'usage
prévu du jeton : il est destiné au client, pas à la ressource.

**Le claim devient une dépendance d'autorisation alors que l'ADR le range en simple entrée.**
`V2-ADR-006` est explicite : « `tenantId` = résolution serveur contrôlée », et le claim est « une
entrée de la résolution, pas son résultat ». Faire du claim une condition de recevabilité du token
lui donne un pouvoir de blocage que l'ADR ne lui donne pas.

**Le tenant devient non révocable dans la durée de vie du token.** Si la valeur qui compte vient du
token, un changement d'appartenance ou une désactivation ne prend effet qu'à son expiration.

**Décision de ce LLD (§3.4) :** le registre d'autorisation serveur, indexé par `sub`, est la **seule**
source du `tenantId`, des rôles et de l'état du compte. Aucun claim personnalisé n'est requis. Le
token d'accès suffit, ce qui aligne le corpus sur la lettre de `V2-ADR-006`.

**Correction attendue dans `V2-LLD-001 §7.1.3` :** `token_use` vaut `access` ; la ligne
`custom:tenantId` est retirée de la table des claims requis ; la phrase « `tenantId` est résolu côté
serveur à partir du claim `custom:tenantId` et d'un registre » devient « à partir de `sub` et du
registre ». Un point supplémentaire, relevé en §3.1 : la phrase « le `sub` devient `actorId` après
hachage » est remplacée par « le `sub` est l'`actorId`, transmis tel quel à `trustedIdentity` — le
hachage produit `subjectId`, pas `actorId` ». Le reste de la table — liste blanche `RS256`,
`iss`/`aud` comparés à la configuration, `exp`/`nbf`, `sub` présent — est inchangé et reste la
référence.

Le gain n'est pas seulement de conformité : il permet de **borner la fenêtre de révocation** à la
durée de cache du registre plutôt qu'à la durée de vie du token (§3.7).

#### Écart 3 — la formule de namespace Memory est tronquée à 48 bits

`V2-LLD-003 §5.3` fixe `namespace = hash(tenantId + "#" + actorId)` et renvoie ici pour la formule
exacte. Le seul mécanisme de hachage du corpus est `safe_hash()` — SHA-256 **tronqué à 12 caractères
hexadécimaux** (`V2-ADR-008`), soit 48 bits.

Une troncature à 48 bits est adaptée à ce pour quoi `safe_hash()` a été conçu : la corrélation dans
les journaux, où une collision produit une ambiguïté de lecture. Elle ne l'est pas pour un
**namespace**, qui est une frontière d'isolation : deux identités qui partagent un namespace
partagent leur mémoire longue durée. La conséquence d'une collision n'est pas une gêne de
diagnostic, c'est une violation de `V2-ADR-006`.

**Décision de ce LLD (§3.3) :** le namespace utilise le condensat SHA-256 **complet** (64 caractères
hexadécimaux). La troncature reste réservée aux journaux et aux métriques. Deux fonctions distinctes,
deux usages distincts, et le nom de chacune le dit.

**Correction attendue dans `V2-LLD-003 §2.5` :** remplacer `hash(...)` par la formule nommée de §3.3
de ce LLD. (La formule est dans le tableau Memory de §2.5, pas dans §5.3 qui porte les budgets
d'invocation.)

---

## 2. Cognito — pool, clients et flux

`V2-ADR-020` exclut explicitement la configuration Cognito de son périmètre et la délègue ici.

### 2.1 User Pool

| Paramètre | Valeur `test` | Motif |
|---|---|---|
| Nom | `${env}-secure-agentcore` | — |
| Attributs requis | `email` (vérifié) | seul attribut nécessaire à la récupération de compte |
| Attributs personnalisés | **aucun** | conséquence de l'écart 2 : le tenant vient du registre, pas du token |
| Inscription libre (`AllowAdminCreateUserOnly`) | **activée — pas d'auto-inscription** | voir ci-dessous |
| Politique de mot de passe | 12 caractères minimum, 4 classes, historique 3 | — |
| MFA | `OPTIONAL`, `SOFTWARE_TOKEN_MFA` (TOTP) uniquement | SMS exclu : coût, et vulnérabilité au portage de numéro |
| `PreventUserExistenceErrors` | `ENABLED` | interdit l'énumération de comptes par la réponse d'erreur |
| Récupération de compte | email vérifié uniquement | — |
| Protection contre la suppression | `ACTIVE` | la suppression du pool invaliderait toutes les identités |
| Threat protection | mode `AUDIT` en `test` | le mode `ENFORCED` est facturé par utilisateur actif ; sa mise en service est une décision d'exploitation (§19) |

**L'auto-inscription est fermée, et c'est une décision de sécurité, pas une commodité.** Un pool
ouvert à l'inscription publique expose un point non authentifié qui crée des identités, donc des
tenants à résoudre, des quotas à allouer et des namespaces Memory à provisionner. Le WAF (§6) ne
distingue pas une inscription légitime d'une inscription automatisée. Fermer l'inscription supprime
cette surface entière plutôt que de la défendre. La contrepartie — les comptes sont créés par un
administrateur — est acceptable au périmètre du projet et cohérente avec la Charte §4.2, qui exclut
d'inventer un parcours d'onboarding client.

**MFA optionnel au pool, exigé pour les scopes d'administration.** Rendre le MFA obligatoire pour
tous ajouterait une friction sans rapport avec le risque porté par un compte utilisateur ordinaire,
dont le périmètre est déjà borné par `V2-ADR-006`. Les scopes d'administration (§4.7), eux, portent
l'effacement d'un utilisateur et le rejeu après restauration — des actions dont la compromission est
irréversible. La vérification est décrite en §4.7 et repose sur une précondition nommée en §17.2.

### 2.2 App clients

Un seul client applicatif en V2 dans le cas nominal — sous réserve de la précondition 4 de §17.2 : si l'attestation MFA n'est pas disponible sur le jeton d'accès, un second client est provisionné, configuré en MFA obligatoire, réservé aux comptes portant le rôle `platform_admin`.

| Paramètre | Valeur | Motif |
|---|---|---|
| Nom | `${env}-web` | SPA React (`V2-LLD-010`) |
| Secret client | **aucun** | un secret dans une SPA est public ; `V2-ADR-016` a rejeté les usage plans pour la même raison |
| Flux OAuth | `code` avec **PKCE S256** | — |
| Flux `implicit` | **interdit** | expose le token dans l'URL, donc dans l'historique, le `Referer` et les journaux d'accès |
| `ALLOW_USER_SRP_AUTH` | activé | authentification sans transmettre le mot de passe |
| `ALLOW_USER_PASSWORD_AUTH` | **interdit** | transmet le mot de passe en clair applicatif à l'API Cognito |
| `ALLOW_ADMIN_USER_PASSWORD_AUTH` | **interdit** | même motif, avec une identité privilégiée |
| `ALLOW_REFRESH_TOKEN_AUTH` | activé | renouvellement (`V2-LLD-010`) |
| Révocation de jeton | activée | voir §2.4 |
| URL de rappel | origine CloudFront du système uniquement | aucune URL locale en `test` partagé |
| Portées | `openid`, `email` | aucune portée personnalisée : les scopes applicatifs sont résolus côté serveur (§4.7) |

### 2.3 Durées de vie des jetons

| Jeton | Durée | Motif |
|---|---|---|
| Accès | **60 min** | jeton présenté à l'API ; borne la fenêtre d'une compromission de jeton |
| Identité | 60 min | non utilisé pour l'appel d'API (écart 2) ; conservé pour le profil côté client |
| Rafraîchissement | **30 jours** | borne la durée d'une session sans réauthentification |

Les trois valeurs sont des paramètres (§17.1).

### 2.4 Révocation — ce que Cognito borne, et ce qu'il ne borne pas

`V2-ADR-020` a laissé la révocation de session hors de son périmètre et conclu que « la durée de vie
du token reste la borne effective ». Ce LLD précise le tableau, parce que la conclusion n'est exacte
que pour l'un des deux jetons.

| Événement | Effet du `RevokeToken` Cognito | Borne effective |
|---|---|---|
| Révocation d'un jeton de rafraîchissement | le rafraîchissement ne produit plus de jeton | immédiate pour la **session** |
| Jetons d'accès déjà émis | **aucun** — ils restent cryptographiquement valides | 60 min (§2.3) |

Un jeton d'accès émis reste donc valide jusqu'à son expiration, quoi qu'il arrive côté Cognito.
Ce fait n'est pas contournable au niveau du fournisseur d'identité, et il est la raison pour laquelle
`V2-ADR-020` a énoncé sa conclusion.

**Ce LLD la resserre, sans introduire de mécanisme nouveau.** La résolution du tenant et des rôles
passe par le registre serveur à chaque requête (§3.4). Un compte désactivé, effacé ou dont le tenant
a changé est refusé **au registre**, avec un jeton parfaitement valide. La borne de révocation
effective n'est donc pas la durée de vie du jeton, mais la durée de cache du registre :

```text
borne de révocation effective = authz_registry_cache_ttl_seconds   (§17.1, défaut 30 s)
                              et non la durée de vie du jeton d'accès (60 min)
```

C'est une conséquence directe de la décision de l'écart 2, et l'un de ses bénéfices non recherchés.
Elle ne contredit pas `V2-ADR-020` : cet ADR constatait qu'aucune révocation n'était **décidée**, non
qu'aucune ne fût atteignable.

---

## 3. Identité de confiance

### 3.1 Composition

`V2-ADR-006` fixe la composition ; ce LLD en fixe les formats et les producteurs.

| Élément | Valeur | Producteur | Circule vers |
|---|---|---|---|
| `actorId` | le claim `sub` du jeton d'accès vérifié, tel quel | Cognito, vérifié par FastAPI | Runtime (`trustedIdentity`) |
| `subjectId` | `safe_hash(actorId)` — SHA-256 tronqué à 12 hex | FastAPI | journaux, métriques, traces |
| `tenantId` | résolu par le registre, indexé par `actorId` | registre serveur (§3.4) | Runtime (`trustedIdentity`) |
| `roles` | résolus par le registre | registre serveur | **ne circulent pas** (§3.6) |
| `scopes` | dérivés des rôles par politique serveur | FastAPI | ne circulent pas |

`actorId` est un UUID opaque produit par Cognito : il n'est pas une donnée identifiante en
lui-même, et sa transmission à Runtime est celle que `V2-ADR-006` prévoit. `subjectId` est ce qui
apparaît dans les journaux — jamais `actorId` (§12.4).

> **Alignement à opérer.** `V2-LLD-001 §7.1.3` écrit « le `sub` devient `actorId` après hachage ».
> `V2-ADR-006` écrit `actorId = sub` puis `subjectId = hash(actorId)`. Les deux ne peuvent pas être
> vrais. La lettre de l'ADR est retenue ici : hacher `actorId` avant de le transmettre à Runtime
> rendrait impossible toute jointure serveur avec le registre, et priverait `subjectId` de son objet.

### 3.2 Deux fonctions de hachage, deux usages

| Fonction | Sortie | Usage | Motif |
|---|---|---|---|
| `safe_hash(v)` | SHA-256, **tronqué à 12 hex** (48 bits) | journaux, métriques, traces, attributs de corrélation | une collision produit une ambiguïté de lecture |
| `isolation_hash(v)` | SHA-256, **complet** (64 hex) | namespace Memory, toute clé portant une frontière d'isolation | une collision produit une violation d'isolation |

C'est la décision de l'écart 3. La distinction est portée par le nom des fonctions, et non par une
consigne d'usage : une consigne se perd, un nom se lit à l'appel.

### 3.3 Namespace de mémoire longue durée

```text
namespace = isolation_hash(tenantId + "#" + actorId)
```

Le séparateur `#` est obligatoire et ne peut apparaître dans aucun des deux opérandes — l'un est un
UUID Cognito, l'autre un identifiant `t-<uuid>` (§3.4). Sans séparateur non ambigu, deux couples
distincts pourraient produire la même concaténation.

La formule est dérivée de `trustedIdentity`, jamais d'un claim brut : c'est l'exigence de
`V2-LLD-003 §5.3`, dont ce paragraphe est la réalisation.

### 3.4 Registre d'autorisation serveur

`V2-ADR-006` conclut qu'« un registre ou adapter d'autorisation serveur est nécessaire » sans le
spécifier. Ce LLD le spécifie ; son schéma exact relève de `V2-LLD-006` à l'implémentation.

**Rôle.** Le registre est la source de vérité de tout ce que le jeton ne doit pas porter : le tenant,
les rôles, et l'état du compte.

| Entrée | Sortie |
|---|---|
| `actorId` (claim `sub` vérifié) | `tenantId`, `roles[]`, `accountStatus` |

**Format du `tenantId` :** `t-` suivi d'un UUID v4 sans tirets. Opaque, assigné par le serveur,
jamais dérivé d'une valeur cliente ni d'un nom d'organisation.

**`accountStatus` :** domaine fermé `active | suspended | erased`. Toute valeur autre que `active`
produit un refus, quel que soit le jeton présenté. C'est le point de révocation de §2.4, et le point
où un utilisateur effacé (`V2-LLD-006 §8.4`) cesse d'obtenir une identité.

**Absence d'entrée = refus.** Un `sub` authentifié par Cognito mais absent du registre n'obtient
aucune identité. C'est le refus par défaut de `V2-ADR-006` appliqué au cas le plus probable en
exploitation : un compte créé dans le pool sans être enregistré. Le symptôme est un refus explicite
et journalisé, jamais un accès à un tenant par défaut.

**Cache.** La lecture est mise en cache par `actorId` pendant `authz_registry_cache_ttl_seconds`
(§17.1, défaut 30 s). Cette durée est la **borne de révocation effective** du système (§2.4) : la
réduire resserre la révocation et augmente la charge de lecture ; l'augmenter fait l'inverse. C'est
le seul arbitrage porté par ce paramètre, et il doit être fait consciemment — d'où sa présence dans
les règles de garde (§17.3).

**Indisponibilité du registre.** Elle **refuse**. Le registre est un contrôle d'autorisation : la
distinction de `V2-ADR-016` — un contrôle d'équité qui échoue dégrade, un contrôle d'autorisation
qui échoue refuse — s'applique ici dans son sens strict, exactement comme `V2-ADR-020` l'a appliquée
au JWKS. L'exception au refus par défaut reste bornée au compteur de quota (§7.3), et le registre ne
l'hérite pas. Le refus forme une série de métrique distincte (§15).

### 3.5 Contrat de validation du jeton

`V2-ADR-020` précondition 3 exige « une liste nominative des claims dont l'absence provoque un refus,
et la vérification que `aud` et `iss` sont contrôlés contre des valeurs de configuration ». C'est ce
contrat. Sa **réalisation** — bibliothèque, options, paramètres — est en `V2-LLD-001 §7.1.3` (§1.6).

| Contrôle | Exigence de ce LLD | Refus si |
|---|---|---|
| Signature | vérifiée par FastAPI contre le JWKS Cognito, jamais déléguée à une affirmation amont | signature invalide, `kid` inconnu après une actualisation |
| `alg` | liste blanche **`RS256` uniquement**, en liste positive et non par exclusion de `none` | tout algorithme hors liste |
| `iss` | **comparé** à une valeur de configuration | différent, absent |
| `aud` | **comparé** à une valeur de configuration | différent, absent |
| `exp` / `nbf` | tolérance d'horloge bornée et déclarée | expiré, pas encore valide |
| `token_use` | doit valoir **`access`** (écart 2) | absent ou différent |
| `sub` | présent, non vide | absent |

**Pourquoi la liste blanche est positive.** Interdire `none` laisse passer `HS256`, qui permet à un
attaquant de signer un jeton avec la clé publique du JWKS — publique par construction. Une liste
positive `["RS256"]` est la seule formulation qui ne dépende pas de l'exhaustivité d'une liste noire.

**Pourquoi `iss` et `aud` sont comparés et non constatés.** Un jeton correctement signé par un autre
pool Cognito, ou destiné à un autre client applicatif, est un jeton **valide** : sa signature vérifie,
ses dates sont bonnes, son `sub` est présent. Seule la comparaison à une valeur de configuration
établit qu'il est le nôtre. C'est la différence entre « ce jeton est authentique » et « ce jeton
m'est destiné ».

**Ce qui n'est pas exigé.** Aucun claim personnalisé. Aucun en-tête d'identité, quel qu'en soit le
nom (§1.7 écart 1). Le chemin de résolution ne consulte aucune valeur transmise en dehors de
`Authorization`, et c'est cette **absence de lecture** qui est prouvée (§16), non le bon
fonctionnement d'un filtre.

### 3.6 Ce qui circule vers Runtime, et ce qui ne circule pas

`runtime-contract.md` §1 laisse le contrat final aux LLD `V2-LLD-003` et `V2-LLD-005`. Pour la part
identité, ce LLD le fixe :

```json
"trustedIdentity": {
  "actorId": "...",
  "tenantId": "..."
}
```

**Les rôles et scopes ne sont délibérément pas transmis.** La CAM Domaine 1 attribue
`Business Authorization` à FastAPI et l'interdit à Runtime. Transmettre les rôles créerait la
capacité d'en faire quelque chose — et un composant qui reçoit des rôles finit par les évaluer. La
décision d'autorisation est prise avant l'invocation ; ce qui traverse la frontière est son
résultat, pas ses intrants.

**Ce que consomme le filtre d'exposition des tools.** `V2-LLD-003 §6.2` restreint le catalogue de
tools présenté au modèle. Ce filtre consomme la `tool_allowlist` d'`AgentConfig` — **résolue par
FastAPI à partir des rôles** (§4.7) — et non les rôles eux-mêmes. Il perd ainsi zéro capacité tout
en restant du bon côté de la frontière : il applique une décision, il n'en prend aucune.

Les champs interdits de `runtime-contract.md` §4 (`cognitoToken`, `authorizationHeader`,
`actorIdRaw`, `tenantIdRaw`, …) sont reconduits sans modification, et le test de contrat qui les
refuse est une preuve de ce LLD (§16).

### 3.7 Fenêtre d'autorisation résiduelle

`V2-LLD-006 §8.4` a nommé une fenêtre résiduelle d'effacement ; il en existe une seconde, de nature
différente, qui n'était pas nommée.

| Fenêtre | Durée | Ce qui subsiste |
|---|---|---|
| Résiduelle d'effacement (`V2-ADR-015`) | `residualWindowDays` | des données dans le périmètre PITR |
| **Résiduelle d'autorisation** (ce LLD) | `authz_registry_cache_ttl_seconds` | une décision d'autorisation prise sur un état révolu |

Un jeton reste valide 60 minutes après une suspension ; une décision d'autorisation reste servie
depuis le cache jusqu'à 30 secondes après. La seconde valeur est la borne réelle, et elle est
paramétrée, gardée (§17.3) et prouvée (§16). La nommer est ce qui la rend opposable : une fenêtre
non nommée n'est pas un risque accepté, c'est un risque ignoré.

---

## 4. Modèle d'autorisation

### 4.1 Les intrants

`V2-ADR-006` fixe **sept** intrants. Le septième — la commande confirmée — y a été ajouté à la
demande de `V2-ADR-014` ; il n'est donc pas un intrant d'une autre origine qui se surimposerait au
modèle, mais une composante du modèle lui-même.

| # | Intrant | Source |
|---|---|---|
| 1 | identité authentifiée | signature du jeton vérifiée par FastAPI (§3.5) |
| 2 | tenant résolu côté serveur | registre (§3.4) |
| 3 | action demandée | route et méthode, jamais un champ du corps |
| 4 | type et classification de la ressource | `documents` pour un document (`V2-ADR-017`) |
| 5 | ownership ou partage explicite | §4.4 |
| 6 | politique de rétention et de conformité | `V2-LLD-006 §10` |
| 7 | **commande confirmée** | magasin de commandes (`V2-ADR-014`, réalisé en `V2-LLD-006 §5.3`), pour les seules actions mutantes déclenchées par le modèle |

**Champs refusés dans le corps de la requête.** `actorId`, `tenantId`, `subjectId`, `roles`,
`scopes`, `trustedIdentity`, `classification` sur un chemin qui ne la modifie pas, toute clé de
partition. Le refus est un **400 avec code dédié**, distinct du 403 : un champ interdit est une
erreur de contrat, et la distinguer d'un refus d'autorisation évite qu'un client la traite comme un
problème de droits. La liste est celle de `V2-ADR-001`, étendue aux valeurs introduites depuis.

**Un refus est la valeur par défaut lorsqu'une information manque** (`V2-ADR-006`). Les deux seules
exceptions du corpus sont nommées, bornées et argumentées ailleurs : le compteur de quota
(`V2-ADR-016`, §7.3) et rien d'autre. Ni le JWKS (`V2-ADR-020`), ni le registre (§3.4), ni la lecture
de `documents` (`V2-ADR-017`) n'en bénéficient.

### 4.2 Ordre d'évaluation

L'ordre est fail-closed à chaque étape : une étape qui ne peut pas conclure refuse, elle ne passe pas
la main à la suivante.

```text
0. Chemin        secret de chemin unique présent et valide          sinon refus     (§5)
1. Jeton         signature, alg, iss, aud, exp, token_use, sub      sinon refus     (§3.5)
2. Registre      actorId connu, accountStatus = active              sinon refus     (§3.4)
3. Quota         admission sur la simultanéité                      sinon refus typé (§7)
4. Tenant        tenantId de la ressource == tenant courant         sinon refus     (§4.8)
5. Classification niveau lu dans `documents`                        détermine le socle (§4.5)
6. Ownership/ACL propriétaire, ou partage explicite                 restreint le socle (§4.4)
7. Indexabilité  restricted -> jamais dans un retrievalContext      refus d'injection (§4.5)
```

Les étapes 4 à 7 sont celles de `V2-ADR-017`, consommées telles quelles. Les étapes 0 à 3 les
précèdent et relèvent de ce LLD.

**Le quota est évalué en 3, avant l'autorisation sur la ressource.** L'ordre inverse serait plus
naturel — pourquoi consommer du quota pour une requête qui sera refusée ? — mais il permettrait à un
appelant de sonder l'existence de ressources sans limite : chaque sonde serait refusée en 4 sans
jamais atteindre le compteur. Le quota borne l'appel, pas son succès.

### 4.3 Refus — codes et ce qu'ils distinguent

`V2-ADR-016` précondition 5 exige que trois causes de refus soient distinguables. Ce LLD en compte
six, et la distinction est portée par le code, pas seulement par la métrique.

| Cause | Statut | Code | Réaction d'exploitation attendue |
|---|---|---|---|
| Chemin non unique (secret absent/faux) | 403 | `path_not_allowed` | tentative de contournement du WAF — incident de sécurité |
| Jeton invalide | 401 | `token_invalid` | normal en volume faible ; anormal en pic |
| JWKS indisponible au-delà de la tolérance | 503 | `jwks_unavailable` | **incident de sécurité** (`V2-ADR-020`) |
| Registre indisponible | 503 | `authz_registry_unavailable` | incident de disponibilité d'un contrôle d'autorisation |
| Quota dépassé | 429 | `quota_exceeded` | perte d'équité — pas un incident de sécurité |
| Autorisation refusée | 403 | `forbidden` | anormal en volume ; possible sonde |
| Champ interdit dans le corps | 400 | `field_not_allowed` | erreur de contrat client, ou tentative d'injection d'identité |

Le `ThrottlingException` Bedrock (`V2-ADR-012`) est une septième série, produite en aval et
distincte de `quota_exceeded` — c'est précisément la distinction que `V2-ADR-016` exige, puisque
l'une signale un abus interne et l'autre une contention de compte.

**Aucun de ces refus n'expose la cause interne au client.** Le corps de la réponse porte le code et
rien d'autre : ni le nom du claim manquant, ni l'existence de la ressource, ni la valeur attendue.
`PreventUserExistenceErrors` (§2.1) serait vain si l'API répondait « ce document appartient à un
autre tenant » plutôt que 403.

### 4.4 Partage explicite

`V2-ADR-017` renvoie ici pour le modèle de partage — « qui partage, avec qui, par quelle API » — et
en consomme le résultat.

**Portée.** Un partage lie un `documentId` à un `actorId` **du même tenant**, en lecture seule.

| Propriété | Décision | Motif |
|---|---|---|
| Granularité | par document, jamais par préfixe ni par lot | un partage de préfixe autoriserait des documents futurs, non consentis au moment du geste |
| Cible | un `actorId` du tenant courant | le partage inter-tenant ouvrirait un chemin d'exfiltration que `V2-ADR-006` ferme par ailleurs |
| Droit conféré | lecture uniquement | un partage en écriture serait une délégation d'ownership, non décidée par le corpus |
| Transitivité | **aucune** — un bénéficiaire ne peut pas repartager | sans cette règle, l'ensemble des bénéficiaires n'est plus borné par le propriétaire |
| Plafond | la classification (`V2-ADR-017`) | un partage autorise **dans** le niveau, jamais au-delà |
| Révocation | immédiate, sans confirmation | resserrer un accès n'est pas une action à conséquence de sécurité (`V2-ADR-014`) |
| Octroi | action mutante `V2-ADR-014` **lorsqu'elle est déclenchée par le modèle** ; directe lorsqu'elle est déclenchée par l'utilisateur via l'API | `V2-ADR-014` borne son périmètre aux actions dont les paramètres sont produits par le modèle |

**Le partage ne franchit pas le plafond, y compris pour `restricted`.** Un document `restricted`
partagé reste lisible par le bénéficiaire en accès direct et n'entre dans aucun `retrievalContext`,
pas même le sien. C'est une preuve nommée de `V2-ADR-017`, reprise en §16.

**Ce que le partage n'est pas.** Il ne crée pas de rôle, ne modifie pas le tenant de la ressource et
n'apparaît pas dans le jeton. C'est une entrée de l'étape 6 (§4.2), rien de plus.

### 4.5 Lecture directe d'un document

`V2-ADR-017` nomme explicitement l'écart : « la lecture directe de document ne mentionne pas de
vérification de classification ». Ce paragraphe le comble.

```text
GET /api/v1/documents/{documentId}

1. tenant           documents[tenantId] == tenant courant           sinon 403
2. classification   niveau lu dans `documents`, pas dans le chunk   détermine le socle
3. ownership/ACL    propriétaire, ou partage explicite (§4.4)       restreint le socle
—— l'étape 4 (indexabilité) ne s'applique pas ——
```

**L'étape 4 ne s'applique pas, et c'est la propriété qui donne son sens à `restricted`.** Un document
`restricted` **reste lisible par son propriétaire** en accès direct ; il n'entre dans aucun contexte
transmis à Bedrock. La lecture directe et l'injection dans un prompt ne sont pas le même acte : la
seconde expose le contenu à l'inférence. Sans cette distinction, `restricted` serait indiscernable
d'une suppression — et c'est exactement le second volet de la preuve exigée par `V2-ADR-017`.

**`quarantined` prime sur la classification.** Un document en quarantaine n'est ni lisible ni
indexable, quelle que soit sa classification déclarée (`V2-ADR-017`). La lecture directe le refuse
au même titre que le retrieval l'écarte.

**Absence d'entrée `documents` = refus.** Le fail-closed de `V2-ADR-006` s'applique : un
`documentId` sans entrée est un 404 indistinguable d'un 403 pour un appelant non autorisé — ne pas
distinguer les deux est délibéré, faute de quoi l'API confirmerait l'existence de ressources d'autres
tenants.

**URL présignées.** Lorsqu'une lecture directe est servie par une URL présignée S3, elle est émise
**après** les étapes 1 à 3, liée à un objet unique, en lecture seule, et d'une durée de vie
`presigned_url_lifetime_seconds` (§17.1), contrainte par N8 à rester inférieure à la fenêtre de
révocation effective (§3.7) — sans quoi une URL survivrait à la suspension du compte qui l'a
obtenue. L'URL est émise et consommée dans le même flux : elle n'est ni mise en cache, ni
partagée, ni stockée par le client. Sa durée courte est une contrainte de conception — le
transfert S3 démarre bien avant l'expiration. C'est la preuve « URL présignée inutilisable hors
ressource et durée autorisées » de `V2-ADR-006`.

### 4.6 Endpoint de confirmation

`V2-ADR-014` place la confirmation hors du chemin du modèle et en délègue la réalisation. Ce LLD en
porte la part autorisation ; le contrat du tool relève de `V2-LLD-004`, le magasin de `V2-LLD-006`.

```text
POST /api/v1/commands/{commandId}/confirm
```

| Contrôle | Règle |
|---|---|
| Authentification | jeton Cognito vérifié par FastAPI, comme toute route (§3.5) |
| Identité | **seule** l'identité qui a fait matérialiser la commande peut la confirmer — la connaissance du `commandId` ne suffit pas |
| Tenant | le tenant de la commande doit être le tenant courant |
| État | la commande doit être `pending` ; toute autre valeur refuse |
| Corps de requête | **vide** — aucun paramètre métier n'est accepté |
| Quota | le nombre de commandes `pending` par identité est borné (§7.2) |

**Le corps vide n'est pas une simplification.** Accepter le moindre paramètre à la confirmation
rouvrirait l'écart de contenu que `V2-ADR-014` ferme : ce qui est exécuté serait de nouveau
partiellement produit ailleurs que dans la commande stockée. La confirmation porte sur une
référence, et sur rien d'autre.

**Le modèle n'est pas sur ce chemin.** Aucun tool, aucune route accessible depuis Runtime n'atteint
cet endpoint. C'est ce qui rend l'injection indirecte incapable de produire un effet de bord (§11.3).

### 4.7 Scopes d'administration

Les scopes sont **résolus côté serveur** à partir des rôles du registre (§3.4). Aucun scope n'est
porté par le jeton — Cognito n'expose que `openid` et `email` (§2.2).

| Rôle | Scope dérivé | Autorise |
|---|---|---|
| `user` | `app:use` | routes conversationnelles et documentaires de son périmètre |
| `tenant_admin` | `tenant:admin` | administration des utilisateurs du tenant, partages |
| `platform_admin` | `platform:admin` | **effacement d'un utilisateur** (`V2-LLD-006 §8.4`), **rejeu après restauration** (`V2-LLD-006 §13.5`), lecture du journal d'audit d'effacement (§12.2) |

**`platform:admin` exige une authentification à second facteur.** Les trois actions qu'il porte sont
irréversibles ou portent sur des données d'audit. Le contrôle est le suivant : FastAPI exige que le
jeton atteste d'une authentification MFA avant d'accorder ce scope. Le porteur exact de cette
attestation dans le jeton d'accès Cognito est une **précondition à vérifier nominativement**
(§17.2, précondition 4) ; si l'attestation n'est pas disponible sur le jeton d'accès, le repli est un
client applicatif distinct configuré en MFA obligatoire, réservé aux comptes portant ce rôle. Le
repli est plus lourd et n'est pas préféré, mais il ne dégrade pas le contrôle.

**Ce que `platform:admin` n'autorise pas.** Il ne lit aucun document, aucun contenu de conversation
et aucune mémoire. L'administration porte sur le cycle de vie des identités et sur les preuves, pas
sur les données des personnes. Un administrateur qui aurait besoin de lire un document doit s'en voir
accorder l'accès par le mécanisme ordinaire (§4.4), et cet accès est audité comme tout autre.

### 4.8 Isolation par magasin

`V2-ADR-006` fixe le principe ; ce LLD énonce ce qui est vérifié, magasin par magasin. Les schémas
appartiennent à `V2-LLD-002` et `V2-LLD-006`.

| Magasin | Contrôle porté par l'autorisation | Ce que ce contrôle ne remplace pas |
|---|---|---|
| DynamoDB | clés construites côté serveur incluant le tenant ; **aucun `Scan` cross-tenant** dans le chemin applicatif | l'évaluation §4.2, qui décide de l'accès |
| S3 | préfixes dérivés côté serveur ; URL présignées bornées (§4.5) | — |
| S3 Vectors | **filtre tenant obligatoire construit côté serveur**, jamais issu d'un paramètre client | le post-filtrage FastAPI, qui est la décision (`V2-ADR-019`) |
| AgentCore Memory | namespace dérivé de `trustedIdentity` par `isolation_hash` (§3.3) | — |
| Runtime et MCP | resource policies IAM ; identité **injectée** côté serveur, toute identité produite par le modèle est écrasée | — |

**Le filtre de magasin est une défense en profondeur, pas l'autorisation.** `V2-ADR-006` le dit :
« les filtres S3 Vectors font partie du contrôle d'accès en profondeur mais ne remplacent pas
l'autorisation applicative ». Un système dont le seul contrôle serait le filtre de requête serait à
la merci d'un filtre mal construit ; c'est la raison pour laquelle l'ordre §4.2 place la décision
avant, et le filtre en complément.

---

## 5. Chemin unique CloudFront → API Gateway

`V2-ADR-016` fixe l'exigence et renvoie ici pour le mécanisme : « secret partagé injecté par
CloudFront et vérifié par une resource policy, ou origine privée — relève de `V2-LLD-005` ».
`V2-LLD-001 §7.4` porte l'exigence et sa vérifiabilité au plan. Ce paragraphe décide du mécanisme.

### 5.1 Ce que les mécanismes candidats permettent réellement

| Mécanisme | Applicable à un REST API Regional | Limite |
|---|---|---|
| Resource policy sur un en-tête secret | **non** | les resource policies API Gateway ne portent pas de condition sur un en-tête applicatif arbitraire |
| Resource policy sur `aws:SourceIp` | partiellement | exigerait d'énumérer les plages d'origine CloudFront, qui changent ; la liste gérée existe pour les groupes de sécurité, pas pour les conditions IAM |
| Origine privée CloudFront | **non** | les origines VPC CloudFront ciblent ALB, NLB et EC2 — pas un point de terminaison API Gateway public |
| API privé (`execute-api` VPC endpoint) | non en l'état | rendrait le point de terminaison injoignable depuis CloudFront sans un intermédiaire non décidé |
| **Secret partagé injecté par CloudFront, vérifié en aval** | **oui** | le point de vérification est le sujet de §5.2 |

La formulation de `V2-ADR-016` — « secret partagé […] vérifié par une resource policy » — décrit donc
un montage que le service ne permet pas. Le secret est le bon mécanisme ; la resource policy n'est
pas le bon vérificateur.

### 5.2 Décision — un secret, deux points de vérification

**Décision :** CloudFront injecte un en-tête secret sur chaque requête vers l'origine. Ce secret est
vérifié à **deux points**, dont l'un ne dépend d'aucune précondition.

```text
CloudFront  ──[ X-Origin-Verify: <secret> ]──►  API Gateway (stage)  ──►  VPC Link  ──►  FastAPI
                                                      │                                    │
                                          règle WAF sur le stage                  vérification applicative
                                          (dépend de P1)                          (ne dépend de rien)
```

| Point | Ce qu'il ferme | Dépend de |
|---|---|---|
| Règle WAF sur le stage REST API | l'accès direct à la **passerelle** : la requête est rejetée avant l'intégration | **P1** (§1.3) |
| Vérification par FastAPI, étape 0 de §4.2 | l'accès direct à l'**application** : aucune requête hors chemin n'est servie | rien |

**Pourquoi deux points, et pourquoi celui de FastAPI est le fondement.** `V2-ADR-016` a supposé ses
deux préconditions bloquantes indépendantes, et a écrit que si P1 échouait, P2 deviendrait
« indispensable ». Or le mécanisme naturel de P2 — une règle WAF sur le stage vérifiant l'en-tête —
**s'attache au même point que P1**. Si le WAF ne s'attache pas au stage, P2 perd son vérificateur en
même temps que P1 perd son WAF : les deux préconditions tombent ensemble, alors que l'ADR comptait
sur la seconde pour compenser la première.

C'est l'écart de couplage relevé en §1.3. La vérification applicative le résout : elle est portée par
un composant que nous écrivons, et son existence ne dépend d'aucune capacité de service à vérifier.
Le raisonnement est celui de `V2-ADR-020` transposé — l'ancrage d'un contrôle ne doit pas reposer sur
le fait le moins établi.

**Ce que la vérification applicative ne fait pas.** Elle ne protège pas la passerelle d'un flot
volumétrique adressé directement à son point de terminaison : la requête est comptée, routée et
transmise avant d'être refusée. C'est le rôle du plafond global d'étape (`V2-ADR-016`) et de la règle
WAF lorsque P1 est satisfaite. Les deux points ne bornent pas la même grandeur, et aucun ne rattrape
l'absence de l'autre — c'est le même partage que celui des trois couches de quotas.

### 5.3 Le secret n'est pas une identité

Le secret de chemin atteste **d'où vient la requête**, jamais **qui l'émet**. Sa compromission donne
l'accès au chemin, pas une identité : une requête portant le bon secret et un jeton invalide est
refusée à l'étape 1 (§4.2).

C'est la conséquence directe de `V2-ADR-020`. Avant cette décision, un secret de chemin compromis
aurait permis de forger des en-têtes d'identité et donc d'usurper un compte. Ce n'est plus le cas :
la compromission du secret est un incident de contournement de WAF, pas une compromission
d'isolation. La gravité est réelle et bornée — et le fait qu'elle soit bornée est un acquis de
l'ADR, pas une propriété du secret.

### 5.4 Rotation

Un secret de chemin non rotatif est un secret permanent : sa compromission n'a pas de terme.

| Propriété | Décision |
|---|---|
| Magasin | Secrets Manager, CMK dédiée (§9) |
| Période | `path_secret_rotation_days` (§17.1) |
| Fenêtre de recouvrement | **deux valeurs acceptées simultanément** — courante et précédente — pendant `path_secret_overlap_hours` |
| Ordre de bascule | 1. publier la nouvelle valeur comme acceptée ; 2. mettre à jour l'origine CloudFront ; 3. retirer l'ancienne à l'issue de la fenêtre |

**La fenêtre de recouvrement est obligatoire.** Une bascule atomique n'existe pas : la propagation
d'une modification de distribution CloudFront n'est pas instantanée, et une rotation sans
recouvrement produirait une indisponibilité totale du service pendant cette propagation. L'ordre
ci-dessus est celui qui n'a aucune fenêtre de refus, et c'est le seul.

**Comparaison des valeurs.** La vérification applicative compare en **temps constant**. Une
comparaison naïve fuit la valeur par le temps de réponse, et l'attaquant dispose ici d'un oracle sans
limite de tentatives autre que le plafond d'étape.

### 5.5 Vérifiabilité au plan

`V2-LLD-001 §7.4` porte la règle de garde de présence. Ce LLD ajoute ce que la garde doit vérifier
sur le mécanisme lui-même (§17.3) : l'en-tête d'origine est configuré sur la distribution, sa valeur
est une référence Secrets Manager et non une valeur littérale dans l'état Terraform, et la période
de rotation est déclarée.

---

## 6. WAF — contenu des règles

`V2-ADR-016` exclut de son périmètre « le contenu des règles WAF managées et leur réglage » et le
délègue ici.

### 6.1 Périmètre — la population non identifiée

`V2-ADR-016` établit que le WAF « n'a aucune prise utile sur l'abus authentifié » : il ne voit ni
l'identité ni le coût. Son objet est donc borné, et l'énoncer évite l'erreur la plus coûteuse — croire
l'abus authentifié couvert.

| Ce que le WAF couvre | Ce qu'il ne couvre pas |
|---|---|
| volumétrie et flot par IP | l'abus par une identité légitime (§7) |
| signatures d'attaque L7 | l'injection indirecte par document (§11.3) |
| protection du point d'authentification Cognito | l'exfiltration par requêtes autorisées (§11.5) |
| protection du frontal statique | le contournement de chemin, sauf la règle §6.4 |

### 6.2 Deux web ACL, deux portées

| Web ACL | Ressource | Portée | Conditionné par |
|---|---|---|---|
| `${env}-waf-cloudfront` | distribution CloudFront | toute la surface publique, frontal statique compris | — |
| `${env}-waf-apigw` | stage REST API | dernier filet avant le chemin privé, **et** vérification du secret de chemin (§5.2) | **P1** |

Le second n'existe que si P1 est satisfaite. Son absence ne retire rien au premier ; elle retire le
point de vérification amont du chemin unique, dont §5.2 démontre qu'il n'est pas le fondement.

### 6.3 Règles managées retenues

Toutes en `Count` d'abord, puis en `Block` (§6.5).

| Groupe managé AWS | Retenu | Motif |
|---|---|---|
| `AWSManagedRulesCommonRuleSet` | oui | signatures génériques L7 |
| `AWSManagedRulesKnownBadInputsRuleSet` | oui | charges d'exploitation connues |
| `AWSManagedRulesAmazonIpReputationList` | oui | réputation, coût nul en faux positifs sur du trafic applicatif |
| `AWSManagedRulesAnonymousIpList` | **non** | bloquerait les VPN d'entreprise et les réseaux d'anonymisation légitimes ; le rapport bénéfice/faux positifs n'est pas favorable sur une application authentifiée |
| `AWSManagedRulesSQLiRuleSet` | **non** | aucune base SQL dans l'architecture ; une règle qui ne protège rien produit des faux positifs sans contrepartie |
| `AWSManagedRulesLinuxRuleSet` / `UnixRuleSet` | non | les tâches ne servent aucun contenu de système de fichiers |
| `AWSManagedRulesBotControlRuleSet` | non en V2 | facturation à la requête et réglage à instruire ; réévalué en V3 (§19) |

**Exclusions au sein de `CommonRuleSet`.** Deux règles doivent être exclues et la raison est
architecturale, pas cosmétique :

| Règle exclue | Motif |
|---|---|
| `SizeRestrictions_BODY` | la limite par défaut du corps inspecté est inférieure à la taille d'upload documentaire admise (`V2-LLD-002 §3`) ; conservée telle quelle, elle bloquerait des uploads légitimes |
| `NoUserAgent_HEADER` | les clients programmatiques légitimes du parcours de test n'en portent pas systématiquement |

L'exclusion de `SizeRestrictions_BODY` **ne retire pas la limite de taille** : elle est portée par
FastAPI et par API Gateway, où elle est exacte plutôt qu'approchée. C'est la règle générale de ce
paragraphe — on n'exclut une règle managée que lorsqu'un contrôle plus précis existe ailleurs.

### 6.4 Règles propres

| # | Règle | Action | Portée | Motif |
|---|---|---|---|---|
| 1 | Secret de chemin absent ou invalide | `Block` | `waf-apigw` | vérification amont du chemin unique (§5.2) |
| 2 | Rate-based par IP sur `/oauth2/*` et les routes d'authentification | `Block` | `waf-cloudfront` | le point d'authentification est la seule surface non authentifiée qui reste ; c'est là que le bourrage d'identifiants s'exerce |
| 3 | Rate-based par IP, seuil global | `Block` | `waf-cloudfront` | flot volumétrique |
| 4 | Taille d'en-tête `Authorization` hors bornes plausibles | `Block` | les deux | un `Authorization` de plusieurs kilooctets n'est pas un JWT Cognito ; le refuser au WAF évite de le porter jusqu'à la vérification de signature |
| 5 | Méthodes HTTP hors `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS` | `Block` | `waf-cloudfront` | aucune route n'en expose d'autres |

**La règle 2 est distincte de la règle 3, et c'est délibéré.** Un seuil global assez haut pour ne pas
gêner l'usage normal est trop haut pour du bourrage d'identifiants, qui se pratique à faible débit.
Un seuil bas sur la seule surface d'authentification borne l'attaque sans toucher au reste.

**Aucune règle rate-based n'agrège sur un claim.** `V2-ADR-016` a rejeté l'option A pour trois
raisons — `tenantId` inexistant à ce point, comptage approximatif, fenêtre discrète — et rien ici
ne les contourne. L'agrégation reste l'IP source.

### 6.5 Déploiement progressif — `Count` avant `Block`

Toute règle managée entre en service en `Count` pendant `waf_count_mode_days` (§17.1), puis passe en
`Block` après revue des correspondances.

**Ce n'est pas une précaution de style.** Un groupe managé activé directement en `Block` sur une
application dont le trafic n'a jamais été observé produit des refus légitimes indiscernables d'une
attaque, et le réflexe d'exploitation — désactiver le groupe — laisse la surface entièrement
découverte. Le mode `Count` produit la même mesure sans le refus.

La sortie du mode `Count` est une **décision explicite**, consignée, jamais un défaut de
configuration. La règle 1 (§6.4) fait exception : elle entre directement en `Block`, puisque son
faux positif ne peut venir que d'une origine non légitime.

### 6.6 Journalisation

Les journaux WAF sont livrés vers CloudWatch Logs, groupe dédié, chiffré par la CMK des journaux
(`V2-LLD-001 §12.1.1`), avec **redaction de l'en-tête `Authorization`** au niveau de la configuration
de journalisation WAF.

C'est le point de fuite le plus facile à manquer : le WAF journalise les en-têtes des requêtes qu'il
inspecte, et `Authorization` transite désormais jusqu'à FastAPI (`V2-ADR-020`). Sans cette
configuration, l'interdiction de §12.4 serait tenue par l'application et violée par
l'infrastructure — et personne ne la chercherait là.

L'en-tête de secret de chemin (§5) est redacté de la même manière et pour la même raison.

---

## 7. Quotas — magasin de compteurs

`V2-ADR-016` précondition 3 délègue le choix du magasin, en exigeant « un incrément atomique et une
expiration », une latence mesurée et un SLA déclaré.

### 7.1 Choix du magasin

| Candidat | Atomicité | Expiration | Coût structurel | Retenu |
|---|---|---|---|---|
| DynamoDB, `UpdateItem` conditionnel | oui | TTL natif | aucun composant nouveau | **oui** |
| ElastiCache Redis | oui (`INCR`) | oui | cluster always-on, sous-réseaux, bascule à opérer | non |
| Compteur en mémoire par tâche | — | — | faux : n tâches, n compteurs | non |

**DynamoDB est retenu.** Le motif décisif n'est pas la latence — Redis est plus rapide — mais le fait
que le comportement en panne du compteur est **déjà décidé comme dégradant** (`V2-ADR-016`). Un
magasin dont l'indisponibilité ne refuse pas ne justifie pas d'introduire un composant always-on
supplémentaire, avec sa bascule, son chiffrement et son groupe de sécurité. Le compteur hérite du
modèle IAM, KMS et de sauvegarde déjà en place.

Le compteur en mémoire est écarté sans discussion : avec plusieurs tâches ECS, il borne la
consommation par tâche et non par identité, c'est-à-dire qu'il ne borne pas ce qu'il prétend borner.

### 7.2 Les quatre dimensions

`V2-ADR-016` fixe les dimensions et la monnaie ; ce LLD fixe le moment et la mécanique.

| Dimension | Moment | Mécanique |
|---|---|---|
| Invocations conversationnelles simultanées | admission | écriture conditionnelle sur l'entrée d'identité (§7.3) |
| Tokens consommés par fenêtre | règlement, fin d'invocation | `ADD` sur un compteur à TTL glissant |
| Documents en cours d'ingestion | admission, à l'upload | même mécanique que la simultanéité |
| Commandes `pending` non résolues | admission, à la matérialisation | même mécanique |

**Aucune valeur n'est fixée ici.** `V2-ADR-016` les classe en paramètres d'exploitation et la Charte
§4.2 exclut d'inventer une politique de service. Elles sont déclarées en §17.1 sans valeur par
défaut, et leur absence au plan est refusée (§17.3).

### 7.3 Simultanéité — les compteurs en vol fuient, et il faut le traiter

Une invocation en vol est décrémentée à son terme. Si la tâche ECS qui la porte s'arrête
brutalement, la décrémentation n'a pas lieu : l'identité perd définitivement une unité de son quota,
et suffisamment d'incidents la bloquent entièrement. Un compteur scalaire ne permet pas de distinguer
une invocation vivante d'une fuite.

**Décision : l'entrée d'identité porte les invocations en vol avec leur échéance**, et non un
compteur.

```text
clé      : ACTOR#<actorId>
attribut : inflight = { "<invocationId>": <expiryEpochSeconds>, ... }
```

La clé utilise `actorId` (l'UUID Cognito, §3.1) et non `subjectId`. `subjectId` est le
pseudonyme des journaux, métriques et traces (§12.4) ; une clé DynamoDB n'est pas un journal. Le
hachage tronqué à 48 bits (`safe_hash`) serait inadéquat ici : une collision assignerait deux
identités au même compteur, faussant l'admission sans violer l'isolation. `actorId` n'est pas une
donnée identifiante par lui-même (§3.1) et ne présente aucun risque de collision.

L'admission est une **écriture conditionnelle unique** qui, dans la même opération :
purge les entrées dont l'échéance est dépassée, compte celles qui restent, refuse si le compte
atteint la limite, et ajoute l'invocation courante avec son échéance.

L'échéance vaut la durée maximale d'un flux (`V2-ADR-011`, 15 min) augmentée d'une marge. Une fuite
se résorbe donc seule à l'échéance, sans processus de nettoyage, et la taille de la structure est
bornée par la limite elle-même — elle ne peut pas croître indéfiniment.

**Le nettoyage a lieu à l'admission, pas en tâche de fond.** Un nettoyage périodique demanderait un
composant, un ordonnancement et une garantie d'exécution ; le faire à l'admission le rend gratuit et
garantit que la valeur lue est toujours à jour au moment où elle décide.

**Le déclenchement est l'invocation, pas la connexion.** `V2-ADR-016` l'exige : un flux abandonné par
déconnexion continue de compter jusqu'à son terme ou son annulation. La décrémentation est portée par
le cycle de vie de l'invocation côté serveur, jamais par la fermeture du flux SSE. C'est une preuve
nommée (§16).

### 7.4 Comportement en panne — l'exception, et sa borne

`V2-ADR-016` pose ici la seule exception au refus par défaut du corpus.

| Situation | Comportement |
|---|---|
| Magasin injoignable | **ne refuse pas** ; repli sur le plafond global d'étape API Gateway |
| Opération atomique au-delà du SLA (`quota_store_p99_ms`, §17.1) | **identique** à l'indisponibilité totale |
| Retour du magasin | les invocations terminées pendant la panne sont perdues pour le règlement ; celles dont le règlement n'a pas été écrit tentent une écriture différée |

L'événement est alerté comme une **perte de contrôle d'équité**, jamais comme un incident de
sécurité. C'est la distinction que `V2-ADR-016` et `V2-ADR-020` établissent ensemble, et le tableau
des refus (§4.3) la porte jusque dans les codes.

**L'exception ne s'étend à rien d'autre.** Ni au JWKS (`V2-ADR-020`), ni au registre d'autorisation
(§3.4), ni à la lecture de `documents` (`V2-ADR-017`), ni au secret de chemin (§5.2). Chacun de ces
contrôles refuse en panne, et la raison est toujours la même : leur objet est d'empêcher.

### 7.5 La cohérence de plateforme

`V2-ADR-016` énonce que le quota par identité ne protège rien sans plafond de plateforme, et fait de
`tauxSursouscription`, `plafondPlateforme` et `tokenBudgetWindowDays` trois paramètres gardés.

```text
somme(quotaIdentité) / plafondPlateforme = tauxSursouscription, déclaré explicitement
plafondPlateforme <= admissions servables par le quota Bedrock du modèle configuré
tokenBudgetWindowDays <= durée maximale d'une invocation conversationnelle
```

Les trois sont vérifiés par `terraform_plan_guard.py` en mode numérique (§17.3). La capacité servable
provient d'un paramètre SSM alimenté à la découverte de capacité (précondition §17.2) ; un plan dont
ce paramètre est absent ou nul est refusé.

**Le repli modèle de `V2-ADR-012` n'est une réserve que si le plafond s'applique avant lui.** Sans
admission en amont, un appelant qui sature le quota primaire bascule sur le repli et le sature à son
tour. C'est la condition que `V2-ADR-016` ajoute à `V2-ADR-012`, portée ici parce que c'est ici que
l'admission est réalisée.

---

## 8. KMS — clés et politiques

`V2-LLD-006 §11` fixe l'inventaire des magasins et leur clé ; il renvoie ici pour « la politique de
clé exacte ». `V2-LLD-001 §12.1.1` a déjà fixé celle des groupes de journaux. Ce paragraphe fixe le
reste.

### 8.1 Inventaire et propriétaires

| Clé | Couvre | Politique fixée par |
|---|---|---|
| `logs` | groupes de journaux applicatifs **et** journal d'audit d'effacement | `V2-LLD-001 §12.1.1` |
| `data` | DynamoDB `documents`, `ledger`, `users`, compteurs de quota ; S3 `documents` | §8.2 |
| `secrets` | Secrets Manager | §8.3 |
| `tfstate` | S3 de l'état Terraform | `V2-LLD-008` |

**Une clé par domaine d'accès, jamais une clé par ressource ni par sujet.** Le critère est la
population de principals qui doit pouvoir déchiffrer. `documents` DynamoDB et S3 `documents` sont
lus par le même rôle dans la même opération : les séparer produirait deux politiques à maintenir
identiques, donc deux occasions de divergence, sans réduire aucune surface.

Le chiffrement par sujet — une clé par utilisateur, dont la destruction vaudrait effacement — a été
écarté par `V2-ADR-015`, et `V2-ADR-017` a étendu ce raisonnement au chiffrement par niveau de
classification. Aucune des deux décisions n'est rouverte ici.

### 8.2 Politique de la clé `data`

La politique est construite sur trois principes, et chacun ferme une erreur observée en pratique.

**Le compte racine conserve `kms:*`.** Une clé dont la politique ne laisse aucun administrateur
devient inadministrable de façon irréversible — il n'existe aucun mécanisme d'escalade. C'est une
condition d'existence, pas une permission accordée.

**Les rôles applicatifs n'obtiennent que ce qu'ils utilisent**, et sous condition de service :

| Principal | Actions | Condition |
|---|---|---|
| `ecs-task-role-fastapi` | `Decrypt`, `GenerateDataKey` | `kms:ViaService` limité à `dynamodb` et `s3` de la région |
| Rôle de sauvegarde | `Decrypt`, `CreateGrant` | `kms:GrantIsForAWSResource` |
| Rôle CI/CD | **aucune action de données** | — |

La condition `kms:ViaService` est ce qui empêche qu'un rôle applicatif compromis déchiffre autre
chose que ce que le service pour lequel il a été conçu lui présente. Sans elle, `kms:Decrypt` est un
droit de déchiffrement universel sur tout ce que cette clé protège.

**Aucun principal n'a `kms:*`, et aucun n'a `kms:ScheduleKeyDeletion`** hors du compte racine. La
suppression d'une clé rend illisibles les données qu'elle protège — c'est une opération dont le
rollback n'existe pas passé la fenêtre d'attente.

| Paramètre | Valeur | Motif |
|---|---|---|
| Rotation automatique | activée | rotation annuelle du matériau, transparente |
| Fenêtre d'attente de suppression | **30 jours** (maximum) | la seule protection contre une suppression accidentelle |
| Alias | `alias/${env}-secure-agentcore-data` | — |

`terraform_plan_guard.py` traite la suppression ou la désactivation de cette clé comme une
destruction de table portant des données (§17.3), au même titre que la clé `logs`
(`V2-LLD-001 §12.1.1`).

### 8.3 Politique de la clé `secrets`

Même construction, avec une séparation supplémentaire qui est le point de la clé :

| Principal | Peut | Ne peut pas |
|---|---|---|
| `ecs-task-execution-role` | `Decrypt` via `secretsmanager` | lire les secrets d'une autre application |
| Rôle CI/CD | **écrire** un secret | le déchiffrer |

**Le pipeline écrit les secrets et ne les lit pas.** Un pipeline qui peut lire les secrets de
production est un point de compromission qui donne accès à tout ce qu'ils protègent, et dont les
journaux d'exécution sont conservés. Écrire sans lire est réalisable — `PutSecretValue` n'exige pas
`Decrypt` — et c'est la séparation la plus rentable de cette section.

### 8.4 Ce qui n'a pas de clé dédiée, et pourquoi

| Magasin | Clé | Motif |
|---|---|---|
| `Trips` | clé gérée AWS | continuité V1 (`V2-LLD-006 §11`) ; aucune donnée V2 n'y est ajoutée |
| S3 Vectors | clé du service | `V2-ADR-019` délègue l'indexation à Knowledge Bases ; le passage à une CMK est un item V3 |
| AgentCore Memory | clé du service | le service n'expose pas de configuration de clé en V2 ; l'isolation repose sur le namespace (§3.3) |

Ces trois cas sont des **risques résiduels acceptés et tracés**, non des omissions. Leur revue est
un item de la trajectoire V3 (§19).

---

## 9. Secrets

### 9.1 Inventaire

| Secret | Contenu | Rotation | Consommateur |
|---|---|---|---|
| `${env}/path-verify` | secret de chemin unique (§5) | `path_secret_rotation_days` | CloudFront (origine), FastAPI |
| `${env}/app-config` | paramètres applicatifs sensibles hors identité | manuelle, sur incident | FastAPI |

**Ce qui n'est pas un secret et ne doit pas y être rangé :** `cognito_issuer`,
`cognito_app_client_id`, l'URL du JWKS. Ce sont des valeurs de configuration publiques par
construction — le client applicatif les connaît. Les traiter comme des secrets produirait une
rotation sans objet et une fausse assurance ; elles sont des variables Terraform ordinaires
(`V2-LLD-001 §16.4`).

Aucun secret ne porte de clé d'API ni d'identifiant statique AWS : les accès aux services AWS
passent par les rôles de tâche (`V2-LLD-001 §5`) et le pipeline par OIDC (`V2-LLD-008`).

### 9.2 Injection dans ECS

Les secrets sont injectés par **référence** dans la task definition (bloc `secrets`), jamais par
valeur dans `environment`. La différence n'est pas cosmétique : une valeur placée dans
`environment` apparaît en clair dans la task definition, donc dans `DescribeTaskDefinition`, dans
l'état Terraform et dans tout journal d'audit d'API qui l'enregistre.

Le déchiffrement est effectué par le rôle d'exécution ECS au démarrage de la tâche ; le rôle de
tâche n'a pas besoin de `secretsmanager:GetSecretValue` pour ces valeurs.

---

## 10. Sécurité des uploads

`V2-LLD-002 §3` déclare explicitement que le **mécanisme** d'analyse est possédé par ce LLD et qu'il
n'en définit que le contrat de verdict. Ce paragraphe fournit le mécanisme.

### 10.1 Le contrat consommé

`V2-LLD-002` attend un verdict asynchrone `validated | quarantined` sur un objet déposé au préfixe de
quarantaine, et porte les transitions d'état `documents` associées. Ce contrat est repris tel quel ;
ce LLD ne le modifie pas.

### 10.2 Les contrôles, et leur ordre

| # | Contrôle | Verdict si échec |
|---|---|---|
| 1 | Taille dans les bornes déclarées | rejeté à l'upload (`V2-LLD-002 §3`), pas de quarantaine |
| 2 | **Type réel** déterminé par signature d'octets, comparé au type déclaré | `quarantined` |
| 3 | Analyse antivirus | `quarantined` sur détection |
| 4 | Conformité structurelle au type reconnu | `quarantined` |

**Le contrôle 2 précède l'analyse, et c'est l'ordre qui compte.** Le type déclaré par le client est
une donnée non fiable comme une autre. Un exécutable renommé en `.pdf` passe tout contrôle qui fait
confiance à l'extension ou à l'en-tête `Content-Type`. Déterminer le type réel avant d'analyser
évite d'appliquer au fichier un analyseur conçu pour un autre format — c'est-à-dire d'obtenir un
verdict `validated` qui n'atteste de rien.

### 10.3 Le mécanisme d'analyse

**Décision : l'analyse est portée par une fonction Lambda déclenchée sur le dépôt S3 en quarantaine,
avec un moteur antivirus embarqué et une base de signatures montée depuis un magasin dédié.**

| Aspect | Décision | Motif |
|---|---|---|
| Déclenchement | notification S3 sur le préfixe de quarantaine | l'analyse est un événement, pas un service à dimensionner |
| Compute | Lambda | l'analyse est ponctuelle et rafalée ; un service ECS always-on serait facturé pour attendre |
| Réseau | dans le VPC, subnets privés | l'analyse lit des documents ; elle est dans le même périmètre qu'eux |
| Egress | **aucun vers internet** hors mise à jour des signatures | voir ci-dessous |
| Base de signatures | rafraîchie par un déclenchement planifié distinct, stockée dans un magasin dédié | l'analyse ne sort jamais du VPC |
| Verdict | écrit via l'API FastAPI de verdict, jamais directement dans `documents` | la transition d'état appartient à `V2-LLD-002` |

**La séparation entre l'analyse et la mise à jour des signatures est le point de conception.** Un
analyseur qui télécharge ses signatures à la volée a besoin d'un accès sortant à internet, dans le
composant même qui manipule les fichiers hostiles. Deux déclenchements distincts — l'un analyse sans
egress, l'autre met à jour sans toucher aux documents — retirent cette conjonction. C'est la même
règle que l'exception d'egress de `V2-LLD-001 §12.2` : chaque sortie est nommée et attribuée à un
composant précis.

**Le verdict passe par l'API, jamais par une écriture directe.** Donner à l'analyseur le droit
d'écrire dans `documents` lui donnerait le pouvoir de faire passer un document en `validated`. Le
verdict est une entrée d'une transition qui appartient à `V2-LLD-002` ; l'analyseur le propose, il ne
l'applique pas.

### 10.4 Quarantaine — ce qu'elle garantit

`V2-ADR-017` traite un document `quarantined` **comme `restricted`** : ni lisible, ni indexable,
quelle que soit sa classification déclarée, et non reclassifiable dans un sens comme dans l'autre.
Ce LLD ajoute que ces propriétés valent aussi pour un document simplement **en attente de verdict** :
un document reste en `uploaded` jusqu'à réception, et un document en `uploaded` n'est pas plus
lisible qu'un document `quarantined`.

Sans cette précision, la fenêtre entre le dépôt et le verdict serait une fenêtre de lecture d'un
contenu non validé — et cette fenêtre est précisément celle que l'analyse asynchrone crée.

**Panne de l'analyseur.** Aucun verdict n'arrive ; les documents restent en `uploaded`, donc non
lisibles et non indexés. La panne dégrade la fonctionnalité et **ne dégrade pas la posture**. C'est
le comportement voulu, et il est prouvé (§16).

---

## 11. Threat model

### 11.1 Méthode et portée

Le modèle porte sur les surfaces de la V2 telles que les LLD les décrivent, et sur les seuls contrôles
qui existent dans le corpus. Il ne postule aucune capacité non décidée. Chaque ligne nomme le contrôle
et le document qui le porte ; une ligne sans contrôle est un risque résiduel, et §11.6 les rassemble.

### 11.2 Surfaces et menaces

| # | Surface | Menace | Contrôle | Porté par |
|---|---|---|---|---|
| T1 | Ingress public | Usurpation d'identité par en-tête forgé | aucun en-tête d'identité n'est lu ; la signature est vérifiée | `V2-ADR-020`, §3.5 |
| T2 | Ingress public | Contournement du WAF par appel direct à la passerelle | secret de chemin, deux points de vérification | §5.2 |
| T3 | Ingress public | Rejeu d'un jeton volé | durée de vie 60 min ; révocation effective à 30 s par le registre | §2.3, §3.4 |
| T4 | Ingress public | Bourrage d'identifiants sur Cognito | rate-based dédié aux routes d'authentification ; `PreventUserExistenceErrors` ; auto-inscription fermée | §6.4, §2.1 |
| T5 | API applicative | Escalade horizontale par injection de `tenantId` | champs refusés en 400 ; tenant résolu par le registre | §4.1, §3.4 |
| T6 | API applicative | Accès cross-tenant à un document | évaluation §4.2 étapes 4–6 ; filtre tenant obligatoire au magasin | §4.2, §4.8 |
| T7 | API applicative | Sonde d'existence de ressources | 403 et 404 indistinguables ; aucun détail en corps de réponse | §4.3, §4.5 |
| T8 | API applicative | Épuisement du quota Bedrock par une identité | admission sur la simultanéité, règlement en tokens | §7 |
| T9 | Chaîne agentique | **Injection indirecte par document** | la confirmation est hors du chemin du modèle | §11.3 |
| T10 | Chaîne agentique | Empoisonnement du corpus | §11.4 | §11.4 |
| T11 | Chaîne agentique | Exfiltration par tool | identité injectée côté serveur ; egress contrôlé | §11.5 |
| T12 | Upload | Fichier hostile déposé | type réel avant analyse ; quarantaine fermée en lecture | §10 |
| T13 | Upload | Contenu non validé lu pendant la fenêtre d'analyse | `uploaded` non lisible | §10.4 |
| T14 | Données au repos | Déchiffrement par un rôle compromis | `kms:ViaService` ; aucun `kms:*` | §8.2 |
| T15 | Données au repos | Suppression de clé | fenêtre 30 jours ; garde de plan | §8.2, §17.3 |
| T16 | Journaux | Fuite de `Authorization` | interdit à toutes les couches, WAF compris | §12.4, §6.6 |
| T17 | Conformité | Effacement contourné par restauration PITR | rejeu obligatoire ; journal hors périmètre PITR | §12.3 |
| T18 | Conformité | Journal d'audit d'effacement altéré ou perdu | magasin append-only, rétention gardée | §12.2 |
| T19 | Exploitation | Compromission du pipeline | le pipeline écrit les secrets sans les lire | §8.3 |
| T20 | Exploitation | Action d'administration irréversible non voulue | scope `platform:admin` avec second facteur | §4.7 |

### 11.3 Injection indirecte — ce qui est fermé et ce qui ne l'est pas

C'est la menace la plus caractéristique du système, et le corpus la traite par construction plutôt
que par filtrage.

Un document ingéré peut porter des instructions que le modèle suivra. `V2-ADR-002` traite le contenu
documentaire comme non fiable, `V2-LLD-002 §13.3` balise le `retrievalContext` comme contexte et non
comme prompt système. Ces mesures réduisent la probabilité ; elles ne l'annulent pas, et aucune
mesure de filtrage ne le peut — un filtre porte sur la forme d'un appel, jamais sur son origine.

Ce qui l'annule est structurel :

```text
injection réussie ──► le modèle fait MATÉRIALISER une commande      possible
                 ──► la commande est PRÉSENTÉE à l'utilisateur      visible
                 ──► la CONFIRMATION arrive par un canal            impossible pour le modèle
                     authentifié auquel le modèle n'accède pas
                 ──► effet de bord                                  jamais sans confirmation
```

**Une injection réussie produit au pire une proposition visible, jamais un effet de bord**
(`V2-ADR-014`). Ce LLD porte la part qui rend cette propriété vraie : l'endpoint de confirmation
n'est atteignable par aucun chemin dont le modèle dispose (§4.6), et le nombre de commandes `pending`
est borné (§7.2) — sans quoi une injection produirait un flot de propositions.

**La propriété est conditionnelle et la condition doit être tenue.** Elle suppose que la
matérialisation reste sans effet observable. Un tool de proposition qui réserverait une ressource,
enverrait une notification ou consommerait un quota externe la romprait. C'est une règle de
conception des tools, vérifiable en revue (`V2-LLD-004`), pas une propriété acquise.

**Ce qui reste ouvert.** L'injection peut faire produire au modèle une réponse trompeuse, faire
citer un document hors de propos, ou consommer du budget. Aucun de ces effets n'est un effet de bord,
et aucun n'est fermé par les contrôles ci-dessus.

### 11.4 Empoisonnement du corpus

| Vecteur | Contrôle | Limite |
|---|---|---|
| Document hostile uploadé par un utilisateur légitime | il n'entre que dans le périmètre de son tenant (§4.8) ; le partage n'est pas transitif (§4.4) | un utilisateur peut empoisonner son propre corpus |
| Document hostile injecté par un tiers | l'auto-inscription est fermée (§2.1) ; aucun dépôt anonyme n'existe | — |
| Dérive de qualité non détectée | datasets et non-régression contre baseline versionnée | `V2-ADR-018`, `V2-LLD-002` |

**Le périmètre de l'empoisonnement est celui du tenant, par construction.** Aucun mécanisme du corpus
ne fait entrer un document d'un tenant dans le contexte d'un autre : le filtre tenant est obligatoire
au magasin et la décision est prise sur `documents` (§4.8). Un empoisonnement reste donc borné à
l'organisation qui l'a subi — ce qui ne le rend pas inoffensif, mais le rend non propageable.

### 11.5 Exfiltration

| Chemin | Contrôle | Porté par |
|---|---|---|
| Par un tool sortant | identité injectée côté serveur ; les tools ignorent toute identité produite par le modèle | `V2-ADR-006` |
| Par egress réseau depuis une tâche | subnets privés, VPC endpoints, exceptions d'egress nommées une à une | `V2-LLD-001 §12.2` |
| Par le contenu d'une réponse | le modèle ne reçoit que le `retrievalContext` autorisé (§4.2 étape 7) | `V2-ADR-019` |
| Par URL présignée | liée à un objet, en lecture, durée < fenêtre de révocation | §4.5 |
| **Par requêtes légitimes répétées** | **aucun** — relève de l'audit | §11.6 |

`V2-ADR-016` le dit sans détour : « un appelant autorisé qui interroge massivement ses propres
données reste dans son périmètre `V2-ADR-006` ; la détection relève de l'audit, pas de la
limitation ». Ce LLD ne prétend pas le contraire.

### 11.6 Risques résiduels acceptés

| # | Risque | Pourquoi il n'est pas traité | Traçabilité |
|---|---|---|---|
| R1 | Exfiltration par un appelant autorisé | la détection comportementale suppose une gouvernance et un volume que le projet n'a pas | `V2-ADR-016` périmètre exclu |
| R2 | Jeton d'accès valide jusqu'à 60 min après compromission | Cognito ne révoque pas un jeton d'accès émis ; le registre borne l'autorisation à 30 s, pas l'authentification | §2.4 |
| R3 | Empoisonnement du corpus d'un tenant par l'un de ses membres | l'utilisateur agit dans son propre périmètre | §11.4 |
| R4 | S3 Vectors et Memory sans CMK dédiée | les services ne l'exposent pas en V2 | §8.4, item V3 |
| R5 | Injection produisant une réponse trompeuse sans effet de bord | aucun filtre ne distingue une instruction d'un contenu | §11.3 |
| R6 | Protection DDoS limitée à Shield Standard | Shield Advanced est un engagement contractuel | `V2-ADR-016` périmètre exclu |
| R7 | Threat protection Cognito en mode `AUDIT` | le mode `ENFORCED` est facturé par utilisateur actif | §2.1, item V3 |

Ces sept risques sont **acceptés et tracés**, non ignorés. Leur revue est une entrée de la gate
(§18).

---

## 12. Audit et journalisation

### 12.1 Ce qui est audité

| Événement | Contenu | Destination |
|---|---|---|
| Décision d'autorisation refusée | `subjectId`, code de politique (§4.3), ressource pseudonymisée | journaux applicatifs |
| Octroi et révocation de partage | `subjectId` acteur et bénéficiaire, `documentId` | journaux applicatifs |
| Reclassification | sens, niveaux, `documentId` | journaux applicatifs |
| Confirmation de commande | `commandId`, `subjectId` | journaux applicatifs |
| Action `platform:admin` | action, `subjectId`, cible pseudonymisée | journaux applicatifs |
| **Effacement d'un utilisateur** | tel que fixé par `V2-LLD-006 §8.6` | **journal d'audit d'effacement** (§12.2) |

`V2-ADR-006` exige que les décisions d'autorisation soient journalisées « avec code de politique et
ressource pseudonymisée ». Les identifiants apparaissent sous `subjectId` (§3.1), jamais sous
`actorId`.

**La rétention des traces est distincte de celle des documents** (`V2-ADR-006`). Les valeurs sont
portées par `V2-LLD-006 §10` et `V2-LLD-007` ; ce LLD n'en fixe qu'une, celle du journal d'effacement,
parce qu'elle est une contrainte de sécurité et non un paramètre d'exploitation.

### 12.2 Journal d'audit d'effacement

`V2-ADR-015` en fait une précondition **bloquante sans repli** (P3, §1.3). `V2-LLD-006 §8.6` crée le
groupe de journaux et son schéma ; `V2-LLD-001 §12.1.1` fixe la politique de clé. Ce LLD porte les
trois propriétés qui en font une preuve.

| Propriété | Exigence | Vérification |
|---|---|---|
| **Indépendance** | le journal est hors du périmètre de restauration : une restauration PITR ne le ramène pas en arrière | garde de plan (§17.3) |
| **Rétention** | `≥` fenêtre PITR maximale des magasins restaurables | garde de plan numérique, `V2-LLD-006 §16.2` |
| **Immuabilité** | append-only ; aucun principal applicatif ne peut supprimer ni modifier une entrée | politique de clé et IAM (§8.1) |

**Pourquoi l'indépendance est la propriété décisive.** Si le journal vivait dans le périmètre
restauré, une restauration à un instant antérieur à un effacement ramènerait à la fois les données
effacées **et** l'oubli de leur effacement. Le rejeu (§12.3) n'aurait plus de source, et la
restauration produirait une résurrection silencieuse — le mode d'échec le moins détectable de tout le
corpus, puisque rien n'en porterait la trace.

**Lecture.** Seul `platform:admin` (§4.7) lit ce journal. Il contient la liste des personnes ayant
exercé un droit à l'effacement : sa lecture doit être aussi contrôlée que celle de `users`
(`V2-LLD-006 §11`).

### 12.3 Rejeu après restauration

`V2-ADR-015` impose que toute restauration soit suivie du rejeu des effacements postérieurs à son
instant cible. `V2-LLD-006 §13.5` en porte la procédure. Ce LLD porte les deux contrôles
d'autorisation qui l'encadrent.

**Garde préalable.** Une restauration dont le journal d'audit n'existe pas, n'est pas indépendant du
périmètre restauré, ou dont la rétention ne couvre pas la fenêtre, est **interdite** — pas dégradée
(`V2-LLD-006 §13.5.3`). Ce LLD confirme la qualification : c'est un refus, pas un avertissement.

**Autorisation.** Le déclenchement du rejeu exige `platform:admin` avec second facteur (§4.7). Le
rejeu supprime des données dans une table qui vient d'être restaurée : c'est l'action la plus
destructrice du système, et la seule dont l'omission est également destructrice — d'un droit, cette
fois.

### 12.4 Valeurs jamais journalisées

`V2-ADR-008` interdit tout JWT en clair ; `V2-ADR-020` a nommé `Authorization` ; `V2-LLD-001 §12.4`
porte la liste au niveau plateforme. Ce paragraphe la porte au niveau transverse, avec les deux
couches que la liste plateforme ne couvre pas.

| Valeur | Interdit à |
|---|---|
| En-tête `Authorization`, sous toute forme, entière ou tronquée | application, ALB, API Gateway (`dataTraceEnabled = false`), **WAF** (§6.6) |
| En-tête de secret de chemin (§5) | mêmes couches, **WAF compris** |
| Tout JWT, tout jeton de rafraîchissement | toutes couches |
| `actorId` brut | journaux, métriques, traces — `subjectId` à la place (§3.1) |
| Prompt brut, réponse brute, contenu documentaire | toutes couches (`V2-ADR-008`) |
| Contenu d'une commande | journaux — `commandId` seul |

**Les journaux d'erreur sont explicitement inclus.** C'est le lieu habituel de la fuite : un
gestionnaire d'exception qui journalise la requête entière pour faciliter le diagnostic contourne
toute politique de redaction appliquée au chemin nominal. `V2-ADR-020` en fait une preuve nommée, et
l'échantillon de vérification doit comporter des journaux d'erreur (§16).

**Le WAF est la seconde couche facile à manquer** (§6.6) : il journalise les en-têtes qu'il inspecte,
et sa configuration de redaction est distincte de celle de l'application.

---

## 13. Résilience des contrôles

Chaque contrôle a un comportement en panne décidé, et la règle qui les départage est celle de
`V2-ADR-016` : un contrôle d'autorisation qui échoue refuse ; un contrôle d'équité qui échoue
dégrade.

| Contrôle en panne | Comportement | Nature | Alerte |
|---|---|---|---|
| JWKS au-delà de la tolérance | **refuse** | autorisation | incident de sécurité |
| JWKS en deçà de la tolérance | sert depuis le cache | — | aucune |
| Registre d'autorisation (§3.4) | **refuse** | autorisation | incident de disponibilité d'un contrôle |
| Magasin de compteurs (§7.4) | **dégrade** — repli sur le plafond d'étape | équité | perte de contrôle d'équité |
| Analyseur d'uploads (§10.4) | dégrade — documents en `uploaded`, non lisibles | — | fonctionnelle |
| Lecture de `documents` au filtrage | **refuse** le candidat, sans échouer la requête | autorisation | compteur `filtered_out` |
| WAF indisponible | dégrade — le trafic passe | — | opérationnelle |
| Secret de chemin illisible au démarrage | **la tâche ne démarre pas** | autorisation | déploiement |

**La dernière ligne mérite d'être explicitée.** Une tâche qui démarrerait sans pouvoir vérifier le
secret de chemin servirait du trafic hors chemin unique sans le savoir. Le refus de démarrage est
préféré : il est visible au déploiement, là où le mode dégradé serait invisible en production.

---

## 14. Configuration par environnement

| Contrôle | `test` | Production (référence) |
|---|---|---|
| Threat protection Cognito | `AUDIT` | `ENFORCED` |
| Règles WAF managées | `Count` puis `Block` (§6.5) | `Block` |
| MFA `platform:admin` | exigé | exigé |
| Auto-inscription | fermée | fermée |
| `authz_registry_cache_ttl_seconds` | 30 | 30 |
| Rotation du secret de chemin | activée | activée |

Aucun contrôle de sécurité n'est désactivé en `test`. Les seules différences sont des modes
d'observation (`AUDIT`, `Count`) et non des exemptions : un environnement de test dont la posture
diffère de la production ne teste pas la production.

---

## 15. Observabilité de sécurité

Les séries suivantes sont distinctes et ne doivent jamais être agrégées — leur confusion est
exactement ce que `V2-ADR-016` précondition 5 cherche à éviter.

| Série | Source | Ce qu'un pic signifie |
|---|---|---|
| `path_not_allowed` | §4.3 | tentative de contournement du WAF |
| `token_invalid` | §4.3 | erreur client, ou sondage |
| `jwks_unavailable` | §4.3 | **incident de sécurité** |
| `authz_registry_unavailable` | §4.3 | contrôle d'autorisation indisponible |
| `quota_exceeded` | §4.3 | perte d'équité |
| `forbidden` | §4.3 | sonde d'autorisation, ou régression de droits |
| `field_not_allowed` | §4.3 | erreur de contrat, ou injection d'identité |
| `ThrottlingException` Bedrock | `V2-ADR-012` | contention de compte, cause externe possible |
| Correspondances WAF par règle | §6 | — |
| `filtered_out` | `V2-LLD-002 §6.2.1` | faux négatifs de reclassification, ou surfiltrage |

Les attributs de corrélation portent `subjectId`, jamais `actorId` (§12.4). L'instrumentation
elle-même relève de `V2-LLD-007`.

---

## 16. Tests et preuves

| # | Preuve | Origine |
|---|---|---|
| S1 | Un en-tête de claims forgé — y compris `X-Amzn-Oidc-Data` — n'a aucun effet, démontré par l'**absence de lecture d'en-tête d'identité** dans le chemin de résolution | `V2-ADR-020` |
| S2 | Un jeton de signature valide mais d'`aud`, d'`iss` incorrect ou expiré est refusé par FastAPI **avec l'authorizer de la passerelle désactivé** | `V2-ADR-020` |
| S3 | Une requête forgée injectée directement sur l'ALB ne produit aucune identité | `V2-ADR-020` |
| S4 | Un jeton signé en `HS256` avec la clé publique du JWKS est refusé | §3.5 |
| S5 | Un `sub` authentifié mais absent du registre n'obtient aucune identité | §3.4 |
| S6 | Un compte passé en `suspended` est refusé **au plus tard** `authz_registry_cache_ttl_seconds` après, avec un jeton valide | §3.7 |
| S7 | Deux couples `(tenantId, actorId)` distincts produisent deux namespaces distincts ; le namespace fait 64 caractères | §3.3 |
| S8 | Une requête émise directement sur le point de terminaison API Gateway, sans le secret de chemin, est refusée | `V2-ADR-016` |
| S9 | La même requête est refusée **avec la règle WAF du stage désactivée** — la vérification applicative suffit | §5.2 |
| S10 | Pendant la fenêtre de recouvrement, les deux valeurs du secret sont acceptées ; après, l'ancienne est refusée | §5.4 |
| S11 | Une identité atteignant sa limite de simultanéité reçoit `quota_exceeded` **avant toute invocation Runtime**, vérifié par l'absence d'appel Bedrock | `V2-ADR-016` |
| S12 | Un flux abandonné par déconnexion continue de compter jusqu'à son terme ou son annulation | `V2-ADR-016` |
| S13 | Une invocation dont la tâche est tuée cesse de compter à l'échéance, sans intervention | §7.3 |
| S14 | L'indisponibilité du magasin de compteurs ne refuse pas, alerte, et laisse le plafond d'étape appliqué ; idem sur dépassement du SLA | `V2-ADR-016` |
| S15 | **Preuve d'équité** : sous une charge saturant `plafondPlateforme × tauxSursouscription`, une seconde identité conserve son temps de première réponse ; la même charge, quotas désactivés, la dégrade | `V2-ADR-016` |
| S16 | User A ne lit ni ne modifie les ressources de User B ; Tenant A ne récupère aucun vecteur de Tenant B | `V2-ADR-006` |
| S17 | L'injection de `actorId` ou `tenantId` dans le corps est refusée en 400, code distinct du 403 | §4.1 |
| S18 | Un document `restricted` n'apparaît dans aucun `retrievalContext`, y compris pour son propriétaire, **et** reste lisible par lui en accès direct | `V2-ADR-017` |
| S19 | Un partage explicite sur un document `restricted` n'autorise pas son injection dans un contexte modèle | `V2-ADR-017` |
| S20 | Un bénéficiaire de partage ne peut pas repartager | §4.4 |
| S21 | Une URL présignée est inutilisable hors de sa ressource et de sa durée ; sa durée est inférieure à la fenêtre de révocation | §4.5 |
| S22 | Une confirmation par une identité autre que celle qui a fait matérialiser la commande est refusée, `commandId` valide compris | `V2-ADR-014` |
| S23 | Un corps non vide sur l'endpoint de confirmation est refusé | §4.6 |
| S24 | Une injection documentaire demandant une mutation produit au plus une commande `pending`, aucune confirmation, aucun effet de bord | `V2-ADR-014` |
| S25 | Le nombre de commandes `pending` par identité est borné, la matérialisation refusée au-delà sans effet observable | `V2-ADR-016` |
| S26 | Un exécutable renommé en `.pdf` est mis en quarantaine par le contrôle de type réel, avant analyse | §10.2 |
| S27 | Un document en `uploaded` n'est ni lisible ni indexable | §10.4 |
| S28 | L'analyseur ne dispose d'aucun accès sortant vers internet | §10.3 |
| S29 | Aucun en-tête `Authorization` n'apparaît dans les journaux d'aucune couche, **journaux WAF et journaux d'erreur compris** | `V2-ADR-020`, §6.6 |
| S30 | Aucun jeton Cognito n'atteint Runtime, MCP ou un tool, vérifié par inspection des en-têtes reçus côté Runtime | `V2-ADR-006` |
| S31 | Le contrat Runtime refuse `cognitoToken`, `authorizationHeader`, `actorIdRaw`, `tenantIdRaw` | `runtime-contract.md` §4 |
| S32 | Le rôle CI/CD peut écrire un secret et ne peut pas le déchiffrer | §8.3 |
| S33 | `ecs-task-role-fastapi` ne peut pas déchiffrer hors des services de sa condition `ViaService` | §8.2 |
| S34 | Une restauration dont le journal d'audit d'effacement est absent ou de rétention insuffisante est **refusée**, pas dégradée | `V2-ADR-015` |
| S35 | Le journal d'audit d'effacement n'est pas ramené en arrière par une restauration PITR | §12.2 |
| S36 | Le rejeu exige `platform:admin` avec second facteur ; un `tenant_admin` est refusé | §4.7 |
| S37 | Les refus S1–S36 forment des séries de métriques distinctes selon §15 | `V2-ADR-016`, `V2-ADR-020` |

**S9 est la preuve la plus significative de ce LLD.** Elle démontre que le chemin unique ne dépend
pas de la précondition bloquante P1 — c'est-à-dire que le couplage relevé en §1.7 est effectivement
résolu, et non seulement décrit.

---

## 17. Configuration Terraform

### 17.1 Variables

| Variable | Défaut | Motif |
|---|---|---|
| `cognito_access_token_validity_minutes` | 60 | §2.3 |
| `cognito_id_token_validity_minutes` | 60 | §2.3 |
| `cognito_refresh_token_validity_days` | 30 | §2.3 |
| `cognito_mfa_configuration` | `OPTIONAL` | §2.1 |
| `cognito_threat_protection_mode` | `AUDIT` | §2.1 |
| `authz_registry_cache_ttl_seconds` | **30** | §3.4 — **borne de révocation effective** (§3.7) |
| `path_secret_rotation_days` | 30 | §5.4 |
| `path_secret_overlap_hours` | 24 | §5.4 — fenêtre de recouvrement |
| `waf_count_mode_days` | 14 | §6.5 |
| `waf_auth_rate_limit_per_5min` | *(sans défaut)* | §6.4 règle 2 |
| `waf_global_rate_limit_per_5min` | *(sans défaut)* | §6.4 règle 3 |
| `quota_store_p99_ms` | 10 | §7.4 — SLA au-delà duquel le repli s'applique |
| `quota_inflight_lease_seconds` | 1080 | §7.3 — 15 min + marge |
| `taux_sursouscription` | *(sans défaut)* | `V2-ADR-016`, gardé |
| `plafond_plateforme` | *(sans défaut)* | `V2-ADR-016`, gardé |
| `token_budget_window_days` | *(sans défaut)* | `V2-ADR-016`, gardé |
| `bedrock_servable_concurrency_ssm_param` | *(sans défaut)* | §7.5 — alimenté à la découverte de capacité |
| `erasure_audit_retention_days` | *(sans défaut)* | §12.2, gardé contre la fenêtre PITR |
| `presigned_url_lifetime_seconds` | *(sans défaut)* | §4.5 — durée des URL présignées S3 ; doit satisfaire N8 |

**Les variables sans défaut sont délibérément sans défaut.** `V2-ADR-016` et la Charte §4.2 excluent
qu'un LLD invente des valeurs de politique de service ; une valeur par défaut serait exactement cela,
avec en outre le risque qu'elle soit adoptée sans décision. Leur absence au plan est refusée
(§17.3) : l'exploitant doit choisir, et le plan l'y contraint.

### 17.2 Préconditions non bloquantes

| # | À vérifier | Repli si infirmé |
|---|---|---|
| 1 | Latence P99 de l'opération atomique du magasin de compteurs sous charge | si le SLA n'est pas tenable sur DynamoDB, réévaluer Redis (§7.1) ; la décision de comportement en panne ne change pas |
| 2 | Capacité servable réelle du quota Bedrock du modèle configuré | sans elle, `plafond_plateforme` est une valeur choisie et non bornée ; le plan est refusé (§7.5) |
| 3 | Coût de la vérification de signature sur les routes documentaires | `V2-ADR-020` précondition 4 ; si la latence est visible, elle est un coût accepté, jamais un motif de retirer la vérification |
| 4 | **Attestation d'authentification MFA disponible sur le jeton d'accès Cognito** | repli : client applicatif distinct en MFA obligatoire, réservé à `platform_admin` (§4.7) |
| 5 | Configuration de redaction des journaux WAF sur un en-tête nommé | si elle n'est pas disponible, la journalisation des en-têtes est désactivée entièrement (§6.6) |
| 6 | Notification S3 sur préfixe de quarantaine et exécution Lambda en VPC sans egress | si l'egress est requis par le moteur retenu, changer de moteur, jamais ouvrir l'egress de l'analyseur (§10.3) |

### 17.3 Règles de garde `terraform_plan_guard.py`

Selon les trois modes de contrôle du script : booléen, borne numérique (`V2-LLD-006 §16.2`),
structurel (`V2-LLD-001 §16.6`).

**Booléennes**

| # | Règle | Refus si |
|---|---|---|
| B1 | Auto-inscription Cognito fermée | `AllowAdminCreateUserOnly` absent ou faux |
| B2 | Flux `implicit`, `USER_PASSWORD_AUTH` et `ADMIN_USER_PASSWORD_AUTH` absents du client | l'un est présent |
| B3 | Secret de chemin présent sur l'origine CloudFront et référencé depuis Secrets Manager | absent, ou valeur littérale dans le plan |
| B4 | Rotation du secret de chemin déclarée | absente |
| B5 | Redaction de `Authorization` configurée sur la journalisation WAF | absente |
| B6 | Aucun principal hors compte racine ne porte `kms:*` ni `kms:ScheduleKeyDeletion` | présent |
| B7 | `kms:ViaService` présent sur les autorisations applicatives de la clé `data` | absente |
| B8 | Le journal d'audit d'effacement est hors du périmètre des ressources restaurables | dans le périmètre |
| B9 | Suppression ou désactivation d'une CMK (`data`, `logs`, `secrets`) | présente au plan |

**Bornes numériques**

| # | Invariant | Refus si |
|---|---|---|
| N1 | `erasure_audit_retention_days >= ` fenêtre PITR maximale déclarée | inférieur |
| N2 | `authz_registry_cache_ttl_seconds <= 300` | supérieur — au-delà, la révocation cesse d'être un contrôle |
| N3 | `quota_inflight_lease_seconds >= ` durée maximale d'un flux (`V2-ADR-011`) | inférieur — une fuite serait purgée avant la fin d'une invocation vivante |
| N4 | `path_secret_overlap_hours > 0` | nul — une rotation sans recouvrement produit une indisponibilité |
| N5 | `somme(quotaIdentité) / plafond_plateforme == taux_sursouscription` déclaré | non déclaré ou incohérent |
| N6 | `plafond_plateforme <= ` capacité servable (SSM, §7.5) | supérieur, ou paramètre SSM absent ou nul |
| N7 | `token_budget_window_days` déclaré | absent |
| N8 | `presigned_url_lifetime_seconds < authz_registry_cache_ttl_seconds` | supérieur ou égal — une URL présignée ne doit pas survivre à la borne de révocation |

**Structurelle**

| # | Règle | Refus si |
|---|---|---|
| X1 | Toute variable sans défaut de §17.1 est valorisée au plan | l'une est absente |

---

## 18. Critères de sortie

- [x] Les trois écarts de §1.7 sont corrigés dans `HLD §7.5`, `capability-allocation-matrix.md`
      Domaine 1, `V2-LLD-001 §7.1.3` et `V2-LLD-003 §2.5` — appliqué dans le même lot
- [ ] P1 (attachement WAF) vérifiée nominativement sur le service — ou §5.2 démontré suffisant sans elle
- [ ] P2 (chemin unique) réalisée et prouvée par S8 **et** S9
- [ ] P3 (journal d'audit indépendant) satisfaite — sans quoi la restauration reste interdite
- [ ] Les six préconditions non bloquantes de §17.2 sont instruites, avec repli tracé
- [ ] Les preuves S1 à S37 sont exécutées et conservées
- [ ] Les sept risques résiduels de §11.6 sont revus et acceptés explicitement
- [ ] Toutes les variables sans défaut de §17.1 sont valorisées
- [ ] `V2-LLD-004` (contrat des tools) et `V2-LLD-010` (geste de confirmation) sont alignés sur §4.6

## 19. Trajectoire V2 → V3

| Sujet | V2 | V3 |
|---|---|---|
| Threat protection Cognito | `AUDIT` | `ENFORCED`, après chiffrage du coût par utilisateur actif (R7) |
| Bot Control WAF | non activé | à instruire après observation du trafic réel |
| Règles WAF propres | cinq règles (§6.4) | enrichies des signatures dérivées des incidents observés |
| CMK S3 Vectors et Memory | clé de service (R4) | CMK dédiée dès que les services l'exposent |
| Chemin unique | secret partagé, deux points | origine privée si CloudFront la rend disponible pour API Gateway |
| Règlement en tokens | fin d'invocation | imputation par tour, sous réserve du couplage SSE à décider dans `V2-ADR-011` |
| Détection d'exfiltration | aucune (R1) | suppose un volume et une gouvernance absents du périmètre |
| Partage | par document, non transitif | délégation d'ownership si un besoin la justifie — nouvel ADR |
