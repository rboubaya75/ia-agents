# V2-ADR-004 — Pipeline d'ingestion documentaire

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-002, V2-ADR-003, V2-ADR-006, V2-ADR-007

## Contexte

Le HLD (section 6.2) décrit déjà le flux cible : upload → S3 source privé → événement d'ingestion
→ worker → validation → parsing → chunking → embeddings → écriture S3 Vectors → écriture
métadonnées DynamoDB → publication du statut. L'exigence est explicite : « idempotente, reprenable
et capable de supprimer ou réindexer un document sans laisser d'éléments orphelins. » La CAM
(Domaine 4) interdit formellement l'ingestion dans AgentCore Runtime. La V1 a déjà validé, pour les
mutations Trips, un mécanisme d'idempotence robuste (`docs/adr/ADR-0006`,
`docs/adr/ADR-0007` : ledger durable dans la table métier, hash canonique du payload, TTL,
`mutation_started` bloquant tout replay après effet de bord) — ce pattern est repris ici plutôt
que réinventé.

## Options

### Option A — Traitement synchrone dans la requête HTTP

Upload, parsing, chunking, embedding et indexation exécutés dans le même appel API.

**Rejet proposé :** incompatible avec la limite de 29 secondes d'API Gateway et avec des documents
volumineux ; aucune reprise possible en cas d'échec partiel.

### Option B — Orchestration Step Functions

Une state machine Step Functions pilote des tâches Lambda/Fargate par étape.

**Rejet proposé :** ajoute un nouveau paradigme d'orchestration distinct du pattern d'idempotence
DynamoDB déjà éprouvé en V1, pour un bénéfice non démontré à l'échelle visée par ce projet ; coût
et complexité supplémentaires non justifiés tant qu'EKS (`V2-ADR-007`) porte déjà le calcul
applicatif.

### Option C — File d'événements SQS + worker EKS

Une file SQS déclenche des workers EKS (namespace `ingestion`, `V2-ADR-007`) qui font progresser
l'état du document dans la table `documents` (`V2-ADR-003`) via des écritures conditionnelles.

## Décision proposée

Retenir **l'option C**.

```text
Upload (FastAPI)
  -> S3 (préfixe quarantaine)
  -> message SQS { documentId, version, stage: "validate" }
  -> worker EKS (namespace ingestion)
       -> validation (type, taille, antivirus) -> promotion S3 (préfixe définitif) | rejet
       -> parsing -> chunking versionné -> embeddings Bedrock -> écriture S3 Vectors
       -> écriture métadonnées DynamoDB (table documents, V2-ADR-003)
       -> publication statut + métriques
```

## Machine à états et idempotence

État porté exclusivement par la table `documents` (`V2-ADR-003`) :

```text
uploaded -> quarantine_scan -> validated | rejected
validated -> parsing -> chunking -> embedding -> indexing -> indexed | failed
```

Chaque transition est une écriture DynamoDB conditionnelle (l'état précédent attendu doit
correspondre, sinon l'opération est un no-op silencieux plutôt qu'une erreur). L'identifiant
d'idempotence par étape est dérivé de manière déterministe (`hash(tenantId + documentId + version
+ stage)`), reprenant directement le pattern « hash canonique + rang d'occurrence » de
`docs/adr/ADR-0007` : un message SQS redélivré ne retraite jamais une étape déjà terminée.

## Quarantaine

Les uploads atterrissent d'abord dans un préfixe S3 de quarantaine. Un worker de validation
(type, taille, antivirus) promeut le document vers le préfixe définitif uniquement après succès ;
un document rejeté reste en quarantaine avec purge automatique par politique de cycle de vie S3
(TTL).

## Reprise et limites de retry

File SQS standard avec délai de visibilité calibré sur la durée maximale de l'étape la plus longue
(embedding) ; DLQ après un nombre borné de tentatives (3, cohérent avec l'absence de retry infini
déjà actée en V1 — `V1-RES-002`/`V1-RES-003`) ; alerte CloudWatch sur profondeur de DLQ. Aucune
étape n'est rejouée après confirmation d'un effet de bord terminal (indexation réussie).

## Conséquences

- une file SQS et une DLQ sont nécessaires (impact Terraform) ;
- un namespace EKS dédié `ingestion` avec autoscaling piloté par la profondeur de file (mécanisme
  précis différé au LLD-001/LLD-002) ;
- l'ingestion reste strictement hors d'AgentCore Runtime (CAM Domaine 4, violation bloquante en
  revue de code sinon) ;
- la suppression et la réindexation documentées par `V2-ADR-003` empruntent ce même pipeline, pas
  un mécanisme distinct.

## Preuves attendues

- un message SQS redélivré ne produit ni doublon d'index ni double écriture de métadonnées
  (test d'idempotence par étape) ;
- un fichier de type ou taille non autorisé est rejeté en quarantaine, jamais indexé ;
- un échec à une étape n'indexe pas de vecteur sans état DynamoDB cohérent (pas d'orphelin S3
  Vectors) ;
- la DLQ capture les messages après le nombre de tentatives borné configuré ;
- suppression et réindexation déclenchées via ce pipeline ne laissent aucun résidu (preuve
  partagée avec `V2-ADR-003`).

## Références AWS

- Amazon SQS (file standard + DLQ) ;
- Amazon EKS Fargate (workers d'ingestion, `V2-ADR-007`) ;
- Amazon S3 (quarantaine et cycle de vie) ;
- Amazon Bedrock (embeddings) ;
- Amazon DynamoDB (état du pipeline, écritures conditionnelles).
