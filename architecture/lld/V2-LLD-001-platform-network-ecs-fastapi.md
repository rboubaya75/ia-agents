# V2-LLD-001 — Plateforme AWS, réseau, ECS et FastAPI

- **Version :** 0.4
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G2
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§5, §6.5, §8, §12, §14)
- **Dépendances ADR :** V2-ADR-001, V2-ADR-006, V2-ADR-007, V2-ADR-008, V2-ADR-009, V2-ADR-011,
  V2-ADR-016, V2-ADR-019, V2-ADR-020

> **Révision v0.2 (revue PR #35) :** alignement sur `V2-ADR-019`. Le service ECS `ingestion` et
> son rôle IAM sont désormais explicitement marqués **cible V3 non provisionnée en V2** (l'ingestion
> V2 est assurée par Bedrock Knowledge Bases, cf. `V2-LLD-002`). Le rôle IAM `fastapi` porte les
> actions KB réellement utilisées en V2 (`Retrieve`, `StartIngestionJob`/`GetIngestionJob`) et non
> l'accès direct S3 Vectors (réservé à V3). Correction du code de graceful shutdown (lifespan),
> du chiffrement des logs (CMK) et de l'exception egress AgentCore Runtime.

> **Révision v0.3 :** alignement sur `V2-ADR-011`, `V2-ADR-016` et `V2-ADR-020`, qui nomment tous
> trois `§7` de ce LLD dans leurs « Écarts à corriger dans le corpus ».
>
> - **Transport du streaming (`V2-ADR-011`).** La route conversationnelle passe d'**API Gateway
>   HTTP API** — qui tamponne systématiquement, de sorte que le « mode direct » de la v0.2 ne
>   diffusait pas — à **REST API Regional en mode `responseTransferMode = STREAM`** ; le plafond de
>   29 s disparaît au profit de 15 min (§7, §7.2). Ajout de l'`idle_timeout` ALB et du keep-alive
>   SSE (§7.3), attendus par `V2-LLD-003 §5.2.2`.
> - **Ancrage de l'identité (`V2-ADR-020`).** §7.1 est **entièrement réécrit**. Les en-têtes
>   `X-Amzn-Oidc-*` qu'il décrivait appartiennent à un ALB en `authenticate-cognito` et ne sont
>   émis par aucun type d'API Gateway ; leur remplacement par un mapping de claims relèverait de
>   l'option A de cet ADR, **rejetée**. FastAPI vérifie désormais elle-même la signature du token
>   contre le JWKS Cognito et **ne lit aucun en-tête d'identité**. La frontière du token devient
>   FastAPI, nommément : `Authorization` est transmis sur le segment passerelle → FastAPI.
> - **WAF et chemin unique (`V2-ADR-016`).** Nouveau §7.4 : exigence de chemin unique et
>   attachement du WAF au type d'API retenu, deux préconditions bloquantes de cet ADR. Le type d'API
>   est **unifié** sur REST API (§7.0) pour un point d'attachement WAF unique — et non, comme une
>   rédaction antérieure le soutenait, pour un mécanisme d'identité unique : `V2-ADR-020` rend
>   l'identité invariante au type d'API et annule ce motif.
> - **Journal d'effacement (`V2-LLD-006 §8.6`).** Ajout de la politique de clé CMK du groupe de
>   journaux `/${env}/erasure-audit` (§12.1.1).

> **Révision v0.4 (écart 3 relevé par `V2-LLD-004 §1.7`) :** la route de confirmation de commande
> (`V2-ADR-014`) et la route d'annulation (`V2-ADR-011`) sont **nommées au tableau des routes**
> de §7.0, en mode `BUFFERED`. `responseTransferMode` étant un réglage par méthode, une route
> couverte par la seule ligne générique « routes documentaires et d'administration » n'avait pas de
> réglage vérifiable au plan — or aucune des deux n'est documentaire.

## 1. Métadonnées

### 1.1 Exigences couvertes

| ID exigence HLD/Charte | Libellé |
|---|---|
| V2-ARCH-005 | Backend FastAPI sur Amazon ECS, launch type Fargate |
| V2-ARCH-009 | Définitions de tâches et services ECS pilotés par Terraform |
| HLD §8 | Multi-AZ, Task IAM Roles, Security Groups awsvpc, autoscaling, déploiements contrôlés |
| HLD §12 | Segmentation réseau, contrôle de l'egress, secrets dans Secrets Manager |
| HLD §14 | Architecture ECS multi-AZ, rollback par nouvelle révision de task definition |
| ADR-001 | API Gateway → VPC Link → ALB interne → FastAPI |
| ADR-007 | VPC dédié, subnets privés/publics, endpoints AWS, Fargate uniquement |
| ADR-008 | Sidecar ADOT dans chaque task definition |
| ADR-011 | Route conversationnelle en REST API `STREAM`, VPC Link V2, keep-alive et idle timeout ALB alignés |
| ADR-016 | Chemin unique CloudFront → API Gateway ; WAF attaché au type d'API retenu |
| ADR-020 | Identité établie par vérification JWKS côté FastAPI ; aucun en-tête d'identité lu |
| HLD §6.5 | Streaming SSE réellement progressif, mode effectif déclaré au client |

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-001 | Chemin ingress : API Gateway → VPC Link → ALB interne → FastAPI sur ECS |
| V2-ADR-006 | Task IAM Role fastapi limité à l'invocation Runtime et aux accès applicatifs |
| V2-ADR-007 | ECS Fargate uniquement ; VPC avec subnets publics (NAT) et privés (tâches + ALB) ; VPC endpoints ; flag `enable_ecs_platform` |
| V2-ADR-008 | Sidecar ADOT dans chaque task definition ; export X-Ray + CloudWatch |
| V2-ADR-009 | Déploiement par nouvelle révision de task definition ECS (pas de Helm) |
| V2-ADR-011 | Transport du streaming : API Gateway **REST API**, endpoint **Regional**, `responseTransferMode = STREAM`, intégration privée `HTTP_PROXY` via **VPC Link V2** vers l'ALB interne. Keep-alive SSE obligatoire, `idle_timeout` ALB aligné dessus (§7.2, §7.3). L'ADR délègue explicitement à ce LLD le choix d'unifier ou non les familles de routes : **unifié sur REST API** (§7.0), pour le motif WAF de `V2-ADR-016` et non pour un motif d'identité |
| V2-ADR-016 | Exigence de **chemin unique** CloudFront → API Gateway, portée ici et outillée au plan (§7.4, §16.6) ; statut de l'**attachement du WAF** au type d'API retenu (§7.4), précondition bloquante vérifiée en §16.5. Le contenu des règles WAF relève de `V2-LLD-005` |
| V2-ADR-020 | Transport et ancrage de l'identité : l'authorizer de la passerelle rejette le non-authentifié, **FastAPI établit l'identité** par vérification de la signature du token contre le **JWKS Cognito** (§7.1). Aucun en-tête d'identité n'est lu — les familles `X-Amzn-Oidc-*` et `X-Claims-*` sont retirées. `Authorization` est transmis sur le seul segment passerelle → FastAPI (§7.1.2) et n'est jamais journalisé. Paramètres de cache, borne de tolérance et fenêtre anti-amplification déclarés en §7.1.4 et §16.4 |
| V2-ADR-019 | En V2, l'ingestion est déléguée à Bedrock Knowledge Bases : le service ECS `ingestion`, son rôle IAM, sa file SQS et son autoscaling **ne sont pas provisionnés en V2** (cible V3). La plateforme provisionne uniquement le service `fastapi` en V2 |

### 1.3 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-002 | Répartition FastAPI/Runtime : hors périmètre plateforme, couvert par LLD-003 |
| V2-ADR-003 | RAG S3 Vectors : hors périmètre plateforme, couvert par LLD-002 |
| V2-ADR-004 | Pipeline d'ingestion applicatif (SQS + worker ECS) : **cible V3**, non provisionné en V2 (`V2-ADR-019`). La plateforme décrit le service `ingestion` comme cible V3 (§4.2) mais ne le déploie pas en V2 ; le détail du pipeline est couvert par LLD-002 |
| V2-ADR-005 | Orchestration agents : hors périmètre plateforme |
| V2-ADR-010 | Sauvegarde/restauration : hors périmètre réseau/calcul, couvert par LLD-006 |

### 1.4 Périmètre et exclusions

**Inclus (provisionné en V2) :** VPC, subnets, NAT Gateway, Internet Gateway, VPC endpoints, ECS
cluster, task definition et service `fastapi`, Task IAM Role `fastapi`, Security Groups, ALB interne,
VPC Link, autoscaling `fastapi`, déploiements contrôlés, health checks, graceful shutdown, ECR,
Secrets Manager (référencement).

**Décrit mais non provisionné en V2 (cible V3, `V2-ADR-019`) :** task definition et service ECS
`ingestion`, Task IAM Role `ingestion`, file SQS, autoscaling `ingestion`, `sg-ingestion`, endpoint
SQS. Ces éléments sont documentés (§4.2, §5.2, §6.3, §9.2) pour préparer la bascule V3, derrière le
flag `enable_ingestion_service = false` (§16.4). Aucun n'est déployé tant que la V2 utilise KB.

**Exclus :** contenu applicatif des conteneurs (couvert par LLD-002 à LLD-004), configuration
détaillée ADOT (LLD-007), schéma DynamoDB (LLD-006), GitLab CI (LLD-008), tests (LLD-009),
frontend (LLD-010).

---

## 2. Topologie VPC

### 2.1 Paramètres de base

| Paramètre | Valeur `test` | Note |
|---|---|---|
| Région | `eu-west-3` (Paris) | cohérent avec les services AgentCore V1 |
| CIDR VPC | `10.0.0.0/16` | 65 534 adresses disponibles |
| Zones de disponibilité | `eu-west-3a`, `eu-west-3b` | minimum 2 AZ (HLD §8) |
| NAT Gateway | 1 (AZ-a uniquement) | compromis coût accepté en `test` ; 1 par AZ recommandé en production |

### 2.2 Subnets

| Nom | AZ | CIDR | Usage |
|---|---|---|---|
| `public-a` | eu-west-3a | `10.0.0.0/24` | NAT Gateway uniquement |
| `public-b` | eu-west-3b | `10.0.1.0/24` | réservé (NAT Gateway production) |
| `private-a` | eu-west-3a | `10.0.10.0/24` | tâches Fargate + ALB interne |
| `private-b` | eu-west-3b | `10.0.11.0/24` | tâches Fargate + ALB interne |

Les subnets publics ne portent ni load balancer internet-facing ni tâche ECS.
Le route par défaut des subnets privés passe par le NAT Gateway de `public-a`.

### 2.3 VPC Endpoints

| Type | Service | Justification |
|---|---|---|
| Gateway | S3 | pull d'objets documents, artefacts d'ingestion — sans passer par NAT |
| Gateway | DynamoDB | accès métadonnées et états — sans passer par NAT |
| Interface | ECR API (`ecr.api`) | authentification pour pull d'image |
| Interface | ECR Docker (`ecr.dkr`) | pull des layers d'image |
| Interface | Secrets Manager (`secretsmanager`) | récupération des secrets au démarrage de tâche |
| Interface | KMS (`kms`) | déchiffrement des secrets et données chiffrées |
| Interface | Bedrock Agent Runtime (`bedrock-agent-runtime`) | **V2** : appel `Retrieve` de Knowledge Bases par `fastapi` |
| Interface | Bedrock Agent (`bedrock-agent`) | **V2** : `StartIngestionJob`/`GetIngestionJob` par `fastapi` |
| Interface | Bedrock Runtime (`bedrock-runtime`) | invocation Runtime (service `fastapi`) ; embeddings applicatifs = **V3** (service `ingestion`) |
| Interface | CloudWatch Logs (`logs`) | export des logs structurés depuis chaque tâche |
| Interface | CloudWatch Monitoring (`monitoring`) | métriques ECS et custom |
| Interface | STS (`sts`) | assume role pour les Task IAM Roles |
| Interface | SQS (`sqs`) | **V3 uniquement** : réception des messages d'ingestion (service `ingestion`) ; non provisionné en V2 |
| Interface | X-Ray (`xray`) | export traces ADOT → X-Ray |

> **Note (exception egress AgentCore Runtime) :** l'existence d'un endpoint PrivateLink pour
> l'invocation AgentCore Runtime reste à confirmer avant implémentation (précondition §16.5). Deux
> cas :
> - **endpoint disponible** → un VPC endpoint interface `bedrock-agentcore` est ajouté et la règle
>   egress `0.0.0.0/0` de `sg-fastapi` (§6.2) est **supprimée** ;
> - **endpoint indisponible** → le trafic transite par le NAT Gateway vers l'API régionale
>   AgentCore. Ce chemin est une **exception de sécurité formellement acceptée en `test`** avec
>   deux contrôles compensatoires obligatoires : (1) **VPC Flow Logs** activés sur `private-a/b`
>   avec alerte sur toute destination hors plages AWS attendues ; (2) egress restreint par
>   destination lorsque techniquement possible (préfixe de service AWS). Le risque résiduel est
>   ré-évalué à chaque release et n'est **pas** transposable en production sans décision explicite.

Tous les endpoints Interface sont associés aux subnets privés et restreints par un Security Group
dédié (`sg-vpc-endpoints`) n'acceptant que le trafic HTTPS (port 443) depuis les tâches ECS.

---

## 3. ECS Cluster

- **Nom :** `secure-agentcore-v2` (régional, 1 seul cluster)
- **Launch type :** Fargate exclusivement (`V2-ADR-007`)
- **Container Insights :** activé (métriques ECS dans CloudWatch)
- **Services V2 :** `fastapi` uniquement
- **Services V3 (non provisionnés en V2) :** `ingestion` (`V2-ADR-019`, flag `enable_ingestion_service`)

Le cluster est provisionné uniquement si `enable_ecs_platform = true` dans l'environnement
Terraform cible. La valeur par défaut est `false` — aucun coût réseau/calcul tant que FastAPI
n'est pas prêt à être déployé (`V2-ADR-007`). En V2, seul le service `fastapi` est déployé :
l'ingestion documentaire est assurée par Bedrock Knowledge Bases (`V2-ADR-019`, `V2-LLD-002`), et
le service `ingestion` reste décrit ci-dessous comme cible V3 derrière le flag
`enable_ingestion_service = false`.

---

## 4. Task Definitions

### 4.1 Service `fastapi`

| Paramètre | Valeur initiale `test` |
|---|---|
| CPU | 512 (0,5 vCPU) |
| Mémoire | 1 024 MB |
| Network mode | `awsvpc` |
| Subnets | `private-a`, `private-b` |
| Task IAM Role | `ecs-task-role-fastapi` (§5.1) |
| Task Execution Role | `ecs-task-execution-role` (pull ECR, push logs) |

**Conteneurs :**

| Nom | Image | Port | Rôle |
|---|---|---|---|
| `fastapi` | ECR `secure-agentcore/fastapi:<digest>` | 8000 (TCP) | service principal |
| `adot-collector` | ECR Public `aws-observability/aws-otel-collector:latest` | 4317, 4318, 2000 | sidecar ADOT (`V2-ADR-008`) |

Secrets injectés via `secrets:` de la task definition (jamais en variable d'environnement en clair) :

```
AGENTCORE_RUNTIME_ARN   → Secrets Manager : /v2/fastapi/runtime-arn
DB_TABLE_PREFIX         → Secrets Manager : /v2/fastapi/db-table-prefix
BEDROCK_MODEL_ID        → Secrets Manager : /v2/fastapi/bedrock-model-id
```

Logs : driver `awslogs`, log group `/ecs/secure-agentcore-v2/fastapi`, rétention 30 jours.

**Graceful shutdown :**

Uvicorn intercepte lui-même `SIGTERM` et déclenche l'arrêt du contexte `lifespan` ; le drain des
requêtes en vol se fait dans la phase de fermeture du `lifespan`, jamais depuis un handler de signal
manuel (un `asyncio.create_task` appelé depuis un handler de signal OS n'est pas garanti de
s'exécuter dans la boucle d'événements uvicorn).

```python
# FastAPI lifespan : le drain se fait à la fermeture, piloté par uvicorn sur SIGTERM
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI

DRAIN_SECONDS = 30

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- démarrage : ouverture des ressources (clients AWS, pools) ---
    yield
    # --- arrêt (déclenché par uvicorn sur SIGTERM) ---
    # laisser les requêtes en vol se terminer avant de fermer les ressources
    await asyncio.sleep(DRAIN_SECONDS)

app = FastAPI(lifespan=lifespan)
```

Uvicorn est lancé avec `--timeout-graceful-shutdown 35` (supérieur au drain) pour ne pas couper le
drain. La séquence ECS/ALB est : l'ALB retire la tâche du target group (fin d'enregistrement,
`deregistration_delay = 30 s`), **puis** ECS envoie `SIGTERM` à la tâche
(`stopTimeout = 40 s`, supérieur au drain) ; les nouvelles requêtes cessent d'arriver avant le début
du drain, et la tâche n'est tuée (`SIGKILL`) qu'après le `stopTimeout`.

### 4.2 Service `ingestion` — cible V3, non provisionné en V2

> **`V2-ADR-019` :** en V2, l'ingestion (parsing, chunking, embeddings, indexation) est assurée par
> Bedrock Knowledge Bases (`V2-LLD-002` §5). Le service ECS ci-dessous **n'est pas déployé en V2**
> (`enable_ingestion_service = false`) ; il est spécifié ici pour que la bascule V3 réutilise la
> même plateforme sans reconception.

| Paramètre | Valeur cible V3 |
|---|---|
| CPU | 1 024 (1 vCPU) |
| Mémoire | 2 048 MB |
| Network mode | `awsvpc` |
| Subnets | `private-a`, `private-b` |
| Task IAM Role | `ecs-task-role-ingestion` (§5.2, **V3**) |
| Task Execution Role | `ecs-task-execution-role` |

**Conteneurs :** même structure que `fastapi` (conteneur principal + sidecar ADOT).

Logs : log group `/ecs/secure-agentcore-v2/ingestion`, rétention 30 jours.

Le service `ingestion` peut scaler à 0 tâches (pas de trafic HTTP entrant — déclenché par SQS en V3).

---

## 5. Task IAM Roles (least privilege)

### 5.1 `ecs-task-role-fastapi` (V2)

En V2, FastAPI est propriétaire du retrieval **via Knowledge Bases** (`V2-ADR-019`) : il appelle
`Retrieve` (jamais `RetrieveAndGenerate`) et déclenche/suit les jobs d'ingestion KB. Il **n'accède
pas directement à S3 Vectors** en V2 — cet accès est réservé à la cible V3 (§5.2). L'absence de
`bedrock:RetrieveAndGenerate` dans la politique est un contrôle de sécurité (interdiction renforcée
côté IAM, `V2-LLD-002` §6.1/§13.1).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreRuntime",
      "Effect": "Allow",
      "Action": ["bedrock-agentcore:InvokeAgent"],
      "Resource": "arn:aws:bedrock-agentcore:eu-west-3:<account>:runtime/<runtime-id>"
    },
    {
      "Sid": "KnowledgeBaseRetrieveV2",
      "Effect": "Allow",
      "Action": ["bedrock-agent-runtime:Retrieve"],
      "Resource": "arn:aws:bedrock:eu-west-3:<account>:knowledge-base/<kb-id>"
    },
    {
      "Sid": "KnowledgeBaseIngestionV2",
      "Effect": "Allow",
      "Action": ["bedrock-agent:StartIngestionJob", "bedrock-agent:GetIngestionJob",
                 "bedrock-agent:ListIngestionJobs"],
      "Resource": "arn:aws:bedrock:eu-west-3:<account>:knowledge-base/<kb-id>/data-source/<ds-id>"
    },
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                 "dynamodb:Query", "dynamodb:ConditionCheckItem"],
      "Resource": [
        "arn:aws:dynamodb:eu-west-3:<account>:table/v2-conversations",
        "arn:aws:dynamodb:eu-west-3:<account>:table/v2-sessions",
        "arn:aws:dynamodb:eu-west-3:<account>:table/<env>-documents",
        "arn:aws:dynamodb:eu-west-3:<account>:table/<env>-documents/index/by-tenant",
        "arn:aws:dynamodb:eu-west-3:<account>:table/<env>-idempotency-ledger"
      ]
    },
    {
      "Sid": "CommandStoreConfirmationOnly",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:UpdateItem"],
      "Resource": [
        "arn:aws:dynamodb:eu-west-3:<account>:table/<env>-commands",
        "arn:aws:dynamodb:eu-west-3:<account>:table/<env>-commands/index/by-operation"
      ]
    },
    {
      "Sid": "S3DocumentSource",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject"],
      "Resource": "arn:aws:s3:::<env>-documents-<account>/*"
    },
    {
      "Sid": "KmsDecryptDocuments",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:eu-west-3:<account>:key/<documents-cmk-id>"
    },
    {
      "Sid": "SecretsManagerRead",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:eu-west-3:<account>:secret:/v2/fastapi/*"
    },
    {
      "Sid": "Observability",
      "Effect": "Allow",
      "Action": [
        "xray:PutTraceSegments", "xray:PutTelemetryRecords",
        "xray:GetSamplingRules", "xray:GetSamplingTargets",
        "logs:CreateLogStream", "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

> **Note ARN KB :** l'ARN de ressource exact pour `bedrock-agent-runtime:Retrieve` et pour les
> actions `bedrock-agent:*IngestionJob` est à confirmer contre la documentation IAM Bedrock à
> l'implémentation (le format `knowledge-base/<id>` et `.../data-source/<id>` est la forme
> attendue). Les noms de tables DynamoDB exacts sont fixés par `V2-LLD-006`.

**Pourquoi le magasin de commandes a son propre bloc, et pourquoi il est plus étroit.** FastAPI
touche `${env}-commands` (`V2-LLD-006 §5.3`) sur deux chemins seulement : la découverte de la
commande à présenter, par requête sur le GSI `by-operation` (`V2-LLD-004 §5.5`), et la transition
`pending` → `confirmed` de l'endpoint de confirmation (`V2-LLD-005 §4.6`). D'où trois actions, et
trois seulement :

| Action accordée | Chemin | Ce que son absence casserait |
|---|---|---|
| `dynamodb:Query` sur le GSI | découverte par `operationId` | le temps 2 de `V2-ADR-014` — FastAPI ne pourrait plus retrouver la commande qu'en la demandant au modèle, ce que l'invariant I9 interdit |
| `dynamodb:GetItem` | rendu du résumé, relecture d'état | la carte de confirmation et la résolution d'issue inconnue |
| `dynamodb:UpdateItem` | transition `pending` → `confirmed` | l'endpoint de confirmation |

**`PutItem` et `DeleteItem` sont délibérément absents.** Créer une commande appartient au tool de
proposition, qui opère depuis un rôle distinct (`V2-LLD-004 §9.1`) : accorder `PutItem` à FastAPI lui
donnerait le moyen de fabriquer une autorisation sans passer par la matérialisation, ce qui
retirerait au mécanisme sa propriété centrale. La suppression, elle, relève du seul TTL
(`V2-LLD-006 §5.3.4`) — un effacement applicatif rouvrirait la fenêtre de rejeu que la rétention de
l'état `executed` ferme.

### 5.2 `ecs-task-role-ingestion` — cible V3, non créé en V2

> **`V2-ADR-019` :** ce rôle accompagne le service ECS `ingestion` du pipeline applicatif V3
> (consommation SQS, embeddings directs, écriture directe S3 Vectors). Il **n'est pas créé en V2** :
> en V2, l'embedding et l'écriture de l'index sont assurés par le rôle d'exécution **de la
> Knowledge Base** (géré par la config KB, distinct des rôles ECS — `V2-LLD-002` §13.1), pas par un
> rôle de tâche ECS. La politique ci-dessous est la spécification cible V3.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SQSConsume",
      "Effect": "Allow",
      "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility",
                 "sqs:GetQueueAttributes"],
      "Resource": "arn:aws:sqs:eu-west-3:<account>:v2-ingestion-queue"
    },
    {
      "Sid": "S3Documents",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject"],
      "Resource": "arn:aws:s3:::v2-documents-<account>/*"
    },
    {
      "Sid": "DynamoDBIngestionState",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                 "dynamodb:Query", "dynamodb:ConditionCheckItem"],
      "Resource": "arn:aws:dynamodb:eu-west-3:<account>:table/v2-ingestion-state"
    },
    {
      "Sid": "BedrockEmbeddings",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:eu-west-3::foundation-model/amazon.titan-embed-text-v2:0"
    },
    {
      "Sid": "S3VectorsWrite",
      "Effect": "Allow",
      "Action": ["s3vectors:UpsertVectors", "s3vectors:DeleteVectors"],
      "Resource": "arn:aws:s3vectors:eu-west-3:<account>:bucket/<vectors-bucket>/index/<index-name>"
    },
    {
      "Sid": "SecretsManagerRead",
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:eu-west-3:<account>:secret:/v2/ingestion/*"
    },
    {
      "Sid": "Observability",
      "Effect": "Allow",
      "Action": [
        "xray:PutTraceSegments", "xray:PutTelemetryRecords",
        "xray:GetSamplingRules", "xray:GetSamplingTargets",
        "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 6. Security Groups

### 6.1 `sg-alb-internal`

| Direction | Protocol | Port | Source/Dest | Justification |
|---|---|---|---|---|
| Inbound | TCP | 443 | `sg-vpc-link` | trafic HTTPS depuis API Gateway via VPC Link |
| Outbound | TCP | 8000 | `sg-fastapi` | forward vers les tâches FastAPI |

### 6.2 `sg-fastapi`

| Direction | Protocol | Port | Source/Dest | Justification |
|---|---|---|---|---|
| Inbound | TCP | 8000 | `sg-alb-internal` | trafic applicatif depuis l'ALB |
| Outbound | TCP | 443 | `sg-vpc-endpoints` | appels AWS (Secrets Manager, DynamoDB, S3, KB `Retrieve`/ingestion, Bedrock Runtime, X-Ray, logs) |
| Outbound | TCP | 443 | `0.0.0.0/0` via NAT | **exception conditionnelle** : AgentCore Runtime si pas d'endpoint PrivateLink — supprimée dès qu'un endpoint existe, sous contrôles compensatoires (§2.3, §16.5) |

### 6.3 `sg-ingestion` — cible V3, non créé en V2

> `V2-ADR-019` : ce Security Group accompagne le service `ingestion` V3 (§4.2). Non créé en V2.

| Direction | Protocol | Port | Source/Dest | Justification |
|---|---|---|---|---|
| Inbound | — | — | — | aucune connexion entrante (déclenché par SQS en V3) |
| Outbound | TCP | 443 | `sg-vpc-endpoints` | SQS, S3, DynamoDB, Bedrock, Secrets Manager, X-Ray, logs |

### 6.4 `sg-vpc-endpoints`

| Direction | Protocol | Port | Source/Dest | Justification |
|---|---|---|---|---|
| Inbound | TCP | 443 | `sg-fastapi` | trafic AWS depuis FastAPI |
| Inbound | TCP | 443 | `sg-ingestion` | **V3 uniquement** : trafic AWS depuis Ingestion (règle ajoutée avec le service V3) |
| Outbound | — | — | — | implicitement autorisé (endpoints managés AWS) |

---

## 7. Ingress — chemin complet

```text
Browser / React (EventSource)
    │ HTTPS (TLS terminé à CloudFront)
    ▼
CloudFront + WAF
    │ cache désactivé sur /api/*, aucun tampon additionnel
    │ seul chemin joignable vers API Gateway (§7.4, V2-ADR-016)
    │ HTTPS (TLS re-terminé à API Gateway)
    ▼
API Gateway REST API — endpoint Regional (V2-ADR-011)
    │ WAF attaché au stage (§7.4)
    │ authorizer Cognito : rejette le non-authentifié (§7.1)
    │ Authorization transmis tel quel à l'intégration (§7.1.2)
    │ responseTransferMode = STREAM  → flux progressif, plafond 15 min
    │ Idle timeout : 5 min (dur)     → keep-alive obligatoire (§7.3)
    ▼
VPC Link V2
    │ trafic privé dans le VPC, cible directe ALB (pas de NLB intermédiaire)
    ▼
ALB interne (`sg-alb-internal`)
    │ Listener HTTPS 443, certificat ACM
    │ Target Group : tâches ECS `fastapi`, port 8000
    │ Idle timeout : 240 s (§7.3)  ·  Deregistration delay : 30 s
    ▼
Tâche ECS `fastapi` (`sg-fastapi`)
    │ port 8000
    ▼
FastAPI (uvicorn, StreamingResponse)
    │ vérification JWKS du token → identité de confiance (§7.1)
    │ le token s'arrête ici (§7.1.2)
```

> **Le contrat d'identité est identique quel que soit le type d'API Gateway** (`V2-ADR-020`).
> Le schéma ci-dessus nomme un REST API parce que `V2-ADR-011` l'impose sur la route
> conversationnelle et que §7.0 unifie ; l'établissement de l'identité en §7.1 ne dépend d'aucune
> propriété de ce type d'API.

### 7.0 Type d'API Gateway — décision et périmètre

`V2-ADR-011` impose le REST API en mode `STREAM` sur la **route conversationnelle** et délègue
explicitement à ce LLD le choix d'unifier ou non les familles de routes. Le HLD §5 le permet dans
les deux sens (« les routes non diffusantes **peuvent** rester sur HTTP API »).

**Décision : un seul API Gateway REST API Regional pour toutes les routes.**

**Le motif n'est pas l'identité.** `V2-ADR-020` rend le contrat d'identité **identique sur les deux
types d'API** : FastAPI vérifie elle-même la signature du token et ne lit aucun en-tête de claims
(§7.1). L'argument « deux types d'API imposeraient deux familles d'en-têtes d'identité » — retenu
dans une rédaction antérieure de cette section — est explicitement annulé par cet ADR, qui note
qu'il « retire un argument de coût à l'unification forcée sur REST API ». Il ne subsiste rien de ce
motif.

**Le motif est l'attachement du WAF et le chemin unique** (`V2-ADR-016`). AWS WAF ne s'attache pas
indifféremment à tous les types d'API Gateway : un web ACL s'associe au **stage d'un REST API**, pas
à un HTTP API. Conserver deux types laisserait les routes documentaires sans WAF au niveau de la
passerelle — couvertes par le seul CloudFront — et **doublerait** le point d'application de
l'exigence de chemin unique (§7.4), qui devrait alors être démontrée deux fois plutôt qu'une. Sur un
contrôle que `V2-ADR-016` classe en précondition bloquante, un point d'application unique n'est pas
un confort d'exploitation.

**La décision est réversible, et doit le rester.** `V2-ADR-020` précondition 1 prévoit que si la
vérification nominative révèle que REST API consomme l'en-tête `Authorization` au lieu de le
transmettre, la route conversationnelle **bascule sur HTTP API sans modifier la décision
d'identité** (§16.5). Cette bascule reste possible précisément parce que l'unification n'est fondée
sur aucun mécanisme d'identité : elle coûte une redéclaration de route et l'attachement d'un second
point WAF, pas une refonte du contrat de confiance.

Le surcoût est réel mais marginal à l'échelle V2 (§14.4) : REST API est facturé plus cher à la
requête qu'HTTP API, sur un volume `test` de l'ordre de quelques dizaines de milliers d'appels par
mois. Ce différentiel est accepté comme prix d'un point d'attachement WAF unique.

| Route | Type | Mode de transfert |
|---|---|---|
| `POST /api/v1/conversations/{id}/messages` | REST API Regional | `STREAM` |
| `GET /api/v1/operations/{operationId}/stream` | REST API Regional | `STREAM` |
| `POST /api/v1/commands/{commandId}/confirm` | REST API Regional | `BUFFERED` |
| `POST /api/v1/operations/{operationId}/cancel` | REST API Regional | `BUFFERED` |
| Routes documentaires et d'administration | REST API Regional | `BUFFERED` (défaut) |

`responseTransferMode` est un réglage **par méthode**, pas par API : les routes non diffusantes
restent en `BUFFERED` sur le même API. L'unification porte sur le type d'API, pas sur le mode.

**Pourquoi ces deux routes courtes sont nommées plutôt que laissées à la ligne générique.** Le mode
étant réglé par méthode, une route couverte par « routes documentaires et d'administration » n'a pas
de réglage vérifiable au plan Terraform. Or ces deux-là ne sont pas documentaires : la confirmation
(`V2-ADR-014`, `V2-LLD-005 §4.6`) est le point d'autorisation de toute action mutante, et
l'annulation (`V2-ADR-011`) doit rester servie même lorsque la route conversationnelle diffuse. Ce
sont des appels courts sans diffusion — `BUFFERED` est correct, et l'écrire le rend opposable.

La confirmation ne transporte que le `commandId` en chemin ; le résumé présenté à l'utilisateur est
rendu par le serveur à partir de la commande stockée, jamais reconstruit depuis la requête
(`V2-LLD-004 §5.5`).

> **Endpoint Regional, jamais edge-optimized.** L'idle timeout d'un endpoint edge-optimized est de
> 30 secondes, ce qui annule l'intérêt du mode `STREAM` (`V2-ADR-011`). La distribution CloudFront
> de `V2-ADR-001` reste en frontal et lui est **distincte** — c'est notre distribution, pas le
> CloudFront managé d'un endpoint edge-optimized.

### 7.1 Transport et ancrage de confiance de l'identité

`V2-ADR-020` tranche la question que `V2-ADR-001` et `V2-ADR-006` avaient laissée ouverte — **depuis
quelle source FastAPI relit les claims** — et nomme `§7.1` de ce LLD dans ses écarts. Cette section
applique sa décision.

> **L'identité n'est pas ce que la couche précédente affirme, c'est ce que FastAPI vérifie.**

**Ce que corrige cette section.** Les versions antérieures décrivaient FastAPI extrayant les claims
d'en-têtes `X-Amzn-Oidc-*` attribués à « API Gateway (natif HTTP API) », puis d'en-têtes `X-Claims-*`
produits par mapping d'intégration. Les premiers appartiennent à un **Application Load Balancer**
configuré en `authenticate-cognito` : aucun type d'API Gateway ne les émet, et l'ALB interne de cette
architecture n'exécute aucune authentification. Les seconds étaient réels mais reposaient sur
l'option A de `V2-ADR-020`, **rejetée** : faire porter l'identité par un en-tête suppose qu'aucun
autre émetteur ne peut le produire, c'est-à-dire l'exigence de chemin unique de `V2-ADR-016` — que
ce même ADR classe en précondition **bloquante non démontrée**. La valeur la plus critique du système
reposerait sur le fait le moins établi.

#### 7.1.1 Deux contrôles, deux finalités

```text
API Gateway   authorizer Cognito     rejette le non-authentifié       protège la disponibilité
FastAPI       vérification JWKS      établit l'identité de confiance  protège l'isolation
```

Ce n'est pas une redondance. L'authorizer de la passerelle empêche le trafic non authentifié
d'atteindre le chemin privé — ce que FastAPI ne peut pas faire pour elle-même, puisqu'elle est
derrière. La vérification FastAPI est le **fondement de l'isolation** `V2-ADR-006` : elle est
conduite sur le token lui-même, pas sur une affirmation transmise.

Deux propriétés en découlent, et ce sont elles qui motivent le choix :

- **le mécanisme est invariant au type d'API.** La vérification de signature est rigoureusement
  identique derrière un HTTP API et derrière un REST API, là où tout mapping impose deux contrats à
  maintenir convergents (§7.0) ;
- **l'ancrage ne dépend d'aucune précondition non démontrée.** Si le chemin unique de `V2-ADR-016`
  venait à faillir, une requête forgée atteignant l'ALB ne produirait **aucune identité** : elle
  serait refusée faute de signature valide. L'échec d'un contrôle réseau reste un problème de
  disponibilité et ne devient pas une usurpation.

**Le type de jeton accepté au bord se déclare, il ne se devine pas.** Un authorizer
`COGNITO_USER_POOLS` de REST API a deux modes, et c'est la présence de `authorizationScopes` sur la
méthode qui les départage : sans scope déclaré, la passerelle traite l'en-tête comme un **jeton
d'identité** et refuse tout jeton d'accès ; avec au moins un scope, elle le traite comme un **jeton
d'accès** et compare les scopes revendiqués à ceux déclarés. Le front présentant un jeton d'accès
(`V2-LLD-010 §4.2`), les méthodes déclarent `aws.cognito.signin.user.admin`.

Ce scope n'est pas un droit métier : il figure sur tout jeton d'accès émis par le pool. Il ne peut
pas en être autrement tant que l'authentification passe par SRP — les scopes d'un *resource server*
ne s'obtiennent que par le flux OAuth2 code d'autorisation. Ce que le contrôle établit reste donc
« jeton d'accès valide de ce pool », ce qui est exactement sa finalité ici : protéger la
disponibilité du chemin privé. L'identité de confiance, elle, est établie par FastAPI (§7.1.3).

Un HTTP API n'a pas ce comportement — son authorizer `JWT` valide nativement un jeton d'accès
Cognito en comparant `client_id` à l'`audience`. C'est la raison pour laquelle le chemin V1
fonctionnait sans rien déclarer, et le piège exact de la migration vers un REST API décidée en §7.0.

#### 7.1.2 Frontière du token

`V2-ADR-006` interdit qu'un token Cognito atteigne Runtime, MCP ou les tools. Il n'a jamais interdit
de le transmettre à FastAPI — c'est ce LLD qui avait ajouté « jamais via `Authorization` au-delà de
ce point », une contrainte qu'aucun ADR n'imposait. `V2-ADR-020` la lève **pour un seul segment** :

| Segment | Token présent | Fondement |
|---|---|---|
| Navigateur → CloudFront → API Gateway | oui | authentification |
| API Gateway → VPC Link → ALB → FastAPI | **oui** | source de vérité de l'identité |
| FastAPI → AgentCore Runtime | non | `trustedIdentity` produite par FastAPI (`V2-ADR-006`) |
| Runtime → MCP, tools | non | `V2-ADR-006`, inchangé |

La frontière du token devient **FastAPI, exactement**. Elle n'est pas plus haute qu'avant — le token
ne va pas plus loin vers Runtime — mais elle est désormais nommée plutôt qu'implicite. L'en-tête
`Authorization` est transmis tel quel par l'intégration, **sans mapping ni réécriture**.

Le segment ajouté est intégralement privé (VPC Link, ALB interne sans DNS public, tâches en subnets
privés) et TLS est terminé à chaque saut. Le token n'y transite donc pas en clair au sens réseau,
mais il devient présent dans un périmètre où il ne l'était pas : `Authorization` est ajouté nommément
aux valeurs **jamais journalisées**, à toutes les couches, journaux d'erreur compris (§12.4,
`V2-ADR-008`).

#### 7.1.3 Contrat de validation

FastAPI vérifie le token à chaque requête, sur les clés publiques du JWKS Cognito mises en cache.

| Contrôle | Règle | Refus si |
|---|---|---|
| Signature | vérifiée contre la clé du JWKS dont le `kid` correspond | signature invalide, `kid` inconnu après actualisation |
| `alg` | liste blanche **`RS256` uniquement** | `none`, `HS256` ou tout algorithme hors liste |
| `iss` | comparé à la valeur de configuration `cognito_issuer` | différent, absent |
| Client applicatif | `aud` si `token_use = id`, `client_id` si `token_use = access` ; comparé à `cognito_app_client_id` | différent, absent |
| `exp` / `nbf` | horodatage courant, tolérance d'horloge 60 s ; `nbf` vérifié s'il est présent, jamais exigé — Cognito n'en émet pas | expiré, pas encore valide |
| `token_use` | doit valoir `access` **ou** `id` | absent ou hors de ces deux valeurs |
| `sub` | présent et non vide | absent, vide |

`iss` et le client applicatif sont **comparés à des valeurs de configuration**, jamais seulement
constatés présents : un token correctement signé par un autre pool ou destiné à un autre client
applicatif est un token valide qui n'est pas le nôtre.

**Pourquoi le claim du client applicatif dépend du type de token.** Cognito ne le nomme pas de la
même façon sur les deux : le token d'identité porte `aud`, le token d'accès porte `client_id`. La
valeur désignée est la même. Le service accepte les deux types et choisit le claim d'après
`token_use` — ce qui laisse au client le choix du token qu'il présente sans jamais relâcher la
comparaison.

La table est **fermée** : un `token_use` absent ou hors des deux valeurs refuse, plutôt que de
laisser passer un token dont aucune audience n'aurait été comparée. C'est la différence entre
« accepter les deux types » et « ne rien vérifier quand le claim manque ».

**Ce que FastAPI ne lit pas.** Le chemin de résolution d'identité **ne lit aucun en-tête d'identité**,
quel que soit son nom — ni `X-Amzn-Oidc-*`, ni `X-Claims-*`, ni aucun équivalent. Il n'y a plus de
règle d'écrasement à énoncer ni d'occurrence multiple à arbitrer : un en-tête forgé n'a pas à être
écarté, il n'est jamais consulté. C'est cette absence de lecture qui est vérifiée en preuve (§15),
et non le bon fonctionnement d'un filtre.

Le `sub` est l'`actorId`, transmis tel quel à `trustedIdentity` — le hachage produit `subjectId`
(`safe_hash(actorId)`), pas `actorId`. Le `tenantId` est **résolu côté serveur** à partir de `sub`
et du registre d'autorisation (`V2-ADR-006`, `V2-LLD-005 §3.4`), sans claim personnalisé. Aucun
claim `custom:tenantId` n'est requis ni lu. Un `tenantId` présent dans le corps de la requête reste
sans effet.

**Bibliothèque.** `PyJWT` avec `cryptography`, via un client JWKS avec cache (§7.1.4). La
configuration est explicite et vérifiée en revue : `algorithms=["RS256"]`, `issuer` et `leeway`
passés à la vérification, `require` portant `exp`, `iat`, `iss`, `sub` et `token_use`.

La comparaison du client applicatif est faite **hors de `PyJWT`**, immédiatement après le décodage.
Le paramètre `audience` de la bibliothèque ne sait lire que `aud` : il refuserait tout token
d'accès. Et le laisser à `None` ne revient pas à « ne rien exiger » — `PyJWT` refuse alors tout
token *portant* un `aud`, donc tous les tokens d'identité. `verify_aud` est donc désactivé et la
comparaison reprise sur le claim que désigne `token_use`, sans qu'aucun chemin ne permette de s'en
dispenser.

`options={"verify_signature": False}` est interdit en toute circonstance, y compris en test — un
test qui a besoin de désactiver la signature teste autre chose que le chemin de production.

**Preuve.** `tests/unit/test_v2_token_validation_contract.py` est la forme exécutable de cette
table : il signe des tokens avec une paire RSA jetable et exerce chaque ligne, en acceptation comme
en refus. Il est lancé par la porte de qualité V2, dont le harnais neutralise `bearer_claims` et ne
traverse donc jamais ce chemin.

#### 7.1.4 Cache JWKS et comportement en panne

Le JWKS est une dépendance externe nouvelle sur le chemin de chaque requête. Elle est mise en cache,
mais elle existe.

**Son indisponibilité refuse.** `V2-ADR-016` a posé une exception au refus par défaut pour le
compteur de quota, en la bornant explicitement à ce compteur ; `V2-ADR-020` confirme qu'elle **ne
s'étend pas au JWKS**. La distinction est la nature du contrôle, pas sa position sur le chemin : un
contrôle d'équité qui échoue dégrade, un contrôle d'autorisation qui échoue refuse.

Le risque de disponibilité se traite par le cache, jamais par l'assouplissement :

| Paramètre | Valeur | Rôle |
|---|---|---|
| `jwks_cache_ttl_seconds` | 3600 (1 h) | TTL nominal des clés en cache |
| `jwks_stale_tolerance_seconds` | 21600 (6 h) | borne de tolérance au-delà du TTL si le JWKS est injoignable — **exprimée en heures, jamais en jours** |
| `jwks_refresh_min_interval_seconds` | 60 | fenêtre anti-amplification : au plus une actualisation par intervalle |

- une clé expirée du cache mais non renouvelable en raison d'une indisponibilité du JWKS reste
  utilisable **jusqu'à la borne de tolérance**, distincte du TTL nominal ;
- au-delà de cette borne, le refus s'applique et l'événement est alerté comme un **incident de
  sécurité**, non comme une perte de contrôle d'équité. Sa série de métrique est distincte du refus
  de quota (`V2-ADR-016`) et du refus d'autorisation : trois causes qui appellent trois réactions
  d'exploitation différentes ;
- un `kid` présent dans le token mais absent du cache déclenche **une seule** actualisation avant
  décision, bornée par `jwks_refresh_min_interval_seconds`. Ce comportement distingue la rotation
  planifiée de Cognito — nouveau `kid` accepté dès la première actualisation réussie — d'une
  tentative d'amplification : un `kid` forgé inconnu ne déclenche qu'une tentative, jamais une
  boucle d'appels au JWKS.

Les trois valeurs sont des **paramètres déclarés** (§16.4), pas les défauts de la bibliothèque
retenue.

### 7.2 Stratégie SSE — streaming progressif et modes

Le protocole retenu est SSE (`Content-Type: text/event-stream`), décidé au HLD §6.5. Le transport
qui le rend réellement progressif est décidé par `V2-ADR-011` et réalisé ici.

**Ce que corrige cette section.** La v0.2 décrivait un « mode direct (réponses ≤ 25 s) → streaming
SSE direct » sur HTTP API. Ce mode **ne diffusait pas** : HTTP API tamponne systématiquement la
réponse et la relaie en un seul bloc à la fin, sans option pour l'en empêcher. Le code était
correct, le protocole était correct, et il n'y avait pas de streaming — une dégradation d'autant
plus dangereuse qu'elle était **silencieuse et non déclarée au frontend**.

**Mode nominal — `native` :**
```
POST /api/v1/conversations/{id}/messages
→ 200 text/event-stream, flux progressif de bout en bout
  premier événement : meta {"streaming": "native", "operationId": "..."}
```

**Mode de reprise — `operationId` :**
```
POST /api/v1/conversations/{id}/messages?async=true
→ 202 application/json  {"operationId": "op-<uuid>", "status": "processing"}

GET /api/v1/operations/{operationId}/stream
→ 200 text/event-stream (rattachement à l'opération en cours ou résultat persisté)
```

Ce second mode **change de raison d'être**. En v0.2 il contournait la limite de 29 secondes ; il
n'existe plus pour cela. Il sert désormais à deux cas que le mode nominal ne couvre pas : les flux
susceptibles de dépasser **15 minutes** (plafond dur de la chaîne) et la **reprise après
déconnexion réseau**. Une reconnexion ne rejoue pas les fragments déjà émis : elle se rattache par
`operationId` et reçoit l'état courant ou le résultat final (`V2-ADR-011`).

**Déclaration du mode effectif.** Le premier événement du flux porte `streaming: native |
emulated`. Le mode `emulated` n'est pas un mode nominal : c'est le repli qui s'applique si la
précondition d'infrastructure de `V2-ADR-011` n'est pas prouvée (§16.5). Il est **déclaré**, jamais
subi — c'est précisément ce que la v0.2 ne faisait pas.

**CloudFront** doit désactiver le cache sur `/api/*` et ne pas ajouter de tampon. La confirmation
que la politique de cache retenue ne tamponne pas le flux est une précondition (§16.5).

### 7.3 Plafonds temporels, idle timeout ALB et keep-alive

Trois plafonds bornent un flux conversationnel. Deux sont durs, un est le nôtre.

| Plafond | Valeur | Nature | Qui le fixe |
|---|---|---|---|
| Durée totale d'un flux | 15 min | dur, non ajustable | API Gateway `STREAM` |
| Idle timeout API Gateway (Regional) | 5 min | dur | API Gateway |
| **Idle timeout ALB** | **240 s** | **configurable — décidé ici** | ce LLD |
| Intervalle de keep-alive SSE | 15 s | configurable | ce LLD, borné par l'idle timeout ALB |

**Pourquoi 240 s et non le défaut de 60 s ni les 300 s d'API Gateway.** La valeur retenue place
délibérément l'ALB comme **la contrainte la plus serrée de la chaîne**, strictement sous les
5 minutes d'API Gateway. Ce choix n'est pas une marge de confort : il détermine **quel composant
coupe le flux**, et donc ce que l'exploitation observe. Si API Gateway coupait le premier, le
symptôme serait une déconnexion côté client sans signal côté serveur — le mode de panne le plus
coûteux à diagnostiquer. En coupant à l'ALB, la rupture apparaît dans les métriques et les logs
d'accès d'un composant que nous possédons et instrumentons (§14.2). Le défaut de 60 s, lui, serait
inutilement serré : il ne protège de rien qu'un keep-alive à 15 s ne couvre déjà.

Cette valeur est celle que `V2-LLD-003 §5.2.2` délègue à ce LLD, et elle en préserve la propriété
structurante : l'idle timeout ALB reste **la contrainte la plus serrée** de la chaîne.

> **Le sens de la dérivation est inversé par rapport à la rédaction initiale de `V2-LLD-003`.**
> Sa table annonçait un idle timeout ALB « défaut 60 s » qui « dimensionne le keep-alive ».
> C'est l'inverse qui s'applique : le keep-alive est fixé à 15 s par `V2-ADR-011`, et l'idle timeout
> en est **dérivé** par l'invariant ci-dessous. `V2-LLD-003 §5.2.2` est aligné en conséquence — sans
> quoi le corpus porterait deux valeurs et deux causalités contradictoires pour le même paramètre.

**Keep-alive obligatoire.** Un tour agentique appelant un tool lent peut rester silencieux plusieurs
dizaines de secondes. FastAPI émet un commentaire SSE (`: ping`) toutes les **15 secondes** — sans
sémantique applicative, ignoré par `EventSource`. Sans lui, un appel de tool de 70 secondes fait
tomber le flux et le symptôme observé est une déconnexion inexpliquée, jamais un dépassement de
budget.

**Invariant vérifié, pas seulement documenté :**

```text
keep_alive_interval × 4  <=  alb_idle_timeout_seconds  <  apigw_idle_timeout (300 s)
       15 s × 4 = 60 s   <=          240 s              <         300 s        ✓
```

Le facteur 4 tolère la perte de trois pings consécutifs avant coupure — un flux ne doit pas tomber
sur un incident réseau transitoire. Cet invariant est contrôlé par `scripts/terraform_plan_guard.py`
en **règle de borne numérique**, selon le mode de contrôle introduit par `V2-LLD-006 §16.2` (§16.6).
Une configuration qui le viole est refusée au plan, pas découverte sur un flux coupé en production.

**Réconciliation avec les budgets agent.** `deadlineEpochMs` de `V2-LLD-003 §5.2.2` (nominal 120 s,
plafond dur 600 s) reste sous les 15 minutes de la chaîne. Un budget supérieur au plafond de la
chaîne n'est pas un budget : il est tué par l'infrastructure avant d'être atteint, et le symptôme
est une déconnexion, pas un `BudgetExceededError`. `V2-LLD-003` refuse ce cas au démarrage.

### 7.4 Chemin unique et attachement du WAF

`V2-ADR-016` nomme deux écarts sur cette section : le chemin nominal décrit ici n'énonçait pas que
les autres sont fermés, et le type d'API retenu n'était pas rapporté à l'attachement du WAF. Les
deux sont des préconditions **bloquantes** de cet ADR.

**Exigence de chemin unique.** Les contrôles portés par CloudFront — WAF, Shield, en-têtes de
sécurité — ne valent que si CloudFront est le **seul** chemin d'accès. Un appel direct au point de
terminaison API Gateway serait un chemin non décrit qui contourne l'intégralité de cette couche, et
rendrait fausse toute preuve qui exercerait ces contrôles par le chemin nominal.

**Règle retenue.** L'API Gateway n'accepte que le trafic provenant de la distribution CloudFront du
système. Le mécanisme précis relève de `V2-LLD-005` ; ce LLD porte l'exigence, sa vérifiabilité au
plan (§16.6, règle 4) et le fait qu'elle s'applique à **un seul** point d'entrée du fait de §7.0.

> **Deux mécanismes candidats sont infirmés — constat d'implémentation.** Une *resource policy* API
> Gateway ne peut porter cette exigence, sous aucune de ses deux formes. Elle ne sait pas lire le
> secret partagé injecté par CloudFront : `aws:RequestHeader` ne figure pas parmi les clés de
> condition globales, et une condition bâtie dessus se fermerait sur l'absence de la clé. Elle ne
> sait pas davantage filtrer sur l'origine du relais : `aws:SourceIp` y est évalué sur l'adresse du
> **client final**, pas sur celle du bord CloudFront — un `Deny` sur la liste de préfixes
> `com.amazonaws.global.cloudfront.origin-facing` refuse donc *tout* le trafic, y compris celui qui
> arrive par la distribution. Constaté au journal d'accès du stage, qui enregistre l'adresse du
> navigateur pour des requêtes relayées par CloudFront.
>
> Il reste le WAF, seul point du chemin capable d'opposer un en-tête arbitraire, et l'origine
> privée. La précondition 9 est donc **subordonnée à la précondition 8** et non indépendante d'elle,
> ce que §16.5 énonçait dans un seul sens. Tant que le WAF n'est pas attaché, la précondition 9 est
> **non tenue** : elle se déclare telle, elle ne se répute pas satisfaite par une politique
> inopérante.

**Attachement du WAF.** Un web ACL AWS WAF s'associe au **stage d'un REST API** ; il ne s'associe
pas à un HTTP API. L'unification de §7.0 fait donc du stage REST API un point d'attachement unique,
en complément de celui de CloudFront. La compatibilité doit être **vérifiée nominativement sur le
service** avant implémentation, pas supposée (§16.5) : si elle est infirmée, le WAF ne subsiste que
sur CloudFront et l'exigence de chemin unique cesse d'être souhaitable pour devenir indispensable.

> **Ce que le chemin unique ne fonde plus.** Avant `V2-ADR-020`, l'identité dépendait de cette
> exigence : des en-têtes de claims ne sont dignes de confiance que si aucun autre émetteur ne peut
> les produire. Ce n'est plus le cas — une requête forgée atteignant directement l'ALB ne produit
> aucune identité (§7.1.1). L'exigence reste **nécessaire et bloquante** pour les contrôles portés
> par CloudFront ; elle n'est simplement plus le fondement de l'isolation.

Le contenu des règles WAF et leur réglage relèvent de `V2-LLD-005` (`V2-ADR-016`).

---

## 8. DNS et certificats

- **Route 53 :** enregistrement A (alias) du domaine API → Custom Domain API Gateway
- **Certificat ACM :** `*.secure-agentcore.example.com`, région `eu-west-3`, validation DNS
- **ALB interne :** pas de DNS public ; accès exclusivement via VPC Link
- **CloudFront :** certificat `us-east-1` (déjà provisionné en V1, réutilisé)

---

## 9. Autoscaling

### 9.1 Service `fastapi`

| Paramètre | Valeur `test` |
|---|---|
| Minimum de tâches | 1 |
| Maximum de tâches | 5 |
| Politique | Target tracking — `ALBRequestCountPerTarget` |
| Cible | 50 requêtes par tâche |
| Cooldown scale-out | 60 s |
| Cooldown scale-in | 300 s |

Une tâche minimum est maintenue en permanence pour garantir la disponibilité sans cold start.

### 9.2 Service `ingestion` — cible V3, non provisionné en V2

> `V2-ADR-019` : cet autoscaling pilote le service `ingestion` V3 sur la profondeur de file SQS.
> Non provisionné en V2 (l'ingestion V2 est asynchrone côté KB, sans tâche ECS à scaler).

| Paramètre | Valeur cible V3 |
|---|---|
| Minimum de tâches | 0 |
| Maximum de tâches | 5 |
| Politique | Target tracking — `ApproximateNumberOfMessagesVisible` (SQS) |
| Cible | 5 messages par tâche |
| Cooldown scale-out | 60 s |
| Cooldown scale-in | 300 s |

En V3, le service scale à 0 quand la file SQS est vide — coût nul hors traitement. La métrique
CloudWatch `ApproximateNumberOfMessagesVisible` est la seule source de décision ; le détail du
déclenchement est précisé en LLD-002 §18 (trajectoire V3).

---

## 10. Déploiements contrôlés

### 10.1 Paramètres de déploiement ECS

| Paramètre | Valeur | Effet |
|---|---|---|
| `minimumHealthyPercent` | 100 | aucune tâche en moins pendant le rollout |
| `maximumPercent` | 200 | jusqu'au double de tâches pendant le remplacement |
| `deploymentCircuitBreaker.enable` | true | arrêt automatique si le déploiement échoue |
| `deploymentCircuitBreaker.rollback` | true | retour automatique à la révision précédente |
| `healthCheckGracePeriod` | 60 s | délai avant que l'ALB commence les health checks |

### 10.2 Stratégie de rollback

Un rollback applicatif s'effectue en pointant le service ECS vers la révision de task definition
précédente (immutable, identifiée par digest ECR) — aucune reconstruction d'image nécessaire.
Ceci est géré par Terraform (`V2-ADR-009`) via mise à jour de la variable `task_definition_revision`.

---

## 11. Health checks

### 11.1 Endpoints FastAPI

| Endpoint | Comportement | Usage |
|---|---|---|
| `GET /health` | 200 si le processus répond | liveness (ALB health check) |
| `GET /ready` | 200 si les dépendances sont accessibles (DynamoDB, Bedrock reachability) | readiness (optionnel, warm-up) |

### 11.2 ALB Target Group

| Paramètre | Valeur |
|---|---|
| Path | `/health` |
| Protocol | HTTP |
| Port | 8000 |
| Interval | 30 s |
| Timeout | 5 s |
| Healthy threshold | 2 checks consécutifs |
| Unhealthy threshold | 3 checks consécutifs |

### 11.3 Container health check (ECS)

```json
{
  "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
  "interval": 30,
  "timeout": 5,
  "retries": 3,
  "startPeriod": 60
}
```

---

## 12. Sécurité

### 12.1 Chiffrement

| Cible | Mécanisme |
|---|---|
| Secrets (variables d'application) | Secrets Manager, chiffré par KMS CMK dédié |
| Logs CloudWatch (`/ecs/secure-agentcore-v2/*`) | **chiffrés par CMK dédiée** (`kms_key_id` sur le log group) — cohérent avec la politique CMK de `V2-LLD-006` §11 ; les logs applicatifs peuvent contenir des identifiants de session/tenant même redacted |
| Journal d'audit d'effacement (`/${env}/erasure-audit`) | **même CMK**, politique de clé étendue explicitement à ce groupe (§12.1.1) — exigé par `V2-LLD-006 §8.6` |
| Trafic réseau interne VPC | HTTPS entre ALB et FastAPI (TLS 1.2 minimum) |
| Images ECR | scan automatique à chaque push, chiffrement at rest |

Le rôle de tâche (§5.1) doit alors inclure `kms:Decrypt`/`kms:GenerateDataKey` sur la CMK des logs
en plus de celle des documents ; le rôle d'exécution ECS (`ecs-task-execution-role`) doit pouvoir
chiffrer via cette CMK pour écrire dans le log group.

#### 12.1.1 Politique de clé du journal d'audit d'effacement

`V2-LLD-006 §8.6` crée un groupe de journaux `/${env}/erasure-audit` chiffré par la CMK des groupes
de journaux et renvoie ici pour la **politique de clé**. Ce LLD la fixe.

Le point d'attention est le préfixe. La politique de clé de CloudWatch Logs restreint l'usage par
`kms:EncryptionContext:aws:logs:arn`, et le journal d'effacement **ne vit pas sous `/ecs/`** : une
condition portant sur `/ecs/secure-agentcore-v2/*` ne le couvre pas. Il doit être listé
explicitement.

```json
{
  "Sid": "AllowCloudWatchLogsEncryption",
  "Effect": "Allow",
  "Principal": { "Service": "logs.eu-west-3.amazonaws.com" },
  "Action": ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*",
             "kms:GenerateDataKey*", "kms:Describe*"],
  "Resource": "*",
  "Condition": {
    "ArnEquals": {
      "kms:EncryptionContext:aws:logs:arn": [
        "arn:aws:logs:eu-west-3:<account>:log-group:/ecs/secure-agentcore-v2/fastapi",
        "arn:aws:logs:eu-west-3:<account>:log-group:/<env>/erasure-audit"
      ]
    }
  }
}
```

**Conséquence d'une omission — elle n'est pas cosmétique.** Sans cette entrée, la création du groupe
`/${env}/erasure-audit` échoue : CloudWatch Logs ne peut pas chiffrer avec une clé dont la politique
ne l'y autorise pas pour ce groupe. Or ce journal est la **source autoritative du rejeu des
effacements** après restauration (`V2-LLD-006 §13.5`), et son absence est exactement la précondition
**P3** de `V2-LLD-006 §1.3` — celle dont `V2-ADR-015` dit qu'elle **n'admet aucun repli** et qui rend
toute restauration PITR interdite plutôt que dégradée. Un oubli de politique de clé au niveau
plateforme a donc une conséquence directe sur un droit des personnes, pas seulement sur
l'exploitation. C'est la raison pour laquelle cette entrée est nommée ici et vérifiée en preuve
(§15).

**Suppression de la clé.** La CMK est partagée entre les journaux applicatifs et le journal
d'effacement. Sa suppression rendrait ce dernier illisible — donc le rejeu impossible, avec le même
effet que P3 non satisfaite. La clé est provisionnée avec une fenêtre d'attente de suppression au
maximum autorisé (30 jours) et `enable_key_rotation = true` ; sa destruction relève d'une décision
explicite, jamais d'un `terraform destroy` d'environnement. `scripts/terraform_plan_guard.py` traite
la suppression ou la désactivation de cette clé au même titre qu'une destruction de table portant
des données (§16.6).

**Nom de la variable.** La CMK est exposée par le module plateforme sous le nom
`logs_kms_key_arn` (§16.4). C'est le nom canonique ; `V2-LLD-006 §8.6` le consomme sous ce nom.

### 12.2 Isolation réseau

- Toutes les tâches ECS dans des subnets privés (pas d'accès direct depuis internet)
- Pas de load balancer internet-facing (ALB interne uniquement)
- Egress vers internet uniquement via NAT Gateway, exception documentée (AgentCore Runtime)
- VPC endpoints pour tout le trafic AWS (aucun passage NAT pour S3, DynamoDB, ECR, etc.)

### 12.3 Principe de moindre privilège IAM

- Chaque service possède son propre Task IAM Role (§5)
- Aucun role avec permissions `iam:*`, `ec2:*` ou `sts:AssumeRole` arbitraire
- Les ARN des ressources sont explicites — pas de `Resource: "*"` sauf pour les APIs de logging/tracing qui l'exigent (CloudWatch Logs, X-Ray)
- Les tables DynamoDB et buckets S3 sont nommés explicitement dans les policies

### 12.4 Valeurs jamais journalisées

`V2-ADR-020` fait entrer le token dans un périmètre où il n'était pas — le segment passerelle →
FastAPI (§7.1.2). Ce qui était implicite devient donc une règle nommée.

| Valeur | Portée de l'interdiction | Fondement |
|---|---|---|
| En-tête `Authorization` et le JWT qu'il porte | **toutes** les couches : journaux d'accès ALB, journaux d'exécution API Gateway, journaux applicatifs FastAPI, traces ADOT | `V2-ADR-020`, `V2-ADR-008` |
| `sub` Cognito brut | idem — haché avant tout usage, y compris en journal | `V2-ADR-006` |
| Clés privées, secrets Secrets Manager | idem | `V2-ADR-008` |

L'interdiction couvre explicitement les **journaux d'erreur et les traces d'exception**, où l'objet
requête est fréquemment sérialisé en entier : c'est le lieu habituel de la fuite, et le seul endroit
où une règle formulée uniquement pour le « chemin nominal » ne s'applique pas. La preuve associée
(§15) échantillonne les journaux d'erreur, pas seulement les journaux nominaux.

Le journal d'exécution d'API Gateway est configuré **sans** journalisation du contenu des requêtes
(`dataTraceEnabled = false`), qui capturerait les en-têtes.

---

## 13. Résilience

| Scénario | Comportement attendu |
|---|---|
| Panne d'une AZ | Les tâches survivantes dans l'autre AZ absorbent le trafic ; ECS replanning automatique ; NAT Gateway unique = risque accepté en `test` |
| Échec de déploiement | Circuit breaker ECS déclenche un rollback automatique vers la révision précédente |
| Tâche FastAPI en erreur | ALB retire la tâche du target group (health check échoué) ; autoscaling lance un remplacement |
| Ingestion KB indisponible (V2) | Le suivi documentaire reflète `failed` ; réessai borné (`V2-LLD-002` §14) ; aucune tâche ECS à superviser |
| File SQS vide (V3) | Service `ingestion` scale à 0 tâche ; pas de consommation de ressources |
| Endpoint AWS indisponible (transitoire) | Retry avec backoff exponentiel et jitter dans le code applicatif ; aucun retry au niveau plateforme |
| Secrets Manager indisponible | La tâche échoue à démarrer (comportement fail-closed) ; aucun secret en clair en fallback |

---

## 14. Observabilité et coûts

### 14.1 Métriques ECS (Container Insights)

- `CPUUtilization`, `MemoryUtilization` par service et par tâche
- `RunningTaskCount`, `PendingTaskCount`
- `DesiredTaskCount` vs `RunningTaskCount` (détection de dérive)

### 14.2 Métriques ALB

- `TargetResponseTime` (latence P50/P95/P99)
- `HTTPCode_Target_5XX_Count`, `HTTPCode_Target_4XX_Count`
- `ActiveConnectionCount`, `RequestCount`

### 14.3 Traces ADOT (via sidecar)

Chaque tâche exporte via ADOT :
- Traces vers AWS X-Ray (W3C traceparent propagé depuis FastAPI)
- Métriques custom vers CloudWatch EMF (Embedded Metric Format)

Voir LLD-007 pour le détail de l'instrumentation OTel et les SLO.

### 14.4 Estimation de coût mensuel (`test`, eu-west-3)

| Composant | Coût estimé/mois | Base |
|---|---|---|
| NAT Gateway | ~32 USD + données | 1 gateway, ~10 GB/mois |
| VPC Interface endpoints | ~7,30 USD × 10 endpoints | ~73 USD |
| ALB interne | ~16 USD + LCU | trafic minimal |
| ECS Fargate — service `fastapi` (1 tâche 0,5 vCPU / 1 GB) | ~15 USD | 730 h/mois |
| ECS Fargate — service `ingestion` | ~0 USD (V2 : non provisionné) | V3 : scale à 0 au repos |
| Bedrock Knowledge Bases (ingestion + `Retrieve`) | à la consommation | **coût RAG V2**, détaillé en `V2-LLD-002` §15.3 |
| ECR stockage | ~1 USD | ~10 GB images |
| API Gateway REST API | à la requête, ~3,50 USD/million | surcoût vs HTTP API (~1,00 USD/million) — voir note |
| **Total minimum (`enable_ecs_platform = true`)** | **~137 USD/mois** | hors trafic, hors coûts KB et hors requêtes API |

> **Surcoût du type REST API (§7.0).** L'unification sur REST API coûte ~2,50 USD par million de
> requêtes de plus qu'HTTP API. À un volume `test` de l'ordre de quelques dizaines de milliers
> d'appels par mois, le différentiel se chiffre en **centimes** et reste sous le seuil de
> significativité du total ci-dessus. Il est accepté comme prix d'un mécanisme de propagation des
> claims unique (§7.1) plutôt que de deux. Ce raisonnement est **à revalider avant production** :
> à volume élevé, le différentiel redevient une décision, et le point de bascule est le moment où
> le coût des requêtes dépasse celui de maintenir deux chemins de confiance — un arbitrage à porter
> en `V2-LLD-007` avec les volumes réels.

> Le coût du RAG en V2 (KB + S3 Vectors + embeddings) est porté par `V2-LLD-002` §15.3, pas par la
> plateforme : la V2 ne provisionne pas de service ECS `ingestion`. L'endpoint interface SQS
> (~7,30 USD/mois) n'est pas non plus provisionné en V2, ce qui abaisse le nombre d'endpoints
> facturés (§2.3).

Différentiel avec l'option EKS écartée (`V2-ADR-007`) : EKS facture un control plane à ~73 USD/mois
indépendamment du trafic, portant le plancher mensuel à ~210 USD pour un profil identique.

---

## 15. Tests et preuves

| Preuve | Méthode | Critère de succès |
|---|---|---|
| `enable_ecs_platform = false` ne provisionne aucune ressource | `terraform plan` + grep | 0 ressource ECS/VPC/ALB dans le plan |
| `terraform plan` ne modifie aucune ressource V1 (DynamoDB, S3 V1, AgentCore) | `terraform plan` + `terraform_plan_guard.py` | 0 destruction, 0 modification V1 |
| Tâche FastAPI ne peut atteindre qu'un domaine explicitement autorisé | Test d'egress curl depuis la tâche vers domaine arbitraire | connexion refusée (Security Group) |
| Invocation AgentCore Runtime depuis FastAPI utilise le Task IAM Role | CloudTrail `AssumeRole` + event source | rôle `ecs-task-role-fastapi`, aucun credential statique |
| Health check `/health` retourne 200 | curl depuis l'ALB | HTTP 200, latence < 100 ms |
| Rollback par révision de task definition antérieure | déploiement d'une mauvaise image → circuit breaker → rollback automatique | service revient à la version précédente en < 5 min |
| Aucune identité brute (JWT, sub) dans les logs | grep sur logs CloudWatch post-requête | 0 occurrence de token JWT ou de sub Cognito en clair |
| **Le flux SSE est réellement progressif** (§7.2) | `curl -N` sur la route conversationnelle, horodatage de réception de chaque événement | premier `delta` reçu **avant** la fin de la génération ; écart > 1 s entre le premier et le dernier événement — un bloc unique en fin de flux est un **échec**, pas une latence |
| Le mode effectif est déclaré au client | lecture du premier événement `meta` | `streaming` présent et conforme au transport réellement servi |
| Keep-alive émis pendant un silence applicatif (§7.3) | flux avec tool lent simulé (> 90 s de silence) | `: ping` observés à ~15 s d'intervalle ; **flux non rompu** |
| L'idle timeout ALB est bien la contrainte la plus serrée | flux sans keep-alive (keep-alive désactivé), mesure du délai de rupture | rupture à ~240 s, **journalisée côté ALB** — pas une déconnexion silencieuse côté client |
| **Aucun en-tête de claims forgé n'a d'effet** (§7.1.3) | requête portant `X-Amzn-Oidc-Data`, `X-Claims-Sub` et `X-Claims-Tenant` forgés, avec un token valide d'un autre tenant | identité résolue = celle du **token vérifié** ; démontré par l'**absence de toute lecture d'en-tête d'identité** dans le chemin de résolution (revue de code + instrumentation), pas par un filtre qui les écarterait |
| **FastAPI valide réellement le token** (§7.1.3) | token de signature valide mais client applicatif incorrect — `aud` sur un token d'identité, `client_id` sur un token d'accès — puis `iss` incorrect, puis expiré — **authorizer de la passerelle désactivé** en environnement de test | les trois refusés par FastAPI. Sans le volet « authorizer désactivé », la preuve n'établit pas que FastAPI valide, seulement que la passerelle valide |
| **L'ancrage ne dépend pas du chemin unique** (§7.1.1, §7.4) | requête forgée injectée **directement sur l'ALB interne**, hors du chemin API Gateway | aucune identité produite, requête refusée — l'échec du chemin unique reste un problème de disponibilité, pas une usurpation |
| Le contrat d'identité est invariant au type d'API (§7.0) | même requête sur une route servie par HTTP API et sur une route servie par REST API | comportement de résolution d'identité identique, mesuré des deux côtés |
| Le JWKS indisponible **au-delà** de la borne de tolérance refuse (§7.1.4) | JWKS rendu injoignable, horloge avancée au-delà de `jwks_stale_tolerance_seconds` | refus, alerté comme **incident de sécurité**, en série de métrique distincte du refus de quota (`V2-ADR-016`) et du refus d'autorisation |
| Le JWKS indisponible **en deçà** de la borne ne refuse pas (§7.1.4) | JWKS rendu injoignable, dans la fenêtre de tolérance | aucun refus, le cache restant sert les vérifications — ce second volet démontre que la borne est **effective et non décorative** |
| Un `kid` inconnu ne déclenche qu'une actualisation (§7.1.4) | rafale de tokens portant des `kid` forgés distincts | au plus une requête JWKS par `jwks_refresh_min_interval_seconds` — pas de boucle d'amplification |
| `Authorization` n'apparaît dans aucun journal (§7.1.2) | grep sur les journaux de **toutes** les couches, échantillon **incluant les journaux d'erreur** | 0 occurrence — les journaux d'erreur sont le lieu habituel de la fuite |
| Le token s'arrête à FastAPI (§7.1.2, `V2-ADR-006`) | inspection des en-têtes reçus côté Runtime sur une requête authentifiée normale | ni `Authorization` ni équivalent ; seule la `trustedIdentity` produite par FastAPI |
| Le WAF est effectivement attaché au type d'API retenu (§7.4) | inspection de l'association web ACL ↔ stage REST API | association présente — si impossible, précondition §16.5 infirmée et chemin unique devenu indispensable |
| API Gateway n'est pas joignable hors CloudFront (§7.4) | appel direct au point de terminaison d'exécution de l'API | refusé — un point joignable directement rend le WAF consultatif |
| La CMK autorise le chiffrement de `/${env}/erasure-audit` (§12.1.1) | `terraform apply` du groupe de journaux, puis `PutLogEvents` de test | groupe créé et événement écrit — un échec ici vaut **P3 non satisfaite** (`V2-LLD-006 §1.3`), donc restauration interdite |
| La politique de clé ne couvre pas par simple préfixe | inspection de la condition `kms:EncryptionContext:aws:logs:arn` | l'ARN `/<env>/erasure-audit` figure **explicitement**, pas via un motif `/ecs/*` |

---

## 16. Exploitation

### 16.1 Déploiement d'une nouvelle version

```bash
# 1. Build et push de la nouvelle image (GitLab CI — V2-LLD-008)
docker build -t <ecr-repo>/fastapi:<git-sha> .
docker push <ecr-repo>/fastapi:<git-sha>

# 2. Mise à jour de la task definition (Terraform)
# infra/environments/test/terraform.tfvars
fastapi_image_tag = "<git-sha>"

# 3. Plan + apply contrôlé
terraform plan -out=plan.bin
python3 scripts/terraform_plan_guard.py record plan.bin
# gate manuelle
python3 scripts/terraform_plan_guard.py verify plan.bin
terraform apply plan.bin
# ECS met à jour le service → déploiement contrôlé automatique
```

### 16.2 Rollback

```bash
# Identifier la révision précédente
aws ecs describe-task-definition --task-definition fastapi --query 'taskDefinition.revision'

# Pointer le service sur la révision précédente
# infra/environments/test/terraform.tfvars
fastapi_task_definition_revision = "<N-1>"
terraform apply
```

### 16.3 Diagnostic

```bash
# Logs en temps réel
aws logs tail /ecs/secure-agentcore-v2/fastapi --follow --format short

# Tâches en cours
aws ecs list-tasks --cluster secure-agentcore-v2 --service-name fastapi

# État du service
aws ecs describe-services --cluster secure-agentcore-v2 --services fastapi \
  --query 'services[0].{running:runningCount,desired:desiredCount,deployments:deployments}'

# Métriques ALB (dernières 5 min)
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=<alb-arn-suffix> \
  --start-time $(date -u -d '5 minutes ago' +%FT%TZ) \
  --end-time $(date -u +%FT%TZ) \
  --period 60 --statistics p95
```

### 16.4 Module Terraform

Le module Terraform dédié suit la convention documentée dans `infra/modules/README.md` :

```
infra/modules/vpc_ecs_platform/
├── versions.tf
├── variables.tf      # enable_ecs_platform, vpc_cidr, azs, nat_gateway_count
├── locals.tf
├── main.tf           # VPC, subnets, NAT GW, IGW, endpoints, ECS cluster, ALB, services
├── outputs.tf        # vpc_id, subnet_ids, cluster_arn, alb_dns_name, sg_ids
└── README.md
```

Nouvelles variables dans `infra/environments/test/variables.tf` :

```hcl
variable "enable_ecs_platform"      { type = bool; default = false }
variable "enable_ingestion_service" { type = bool; default = false }  # V3 (V2-ADR-019) — jamais true en V2
variable "vpc_cidr"                 { type = string; default = "10.0.0.0/16" }
variable "availability_zones"       { type = list(string); default = ["eu-west-3a", "eu-west-3b"] }
variable "nat_gateway_count"        { type = number; default = 1 }
variable "fastapi_image_tag"        { type = string }
variable "fastapi_task_definition_revision" { type = number; default = null }
variable "logs_kms_key_arn"         { type = string }  # CMK des log groups (§12.1, §12.1.1)
variable "alb_idle_timeout_seconds" { type = number; default = 240 }  # §7.3 — < idle API GW (300 s)
variable "sse_keepalive_seconds"    { type = number; default = 15 }   # §7.3 — × 4 <= idle ALB
variable "apigw_response_transfer_mode" { type = string; default = "STREAM" }  # §7.0 (V2-ADR-011)
variable "cognito_issuer"           { type = string }  # §7.1.3 — comparé à iss, jamais déduit
variable "cognito_app_client_id"    { type = string }  # §7.1.3 — comparé à aud/client_id, jamais déduit
variable "jwks_cache_ttl_seconds"        { type = number; default = 3600 }   # §7.1.4
variable "jwks_stale_tolerance_seconds"  { type = number; default = 21600 }  # §7.1.4 — heures, jamais jours
variable "jwks_refresh_min_interval_seconds" { type = number; default = 60 } # §7.1.4 — anti-amplification
```

`cognito_issuer` et `cognito_app_client_id` sont des **paramètres**, pas des valeurs dérivées à
l'exécution du token reçu : c'est ce qui distingue « `iss` et `aud` contrôlés » de « `iss` et `aud`
présents » (§7.1.3). Les trois paramètres JWKS sont consommés par le service FastAPI en variables
d'environnement — ils ne sont jamais laissés aux défauts de la bibliothèque de validation.

`alb_idle_timeout_seconds` et `sse_keepalive_seconds` sont liés par l'invariant de §7.3 : ils ne
sont pas réglables indépendamment. `sse_keepalive_seconds` est également consommé par le service
FastAPI (variable d'environnement) — une seule source de vérité, pas une constante dupliquée dans le
code.

Le flag `enable_ingestion_service` conditionne la création du service ECS `ingestion`, son rôle IAM,
son `sg-ingestion`, son autoscaling SQS et l'endpoint interface SQS (tous §4.2/§5.2/§6.3/§9.2). Il
reste `false` en V2 : aucune de ces ressources n'est provisionnée tant que la V2 utilise KB
(`V2-ADR-019`). `scripts/terraform_plan_guard.py` doit vérifier que `enable_ingestion_service` n'est
pas mis à `true` dans un environnement V2, et couvrir les nouvelles ressources réseau et ECS au même
titre que DynamoDB et S3 (conséquence listée dans `V2-ADR-007`).

### 16.5 Préconditions de vérification avant implémentation

Les points suivants doivent être vérifiés **avant** de provisionner la plateforme, et tracés comme
preuves. Chacun énonce le repli qui s'applique tant que sa preuve n'est pas produite — aucune
précondition ne rouvre une décision, toutes conditionnent une mise en service.

1. **Disponibilité KB + S3 Vectors en `eu-west-3`** (`V2-ADR-019`) : condition d'activation de tout
   le phasage RAG V2. Si non confirmée, l'ingestion V2 bascule sur le pipeline applicatif
   (`enable_ingestion_service = true`) et le rôle §5.2 devient actif — décision explicite, pas
   silencieuse.
2. **Endpoint PrivateLink AgentCore Runtime** (§2.3, §6.2) : si disponible, ajouter l'endpoint et
   supprimer la règle egress `0.0.0.0/0` ; sinon, activer les contrôles compensatoires (VPC Flow
   Logs + alerte) et acter formellement le risque résiduel `test`.
3. **`responseTransferMode = STREAM` disponible sur API Gateway REST en `eu-west-3`**
   (`V2-ADR-011`, §7.0) : condition du streaming progressif. **Repli :** le flux reste servi, mais
   en mode `emulated` déclaré au client dans l'événement `meta` (§7.2) — jamais en silence. Le mode
   `emulated` est alors le mode nominal *de fait*, ce qui doit être acté et non subi.
4. **VPC Link V2 vers ALB disponible en `eu-west-3`** (`V2-ADR-011`, §7) : condition du chemin sans
   saut intermédiaire. **Repli :** VPC Link V1, qui exige un **NLB devant l'ALB** — un composant
   supplémentaire, un saut réseau de plus et un coût que ni `V2-ADR-007` ni les estimations de §14.4
   n'ont provisionnés. Ce repli n'est pas neutre : il modifie la topologie de §7 et le total de
   §14.4, et doit donc être décidé, pas constaté à l'implémentation.
5. **CloudFront ne tamponne pas le flux avec la politique de cache retenue** (§7.2) : à vérifier par
   mesure, pas par lecture de configuration — un tampon en amont produit exactement le symptôme que
   la v0.2 n'avait pas su voir (flux correct en apparence, bloc unique à l'arrivée). La preuve
   « flux réellement progressif » de §15 est la vérification de bout en bout de ce point.
6. **Confirmation nominative des plafonds temporels de §7.3** (15 min, 5 min d'idle API Gateway)
   contre la documentation en vigueur au moment de l'implémentation. Ces valeurs bornent
   `deadlineEpochMs` de `V2-LLD-003 §5.2.2` : une révision à la baisse se propage directement aux
   budgets agent.
7. **Transmission de `Authorization` par API Gateway REST** (`V2-ADR-020`, §7.1.2) : vérifier
   **nominativement** que la passerelle relaie l'en-tête à l'intégration VPC Link **sans le
   consommer**. **Repli :** basculer la route conversationnelle sur HTTP API — le contrat d'identité
   étant invariant au type d'API (§7.1.1), cette bascule ne modifie aucune décision de sécurité et
   `V2-ADR-011` l'autorise. Elle coûte la redéclaration de la route et un second point
   d'attachement WAF (§7.4). **Aucun retour à un mapping d'en-têtes de claims n'est acceptable comme
   alternative** — c'est l'option A rejetée par `V2-ADR-020`.
8. **Attachement du WAF au type d'API retenu** (`V2-ADR-016`, §7.4) — **bloquante**. Vérifier sur le
   service que le web ACL s'associe bien au stage du REST API. **Repli :** si l'association est
   impossible, le WAF ne subsiste que sur CloudFront et la précondition 9 cesse d'être souhaitable
   pour devenir indispensable ; le risque résiduel est acté explicitement, pas constaté.
9. **Mécanisme de chemin unique CloudFront → API Gateway** (`V2-ADR-016`, §7.4) — **bloquante**.
   Existence et vérifiabilité **au plan Terraform** d'un mécanisme rendant CloudFront le seul chemin
   joignable (§16.6, règle 4). Sans lui, tous les contrôles portés par CloudFront sont contournables
   et les preuves qui les exercent par le chemin nominal ne démontrent rien. Le mécanisme précis
   relève de `V2-LLD-005`. **Ce point ne conditionne plus l'identité** (§7.1.1) : son échec est un
   problème de disponibilité, pas une usurpation.
10. **Coût de la validation JWKS mesuré** (`V2-ADR-020`, §7.1.4) : latence de la vérification de
    signature sur clés en cache, mesurée **sur les routes documentaires** — c'est là qu'elle est
    proportionnellement la plus visible, la route conversationnelle l'amortissant sur une invocation
    de plusieurs minutes. Non bloquante ; elle informe le dimensionnement de §3.

### 16.6 Règles de garde `terraform_plan_guard.py`

Ce LLD ajoute cinq règles au garde de plan existant. Trois sont **booléennes** (mode historique) ;
deux sont des **règles de borne numérique**, selon le mode de contrôle introduit par
`V2-LLD-006 §16.2`.

| # | Règle | Mode | Motif |
|---|---|---|---|
| 1 | `enable_ingestion_service` n'est jamais `true` dans un environnement V2 | booléen | `V2-ADR-019` — le pipeline applicatif est V3 (§16.4) |
| 2 | La CMK des groupes de journaux n'est ni supprimée ni désactivée par le plan | booléen | §12.1.1 — sa perte rend le journal d'effacement illisible, donc le rejeu impossible (effet P3) |
| 3 | `sse_keepalive_seconds × 4 <= alb_idle_timeout_seconds < 300` | **borne numérique** | §7.3 — un keep-alive trop espacé fait tomber le flux ; un idle ALB ≥ 300 s déplace la coupure sur API Gateway, hors de notre observabilité |
| 4 | Le mécanisme de chemin unique CloudFront → API Gateway est présent dans le plan | booléen | §7.4 — `V2-ADR-016` précondition bloquante : un point de terminaison joignable directement rend le WAF consultatif |
| 5 | `jwks_stale_tolerance_seconds <= 86400` | **borne numérique** | §7.1.4 — `V2-ADR-020` borne la tolérance « en heures, non en jours » ; au-delà, un JWKS durablement injoignable ferait accepter des tokens sur des clés non révocables |

Les règles 3 et 5 sont vérifiées **sur le plan**, donc sur les valeurs réellement appliquées — pas
sur les valeurs par défaut des variables. C'est ce qui les distingue d'une simple `validation` de
variable Terraform : un `terraform.tfvars` d'environnement qui surcharge l'une des deux valeurs de
la règle 3 sans l'autre est précisément le cas qu'elle attrape.

La règle 4 ne vérifie que la **présence** du mécanisme, pas sa correction : le plan Terraform peut
établir qu'une resource policy ou une origine privée existe, il ne peut pas établir qu'elle est
efficace. Sa correction est démontrée par la preuve d'appel direct de §15, et son contenu relève de
`V2-LLD-005`.
