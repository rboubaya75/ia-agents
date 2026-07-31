# V2-LLD-002 — RAG et ingestion documentaire

- **Version :** 0.4
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§6.2, §9)
- **ADR de référence :** `V2-ADR-019` (décision de phasage), `V2-ADR-003`, `V2-ADR-004`,
  `V2-ADR-006`, `V2-ADR-010`, `V2-ADR-013`, `V2-ADR-017`, `V2-ADR-018`
- **Gate :** V2-G2

> **Révision v0.2 (revue PR #35, bloquants/majeurs) :** contrat antivirus clarifié (verdict consommé
> de `V2-LLD-005`, retrait du « worker » non défini) ; mécanisme de réconciliation des jobs KB
> tranché (reconciler planifié, §5.1) ; préfixes IAM Bedrock corrigés
> (`bedrock-agent-runtime:Retrieve`, `bedrock-agent:*IngestionJob`, §13.1) ; précondition de
> disponibilité KB+S3V explicitée (§1.6).
>
> **Révision v0.3 (revue PR #35, observations) :** distinction `skipped/no_match` vs
> `skipped/filtered_out` avec seuils d'alerte distincts (§6.2.1, §15.1) ; cohérence de la précondition
> KB+S3V dans la config data source (§5.2).
>
> **Révision v0.4 (alignement sur les ADR complémentaires acceptés) :** `embeddingSpaceId` remplace
> `embeddingModelId`/`embeddingVersion` et l'index devient l'unité de l'espace d'embedding
> (`V2-ADR-013` — §4.2, §4.3, §5.2, §11.2, §12) ; la migration d'embeddings passe de la
> resynchronisation en place à l'index parallèle avec bascule de pointeur (§5.4, §17.2) ;
> `VectorRetrievalPort` expose et vérifie l'espace avant `retrieve`, fail-closed sur divergence
> (§7.1) ; la chaîne de retrieval lit `documents` **avant** le filtre, la classification qui autorise
> étant celle de `documents` et non celle du chunk (`V2-ADR-017` — §4.1, §4.2, §5.3, §6.2, §6.2.1) ;
> préfixe S3 `restricted` hors data source KB (§4.1) ; l'évaluation qualité se scinde en deux
> datasets avec verdict de non-régression contre baseline versionnée (`V2-ADR-018` — §1.1, §1.2,
> §15.1, §16).

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD/Charte | Libellé |
|---|---|
| V2-ARCH-006 | RAG applicatif fondé sur S3 Vectors ; en V2, ingestion/retrieval via KB adossé à S3V, FastAPI conservant le filtrage tenant/ACL ; pipeline applicatif = cible V3 |
| HLD §6.2 | Flux d'ingestion documentaire et suivi d'état exposé à l'utilisateur |
| HLD §9 | Modèle de données documentaire, versioning S3, suppression coordonnée |
| ADR-019 | KB adossé à S3 Vectors en V2 ; FastAPI garde `Retrieve`, post-filtrage tenant/ACL, `retrievalContext`, citations ; pipeline SQS+worker ECS = cible V3 |
| ADR-006 | Métadonnées de filtrage obligatoires : `tenantId`, `documentId`, `version`, `status` |
| ADR-013 | Un index porte un et un seul `embeddingSpaceId`, immuable ; symétrie requête/document vérifiée avant `retrieve`, fail-closed sur divergence |
| ADR-017 | Taxonomie fermée `internal` / `confidential` / `restricted`, défaut `confidential` ; la classification qui autorise est celle de `documents`, jamais celle du chunk |
| ADR-018 | Deux datasets (retrieval déterministe bloquant, génération publié non bloquant) ; verdict = non-régression contre baseline versionnée, jamais seuil absolu |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-019 | **Décision structurante du LLD** : phase V2 = KB adossé à S3 Vectors ; FastAPI utilise l'API `Retrieve` uniquement, applique le post-filtrage tenant/ACL, construit le `retrievalContext` et résout les citations ; adapter de magasin vectoriel = point de migration unique vers la cible V3 |
| V2-ADR-003 | **Cible V3** : schéma de stockage (S3 source, S3 Vectors, table `documents`), métadonnées de chunk, citations, suppression coordonnée. Les contrats d'isolation et de citations qu'il fixe restent applicables en V2 ; leur réalisation d'ingestion diffère (KB) |
| V2-ADR-004 | **Cible V3** : pipeline d'ingestion applicatif SQS + worker ECS. Non provisionné en V2 (l'ingestion V2 est déléguée à KB `StartIngestionJob`) |
| V2-ADR-006 | Métadonnées filtrables obligatoires `tenantId`, `documentId`, `version`, `status` ; suppression coordonnée ; preuve cross-tenant |
| V2-ADR-010 | Sauvegarde/restauration : versioning S3 source, réhydratation de l'index par resynchronisation KB |
| V2-ADR-013 | **`embeddingSpaceId`** — identifiant opaque liant modèle, dimension et métrique de distance — remplace `embeddingModelId`/`embeddingVersion` ; un index porte un et un seul espace, fixé à sa création et immuable ; `chunkerVersion` reste distinct (il ne conditionne pas la comparabilité) ; un changement de modèle se fait par **index parallèle + bascule de pointeur** (jamais par resynchronisation en place) ; l'espace est lu depuis l'index interrogé, jamais depuis la configuration, et une divergence est **fail-closed** (`degraded`) ; la taille de chunk est dérivée de la limite d'entrée du modèle et vérifiée au démarrage |
| V2-ADR-017 | Taxonomie fermée à trois niveaux `internal` / `confidential` / `restricted`, défaut **`confidential`** ; `restricted` n'est jamais indexé ni injecté dans un contexte modèle (préfixe S3 hors data source KB) ; **la classification qui autorise est celle de `documents`**, lue en `BatchGetItem` **avant** le filtre — la métadonnée de chunk n'est qu'un filtre grossier de défense en profondeur, potentiellement obsolète ; la classification est un plafond que l'ACL ne franchit pas ; ordre d'évaluation : tenant → `documents.classification` → ownership/ACL → indexabilité |
| V2-ADR-018 | **Deux datasets** portés par un même corpus de fixtures : retrieval (déterministe, CI, **bloquant**) et génération (non déterministe, planifié, **publié non bloquant**) ; le verdict est la **non-régression contre une baseline versionnée**, jamais un seuil absolu de qualité ; seuls seuils absolus admis : propriétés binaires de sûreté à zéro ; corpus de fixtures isolé de la production ; régime d'amorçage explicite pour la première exécution |

### 1.3 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-001 | Ingress : couvert par `V2-LLD-001` |
| V2-ADR-002 | Répartition FastAPI/Runtime : couvert par `V2-LLD-003` ; ce LLD applique seulement le principe « contenu documentaire = donnée non fiable » |
| V2-ADR-005 | Framework d'agents : couvert par `V2-LLD-003` |
| V2-ADR-007 | Plateforme ECS : couvert par `V2-LLD-001` (le module `ingestion` ECS n'est pas provisionné en V2) |

### 1.4 Périmètre et exclusions

**Inclus (V2) :** formats et limites d'upload, quarantaine, validation/antivirus, déclenchement
d'ingestion KB, configuration de la data source KB (chunking dérivé de la limite du modèle,
`embeddingSpaceId`), magasin vectoriel S3 Vectors adossé à KB, table DynamoDB `documents`, adapter
de retrieval avec vérification d'espace, post-filtrage tenant/classification/ACL/indexabilité sur
`documents`, taxonomie de classification et ses deux préfixes S3, construction du
`retrievalContext`, résolution des citations, suppression et réindexation via KB, séquence de
bascule d'espace d'embedding, réhydratation, deux datasets d'évaluation et leur régime de verdict.

**Exclus (différé cible V3, `V2-ADR-003`/`V2-ADR-004`) :** parsing applicatif multi-format, machine
à états d'ingestion SQS + worker ECS, écriture directe S3 Vectors, saga de suppression applicative
sur trois magasins, jobs applicatifs de migration d'embeddings. Ces éléments sont décrits comme
cible et ne sont **pas** provisionnés en V2.

**Exclus (autres LLD) :** ingress et plateforme (`V2-LLD-001`), agents et Converse API
(`V2-LLD-003`), threat model global et KMS transverse (`V2-LLD-005`), modèle de données et PITR
(`V2-LLD-006`).

### 1.5 Décision de phasage explicite

Ce LLD **réalise `V2-ADR-019`**. Toute divergence entre la description d'ingestion de `V2-ADR-003`/
`V2-ADR-004` (pipeline applicatif) et le présent LLD (KB) est résolue en faveur de `V2-ADR-019`
**pour la phase V2**. La section 18 rappelle la trajectoire de bascule vers la cible V3.

### 1.6 Précondition bloquante — disponibilité KB + S3 Vectors en `eu-west-3`

`V2-ADR-019` conditionne tout ce LLD à une **précondition de vérification** : la disponibilité de
Bedrock Knowledge Bases adossé à S3 Vectors dans la région `eu-west-3`. Cette précondition n'est
**pas encore prouvée dans la PR** ; elle doit l'être avant tout début d'implémentation (gate G2) :

- **preuve attendue** : création effective d'une KB de test adossée à S3 Vectors en `eu-west-3`, ou
  confirmation documentée de la disponibilité régionale de la fonctionnalité (référence AWS datée) ;
- **si la précondition n'est pas levée** : l'ingestion V2 bascule sur le pipeline applicatif
  (`V2-ADR-003`/`V2-ADR-004`, `enable_ingestion_service = true` dans `V2-LLD-001`) — décision
  explicite, sans nouvel ADR (`V2-ADR-019` le prévoit) ;
- tant que la précondition n'est pas tranchée, les sections 5, 6, 7 et 13 de ce LLD sont **en
  attente de confirmation**, pas approuvées pour implémentation.

## 2. Architecture d'ensemble

### 2.1 Deux phases, une frontière constante

FastAPI reste la frontière et le propriétaire applicatif du retrieval dans les deux phases. Seul le
moteur d'ingestion/indexation change, encapsulé derrière un **adapter de magasin vectoriel**.

```text
Phase V2 (livrée)
  Upload (FastAPI)
    -> validation + quarantaine (FastAPI)
    -> S3 source (préfixe géré côté serveur, versioning activé)
    -> écriture DynamoDB documents (status = "ingesting")
    -> KB StartIngestionJob (adapter)
    -> KB : parsing, chunking, embeddings, indexation dans S3 Vectors
    -> réconciliation d'état (status = "indexed" | "failed")

  Question (FastAPI)
    -> FastAPI : vérification d'espace d'embedding (fail-closed si divergence)   [V2-ADR-013]
    -> adapter.retrieve() == KB Retrieve (candidats + scores + métadonnées)   [jamais RetrieveAndGenerate]
    -> FastAPI : filtre grossier sur chunk.classification    (défense en profondeur, peut être obsolète)
    -> FastAPI : LECTURE DynamoDB documents (BatchGetItem, <= topK)   [source de vérité, V2-ADR-017]
    -> FastAPI : post-filtrage tenant + documents.classification + ACL + indexabilité   (OBLIGATOIRE)
    -> FastAPI : construction du retrievalContext borné (ok | degraded | skipped)
    -> FastAPI : résolution des citations depuis documents déjà lu
    -> AgentCore Runtime (IAM-only, ne fait jamais de retrieval)

Phase V3 (cible, V2-ADR-003 / V2-ADR-004)
    -> adapter.retrieve() == requête S3 Vectors directe (filtre tenantId construit avant la requête)
    -> ingestion applicative SQS + worker ECS
    -> embedding de requête produit par FastAPI : la symétrie d'espace devient à garantir
    (FastAPI, Runtime, agents, tools MCP, HLD, CAM inchangés)
```

### 2.2 Composants et responsabilités

| Composant | Responsabilité V2 | Change en V3 ? |
|---|---|---|
| FastAPI (upload) | Validation, quarantaine, écriture S3 source, écriture `documents`, déclenchement ingestion | Non (déclenche SQS au lieu de KB) |
| KB (data source S3V) | Parsing, chunking, embeddings, indexation S3 Vectors | Retiré — remplacé par worker ECS |
| S3 Vectors | Magasin vectoriel (backend de KB en V2, direct en V3) | **Conservé** |
| DynamoDB `documents` | Métadonnées documentaires, état, citations, classification | **Conservé** |
| Adapter magasin vectoriel | `retrieve()` → `KB Retrieve` | `retrieve()` → S3 Vectors direct |
| FastAPI (retrieval) | Post-filtrage tenant/ACL, `retrievalContext`, citations | **Inchangé** |

Le tableau ci-dessus est le contrat de réversibilité : tout ce qui est marqué « Conservé » ou
« Inchangé » ne doit pas être réécrit lors de la bascule V3.

## 3. Formats, tailles et upload

### 3.1 Formats acceptés (V2)

| Type | Extensions | Limite | Note |
|---|---|---|---|
| PDF | `.pdf` | 50 Mo | Parsing délégué à KB ; PDF scanné traité selon capacité KB (OCR non garanti en V2) |
| Word | `.docx` | 25 Mo | |
| Texte | `.txt`, `.md` | 10 Mo | |
| HTML | `.html` | 10 Mo | Détouré du balisage par KB |

Un type hors de cette liste est rejeté en amont de la quarantaine (validation MIME + magic bytes,
pas seulement l'extension). Le CSV/XLSX et le PDF scanné avec OCR sont différés (dépendent des
capacités de la data source KB, à confirmer en preuve avant activation).

### 3.2 Upload et quarantaine

```text
POST /documents (multipart, FastAPI) — chemin synchrone
  1. Auth JWT validée + résolution tenant côté serveur
  2. Validation type/taille/magic-bytes  -> rejet 415/413 si invalide
  3. documentId = UUID v4 (généré serveur) ; version = 1
  4. PUT S3 préfixe quarantaine : s3://<bucket>/quarantine/<tenantId>/<documentId>/v1/<filename>
  5. Écriture DynamoDB documents : status = "uploaded", creationOperationId
  6. Réponse 202 { documentId, operationId, status: "uploaded" }
     (l'objet n'est PAS encore requêtable ; il attend le verdict de validation)

Verdict de validation (asynchrone, contrôle possédé par V2-LLD-005) :
  7. Le contrôle de sécurité des uploads (antivirus + validation approfondie) émet un verdict
     "validated" | "quarantined" pour l'objet en quarantaine.
  8. Sur "validated" : FastAPI copie vers le préfixe définitif
     s3://<bucket>/sources/<tenantId>/<documentId>/v1/ + génère <filename>.metadata.json (§5.3),
     documents.status = "validated", puis déclenche l'ingestion KB (section 5) -> "ingesting".
  9. Sur "quarantined" : documents.status = "quarantined" ; l'objet reste en quarantaine.
```

**Frontière de responsabilité (B3, revue PR #35) :** le *mécanisme* d'analyse des uploads
(moteur antivirus, compute qui l'exécute, déclenchement sur dépôt S3) est **possédé par
`V2-LLD-005`** (sécurité des uploads). Ce LLD **ne définit pas** de « worker » d'analyse : il définit
seulement le **contrat de verdict** qu'il consomme (`validated` | `quarantined`) et les transitions
d'état `documents` associées. Le verdict est asynchrone : un document reste en `uploaded` jusqu'à
réception du verdict, puis passe `validated` (et enchaîne l'ingestion) ou `quarantined`. Un document
`quarantined` reste en quarantaine avec purge par cycle de vie S3 (TTL défini en `V2-LLD-006`).

## 4. Stockage

### 4.1 S3 source

- bucket privé dédié, chiffrement KMS, **versioning activé** (base de la réhydratation `V2-ADR-010`) ;
- **deux préfixes de documents validés**, distingués par l'indexabilité et non par la rétention :

| Préfixe | Classification | Couvert par la data source KB | Indexé |
|---|---|---|---|
| `sources/<tenantId>/<documentId>/v<version>/` | `internal`, `confidential` | **oui** | oui |
| `restricted/<tenantId>/<documentId>/v<version>/` | `restricted` | **non** | **non** |

- accès en lecture par le rôle d'ingestion KB (section 13, **restreint au seul préfixe `sources/`**)
  et par FastAPI (les deux préfixes) ; aucun accès public ;
- le contenu source reste la **source de vérité** : l'index S3 Vectors et les métadonnées sont
  reconstructibles à partir de S3 + config KB.

**Le préfixe `restricted/` encode l'indexabilité, pas la rétention (`V2-ADR-017`).** Les data
sources KB se définissant par préfixe S3, exclure un document de l'indexation exige qu'il soit
stocké hors du préfixe couvert. Les deux préfixes portent **la même politique de conservation**
(§13.2 et `V2-LLD-006` §7) : la classification ne module pas la rétention.

**La transition vers `restricted` est la seule reclassification destructive.** Elle déplace l'objet
de `sources/` vers `restricted/` (copy + delete), puis désindexe les chunks existants par
resynchronisation KB (§8.1). Sur un bucket versionné, la suppression de la clé source ne crée qu'un
delete marker : les **versions non-courantes restent atteignables par version ID à l'ancien
emplacement**. Elles doivent donc être supprimées explicitement (hard delete des non-current
versions) dans la même opération, faute de quoi un résidu du document reste lisible hors du préfixe
`restricted/`.

### 4.2 S3 Vectors (backend de KB en V2)

- un index vectoriel partagé (pas d'index par tenant en V2 — l'isolation repose sur le filtre
  `tenantId` + le post-filtrage FastAPI, cohérent avec `V2-ADR-003`) ;
- métadonnées de chunk **filtrables obligatoires** : `tenantId`, `documentId`, `version`, `status`
  (imposées par `V2-ADR-006`) ; ces champs sont mappés dans la configuration de la data source KB
  pour être exposés au filtre `Retrieve` ;
- métadonnées non filtrables : `chunkIndex`, `sourceUri`, `createdAt`, `embeddingSpaceId`,
  `chunkerVersion`, `classification` ;
- l'index est écrit par KB, jamais par FastAPI en V2 (en V3, l'adapter écrit directement).

**L'index est l'unité de l'espace d'embedding (`V2-ADR-013`).** Un index porte un et un seul
`embeddingSpaceId` — identifiant opaque liant le modèle, la dimension et la métrique de distance —
**fixé à sa création et immuable**. Deux vecteurs issus d'espaces différents ne sont pas
« moins comparables » : leur similarité est arbitraire. Le calcul aboutit, retourne un score
plausible, et classe des chunks sans rapport avec la question, sans exception ni code d'erreur.
C'est pourquoi aucune écriture n'est admise dans un index dont l'espace diffère de celui du
producteur, et pourquoi un changement de modèle d'embedding est la **création d'un index**, pas une
mise à jour (§5.4). `chunkerVersion` est tracé séparément : un changement de chunker modifie la
qualité, pas la comparabilité, et reste évaluable à espace constant.

**`classification` est un filtre grossier, pas la valeur qui autorise (`V2-ADR-017`).** La copie
portée par le chunk est figée au moment de l'indexation et n'est pas synchrone avec `documents` :
une reclassification enregistrée dans `documents` reste sans effet sur elle jusqu'à la prochaine
ré-ingestion. Elle est appliquée **avant** la lecture de `documents` à seule fin de défense en
profondeur (§6.2 étape 1). **La décision d'autorisation est prise sur `documents`, jamais sur le
chunk.** Ce partage est sûr parce que le sens de l'erreur possible est borné : un chunk plus
restrictif que sa source écarte un candidat autorisé — perte de rappel, mesurée en
`filtered_out` (§6.2.1) ; un chunk plus permissif que sa source ne produit rien, la décision finale
étant prise sur la source.

### 4.3 DynamoDB — table `documents`

Identique au schéma de `V2-ADR-003` (conservé en V2 et V3) :

- `PK = tenantId#documentId`, `SK = version` ;
- GSI `by-tenant` : `PK = tenantId` pour lister les documents d'un tenant (défini en `V2-LLD-006`) ;
- attributs : `status`, `chunkCount`, `embeddingSpaceId` (`V2-ADR-013` — remplace le couple
  `embeddingModelId`/`embeddingVersion`), `chunkerVersion`, `classification` (domaine fermé
  `internal` | `confidential` | `restricted`, défaut `confidential`, `V2-ADR-017`), `sourceUri`,
  `creationOperationId`, `kbIngestionJobId` (nouveau en V2 — id du job KB pour la réconciliation),
  `kbDataSourceId`.

**`documents` est la source de vérité de l'autorisation documentaire.** L'attribut `classification`
y est écrit exclusivement côté serveur, et c'est sa valeur — jamais celle du chunk — qui décide de
l'accès (§6.2). Une valeur hors du domaine fermé est refusée à l'écriture ; une entrée portant une
valeur inconnue provoque un refus de lecture, jamais un accès par défaut (`V2-ADR-006`, refus par
défaut).

**Cycle de vie du `status` en V2 (adapté au modèle KB) :**

```text
uploaded -> validated | quarantined
validated -> ingesting -> indexed | failed
indexed -> superseded (réindexation) | deleting -> deleted
```

Les états intermédiaires applicatifs de `V2-ADR-003` (`parsing`, `chunking`, `embedding`,
`indexing`) sont **collapsés en `ingesting`** en V2 : ces étapes sont internes à KB et non observables
au grain fin. Ils réapparaissent en V3 quand FastAPI reprend le pipeline. Le mapping est explicite
pour que la bascule V3 n'invente pas de nouveaux états.

## 5. Ingestion V2 via Knowledge Bases

### 5.1 Modèle asynchrone `StartIngestionJob`

FastAPI ne parse ni n'indexe : il déclenche un job d'ingestion KB sur la data source S3, puis
réconcilie l'état.

```text
FastAPI (après validation) :
  1. kb.StartIngestionJob(knowledgeBaseId, dataSourceId)   [via adapter]
  2. documents.kbIngestionJobId = job.id ; status = "ingesting"
  3. Réponse 202 { documentId, operationId, status: "ingesting" }

Réconciliation (reconciler planifié — voir ci-dessous) :
  4. pour chaque documents.status = "ingesting" : kb.GetIngestionJob(jobId) -> COMPLETE | FAILED | IN_PROGRESS
  5. COMPLETE : status = "indexed", chunkCount renseigné (best effort)
     FAILED   : status = "failed", raison journalisée (redacted)
     IN_PROGRESS : inchangé (repris au prochain tick)
```

**Mécanisme de réconciliation retenu (M5, revue PR #35) — reconciler planifié.** La transition
`ingesting -> indexed | failed` est effectuée par une tâche de réconciliation **déclenchée
périodiquement** (EventBridge Scheduler, période initiale 60 s en `test`), et **non** par un poll
in-request FastAPI ni par une dépendance à des événements de complétion émis par KB :

- **pas de poll in-request** : la latence de réponse HTTP ne doit pas être couplée à la durée du job
  KB (le chemin d'upload répond `202` immédiatement, §5.1 étape 3) ;
- **pas de dépendance aux events KB** : l'émission d'événements de complétion de job d'ingestion par
  Bedrock KB n'est pas garantie dans le périmètre du projet ; s'y adosser introduirait une
  dépendance non vérifiée. Si ces événements sont confirmés disponibles ultérieurement, le
  reconciler peut être complété par un déclenchement événementiel **sans changer le contrat d'état**
  (le tick planifié reste le filet de sécurité) ;
- le reconciler interroge `GetIngestionJob` pour les seuls documents en `ingesting` (borne la charge
  sur l'API KB), et est **idempotent** : rejouer un tick sur un document déjà `indexed` est un no-op.

Le reconciler s'exécute dans le service `fastapi` (tâche de fond) en V2 — aucun service ECS
supplémentaire n'est requis. Son ARN de scheduler et sa cible sont provisionnés par Terraform.

**Latence assumée (`V2-ADR-019`) :** un document uploadé n'est pas requêtable en quelques secondes
mais après le job KB (ordre de la minute) plus le délai du prochain tick de réconciliation. Le suivi
d'état exposé à l'utilisateur (HLD §6.2) reflète `ingesting` jusqu'à la complétion du job. Aucune
requête ne doit renvoyer de citation vers un document en `ingesting`.

### 5.2 Configuration de la data source KB

Paramètres fixés par configuration (Terraform, jamais codés en dur), traçés pour reproductibilité :

| Paramètre | Valeur V2 | Justification |
|---|---|---|
| Vector store | S3 Vectors | `V2-ADR-019` — pas d'OpenSearch Serverless |
| Région | `eu-west-3` | Sous réserve de la précondition `V2-ADR-019` (disponibilité KB+S3V à prouver avant implémentation, §1.6) |
| Préfixe S3 de la data source | `sources/` **uniquement** | le préfixe `restricted/` en est exclu (`V2-ADR-017`, §4.1) |
| Modèle d'embedding | paramètre, composante de l'espace | `V2-ADR-013` ; jamais codé en dur |
| Dimension de l'index | paramètre, composante de l'espace | fixée à la création de l'index, **immuable** |
| Métrique de distance | paramètre, composante de l'espace | fixée à la création de l'index, **immuable** |
| `embeddingSpaceId` | dérivé du triplet ci-dessus | identifiant opaque de l'espace ; tracé dans `documents` et dans les métadonnées de chunk |
| Taille max de chunk | **dérivée de la limite d'entrée du modèle** | vérifiée au démarrage — refus si incompatible (voir ci-dessous) |
| Recouvrement de chunk | fixe, configuré | reproductibilité ; `chunkerVersion` non géré par KB en V2 (voir limite §5.4) |
| Champs de métadonnées | `tenantId`, `documentId`, `version`, `status` | exposés au filtre `Retrieve` (`V2-ADR-006`) |

**Format et attribution de l'`embeddingSpaceId`.** L'identifiant est une valeur stable et opaque au
domaine : le code ne dérive aucune logique de sa forme, il ne fait que comparer des égalités
(`V2-ADR-013`). Il est attribué à la création de l'index, dérivé du triplet (modèle, dimension,
métrique), et enregistré comme paramètre Terraform aux côtés de `KB_ID`/`KB_DATA_SOURCE_ID` (§12).
Convention retenue : `<modelSlug>-<dimension>-<metric>` (par exemple `titan-v2-1024-cosine`), forme
lisible en exploitation mais **jamais parsée par le code**.

**Contrôle au démarrage de la taille de chunk (`V2-ADR-013`).** Chaque modèle d'embedding impose une
limite d'entrée en tokens, et ces limites diffèrent d'un ordre de grandeur d'un modèle à l'autre. Un
chunk qui la dépasse est, selon le modèle, rejeté ou **tronqué silencieusement** — et c'est ce
second cas qui est dangereux : la fin de chaque chunk trop long n'est jamais indexée, le document
paraît indexé, `chunkCount` est correct, et le rappel est amputé d'une part invisible du corpus. La
taille max de chunk est donc dérivée de la limite d'entrée du modèle configuré et **vérifiée au
démarrage de FastAPI** ; une configuration incompatible est un refus de démarrage, pas une perte de
rappel découverte à l'évaluation. Ce contrôle est le pendant, côté ingestion, de la dérivation de
`maxTokens` depuis la fenêtre de contexte du modèle de génération (`V2-LLD-003` §5.2.1).

### 5.3 Injection du `tenantId` dans les métadonnées de chunk

Pour que le filtre `Retrieve` puisse isoler par tenant, le `tenantId` doit être porté par les
métadonnées de chunk. En V2, il est fourni à KB via un **fichier de métadonnées S3 associé à chaque
source** (`<filename>.metadata.json`), généré par FastAPI à l'upload et contenant `tenantId`,
`documentId`, `version`, `status`, `classification`, `embeddingSpaceId`, `chunkerVersion`. KB
propage ces métadonnées aux chunks indexés.

Ce fichier de métadonnées est le point d'ancrage de l'isolation côté KB. Sa génération est un
contrôle testé (section 16).

**Statut des valeurs portées par ce fichier.** Deux régimes coexistent et ne doivent pas être
confondus :

| Champ | Rôle | Peut devenir obsolète ? |
|---|---|---|
| `tenantId`, `documentId`, `version` | isolation et identification — **filtrables**, socle du filtre `Retrieve` | non (immuables pour une version donnée) |
| `status` | filtrable ; exclut les documents non `indexed` du retrieval | oui, réconcilié à la ré-ingestion |
| `classification` | **filtre grossier uniquement** — la valeur qui autorise est celle de `documents` (§4.2, §6.2) | **oui** — une reclassification n'est pas propagée aux chunks sans réindexation |
| `embeddingSpaceId`, `chunkerVersion` | traçabilité de l'espace et du découpage | non pour un index donné (l'espace est immuable, §4.2) |

La ligne `classification` est le point sensible : sa valeur est figée par KB au moment de
l'indexation, et `V2-LLD-002` §5.4 énonce déjà que KB ne permet pas de reprendre finement une
métadonnée sans resynchronisation. Elle est donc utilisée comme pré-filtre de défense en profondeur,
**jamais comme décision d'autorisation**.

### 5.4 Limites assumées de l'ingestion KB en V2

- **`chunkerVersion` non maîtrisé finement** : la stratégie de chunking est celle de KB ; la
  réévaluation ciblée par version de chunker de `V2-ADR-003` n'est pas disponible en V2. Reprise en
  V3.
- **Grain d'état collapsé** : voir §4.3.

### 5.5 Changement d'espace d'embedding — index parallèle et bascule de pointeur

Un changement de modèle, de dimension ou de métrique change l'espace, donc **crée un index**
(§4.2). La question n'est pas s'il faut réindexer, mais dans quel ordre, et ce que le système sert
pendant l'opération.

**La resynchronisation en place est écartée (`V2-ADR-013`).** Purger l'index et le reconstruire avec
le nouveau modèle a deux défauts, dont un rédhibitoire : pendant la reconstruction le retrieval
répond sur un corpus partiel — dégradation progressive et silencieuse, `retrievalContext.status`
valant `ok` puisque des candidats sont bien retournés ; surtout, **une interruption en cours de
route laisse l'index dans un état mixte**, sans marqueur ni erreur, indistinguable d'un index sain.
Un index mixte répond avec des scores crédibles et des résultats faux : c'est la panne la plus
coûteuse du pipeline RAG, parce qu'elle est silencieuse pour la machine.

La séquence retenue est bornée et son point de non-retour est explicite :

```text
1. Création d'un index cible portant le nouvel embeddingSpaceId.
   En V2 : une nouvelle base de connaissances, le modèle d'embedding étant fixé à sa création.
   L'index courant continue de servir, sans modification.

2. Réindexation complète du corpus depuis S3 (source de vérité, V2-ADR-010)
   -> StartIngestionJob sur la data source de la nouvelle KB.

3. Exécution du DATASET DE RETRIEVAL de V2-ADR-018 sur l'index cible,
   à datasetVersion et fixturesVersion constants, comparaison à la baseline
   de l'index courant. Un écart au-delà de la marge configurée INTERDIT la bascule.
   (Un changement d'embeddingSpaceId n'invalide pas la baseline : c'est
    précisément l'écart que cette étape mesure.)

4. Bascule du pointeur applicatif : KB_ID / KB_DATA_SOURCE_ID / EMBEDDING_SPACE_ID
   -> opération atomique, UNIQUE POINT DE NON-RETOUR.

5. Conservation de l'index précédent pendant la période de grâce définie en V2-LLD-006
   -> le retour arrière est la bascule inverse du pointeur, sans reconstruction.

6. Suppression de l'index précédent à l'issue de la période de grâce.
```

L'étape 3 est ce qui distingue cette séquence d'un simple remplacement. Un modèle d'embedding plus
récent n'est pas meilleur sur un corpus donné par construction — le domaine, la langue et la taille
des chunks font varier le résultat. **Sans mesure, une migration d'embedding est un pari.** Elle
rend `V2-ADR-018` bloquant pour cette capacité : sans dataset d'évaluation, aucune migration
d'embedding n'est autorisée.

**Coûts assumés :** doublement temporaire du stockage vectoriel pendant la coexistence des deux
index, et recalcul complet des embeddings du corpus (proportionnel à sa taille). Ces deux grandeurs
sont une entrée pour `V2-LLD-007`.

**Délai de remise en service.** La somme (recalcul complet + évaluation `V2-ADR-018` + bascule) est
le délai qui doit tenir dans le préavis de fin de vie d'un modèle (`V2-ADR-012` : au moins six mois
en statut `Legacy`). Ce délai est **mesuré, pas estimé** : la première migration réalisée en fournit
la valeur de référence, et cette valeur devient le seuil d'alerte de la sonde de cycle de vie. Perdre
l'accès au modèle d'embedding ne dégrade pas le retrieval, il l'arrête : les vecteurs restent
lisibles mais plus aucune requête ne peut être projetée dans leur espace — **un index dont le modèle
est mort n'est pas dégradé, il est inerte.**

## 6. Retrieval V2

### 6.1 API `Retrieve` uniquement — jamais `RetrieveAndGenerate`

**Contrôle non négociable (`V2-ADR-019`) :** FastAPI appelle exclusivement l'API `Retrieve`, qui
renvoie les candidats (chunks + scores + métadonnées) à FastAPI. `RetrieveAndGenerate` est
**interdit** en code (violation bloquante en revue) car il injecterait le contexte dans un modèle
sans point de contrôle FastAPI, court-circuitant le post-filtrage tenant/ACL et la construction du
`retrievalContext`.

### 6.2 Chaîne de retrieval

```text
FastAPI.answer(question, tenantId, userAcl) :

  0. VÉRIFICATION D'ESPACE (V2-ADR-013, avant tout appel) :
        espace_index = adapter.get_embedding_space()      # lu depuis l'index, PAS la config
        si espace_index != EMBEDDING_SPACE_ID configuré :
             -> status = "degraded", reason = "embedding_space_mismatch"
             -> AUCUN retrieval exécuté (fail-closed)

  1. candidats = adapter.retrieve(question, filter={ tenantId, status: "indexed" }, topK)
        (adapter V2 == KB Retrieve avec filtre métadonnées)
        -> n_bruts = len(candidats)

  2. FILTRE GROSSIER sur la métadonnée de chunk (défense en profondeur, V2-ADR-017) :
        écarter les candidats dont chunk.classification est incompatible avec l'utilisateur.
        Cette valeur peut être OBSOLÈTE : elle ne décide pas, elle réduit le volume à lire.
        -> candidats_pre

  3. LECTURE DE LA SOURCE DE VÉRITÉ (V2-ADR-017, AVANT le filtre) :
        docIds = distinct(c.documentId for c in candidats_pre)     # <= topK
        docs   = documents.BatchGetItem(tenantId, docIds)          # une lecture groupée

  4. POST-FILTRAGE FastAPI (côté serveur, obligatoire) — ordre fail-closed à chaque étape :
        a. tenant         : docs[c].tenantId == tenant courant       sinon refus
        b. classification : niveau lu dans DOCUMENTS (pas le chunk)  détermine le socle
        c. ownership/ACL  : propriétaire ou partage explicite        restreint le socle
        d. indexabilité   : classification == "restricted"           -> JAMAIS dans le contexte
        e. entrée absente : documentId absent de docs                -> refus (fail-closed)
        -> n_retenus = len(candidats retenus) ; n_rejetes = n_bruts - n_retenus

  5. déterminer retrievalContext.status et reason (voir §6.2.1) :
     si KB indisponible                     -> status = "degraded"
     si divergence d'espace (étape 0)        -> status = "degraded"
     sinon si n_retenus > 0                  -> status = "ok"
     sinon si n_bruts == 0                   -> status = "skipped", reason = "no_match"
     sinon (n_bruts > 0 et n_retenus == 0)   -> status = "skipped", reason = "filtered_out"

  6. construire retrievalContext borné (topK, longueur max, dedup par documentId)
  7. résoudre citations depuis docs déjà lu à l'étape 3 (titre, page, sourceUri)
  8. transmettre retrievalContext à AgentCore Runtime (jamais le texte brut sans pointeur)
```

**Pourquoi `documents` est lu avant le filtre et non après (`V2-ADR-017`).** Dans la version
précédente de cette chaîne, la classification était filtrée à l'étape 2 et `documents` n'était lu
qu'à l'étape 5, pour résoudre les citations. La seule valeur disponible au moment de la décision
était donc celle **portée par le chunk**, figée à l'indexation. Une reclassification enregistrée
dans `documents` restait sans effet sur le filtre jusqu'à la prochaine ré-ingestion.

Le sens de l'écart était le problème. Une reclassification **restrictive** — un document dont on
resserre l'accès — est précisément celle qu'on attend immédiate, et c'était celle qui n'avait aucun
effet : le chunk continuait de porter l'ancien niveau, plus permissif, et le post-filtrage
l'appliquait. La fenêtre de sur-exposition durait jusqu'à la prochaine ré-ingestion, dont aucun
document ne fixait l'échéance. Un contrôle d'autorisation était traité comme une donnée
d'affichage.

Avec la séquence ci-dessus, **une reclassification est immédiatement effective sans réindexation**,
et la lecture de l'étape 3 sert deux fois : elle autorise (étape 4) puis résout les citations
(étape 7) — la lecture n'est pas dupliquée, elle est déplacée.

**Coût.** La lecture porte sur les candidats et non sur les seuls retenus : au plus `topK` documents
distincts, en une lecture groupée, la déduplication par `documentId` étant déjà prévue. Il est
assumé — un contrôle d'autorisation se juge sur sa justesse avant son coût. Si la latence dépasse le
budget de retrieval, le levier conforme est la réduction de `topK` ou un cache court par
`documentId`, **jamais** le retour à la décision sur la métadonnée de chunk.

**La classification est un plafond, l'ACL restreint en deçà (`V2-ADR-017`).** Un partage explicite
n'autorise pas à franchir un niveau : il autorise un accès **dans** ce que le niveau permet. Sans
cette règle, un partage suffirait à contourner la classification et l'attribut serait décoratif.
L'étape 4d n'est pas une répétition de 4b : `restricted` interdit l'injection dans un contexte
modèle **même à un utilisateur autorisé à lire le document**. La lecture directe et l'injection dans
un prompt ne sont pas le même acte — la seconde transmet le contenu à Bedrock et l'expose à
l'inférence. La lecture directe d'un document `restricted` par son propriétaire reste autorisée et
relève de `V2-LLD-005`.

**Un document `quarantined` est traité comme `restricted`**, quelle que soit sa classification
déclarée : son contenu n'a pas été validé, il n'est ni lisible ni indexable. Toute tentative de
reclassification sur un document `quarantined` est refusée par FastAPI, dans un sens comme dans
l'autre — le statut prime sur l'attribut.

### 6.2.1 Deux causes de `skipped` — ne pas les confondre (O3, revue PR #35)

Un `retrievalContext.status = "skipped"` recouvre deux situations opérationnellement très
différentes, distinguées par `reason` :

| `reason` | Cause | Interprétation | Signal |
|---|---|---|---|
| `no_match` | `Retrieve` n'a renvoyé aucun candidat (`n_bruts == 0`) | le corpus ne contient rien de pertinent — comportement normal | métrique de couverture, pas d'alerte |
| `filtered_out` | `Retrieve` a renvoyé des candidats mais le post-filtrage les a tous rejetés (`n_bruts > 0`, `n_retenus == 0`) | soit l'utilisateur n'a pas les droits (normal), soit le filtre est trop strict ou mal configuré (**anomalie possible**) | **seuil d'alerte distinct** (§15.1) : un taux élevé de `filtered_out` signale un défaut de configuration ACL/classification ou de métadonnées KB |

Confondre les deux masquerait une misconfiguration : un filtre trop agressif produirait des réponses
sans source tout en paraissant « pas de résultat ». La distinction `no_match` / `filtered_out` rend
ce cas observable.

**Trois causes distinctes de `filtered_out`**, qu'il faut savoir départager en exploitation :

| Cause | Origine | Régime |
|---|---|---|
| Droits insuffisants | l'utilisateur n'est ni propriétaire ni bénéficiaire d'un partage | **normal** — le filtre travaille |
| Faux négatif de reclassification | le chunk porte un niveau **plus restrictif** que `documents` (reclassification assouplissante non encore réindexée) | **normal, transitoire** — perte de rappel, pas d'isolation ; se résorbe à la réindexation suivante |
| Misconfiguration | métadonnées KB manquantes, filtre ACL trop large côté serveur, mapping de champs incorrect | **anomalie** — c'est ce que le seuil d'alerte cherche à détecter |

Le deuxième cas est la contrepartie assumée du filtre grossier de l'étape 2 (§6.2) : il ne peut
produire que des **faux négatifs**. Un chunk plus restrictif que sa source écarte un candidat
autorisé — la perte est de rappel, jamais d'isolation. L'inverse ne produit rien, la décision finale
étant prise sur `documents`.

**Un candidat dont l'entrée `documents` est absente est compté en `filtered_out`.** Si le
`BatchGetItem` ne retourne pas d'entrée pour un `documentId` — document supprimé dans la fenêtre
entre le `Retrieve` et la lecture groupée — le candidat est écarté sans erreur ni échec de la
requête (fail-closed de `V2-ADR-006`).

**Ces deux valeurs de `reason` sont l'attendu de cas de test, pas seulement un signal
d'observabilité (`V2-ADR-018`).** Un cas de la famille négative d'autorisation qui produirait
`no_match` au lieu de `filtered_out` **échoue**, même si aucun contenu n'a fuité : le filtre n'a pas
travaillé, et la prochaine régression passerait inaperçue (§16).

### 6.3 Post-filtrage : la ligne de défense

Le filtre `tenantId` passé à `Retrieve` s'appuie sur la configuration KB. Le **post-filtrage FastAPI
est la ligne de défense testée en priorité** : même si un candidat d'un autre tenant remontait
(erreur de config KB, métadonnée manquante), FastAPI le rejette avant qu'il n'atteigne le modèle.
Ce double contrôle (filtre `Retrieve` + post-filtrage) est ce qui rend l'isolation acceptable en V2
sans garantie par construction. En V3, le filtre `tenantId` construit avant la requête S3 Vectors
rend l'omission impossible par design.

### 6.4 Citations

Le retrieval retourne des références de chunk (`documentId`, `version`, `chunkIndex`, `sourceUri`),
jamais du contenu sans pointeur vérifiable. FastAPI résout les métadonnées d'affichage (titre, page)
**depuis les entrées `documents` déjà lues à l'étape 3 de §6.2** — la lecture n'est pas dupliquée.
Aucune citation n'est construite à partir du seul texte du modèle (principe `V2-ADR-003` conservé).

La couverture des citations est une propriété **mécanique et déterministe**, vérifiable sans
jugement sémantique : chaque référence citée existe, appartient au tenant, pointe vers un document
autorisé et vers un chunk effectivement présent dans le `retrievalContext`. C'est à ce titre qu'elle
est **bloquante** dans le gate qualité, là où la groundedness — qui exige un juge non étalonné — ne
l'est pas (§16.4).

## 7. Adapter de magasin vectoriel

### 7.1 Contrat

L'adapter est le **seul point d'échange V2 → V3**. Interface applicative stable :

```text
interface VectorRetrievalPort:
    get_embedding_space() -> EmbeddingSpaceId          # lu depuis l'index, jamais depuis la config
    ingest(documentId, version, sourceUri, metadata) -> IngestionHandle
    get_ingestion_status(handle) -> "ingesting" | "indexed" | "failed"
    retrieve(query, filter, topK) -> list[Candidate]   # Candidate = {chunkRef, score, metadata, text}
    delete(documentId, version) -> DeletionResult
```

| Méthode | Implémentation V2 (KB) | Implémentation V3 (S3 Vectors direct) |
|---|---|---|
| `get_embedding_space` | espace déclaré par la base de connaissances interrogée | métadonnées de l'index S3 Vectors |
| `ingest` | `StartIngestionJob` + fichier métadonnées S3 | enqueue SQS `stage=validate` (`V2-ADR-004`) |
| `get_ingestion_status` | `GetIngestionJob` | lecture `documents.status` |
| `retrieve` | `KB Retrieve` + filtre métadonnées | requête S3 Vectors, filtre `tenantId` pré-construit |
| `delete` | suppression source S3 + resync KB | saga suppression coordonnée (`V2-ADR-003`) |

### 7.1.1 Invariant de symétrie requête/document (`V2-ADR-013`)

Une requête doit être projetée dans l'espace du corpus qu'elle interroge. La violation de cet
invariant est la panne silencieuse décrite en §4.2, et elle a deux origines possibles :

- **dérive de configuration** : le paramètre de modèle d'embedding est modifié alors que l'index, lui,
  n'a pas changé ;
- **bascule incomplète** : le pointeur d'index est basculé mais la configuration d'embedding de
  requête ne l'est pas, ou l'inverse (§5.5 étape 4).

> **La configuration n'est jamais la source de vérité de l'espace.** L'`embeddingSpaceId` est lu
> depuis les métadonnées de l'index interrogé (`get_embedding_space()`), et comparé à la valeur
> configurée **avant** tout `retrieve` (§6.2 étape 0).

Le comportement sur divergence est **fail-closed** : `retrievalContext.status = degraded` avec
`reason = "embedding_space_mismatch"`, et **aucun retrieval n'est exécuté**. Servir une réponse sans
sources est acceptable ; servir des sources fausses avec des scores crédibles ne l'est pas.

**Symétriquement à l'écriture** : aucune écriture n'est admise dans un index dont l'espace diffère de
celui du producteur. En V2 la contrainte est portée par KB, qui fixe le modèle au niveau de la base
de connaissances ; le contrôle est néanmoins écrit dès la V2 dans l'adapter, car il devient
nécessaire en V3 et l'écrire tard revient à l'oublier au moment où il compte.

**Ce que la V2 acquiert sans effort, et ce qu'elle doit quand même écrire.** En V2 la symétrie est
structurellement garantie : KB projette la requête et les documents avec le même modèle. Le contrôle
n'est donc pas ce qui protège la V2 — il est ce qui rend le contrat de l'adapter complet, pour que
le report en V3 ne devienne pas une réécriture.

> **Précondition (`V2-ADR-013`) :** la capacité de KB à exposer l'espace d'origine des chunks reste
> à prouver. Si elle n'existe pas, `get_embedding_space()` retombe en V2 sur l'espace déclaré à la
> création de la base de connaissances (paramètre Terraform), et le contrôle d'homogénéité repose
> alors sur la seule discipline de configuration — risque résiduel à tracer, non à découvrir en
> exploitation.

### 7.2 Invariant de réversibilité

Le post-filtrage tenant/ACL, la construction du `retrievalContext` et la résolution des citations
sont **en dehors** de l'adapter, dans FastAPI. Ils ne changent pas à la bascule. L'adapter ne
renvoie jamais de contexte pré-assemblé prêt pour le modèle : il renvoie des candidats bruts que
FastAPI filtre. Cet invariant est vérifié par revue d'architecture avant merge de tout code de
retrieval.

## 8. Suppression et réindexation

### 8.1 Suppression (V2)

```text
DELETE /documents/{documentId} (FastAPI) :
  1. documents.status = "deleting"
  2. adapter.delete(documentId, version) :
        - suppression de l'objet S3 source (toutes versions, y compris les non-courantes)
          + fichier métadonnées, sur le préfixe portant le document (sources/ ou restricted/)
        - resynchronisation KB de la data source (retire les chunks du document de l'index)
          — sans effet pour un document restricted, qui n'y a jamais été indexé
  3. Vérification : aucun chunk résiduel pour documentId (Retrieve filtré doit renvoyer 0)
  4. documents.status = "deleted" — l'entrée est conservée 30 jours comme tombstone
     et CONSERVE sa classification (V2-ADR-017), puis purgée selon V2-LLD-006 §10
```

La suppression coordonnée exigée par `V2-ADR-006` est satisfaite en V2 par : suppression S3 +
resync KB + vérification d'absence de résidu. En V3, elle devient la saga applicative de
`V2-ADR-003`. La **preuve d'absence de résidu** est identique dans les deux phases.

**Le tombstone conserve `classification` (`V2-ADR-017`).** Une trace d'audit qui ne dirait pas à
quel niveau le document supprimé était classé n'atteste rien d'exploitable. Cette conservation n'est
pas une rétention différenciée : les trois niveaux portent la même durée de tombstone, sur les deux
préfixes. La classification n'est par ailleurs **pas une donnée personnelle** — elle qualifie la
ressource, non la personne — et n'entre dans le périmètre d'effacement de `V2-ADR-015` que par la
suppression de l'entrée `documents` qui la porte.

**La désindexation d'une transition vers `restricted` emprunte cette même mécanique** (retrait de la
source puis resynchronisation, §4.1). Elle est asynchrone, et cette asynchronie est **sans effet sur
l'autorisation** : dès l'écriture dans `documents`, le post-filtrage refuse l'injection (§6.2). Les
chunks survivants ne sont plus qu'un résidu à nettoyer.

### 8.2 Réindexation (V2)

Une réindexation crée une nouvelle `version` (S3 source `v<n+1>`, nouvelle entrée `documents`), la
version précédente passe `superseded`, puis une resync KB indexe la nouvelle version. La bascule
d'affichage vers la nouvelle version se fait après complétion du job (statut `indexed`).

## 9. Isolation multi-tenant

| Ligne de défense | Mécanisme V2 | Testé par |
|---|---|---|
| 1. Métadonnées de chunk | fichier `<filename>.metadata.json` avec `tenantId` généré serveur | test génération métadonnées |
| 2. Filtre `Retrieve` | filtre `tenantId` passé à KB | test filtre KB |
| 3. Filtre grossier `classification` | pré-filtre sur la métadonnée de chunk — **ne décide pas** | test faux négatif de reclassification |
| 4. **Lecture `documents` (BatchGetItem)** | `PK = tenantId#documentId` — **source de vérité de l'autorisation** | **test reclassification sans réindexation** |
| 5. **Post-filtrage FastAPI** | rejet côté serveur de tout candidat `tenantId != courant`, puis classification → ACL → indexabilité | **test cross-tenant bloquant** |
| 6. Résolution citations | depuis les entrées `documents` lues en 4 | test citation cross-tenant |

Aucune de ces lignes ne fait confiance au client. La ligne 5 est bloquante : un échec cross-tenant
en test empêche le merge (`V2-ADR-019`, `V2-ADR-006`).

**Les lignes 3 et 4 réalisent le partage décidé par `V2-ADR-017`** : la première réduit le volume à
lire et ne peut produire que des faux négatifs, la seconde décide. Une ligne 3 défaillante coûte du
rappel ; une ligne 4 défaillante coûterait l'isolation — c'est pourquoi elles ne sont pas
interchangeables et pourquoi la ligne 4 précède le filtre au lieu de le suivre.

## 10. Idempotence

- **Upload** : `creationOperationId` (UUID client-fourni ou généré) rend l'upload rejouable sans
  doublon, même pattern d'idempotence que `docs/adr/ADR-0006`/`ADR-0007` en V1 ;
- **Ingestion** : `StartIngestionJob` est idempotent au niveau document via le contenu S3 (un même
  contenu réingéré produit les mêmes chunks) ; `kbIngestionJobId` évite le double déclenchement ;
- **Suppression** : rejouable — une suppression sur un document déjà `deleted` est un no-op.

## 11. Contrats

### 11.1 API documentaire (extrait OpenAPI, détail `V2-LLD-010`)

| Route | Méthode | Corps / réponse | Idempotence |
|---|---|---|---|
| `/documents` | POST | multipart → `202 { documentId, operationId, status }` | `operationId` |
| `/documents/{id}` | GET | `200 { status, version, chunkCount, classification }` | lecture |
| `/documents/{id}` | DELETE | `202 { status: "deleting" }` | rejouable |
| `/documents/{id}/reindex` | POST | `202 { version, status: "ingesting" }` | `operationId` |

Champs interdits côté client (rejetés) : `tenantId`, `status`, `kbIngestionJobId`, `sourceUri`,
`embeddingSpaceId`, `chunkerVersion` — tous dérivés côté serveur.

`classification` est en revanche **déclarable à l'upload**, dans le domaine fermé
`internal` | `confidential` | `restricted` ; une valeur hors domaine est rejetée, une absence de
valeur produit le défaut `confidential` (`V2-ADR-017`). La reclassification suit deux régimes :

| Route | Sens | Régime |
|---|---|---|
| `PATCH /documents/{id}` (restrictif, ex. `internal` → `confidential`) | resserre l'accès | effet immédiat, **sans confirmation** |
| `PATCH /documents/{id}` (assouplissant, ex. `confidential` → `internal`) | élargit l'accès | **action mutante `V2-ADR-014`** : matérialisée, confirmée hors du chemin du modèle, puis exécutée |

L'asymétrie applique `V2-ADR-014` sans l'étendre : une action qui élargit un accès est une action à
conséquence de sécurité ; une action qui le resserre n'en est pas une. Un modèle ne déclenche jamais
un élargissement sur la seule foi d'un tour de conversation. La transition vers `restricted` ajoute
le coût structurel décrit en §4.1 (déplacement de préfixe, purge des versions non-courantes,
désindexation asynchrone) ; cette asynchronie est **sans effet sur l'autorisation**, qui bascule dès
l'écriture dans `documents`.

### 11.2 Schéma de métadonnées de chunk (source de l'isolation)

```json
{
  "tenantId": "<uuid>",
  "documentId": "<uuid>",
  "version": 1,
  "status": "indexed",
  "classification": "confidential",
  "sourceUri": "s3://.../sources/<tenantId>/<documentId>/v1/<file>",
  "chunkIndex": 0,
  "createdAt": "2026-01-01T00:00:00Z",
  "embeddingSpaceId": "titan-v2-1024-cosine",
  "chunkerVersion": "fixed-512-64"
}
```

`tenantId`, `documentId`, `version`, `status` sont **filtrables** (exposés à `Retrieve`) ; les autres
sont retournés mais filtrés côté FastAPI.

L'exemple porte `confidential` : c'est la valeur par défaut décidée par `V2-ADR-017` pour tout
document uploadé sans classification déclarée. `confidential` est fail-closed sur l'accès — seul le
propriétaire lit — **et** fonctionnel sur l'indexation : un défaut à `restricted` produirait un
système où aucun document n'est indexé sans geste explicite, alors que l'upload documentaire existe
pour alimenter le RAG.

> **Rappel (§4.2, §6.2) :** `classification` figure ici comme **filtre grossier**. La valeur qui
> autorise est celle de `documents`. Une valeur de chunk divergente de sa source est un état
> normal et transitoire, pas une incohérence à corriger.

## 12. Configuration

| Paramètre | Type | Défaut V2 | Note |
|---|---|---|---|
| `KB_ID` | secret/param | — | id de la Knowledge Base — **pointeur basculé à l'étape 4 de §5.5** |
| `KB_DATA_SOURCE_ID` | param | — | data source S3V — pointeur basculé avec `KB_ID` |
| `EMBEDDING_SPACE_ID` | param | — | `V2-ADR-013` — identifiant opaque de l'espace ; **comparé à `adapter.get_embedding_space()` avant chaque retrieval** (§6.2 étape 0) ; basculé avec `KB_ID` |
| `EMBEDDING_MODEL_ID` | param | configuré | composante de l'espace ; jamais codé en dur ; ne décide jamais seul de la compatibilité |
| `EMBEDDING_DIMENSION` | param | — | composante de l'espace ; immuable pour un index donné |
| `EMBEDDING_DISTANCE_METRIC` | param | — | composante de l'espace ; immuable pour un index donné |
| `CHUNK_MAX_TOKENS` | param | dérivé | **dérivé de la limite d'entrée du modèle, vérifié au démarrage** (§5.2) — refus de démarrage si incompatible |
| `CHUNKER_VERSION` | param | — | stratégie de découpage ; distincte de l'espace, évaluable à espace constant |
| `RESTRICTED_S3_PREFIX` | param | `restricted/` | préfixe hors data source KB (`V2-ADR-017`, §4.1) |
| `RETRIEVE_TOP_K` | param | 8 | candidats demandés à `Retrieve` ; borne aussi la lecture groupée `documents` (§6.2 étape 3) |
| `RETRIEVAL_CONTEXT_MAX_CHUNKS` | param | 5 | après post-filtrage/dedup |
| `RETRIEVAL_CONTEXT_MAX_CHARS` | param | 6000 | borne du contexte |
| `enable_rag` | feature flag | `true` (V2) | dégradation contrôlée si `false` |
| `enable_kb_ingestion` | feature flag | `true` (V2) | bascule vers pipeline applicatif = flag V3 |

## 13. Sécurité

### 13.1 IAM (least privilege)

- **Rôle FastAPI** (`V2-LLD-001` §5.1) : `bedrock-agent-runtime:Retrieve` sur l'ARN de la KB,
  `bedrock-agent:StartIngestionJob` / `bedrock-agent:GetIngestionJob` / `bedrock-agent:ListIngestionJobs`
  sur la data source, lecture/écriture `documents`, lecture/écriture S3 source, `kms:Decrypt` sur la
  CMK du bucket. **Pas** de `bedrock-agent-runtime:RetrieveAndGenerate` dans la politique
  (interdiction §6.1 renforcée par IAM). **Pas** d'action `s3vectors:*` en V2 (l'accès direct S3
  Vectors est réservé à la cible V3).
- **Rôle d'exécution KB** : lecture S3 source **restreinte au préfixe `sources/`** (le préfixe
  `restricted/` doit être hors de portée de ce rôle — c'est le contrôle IAM qui rend le niveau
  `restricted` non indexable par construction et non par configuration de data source seule),
  écriture index S3 Vectors, invocation du modèle d'embedding — géré par la configuration de la KB,
  distinct du rôle FastAPI et du rôle de tâche ECS.
- **Rôle d'exécution KB d'évaluation** : même politique, sur la base de connaissances de fixtures
  (`V2-ADR-018`, §16.4) — isolée de la production, jamais adossée au bucket documentaire réel.

> **Préfixes IAM (O2, revue PR #35) :** les actions Bedrock KB relèvent des services
> `bedrock-agent-runtime` (plan d'exécution : `Retrieve`) et `bedrock-agent` (plan de contrôle :
> `*IngestionJob`), **pas** du service `bedrock` (réservé à l'invocation de modèles). Les ARN de
> ressource exacts sont à confirmer contre la documentation IAM Bedrock à l'implémentation.

### 13.2 Chiffrement

- S3 source, S3 Vectors, `documents` : chiffrement au repos KMS ;
- en transit : TLS via VPC endpoints (`V2-LLD-001`) ;
- fichier de métadonnées S3 : même chiffrement que la source.

### 13.3 Contenu documentaire = donnée non fiable

Le texte des chunks retournés par `Retrieve` est traité comme donnée non fiable (principe
`V2-ADR-002`) : il n'est jamais interprété comme instruction. Le `retrievalContext` transmis au
Runtime est balisé comme contexte, pas comme prompt système. Défense prompt injection documentaire :
détaillée en `V2-LLD-005`, consommée ici.

## 14. Résilience

| Panne | Comportement V2 |
|---|---|
| KB `Retrieve` indisponible | `retrievalContext.status = "degraded"` ; la conversation continue sans échec (dégradation `V2-ADR-003`) |
| KB ingestion échoue | `documents.status = "failed"` ; suivi utilisateur reflète l'échec ; réessai manuel/automatique borné |
| S3 Vectors indisponible | remonté par KB comme échec `Retrieve` → `degraded` |
| `documents` indisponible | **aucun retrieval servi** — `degraded` : la lecture de `documents` étant la source de vérité de l'autorisation (§6.2 étape 3), son indisponibilité interdit de filtrer, donc de répondre avec des sources |
| Divergence d'espace d'embedding | `degraded`, `reason = "embedding_space_mismatch"` — aucun retrieval exécuté (`V2-ADR-013`, §7.1.1) |
| Modèle d'embedding en fin de vie | l'index devient **inerte**, pas dégradé : plus aucune requête n'est projetable dans son espace ; alerte de cycle de vie, migration §5.5 déclenchée |
| Modèle juge indisponible | groundedness **marquée non mesurée** dans le rapport, sans `FAIL` ni effet sur le verdict des métriques déterministes (`V2-ADR-018`) |

Aucun de ces cas ne renvoie de contenu non filtré ou de citation non vérifiée : la dégradation est
toujours dans le sens de la sûreté.

**Le cas `documents` indisponible a changé de comportement en v0.4.** Il produisait auparavant une
« réponse sans citations » : `documents` n'étant lu qu'à l'étape de résolution des citations, son
indisponibilité n'empêchait pas de servir le contexte. Depuis que la classification qui autorise est
celle de `documents` (`V2-ADR-017`), cette table est sur le chemin de l'autorisation : servir un
contexte sans avoir pu la lire reviendrait à répondre sans avoir filtré. Le fail-closed de
`V2-ADR-006` s'applique — servir une réponse sans sources est acceptable, servir des sources non
autorisées ne l'est pas.

## 15. Observabilité et coûts

### 15.1 Métriques

- ingestion : nombre de jobs, durée, taux d'échec, latence upload→`indexed` (reflète la latence
  asynchrone assumée) ;
- retrieval : latence `Retrieve`, `topK` effectif, taux de `degraded`, taux de `skipped` **ventilé
  par `reason`** (`no_match` vs `filtered_out`, §6.2.1), nombre de candidats rejetés au
  post-filtrage. Deux signaux distincts :
  - un rejet **cross-tenant** > 0 est une **alerte de sécurité** (défense en profondeur déclenchée) ;
  - un taux de `skipped/filtered_out` au-dessus d'un seuil (à calibrer, ex. > 20 % des requêtes non
    vides) est une **alerte de configuration** (ACL/classification trop stricte ou métadonnées KB
    manquantes) — distincte du `no_match` qui, lui, ne déclenche pas d'alerte ;
- **divergence d'espace d'embedding** (`reason = "embedding_space_mismatch"`, §6.2 étape 0) : toute
  occurrence est une **alerte de configuration critique** — le retrieval est arrêté, pas dégradé.

**Métriques de qualité — deux régimes distincts (`V2-ADR-018`).** Les cinq grandeurs nommées par
`V2-ADR-003` ne se mesurent pas sur le même chemin et n'ont ni le même déterminisme ni le même
verdict possible. Elles ne forment pas un bloc homogène :

| Métrique | Dataset | Appel de génération | Déterministe à index constant | Exécution | Verdict |
|---|---|---|---|---|---|
| recall@k | retrieval | non | **oui** | CI, à chaque changement du pipeline | **bloquant** |
| precision@k | retrieval | non | **oui** | CI | **bloquant** |
| couverture des citations | retrieval + résolution | non | **oui** | CI | **bloquant** |
| taux de refus | génération | oui | non | planifiée, hors CI | publié, non bloquant |
| groundedness | génération | oui | non, et exige un juge | planifiée, hors CI | publié, non bloquant |

Les trois premières sont des fonctions de l'index et de la chaîne de filtrage : à index constant,
deux exécutions donnent le même résultat, sans appel Bedrock de génération, à coût quasi nul. Les
deux dernières portent sur la réponse produite, dont la sortie varie d'une exécution à l'autre.

**La groundedness est mesurée et publiée, jamais bloquante**, parce que son instrument — un modèle
juge Bedrock, distinct de celui qui produit la réponse évaluée — **n'est pas étalonné** : rien
n'établit sa concordance avec un jugement humain sur ce corpus. Rendre bloquante une mesure dont
l'instrument n'est pas validé remplacerait une incertitude par une fausse certitude. Le juge subit
par ailleurs le cycle de vie de `V2-ADR-012` : son indisponibilité laisse la groundedness
**marquée non mesurée** dans le rapport, sans `FAIL` et sans effet sur le verdict des métriques
déterministes.

C'est cette séparation qui rend exécutable l'étape 3 de la bascule d'embedding (§5.5) : elle porte
sur le **seul** dataset de retrieval, déterministe et reproductible. Un gate non déterministe
n'est pas un gate.

- métriques d'exploitation ci-dessus (latence, `degraded`, `skipped`) : mesurées sur le **corpus
  réel**, distinctes de l'évaluation de qualité qui s'exécute sur le **corpus de fixtures** isolé.

### 15.2 Corrélation

`requestId`/`operationId` propagés de l'upload au job KB et du `Retrieve` à la réponse
(OpenTelemetry, `V2-ADR-008`).

### 15.3 Coûts (ordre de grandeur, `eu-west-3`)

- S3 Vectors : stockage + requêtes (faible pour un corpus portfolio) ;
- KB : ingestion (par job) + `Retrieve` (par requête) ;
- embeddings Bedrock : par token ingéré ;
- **pas d'OpenSearch Serverless** (économie clé de `V2-ADR-019`, ~$700/mois évités).

Le coût V2 est comparable à celui du pipeline applicatif, sans le coût de développement (~2 700
lignes non écrites).

## 16. Tests et preuves

### 16.1 Preuves de sûreté et d'intégration

| Preuve attendue | Type | Bloquant |
|---|---|---|
| Une requête ne retourne jamais de chunk d'un autre tenant | cross-tenant, post-filtrage FastAPI | **Oui** |
| `RetrieveAndGenerate` absent du code et de la politique IAM | statique + IAM | **Oui** |
| Le fichier de métadonnées porte le bon `tenantId` généré serveur | intégration | Oui |
| Une suppression ne laisse aucun résidu (S3 + index KB) | intégration | Oui |
| Un document en `ingesting` n'est jamais cité | intégration | Oui |
| `retrievalContext.status = degraded` quand KB indisponible, sans échec conversation | résilience | Oui |
| Chaque citation est résolvable vers une source réelle et autorisée | intégration | Oui |

### 16.2 Preuves de classification (`V2-ADR-017`)

| Preuve attendue | Type | Bloquant |
|---|---|---|
| Un document reclassé `internal` → `confidential` cesse d'être retourné à un membre du tenant non propriétaire **sans réindexation** | intégration — **preuve centrale de la correction §6.2** | **Oui** |
| Un chunk portant `internal` obsolète dont `documents` porte `confidential` n'est pas retourné — le filtre grossier ne décide pas | intégration | **Oui** |
| Un chunk portant `confidential` dont `documents` porte `internal` est écarté et compté en `filtered_out`, sans erreur — la perte est de rappel, et elle est mesurée | intégration | Oui |
| Un document `restricted` n'apparaît dans aucun `retrievalContext`, y compris pour son propriétaire, **et** reste lisible par lui en accès direct | intégration — les deux volets sont nécessaires | **Oui** |
| Aucun chunk d'un document `restricted` n'existe dans l'index (`Retrieve` non filtré en test) | intégration | **Oui** |
| Un partage explicite sur un document `restricted` n'autorise pas son injection dans un contexte modèle — le plafond n'est pas franchi par l'ACL | négative | **Oui** |
| Un document uploadé sans classification déclarée reçoit `confidential` et n'est lisible par aucun autre membre du tenant | intégration | Oui |
| Un document `quarantined` n'est ni lisible ni indexable, quelle que soit la classification déclarée | négative | Oui |
| Une valeur hors du domaine fermé est refusée à l'écriture ; une entrée portant une valeur inconnue provoque un refus de lecture, jamais un accès par défaut | négative | **Oui** |
| Un candidat dont `documentId` est absent du `BatchGetItem` est écarté sans erreur et compté en `filtered_out` | négative | Oui |
| Une reclassification sur un document `quarantined` est refusée, dans les deux sens | négative | Oui |
| Après transition vers `restricted` : aucune version S3 non-courante ne subsiste à l'ancien préfixe, aucun chunk de l'ancien préfixe n'est ingéré | intégration | **Oui** |
| Une reclassification assouplissante sans confirmation `V2-ADR-014` est refusée ; une reclassification restrictive aboutit sans confirmation | négative | Oui |

### 16.3 Preuves d'espace d'embedding (`V2-ADR-013`)

| Preuve attendue | Type | Bloquant |
|---|---|---|
| Une requête projetée dans un espace différent de celui de l'index produit `degraded` **au lieu d'exécuter la recherche** | négative — **preuve la plus importante : sans elle la panne silencieuse reste possible** | **Oui** |
| L'écriture d'un vecteur d'un espace étranger dans un index est refusée, non acceptée puis détectée après coup | négative | **Oui** |
| Une configuration de chunking dépassant la limite d'entrée du modèle provoque un **refus au démarrage**, et aucune troncature silencieuse à l'ingestion | démarrage + intégration | **Oui** |
| Migration complète en test : index parallèle construit, dataset de retrieval exécuté sur les deux index, écart mesuré, bascule effectuée | intégration | Oui |
| Retour arrière après bascule : effectué par bascule inverse du pointeur, sans reconstruction, vérifié sur le même dataset | intégration | Oui |
| Délai de remise en service mesuré sur cette migration et enregistré comme valeur de référence du seuil d'alerte de cycle de vie | mesure | Oui |
| Restauration après changement d'espace : la reconstruction se fait dans l'espace déclaré par l'index restauré ; un mélange d'espaces est impossible à produire par la procédure | intégration | **Oui** |

### 16.4 Gate qualité (`V2-ADR-018`)

> **Le critère du gate est la non-régression contre une baseline versionnée. Aucun seuil absolu de
> qualité n'est inscrit dans ce LLD.**

Un seuil absolu — « recall@5 ≥ 0,8 » — appliqué à un dataset que l'équipe rédige elle-même ne mesure
pas la qualité du système : il mesure **la difficulté que l'auteur du dataset a choisi de se
donner**. Un seuil non atteint se corrige en reformulant une question ambiguë, geste légitime en
soi ; le seuil est alors toujours franchi et ne détecte plus aucune régression. Une gate qui ne peut
pas échouer n'est pas une gate.

Le gate comporte donc **deux composantes de nature différente** :

| Composante | Critère | Peut être entériné par une baseline ? |
|---|---|---|
| **Propriétés binaires de sûreté** | zéro chunk cross-tenant, zéro chunk `restricted` dans un `retrievalContext`, zéro citation non résolvable | **jamais** — valeur admissible zéro, non négociable |
| **Métriques déterministes de retrieval** | écart ≤ marge configurée avec la baseline (recall@k, precision@k, couverture des citations) | oui — l'écart toléré est une donnée versionnée, révisée sous revue |

**Régime d'amorçage.** La première exécution sur un couple (`datasetVersion`, `fixturesVersion`,
`embeddingSpaceId`) inédit **établit** la baseline et ne peut pas échouer sur les métriques de
qualité — elle reste intégralement soumise aux propriétés binaires de sûreté. Sans ce régime, le
gate serait inapplicable au jour de sa création.

**Ce à quoi une baseline est attachée**, et l'effet de chaque champ sur sa validité :

| Champ | Effet d'un changement | Raison |
|---|---|---|
| `datasetVersion` | **invalide** | les cas mesurés changent → régime d'amorçage |
| `fixturesVersion` | **invalide** | le corpus interrogé change → régime d'amorçage |
| `topK` | **invalide** | `recall@5` et `recall@10` ne sont pas deux valeurs d'une même métrique |
| `embeddingSpaceId` | **n'invalide pas** | c'est précisément l'écart que l'étape 3 de §5.5 mesure |
| `chunkerVersion` | **n'invalide pas** | c'est l'écart entre deux stratégies de découpage, à espace constant |

Cette asymétrie rend impossible de masquer une régression du pipeline en modifiant le dataset, la
profondeur de retrieval ou les fixtures, tout en autorisant la comparaison qu'une migration
d'embedding exige.

**Composition obligatoire du dataset de retrieval.** Quatre familles, dont les trois dernières
portent l'essentiel du pouvoir de détection sur un corpus de faible volumétrie — sur quelques
dizaines de chunks interrogés avec un `topK` de 5 à 10, recall@k plafonne au voisinage de 1 et
**cesse de discriminer** :

| Famille | Entrée | Attendu | Détecte |
|---|---|---|---|
| Positive | question dont la réponse est dans le corpus | le chunk attendu figure dans les `k` premiers | régression de rappel, dérive d'espace |
| Négative de corpus | question sans réponse dans le corpus | `status = skipped`, `reason = no_match` | production d'une réponse sans source |
| Négative d'autorisation | réponse dans un document d'un autre tenant, ou non partagé | aucun candidat retenu, `reason = filtered_out` | régression du post-filtrage |
| Négative d'indexabilité | réponse dans un document `restricted` | aucun chunk dans le `retrievalContext`, y compris pour le propriétaire | régression de `V2-ADR-017` |

La famille d'indexabilité se décline en **deux sous-familles obligatoires**, dont l'attendu diffère :

- document `restricted` **dès son ingestion**, donc jamais indexé → aucun candidat, `reason = no_match` ;
- document indexé puis **reclassifié en `restricted`** → un candidat produit, écarté par le
  post-filtrage, `reason = filtered_out`.

**C'est la seconde qui porte la détection** : elle seule établit que le post-filtrage a travaillé sur
un chunk réellement présent dans le résultat brut. La première ne vaut que tant que l'indexation
reste correcte, et deviendrait silencieusement vide si un défaut d'indexation la satisfaisait pour
la mauvaise raison.

**Corpus de fixtures isolé de la production.** Le corpus de production change à chaque upload : un
document ajouté modifie les voisins d'une requête, donc le classement, donc recall@k — sans qu'aucun
changement du système soit en cause, ce qui invalide la baseline. Le dataset exige donc son propre
corpus, **figé et versionné**, indexé dans une **base de connaissances distincte** de celle de
production (`V2-ADR-018`). Ce corpus doit contenir au moins deux tenants, un document non partagé,
un document `restricted` dès son ingestion et un document reclassifié en `restricted` après
indexation : `fixturesVersion` identifie donc un état atteint par une **séquence d'opérations**, pas
un simple jeu de fichiers.

**L'évaluation s'exécute à travers l'adapter et le post-filtrage FastAPI**, jamais contre `Retrieve`
directement — une évaluation qui court-circuiterait le post-filtrage ne pourrait pas porter les
familles négatives d'autorisation et d'indexabilité, précisément celles dont dépend le pouvoir de
détection.

| Preuve attendue | Type | Bloquant |
|---|---|---|
| Une régression injectée dans la chaîne de post-filtrage fait **échouer** le dataset de retrieval | négative — **sans elle, rien n'établit que le gate peut échouer** | **Oui** |
| Deux exécutions consécutives sur un index inchangé produisent des métriques identiques, ou une dispersion bornée et mesurée | déterminisme | Oui |
| Une exécution sur un couple inédit établit une baseline et rend `PASS` sans comparaison, tout en échouant si une propriété binaire est violée | amorçage | Oui |
| Un changement de `datasetVersion` ou de `topK` invalide la baseline ; un changement d'`embeddingSpaceId` ne l'invalide pas et produit un écart mesuré | intégration | Oui |
| Un cas de la famille négative d'autorisation produit `filtered_out` et non `no_match` — l'inversion fait échouer le cas | négative | **Oui** |
| Les deux sous-familles d'indexabilité sont couvertes, avec leurs `reason` respectifs | négative | **Oui** |
| Une baseline entérinant une violation d'isolation est impossible : le cas de sûreté échoue indépendamment de toute comparaison | négative | **Oui** |
| Le corpus de fixtures est indexé dans une ressource distincte : une ingestion de production ne modifie aucune métrique de baseline | intégration | Oui |
| La groundedness ne produit aucun `FAIL` tant que la concordance du juge n'est pas établie | régime | Oui |

Les preuves sont redacted, versionnées et conservées (`V2-LLD-009`), qui fixe par ailleurs la valeur
initiale de l'écart toléré à partir de la dispersion observée — **non postulée**.

## 17. Exploitation

### 17.1 Relancer une ingestion échouée

```text
# 1. Identifier les documents en échec
aws dynamodb query --table-name documents --index-name by-status --key-condition ... (status="failed")
# 2. Relancer le job KB pour la data source
aws bedrock-agent start-ingestion-job --knowledge-base-id <KB_ID> --data-source-id <DS_ID>
# 3. Réconcilier documents.status après complétion
```

### 17.2 Réhydrater l'index après incident

```text
# La source de vérité est S3 (versioning activé).
# 0. LIRE L'ESPACE DÉCLARÉ PAR L'INDEX RESTAURÉ (V2-ADR-013) — pas la config courante
#    espace_index = adapter.get_embedding_space()
#    si espace_index != EMBEDDING_SPACE_ID courant :
#         -> CE N'EST PAS UNE RESTAURATION, C'EST UNE MIGRATION : appliquer §5.5 (évaluation comprise)
# 1. Vérifier l'intégrité des objets S3 source
# 2. start-ingestion-job (resynchronisation complète de la data source, dans l'espace de l'étape 0)
# 3. Recalculer chunkCount et réconcilier documents
# 4. Rejouer le DATASET DE RETRIEVAL sur le corpus de FIXTURES (pas sur le corpus restauré)
#    -> verdict = non-régression vs baseline ; seules les métriques déterministes sont bloquantes
```

**Une reconstruction est toujours totale à l'échelle d'un index, et se fait dans l'espace déclaré
par cet index (`V2-ADR-013`).** Une reconstruction produit des vecteurs avec la configuration active
au moment où elle s'exécute. Si un changement d'espace est intervenu entre la sauvegarde et la
restauration, reconstruire une partie du corpus avec la configuration courante et laisser le reste
dans l'ancien espace produit exactement **l'index mixte** que §4.2 interdit — sans marqueur, sans
erreur, avec des scores crédibles et des résultats faux.

> Restaurer dans un espace différent n'est pas une restauration : **c'est une migration**, et elle
> suit la séquence de bascule de §5.5, évaluation comprise. L'étape 0 ci-dessus est ce qui rend
> cette distinction opérante au lieu de la laisser à la vigilance de l'opérateur.

L'étape 4 rejoue le dataset **sur le corpus de fixtures**, jamais sur le corpus restauré : le volume
restauré ne doit avoir aucun effet sur le verdict (`V2-ADR-018`).

### 17.3 Diagnostiquer une réponse sans sources

```text
# 1. Vérifier retrievalContext.status ET reason dans les traces
# 2. degraded + reason = "embedding_space_mismatch"
#       -> DIVERGENCE D'ESPACE (V2-ADR-013) : comparer adapter.get_embedding_space()
#          et EMBEDDING_SPACE_ID configuré. Cause probable : bascule §5.5 incomplète
#          (KB_ID basculé sans EMBEDDING_SPACE_ID, ou l'inverse). Aucun retrieval n'a été exécuté.
#    degraded (autre)
#       -> vérifier disponibilité KB / S3 Vectors / table documents
#    skipped + reason = "no_match"
#       -> normal : le corpus ne contient rien de pertinent. Pas d'action.
#    skipped + reason = "filtered_out"
#       -> départager les trois causes (§6.2.1) :
#          a. droits insuffisants          -> normal, vérifier l'ACL attendue
#          b. faux négatif de reclassif.   -> normal transitoire : chunk plus restrictif
#                                             que documents ; se résorbe à la réindexation
#          c. misconfiguration             -> ANOMALIE : métadonnées KB manquantes,
#                                             mapping de champs incorrect
# 3. Vérifier le compteur "candidats rejetés au post-filtrage" (alerte sécurité si cross-tenant)
# 4. Pour départager (b) de (c) : comparer chunk.classification et documents.classification
#    sur un échantillon de candidats rejetés. Un écart systématique dans le sens
#    "chunk plus restrictif" est le cas (b) ; un rejet sans écart de classification est le cas (c).
```

## 18. Trajectoire vers la cible V3

La bascule vers le pipeline applicatif (`V2-ADR-003`/`V2-ADR-004`) se fait par :

1. implémentation V3 de l'adapter (`retrieve` → S3 Vectors direct ; `ingest` → SQS `stage=validate` ;
   `get_embedding_space` → métadonnées de l'index S3 Vectors) ;
2. provisionnement du module ECS `ingestion` + SQS + DLQ (différé en V2) ;
3. réexpansion des états collapsés (`ingesting` → `parsing`/`chunking`/`embedding`/`indexing`) ;
4. reprise applicative de la migration d'embeddings : la séquence de §5.5 ne change pas, seul son
   point d'application se déplace — un nouvel index au lieu d'une nouvelle base de connaissances
   (`V2-ADR-013`) ;
5. bascule du flag `enable_kb_ingestion` → `false`, KB retirée.

**Ce que la V3 doit implémenter et que la V2 obtient gratuitement.** En V2, la symétrie
requête/document est structurellement garantie par KB, qui projette la requête et les documents avec
le même modèle. En V3, FastAPI produit lui-même l'embedding de requête avant d'interroger S3
Vectors : le contrôle de §7.1.1 cesse d'être une précaution et devient **le seul mécanisme** qui
empêche la panne silencieuse. C'est la raison pour laquelle il est écrit dès la V2.

FastAPI (post-filtrage, `retrievalContext`, citations), AgentCore Runtime, les agents, les tools
MCP, le HLD et la CAM **ne changent pas**. Les schémas de métadonnées `V2-ADR-006` étant respectés
dès la V2, la migration ne réécrit pas les contrats d'isolation.
