# Module `vpc_ecs_platform`

Socle plateforme V2 : VPC, subnets, NAT/IGW, VPC endpoints, cluster ECS Fargate, ALB interne,
service `fastapi`, rôles IAM de tâche, Security Groups et groupes de journaux chiffrés.

Réalise `V2-LLD-001` — Plateforme, réseau, ECS et FastAPI. Chaque ressource porte en commentaire la
section du LLD qui la fixe.

## Activation

Le module ne s'auto-active pas. Il est appelé avec `count` depuis l'environnement, piloté par
`enable_ecs_platform`, dont la valeur par défaut est `false` (`V2-LLD-001 §3`) : aucun coût réseau ni
calcul tant que l'image FastAPI n'existe pas.

## Ce que le module ne crée pas

| Élément | Raison |
|---|---|
| Service ECS `ingestion`, `ecs-task-role-ingestion`, `sg-ingestion` | cible V3 (`V2-ADR-019`, `V2-LLD-001` §4.2, §5.2, §6.3). Seul l'endpoint SQS est câblé, derrière `enable_ingestion_service` |
| VPC Link, API Gateway, CloudFront, WAF | la précondition 4 de `§16.5` (VPC Link V2 vers ALB en `eu-west-3`) n'est pas vérifiée, et son repli change la topologie de `§7`. Le module crée le `sg-vpc-link` que le VPC Link consommera |
| Certificat ACM, Route 53 | `§8` — fournis par l'environnement via `alb_certificate_arn` |
| Tables DynamoDB, bucket documents, Knowledge Base | `V2-LLD-006` et `V2-LLD-002`. Le module ne fait que référencer leurs ARN pour la politique de rôle |

## Écarts assumés à `V2-LLD-001` (périmètre MVP)

L'observabilité relève de `V2-LLD-007`, reporté hors MVP. Quatre écarts en découlent. Tous sont
réversibles par une variable ou une valeur — aucun n'est structurel.

| Écart | Section | Retour arrière |
|---|---|---|
| Container Insights désactivé | §3 | `containerInsights = "enabled"` dans `ecs.tf` |
| Sidecar `adot-collector` absent de la task definition | §4.1 | ajout du second conteneur |
| VPC endpoint `xray` non provisionné | §2.3 | ajout à `local.interface_endpoint_services` |
| Actions X-Ray absentes du rôle de tâche | §5.1 | ajout au `statement` `WriteOwnLogs` |

Un cinquième écart n'est pas un choix de périmètre mais une précondition non levée : l'endpoint
`bedrock-agentcore` n'est pas provisionné et `sg-fastapi` conserve donc son egress `0.0.0.0/0`
conditionnel (`§2.3`, `§6.2`, précondition 2 de `§16.5`). Passer `enable_agentcore_privatelink` à
`true` ajoute l'endpoint et supprime la règle dans le même plan.

## Invariants portés par le module

- `alb_idle_timeout_seconds < 300` et `jwks_stale_tolerance_seconds <= 86400` sont vérifiés par des
  blocs `validation` de variable. Ils sont **aussi** vérifiés sur le plan par
  `scripts/terraform_plan_guard.py` (§16.6, règles 3 et 5) : un `tfvars` qui surcharge
  `sse_keepalive_seconds` sans toucher `alb_idle_timeout_seconds` est exactement le cas qu'une
  validation par variable ne peut pas attraper.
- `sse_keepalive_seconds` est passé au conteneur en variable d'environnement. C'est la source unique
  (`§16.4`) : le code applicatif ne redéclare pas cette constante.
- `cognito_issuer` et `cognito_app_client_id` sont des **paramètres**, jamais dérivés du token reçu
  (`§7.1.3`).

## Politique du rôle de tâche

Les statements dont la cible n'est pas encore connue (Knowledge Base, Runtime AgentCore, bucket
documents) sont **retirés** de la politique plutôt que pointés sur un ARN gabarit. Un rôle qui
n'accorde rien est auditable ; un rôle qui accorde quelque chose sur un ARN malformé ne l'est pas.

Deux absences sont des contrôles de sécurité, pas des oublis :

- `bedrock:RetrieveAndGenerate` est absent (`V2-LLD-002 §6.1`) ;
- sur le magasin de commandes, `PutItem` et `DeleteItem` sont absents (`§5.1`). Créer une commande
  appartient au tool de proposition, qui opère depuis un rôle distinct ; un effacement applicatif
  rouvrirait la fenêtre de rejeu que la rétention de l'état `executed` ferme.

## Variables principales

| Variable | Défaut | Rôle |
|---|---|---|
| `name_prefix` | — | préfixe de nommage, requis |
| `vpc_cidr` | `10.0.0.0/16` | §2.1 |
| `availability_zones` | `["eu-west-3a", "eu-west-3b"]` | exactement deux (§2.1) |
| `nat_gateway_count` | `1` | compromis coût accepté en `test` (§2.1) |
| `fastapi_image` | `""` | image pinnée par digest (§4.1) |
| `fastapi_secrets` | `{}` | nom de variable → ARN Secrets Manager (§4.1) |
| `alb_idle_timeout_seconds` | `240` | §7.3 |
| `sse_keepalive_seconds` | `15` | §7.3, §16.4 |
| `alb_certificate_arn` | `""` | sans certificat, pas de listener HTTPS |
| `logs_kms_key_arn` | `""` | vide ⇒ le module crée sa propre CMK (§12.1) |
| `enable_agentcore_privatelink` | `false` | précondition 2 de §16.5 |
| `enable_ingestion_service` | `false` | V3, jamais `true` en V2 (§16.4) |

Les autres variables sont documentées dans `variables.tf`.

## Sorties

`vpc_id`, `vpc_cidr`, `public_subnet_ids`, `private_subnet_ids`, `cluster_arn`, `cluster_name`,
`service_name`, `task_definition_arn`, `alb_arn`, `alb_dns_name`, `target_group_arn`,
`security_group_ids` (map par rôle), `task_role_arn`, `execution_role_arn`, `logs_kms_key_arn`,
`fastapi_log_group_name`.
