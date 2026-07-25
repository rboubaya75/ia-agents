# V2-LLD-002 — RAG et ingestion documentaire

- **Version :** 0.2
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§6.2, §9)
- **ADR de référence :** `V2-ADR-019` (décision de phasage), `V2-ADR-003`, `V2-ADR-004`,
  `V2-ADR-006`, `V2-ADR-010`, `V2-ADR-013`, `V2-ADR-017`, `V2-ADR-018`
- **Gate :** V2-G2

> **Révision v0.2 (revue PR #35) :** contrat antivirus clarifié (verdict consommé de `V2-LLD-005`,
> retrait du « worker » non défini) ; mécanisme de réconciliation des jobs KB tranché (reconciler
> planifié, §5.1) ; préfixes IAM Bedrock corrigés (`bedrock-agent-runtime:Retrieve`,
> `bedrock-agent:*IngestionJob`, §13.1) ; précondition de disponibilité KB+S3V explicitée (§1.6).

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD/Charte | Libellé |
|---|---|
| V2-ARCH-006 | RAG applicatif fondé sur S3 Vectors ; en V2, ingestion/retrieval via KB adossé à S3V, FastAPI conservant le filtrage tenant/ACL ; pipeline applicatif = cible V3 |
| HLD §6.2 | Flux d'ingestion documentaire et suivi d'état exposé à l'utilisateur |
| HLD §9 | Modèle de données documentaire, versioning S3, suppression coordonnée |
| ADR-019 | KB adossé à S3 Vectors en V2 ; FastAPI garde `Retrieve`, post-filtrage tenant/ACL, `retrievalContext`, citations ; pipeline SQS+worker ECS = cible V3 |
| ADR-006 | Métadonnées de filtrage obligatoires : `tenantId`, `documentId`, `version`, `status` |
| ADR-018 | Dataset d'évaluation versionné et métriques de retrieval (gate qualité) |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-019 | **Décision structurante du LLD** : phase V2 = KB adossé à S3 Vectors ; FastAPI utilise l'API `Retrieve` uniquement, applique le post-filtrage tenant/ACL, construit le `retrievalContext` et résout les citations ; adapter de magasin vectoriel = point de migration unique vers la cible V3 |
| V2-ADR-003 | **Cible V3** : schéma de stockage (S3 source, S3 Vectors, table `documents`), métadonnées de chunk, citations, suppression coordonnée. Les contrats d'isolation et de citations qu'il fixe restent applicables en V2 ; leur réalisation d'ingestion diffère (KB) |
| V2-ADR-004 | **Cible V3** : pipeline d'ingestion applicatif SQS + worker ECS. Non provisionné en V2 (l'ingestion V2 est déléguée à KB `StartIngestionJob`) |
| V2-ADR-006 | Métadonnées filtrables obligatoires `tenantId`, `documentId`, `version`, `status` ; suppression coordonnée ; preuve cross-tenant |
| V2-ADR-010 | Sauvegarde/restauration : versioning S3 source, réhydratation de l'index par resynchronisation KB |
| V2-ADR-013 | Versionnement des embeddings : en V2 délégué à KB (resynchronisation) ; `embeddingModelId`/`embeddingVersion` tracés côté `documents` pour préparer la reprise V3 |
| V2-ADR-017 | Classification documentaire : `classification` porté par la table `documents`, appliqué au post-filtrage FastAPI |
| V2-ADR-018 | Stratégie de tests RAG : dataset versionné, recall@k, precision@k, groundedness, couverture des citations, taux de refus |

### 1.3 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-001 | Ingress : couvert par `V2-LLD-001` |
| V2-ADR-002 | Répartition FastAPI/Runtime : couvert par `V2-LLD-003` ; ce LLD applique seulement le principe « contenu documentaire = donnée non fiable » |
| V2-ADR-005 | Framework d'agents : couvert par `V2-LLD-003` |
| V2-ADR-007 | Plateforme ECS : couvert par `V2-LLD-001` (le module `ingestion` ECS n'est pas provisionné en V2) |

### 1.4 Périmètre et exclusions

**Inclus (V2) :** formats et limites d'upload, quarantaine, validation/antivirus, déclenchement
d'ingestion KB, configuration de la data source KB (chunking, modèle d'embedding), magasin
vectoriel S3 Vectors adossé à KB, table DynamoDB `documents`, adapter de retrieval, post-filtrage
tenant/ACL, construction du `retrievalContext`, résolution des citations, suppression et
réindexation via KB, réhydratation, dataset et métriques d'évaluation.

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
    -> adapter.retrieve() == KB Retrieve (candidats + scores + métadonnées)   [jamais RetrieveAndGenerate]
    -> FastAPI : post-filtrage tenant + ACL + classification    (OBLIGATOIRE, côté serveur)
    -> FastAPI : construction du retrievalContext borné (ok | degraded | skipped)
    -> FastAPI : résolution des citations via DynamoDB documents
    -> AgentCore Runtime (IAM-only, ne fait jamais de retrieval)

Phase V3 (cible, V2-ADR-003 / V2-ADR-004)
    -> adapter.retrieve() == requête S3 Vectors directe (filtre tenantId construit avant la requête)
    -> ingestion applicative SQS + worker ECS
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
- préfixe par tenant : `sources/<tenantId>/<documentId>/v<version>/` ;
- accès en lecture par le rôle d'ingestion KB (section 13) et par FastAPI ; aucun accès public ;
- le contenu source reste la **source de vérité** : l'index S3 Vectors et les métadonnées sont
  reconstructibles à partir de S3 + config KB.

### 4.2 S3 Vectors (backend de KB en V2)

- un index vectoriel partagé (pas d'index par tenant en V2 — l'isolation repose sur le filtre
  `tenantId` + le post-filtrage FastAPI, cohérent avec `V2-ADR-003`) ;
- métadonnées de chunk **filtrables obligatoires** : `tenantId`, `documentId`, `version`, `status`
  (imposées par `V2-ADR-006`) ; ces champs sont mappés dans la configuration de la data source KB
  pour être exposés au filtre `Retrieve` ;
- métadonnées non filtrables : `chunkIndex`, `sourceUri`, `createdAt`, `embeddingModelId`,
  `classification` (le post-filtrage classification se fait aussi côté FastAPI via `documents`) ;
- l'index est écrit par KB, jamais par FastAPI en V2 (en V3, l'adapter écrit directement).

### 4.3 DynamoDB — table `documents`

Identique au schéma de `V2-ADR-003` (conservé en V2 et V3) :

- `PK = tenantId#documentId`, `SK = version` ;
- GSI `by-tenant` : `PK = tenantId` pour lister les documents d'un tenant (défini en `V2-LLD-006`) ;
- attributs : `status`, `chunkCount`, `embeddingModelId`, `embeddingVersion`, `classification`,
  `sourceUri`, `creationOperationId`, `kbIngestionJobId` (nouveau en V2 — id du job KB pour la
  réconciliation), `kbDataSourceId`.

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
| Région | `eu-west-3` | Disponibilité KB+S3V confirmée (précondition `V2-ADR-019` levée) |
| Stratégie de chunking | fixe, taille + recouvrement configurés | reproductibilité ; `chunkerVersion` non géré par KB en V2 (voir limite §5.4) |
| Modèle d'embedding | `embeddingModelId` en paramètre | `V2-ADR-013` ; jamais codé en dur ; tracé dans `documents` |
| Champs de métadonnées | `tenantId`, `documentId`, `version`, `status` | exposés au filtre `Retrieve` (`V2-ADR-006`) |

### 5.3 Injection du `tenantId` dans les métadonnées de chunk

Pour que le filtre `Retrieve` puisse isoler par tenant, le `tenantId` doit être porté par les
métadonnées de chunk. En V2, il est fourni à KB via un **fichier de métadonnées S3 associé à chaque
source** (`<filename>.metadata.json`), généré par FastAPI à l'upload et contenant `tenantId`,
`documentId`, `version`, `status`, `classification`. KB propage ces métadonnées aux chunks indexés.

Ce fichier de métadonnées est le point d'ancrage de l'isolation côté KB. Sa génération est un
contrôle testé (section 16).

### 5.4 Limites assumées de l'ingestion KB en V2

- **`chunkerVersion` non maîtrisé finement** : la stratégie de chunking est celle de KB ; la
  réévaluation ciblée par version de chunker de `V2-ADR-003` n'est pas disponible en V2. Reprise en
  V3.
- **Migration d'embeddings déléguée** : un changement de `embeddingModelId` se fait par
  resynchronisation KB complète, pas par job applicatif incrémental. Tracé dans `documents` pour
  préparer V3.
- **Grain d'état collapsé** : voir §4.3.

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
  1. candidats = adapter.retrieve(question, filter={ tenantId, status: "indexed" }, topK)
        (adapter V2 == KB Retrieve avec filtre métadonnées)
  2. POST-FILTRAGE FastAPI (côté serveur, obligatoire) :
        - rejeter tout candidat dont tenantId != tenant courant   (défense en profondeur)
        - appliquer ACL utilisateur (droits document)
        - appliquer classification (V2-ADR-017)
  3. si aucun candidat après filtrage -> retrievalContext.status = "skipped"
     si KB indisponible                -> retrievalContext.status = "degraded"
     sinon                             -> retrievalContext.status = "ok"
  4. construire retrievalContext borné (topK, longueur max, dedup par documentId)
  5. résoudre citations : pour chaque chunk retenu, lire documents (titre, page, sourceUri)
  6. transmettre retrievalContext à AgentCore Runtime (jamais le texte brut sans pointeur)
```

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
depuis `documents` avant de répondre. Aucune citation n'est construite à partir du seul texte du
modèle (principe `V2-ADR-003` conservé).

## 7. Adapter de magasin vectoriel

### 7.1 Contrat

L'adapter est le **seul point d'échange V2 → V3**. Interface applicative stable :

```text
interface VectorRetrievalPort:
    ingest(documentId, version, sourceUri, metadata) -> IngestionHandle
    get_ingestion_status(handle) -> "ingesting" | "indexed" | "failed"
    retrieve(query, filter, topK) -> list[Candidate]   # Candidate = {chunkRef, score, metadata, text}
    delete(documentId, version) -> DeletionResult
```

| Méthode | Implémentation V2 (KB) | Implémentation V3 (S3 Vectors direct) |
|---|---|---|
| `ingest` | `StartIngestionJob` + fichier métadonnées S3 | enqueue SQS `stage=validate` (`V2-ADR-004`) |
| `get_ingestion_status` | `GetIngestionJob` | lecture `documents.status` |
| `retrieve` | `KB Retrieve` + filtre métadonnées | requête S3 Vectors, filtre `tenantId` pré-construit |
| `delete` | suppression source S3 + resync KB | saga suppression coordonnée (`V2-ADR-003`) |

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
        - suppression de l'objet S3 source (toutes versions) + fichier métadonnées
        - resynchronisation KB de la data source (retire les chunks du document de l'index)
  3. Vérification : aucun chunk résiduel pour documentId (Retrieve filtré doit renvoyer 0)
  4. documents.status = "deleted" (ou entrée purgée selon politique V2-LLD-006)
```

La suppression coordonnée exigée par `V2-ADR-006` est satisfaite en V2 par : suppression S3 +
resync KB + vérification d'absence de résidu. En V3, elle devient la saga applicative de
`V2-ADR-003`. La **preuve d'absence de résidu** est identique dans les deux phases.

### 8.2 Réindexation (V2)

Une réindexation crée une nouvelle `version` (S3 source `v<n+1>`, nouvelle entrée `documents`), la
version précédente passe `superseded`, puis une resync KB indexe la nouvelle version. La bascule
d'affichage vers la nouvelle version se fait après complétion du job (statut `indexed`).

## 9. Isolation multi-tenant

| Ligne de défense | Mécanisme V2 | Testé par |
|---|---|---|
| 1. Métadonnées de chunk | fichier `<filename>.metadata.json` avec `tenantId` généré serveur | test génération métadonnées |
| 2. Filtre `Retrieve` | filtre `tenantId` passé à KB | test filtre KB |
| 3. **Post-filtrage FastAPI** | rejet côté serveur de tout candidat `tenantId != courant` | **test cross-tenant bloquant** |
| 4. Résolution citations | `documents` lu avec `PK = tenantId#documentId` | test citation cross-tenant |

Aucune de ces lignes ne fait confiance au client. La ligne 3 est bloquante : un échec cross-tenant
en test empêche le merge (`V2-ADR-019`, `V2-ADR-006`).

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
`embeddingModelId` — tous dérivés côté serveur.

### 11.2 Schéma de métadonnées de chunk (source de l'isolation)

```json
{
  "tenantId": "<uuid>",
  "documentId": "<uuid>",
  "version": 1,
  "status": "indexed",
  "classification": "internal",
  "sourceUri": "s3://.../sources/<tenantId>/<documentId>/v1/<file>",
  "chunkIndex": 0,
  "createdAt": "2026-01-01T00:00:00Z",
  "embeddingModelId": "<configuré>"
}
```

`tenantId`, `documentId`, `version`, `status` sont **filtrables** (exposés à `Retrieve`) ; les autres
sont retournés mais filtrés côté FastAPI.

## 12. Configuration

| Paramètre | Type | Défaut V2 | Note |
|---|---|---|---|
| `KB_ID` | secret/param | — | id de la Knowledge Base |
| `KB_DATA_SOURCE_ID` | param | — | data source S3V |
| `EMBEDDING_MODEL_ID` | param | configuré | `V2-ADR-013`, jamais codé en dur |
| `RETRIEVE_TOP_K` | param | 8 | candidats demandés à `Retrieve` |
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
- **Rôle d'exécution KB** : lecture S3 source, écriture index S3 Vectors, invocation du modèle
  d'embedding — géré par la configuration de la KB, distinct du rôle FastAPI et du rôle de tâche ECS.

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
| `documents` indisponible | citations non résolvables → réponse sans citations plutôt que citation non vérifiée |

Aucun de ces cas ne renvoie de contenu non filtré ou de citation non vérifiée : la dégradation est
toujours dans le sens de la sûreté.

## 15. Observabilité et coûts

### 15.1 Métriques

- ingestion : nombre de jobs, durée, taux d'échec, latence upload→`indexed` (reflète la latence
  asynchrone assumée) ;
- retrieval : latence `Retrieve`, `topK` effectif, taux de `degraded`/`skipped`, nombre de candidats
  rejetés au post-filtrage (un rejet cross-tenant > 0 est une **alerte de sécurité**) ;
- qualité : recall@k, precision@k, groundedness, couverture des citations, taux de refus (calculées
  hors ligne sur le dataset versionné, `V2-ADR-018`).

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

| Preuve attendue | Type | Bloquant |
|---|---|---|
| Une requête ne retourne jamais de chunk d'un autre tenant | cross-tenant, post-filtrage FastAPI | **Oui** |
| `RetrieveAndGenerate` absent du code et de la politique IAM | statique + IAM | **Oui** |
| Le fichier de métadonnées porte le bon `tenantId` généré serveur | intégration | Oui |
| Une suppression ne laisse aucun résidu (S3 + index KB) | intégration | Oui |
| Un document en `ingesting` n'est jamais cité | intégration | Oui |
| `retrievalContext.status = degraded` quand KB indisponible, sans échec conversation | résilience | Oui |
| Chaque citation est résolvable vers une source réelle et autorisée | intégration | Oui |
| Métriques de qualité calculées sur le dataset versionné | qualité (`V2-ADR-018`) | Gate |

Les preuves sont redacted, versionnées et conservées (`V2-LLD-009`).

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
# 1. Vérifier l'intégrité des objets S3 source
# 2. start-ingestion-job (resynchronisation complète de la data source)
# 3. Recalculer chunkCount et réconcilier documents
```

### 17.3 Diagnostiquer une réponse sans sources

```text
# 1. Vérifier retrievalContext.status dans les traces (degraded ? skipped ?)
# 2. degraded  -> vérifier disponibilité KB / S3 Vectors
#    skipped   -> vérifier post-filtrage (candidats rejetés ? tenant correct ?)
# 3. Vérifier le compteur "candidats rejetés au post-filtrage" (alerte sécurité si cross-tenant)
```

## 18. Trajectoire vers la cible V3

La bascule vers le pipeline applicatif (`V2-ADR-003`/`V2-ADR-004`) se fait par :

1. implémentation V3 de l'adapter (`retrieve` → S3 Vectors direct ; `ingest` → SQS `stage=validate`) ;
2. provisionnement du module ECS `ingestion` + SQS + DLQ (différé en V2) ;
3. réexpansion des états collapsés (`ingesting` → `parsing`/`chunking`/`embedding`/`indexing`) ;
4. reprise applicative de la migration d'embeddings (`V2-ADR-013`) ;
5. bascule du flag `enable_kb_ingestion` → `false`, KB retirée.

FastAPI (post-filtrage, `retrievalContext`, citations), AgentCore Runtime, les agents, les tools
MCP, le HLD et la CAM **ne changent pas**. Les schémas de métadonnées `V2-ADR-006` étant respectés
dès la V2, la migration ne réécrit pas les contrats d'isolation.
