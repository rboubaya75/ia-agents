# V2-ADR-003 — RAG applicatif avec S3 Vectors

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-002, V2-ADR-006

## Contexte

La V1 diffère explicitement le RAG (`docs/adr/ADR-004-rag-future-capability.md`) : `enable_rag =
false`, capacité future sans remplacer Memory, les tools ou DynamoDB. `V2-ADR-002` a déjà attribué
l'ensemble du pipeline RAG à FastAPI dans la Capability Allocation Matrix (Domaine 4 — Retrieval) :
AgentCore Runtime ne réalise ni retrieval ni indexation, il reçoit un `retrievalContext` borné et
préassemblé (`architecture/hld/runtime-contract.md`). `V2-ADR-006` a déjà fixé les métadonnées de
filtrage obligatoires (`tenantId`, `documentId`, `version`, `status`). Cet ADR lève le report V1 et
détaille le schéma, le pipeline et les garanties de qualité du RAG applicatif.

## Options

### Option A — Bedrock Knowledge Bases

Service managé AWS pour le RAG, avec OpenSearch Serverless comme moteur vectoriel.

**Rejet proposé :** exclu explicitement par la charte V2 (Bedrock Knowledge Bases et OpenSearch
Serverless sont hors périmètre). Duplique en outre la capacité de retrieval déjà attribuée à
FastAPI par la CAM (violation P-02).

### Option B — Moteur vectoriel auto-hébergé

pgvector sur RDS, OpenSearch auto-géré, ou service SaaS tiers (Pinecone, Weaviate...).

**Rejet proposé :** ajoute un magasin de données hors de l'empreinte AWS-native déjà retenue
(S3/DynamoDB/S3 Vectors), charge opérationnelle et coût supplémentaires sans bénéfice démontré ;
contredit l'attribution déjà actée du Domaine 8 de la CAM (Vector Storage → S3 Vectors).

### Option C — S3 Vectors applicatif

Pipeline RAG entièrement applicatif : S3 pour les documents sources, S3 Vectors pour les
embeddings, DynamoDB pour les métadonnées, orchestré par FastAPI.

## Décision proposée

Retenir **l'option C**, conformément au choix technique déjà fixé par la charte V2 et à
l'attribution CAM Domaine 8.

## Schéma et pipeline

### Stockage

- **S3 source :** document original, version, hash, statut de conservation (déjà défini par le
  HLD section 9) ;
- **S3 Vectors :** un index partagé (pas d'index par tenant — l'isolation repose sur le filtre
  `tenantId` obligatoire déjà décidé par `V2-ADR-006`, plus simple à opérer ; un index par tenant
  reste une option différée si le volume de tenants le justifie) ;
- **DynamoDB — nouvelle table `documents`** (la table `Trips` existante n'est pas conçue pour
  porter des métadonnées documentaires) : `PK = tenantId#documentId`, `SK = version`. La clé de
  partition composite évite de concentrer tout le catalogue d'un tenant dans une seule partition
  (anti-pattern de partition chaude limitant à 3000 RCU / 1000 WCU) ; le listing des documents
  d'un tenant passe par un GSI `PK = tenantId` défini en LLD-006. `documentId` est un UUID
  globalement unique. Attributs : `status` (`uploaded | validating | parsing | chunking |
  embedding | indexing | indexed | failed | quarantined | deleted`), `chunkCount`,
  `embeddingModelId`, `embeddingVersion`, `chunkerVersion`, `classification`, `sourceUri`,
  `creationOperationId` (même pattern d'idempotence que `docs/adr/ADR-0006` et `docs/adr/ADR-0007`
  en V1).

### Métadonnées de chunk (S3 Vectors)

Champs filtrables obligatoires : `tenantId`, `documentId`, `version`, `status` (imposés par
`V2-ADR-006`). Champs non filtrables : `chunkIndex`, `sourceUri`, `createdAt`, `embeddingModelId`,
`embeddingVersion`, `chunkerVersion`, extrait de texte.

### Chunking et embeddings

- chunking versionné (taille et recouvrement fixés en LLD, identifiant `chunkerVersion` stocké
  avec chaque chunk pour permettre une réévaluation ciblée) ;
- identifiant de chunk déterministe : `hash(documentId + version + chunkIndex + chunkerVersion)`,
  garantissant l'idempotence d'une réindexation ; `documentId` étant un UUID globalement unique,
  aucun risque de collision inter-tenant même sans `tenantId` dans la dérivation ;
- embeddings Bedrock configurables (`embeddingModelId` en paramètre, jamais codé en dur), version
  du modèle tracée pour permettre une migration de modèle sans réécriture silencieuse de l'index.

### Citations

Le retrieval retourne des références de chunk (`documentId`, `version`, `chunkIndex`,
`sourceUri`), jamais du contenu sans pointeur vérifiable. FastAPI résout les métadonnées
d'affichage (titre, page) depuis DynamoDB avant de répondre — aucune citation n'est construite à
partir du seul texte du modèle.

### Suppression et réindexation

Déclenchées par le même mécanisme de traitement que l'ingestion (`V2-ADR-004`) : une suppression
retire l'objet S3, les vecteurs associés et l'entrée DynamoDB dans une même opération coordonnée
(cohérent avec l'exigence de suppression coordonnée déjà fixée par `V2-ADR-006`). Une
réindexation crée une nouvelle version ; les chunks/vecteurs de l'ancienne version sont marqués
`superseded` puis purgés après une période de grâce définie en LLD.

### Qualité

Dataset d'évaluation versionné (paires question/source attendue), métriques calculées hors ligne :
recall@k, precision@k, groundedness, couverture des citations, taux de refus lorsque les sources
sont insuffisantes. Ces métriques alimentent la gate de `V2-LLD-009` et sont reprises par
`V2-ADR-018` (stratégie de tests RAG).

## Conséquences

- une nouvelle table DynamoDB `documents` est nécessaire (impact Terraform) ;
- le contenu documentaire reste traité comme donnée non fiable à tous les niveaux (principe déjà
  acté par `V2-ADR-002`) ;
- `retrievalContext.status` (`ok | degraded | skipped`, déjà défini dans
  `architecture/hld/runtime-contract.md`) doit refléter l'état réel de ce pipeline, notamment en
  cas d'indisponibilité S3 Vectors (dégradation déjà documentée dans
  `architecture/hld/capability-allocation-matrix.md`) ;
- `V2-ADR-013` (versionnement des embeddings) et `V2-ADR-017` (classification documentaire)
  précisent ultérieurement des aspects volontairement laissés ouverts ici.

## Preuves attendues

- une requête ne retourne jamais de vecteur d'un autre tenant (test cross-tenant, prolonge les
  preuves déjà exigées par `V2-ADR-006`) ;
- une réindexation ne duplique ni ne laisse orphelin aucun chunk ;
- une suppression ne laisse aucun résidu S3, S3 Vectors ou DynamoDB ;
- chaque citation renvoyée est résolvable vers une source réelle et autorisée ;
- `retrievalContext.status = degraded` renvoyé lorsque S3 Vectors est indisponible, sans échec de
  la conversation ;
- métriques de qualité calculées et publiées sur le dataset d'évaluation versionné.

## Références AWS

- Amazon S3 Vectors (stockage et filtrage de métadonnées) ;
- Amazon Bedrock (modèles d'embedding configurables) ;
- Amazon DynamoDB (métadonnées documentaires) ;
- Amazon S3 (documents sources, versioning).
