# V2-LLD-006 — Données, mémoire, rétention et restauration

- **Version :** 0.5
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§9, §14)
- **ADR de référence :** `V2-ADR-003`, `V2-ADR-004`, `V2-ADR-006`, `V2-ADR-010`, `V2-ADR-013`,
  `V2-ADR-014`, `V2-ADR-015`, `V2-ADR-017`, `V2-ADR-019`
- **Gate :** V2-G2

> **Révision v0.2 (revue PR #35, bloquants/majeurs) :** les scripts d'exploitation référencés
> (`check_dv_consistency.py`, `run_rag_eval.py`) sont désormais explicitement marqués **artefacts
> planifiés** avec leur contrat d'entrée/sortie (§16.3), et non des outils existants. Aucun code
> n'est créé avant l'approbation des LLD (G2).
>
> **Révision v0.3 (revue PR #35, observations) :** limite du GSI `by-tenant` documentée avec
> évolution compatible (§4.2) ; prérequis de conception rendant la bascule Terraform de restauration
> réellement exécutable — noms de tables en variables + outputs + vérification (§13.1.1).
>
> **Révision v0.4 (alignement `V2-ADR-013`, `V2-ADR-015`, `V2-ADR-017`) :** les trois ADR que la
> v0.3 traitait comme « au backlog » sont désormais `Accepted`. Ce LLD ne fixe plus de contrats
> provisoires en leur nom : il applique leurs décisions. Les seize passages nommés dans leurs tables
> « Écarts à corriger » sont traités. Changements structurants : `embeddingSpaceId` remplace
> `embeddingModelId`/`embeddingVersion` et une période de grâce d'index est fixée (§4.3, §14.5) ; la
> mémoire longue durée devient une donnée personnelle effacée et vérifiée, l'effacement gagne une
> fenêtre résiduelle déclarée `erasureDurableAt`, un journal d'audit hors périmètre PITR et une
> obligation de rejeu après restauration (§2, §6.2, §8, §9, §13.5) ; la classification documentaire
> reçoit son domaine fermé, son défaut et le préfixe `restricted/` hors data source KB (§2, §4.3,
> §7).
>
> **Révision v0.5 (écarts 1 et 2 relevés par `V2-LLD-004 §1.7`) :** ce LLD **possède désormais le
> magasin de commandes** de `V2-ADR-014`. La v0.4 renvoyait cette réalisation à `V2-LLD-004` et
> `V2-LLD-005`, lesquels la renvoyaient ici : une boucle de délégation ne produit pas de
> propriétaire, et l'objet le plus critique de l'ADR — celui qui porte l'autorisation de toute
> action mutante — n'était décrit nulle part. L'arbitrage étant déjà rendu par l'ADR, le §5.3 fixe
> la table `${env}-commands`, ses clés, son GSI `by-operation`, ses attributs, ses trois durées et
> la contrainte de colocalisation transactionnelle. Corollaire (écart 2) : les mutations `Trips`
> **quittent la portée du ledger d'idempotence** (§5.1, §5.2), que `V2-ADR-014` réserve aux
> opérations sans commande — les y maintenir produisait deux enregistrements pour la même mutation,
> dont un seul lu.

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD/Charte | Libellé |
|---|---|
| HLD §9 | Modèle de données V2, versioning S3, table `documents`, cohérence documents/vecteurs/métadonnées |
| HLD §14 | Sauvegarde, restauration, RTO/RPO, cohérence de restauration |
| Charte §6 Sécurité | Chiffrement au repos, secrets dans Secrets Manager, isolation par tenant |
| Charte §6 Résilience | Sauvegarde et restauration testées, reprise idempotente |
| Charte §8 DoD | Tests de restauration passés, réhydratation S3 Vectors documentée |
| ADR-010 | RTO/RPO par catégorie, réhydratation S3V par reconstruction depuis source, cohérence PITR + versioning S3 |
| ADR-006 | Isolation par tenant conservée en restauration ; suppression coordonnée = restauration miroir |
| ADR-019 | Réhydratation S3V en V2 = resynchronisation KB (pas de pipeline SQS+ECS provisionné) |
| ADR-013 | Un index porte un et un seul `embeddingSpaceId`, immuable ; une reconstruction se fait dans l'espace déclaré par l'index, jamais dans celui de la configuration courante ; période de grâce de l'index précédent après bascule |
| ADR-015 | Effacement logique immédiat + fenêtre résiduelle déclarée (`erasureDurableAt`) ; mémoire longue durée = donnée personnelle effacée et vérifiée ; journal d'audit hors périmètre PITR ; rejeu des effacements après restauration |
| ADR-017 | Classification documentaire : domaine fermé (`internal`, `confidential`, `restricted`), défaut `confidential`, préfixe `restricted/` hors data source KB, rétention indépendante de la classification |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-003 | Schéma table `documents` (`PK = tenantId#documentId`, `SK = version`), attributs, GSI `by-tenant`, cycle de vie du `status` |
| V2-ADR-004 | Pipeline d'ingestion SQS + worker ECS = **cible V3 uniquement** ; en V2, la réhydratation utilise KB `StartIngestionJob` |
| V2-ADR-006 | Métadonnées obligatoires (`tenantId`, `documentId`, `version`, `status`) ; isolation préservée en restauration ; suppression coordonnée S3 + S3V + DynamoDB + Memory |
| V2-ADR-010 | RTO/RPO par catégorie ; option B (réhydratation applicative depuis source) ; cohérence de restauration ; DR drills trimestriels ; `terraform_plan_guard.py` étendu |
| V2-ADR-019 | En V2, la réhydratation S3V s'exécute par `StartIngestionJob` KB (pas par le pipeline SQS+ECS différé) ; les preuves de non-régression restent identiques |
| V2-ADR-013 | `embeddingSpaceId` est l'unité de versionnement, opaque et immuable par index ; migration par index parallèle et bascule de pointeur ; période de grâce de l'index précédent (§14.5) ; une restauration reconstruit dans l'espace déclaré par l'index restauré |
| V2-ADR-015 | `erasureDurableAt` et `residualWindowDays` ; suppression Memory explicite et vérifiée, bloquante ; journal d'audit d'effacement append-only hors périmètre PITR ; rejeu obligatoire après restauration ; `erasure_sla_days` et deux règles de borne du guard |
| V2-ADR-017 | Domaine fermé de `classification`, défaut `confidential`, deux régimes de reclassification, préfixe `restricted/` hors data source KB, tombstone conservant la classification, rétention indépendante de la classification |
| V2-ADR-014 | **Magasin de commandes** : table, clés, attributs, les deux fenêtres d'expiration et la rétention de l'état `executed` (§5.3). Le contrat du tool et les invariants du magasin appartiennent à `V2-LLD-004 §6.1`, la part autorisation de la confirmation à `V2-LLD-005 §4.6` ; ce LLD réalise le magasin que ces deux documents consomment. Une demande d'effacement (§8.4) et une reclassification assouplissante (§4.3.2) sont des actions mutantes qui en relèvent |

### 1.3 Préconditions bloquantes héritées des ADR

Ces décisions sont prises ; leur **activation** dépend de faits à établir avant implémentation. La
distinction est celle de `V2-ADR-013` et `V2-ADR-015` : ce ne sont pas des questions ouvertes de
conception, mais des vérifications sur le service.

| # | Précondition | Origine | Conséquence si non satisfaite |
|---|---|---|---|
| P1 | Existence d'une opération de suppression des enregistrements longue durée d'un namespace Memory, et d'une relecture permettant de vérifier l'absence | `V2-ADR-015` §Préconditions 1 | Bascule sur l'option C de `V2-ADR-015` : les préférences quittent Memory pour une table DynamoDB — amendement CAM Domaine 6 et `V2-ADR-002` |
| P2 | Existence d'une durée d'expiration configurable sur les événements de session Memory, et valeur maximale admise | `V2-ADR-015` §Préconditions 2 | Même repli que P1 |
| P3 | Un magasin append-only, hors du périmètre des restaurations de tables, retenu au moins aussi longtemps que la fenêtre résiduelle, peut porter le journal d'effacement | `V2-ADR-015` §Préconditions 3 | **Aucun repli.** Une restauration PITR est alors traitée comme **interdite**, non comme dégradée (§13.5.3) |
| P4 | Valeur effective et configurabilité de la fenêtre PITR DynamoDB | `V2-ADR-015` §Préconditions 4 | `residualWindowDays` n'est pas calculable ; aucun délai d'effacement n'est annonçable |
| P5 | La séquence de suppression S3 retire chaque version et ne pose pas de marqueur de suppression | `V2-ADR-015` §Préconditions 5 | S3 constitue un résidu de 90 jours (§10), supérieur à la fenêtre déclarée : la fenêtre résiduelle est fausse |
| P6 | Immuabilité de la dimension et de la métrique d'un index S3 Vectors ; immuabilité du modèle d'embedding d'une base de connaissances | `V2-ADR-013` §Préconditions | La règle « un index, un espace » n'est pas garantie par le service et repose sur la seule discipline de configuration |

**Aucune de ces préconditions n'est levée à ce stade.** Tant qu'elles ne le sont pas :

- aucune stratégie de mémoire longue durée n'est activée en V2 (règle fail-closed de
  `V2-ADR-015` : *Memory ne peut contenir une donnée personnelle que si sa suppression est
  prouvée*) ;
- aucune migration d'espace d'embedding n'est autorisée — la configuration reste celle de
  `V2-LLD-002` §5.2 ;
- aucune valeur n'est annoncée pour `erasure_sla_days`.

### 1.4 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-001, V2-ADR-005, V2-ADR-007, V2-ADR-008, V2-ADR-009, V2-ADR-011, V2-ADR-012, V2-ADR-016, V2-ADR-018 | Ingress, agents, plateforme, observabilité, CI/CD, streaming, modèles de génération, frontend et évaluation RAG : consommés en tant que contexte mais aucune décision de données ne relève de ce LLD |
| V2-ADR-002 | Non applicable **sauf** par le repli conditionnel de `V2-ADR-015` : si la précondition P1 ou P2 échoue, le déplacement des préférences hors de Memory amende la capacité `Memory Persistence` allouée à Runtime par la CAM, donc `V2-ADR-002`. Ce chemin est identifié, pas emprunté |

### 1.5 Périmètre et exclusions

**Inclus (V2) :** modèles DynamoDB (table `Trips` V1 conservée, table `documents` V2 nouvelle,
ledger d'idempotence, `users`), TTL et rétention, S3 buckets (source documents, frontend,
artefacts), S3 Vectors comme état dérivé et son espace d'embedding, AgentCore Memory sous ses deux
natures (session et longue durée), chiffrement au repos, PITR et versioning, suppression
documentaire et effacement utilisateur avec fenêtre résiduelle déclarée, journal d'audit
d'effacement, restauration et réhydratation (via KB en V2), rejeu des effacements après
restauration, cohérence source/métadonnées/index, contrôles Terraform, runbooks.

**Exclus (autres LLD) :** parcours de retrieval et adapter magasin vectoriel (`V2-LLD-002`),
authentification et threat model (`V2-LLD-005`), instrumentation OpenTelemetry (`V2-LLD-007`),
plateforme ECS et VPC (`V2-LLD-001`).

**Exclus (différé cible V3) :** pipeline applicatif d'ingestion (SQS + worker ECS de `V2-ADR-004`),
saga applicative de suppression coordonnée sur trois magasins, jobs de migration d'embeddings —
tous conservés comme cible V3 (`V2-ADR-019`).

**Exclus (hors périmètre projet) :** réplication cross-région S3, DynamoDB Global Tables, réplication
AZ-croisée forcée au-delà du multi-AZ natif (`V2-ADR-010` §RTO/RPO).

## 2. Catégories de données et propriétaires

Toute donnée V2 relève d'exactement une catégorie ci-dessous. La catégorie détermine le magasin, le
mécanisme de sauvegarde, la stratégie de suppression et le RTO/RPO applicable.

| Catégorie | Exemple | Magasin | Sauvegarde | Cycle de vie | Sensibilité |
|---|---|---|---|---|---|
| Métier transactionnel | `Trips` (V1, conservée) | DynamoDB | **PITR obligatoire** | TTL applicatif optionnel (`expiresAt`) | utilisateur |
| Métadonnées documentaires | `documents` (V2, nouvelle) | DynamoDB | **PITR obligatoire** | supersession par version ; effacement coordonné | tenant |
| Ledger d'idempotence | uploads documentaires, déclenchement d'ingestion | DynamoDB | PITR | **TTL 7 jours** (par entrée) | technique |
| Magasin de commandes | autorisation des actions mutantes (`V2-ADR-014`) | DynamoDB | **PITR obligatoire** | deux fenêtres d'expiration + rétention de `executed` (§5.3.2) | identité et métier |
| Utilisateurs | `users` (nouvelle en V2, trace effacement) | DynamoDB | PITR | conservation liée à l'exigence légale (V2-ADR-015) | identité |
| Contenu documentaire | fichiers uploadés | S3 (bucket `documents`) | **versioning obligatoire** ; pas de réplication cross-région en V2 | supersession par nouvelle version ; effacement toutes versions | tenant |
| Index vectoriel | chunks + embeddings | S3 Vectors (via KB en V2) | **aucune** — état dérivé | reconstructible par ré-ingestion **dans l'espace déclaré par l'index** (§14.1) | technique dérivée |
| Mémoire agentique — session | tours de conversation d'une invocation | Memory | **aucune** par conception | **durée d'expiration explicite**, paramètre Terraform, choisie strictement inférieure à `residualWindowDays` (§9.3) | conversationnelle |
| Mémoire agentique — longue durée | préférences extraites par une stratégie Memory | Memory | **aucune** par conception | **pas d'expiration automatique** ; sa borne est l'effacement, explicite et vérifié (§8.3) | identité |
| Journal d'audit d'effacement | événements d'acceptation et de clôture d'effacement | CloudWatch Logs, groupe dédié **hors périmètre PITR** (§8.6) | append-only par nature du magasin | rétention ≥ fenêtre PITR, non désactivable (§16) | technique d'audit |
| Frontend statique | SPA React | S3 (bucket `frontend`) | versioning | remplacé par déploiement | public |
| Artefacts CI | images container, SBOM | ECR / S3 | rétention CI (`V2-LLD-008`) | conservation par version tagguée | technique |
| Secrets applicatifs | clés API tierces, mots de passe DB si applicable | Secrets Manager | rotation automatique | rotation périodique | critique |
| Configuration IaC | Terraform | Git (source de vérité) | Git | versionnement Git | technique |
| État Terraform | `terraform.tfstate` | S3 backend séparé | versioning + verrouillage | conservation illimitée (audit) | critique |

**Principe fondateur :** *aucune donnée régénérable ne fait l'objet d'une sauvegarde dédiée.*
Les données régénérables (S3 Vectors, Memory) sont reconstruites depuis leur source (S3 + KB config,
ou rien). Seules les données irremplaçables (transactionnel, métadonnées, ledger, commandes,
utilisateurs, contenu source, secrets, tfstate) sont sauvegardées.

**Ce que « aucune sauvegarde » ne dit pas (V2-ADR-015).** L'absence de sauvegarde signifie qu'aucune
**copie** ne survit ; elle ne dit rien de la durée de vie de l'**original**. La v0.3 de ce LLD tirait
de « Memory est volatile » la conclusion « pas de sauvegarde donc pas de résidu » — l'implication est
invalide, et c'est pourquoi la mémoire longue durée figure désormais sur sa propre ligne, avec la
sensibilité `identité` et une borne qui est l'effacement, pas l'expiration.

### 2.1 Deux axes de sensibilité, sans relation d'ordre (V2-ADR-017)

La colonne « Sensibilité » ci-dessus et l'attribut `classification` de `documents` (§4.3) emploient
des vocabulaires distincts et **ne se composent pas** :

| | Colonne « Sensibilité » | Attribut `classification` |
|---|---|---|
| Qualifie | une **catégorie de données** — un magasin, une table, un bucket | une **ressource** — un document précis |
| Valeurs | `utilisateur`, `tenant`, `technique`, `identité`, `conversationnelle`, `public`, `critique`, `technique dérivée`, `technique d'audit` | `internal`, `confidential`, `restricted` (ensemble fermé, `V2-ADR-017`) |
| Décide | la stratégie de sauvegarde, de chiffrement et de rétention du magasin | l'accès en lecture, l'indexabilité et l'injection dans un contexte modèle |
| Fixée par | ce LLD, à la conception | le serveur, au dépôt du document, modifiable par reclassification |

Aucune valeur de l'une ne se traduit dans l'autre. En particulier, la valeur `public` employée pour
le bucket `frontend` **n'a pas d'équivalent** dans la taxonomie documentaire : `V2-ADR-017` a écarté
tout niveau `public`, `V2-ADR-006` excluant l'accès anonyme. Deux documents de sensibilité `tenant`
peuvent porter des classifications différentes, et c'est le cas nominal.

## 3. Table DynamoDB `Trips` (V1, conservée)

### 3.1 Schéma

Repris intégralement du module V1 `infra/modules/dynamodb_trips` :

- `hash_key = userId`, `range_key = tripId` (les deux `S`) ;
- `billing_mode = PAY_PER_REQUEST` ;
- `ttl = { attribute_name = "expiresAt", enabled = true }` ;
- `point_in_time_recovery = true` (**obligatoire** en V2, cf. §12) ;
- `server_side_encryption = true` (SSE-KMS clé managée AWS).

### 3.2 Ce que V2 n'ajoute pas à `Trips`

Aucune métadonnée documentaire ni RAG n'est portée par `Trips` : `V2-ADR-003` a justifié la
création d'une table dédiée `documents` pour éviter la partition chaude sur un seul PK. `Trips`
reste strictement le magasin métier transactionnel.

## 4. Table DynamoDB `documents` (V2, nouvelle)

### 4.1 Schéma

```hcl
resource "aws_dynamodb_table" "documents" {
  name         = "${var.env}-documents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"    # "tenantId#documentId"
  range_key    = "sk"    # version (string : "v1", "v2", ...)

  attribute { name = "pk"                type = "S" }
  attribute { name = "sk"                type = "S" }
  attribute { name = "gsi1pk"            type = "S" }   # tenantId
  attribute { name = "gsi1sk"            type = "S" }   # status#createdAt (tri par statut puis date)

  global_secondary_index {
    name            = "by-tenant"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  ttl { attribute_name = "expiresAt" enabled = true }   # utilisé uniquement pour purge quarantaine
  point_in_time_recovery { enabled = true }             # non désactivable en V2 (plan_guard §16)
  server_side_encryption { enabled = true kms_key_arn = var.kms_documents_arn }
}
```

### 4.2 Clé de partition composite et design du GSI

`pk = tenantId#documentId` évite la partition chaude sur un tenant unique (`V2-ADR-003` §schéma).
L'accès direct à un document connu reste O(1) sur `pk = tenantId#…`.

**GSI `by-tenant` — choix de `gsi1sk` (O4, revue PR #35).** La clé de tri `gsi1sk = status#createdAt`
optimise le cas d'usage principal (« lister les documents d'un tenant dans un statut donné, triés par
date ») via `Query(gsi1pk = tenantId AND begins_with(gsi1sk, "indexed#"))`. Elle a une limite
assumée : un listing **tous statuts confondus triés par date** ne peut pas s'exprimer en une seule
`Query` efficace (le préfixe `status#` casse l'ordre chronologique global) et forcerait soit
plusieurs `Query` (une par statut, fusionnées côté applicatif), soit un `Scan` du partition —
coûteux sur un tenant actif.

Ce compromis est **retenu** parce que les parcours réels sont presque toujours filtrés par statut
(afficher les `indexed`, suivre les `ingesting`, purger les `deleted`). Si un besoin de listing
chronologique tous-statuts émerge, l'évolution compatible est un **second GSI** `by-tenant-date`
(`gsi1pk = tenantId`, `gsi1sk = createdAt`) plutôt qu'une refonte de `by-tenant` — ajout d'index
sans réécriture des accès existants. Ce point est laissé ouvert et tracé ici, pas tranché
prématurément.

### 4.3 Attributs (compatibles avec V2 et V3)

| Attribut | Type | Écrit par | Modifié en V3 ? |
|---|---|---|---|
| `pk`, `sk`, `gsi1pk`, `gsi1sk` | S | serveur | non |
| `status` | S | serveur | non (mais grain rétabli en V3, cf. §4.4) |
| `chunkCount` | N | KB (V2) / worker (V3) | non |
| `embeddingSpaceId` | S | serveur — lu depuis l'index, pas depuis la configuration (§4.3.1) | non |
| `chunkerVersion` | S | vide en V2, renseigné en V3 | rempli |
| `classification` | S | serveur (§4.3.2) | non |
| `sourceUri` | S | serveur | non |
| `creationOperationId` | S | serveur | non |
| `kbIngestionJobId` | S | serveur (V2 uniquement) | supprimé en V3 |
| `kbDataSourceId` | S | config (V2 uniquement) | supprimé en V3 |
| `createdAt`, `updatedAt` | S (ISO) | serveur | non |

Les attributs `kb*` sont **présents uniquement en V2**. Leur suppression en V3 est un changement de
schéma **compatible ascendant** (attributs optionnels).

#### 4.3.1 `embeddingSpaceId` remplace `embeddingModelId` et `embeddingVersion` (V2-ADR-013)

La v0.3 traçait deux attributs distincts, `embeddingModelId` et `embeddingVersion`. `V2-ADR-013` a
écarté cette décomposition : elle traite avec trois chaînes de même rang deux natures qui ne se
gèrent pas pareillement — un changement de modèle rend les vecteurs incomparables et impose un
nouvel index, un changement de chunker ne rend rien incomparable et se réévalue à espace constant.

`embeddingSpaceId` est un identifiant **opaque** liant le modèle, la dimension et la métrique de
distance. Le code n'en dérive aucune logique : il compare des égalités. Le format et la procédure
d'attribution appartiennent à `V2-LLD-002` ; ce LLD n'en fixe que le stockage et les invariants.

| Invariant | Portée |
|---|---|
| Un index porte un et un seul `embeddingSpaceId`, fixé à sa création et immuable | index |
| `documents.embeddingSpaceId` enregistre **l'espace de l'index où le document est effectivement indexé** — la valeur est lue depuis les métadonnées de l'index, jamais depuis la configuration d'embedding courante | document |
| Un document dont `status = indexed` et dont `embeddingSpaceId` diffère de celui de l'index courant est une **incohérence bloquante**, détectée par `check_dv_consistency.py` (§16.3) | corpus |
| `chunkerVersion` reste tracé séparément : il ne conditionne pas la comparabilité et permet la réévaluation ciblée à espace constant | chunk |

La raison de lire l'espace depuis l'index et non depuis la configuration est le mode de panne que
`V2-ADR-013` décrit : un index mêlant deux espaces répond sans erreur, avec des scores crédibles, et
des résultats faux. Aucune exception n'est levée, aucune métrique technique ne bouge. Faire de la
configuration la source de vérité de l'espace, c'est rendre cette panne indétectable.

La conséquence côté migration (index parallèle, évaluation, bascule de pointeur, période de grâce)
est traitée en §14.5 ; la conséquence côté restauration en §14.1.

#### 4.3.2 `classification` — domaine fermé, défaut et régimes de reclassification (V2-ADR-017)

La v0.3 déclarait `classification` « écrit par serveur (`V2-ADR-017`) » sans valeurs ni défaut.
`V2-ADR-017` a tranché : **ensemble fermé de trois niveaux**, ordonnés par restriction croissante.

| Valeur | Accès en lecture | Indexé | Injecté dans un contexte modèle | Préfixe S3 (§7.1) |
|---|---|---|---|---|
| `internal` | tout membre du tenant | oui | oui, pour tout membre du tenant | `sources/` |
| `confidential` (**défaut**) | ownership ou partage explicite | oui | oui, pour les seuls autorisés | `sources/` |
| `restricted` | ownership ou partage explicite | **non** | **non** | `restricted/` — hors data source KB |

Quatre règles de validation portées par la table :

- **toute valeur hors de cet ensemble est refusée à l'écriture.** Le domaine est fermé dans le code,
  pas en configuration : une valeur inconnue n'aurait pas de comportement défini, et le refus par
  défaut de `V2-ADR-006` la rejetterait de toute façon — autant fermer l'ensemble là où il est
  décidé ;
- **le défaut est `confidential`**, pas le niveau le plus restrictif. Un défaut à `restricted`
  produirait un système où aucun document n'est indexé sans geste explicite, ce qui vide l'upload
  documentaire de son objet. `confidential` est fail-closed sur l'accès — seul le propriétaire lit —
  et fonctionnel sur l'indexation ;
- **un document en `status = quarantined` est traité comme `restricted`**, quelle que soit la valeur
  déclarée. Son contenu n'a pas été validé : il n'est ni lisible ni indexable ;
- **la reclassification d'un document `quarantined` est refusée** par la couche applicative, dans
  les deux sens et sans passer par `V2-ADR-014` : le statut prime sur l'attribut, la reclassification
  est donc sans objet.

**Deux régimes de reclassification**, selon le sens :

| Sens | Exemple | Régime | Effet sur les données |
|---|---|---|---|
| Restrictif | `internal` → `confidential` | pas de confirmation ; effet immédiat | écriture `documents` seule |
| Assouplissant | `confidential` → `internal` | action mutante `V2-ADR-014` : matérialisée, confirmée hors du chemin du modèle | écriture `documents` seule |
| Vers `restricted` | tout niveau → `restricted` | régime restrictif (pas de confirmation) mais **coût structurel** | écriture `documents` + déplacement S3 vers `restricted/` + purge des versions non-courantes à l'ancien préfixe + désindexation asynchrone (§8.2 étape 3) |

L'asymétrie suit `V2-ADR-014` sans l'étendre : élargir un accès est une action à conséquence de
sécurité, le resserrer n'en est pas une.

**La transition vers `restricted` est la seule à toucher le stockage.** Sur un bucket versionné,
déplacer un objet est une opération copy + delete : la suppression de la clé source pose un marqueur
de suppression, mais les versions non-courantes restent atteignables par version ID à l'ancien
emplacement. Elles doivent donc être **supprimées explicitement dans la même opération** (hard delete
des non-current versions), faute de quoi un résidu reste accessible hors du préfixe `restricted/`.
C'est le même mécanisme que la règle « supprimer chaque version » de l'effacement utilisateur
(§8.4), et pour la même raison.

L'asynchronie de la désindexation est sans effet sur l'autorisation : dès l'écriture dans
`documents`, le post-filtrage de `V2-LLD-002` §6.2 refuse l'injection, puisque la classification qui
autorise est celle de `documents` et jamais celle du chunk. Les chunks survivants ne sont qu'un
résidu à nettoyer.

**La classification n'est pas une donnée personnelle** : elle qualifie la ressource, non la
personne. Elle n'entre dans le périmètre d'effacement de `V2-ADR-015` que par la suppression du
document qui la porte.

### 4.4 Cycle de vie du `status`

Repris de `V2-LLD-002` §4.3 pour cohérence :

```text
V2 : uploaded -> validated | quarantined
     validated -> ingesting -> indexed | failed
     indexed  -> superseded (réindexation) | deleting -> deleted

V3 : uploaded -> validated | quarantined
     validated -> parsing -> chunking -> embedding -> indexing -> indexed | failed
     indexed  -> superseded | deleting -> deleted
```

Le mapping V2 (`ingesting`) → V3 (`parsing`/`chunking`/`embedding`/`indexing`) est **le seul point
d'évolution** du cycle. Les états terminaux (`indexed`, `deleted`, `failed`, `superseded`,
`quarantined`) sont identiques dans les deux phases : les requêtes qui filtrent sur l'un de ces
états ne changent pas à la bascule.

## 5. Idempotence et autorisation des mutations — deux magasins disjoints

### 5.1 Deux magasins, deux portées

`V2-ADR-014` a séparé ce que la V1 traitait d'un seul tenant. Une mutation passée par une commande
tire son idempotence de l'état terminal de cette commande ; une opération sans commande la tire du
ledger hérité de la V1. Les deux portées sont **disjointes par construction** :

| Magasin | Portée | Ce qui garantit la non-répétition |
|---|---|---|
| Magasin de commandes (§5.3) | toute action mutante passée par une commande — mutations `Trips`, demande d'effacement (§8.4), reclassification assouplissante (§4.3.2) | l'état terminal `executed`, condition de la transaction d'exécution |
| Ledger d'idempotence (§5.2) | opérations **sans** commande — uploads documentaires, déclenchement d'ingestion KB | le hash canonique du payload et le marqueur `mutation_started` |

**Pourquoi les mutations `Trips` ne sont plus dans la portée du ledger.** Une rédaction antérieure de
cette section les y maintenait, en reconduction du pattern V1. `V2-ADR-014` les en a retirées :

> « Une mutation passée par une commande **n'écrit pas d'entrée dans le ledger** de `V2-LLD-006` §5,
> qui reste réservé aux opérations sans commande — uploads documentaires et déclenchements
> d'ingestion. »

Maintenir les deux formulations produirait **deux enregistrements d'idempotence pour la même
mutation, dont un seul serait lu** à l'exécution. Le second ne serait pas une redondance
inoffensive : il donnerait l'apparence d'une garantie à un enregistrement que rien ne consulte, et sa
purge à sept jours (§5.2) ne dirait rien de la fenêtre réellement protégée — celle de la rétention
`executed` (§5.3.4).

Le pattern V1 n'est pas abandonné pour autant : il change de porteur. La condition transactionnelle
du §5.3.3 joue le rôle que `mutation_started` jouait en V1, avec la même propriété — l'effet de bord
et la marque qui interdit son rejeu sont écrits ensemble, ou pas du tout.

### 5.2 Ledger d'idempotence (V1 pattern, réutilisé)

Le pattern V1 (`docs/adr/ADR-0006`, `docs/adr/ADR-0007`) — hash canonique du payload,
`mutation_started` bloquant tout replay après effet de bord, TTL — est repris pour les opérations
qui ne passent pas par une commande :

- uploads documentaires (nouveau, `creationOperationId` généré client ou serveur) ;
- déclenchement d'ingestion KB (nouveau, `hash(tenantId + documentId + version)` pour éviter double
  `StartIngestionJob`).

Le ledger est porté par une **table dédiée** `${env}-idempotency-ledger` (pas fusionné avec
`documents` ou `Trips`) :

- `pk = scope#hash` (scope = `document-upload` / `document-ingest` ; hash = canonique) ;
- `sk = createdAt` ;
- `ttl = 7 jours` (attribut `expiresAt`), suffisant pour couvrir tous les retry raisonnables
  (SQS/HTTP/utilisateur) ;
- PITR activé (traçabilité en cas d'audit sur un doublon supposé) ;
- SSE-KMS.

Le scope `trip-mutation` de la rédaction antérieure **n'existe plus** : ces mutations relèvent du
magasin de commandes. Un scope résiduel écrirait des entrées que rien ne lit.

Ce découplage évite qu'une purge TTL du ledger n'affecte les métadonnées ou métier ; il permet
aussi de dimensionner indépendamment (le ledger est majoritairement write-once + TTL).

### 5.3 Magasin de commandes (V2-ADR-014)

`V2-ADR-014` délègue le magasin à ce LLD — « le choix du magasin, la valeur des TTL et la forme des
clés sont délégués à `V2-LLD-006`, qui possède les modèles de données ». `V2-LLD-004 §6.1` en énonce
les neuf invariants sans porter aucune valeur, et `V2-LLD-005 §4.6` la part autorisation de la
confirmation. Cette section est la réalisation : elle décide la table, ses clés, ses attributs et ses
trois durées.

C'est le seul objet durable dont dépend la garantie centrale de `V2-ADR-014` : il porte
l'autorisation de toute action mutante et, l'état `executed` étant terminal, l'idempotence de cette
même action.

#### 5.3.1 Schéma

Table dédiée `${env}-commands`, distincte du ledger et des tables métier.

| Élément | Valeur | Justification |
|---|---|---|
| `pk` | `commandId` | résolution directe à l'exécution ; seule valeur qui circule (`V2-ADR-014`) |
| `sk` | *(aucune)* | une commande est un item unique, sans historique de versions |
| GSI `by-operation` | `pk = tenantId#operationId`, `sk = createdAt` | invariant I9 : FastAPI retrouve la commande à présenter par l'`operationId` qu'elle possède déjà, jamais par une référence relayée par le modèle |

`commandId` est **opaque et non devinable** (invariant I8) : préfixe `cmd_` suivi de 32 caractères
hexadécimaux issus d'une source aléatoire cryptographique, soit 128 bits d'entropie. Il n'encode ni
le tenant, ni l'acteur, ni l'action, et n'est pas dérivé du contenu de la commande.

**Le tenant est dans la clé du GSI, pas seulement en attribut.** Un index dont la clé de partition
serait le seul `operationId` rendrait exprimable la requête d'un tenant sur la commande d'un autre,
avec pour seul rempart le filtre applicatif. Le préfixer par `tenantId` rend cette requête
inexprimable — même règle qu'au GSI `by-tenant` de §4.2, et même fondement (`V2-ADR-006`).

| Attribut | Type | Rôle |
|---|---|---|
| `commandId` | `S` | clé de partition |
| `tenantId` | `S` | invariant I2 ; composant de la clé du GSI |
| `actorId` | `S` | invariant I1 ; comparé à l'identité injectée, à la confirmation comme à l'exécution |
| `operationId` | `S` | invariant I9 ; composant de la clé du GSI |
| `toolName` | `S` | tool d'exécution seul habilité à consommer cette commande |
| `payload` | `M` | valeurs de la mutation telles que matérialisées — le résumé présenté à la confirmation en est rendu, jamais reconstruit depuis la requête |
| `state` | `S` | `pending` \| `confirmed` \| `executed` |
| `pendingExpiresAt` | `N` | échéance de la fenêtre de proposition (epoch) |
| `confirmedExpiresAt` | `N` | échéance de la fenêtre d'exécution (epoch), écrite à la confirmation |
| `result` | `M` | résultat de l'exécution initiale, renvoyable sur rejeu (invariant I6) |
| `createdAt`, `confirmedAt`, `executedAt` | `N` | horodatages ; `createdAt` est le `sk` du GSI |
| `expiresAt` | `N` | TTL DynamoDB — **purge seule**, jamais l'application d'une fenêtre (§5.3.4) |

Il n'existe **pas** d'état `expired` écrit. L'expiration est déduite de la comparaison des
horodatages à la relecture (`V2-LLD-004 §6.4`) : un état écrit supposerait un balayage périodique
dont le retard rouvrirait exactement la fenêtre que les horodatages ferment.

#### 5.3.2 Les trois durées

`V2-LLD-004 §7.4` distingue trois durées et refuse de déduire l'une des autres. Ce LLD les chiffre :

| Durée | Variable Terraform | Valeur `test` | Ce qu'elle borne |
|---|---|---|---|
| Fenêtre `pending` | `command_pending_window_minutes` | 15 min | validité d'une proposition non confirmée |
| Fenêtre `confirmed` | `command_confirmed_window_seconds` | 120 s | validité d'une autorisation non exécutée |
| Rétention `executed` | `command_executed_retention_days` | 7 j | garantie de non-rejeu |

**La deuxième est courte par décision, pas par prudence.** Elle borne l'intervalle entre le geste de
confirmation et l'exécution — un aller-retour serveur, pas une réflexion utilisateur, laquelle est
bornée par la première. C'est aussi ce qui donne son effet à l'annulation : `V2-ADR-011` évalue les
points d'annulation avant l'émission d'un appel de tool, et cette fenêtre borne le délai pendant
lequel une commande confirmée puis annulée resterait exécutable (`V2-LLD-004 §10.2`).

**La troisième est alignée sur le ledger, et ce n'est pas une coïncidence.** Sept jours est la
rétention du ledger (§5.2), retenue pour couvrir tout retry raisonnable. Les mutations par commande
ayant quitté le ledger (§5.1), leur fenêtre d'idempotence doit être **au moins** équivalente : sans
cela, la séparation dégraderait une garantie déjà tenue en V1. C'est l'invariant I7 de `V2-LLD-004`.

Ces trois valeurs sont des **paramètres Terraform** (§10), jamais des constantes applicatives.

#### 5.3.3 Transaction d'exécution

La condition d'autorisation et l'effet de bord tiennent dans un `TransactWriteItems` unique — forme
retenue par `V2-ADR-014`, déjà employée en V1 (`lambda_function_hardened.py`, `update_trip`) :

```text
TransactWriteItems
  ├── Update  ${env}-commands[commandId]
  │     ConditionExpression :  state = "confirmed"
  │                       ET   actorId  = <identité injectée>
  │                       ET   tenantId = <tenant injecté>
  │                       ET   confirmedExpiresAt > <maintenant>
  │     UpdateExpression   :  state ← "executed", result ← <résultat>, executedAt ← now
  │
  └── Put / Update  ${env}-Trips[…]            ← l'effet de bord métier
                                                 (ou la cible métier de l'action)

  échec de la condition ⇒ AUCUNE des deux écritures n'est appliquée
```

**Contrainte de placement, et pourquoi elle est structurante.** `TransactWriteItems` n'opère que dans
une seule région et sur des tables du même compte. `${env}-commands` est donc créée dans la région et
le compte de la cible métier — `eu-west-3`, avec `Trips`. C'est la précondition P2 de `V2-LLD-004` ;
elle est satisfaite ici par construction. Une cible métier hors région ne rendrait pas la garantie
coûteuse, elle la rendrait **inapplicable** : il faudrait revenir à « vérifier puis écrire », que
`V2-ADR-014` refuse. Toute cible métier future relevant d'une commande hérite donc de cette
contrainte de colocalisation.

La limite d'items par transaction n'est pas contraignante : une commande porte une mutation.

#### 5.3.4 Rétention, TTL et entrée réduite

Le TTL DynamoDB (`expiresAt`) **purge**, il n'applique aucune fenêtre. `V2-LLD-004 §6.4` en fait une
règle : l'expiration d'une commande est appliquée par la condition sur `confirmedExpiresAt` dans la
transaction, jamais par le TTL, dont la suppression est différée et non bornée utilement. Une
commande dont la fenêtre courte est écoulée mais l'item non encore purgé est donc **inexécutable**,
et c'est la condition transactionnelle qui le garantit.

`expiresAt` est positionné à la borne la plus tardive de l'item :

| État | `expiresAt` |
|---|---|
| `pending` | `pendingExpiresAt` + marge de purge |
| `confirmed` | `confirmedExpiresAt` + marge de purge |
| `executed` | `executedAt` + `command_executed_retention_days` |

**Si la rétention `executed` ne pouvait pas couvrir la fenêtre d'idempotence exigée** (précondition
P3 de `V2-LLD-004`), la réponse conforme ne serait pas de laisser la commande disparaître : une
**entrée réduite** valant enregistrement de non-rejeu serait conservée au-delà — `commandId`,
`tenantId`, `actorId`, `state = executed`, `executedAt` — sans `payload` ni `result`. Elle ne permet
plus de renvoyer le résultat initial ; elle permet de refuser un second effet de bord, qui est la
propriété à préserver. En V2, les sept jours étant alignés sur le ledger, ce repli n'est pas activé.

## 6. Table `users` (V2, nouvelle — trace d'effacement)

### 6.1 Portée V2 (minimale)

En V2, `users` porte uniquement ce qui est **nécessaire à l'audit de suppression** (§8) sans
préempter `V2-ADR-015`. Elle **ne remplace pas Cognito** comme source d'identité (V2-LLD-005).

### 6.2 Schéma minimal

```hcl
resource "aws_dynamodb_table" "users" {
  name         = "${var.env}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute { name = "userId" type = "S" }
  attribute { name = "gsi1pk" type = "S" }   # tenantId

  global_secondary_index {
    name            = "by-tenant"
    hash_key        = "gsi1pk"
    projection_type = "ALL"
  }

  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true kms_key_arn = var.kms_users_arn }
}
```

### 6.3 Attributs et horodatages d'effacement (V2-ADR-015)

| Attribut | Écrit à | Signification |
|---|---|---|
| `userId` | création | miroir de l'identifiant Cognito |
| `tenantId` | création | tenant de rattachement (`gsi1pk`) |
| `createdAt` | création | — |
| `erasureOperationId` | acceptation de la demande | UUID de la commande confirmée (`V2-ADR-014`) ; trace qui rend la reprise possible sans nouvelle confirmation |
| `erasureRequestedAt` | acceptation de la demande | la demande est matérialisée et acceptée ; l'exécution commence |
| `erasureCompletedAt` | après **vérification d'absence** (§8.4 étape 5) | **effacement logique** atteint : aucun magasin interrogé en ligne ne retourne la donnée |
| `erasureDurableAt` | en même temps que `erasureCompletedAt` | `erasureCompletedAt + residualWindowDays` — **plus aucune copie restaurable**. Valeur **calculée**, jamais le résultat d'un traitement |

`erasureDurableAt` est l'attribut que la v0.3 n'avait pas, et son absence rendait fausse
l'affirmation portée par `erasureCompletedAt`. Le raisonnement est celui de `V2-ADR-015` : le PITR
est une sauvegarde continue qui n'expose **aucune opération de rédaction**. Tant que la fenêtre PITR
couvre l'instant qui précède un effacement, une copie exploitable de la donnée effacée existe, et
une restauration parfaitement légitime la réintroduit.

```text
residualWindowDays = max(fenêtres PITR des tables couvertes par V2-ADR-010)
                     Trips, documents, users, ledger — 35 jours en l'état (§12.1)
```

**Le maximum, pas la valeur commune.** Le PITR se configure table par table. Les quatre tables
partagent aujourd'hui la même fenêtre, mais une seule dont la fenêtre serait allongée étendrait le
résidu réel sans que la constante déclarée le reflète. La fenêtre résiduelle est une propriété du
système, pas d'une table — c'est pourquoi elle est calculée et non saisie.

Les autres résidus sont soit immédiats, soit strictement inclus dans cette fenêtre : le ledger
expire en 7 jours (§5.2), S3 est purgé version par version (§8.4), S3 Vectors est vérifié à zéro
(§8.2 étape 4). La fenêtre résiduelle est donc entièrement déterminée par un paramètre déjà décidé
par `V2-ADR-010`.

**Ce qui est communiqué en cas de demande d'attestation est `erasureDurableAt`**, pas
`erasureCompletedAt`. Le second atteste l'effacement logique ; le premier atteste la fin.

Toute extension de la table (préférences, profil enrichi) reste hors périmètre V2 — sauf activation
du repli conditionnel de `V2-ADR-015` (P1/P2, §1.3), qui y ferait entrer les préférences aujourd'hui
portées par Memory.

### 6.4 `erasure_sla_days` — délai annonçable, pas obligation inventée

`V2-ADR-015` ne fixe aucun délai légal : la Charte §4.2 exclut d'inventer la gouvernance d'un client
qui n'existe pas. Ce LLD porte donc un **paramètre Terraform** sans valeur imposée, et un plancher
technique qui, lui, n'est pas négociable :

```text
erasure_sla_days >= residualWindowDays
```

Sémantique : la durée maximale entre `erasureRequestedAt` et `erasureDurableAt` que le système
s'engage à tenir. Elle se décompose en une part pilotable — les étapes 1 à 6 de §8.4, de l'ordre de
la minute lorsqu'elles réussissent — et une part **subie**, la fenêtre résiduelle, non
raccourcissable.

Le paramètre est consommé à deux endroits, et deux seulement :

1. la garde de plan Terraform (§16), qui refuse toute valeur sous le plancher ;
2. l'alerte d'exploitation sur effacement incomplet (§8.7), qui se déclenche à
   `erasureRequestedAt + erasure_sla_days - residualWindowDays`.

Un `erasure_sla_days` fixé au plancher exact réduit ce seuil d'alerte à zéro : tout effacement non
clôturé immédiatement alerte. C'est cohérent, et c'est la raison d'être de la marge que l'exploitant
choisit d'ajouter au plancher.

Si un délai plus court devenait exigible, le seul levier conforme est la réduction de la fenêtre
PITR — au prix documenté du RPO — ou la bascule vers l'effacement cryptographique (option C de
`V2-ADR-015`, écartée en V2). Aucun autre chemin ne raccourcit le résidu.

## 7. Buckets S3

### 7.1 Bucket `documents` (sources)

```hcl
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }   # non désactivable (plan_guard §16)
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_documents_arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

Préfixes gouvernés côté serveur :

| Préfixe | Contenu | Couvert par la data source KB | Classification admise |
|---|---|---|---|
| `sources/<tenantId>/<documentId>/v<version>/` | contenu source définitif, indexable | **oui** | `internal`, `confidential` |
| `sources/<tenantId>/<documentId>/v<version>/<filename>.metadata.json` | métadonnées consommées par KB (`V2-LLD-002` §5.3) | oui | — |
| `restricted/<tenantId>/<documentId>/v<version>/` | contenu source définitif, **non indexable** | **non** | `restricted` uniquement |
| `quarantine/<tenantId>/<documentId>/v<version>/` | upload en attente de validation | non | traité comme `restricted` (§4.3.2) |

**Pourquoi un préfixe et non un attribut (V2-ADR-017).** La data source KB se définit **par préfixe
S3** : exclure un document de l'indexation exige que sa clé de stockage sorte du préfixe couvert.
C'est une contrainte du service, pas un choix de conception — et c'est la seule propriété de
classification portée par la clé.

Ce préfixe encode l'**indexabilité**, c'est-à-dire dans quel service la donnée entre. Il **n'encode
aucune rétention** : `sources/` et `restricted/` portent la même politique de conservation (§7.2,
§10). C'est ce qui distingue cette exception du cas général écarté par `V2-ADR-017` — un préfixe par
niveau de classification rendrait toute reclassification destructive, alors qu'ici seule la
transition vers `restricted` déplace des octets.

### 7.2 Cycle de vie S3

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "purge-quarantine"
    status = "Enabled"
    filter { prefix = "quarantine/" }
    expiration { days = 7 }                          # rejet auto après 7 jours
    noncurrent_version_expiration { noncurrent_days = 7 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }

  rule {
    id     = "expire-superseded-source-versions"
    status = "Enabled"
    filter { prefix = "sources/" }
    noncurrent_version_expiration { noncurrent_days = 90 }   # rétention post-supersession
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }

  rule {
    id     = "expire-superseded-restricted-versions"
    status = "Enabled"
    filter { prefix = "restricted/" }
    noncurrent_version_expiration { noncurrent_days = 90 }   # STRICTEMENT identique à sources/
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
}
```

Les objets courants (version live) ne sont **jamais** expirés par cycle de vie : seule une
suppression coordonnée (§8) peut les retirer. Les versions non-courantes sont purgées après une
période de grâce (90 jours) pour éviter la croissance illimitée du bucket.

**Les deux préfixes de sources portent la même valeur de rétention, et c'est une décision (V2-ADR-017).**
La règle `restricted/` n'existe séparément que parce qu'un cycle de vie S3 se définit par préfixe :
si `sources/` et `restricted/` pouvaient être couverts par une règle unique, ils le seraient. Toute
divergence future entre ces deux valeurs ferait de la classification un pilote de conservation, ce
que `V2-ADR-017` a explicitement écarté (§10).

**Cette rétention de cycle de vie ne suffit pas à un effacement.** Attendre 90 jours n'est pas une
suppression : l'effacement utilisateur (§8.4) et la transition vers `restricted` (§4.3.2) suppriment
chaque version explicitement, sans s'en remettre au cycle de vie. La distinction compte parce que
90 jours dépassent la fenêtre résiduelle de 35 jours (§6.3) : un résidu laissé au cycle de vie
sortirait de la fenêtre déclarée et la rendrait fausse.

### 7.3 Autres buckets

- `frontend` : SPA React déployée, versioning activé, pas de KMS obligatoire (contenu public
  servi via CloudFront) ;
- `artefacts` : SBOM CI, rapports de test, versioning + KMS, cycle de vie 90 jours (`V2-LLD-008`) ;
- `tfstate` : backend Terraform, verrouillage DynamoDB, versioning + KMS, conservation illimitée.

## 8. Suppression coordonnée et droit à l'effacement (frontière V2)

### 8.1 Deux niveaux de suppression

| Niveau | Portée | Déclencheur | Étendue |
|---|---|---|---|
| Suppression documentaire | 1 document | utilisateur ou admin | 1 `documentId` toutes versions |
| Effacement utilisateur | tous les documents + mémoire longue durée + trace | demande d'effacement, action mutante `V2-ADR-014` | tous documents du user, namespace Memory de l'acteur, `users.erasureCompletedAt` et `erasureDurableAt` renseignés |

L'effacement utilisateur en V2 est **une composition** de suppressions documentaires, d'une
suppression mémoire explicite et d'une entrée `users` de trace. `V2-ADR-015` en a fixé le modèle :
**effacement logique immédiat, fenêtre résiduelle bornée et déclarée** (§6.3). Ce qui suit est la
mécanique de cette décision, pas une mécanique en attente de décision.

### 8.2 Suppression documentaire — séquence V2

```text
DELETE /documents/{documentId}
  1. FastAPI vérifie ACL (utilisateur ou admin du tenant)
  2. documents.status = "deleting"  (transition conditionnelle depuis "indexed" ou "failed")
  3. Adapter magasin vectoriel .delete(documentId, toutes versions) :
       V2 : suppression S3 des sources — TOUTES les versions, par version ID, sous les
            deux préfixes possibles (sources/ et restricted/, §7.1), fichier
            .metadata.json compris ; JAMAIS un simple marqueur de suppression
            + StartIngestionJob KB (resync qui retire les chunks de l'index S3V)
       V3 : saga applicative (V2-ADR-003)
  4. Vérification "no résidu" :
       - list_object_versions S3 avec préfixe = 0 (versions ET marqueurs)
       - Retrieve KB avec filter documentId = 0
  5. documents.status = "deleted" (transition conditionnelle depuis "deleting")
  6. Émission d'un événement d'audit (V2-LLD-005) sans données sensibles
```

**Point critique V2 :** l'étape 3 (V2) est **asynchrone** — la resync KB prend l'ordre de la
minute. Le `status = "deleted"` n'est atteint qu'après vérification en étape 4. Un client qui liste
les documents entre l'étape 2 et 5 voit `deleting`, jamais un état incohérent.

**Suppression par version, pas marqueur (V2-ADR-015, précondition P5).** L'étape 3 emploie
`list_object_versions` puis `delete_object --version-id` pour chaque version, et l'étape 4 vérifie
l'absence de versions **et** de marqueurs de suppression. Poser un marqueur laisserait les versions
antérieures atteignables par version ID pendant 90 jours (§7.2) — au-delà de la fenêtre résiduelle
de 35 jours, ce qui rendrait fausse la garantie d'`erasureDurableAt`. C'est la même règle que la
purge des versions non-courantes lors d'une transition vers `restricted` (§4.3.2), et la raison est
identique : sur un bucket versionné, supprimer une clé ne supprime pas son contenu.

### 8.3 Suppression coordonnée — Memory (V2-ADR-015)

`V2-ADR-006` exige la suppression coordonnée sur S3 + S3V + DynamoDB + Memory. La v0.3 réduisait la
part Memory à un best-effort, sur l'argument « pas de sauvegarde donc pas de résidu ».
`V2-ADR-015` a invalidé cet argument (§2) et remplacé le régime :

| Nature | Régime de suppression | Bloquant pour l'effacement ? |
|---|---|---|
| Mémoire de session | couverte par la durée d'expiration configurée (§9.3), choisie strictement inférieure à `residualWindowDays` | non — elle entre dans le résidu déjà borné par le PITR |
| Mémoire longue durée | **suppression explicite du namespace de l'acteur, puis vérification par relecture** (résultat attendu : zéro enregistrement) | **oui** |

La règle qui tranche est fail-closed et se formule sans ambiguïté :

> **AgentCore Memory ne peut contenir une donnée personnelle que si sa suppression est prouvée.**
> Tant que la suppression n'est pas démontrée par un test, aucune stratégie de mémoire longue durée
> n'est activée en V2.

C'est la transposition à Memory du principe déjà retenu par `V2-ADR-006` — le refus est la valeur
par défaut lorsqu'une information manque. Elle rend la précondition P1 (§1.3) bloquante au lieu de
laisser un doute se propager jusqu'à l'exploitation.

**Ce que ce changement coûte :** une suppression Memory qui échoue **bloque** désormais l'écriture
d'`erasureCompletedAt`, là où le best-effort de la v0.3 ne produisait aucune alerte. L'exploitation
gagne un état à surveiller et un geste de reprise (§8.7, §18.3). C'est le prix assumé de la
garantie.

### 8.4 Effacement utilisateur — séquence V2 (V2-ADR-015)

```text
POST /admin/users/{userId}/erase

  1. Matérialisation (V2-ADR-014)
       La demande est matérialisée en commande, confirmée hors du chemin du modèle,
       puis exécutée par référence. Un modèle ne déclenche JAMAIS un effacement sur
       la seule foi d'un tour de conversation. Vérification admin + résolution tenant.

  2. Acceptation
       users.erasureRequestedAt  = now
       users.erasureOperationId  = uuid (trace de la commande confirmée)
       Événement d'audit émis dans le journal append-only (§8.6).

  3. Suppression documentaire
       Pour chaque documentId de l'utilisateur : séquence §8.2, avec suppression
       permanente de chaque version S3 (pas de marqueur).

  4. Suppression mémoire
       Enregistrements longue durée du namespace de l'acteur : suppression explicite,
       puis vérification par relecture (résultat attendu : vide).
       Mémoire de session : couverte par la durée d'expiration configurée (§9.3).

  5. Vérification d'absence — GARDE DU MODÈLE
       S3         : list_object_versions par préfixe = 0, toutes versions, aucun marqueur
       S3 Vectors : Retrieve filtré sur le tenant et l'utilisateur = 0 chunk
       Memory     : relecture du namespace = 0 enregistrement longue durée
       Une vérification non concluante INTERDIT l'étape 6.

  6. Clôture logique
       users.erasureCompletedAt = now
       users.erasureDurableAt   = now + residualWindowDays
       Événement d'audit émis dans le journal append-only (§8.6)
       — c'est cet événement qui est la source du rejeu après restauration (§13.5).
```

**L'étape 5 est la garde du modèle.** `erasureCompletedAt` n'est jamais écrit sur le simple succès
des appels de suppression : il l'est après vérification. C'est la discipline que §8.2 applique déjà
au passage en `status = deleted`, étendue à l'effacement utilisateur et à Memory. Sans elle,
l'horodatage atteste un fait non vérifié — et une trace d'audit qui atteste un fait faux est pire
que l'absence de trace.

**Ce qui reste hors de ce LLD :** la forme exacte de la confirmation (`V2-ADR-014`, appliqué tel
quel, implémenté en `V2-LLD-004`/`V2-LLD-005`), la communication utilisateur, et la qualification
juridique du traitement — `V2-ADR-015` §Périmètre exclu rappelle que la Charte §4.2 exclut toute
gouvernance client inventée.

### 8.5 Ce que l'effacement ne couvre pas

Énoncer ces exclusions fait partie de la décision : un effacement dont le périmètre est implicite ne
peut être ni testé ni attesté.

| Élément | Statut | Justification |
|---|---|---|
| Entrée `users` avec `erasureCompletedAt` / `erasureDurableAt` | **conservée** | La supprimer rendrait l'effacement invérifiable. Elle ne contient que l'identifiant, le tenant et les horodatages ; le contenu personnel a précisément été retiré |
| Journal d'audit d'effacement (§8.6) | **conservé au-delà de la fenêtre PITR** | Contrainte de rejeu (§13.5) : sans lui, la fenêtre résiduelle n'est plus fermée par un mécanisme |
| Journaux et traces applicatifs | **conservés**, non purgés | Identifiants hashés, aucun contenu en clair (`V2-ADR-006`) : pseudonymisés par construction. La correspondance permettant la ré-identification est l'entrée `users`, dont le contenu personnel a été retiré. Rétention d'audit fixée par `V2-LLD-007` |
| Données agrégées non ré-identifiables (volumes, comptages, coûts) | non concernées | — |
| Sauvegardes déjà écrites (fenêtre PITR, versions S3 non encore purgées) | **non rédigées ; elles expirent** | C'est l'objet même de la fenêtre résiduelle (§6.3). Aucun mécanisme AWS ne permet de rédiger une fenêtre PITR |
| `classification` du document supprimé | conservée dans le tombstone (§10) | Une trace d'audit qui ne dirait pas à quel niveau le document supprimé était classé n'atteste rien d'exploitable (`V2-ADR-017`) |

Un nouvel identifiant utilisateur créé pour la même personne physique n'hérite pas de l'ancien
enregistrement.

### 8.6 Journal d'audit d'effacement — magasin contraint (V2-ADR-015)

La v0.3 émettait « un événement d'audit » sans en fixer la destination. `V2-ADR-015` a montré que
cette omission est structurante : rien n'interdisait qu'il atterrisse dans une table DynamoDB, donc
sous PITR.

> **Une source de rejeu restaurable en même temps que les tables qu'elle sert à corriger n'est pas
> une source.**

La table `users` ne peut donc pas servir de source au rejeu : elle est elle-même soumise au PITR et
peut avoir été ramenée en arrière par la restauration même qu'il s'agit de corriger.

**Deux contraintes, non négociables :**

```text
1. indépendance   le journal n'est porté par AUCUNE ressource couverte par le PITR
                  de V2-ADR-010 (Trips, documents, users, ledger)
2. rétention      rétention(journal d'effacement) >= fenêtre PITR
```

Sans la seconde, une restauration au bord de la fenêtre PITR pourrait ne plus disposer de la liste
des effacements à rejouer.

**Médium retenu :** un **groupe de journaux CloudWatch dédié**, `/${env}/erasure-audit`, append-only
par nature du service, avec `retention_in_days` explicite, chiffré par CMK (`V2-LLD-001` pour la
politique de clé des groupes de journaux).

```hcl
resource "aws_cloudwatch_log_group" "erasure_audit" {
  name              = "/${var.env}/erasure-audit"
  retention_in_days = var.erasure_audit_retention_days  # >= fenêtre PITR — gardé §16
  kms_key_id        = var.kms_logs_arn
}
```

Le choix du médium appartient à ce LLD ; l'indépendance et la rétention sont des **intrants** de ce
choix, pas des préférences — c'est la formulation de `V2-ADR-015`, reprise telle quelle.

**Contenu d'un événement** (aucune donnée personnelle en clair, `V2-ADR-006`) :

| Champ | Exemple | Rôle |
|---|---|---|
| `event` | `erasure_accepted` \| `erasure_completed` | distingue l'étape 2 de l'étape 6 |
| `erasureOperationId` | UUID | corrèle les deux événements d'un même effacement |
| `userIdHash` | hash de `userId` | identifie la cible sans porter l'identifiant en clair |
| `tenantId` | — | périmètre du rejeu |
| `erasureCompletedAt` | ISO 8601 | **la donnée dont le rejeu a besoin** : comparer à l'instant T de restauration |
| `documentIdHashes` | liste de hash | permet de rejouer sans relire une table restaurée |

`documentIdHashes` est ce qui rend le rejeu autonome : sans lui, retrouver quels documents effacer
exigerait de lire la table `documents` restaurée, c'est-à-dire celle qui vient précisément d'être
ramenée à un état antérieur à l'effacement.

**Si la précondition P3 (§1.3) n'est pas satisfaite**, ce journal n'existe pas comme source
autoritative. `V2-ADR-015` est explicite : cette précondition **n'admet aucun repli**. Une
restauration PITR reste alors techniquement possible mais réintroduit des données effacées sans
moyen de les retirer — elle doit être traitée comme **interdite**, non comme dégradée (§13.5.3).

### 8.7 L'effacement incomplet est un état, pas un échec silencieux

Rendre la suppression Memory bloquante (§8.3) crée un état que la v0.3 ne connaissait pas : une
entrée `users` porte `erasureRequestedAt` et `erasureOperationId`, mais pas `erasureCompletedAt`.
Les documents sont partis, les vecteurs aussi ; la mémoire est encore là. C'est la conséquence
directe et voulue de la décision, et elle est traitée comme un état nommé.

**Il est observable.** L'absence d'`erasureCompletedAt` sur une entrée dont `erasureRequestedAt` est
renseigné *est* la définition de l'effacement en cours ; elle s'interroge sans journal annexe.
L'alerte d'exploitation se déclenche lorsque cet état **se prolonge** au-delà du seuil de §6.4, et
non lorsqu'un appel échoue — un échec suivi d'une reprise réussie n'est pas un incident.

```text
seuil d'alerte = erasureRequestedAt + erasure_sla_days - residualWindowDays
```

**Il est reprenable.** Chaque étape de §8.4 se termine par une vérification par relecture, donc
chaque étape est rejouable sans effet de bord : supprimer ce qui est déjà supprimé et relire un
namespace vide sont idempotents. La reprise reprend la séquence **à l'étape 3**, sans état
intermédiaire à conserver et **sans nouvelle confirmation `V2-ADR-014`** — la commande a déjà été
confirmée, `erasureOperationId` en est la trace. En V2, la reprise est manuelle, déclenchée par
l'opérateur via le runbook §18.3.

**Il ne rend rien à l'utilisateur.** L'effacement en cours n'est pas un rollback : les données déjà
supprimées ne reviennent pas, et l'accès reste refusé. Le système ne repasse jamais d'un effacement
partiel à un état nominal ; il n'avance que vers la clôture.

## 9. AgentCore Memory — deux natures, deux cycles de vie (V2-ADR-015)

### 9.1 Positionnement — ce que « volatile » qualifie

Memory n'est **sauvegardée nulle part** : aucune sauvegarde n'est configurée, aucun RTO/RPO n'est
engagé, et une indisponibilité déclenche la dégradation « poursuite sans mémoire durable » déjà
actée par la CAM (`architecture/hld/capability-allocation-matrix.md`, Domaine 6). Ce point n'est pas
rediscuté.

Ce que la v0.3 en tirait à tort, c'est une propriété de **rétention**. « Volatile » qualifie ici la
stratégie de sauvegarde ; une donnée peut n'être sauvegardée nulle part et demeurer indéfiniment
dans son magasin primaire. Le corpus V1 en fournit le contre-exemple :
`docs/validation/V1-MEMORY-SECURITY-SUMMARY-FR.md` documente que l'objet du correctif V1 était
précisément de faire **survivre les préférences à la session**, via une stratégie
`USER_PREFERENCE` / `TravelPreferences` sur le namespace `/travel/{actorId}/preferences`, **sans
aucune durée d'expiration configurée**.

En l'état, les enregistrements longue durée étaient donc la donnée personnelle **la plus durable du
système** : ils survivent à la session, n'ont pas de TTL, sont dérivés du contenu conversationnel de
l'utilisateur, et n'étaient couverts par aucune procédure d'effacement vérifiée. Le corpus traitait
comme négligeable la seule donnée pour laquelle il n'avait fixé aucune borne.

### 9.2 Les deux mémoires

| | Mémoire de session | Mémoire longue durée |
|---|---|---|
| Contenu | tours de conversation écrits au fil de l'invocation | préférences extraites par une stratégie Memory |
| Portée | une session | toutes les sessions d'un acteur |
| Écriture | au fil de l'invocation | après le dernier tour réussi (`V2-LLD-003` §2.5) |
| Sensibilité (§2) | `conversationnelle` | **`identité`** |
| Rétention | **durée d'expiration explicite**, paramètre Terraform (§9.3) | **pas d'expiration automatique** — c'est délibéré |
| Suppression sur effacement | couverte par l'expiration | **explicite et vérifiée, sans exception** (§8.3) |
| Bloquante pour `erasureCompletedAt` | non | **oui** |
| Sauvegarde | aucune | aucune |
| Restauration | aucune | aucune |

Deux points méritent d'être énoncés plutôt que déduits.

**La mémoire longue durée n'a délibérément pas d'expiration automatique.** Une préférence qui
s'effacerait seule au bout de N jours détruirait la fonctionnalité que la V1 a construite. Sa borne
n'est pas temporelle : elle est l'effacement — ce qui est précisément pourquoi cet effacement doit
être prouvé (§8.3).

**La mémoire de session reçoit une durée d'expiration explicite, strictement inférieure à la fenêtre
résiduelle.** Ce choix n'est pas cosmétique : il fait entrer la mémoire de session dans le résidu
déjà borné par le PITR (§6.3), au lieu d'en constituer un second, non borné et de nature différente.

### 9.3 Paramètre d'expiration de la mémoire de session

```text
memory_session_ttl_days   paramètre Terraform
contrainte : memory_session_ttl_days < residualWindowDays
```

La valeur exacte relève de l'exploitation ; la contrainte, non. Elle est vérifiée par le guard
(§16). Sa valeur maximale admise par le service reste à établir — précondition P2 (§1.3).

### 9.4 Conséquences pour ce LLD

- Memory n'apparaît dans **aucune** procédure de restauration, donc dans aucun rejeu (§13.5) —
  l'absence de sauvegarde a ici une conséquence utile ;
- la mémoire longue durée **est** incluse dans la suppression coordonnée, de façon explicite et
  vérifiée, et son échec bloque la clôture (§8.3, §8.7) ;
- aucune donnée durable métier ou documentaire ne doit être stockée dans Memory (contrôle
  d'architecture, vérifié en revue) — toute donnée à conserver appartient à `Trips`, `documents`,
  `users` ou `ledger` ;
- **tant que les préconditions P1 et P2 (§1.3) ne sont pas levées, aucune stratégie de mémoire
  longue durée n'est activée en V2.** Si l'une échoue, le repli est l'option C de `V2-ADR-015` : les
  préférences quittent Memory pour une table DynamoDB, ce qui amende la CAM Domaine 6 et
  `V2-ADR-002`. Ce chemin est prévu, pas subi.

## 10. Rétention et TTL — vue synthétique

| Donnée | Rétention | Mécanisme |
|---|---|---|
| `Trips` items sans TTL | illimitée | pas de purge automatique |
| `Trips` items avec `expiresAt` | selon écriture applicative | TTL DynamoDB |
| `documents` items courants (`indexed`) | illimitée sauf effacement | pas de purge |
| `documents` items `superseded` | 90 jours après supersession | script périodique + cycle de vie source |
| `documents` items `quarantined` | 7 jours | TTL DynamoDB (`expiresAt`) |
| `documents` items `deleted` | 30 jours (tombstone) puis purge | script périodique (audit) |
| `ledger` items | 7 jours | TTL DynamoDB (`expiresAt`) |
| `commands` items `pending` | `command_pending_window_minutes` (15 min) + marge | TTL DynamoDB — **purge seule**, l'expiration est transactionnelle (§5.3.4) |
| `commands` items `confirmed` | `command_confirmed_window_seconds` (120 s) + marge | TTL DynamoDB — idem |
| `commands` items `executed` | `command_executed_retention_days` (7 j), **≥ fenêtre d'idempotence** | TTL DynamoDB (`expiresAt`) |
| `users` items sans effacement | illimitée | — |
| `users` items effacés | illimitée (trace) | — |
| S3 `sources/` version courante | illimitée sauf effacement | — |
| S3 `sources/` versions non-courantes | 90 jours après supersession | cycle de vie S3 |
| S3 `restricted/` version courante | illimitée sauf effacement | — (identique à `sources/`) |
| S3 `restricted/` versions non-courantes | 90 jours après supersession | cycle de vie S3 (identique à `sources/`) |
| S3 `quarantine/` | 7 jours | cycle de vie S3 |
| S3 `frontend/` versions non-courantes | 30 jours | cycle de vie S3 |
| S3 `artefacts/` | 90 jours | cycle de vie S3 (`V2-LLD-008`) |
| S3 `tfstate/` | illimitée | pas de purge (audit) |
| S3 Vectors | vit avec `documents` | reconstruit par ingestion |
| Memory — session | `memory_session_ttl_days`, **< `residualWindowDays`** | durée d'expiration configurée sur le service (§9.3) |
| Memory — longue durée | **pas d'expiration** ; borne = effacement explicite vérifié | suppression du namespace de l'acteur (§8.3) |
| Journal d'audit d'effacement | `erasure_audit_retention_days`, **≥ fenêtre PITR** | `retention_in_days` du groupe de journaux (§8.6) |
| Secrets Manager | rotation périodique | selon secret |

Les rétentions ci-dessus sont **des paramètres Terraform** : aucune valeur n'est codée en dur dans
le code applicatif.

### 10.1 La classification ne module aucune rétention (V2-ADR-017)

Aucune ligne du tableau ci-dessus ne dépend de `classification`. C'est une **décision**, pas un
silence, et elle repose sur deux faits de mécanisme :

- **le PITR est table-wide.** Il ne s'exprime pas par item et n'offre aucune opération de rédaction
  (`V2-ADR-015`). Une rétention par classification sur les métadonnées documentaires n'est tout
  simplement pas exprimable dans le mécanisme de durabilité que `V2-ADR-010` impose ;
- **une rétention S3 par classification exigerait un préfixe par niveau.** Les cycles de vie S3 se
  définissent par préfixe, pas par attribut. Porter les trois niveaux dans la clé rendrait **toute**
  reclassification destructive — copie puis suppression, perte de l'historique de versions — alors
  que §4.3.2 les rend immédiates et non destructives, à la seule exception de `restricted`.

Le préfixe `restricted/` n'est pas un contre-exemple : il encode l'**indexabilité**, imposée par la
définition par préfixe des data sources KB, et il porte exactement la même politique de conservation
que `sources/` (§7.2).

### 10.2 Le tombstone conserve la classification (V2-ADR-017)

L'entrée `documents` en `status = deleted`, retenue 30 jours, **conserve son attribut
`classification`**. Une trace d'audit qui ne dirait pas à quel niveau le document supprimé était
classé n'atteste rien d'exploitable. Cette conservation n'entre pas en conflit avec l'effacement
utilisateur (§8.5) : la classification qualifie la ressource, pas la personne.

## 11. Chiffrement au repos

| Magasin | Clé | Justification |
|---|---|---|
| `Trips` | KMS managée AWS (V1 conservé) | continuité V1, données métier standard |
| `documents` | **KMS managée client (CMK dédiée)** | rotation contrôlée, séparation des privilèges d'accès (V2-ADR-006) |
| `ledger` | KMS managée client (CMK dédiée) | même politique que `documents` |
| `commands` | KMS managée client (CMK dédiée) | porte l'autorisation des actions mutantes et le `payload` matérialisé ; sa lecture doit être aussi contrôlée que celle de la cible métier |
| `users` | KMS managée client (CMK dédiée) | données identité |
| S3 `documents` | même CMK que `documents` DynamoDB | cohérence d'accès KMS entre source et métadonnées |
| S3 Vectors | KMS géré par KB / S3V (config) | délégué au service ; en V3 : passage à CMK dédiée si S3V natif l'expose |
| S3 `tfstate` | CMK dédiée `tfstate` | accès restreint aux mains CI/CD |
| Journal d'audit d'effacement (CloudWatch Logs) | CMK logs (`V2-LLD-001`) | contient des hash d'identifiants et la liste des effacements ; sa lecture doit être aussi contrôlée que celle de `users` |
| Secrets Manager | CMK par défaut ou dédiée | selon criticité |

**Contrôle IAM associé :** le rôle FastAPI (`V2-LLD-001`) obtient `kms:Decrypt` uniquement sur les
CMK qu'il doit lire. Aucun rôle applicatif n'a `kms:*` global. Les CMK sont provisionnées par
Terraform (`V2-LLD-005` pour la politique de clé exacte).

## 12. Sauvegarde

### 12.1 Ce qui est activé et non désactivable

- PITR sur `Trips`, `documents`, `ledger`, `commands`, `users` — 35 jours ;
- Versioning S3 sur `documents`, `frontend`, `artefacts`, `tfstate` ;
- Rétention du journal d'audit d'effacement ≥ fenêtre PITR (§8.6).

Ces garanties sont **contrôlées par `terraform_plan_guard.py`** (§16) : tout plan qui les
désactiverait ou détruirait une ressource concernée sans confirmation explicite est bloqué.

**La profondeur du PITR n'est plus un arbitrage de RPO seul (V2-ADR-015).** Ces 35 jours
déterminent aussi `residualWindowDays` (§6.3), donc le plancher d'effacement annonçable :

```text
profondeur de restauration  et  fenêtre résiduelle d'effacement
= le MÊME paramètre, lu dans deux sens opposés
```

Réduire la fenêtre PITR raccourcit le résidu d'effacement et dégrade le RPO ; l'allonger fait
l'inverse. Aucune politique d'effacement ne peut promettre une échéance inférieure à cette fenêtre
sans contredire `V2-ADR-010`. Un changement de cette valeur relève donc des deux décisions à la
fois, et le guard le matérialise en dérivant le plancher du plan lui-même (§16).

### 12.2 Ce qui n'est pas sauvegardé et pourquoi

- **S3 Vectors** : état dérivé. Reconstruction par ingestion (V2-ADR-010 option B). Reprise par KB
  `StartIngestionJob` en V2.
- **Memory** : volatile par conception (§9).
- **Configuration Terraform** : source = dépôt Git.

### 12.3 Ce qui n'est pas couvert en V2 (risque résiduel accepté)

- Perte totale du bucket S3 `documents` (ex. sinistre régional complet) : aucune réplication
  cross-région configurée en V2. Décision différée à un ADR de production (`V2-ADR-010` §RTO).
  Impact en `test` : sur perte totale, ré-upload des documents nécessaire.

## 13. Restauration — procédures

### 13.1 Restauration DynamoDB (PITR)

**RTO cible : quelques minutes** — restauration d'une table vers une **nouvelle table**, bascule
Terraform vers le nouveau nom.

```bash
# 1. Restaurer vers une table de récupération
aws dynamodb restore-table-to-point-in-time \
  --source-table-name test-documents \
  --target-table-name test-documents-restore-YYYYMMDD-HHMM \
  --restore-date-time <iso8601>

# 2. Vérifier : comptage, échantillonnage, cohérence
aws dynamodb scan --table-name test-documents-restore-... --select COUNT

# 3. Bascule contrôlée (voir prérequis de conception §13.1.1) :
#    3a. terraform apply -var="documents_table_name=test-documents-restore-YYYYMMDD-HHMM"
#        (le nom de table est une VARIABLE, pas une valeur codée en dur)
#    3b. terraform plan  (validé par terraform_plan_guard.py — voir §16)
#    3c. terraform apply
#    3d. La table originale n'est PAS supprimée automatiquement (conservation 7 jours minimum)
```

**Point critique :** DynamoDB PITR restaure vers une **nouvelle** table ; la bascule Terraform doit
être testée en DR drill pour valider la procédure sous stress.

#### 13.1.1 Prérequis de conception pour rendre la bascule réellement exécutable (O5, revue PR #35)

La bascule §13.1 étape 3 n'est possible **que si les modules Terraform ne codent pas les noms de
tables en dur**. Sans ce prérequis, une restauration sous incident exigerait de modifier le code
Terraform à chaud — précisément ce qu'on ne veut pas sous stress. Contraintes fixées par ce LLD :

- chaque table lue par un service (`documents`, `Trips`, `users`, `ledger`) expose son nom via une
  **variable Terraform** (`documents_table_name`, etc.) et non une constante ; la valeur par défaut
  est le nom nominal, surchargeable à l'`apply` de restauration ;
- le module publie en **output** le nom effectif de chaque table
  (`output "documents_table_name"`), consommé par les services (task definition FastAPI, §`V2-LLD-001`)
  — la bascule met à jour l'input, les consommateurs suivent l'output ;
- avant de considérer la bascule terminée, **vérifier qu'aucun service ne lit encore l'ancienne
  table** : `aws dynamodb describe-table --table-name <ancienne>` + inspection des variables
  d'environnement/secrets résolus des tâches ECS en cours (`aws ecs describe-tasks`) ;
- le DR drill (§17.2) exécute cette bascule **en environnement `test` isolé** pour prouver que la
  procédure fonctionne sans édition de code — un drill qui exige une modification manuelle du module
  est un échec de conception à corriger, pas une étape normale.

### 13.2 Restauration S3 (versioning, écrasement/suppression accidentelle)

**RTO cible : immédiat** — la version précédente est déjà accessible.

```bash
# 1. Lister les versions de l'objet
aws s3api list-object-versions --bucket <bucket> --prefix <clé>

# 2. Restaurer une version antérieure (copie sur elle-même)
aws s3api copy-object --bucket <bucket> --key <clé> \
  --copy-source "<bucket>/<clé>?versionId=<versionId>"

# 3. Si suppression marker à retirer :
aws s3api delete-object --bucket <bucket> --key <clé> --version-id <deleteMarkerId>
```

### 13.3 Restauration cohérente DynamoDB + S3

**Cas d'usage :** rollback logique après incident applicatif (ex. suppressions massives erronées).

```text
1. Choisir un horodatage T cible (avant l'incident)
2. Restaurer documents (PITR à T) vers une table de récupération
3. REJEU DES EFFACEMENTS (§13.5) — obligatoire, avant toute remise en service
     Rejouer tous les effacements dont erasureCompletedAt > T, depuis le journal
     d'audit (§8.6). Sans cette étape, l'étape 5 tenterait de réindexer des
     documents effacés.
4. Pour chaque documentId subsistant dans la table restaurée avec status = "indexed" :
     a. Vérifier que S3 sources/ ou restricted/<tenantId>/<documentId>/<version> existe
     b. Si absent : la source a été supprimée après T (perte irrécupérable de contenu, à noter)
     c. Vérifier que documents.embeddingSpaceId == espace déclaré par l'index cible (§14.1)
5. Bascule Terraform vers la table restaurée
6. Déclencher une ré-ingestion ciblée sur les documents "indexed"
   (V2 : StartIngestionJob par data source ; V3 : SQS enqueue stage=validate)
7. Attendre la complétion des jobs
8. Vérification : Retrieve renvoie les documents attendus, et AUCUN document effacé
```

**Deux ordres non commutables :**

- DynamoDB restauré **avant** ré-ingestion. L'inverse produirait des chunks orphelins pointant vers
  des documents dont l'entrée `documents` a été perdue ;
- rejeu des effacements **avant** ré-ingestion (étape 3 avant étape 6). L'inverse réindexerait des
  documents effacés — et pour ceux dont les objets S3 ont bien été supprimés, la ré-ingestion
  échouerait bruyamment, ce qui masquerait le vrai problème : les **métadonnées**, elles, seraient
  revenues.

### 13.4 Restauration `users` — ce que le raisonnement de la v0.3 ne couvrait pas

La v0.3 concluait qu'il n'y avait pas de problème :

> « Une entrée `users.erasureCompletedAt` restaurée par PITR **ne réintroduit pas** les documents
> effacés (ils ont été supprimés, pas archivés). »

Le raisonnement est **exact pour la table `users`**, et **sans objet pour le reste**. Une
restauration PITR de `documents` à un instant T antérieur à un effacement réintroduit les entrées de
métadonnées de l'utilisateur effacé — nom de fichier, tenant, classification, versions. Le contenu
ne revient pas ; les métadonnées, si. C'est l'écart que `V2-ADR-015` a relevé, et il est corrigé par
l'étape de rejeu ci-dessous.

Ce qui reste vrai de la v0.3 : PITR restaure la **trace** d'effacement, pas la donnée effacée. Une
demande contraire relèverait d'une exigence légale distincte, hors périmètre (`V2-ADR-015`
§Périmètre exclu).

#### 13.4.1 Restauration `commands` — pourquoi elle ne réautorise rien

Une restauration PITR de `${env}-commands` à un instant T antérieur ramène des commandes dans un
état révolu : une commande alors `confirmed` et depuis exécutée redevient `confirmed`, et une
commande depuis expirée redevient exécutable *en apparence*. La question mérite d'être posée
explicitement, parce qu'une réponse négligente rouvrirait la faille que `V2-ADR-014` ferme.

**Elle ne réautorise rien, et c'est `confirmedExpiresAt` qui le garantit.** L'exécution est
conditionnée par `confirmedExpiresAt > maintenant` (§5.3.3). Une fenêtre de 120 secondes restaurée
depuis un instant antérieur à la restauration elle-même est nécessairement échue : aucune procédure
de restauration ne s'exécute en moins de deux minutes. La condition échoue, la transaction est
refusée, et l'effet de bord n'est pas rejoué.

C'est la contrepartie concrète de la règle du §5.3.4. Une expiration reposant sur le TTL n'offrirait
pas cette propriété : le TTL restauré porterait une échéance passée, l'item resterait lisible jusqu'à
sa repurge, et rien dans la condition d'exécution ne s'y opposerait. La table `commands` reste donc
dans le périmètre PITR — contrairement au journal d'audit d'effacement (§8.6), dont l'exclusion tient
à une autre propriété : lui n'a aucun horodatage qui rende inoffensive sa restauration.

Ce que la restauration peut en revanche produire : une commande `executed` ramenée à `confirmed`
perd son `result`, donc la capacité de répondre à un rejeu par le résultat initial (invariant I6).
Le rejeu ne produira pas de second effet de bord — la fenêtre est échue — mais renverra
`COMMAND_EXPIRED` là où il aurait renvoyé le résultat. C'est une **dégradation de la qualité de
réponse, pas de la garantie de sûreté** ; elle est acceptée et n'appelle pas de rejeu (§13.5).

### 13.5 Rejeu des effacements après restauration (V2-ADR-015)

#### 13.5.1 La règle

> **Toute restauration ramenant un magasin à un instant T est suivie, avant remise en service, du
> rejeu de tous les effacements dont `erasureCompletedAt` est postérieur à T.**

La règle s'applique à **toute** restauration de table, pas seulement à la séquence cohérente §13.3.
Elle est la contrepartie opérationnelle du modèle d'effacement retenu : sans elle, la fenêtre
résiduelle déclarée en §6.3 n'est fermée par aucun mécanisme et redevient une déclaration
invérifiable.

#### 13.5.2 La source du rejeu

**Ce n'est pas la table `users`** — elle est elle-même soumise au PITR et peut avoir été ramenée en
arrière par la restauration qu'il s'agit de corriger (§8.6). La source autoritative est le **journal
d'audit d'effacement** (§8.6), append-only et hors périmètre PITR.

```text
Pour chaque événement erasure_completed du journal avec erasureCompletedAt > T :
  1. Relire l'entrée users (restaurée) : si erasureCompletedAt absent ou < T,
     l'effacement a été perdu par la restauration -> rejeu requis
  2. Pour chaque documentIdHash de l'événement :
       supprimer l'entrée documents correspondante (toutes versions)
       supprimer les objets S3 correspondants (toutes versions, aucun marqueur)
  3. Réécrire users.erasureRequestedAt / erasureCompletedAt / erasureDurableAt
     / erasureOperationId aux valeurs du journal
  4. Vérification d'absence (§8.4 étape 5)
```

Le rejeu est **idempotent** : supprimer ce qui est déjà supprimé et réécrire des horodatages
identiques sont sans effet de bord. Il ne requiert **aucune nouvelle confirmation `V2-ADR-014`** —
la commande d'origine a été confirmée, et `erasureOperationId` en est la trace.

Memory n'entre pas dans le rejeu : elle n'est ni sauvegardée ni restaurée (§9.4), donc la
restauration ne peut pas la ramener en arrière.

**En V2, le rejeu est manuel**, exécuté par l'opérateur via le runbook §18.5 et lors du DR drill
(§17.2). C'est un choix : il est rare, il suit une restauration qui est elle-même une opération
encadrée, et son automatisation prématurée introduirait un traitement destructeur déclenché
automatiquement — risque supérieur au gain. En V3, il est automatisé depuis le journal.

#### 13.5.3 Si la précondition P3 n'est pas levée

`V2-ADR-015` est explicite : la précondition d'indépendance du journal **n'admet aucun repli**.
Aucune décision ne rend le rejeu superflu.

Tant que P3 (§1.3) n'est pas satisfaite, une restauration PITR reste techniquement possible mais
réintroduit des données effacées sans moyen de les retirer. Elle est alors traitée comme
**interdite**, non comme dégradée : le runbook §18.1 porte cette garde en première étape, et le DR
drill (§17.2) ne peut pas être considéré comme passé.

C'est la seule interdiction opérationnelle de ce LLD, et elle est délibérée : une procédure de
restauration qui réintroduit silencieusement des données effacées est pire qu'une restauration
indisponible.

## 14. Réhydratation S3 Vectors

### 14.1 Principe (V2-ADR-010 option B, borné par V2-ADR-013)

S3 Vectors est un **état dérivé**. Il n'est ni sauvegardé, ni exporté : il est **reconstruit depuis
S3 (sources) + `documents` (métadonnées)**. La ré-ingestion complète est le mécanisme de reprise.

`V2-ADR-013` ajoute à ce principe une contrainte que `V2-ADR-010` n'énonçait pas :

> **Une reconstruction est toujours totale à l'échelle d'un index, et se fait dans l'espace déclaré
> par cet index — jamais dans celui de la configuration courante.**

La raison est un mode de panne, pas une préférence. Une reconstruction produit des vecteurs avec la
configuration active **au moment de la reconstruction**. Si un changement d'espace est intervenu
entre la sauvegarde et la restauration, reconstruire une partie du corpus avec la configuration
courante et laisser le reste dans l'ancien espace produit un index mêlant deux espaces — qui répond
sans erreur, avec des scores crédibles, et des résultats faux (§4.3.1).

Deux conséquences opérationnelles :

| Situation | Traitement |
|---|---|
| L'espace de l'index restauré == espace de la configuration courante | **restauration** : ré-ingestion totale de l'index, procédure §14.2 |
| L'espace de l'index restauré ≠ espace de la configuration courante | **ce n'est pas une restauration, c'est une migration** : elle suit la séquence de bascule §14.5, évaluation comprise. La reconstruire « au passage » dans le nouvel espace est interdit |

La vérification est portée par l'étape 4c de §13.3 et par `check_dv_consistency.py` (§16.3).

### 14.2 Procédure V2 (via KB)

```text
1. S'assurer que S3 (sources) et documents sont dans un état cohérent (§13.3 si restauration)
2. Déclencher la resynchronisation KB de la data source :
     aws bedrock-agent start-ingestion-job \
       --knowledge-base-id $KB_ID --data-source-id $DS_ID
3. Suivre l'avancement :
     aws bedrock-agent get-ingestion-job --ingestion-job-id <id>
4. À la complétion :
     - Réconcilier documents.chunkCount et status
     - Exécuter un Retrieve sur un échantillon de requêtes du dataset d'éval (V2-ADR-018)
     - Vérifier que les métriques recall@k / precision@k sont dans la marge d'écart tolérée
```

**RTO estimé V2 :** dépend du volume à réingérer et des quotas KB en `eu-west-3`. Cible initiale :
**sous 4 heures pour le corpus de démonstration** (V2-ADR-010) ; à réviser lorsque le corpus dépasse
un ordre de grandeur.

### 14.3 Procédure V3 (via pipeline applicatif)

En V3, la ré-ingestion massive utilise le pipeline SQS + worker ECS (`V2-ADR-004`) : enqueue en
masse des documents `indexed` à ré-ingérer avec `stage = validate`, montée en charge des workers
ECS par autoscaling piloté par la profondeur de file (`V2-LLD-001` §9.2).

Le contrat de **cohérence source/métadonnées/index** (§14.4) est identique dans les deux phases.

### 14.4 Cohérence source / métadonnées / index

L'invariant à préserver, quel que soit le mécanisme d'ingestion :

```text
Pour tout chunk c dans S3 Vectors :
  ∃ documentId, version tel que :
    c.metadata.documentId == documentId
    c.metadata.version    == version
    documents[tenantId#documentId].status == "indexed"
    documents[tenantId#documentId].version == version (ou "superseded" en cours de bascule)
    S3 sources/<tenantId>/<documentId>/v<version>/  existe
```

**Test de vérification (§18 et V2-LLD-009) :** échantillonner N chunks depuis S3 Vectors et vérifier
que les trois autres coordonnées existent. Un écart > 0 est un défaut de cohérence bloquant.

L'invariant porte une cinquième coordonnée depuis `V2-ADR-013` :

```text
    documents[tenantId#documentId].embeddingSpaceId == embeddingSpaceId de l'index interrogé
```

Elle se vérifie sans échantillonnage — c'est une égalité sur une valeur unique par index — et son
échec est de nature différente des quatre autres : un chunk orphelin dégrade le rappel, un espace
divergent rend **tout** le classement arbitraire. C'est pourquoi la divergence d'espace est
fail-closed côté retrieval (`V2-LLD-002` §7.1) et non simplement signalée.

### 14.5 Migration d'espace d'embedding et période de grâce (V2-ADR-013)

Un changement de modèle d'embedding **n'est pas une mise à jour d'index : c'est la création d'un
index**. La séquence est décidée par `V2-ADR-013` (option B — index parallèle, évaluation, bascule
de pointeur) ; ce LLD en porte les conséquences côté données.

```text
1. Création d'un index cible portant le nouvel embeddingSpaceId
   L'index courant continue de servir, sans modification.
2. Réindexation complète du corpus depuis S3, qui reste la source de vérité
3. Exécution du dataset d'évaluation de V2-ADR-018 sur l'index cible, comparaison
   aux valeurs de référence de l'index courant.
   Un écart au-delà du seuil de V2-ADR-018 INTERDIT la bascule.
4. Bascule du pointeur applicatif — atomique, UNIQUE POINT DE NON-RETOUR
   V2 : pointeur KB_ID / KB_DATA_SOURCE_ID    V3 : pointeur d'index de l'adapter
5. Période de grâce : l'index précédent est CONSERVÉ (§14.5.1)
6. Suppression de l'index précédent à l'issue de la période de grâce
```

L'étape 3 est ce qui distingue cette séquence d'un simple remplacement : un modèle d'embedding plus
récent n'est pas meilleur sur un corpus donné par construction — le domaine, la langue et la taille
des chunks font varier le résultat. **Sans mesure, une migration d'embedding est un pari.**

En V2, un changement de modèle impose vraisemblablement une **nouvelle base de connaissances**, le
modèle étant fixé à la création de la KB (précondition P6, §1.3). Cette contrainte n'est pas une
gêne : elle réalise mécaniquement la stratégie d'index parallèle.

#### 14.5.1 Période de grâce de l'index précédent

`V2-ADR-013` renvoie explicitement à ce LLD la définition de cette période. Elle est fixée ici :

```text
embedding_index_grace_days   paramètre Terraform
valeur retenue : 30 jours
contrainte    : >= durée d'un cycle complet d'évaluation V2-ADR-018 sur le corpus
```

**Ce que la période de grâce achète.** Pendant sa durée, le retour arrière est une **bascule inverse
du pointeur** — opération atomique, de l'ordre de la seconde — et non une reconstruction complète du
corpus. C'est la différence entre un incident de quelques secondes et un incident de plusieurs
heures, sur un chemin où la panne est silencieuse et peut n'être détectée qu'à l'usage.

**Pourquoi 30 jours, et pourquoi la contrainte.** Une régression de qualité d'embedding ne se
manifeste pas par une alarme : elle se manifeste par des réponses moins pertinentes, constatées par
des utilisateurs sur plusieurs jours. Une période inférieure au temps qu'il faut pour rejouer une
évaluation complète rendrait la garantie de retour arrière théorique. La valeur est un paramètre ;
la contrainte n'en est pas un.

**Ce que la période de grâce coûte.** Le stockage vectoriel est **doublé** pendant toute sa durée,
en plus du coût de recalcul complet des embeddings du corpus. Les deux sont des entrées pour
`V2-LLD-007` (`V2-ADR-013` §Conséquences), qui n'est pas encore rédigé.

**Ce qu'elle ne couvre pas.** Passé le délai, l'index précédent est supprimé et un retour arrière
redevient une migration complète, évaluation comprise. La suppression est donc elle-même une
décision d'exploitation, pas une purge automatique silencieuse : elle est tracée au même titre
qu'une bascule.

#### 14.5.2 Délai de remise en service — grandeur mesurée, pas estimée

`V2-ADR-012` a établi que le cycle de vie d'un modèle Bedrock est subi (`Active`, puis `Legacy` avec
un préavis d'au moins six mois, puis échec des appels), et sa sonde périodique **couvre également le
modèle d'embedding configuré**.

La conséquence diffère de celle d'un modèle de génération : perdre l'accès au modèle d'embedding ne
dégrade pas le retrieval, il **l'arrête**. Les vecteurs stockés restent lisibles, mais plus aucune
requête ne peut être projetée dans leur espace. **Un index dont le modèle est mort n'est pas
dégradé, il est inerte.**

Le préavis de six mois n'est donc utile que s'il excède le délai de remise en service :

```text
délai de remise en service = recalcul complet des embeddings du corpus
                           + évaluation V2-ADR-018
                           + bascule
```

Ce délai croît avec le corpus. Il est **mesuré, pas estimé** : la première migration réalisée en
fournit la valeur de référence, et cette valeur devient le seuil d'alerte de la sonde de cycle de
vie. Cette mesure fait partie des preuves attendues (§17.1).

## 15. Cohérence en cas de restauration partielle

`V2-ADR-010` exige qu'aucun vecteur orphelin ne subsiste après restauration. La séquence §13.3 le
garantit **si elle est respectée dans l'ordre**. Deux garde-fous supplémentaires :

- **Vérification préalable à toute ré-ingestion massive** : script `scripts/check_dv_consistency.py`
  (**artefact planifié, contrat en §16.3** — non encore créé) qui liste les
  `documents.status = indexed` sans objet S3 correspondant. Ces documents doivent être passés à
  `status = "failed"` avant la ré-ingestion, pas ignorés.
- **Métrique post-restauration** : nombre de chunks dans S3 Vectors ± X% du `sum(chunkCount)` de
  `documents.status = indexed`. Un écart supérieur à la marge alerte (`V2-LLD-007`).

## 16. Contrôles Terraform (`terraform_plan_guard.py`)

`V2-ADR-010` demande d'étendre le guard existant. Ce LLD fixe les règles bloquantes précises :

### 16.1 Règles booléennes (présence, activation, destruction)

| Règle | Ressource | Comportement bloqué |
|---|---|---|
| PITR obligatoire | `aws_dynamodb_table` tables `Trips`, `documents`, `ledger`, `commands`, `users` | plan qui passe `point_in_time_recovery.enabled = false` |
| Destruction interdite | mêmes tables | plan qui contient `destroy` sans variable `CONFIRM_DESTROY_DYNAMODB=<table_name>` |
| Versioning obligatoire | `aws_s3_bucket_versioning` `documents`, `frontend`, `artefacts`, `tfstate` | plan qui passe `status = Suspended` |
| Destruction interdite | buckets S3 versionnés + KMS CMK utilisées | plan qui contient `destroy` sans variable `CONFIRM_DESTROY_S3=<bucket>` ou `CONFIRM_DESTROY_KMS=<key>` |
| SSE-KMS obligatoire | `documents`, `ledger`, `commands`, `users` DynamoDB et bucket `documents` | plan qui retire `server_side_encryption` ou passe à SSE-S3 sur `documents` bucket |
| Colocalisation transactionnelle | `${env}-commands` et la cible métier d'une action mutante (`Trips`) | plan qui les placerait dans deux régions ou deux comptes — `TransactWriteItems` deviendrait inapplicable et la garantie de `V2-ADR-014` retomberait sur « vérifier puis écrire » (§5.3.3) |
| Public block obligatoire | tous buckets S3 | plan qui met un `block_public_*` à `false` |
| Indépendance du journal d'effacement | `aws_cloudwatch_log_group.erasure_audit` | plan qui porterait le journal d'effacement sur une ressource couverte par le PITR (table DynamoDB) — l'indépendance de §8.6 est une contrainte de plan, pas une convention |
| Destruction interdite | `aws_cloudwatch_log_group.erasure_audit` | plan qui contient `destroy` sans `CONFIRM_DESTROY_ERASURE_AUDIT` — sa perte prive le rejeu (§13.5) de sa source |

### 16.2 Règles de borne — un mode de contrôle nouveau (V2-ADR-015)

`V2-ADR-015` l'a relevé : toutes les règles ci-dessus sont **booléennes** — une ressource détruite,
un drapeau désactivé. Les trois règles suivantes exigent de **comparer des valeurs numériques dans
le plan**, capacité que `terraform_plan_guard.py` n'a pas aujourd'hui. Sans cette extension, un
plancher pourrait être franchi par un simple changement de variable.

| Règle | Expression | Ce que son absence permettrait |
|---|---|---|
| Plancher d'effacement | `erasure_sla_days >= residualWindowDays` où `residualWindowDays = max(fenêtres PITR de Trips, documents, users, ledger, commands)` | Annoncer un délai d'effacement que l'architecture ne peut pas tenir (§6.4) |
| Rétention du journal | `erasure_audit_retention_days >= max(fenêtres PITR)` | Une restauration au bord de la fenêtre PITR ne disposerait plus de la liste des effacements à rejouer (§8.6) |
| Expiration mémoire de session | `memory_session_ttl_days < residualWindowDays` | La mémoire de session constituerait un second résidu, non borné et de nature différente de celui du PITR (§9.3) |
| Fenêtre d'exécution bornée | `command_confirmed_window_seconds <= 300` | Une commande confirmée puis annulée resterait exécutable plus longtemps que le délai d'annulation attendu par `V2-ADR-011` (`V2-LLD-004 §10.2`) |
| Idempotence non dégradée | `command_executed_retention_days >= ledger_ttl_days` | Les mutations passées par une commande ayant quitté le ledger (§5.1), une rétention plus courte offrirait une fenêtre de non-rejeu inférieure à celle déjà tenue en V1 — invariant I7 de `V2-LLD-004` |

Trois propriétés de ces règles méritent d'être notées.

**Le membre droit est calculé, pas saisi.** `residualWindowDays` se dérive des fenêtres PITR
présentes **dans le plan lui-même**. Un plan qui allongerait la fenêtre PITR d'une seule table
déplacerait donc le plancher, et pourrait faire échouer la règle sans qu'`erasure_sla_days` ait
changé. C'est le comportement voulu : la fenêtre résiduelle est une propriété du système, pas d'une
table (§6.3).

**La comparaison est stricte pour la mémoire de session, large pour les deux autres.** L'expiration
de session doit être *strictement* inférieure pour entrer dans le résidu existant ; une égalité en
ferait une borne coïncidente sans marge.

**Un `erasure_sla_days` au plancher exact est valide** mais réduit à zéro le seuil d'alerte de §6.4.
Le guard ne l'interdit pas — c'est une décision d'exploitation, pas une erreur de configuration.

Le guard est un script CI exécuté avant `terraform apply` (`V2-LLD-008`). Une violation renvoie un
code d'échec non contournable en CI ; en local, la confirmation explicite passe par variable
d'environnement (jamais par flag CLI, pour éviter les accidents).

### 16.3 Scripts d'exploitation planifiés (à créer à l'implémentation)

Les runbooks §15 et §18 s'appuient sur deux scripts qui **n'existent pas encore** : ils sont des
**artefacts planifiés**, créés à l'implémentation (périmètre outillage, aligné sur `V2-LLD-009`),
pas des outils disponibles à ce stade documentaire pré-G2. Ce LLD fixe leur contrat pour que la
future implémentation soit sans ambiguïté. À l'inverse, `scripts/terraform_plan_guard.py` et
`scripts/run_industrial_test_suite.py` **existent déjà** dans le dépôt et sont réutilisés tels quels.

| Script (planifié) | Entrées | Sortie | Rôle |
|---|---|---|---|
| `scripts/check_dv_consistency.py` | `--table <documents>`, `--bucket <sources>`, `--index-space <embeddingSpaceId>` (optionnel), `--sample N` (optionnel) | code 0 si cohérent, code ≠ 0 + rapport JSON listant les écarts, séparés par nature | Vérifier l'invariant §14.4 : tout `documents.status = indexed` a un objet S3 source correspondant sous `sources/` **ou** `restricted/`, et signaler les `indexed` sans source (à repasser `failed` avant ré-ingestion). Avec `--index-space`, vérifie en outre l'égalité `documents.embeddingSpaceId == espace de l'index` (§4.3.1) — écart de nature distincte, rapporté séparément car il invalide le classement entier et non un document |
| `scripts/run_rag_eval.py` | `--dataset <ref>`, `--baseline <artefact.json>` | rapport JSON (recall@k, precision@k, groundedness, couverture citations) + statut PASS/FAIL vs baseline | Rejouer le dataset d'évaluation retrieval (`V2-ADR-018`) après réhydratation et comparer aux métriques pré-incident. Sert aussi de garde à l'étape 3 de la migration d'espace (§14.5) |
| `scripts/replay_erasures.py` | `--log-group </env/erasure-audit>`, `--since <T>`, `--table <documents>`, `--bucket <sources>`, `--dry-run` | code 0 si le rejeu est complet, rapport JSON des effacements rejoués et des vérifications d'absence | Rejouer les effacements dont `erasureCompletedAt > T` après une restauration (§13.5). `--dry-run` liste sans supprimer — mode par défaut du DR drill avant exécution réelle |

Tant que ces scripts ne sont pas créés, les runbooks §18.2, §18.4 et §18.5 qui les invoquent sont
**non exécutables** : ils décrivent la procédure cible, pas une capacité présente. Cette limite est
explicitement portée au périmètre d'implémentation, pas masquée.

`replay_erasures.py` est le seul des trois dont l'absence a une conséquence **de sécurité** et non
d'exploitation : sans lui, le rejeu de §13.5 doit être exécuté à la main depuis les événements du
journal, ce qui reste possible mais devient une opération à risque d'omission. Tant qu'il n'existe
pas, le DR drill (§17.2) est la seule occasion où la procédure est éprouvée.

## 17. Tests et preuves

### 17.1 Matrice de preuves

| Preuve attendue | Type | Bloquant |
|---|---|---|
| PITR restauration `documents` : comptage identique à référence | intégration DR drill | **Oui** |
| PITR restauration `Trips` : comptage identique | intégration DR drill | **Oui** |
| Suppression documentaire : 0 objet S3 **toutes versions et aucun marqueur**, 0 chunk KB, `documents.status = deleted` | intégration | **Oui** |
| Effacement utilisateur : aucun objet S3 sous le préfixe de l'utilisateur **toutes versions confondues**, aucun marqueur masquant une version conservée | intégration | **Oui** |
| Effacement utilisateur : `Retrieve` filtré sur le tenant et l'utilisateur effacé renvoie **0 chunk** | intégration | **Oui** |
| Effacement utilisateur : relecture du namespace Memory de l'acteur effacé renvoie **0 enregistrement longue durée** | intégration | **Oui** |
| Effacement utilisateur : `erasureCompletedAt` **et** `erasureDurableAt` renseignés, le second = premier + `residualWindowDays` | intégration | **Oui** |
| **Échec simulé de la suppression Memory** : `erasureCompletedAt` **n'est pas écrit** ; l'alerte se déclenche au seuil de §6.4 ; la reprise après rétablissement clôture sans nouvelle confirmation ni effet de bord | intégration négative | **Oui** |
| **Preuve centrale du rejeu (§17.2)** : restauration PITR antérieure à un effacement, **suivie du rejeu**, ne réintroduit aucune métadonnée de l'utilisateur effacé — **et la même restauration sans rejeu la réintroduit** | DR drill, deux volets | **Oui** |
| Rétention du journal d'effacement ≥ fenêtre PITR, **et** journal porté par aucune ressource couverte par le PITR | statique sur plan Terraform | **Oui** |
| Plan fixant `erasure_sla_days` sous le plancher : bloqué par le guard | statique CI | **Oui** |
| Plan fixant `memory_session_ttl_days ≥ residualWindowDays` : bloqué par le guard | statique CI | **Oui** |
| Événements de session au-delà de la durée d'expiration configurée : plus lisibles | intégration | **Oui** |
| Deux acteurs distincts ne partagent aucun enregistrement de mémoire longue durée, avant comme après un effacement de l'un des deux | intégration isolation | **Oui** |
| Cohérence après restauration : aucun chunk orphelin sur échantillon de N | intégration DR drill | **Oui** |
| **Écriture d'un vecteur d'un espace étranger dans un index** : refusée, et non acceptée puis détectée ultérieurement | intégration négative | **Oui** |
| **Restauration après changement d'espace** : la reconstruction se fait dans l'espace déclaré par l'index restauré ; un mélange d'espaces est impossible à produire par la procédure | DR drill | **Oui** |
| `terraform_plan_guard.py` bloque désactivation PITR / versioning / destroy sans confirm | statique CI | **Oui** |
| Document `restricted` : absent de l'index, absent du `retrievalContext`, présent en lecture directe pour son propriétaire | intégration | **Oui** |
| Transition vers `restricted` : aucune version non-courante atteignable à l'ancien préfixe après l'opération | intégration négative | **Oui** |
| Tombstone `status = deleted` : `classification` conservée | intégration | Oui |
| RTO S3V mesuré ≤ cible sur corpus de démonstration | DR drill | Oui (métrique publiée) |
| **Délai de remise en service** mesuré sur une migration d'espace de test, enregistré comme valeur de référence du seuil d'alerte de cycle de vie (§14.5.2) | DR drill / migration de test | Oui (métrique publiée) |
| **Retour arrière après bascule d'espace** : effectué par bascule inverse du pointeur, sans reconstruction, dans la période de grâce, vérifié sur le même dataset | migration de test | Oui |
| Métriques qualité retrieval post-réhydratation dans marge d'éval (`V2-ADR-018`) | qualité DR drill | Oui |
| Ledger d'idempotence : TTL effectif à 7 jours | intégration | Oui |
| **Exécution d'une commande hors fenêtre `confirmed`** : la transaction est refusée et **aucun effet de bord n'est appliqué**, y compris lorsque l'item n'a pas encore été purgé par le TTL (§5.3.4) | intégration négative | **Oui** |
| **Exécution d'une commande par un autre acteur ou un autre tenant** : refusée, avec le même code que pour une commande inexistante (`V2-LLD-004 §6.3`) | intégration négative | **Oui** |
| **Double exécution concurrente du même `commandId`** : une seule aboutit, une seule mutation métier existe, la seconde renvoie le résultat initial | intégration concurrence | **Oui** |
| **Restauration PITR de `commands`** : aucune commande restaurée n'est exécutable, la fenêtre `confirmed` étant échue (§13.4.1) | DR drill | **Oui** |
| Aucune mutation passée par une commande n'écrit d'entrée dans le ledger ; aucun scope `trip-mutation` n'existe (§5.1) | intégration + statique | **Oui** |
| GSI `by-operation` : une requête portant l'`operationId` d'un autre tenant ne renvoie aucune commande | intégration isolation | **Oui** |
| Plan plaçant `commands` et la cible métier hors d'une même région/compte : bloqué par le guard | statique CI | **Oui** |
| Aucune donnée durable métier ou documentaire dans Memory (revue statique) | statique | Oui |

### 17.2 DR drill trimestriel

Fréquence trimestrielle ou avant chaque release majeure (`V2-ADR-010`). Contenu minimum :

1. Restaurer `documents` PITR vers une table de récupération ;
2. **Rejeu des effacements** (§13.5) depuis le journal d'audit, avant toute remise en service ;
3. Bascule Terraform contrôlée (dry run + apply en environnement `test` isolé) ;
4. Ré-ingestion complète via KB (V2) ou pipeline (V3), **dans l'espace déclaré par l'index restauré**
   (§14.1) ;
5. Exécution du dataset d'éval retrieval (`V2-ADR-018`) et comparaison avec la baseline ;
6. Publication des preuves au format standard (`scripts/run_industrial_test_suite.py` : JSON, SHA
   Git, horodatage, durée, statut).

#### 17.2.1 Scénario d'effacement — la preuve centrale, en deux volets

`V2-ADR-015` fait de ce scénario la seule preuve du corpus qui démontre que la fenêtre résiduelle
est fermée **par un mécanisme** et non par une déclaration. Il est ajouté au drill :

```text
Préparation
  a. Créer un utilisateur de test avec N documents indexés
  b. Noter T0

Effacement
  c. Effacer l'utilisateur (§8.4) ; vérifier erasureCompletedAt et erasureDurableAt
  d. Noter T1 = erasureCompletedAt

VOLET 1 — restauration AVEC rejeu (comportement attendu)
  e. Restaurer documents PITR à T0 (antérieur à l'effacement)
  f. Rejouer les effacements depuis le journal (§13.5), erasureCompletedAt > T0
  g. ATTENDU : aucune métadonnée de l'utilisateur effacé n'est présente

VOLET 2 — restauration SANS rejeu (contre-épreuve)
  h. Restaurer documents PITR à T0, dans un environnement isolé
  i. NE PAS rejouer
  j. ATTENDU : les métadonnées de l'utilisateur effacé SONT présentes
```

**Le volet 2 n'est pas facultatif.** Sans lui, le test passe tout aussi bien lorsque le rejeu ne fait
rien — il n'attesterait alors que l'absence de donnée, ce qui est aussi le résultat d'un effacement
qui n'aurait jamais eu à être rejoué. C'est la contre-épreuve qui donne au volet 1 sa valeur
probante.

Un drill dont le volet 2 échoue (les métadonnées ne reviennent pas sans rejeu) n'est pas un succès :
c'est le signe que le scénario ne teste pas ce qu'il prétend tester, et il doit être corrigé avant
d'être compté comme preuve.

**Le volet 2 s'exécute en environnement `test` isolé**, et son état final est détruit : il produit
délibérément des données qui n'auraient pas dû exister.

## 18. Exploitation — runbooks

### 18.1 Restaurer `documents` à un point dans le temps

```bash
# 0. GARDE PRÉALABLE (§13.5.3) : le journal d'audit d'effacement existe-t-il,
#    est-il hors périmètre PITR et sa rétention couvre-t-elle la fenêtre ?
#    Si NON -> la restauration est INTERDITE, pas dégradée. Arrêter ici.
aws logs describe-log-groups --log-group-name-prefix /test/erasure-audit

# 1. Identifier l'horodatage cible (avant incident)
export T="2026-07-01T14:30:00Z"

# 2. Restaurer PITR
aws dynamodb restore-table-to-point-in-time \
  --source-table-name test-documents \
  --target-table-name test-documents-restore-$(date +%Y%m%d-%H%M) \
  --restore-date-time $T

# 3. Vérifier la restauration
aws dynamodb describe-table --table-name test-documents-restore-...

# 4. REJEU DES EFFACEMENTS — obligatoire avant remise en service (§13.5, §18.5)
python3 scripts/replay_erasures.py \
  --log-group /test/erasure-audit --since $T \
  --table test-documents-restore-... --bucket test-documents-sources --dry-run
# puis, après revue du rapport, sans --dry-run

# 5. Vérifier cohérence avec S3 sources et espace d'embedding (script §16.3)
python3 scripts/check_dv_consistency.py \
  --table test-documents-restore-... \
  --bucket test-documents-sources \
  --index-space "$EMBEDDING_SPACE_ID"

# 6. Bascule Terraform (voir §13.1 étape 3)
```

### 18.2 Réhydrater S3 Vectors après incident

```bash
# 1. Vérifier la cohérence source/métadonnées (§15)
python3 scripts/check_dv_consistency.py --table test-documents --bucket test-documents-sources

# 2. Déclencher la resync KB
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id $KB_ID --data-source-id $DS_ID

# 3. Suivre la complétion (polling ou event bridge)
aws bedrock-agent get-ingestion-job --knowledge-base-id $KB_ID \
  --data-source-id $DS_ID --ingestion-job-id <id>

# 4. Post-réhydratation : dataset d'éval retrieval
python3 scripts/run_rag_eval.py --dataset test/rag_eval_v1 \
  --baseline artefacts/rag_baseline_pre_incident.json
```

### 18.3 Effacer un utilisateur

```bash
# 1. Requête admin (nécessite scope admin, V2-LLD-005)
#    La demande est une action mutante V2-ADR-014 : matérialisée puis confirmée
#    hors du chemin du modèle.
POST /admin/users/<userId>/erase
Content-Type: application/json
{ "reason": "user request", "operationId": "<uuid>" }

# 2. Suivre l'avancement
GET /admin/users/<userId>
=> { "erasureRequestedAt": "...",
     "erasureCompletedAt": null | "...",
     "erasureDurableAt":   null | "..." }

# 3. Preuves : vérifier absence des documents
GET /admin/users/<userId>/documents
=> [] (liste vide après complétion)
```

**Ce que signifient les deux horodatages** — à dire tel quel si une attestation est demandée :
`erasureCompletedAt` atteste l'**effacement logique** (aucun magasin en ligne ne retourne la
donnée) ; `erasureDurableAt` atteste la **fin** de l'effacement (plus aucune copie restaurable).
C'est le second qui est communiqué.

#### 18.3.1 Reprendre un effacement incomplet

**Symptôme :** l'entrée `users` porte `erasureRequestedAt` et `erasureOperationId` mais pas
`erasureCompletedAt`, et l'alerte de §8.7 s'est déclenchée. Cause la plus fréquente : la suppression
Memory de l'étape 4 a échoué, ce qui est bloquant depuis `V2-ADR-015`.

```bash
# 1. Identifier les effacements en cours
aws dynamodb scan --table-name test-users \
  --filter-expression "attribute_exists(erasureRequestedAt) AND attribute_not_exists(erasureCompletedAt)"

# 2. Diagnostiquer l'étape bloquée — les vérifications sont idempotentes
#    S3 :
aws s3api list-object-versions --bucket test-documents-sources \
  --prefix "sources/<tenantId>/" --query 'length(Versions)'
#    Memory : relecture du namespace de l'acteur (doit renvoyer 0 enregistrement)

# 3. REPRENDRE À L'ÉTAPE 3 de §8.4 — pas à l'étape 1
#    Rejouer la même commande, avec le MÊME erasureOperationId :
POST /admin/users/<userId>/erase
{ "operationId": "<erasureOperationId EXISTANT, relu depuis users>" }
```

**Trois règles de la reprise :**

- **on reprend à l'étape 3, jamais à l'étape 1.** Chaque étape de §8.4 se termine par une
  vérification par relecture, donc chaque étape est rejouable sans effet de bord : supprimer ce qui
  est déjà supprimé et relire un namespace vide sont idempotents ;
- **aucune nouvelle confirmation `V2-ADR-014` n'est requise.** La commande a déjà été confirmée et
  `erasureOperationId` en est la trace ; en créer une nouvelle produirait deux commandes pour un seul
  effacement ;
- **la reprise ne rend rien à l'utilisateur.** Les données déjà supprimées ne reviennent pas et
  l'accès reste refusé. Le système n'avance que vers la clôture (§8.7).

Si la reprise échoue de façon répétée sur Memory, la question à instruire est la précondition P1
(§1.3), pas la reprise elle-même.

### 18.4 Diagnostiquer un chunk orphelin

```bash
# 1. Symptôme : Retrieve renvoie un chunk dont documents[tenantId#documentId] est absent
# 2. Vérifier la cohérence
python3 scripts/check_dv_consistency.py --sample 1000
# 3. Si écart confirmé :
#    - Cause probable : suppression documentaire interrompue entre étapes 3 et 5 (§8.2)
#    - Réparation : relancer la suppression du documentId concerné
```

**Cas particulier — chunk d'un utilisateur effacé.** Si le `documentId` orphelin appartient à un
utilisateur dont `users.erasureCompletedAt` est renseigné, la cause n'est pas une suppression
interrompue : c'est une **restauration sans rejeu** (§13.5). La réparation n'est pas de relancer une
suppression unitaire mais d'exécuter le rejeu complet (§18.5), puis d'instruire pourquoi la
restauration a omis l'étape.

### 18.5 Rejouer les effacements après une restauration

**Quand :** après **toute** restauration de table ramenant un magasin à un instant T, avant remise en
service. Pas seulement après la séquence cohérente §13.3.

```bash
# 0. GARDE (§13.5.3) : sans journal d'audit indépendant, la restauration est INTERDITE.
#    Ne pas poursuivre en espérant rejouer plus tard — la source n'existerait pas.
aws logs describe-log-groups --log-group-name-prefix /test/erasure-audit

export T="2026-07-01T14:30:00Z"   # instant de restauration

# 1. Lister les effacements à rejouer, sans rien supprimer
python3 scripts/replay_erasures.py \
  --log-group /test/erasure-audit --since $T \
  --table test-documents-restore-... \
  --bucket test-documents-sources \
  --dry-run

# 2. Revoir le rapport : un effacement listé mais introuvable dans la table restaurée
#    n'est pas une anomalie — il signifie que la restauration ne l'a pas ramené.

# 3. Exécuter le rejeu
python3 scripts/replay_erasures.py \
  --log-group /test/erasure-audit --since $T \
  --table test-documents-restore-... \
  --bucket test-documents-sources

# 4. Vérification d'absence (§8.4 étape 5), par utilisateur rejoué
#    S3 : list_object_versions par préfixe = 0, versions ET marqueurs
#    S3 Vectors : Retrieve filtré = 0
#    (Memory n'entre pas dans le rejeu : elle n'est pas restaurée — §9.4)

# 5. Seulement ensuite : bascule Terraform et remise en service (§13.1 étape 3)
```

**Trois points d'exploitation :**

- **le rejeu est idempotent** : le relancer après une interruption est sans effet de bord ;
- **il ne demande aucune nouvelle confirmation `V2-ADR-014`** — les commandes d'origine ont été
  confirmées et leurs `erasureOperationId` figurent dans le journal ;
- **il précède la ré-ingestion**, jamais l'inverse (§13.3). Rejouer après avoir réindexé conduirait
  à indexer puis désindexer des documents effacés, en laissant une fenêtre pendant laquelle ils sont
  interrogeables.

## 19. Trajectoire V2 → V3

Ce que la bascule change côté données :

- attributs `kbIngestionJobId` / `kbDataSourceId` de `documents` deviennent inutilisés (schéma
  compatible ascendant, cf. §4.3) ;
- ré-ingestion massive change de mécanisme (KB → SQS+ECS), mais la procédure §14 conserve la même
  interface (script `runbook`) ;
- suppression coordonnée passe en saga applicative (`V2-ADR-003`) — l'étape 4 « vérification no
  résidu » reste identique ;
- suppression vectorielle : resynchronisation KB (V2) → suppression directe S3 Vectors (V3) ;
- **symétrie requête/document** : garantie structurellement par KB en V2, **à garantir par le
  contrôle d'espace de l'adapter en V3** (`V2-ADR-013`). C'est la raison pour laquelle ce contrôle
  est écrit dès la V2 alors qu'il y est redondant — l'écrire au moment où il compte serait l'écrire
  trop tard ;
- **changement d'espace d'embedding** : nouvelle base de connaissances **et** nouvel index en V2 ;
  nouvel index seul en V3. La séquence §14.5 est identique dans les deux phases ;
- **rejeu des effacements** : procédure manuelle documentée (§18.5), exécutée au DR drill en V2 ;
  automatisé depuis le journal d'audit en V3 ;
- cycle de vie du `status` regagne son grain fin (§4.4) — les états terminaux ne changent pas.

Ce que la bascule **ne change pas** (contrats stables) :

- schéma des tables `Trips`, `documents`, `users`, `ledger` — `erasureDurableAt` compris ;
- politique de rétention et TTL (§10), et l'indépendance de la rétention vis-à-vis de la
  classification (§10.1) ;
- taxonomie de `classification`, son défaut et ses deux régimes de reclassification (§4.3.2) ;
- chiffrement au repos (§11) ;
- garanties PITR et versioning (§12) ;
- règles `terraform_plan_guard.py` (§16), booléennes comme de borne ;
- invariant de cohérence (§14.4), espace d'embedding compris ;
- **modèle d'effacement** : effacement logique immédiat, fenêtre résiduelle déclarée, vérification
  d'absence en garde, journal d'audit hors périmètre PITR (§6.3, §8.4, §8.6) ;
- **statut de la mémoire longue durée** : donnée personnelle, suppression explicite et vérifiée,
  bloquante (§8.3, §9.2) ;
- procédures de restauration DynamoDB et S3 (§13.1, §13.2) et l'obligation de rejeu (§13.5) ;
- runbooks §18.1, §18.3, §18.5.

Cette stabilité vaut sous une réserve : si la précondition P1 ou P2 (§1.3) échoue, le repli de
`V2-ADR-015` déplace les préférences de Memory vers DynamoDB. Le **modèle** d'effacement ne change
pas — c'est même lui qui devient plus simple, la mécanique documentaire s'appliquant telle quelle —
mais l'allocation de capacité de la CAM Domaine 6, elle, est amendée.

Cette stabilité est ce qui rend le passage V3 réversible sans réécriture des procédures
d'exploitation.
