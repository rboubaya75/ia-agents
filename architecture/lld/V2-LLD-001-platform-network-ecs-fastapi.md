# V2-LLD-001 — Plateforme AWS, réseau, ECS et FastAPI

- **Version :** 0.1
- **Statut :** Draft
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G2
- **HLD de référence :** `architecture/hld/HLD-Secure-AgentCore-V2-FR.md` (§8, §12, §14)
- **Dépendances ADR :** V2-ADR-001, V2-ADR-006, V2-ADR-007, V2-ADR-008, V2-ADR-009

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

### 1.2 ADR applicables — décisions retenues

| ADR | Décision applicable à ce LLD |
|---|---|
| V2-ADR-001 | Chemin ingress : API Gateway → VPC Link → ALB interne → FastAPI sur ECS |
| V2-ADR-006 | Task IAM Role fastapi limité à l'invocation Runtime et aux accès applicatifs |
| V2-ADR-007 | ECS Fargate uniquement ; VPC avec subnets publics (NAT) et privés (tâches + ALB) ; VPC endpoints ; flag `enable_ecs_platform` |
| V2-ADR-008 | Sidecar ADOT dans chaque task definition ; export X-Ray + CloudWatch |
| V2-ADR-009 | Déploiement par nouvelle révision de task definition ECS (pas de Helm) |

### 1.3 ADR non applicables

| ADR | Justification |
|---|---|
| V2-ADR-002 | Répartition FastAPI/Runtime : hors périmètre plateforme, couvert par LLD-003 |
| V2-ADR-003 | RAG S3 Vectors : hors périmètre plateforme, couvert par LLD-002 |
| V2-ADR-004 | Pipeline d'ingestion : la plateforme expose le service ECS `ingestion` ; le détail du pipeline est couvert par LLD-002 |
| V2-ADR-005 | Orchestration agents : hors périmètre plateforme |
| V2-ADR-010 | Sauvegarde/restauration : hors périmètre réseau/calcul, couvert par LLD-006 |

### 1.4 Périmètre et exclusions

**Inclus :** VPC, subnets, NAT Gateway, Internet Gateway, VPC endpoints, ECS cluster, task definitions
(`fastapi`, `ingestion`), Task IAM Roles, Security Groups, ALB interne, VPC Link, autoscaling,
déploiements contrôlés, health checks, graceful shutdown, ECR, Secrets Manager (référencement).

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
| Interface | Bedrock Runtime (`bedrock-runtime`) | embeddings (service `ingestion`) et invocation Runtime (service `fastapi`) |
| Interface | CloudWatch Logs (`logs`) | export des logs structurés depuis chaque tâche |
| Interface | CloudWatch Monitoring (`monitoring`) | métriques ECS et custom |
| Interface | STS (`sts`) | assume role pour les Task IAM Roles |
| Interface | SQS (`sqs`) | réception des messages d'ingestion (service `ingestion`) |
| Interface | X-Ray (`xray`) | export traces ADOT → X-Ray |

> **Note :** l'existence d'un endpoint PrivateLink pour l'invocation AgentCore Runtime reste à
> confirmer. À défaut, ce trafic transite par le NAT Gateway — exception documentée, à lever
> prioritairement si un endpoint devient disponible.

Tous les endpoints Interface sont associés aux subnets privés et restreints par un Security Group
dédié (`sg-vpc-endpoints`) n'acceptant que le trafic HTTPS (port 443) depuis les tâches ECS.

---

## 3. ECS Cluster

- **Nom :** `secure-agentcore-v2` (régional, 1 seul cluster)
- **Launch type :** Fargate exclusivement (`V2-ADR-007`)
- **Container Insights :** activé (métriques ECS dans CloudWatch)
- **Services :** `fastapi` et `ingestion`

Le cluster est provisionné uniquement si `enable_ecs_platform = true` dans l'environnement
Terraform cible. La valeur par défaut est `false` — aucun coût réseau/calcul tant que FastAPI
n'est pas prêt à être déployé (`V2-ADR-007`).

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

```python
# FastAPI lifespan : SIGTERM → arrêt des nouvelles requêtes, drain 30 s
import signal, asyncio

async def shutdown_handler():
    server.should_exit = True
    await asyncio.sleep(30)   # drain in-flight requests

signal.signal(signal.SIGTERM, lambda *_: asyncio.create_task(shutdown_handler()))
```

Le délai de déregistrement ALB (`deregistration_delay`) est fixé à 30 s pour laisser le temps
au drain avant que la tâche reçoive SIGTERM.

### 4.2 Service `ingestion`

| Paramètre | Valeur initiale `test` |
|---|---|
| CPU | 1 024 (1 vCPU) |
| Mémoire | 2 048 MB |
| Network mode | `awsvpc` |
| Subnets | `private-a`, `private-b` |
| Task IAM Role | `ecs-task-role-ingestion` (§5.2) |
| Task Execution Role | `ecs-task-execution-role` |

**Conteneurs :** même structure que `fastapi` (conteneur principal + sidecar ADOT).

Logs : log group `/ecs/secure-agentcore-v2/ingestion`, rétention 30 jours.

Le service `ingestion` peut scaler à 0 tâches (pas de trafic HTTP entrant — déclenché par SQS).

---

## 5. Task IAM Roles (least privilege)

### 5.1 `ecs-task-role-fastapi`

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
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                 "dynamodb:Query", "dynamodb:ConditionCheckItem"],
      "Resource": [
        "arn:aws:dynamodb:eu-west-3:<account>:table/v2-conversations",
        "arn:aws:dynamodb:eu-west-3:<account>:table/v2-sessions"
      ]
    },
    {
      "Sid": "S3VectorsRetrieval",
      "Effect": "Allow",
      "Action": ["s3vectors:QueryVectors", "s3vectors:GetVectors"],
      "Resource": "arn:aws:s3vectors:eu-west-3:<account>:bucket/<vectors-bucket>/index/<index-name>"
    },
    {
      "Sid": "S3DocumentRead",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::v2-documents-<account>/*"
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
        "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

### 5.2 `ecs-task-role-ingestion`

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
| Outbound | TCP | 443 | `sg-vpc-endpoints` | appels AWS (Secrets Manager, DynamoDB, S3, Bedrock, X-Ray, logs) |
| Outbound | TCP | 443 | `0.0.0.0/0` via NAT | AgentCore Runtime si pas d'endpoint PrivateLink (exception documentée) |

### 6.3 `sg-ingestion`

| Direction | Protocol | Port | Source/Dest | Justification |
|---|---|---|---|---|
| Inbound | — | — | — | aucune connexion entrante (déclenché par SQS) |
| Outbound | TCP | 443 | `sg-vpc-endpoints` | SQS, S3, DynamoDB, Bedrock, Secrets Manager, X-Ray, logs |

### 6.4 `sg-vpc-endpoints`

| Direction | Protocol | Port | Source/Dest | Justification |
|---|---|---|---|---|
| Inbound | TCP | 443 | `sg-fastapi` | trafic AWS depuis FastAPI |
| Inbound | TCP | 443 | `sg-ingestion` | trafic AWS depuis Ingestion |
| Outbound | — | — | — | implicitement autorisé (endpoints managés AWS) |

---

## 7. Ingress — chemin complet

```text
Browser / React
    │ HTTPS (TLS terminé à CloudFront)
    ▼
CloudFront + WAF
    │ HTTPS (TLS re-terminé à API Gateway)
    ▼
API Gateway HTTP API
    │ JWT Cognito validé, claims extraits
    │ Timeout max : 29 s (contrainte dure, voir §7.2)
    ▼
VPC Link v2
    │ trafic privé dans le VPC
    ▼
ALB interne (`sg-alb-internal`)
    │ Listener HTTPS 443, certificat ACM
    │ Target Group : tâches ECS `fastapi`, port 8000
    │ Deregistration delay : 30 s
    ▼
Tâche ECS `fastapi` (`sg-fastapi`)
    │ port 8000
    ▼
FastAPI (uvicorn)
```

### 7.1 Headers de propagation des claims

API Gateway extrait les claims Cognito et les propage à FastAPI via des en-têtes HTTP dédiés,
jamais dans le corps de la requête, jamais via l'en-tête `Authorization` au-delà de ce point :

| En-tête | Valeur | Source |
|---|---|---|
| `X-Amzn-Oidc-Identity` | `sub` Cognito | API Gateway (natif HTTP API) |
| `X-Amzn-Oidc-Access-Token` | **non transmis** (supprimé par policy) | — |
| `X-Amzn-Oidc-Data` | payload JWT encodé (claims) | API Gateway (natif HTTP API) |

FastAPI valide et extrait les claims depuis `X-Amzn-Oidc-Data` uniquement — jamais depuis le
corps de la requête, conformément à la règle de confiance `V2-ADR-006`. Le `sub` devient `actorId`
après hachage ; `tenantId` est résolu côté serveur.

### 7.2 Stratégie SSE et contrainte timeout 29 s

Le protocole de streaming retenu est SSE (`Content-Type: text/event-stream`), décidé au HLD §6.5.

La contrainte de timeout 29 s d'API Gateway HTTP API est gérée par deux modes :

**Mode direct (réponses ≤ 25 s) :**
```
POST /api/v1/conversations/{id}/messages
→ 200 text/event-stream (streaming SSE direct)
```

**Mode asynchrone (réponses potentiellement > 25 s) :**
```
POST /api/v1/conversations/{id}/messages?async=true
→ 202 application/json  {"operationId": "op-<uuid>", "status": "processing"}

GET /api/v1/operations/{operationId}/stream
→ 200 text/event-stream (SSE du résultat dès disponibilité)
```

Le choix du mode est configurable par feature flag (`STREAMING_MODE=direct|async`).
CloudFront doit désactiver le cache sur les chemins `/api/*` et transmettre l'en-tête
`Cache-Control: no-cache` sans buffering additionnel.

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

### 9.2 Service `ingestion`

| Paramètre | Valeur `test` |
|---|---|
| Minimum de tâches | 0 |
| Maximum de tâches | 5 |
| Politique | Target tracking — `ApproximateNumberOfMessagesVisible` (SQS) |
| Cible | 5 messages par tâche |
| Cooldown scale-out | 60 s |
| Cooldown scale-in | 300 s |

Le service peut scaler à 0 quand la file SQS est vide — coût nul hors traitement. La métrique
CloudWatch `ApproximateNumberOfMessagesVisible` est la seule source de décision ; le détail du
déclenchement est précisé en LLD-002.

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
| Logs CloudWatch | chiffrement côté serveur AWS (SSE-S3 par défaut, KMS CMK optionnel) |
| Trafic réseau interne VPC | HTTPS entre ALB et FastAPI (TLS 1.2 minimum) |
| Images ECR | scan automatique à chaque push, chiffrement at rest |

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

---

## 13. Résilience

| Scénario | Comportement attendu |
|---|---|
| Panne d'une AZ | Les tâches survivantes dans l'autre AZ absorbent le trafic ; ECS replanning automatique ; NAT Gateway unique = risque accepté en `test` |
| Échec de déploiement | Circuit breaker ECS déclenche un rollback automatique vers la révision précédente |
| Tâche FastAPI en erreur | ALB retire la tâche du target group (health check échoué) ; autoscaling lance un remplacement |
| File SQS vide | Service `ingestion` scale à 0 tâche ; pas de consommation de ressources |
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
| ECS Fargate — service `ingestion` (0 tâche au repos) | ~0 USD | scale à 0 |
| ECR stockage | ~1 USD | ~10 GB images |
| **Total minimum (`enable_ecs_platform = true`)** | **~137 USD/mois** | hors trafic |

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
variable "enable_ecs_platform" { type = bool; default = false }
variable "vpc_cidr"            { type = string; default = "10.0.0.0/16" }
variable "availability_zones"  { type = list(string); default = ["eu-west-3a", "eu-west-3b"] }
variable "nat_gateway_count"   { type = number; default = 1 }
variable "fastapi_image_tag"   { type = string }
variable "fastapi_task_definition_revision" { type = number; default = null }
```

`scripts/terraform_plan_guard.py` doit être étendu pour couvrir les nouvelles ressources réseau et
ECS au même titre que DynamoDB et S3 (conformément à la conséquence listée dans `V2-ADR-007`).
