# V2-LLD-006 — Données, mémoire, rétention et restauration

- **Version :** 0.3
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§9, §14)
- **ADR de référence :** `V2-ADR-003`, `V2-ADR-004`, `V2-ADR-006`, `V2-ADR-010`, `V2-ADR-019`
  (phasage RAG), plus `V2-ADR-013`/`V2-ADR-015`/`V2-ADR-017` (au backlog — traités comme contrats
  ouverts, cf. §1.3)
- **Gate :** V2-G2

> **Révision v0.2 (revue PR #35, bloquants/majeurs) :** les scripts d'exploitation référencés
> (`check_dv_consistency.py`, `run_rag_eval.py`) sont désormais explicitement marqués **artefacts
> planifiés** avec leur contrat d'entrée/sortie (§16.1), et non des outils existants. Aucun code
> n'est créé avant l'approbation des LLD (G2).
>
> **Révision v0.3 (revue PR #35, observations) :** limite du GSI `by-tenant` documentée avec
> évolution compatible (§4.2) ; prérequis de conception rendant la bascule Terraform de restauration
> réellement exécutable — noms de tables en variables + outputs + vérification (§13.1.1).

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

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-003 | Schéma table `documents` (`PK = tenantId#documentId`, `SK = version`), attributs, GSI `by-tenant`, cycle de vie du `status` |
| V2-ADR-004 | Pipeline d'ingestion SQS + worker ECS = **cible V3 uniquement** ; en V2, la réhydratation utilise KB `StartIngestionJob` |
| V2-ADR-006 | Métadonnées obligatoires (`tenantId`, `documentId`, `version`, `status`) ; isolation préservée en restauration ; suppression coordonnée S3 + S3V + DynamoDB + Memory |
| V2-ADR-010 | RTO/RPO par catégorie ; option B (réhydratation applicative depuis source) ; cohérence de restauration ; DR drills trimestriels ; `terraform_plan_guard.py` étendu |
| V2-ADR-019 | En V2, la réhydratation S3V s'exécute par `StartIngestionJob` KB (pas par le pipeline SQS+ECS différé) ; les preuves de non-régression restent identiques |

### 1.3 ADR au backlog — contrats laissés ouverts

Trois ADR complémentaires ne sont pas encore instruits mais impactent directement les données. Ce
LLD **fixe des contrats côté données** compatibles avec leurs futures décisions, sans les
préempter :

| ADR (backlog) | Ce que le LLD-006 fixe dès la V2 | Ce qui reste à décider par l'ADR |
|---|---|---|
| V2-ADR-013 — Embeddings et versionnement | `embeddingModelId` et `embeddingVersion` stockés par document dans `documents` ; changement de modèle traçable | Stratégie de migration (resync complète KB en V2, job applicatif en V3) et politique de dépréciation |
| V2-ADR-015 — Mémoire et droit à l'effacement | Frontière stricte entre données durables (S3/DynamoDB) et volatiles (Memory) ; entrée `users` prévue pour la trace d'effacement (§8.5) | Portée exacte du droit à l'effacement, délais légaux applicables, cycle de vie Memory |
| V2-ADR-017 — Classification documentaire | Attribut `classification` porté par `documents` (V2-ADR-003) et propagé dans les métadonnées de chunk (`V2-LLD-002` §11.2) | Taxonomie exacte, règles d'accès par niveau, workflow de reclassification |

Ces contrats sont marqués « stable » (non renégociable) versus « ouvert » (renégociable par l'ADR).
Toute demande de renégociation d'un contrat stable relève d'un nouvel ADR de phasage type
`V2-ADR-019`, pas d'une modification silencieuse du LLD.

### 1.4 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-001, V2-ADR-002, V2-ADR-005, V2-ADR-007, V2-ADR-008, V2-ADR-009 | Ingress, répartition, agents, plateforme, observabilité et CI/CD : consommés en tant que contexte mais aucune décision de données ne relève de ce LLD |

### 1.5 Périmètre et exclusions

**Inclus (V2) :** modèles DynamoDB (table `Trips` V1 conservée, table `documents` V2 nouvelle,
ledger d'idempotence), TTL et rétention, S3 buckets (source documents, frontend, artefacts),
S3 Vectors comme état dérivé, AgentCore Memory comme donnée non durable, chiffrement au repos,
PITR et versioning, suppression utilisateur (frontière stable pour V2-ADR-015), restauration et
réhydratation (via KB en V2), cohérence source/métadonnées/index, contrôles Terraform, runbooks.

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
| Ledger d'idempotence | mutations `Trips`/uploads/ingestion | DynamoDB | PITR | **TTL 7 jours** (par entrée) | technique |
| Utilisateurs | `users` (nouvelle en V2, trace effacement) | DynamoDB | PITR | conservation liée à l'exigence légale (V2-ADR-015) | identité |
| Contenu documentaire | fichiers uploadés | S3 (bucket `documents`) | **versioning obligatoire** ; pas de réplication cross-région en V2 | supersession par nouvelle version ; effacement toutes versions | tenant |
| Index vectoriel | chunks + embeddings | S3 Vectors (via KB en V2) | **aucune** — état dérivé | reconstructible par ré-ingestion | technique dérivée |
| Mémoire agentique | `AgentCore Memory` | Memory | **aucune** par conception | volatile ; dégradation contrôlée en cas de panne | conversationnelle |
| Frontend statique | SPA React | S3 (bucket `frontend`) | versioning | remplacé par déploiement | public |
| Artefacts CI | images container, SBOM | ECR / S3 | rétention CI (`V2-LLD-008`) | conservation par version tagguée | technique |
| Secrets applicatifs | clés API tierces, mots de passe DB si applicable | Secrets Manager | rotation automatique | rotation périodique | critique |
| Configuration IaC | Terraform | Git (source de vérité) | Git | versionnement Git | technique |
| État Terraform | `terraform.tfstate` | S3 backend séparé | versioning + verrouillage | conservation illimitée (audit) | critique |

**Principe fondateur :** *aucune donnée régénérable ne fait l'objet d'une sauvegarde dédiée.*
Les données régénérables (S3 Vectors, Memory) sont reconstruites depuis leur source (S3 + KB config,
ou rien). Seules les données irremplaçables (transactionnel, métadonnées, ledger, utilisateurs,
contenu source, secrets, tfstate) sont sauvegardées.

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
| `embeddingModelId` | S | serveur (paramètre config) | non |
| `embeddingVersion` | S | serveur | non |
| `chunkerVersion` | S | vide en V2, renseigné en V3 | rempli |
| `classification` | S | serveur (V2-ADR-017) | non |
| `sourceUri` | S | serveur | non |
| `creationOperationId` | S | serveur | non |
| `kbIngestionJobId` | S | serveur (V2 uniquement) | supprimé en V3 |
| `kbDataSourceId` | S | config (V2 uniquement) | supprimé en V3 |
| `createdAt`, `updatedAt` | S (ISO) | serveur | non |

Les attributs `kb*` sont **présents uniquement en V2**. Leur suppression en V3 est un changement de
schéma **compatible ascendant** (attributs optionnels).

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

## 5. Ledger d'idempotence (V1 pattern, réutilisé)

### 5.1 Portée V2

Le pattern V1 (`docs/adr/ADR-0006`, `docs/adr/ADR-0007`) — hash canonique du payload, `mutation_started`
bloquant tout replay après effet de bord, TTL — est repris pour :

- mutations `Trips` (V1, inchangé) ;
- uploads documentaires (nouveau, `creationOperationId` généré client ou serveur) ;
- déclenchement d'ingestion KB (nouveau, `hash(tenantId + documentId + version)` pour éviter double
  `StartIngestionJob`).

### 5.2 Choix de magasin

Le ledger d'idempotence est porté par une **table dédiée** `${env}-idempotency-ledger` (pas fusionné
avec `documents` ou `Trips`) :

- `pk = scope#hash` (scope = `trip-mutation` / `document-upload` / `document-ingest` ; hash =
  canonique) ;
- `sk = createdAt` ;
- `ttl = 7 jours` (attribut `expiresAt`), suffisant pour couvrir tous les retry raisonnables
  (SQS/HTTP/utilisateur) ;
- PITR activé (traçabilité en cas d'audit sur un doublon supposé) ;
- SSE-KMS.

Ce découplage évite qu'une purge TTL du ledger n'affecte les métadonnées ou métier ; il permet
aussi de dimensionner indépendamment (le ledger est majoritairement write-once + TTL).

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

Attributs V2 : `userId` (miroir Cognito), `tenantId`, `createdAt`, `erasureRequestedAt`,
`erasureCompletedAt`, `erasureOperationId`. Toute extension (préférences, profil enrichi) est
différée à `V2-ADR-015`.

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

- `sources/<tenantId>/<documentId>/v<version>/` — contenu source définitif ;
- `sources/<tenantId>/<documentId>/v<version>/<filename>.metadata.json` — fichier de métadonnées
  consommé par KB (`V2-LLD-002` §5.3) ;
- `quarantine/<tenantId>/<documentId>/v<version>/` — upload en attente de validation.

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
}
```

Les objets courants (version live) ne sont **jamais** expirés par cycle de vie : seule une
suppression coordonnée (§8) peut les retirer. Les versions non-courantes sont purgées après une
période de grâce (90 jours) pour éviter la croissance illimitée du bucket.

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
| Effacement utilisateur | tous les documents + trace | demande légale (RGPD ou équivalent) | tous documents du user + `users.erasureCompletedAt` renseigné |

L'effacement utilisateur en V2 est **délégué à la composition** de suppressions documentaires + une
entrée `users` de trace. La stratégie complète (délais légaux, périmètre exact) est décidée par
`V2-ADR-015` ; ce LLD fournit la mécanique de bas niveau.

### 8.2 Suppression documentaire — séquence V2

```text
DELETE /documents/{documentId}
  1. FastAPI vérifie ACL (utilisateur ou admin du tenant)
  2. documents.status = "deleting"  (transition conditionnelle depuis "indexed" ou "failed")
  3. Adapter magasin vectoriel .delete(documentId, toutes versions) :
       V2 : suppression S3 sources (toutes versions + fichier .metadata.json)
            + StartIngestionJob KB (resync qui retire les chunks de l'index S3V)
       V3 : saga applicative (V2-ADR-003)
  4. Vérification "no résidu" :
       - list_objects S3 avec préfixe = 0
       - Retrieve KB avec filter documentId = 0
  5. documents.status = "deleted" (transition conditionnelle depuis "deleting")
  6. Émission d'un événement d'audit (V2-LLD-005) sans données sensibles
```

**Point critique V2 :** l'étape 3 (V2) est **asynchrone** — la resync KB prend l'ordre de la
minute. Le `status = "deleted"` n'est atteint qu'après vérification en étape 4. Un client qui liste
les documents entre l'étape 2 et 5 voit `deleting`, jamais un état incohérent.

### 8.3 Suppression coordonnée — inclusion Memory

`V2-ADR-006` exige la suppression coordonnée sur S3 + S3V + DynamoDB + Memory. Memory étant
volatile par conception (§9), sa « suppression » se réduit à :

- pas de sauvegarde donc pas de résidu ;
- expiration naturelle des sessions ;
- si une suppression synchrone Memory est possible via l'API, elle est appelée au best-effort ;
  sinon, l'expiration naturelle suffit à satisfaire l'exigence.

Cette réduction est explicitement documentée : Memory ne bloque pas la suppression coordonnée.

### 8.4 Effacement utilisateur — séquence V2

```text
POST /admin/users/{userId}/erase
  1. Vérification admin + résolution tenant
  2. users.erasureRequestedAt = now ; erasureOperationId = uuid
  3. Pour chaque documentId du user :
       suppression documentaire (§8.2)
  4. users.erasureCompletedAt = now
  5. Événement d'audit émis
```

**Ce que le LLD-006 ne préempte pas :** délai maximum entre requête et complétion,
communication utilisateur, portée exacte (Memory ? conversations ? logs redacted ?), obligations
légales — décisions de `V2-ADR-015`.

### 8.5 Trace conservée après effacement

Les entrées `users` sont conservées (avec `erasureCompletedAt` renseigné) après effacement des
documents, pour tracer qu'une suppression a bien eu lieu et permettre l'audit. Aucune donnée
personnelle n'est retenue au-delà de ce minimum. Un nouvel identifiant utilisateur créé pour la
même personne physique n'hérite pas de l'ancien enregistrement.

## 9. AgentCore Memory (non durable)

### 9.1 Positionnement

Memory est **volatile par conception** dans la CAM V2 (`architecture/hld/capability-allocation-matrix.md`).
Aucune sauvegarde n'est configurée, aucun RTO/RPO n'est engagé, et une indisponibilité déclenche la
dégradation « poursuite sans mémoire durable » déjà actée.

### 9.2 Conséquences pour ce LLD

- Memory n'apparaît pas dans les procédures de restauration ;
- Memory est incluse dans la suppression coordonnée uniquement au best-effort (§8.3) ;
- Aucune donnée durable métier ou documentaire ne doit être stockée dans Memory (contrôle
  d'architecture, vérifié en revue) — toute donnée à conserver appartient à `Trips`, `documents`,
  `users` ou `ledger`.

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
| `users` items sans effacement | illimitée | — |
| `users` items effacés | illimitée (trace) | — |
| S3 `sources/` version courante | illimitée sauf effacement | — |
| S3 `sources/` versions non-courantes | 90 jours après supersession | cycle de vie S3 |
| S3 `quarantine/` | 7 jours | cycle de vie S3 |
| S3 `frontend/` versions non-courantes | 30 jours | cycle de vie S3 |
| S3 `artefacts/` | 90 jours | cycle de vie S3 (`V2-LLD-008`) |
| S3 `tfstate/` | illimitée | pas de purge (audit) |
| S3 Vectors | vit avec `documents` | reconstruit par ingestion |
| Memory | volatil | expiration naturelle |
| Secrets Manager | rotation périodique | selon secret |

Les rétentions ci-dessus sont **des paramètres Terraform** : aucune valeur n'est codée en dur dans
le code applicatif.

## 11. Chiffrement au repos

| Magasin | Clé | Justification |
|---|---|---|
| `Trips` | KMS managée AWS (V1 conservé) | continuité V1, données métier standard |
| `documents` | **KMS managée client (CMK dédiée)** | rotation contrôlée, séparation des privilèges d'accès (V2-ADR-006) |
| `ledger` | KMS managée client (CMK dédiée) | même politique que `documents` |
| `users` | KMS managée client (CMK dédiée) | données identité |
| S3 `documents` | même CMK que `documents` DynamoDB | cohérence d'accès KMS entre source et métadonnées |
| S3 Vectors | KMS géré par KB / S3V (config) | délégué au service ; en V3 : passage à CMK dédiée si S3V natif l'expose |
| S3 `tfstate` | CMK dédiée `tfstate` | accès restreint aux mains CI/CD |
| Secrets Manager | CMK par défaut ou dédiée | selon criticité |

**Contrôle IAM associé :** le rôle FastAPI (`V2-LLD-001`) obtient `kms:Decrypt` uniquement sur les
CMK qu'il doit lire. Aucun rôle applicatif n'a `kms:*` global. Les CMK sont provisionnées par
Terraform (`V2-LLD-005` pour la politique de clé exacte).

## 12. Sauvegarde

### 12.1 Ce qui est activé et non désactivable

- PITR sur `Trips`, `documents`, `ledger`, `users` — 35 jours ;
- Versioning S3 sur `documents`, `frontend`, `artefacts`, `tfstate`.

Ces deux garanties sont **contrôlées par `terraform_plan_guard.py`** (§16) : tout plan qui les
désactiverait ou détruirait une ressource concernée sans confirmation explicite est bloqué.

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
3. Pour chaque documentId présent dans la table restaurée avec status = "indexed" :
     a. Vérifier que S3 sources/<tenantId>/<documentId>/<version> existe (version indexée à T)
     b. Si absent : la source a été supprimée après T (perte irrécupérable de contenu, à noter)
4. Bascule Terraform vers la table restaurée
5. Déclencher une ré-ingestion ciblée sur les documents "indexed"
   (V2 : StartIngestionJob par data source ; V3 : SQS enqueue stage=validate)
6. Attendre la complétion des jobs
7. Vérification : Retrieve renvoie les documents attendus
```

**Ordre non commutable :** DynamoDB restauré **avant** ré-ingestion. L'inverse produirait des
chunks orphelins pointant vers des documents dont l'entrée `documents` a été perdue.

### 13.4 Restauration `users` et effacement

Une entrée `users.erasureCompletedAt` restaurée par PITR **ne réintroduit pas** les documents
effacés (ils ont été supprimés, pas archivés). C'est le comportement attendu : PITR restaure la
**trace d'effacement**, pas la donnée effacée. Toute demande contraire relève d'une exigence légale
distincte, décidée par `V2-ADR-015`.

## 14. Réhydratation S3 Vectors

### 14.1 Principe (V2-ADR-010, option B)

S3 Vectors est un **état dérivé**. Il n'est ni sauvegardé, ni exporté : il est **reconstruit depuis
S3 (sources) + `documents` (métadonnées)**. La ré-ingestion complète est le mécanisme de reprise.

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

## 15. Cohérence en cas de restauration partielle

`V2-ADR-010` exige qu'aucun vecteur orphelin ne subsiste après restauration. La séquence §13.3 le
garantit **si elle est respectée dans l'ordre**. Deux garde-fous supplémentaires :

- **Vérification préalable à toute ré-ingestion massive** : script `scripts/check_dv_consistency.py`
  (**artefact planifié, contrat en §16.1** — non encore créé) qui liste les
  `documents.status = indexed` sans objet S3 correspondant. Ces documents doivent être passés à
  `status = "failed"` avant la ré-ingestion, pas ignorés.
- **Métrique post-restauration** : nombre de chunks dans S3 Vectors ± X% du `sum(chunkCount)` de
  `documents.status = indexed`. Un écart supérieur à la marge alerte (`V2-LLD-007`).

## 16. Contrôles Terraform (`terraform_plan_guard.py`)

`V2-ADR-010` demande d'étendre le guard existant. Ce LLD fixe les règles bloquantes précises :

| Règle | Ressource | Comportement bloqué |
|---|---|---|
| PITR obligatoire | `aws_dynamodb_table` tables `Trips`, `documents`, `ledger`, `users` | plan qui passe `point_in_time_recovery.enabled = false` |
| Destruction interdite | mêmes tables | plan qui contient `destroy` sans variable `CONFIRM_DESTROY_DYNAMODB=<table_name>` |
| Versioning obligatoire | `aws_s3_bucket_versioning` `documents`, `frontend`, `artefacts`, `tfstate` | plan qui passe `status = Suspended` |
| Destruction interdite | buckets S3 versionnés + KMS CMK utilisées | plan qui contient `destroy` sans variable `CONFIRM_DESTROY_S3=<bucket>` ou `CONFIRM_DESTROY_KMS=<key>` |
| SSE-KMS obligatoire | `documents`, `ledger`, `users` DynamoDB et bucket `documents` | plan qui retire `server_side_encryption` ou passe à SSE-S3 sur `documents` bucket |
| Public block obligatoire | tous buckets S3 | plan qui met un `block_public_*` à `false` |

Le guard est un script CI exécuté avant `terraform apply` (`V2-LLD-008`). Une violation renvoie un
code d'échec non contournable en CI ; en local, la confirmation explicite passe par variable
d'environnement (jamais par flag CLI, pour éviter les accidents).

### 16.1 Scripts d'exploitation planifiés (à créer à l'implémentation)

Les runbooks §15 et §18 s'appuient sur deux scripts qui **n'existent pas encore** : ils sont des
**artefacts planifiés**, créés à l'implémentation (périmètre outillage, aligné sur `V2-LLD-009`),
pas des outils disponibles à ce stade documentaire pré-G2. Ce LLD fixe leur contrat pour que la
future implémentation soit sans ambiguïté. À l'inverse, `scripts/terraform_plan_guard.py` et
`scripts/run_industrial_test_suite.py` **existent déjà** dans le dépôt et sont réutilisés tels quels.

| Script (planifié) | Entrées | Sortie | Rôle |
|---|---|---|---|
| `scripts/check_dv_consistency.py` | `--table <documents>`, `--bucket <sources>`, `--sample N` (optionnel) | code 0 si cohérent, code ≠ 0 + rapport JSON listant les écarts | Vérifier l'invariant §14.4 : tout `documents.status = indexed` a un objet S3 source correspondant, et signaler les `indexed` sans source (à repasser `failed` avant ré-ingestion) |
| `scripts/run_rag_eval.py` | `--dataset <ref>`, `--baseline <artefact.json>` | rapport JSON (recall@k, precision@k, groundedness, couverture citations) + statut PASS/FAIL vs baseline | Rejouer le dataset d'évaluation retrieval (`V2-ADR-018`) après réhydratation et comparer aux métriques pré-incident |

Tant que ces scripts ne sont pas créés, les runbooks §18.2 et §18.4 qui les invoquent sont **non
exécutables** : ils décrivent la procédure cible, pas une capacité présente. Cette limite est
explicitement portée au périmètre d'implémentation, pas masquée.

## 17. Tests et preuves

### 17.1 Matrice de preuves

| Preuve attendue | Type | Bloquant |
|---|---|---|
| PITR restauration `documents` : comptage identique à référence | intégration DR drill | **Oui** |
| PITR restauration `Trips` : comptage identique | intégration DR drill | **Oui** |
| Suppression documentaire : 0 objet S3, 0 chunk KB, `documents.status = deleted` | intégration | **Oui** |
| Effacement utilisateur : tous les documents supprimés, `users.erasureCompletedAt` renseigné | intégration | **Oui** |
| Cohérence après restauration : aucun chunk orphelin sur échantillon de N | intégration DR drill | **Oui** |
| `terraform_plan_guard.py` bloque désactivation PITR / versioning / destroy sans confirm | statique CI | **Oui** |
| RTO S3V mesuré ≤ cible sur corpus de démonstration | DR drill | Oui (métrique publiée) |
| Métriques qualité retrieval post-réhydratation dans marge d'éval (`V2-ADR-018`) | qualité DR drill | Oui |
| Ledger d'idempotence : TTL effectif à 7 jours | intégration | Oui |
| Aucune donnée durable dans Memory (revue statique) | statique | Oui |

### 17.2 DR drill trimestriel

Fréquence trimestrielle ou avant chaque release majeure (`V2-ADR-010`). Contenu minimum :

1. Restaurer `documents` PITR vers une table de récupération ;
2. Bascule Terraform contrôlée (dry run + apply en environnement `test` isolé) ;
3. Ré-ingestion complète via KB (V2) ou pipeline (V3) ;
4. Exécution du dataset d'éval retrieval (`V2-ADR-018`) et comparaison avec la baseline ;
5. Publication des preuves au format standard (`scripts/run_industrial_test_suite.py` : JSON, SHA
   Git, horodatage, durée, statut).

## 18. Exploitation — runbooks

### 18.1 Restaurer `documents` à un point dans le temps

```bash
# 1. Identifier l'horodatage cible (avant incident)
export T="2026-07-01T14:30:00Z"

# 2. Restaurer PITR
aws dynamodb restore-table-to-point-in-time \
  --source-table-name test-documents \
  --target-table-name test-documents-restore-$(date +%Y%m%d-%H%M) \
  --restore-date-time $T

# 3. Vérifier la restauration
aws dynamodb describe-table --table-name test-documents-restore-...

# 4. Vérifier cohérence avec S3 sources (script §15)
python3 scripts/check_dv_consistency.py \
  --table test-documents-restore-... \
  --bucket test-documents-sources

# 5. Bascule Terraform (voir §13.1 étape 3)
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
POST /admin/users/<userId>/erase
Content-Type: application/json
{ "reason": "user request", "operationId": "<uuid>" }

# 2. Suivre l'avancement
GET /admin/users/<userId>
=> { "erasureRequestedAt": "...", "erasureCompletedAt": null | "..." }

# 3. Preuves : vérifier absence des documents
GET /admin/users/<userId>/documents
=> [] (liste vide après complétion)
```

### 18.4 Diagnostiquer un chunk orphelin

```bash
# 1. Symptôme : Retrieve renvoie un chunk dont documents[tenantId#documentId] est absent
# 2. Vérifier la cohérence
python3 scripts/check_dv_consistency.py --sample 1000
# 3. Si écart confirmé :
#    - Cause probable : suppression documentaire interrompue entre étapes 3 et 5 (§8.2)
#    - Réparation : relancer la suppression du documentId concerné
```

## 19. Trajectoire V2 → V3

Ce que la bascule change côté données :

- attributs `kbIngestionJobId` / `kbDataSourceId` de `documents` deviennent inutilisés (schéma
  compatible ascendant, cf. §4.3) ;
- ré-ingestion massive change de mécanisme (KB → SQS+ECS), mais la procédure §14 conserve la même
  interface (script `runbook`) ;
- suppression coordonnée passe en saga applicative (`V2-ADR-003`) — l'étape 4 « vérification no
  résidu » reste identique ;
- cycle de vie du `status` regagne son grain fin (§4.4) — les états terminaux ne changent pas.

Ce que la bascule **ne change pas** (contrats stables) :

- schéma des tables `Trips`, `documents`, `users`, `ledger` ;
- politique de rétention et TTL (§10) ;
- chiffrement au repos (§11) ;
- garanties PITR et versioning (§12) ;
- règles `terraform_plan_guard.py` (§16) ;
- invariant de cohérence (§14.4) ;
- procédures de restauration DynamoDB et S3 (§13.1, §13.2) ;
- runbooks §18.1, §18.3.

Cette stabilité est ce qui rend le passage V3 réversible sans réécriture des procédures
d'exploitation.
