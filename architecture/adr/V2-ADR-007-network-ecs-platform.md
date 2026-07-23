# V2-ADR-007 — Architecture réseau et calcul ECS

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-001, V2-ADR-006

## Contexte

La V1 est entièrement serverless (API Gateway, Lambda, DynamoDB, Cognito, AgentCore natif) : aucun
VPC, subnet ou plateforme de calcul conteneurisé n'existe dans l'infrastructure actuelle.
`V2-ADR-001` fixe déjà le chemin réseau cible pour l'ingress (`API Gateway → intégration privée
VPC Link → load balancer interne → FastAPI sur conteneurs → AgentCore Runtime IAM-only`) mais ne
tranche ni la plateforme de calcul conteneurisé, ni le dimensionnement du VPC, des subnets et des
endpoints qu'elle présuppose. Cet ADR comble ce vide, en deux temps : d'abord le choix de la
plateforme elle-même, puis son dimensionnement.

## Exigences

- multi-AZ (HLD section 8) ;
- Runtime jamais exposé directement à internet ;
- workloads FastAPI et workers d'ingestion identifiés par une identité IAM dédiée par
  service/tâche ;
- egress par défaut refusé, ouvert explicitement par cas d'usage ;
- coût contrôlable pour un environnement `test` jetable (cohérent avec le pattern
  `force_destroy = true` déjà utilisé pour le frontend) ;
- support du streaming HTTP à terme (exigence déjà posée par `V2-ADR-001`) ;
- aucune ressource de calcul ne doit être provisionnée avant que FastAPI soit prêt à être déployé.

## Choix de la plateforme de calcul conteneurisé

Avant de dimensionner quoi que ce soit, la question préalable est : quelle plateforme porte
FastAPI et les workers d'ingestion ? Trois options réelles existent sur AWS pour ce profil de
charge (un service HTTP stateless + des workers déclenchés par SQS, sans multi-tenant applicatif,
sans besoin documenté de GPU, service mesh, opérateurs ou workloads hétérogènes).

### Option A — AWS Lambda (conteneurs ou zip)

**Rejet proposé :** FastAPI est déjà fixé par la charte comme framework ASGI cible, conçu pour un
processus serveur persistant. L'exigence de streaming HTTP (`V2-ADR-001`) et la limite de 29
secondes d'API Gateway (déjà identifiée comme facteur de rejet du traitement synchrone en
`V2-ADR-004`) rendent Lambda structurellement inadapté à ce rôle, indépendamment du coût ou de la
familiarité de l'équipe avec le service.

### Option B — Amazon ECS (launch type Fargate)

Cluster ECS dont les services (`fastapi`, `ingestion`) tournent en launch type Fargate, sans
instance EC2 à gérer.

**Avantages :** aucun control plane facturé séparément (contrairement à EKS, qui facture le
control plane indépendamment du calcul) ; rôles IAM par tâche nativement supportés en Fargate,
sans mécanisme d'attribution d'identité intermédiaire à choisir ; surface d'exploitation minimale
(pas de CNI, pas d'admission controller, pas de CRD à opérer) ; correspond exactement au besoin
documenté à ce jour (service HTTP stateless + workers SQS).

**Limites :** écosystème d'extensions (opérateurs, service mesh, outillage GitOps) plus restreint
que Kubernetes si un besoin de cette nature apparaît plus tard ; moins démonstratif d'une
compétence Kubernetes pour un objectif de portfolio.

### Option C — Amazon EKS (launch type Fargate)

Cluster EKS dont tous les pods tournent en profils Fargate, sans node group EC2 (option
initialement retenue par une version antérieure de cet ADR).

**Avantages :** écosystème Kubernetes complet si un besoin concret apparaît (multi-équipes,
GitOps, service mesh, opérateurs, workloads hétérogènes) ; compétence valorisée sur le marché pour
un objectif de portfolio.

**Rejet proposé :** aucun des besoins ci-dessus n'est documenté dans le périmètre V2 actuel — la
charge décrite reste un service HTTP stateless et des workers homogènes. Le control plane EKS
facture un coût plancher indépendant du trafic, en plus d'exiger une couche d'attribution
d'identité supplémentaire (IRSA, Pod Identity indisponible sur Fargate) que Fargate résout
nativement côté ECS. Retenir EKS ici reviendrait à payer la complexité Kubernetes sans consommer
le bénéfice qui la justifie. Si un besoin concret de cette nature apparaît (cf. options futures
ci-dessous), il justifiera un nouvel ADR au moment où il sera documenté — pas une anticipation non
étayée aujourd'hui.

## Décision proposée pour la plateforme

Retenir **l'option B — Amazon ECS, launch type Fargate**. Un besoin futur documenté (GPU,
multi-équipes, service mesh) peut justifier une migration vers EKS ; ce n'est pas le cas
aujourd'hui, et anticiper ce besoin sans le documenter violerait le principe de proportionnalité
déjà appliqué ailleurs dans ce corpus (ex. rejet de l'orchestration multi-agent par défaut en
`V2-ADR-005`).

## Choix du launch type ECS

### Option A — Launch type EC2 (instances gérées)

Cluster ECS avec instances EC2 (Cluster Autoscaler ou Capacity Provider EC2).

**Avantages :** contrôle fin des instances, coût par vCPU/GB inférieur à Fargate à charge
constante, familiarité opérationnelle large.

**Limites :** coût fixe dès la première instance même sans trafic, patching OS à la charge du
projet, dimensionnement initial à deviner pour un environnement de démonstration à trafic
imprévisible.

### Option B — Launch type Fargate uniquement

Tous les services (FastAPI et workers d'ingestion) tournent en Fargate, sans instance EC2.

**Avantages :** aucune gestion d'instance, aucun patching OS, facturation à la tâche exécutée
cohérente avec un environnement `test` à trafic intermittent, aligné avec l'objectif FinOps de la
charte.

**Limites :** coût par unité de calcul plus élevé qu'EC2 à charge soutenue, pas d'accès GPU, temps
de démarrage de tâche légèrement supérieur à une instance déjà chaude.

### Option C — Hybride Fargate + capacity provider EC2

Fargate par défaut, avec un capacity provider EC2 réservé aux futurs besoins non couverts (GPU).

**Rejet proposé pour la V2 initiale :** aucun besoin actuel ne justifie une instance EC2 ; son
ajout prématuré augmente le coût de base et la surface d'exploitation sans bénéfice démontré.

## Décision proposée pour le launch type

Retenir **l'option B — Fargate uniquement**. Le capacity provider EC2 reste une option future
explicitement différée, à justifier par un besoin concret (GPU) avant tout ajout.

```text
VPC dédié V2 (nouveau, eu-west-3, ≥ 2 AZ)
  ├── subnets publics   (NAT Gateway uniquement, pas de load balancer internet-facing)
  ├── subnets privés    (tâches Fargate ECS, load balancer interne)
  └── VPC endpoints      (S3, DynamoDB, ECR API/DKR, Secrets Manager, STS,
                           CloudWatch Logs, KMS, Bedrock Runtime — trafic AWS sans NAT)

ECS (cluster régional, sans control plane facturé séparément)
  ├── service `fastapi`     — launch type Fargate, exposé par le load balancer interne
  └── service `ingestion`   — launch type Fargate, workers déclenchés par SQS (V2-ADR-004)
```

Le provisionnement ECS/VPC est gouverné par un flag Terraform `enable_ecs_platform` (même
convention que `enable_rag`), permettant de garder l'environnement `test` 100 % serverless tant
que FastAPI n'est pas prêt à être déployé — le vote de cet ADR n'engage pas de coût immédiat.

## Réseau et sécurité

- **Subnets :** privés pour toutes les tâches et le load balancer interne ; publics réservés au
  NAT Gateway (1 par défaut en `test` pour limiter le coût, 1 par AZ recommandé pour la
  disponibilité en environnement de production future — compromis documenté comme risque accepté
  pour `test`) ;
- **VPC endpoints (Gateway pour S3/DynamoDB, Interface pour le reste) :** réduisent la dépendance
  au NAT Gateway pour le trafic AWS et limitent la surface d'exfiltration. L'endpoint
  `bedrock-runtime` couvre les embeddings des workers d'ingestion (`V2-ADR-003`/`V2-ADR-004`) ;
  l'endpoint ECR couvre le pull d'image sans NAT. L'existence d'un endpoint PrivateLink pour
  l'invocation AgentCore Runtime reste à confirmer en LLD-001 ; à défaut, ce trafic transite par le
  NAT Gateway (exception documentée) ;
- **Security Groups :** réseau `awsvpc` natif à Fargate — chaque tâche reçoit sa propre interface
  réseau et son propre security group. Refus par défaut entre services ; autorisations explicites
  FastAPI → DNS, FastAPI → AgentCore Runtime (IAM, pas de règle réseau spécifique nécessaire
  au-delà du load balancer), workers ingestion → S3/DynamoDB/Bedrock ;
- **IAM :** un **rôle IAM de tâche (Task IAM Role)** dédié par service ECS, attribué nativement en
  Fargate sans mécanisme d'attribution intermédiaire à opérer — la question IRSA/Pod Identity qui
  se posait pour EKS n'existe pas ici. Le rôle FastAPI est limité à l'invocation IAM d'AgentCore
  Runtime et aux accès applicatifs nécessaires, jamais à une administration IAM large ;
- **Autoscaling :** ECS Service Auto Scaling (Application Auto Scaling) en target tracking sur le
  déploiement FastAPI (requêtes/CPU) ; les workers d'ingestion sont dimensionnés par une politique
  de target tracking sur la profondeur de la file SQS (métrique CloudWatch
  `ApproximateNumberOfMessagesVisible`, mécanisme précis différé au LLD-001/LLD-002).

## Conséquences

- un nouveau module Terraform (`infra/modules/vpc_ecs_platform` ou équivalent) est nécessaire,
  suivant la convention documentée dans `infra/modules/README.md` (versions.tf, variables.tf,
  locals.tf, main.tf, outputs.tf, README.md, tags communs, IAM least privilege) ;
- de nouvelles variables Terraform sont ajoutées à `infra/environments/test/variables.tf`
  (`enable_ecs_platform`, CIDR VPC, zones de disponibilité, nombre de NAT Gateway) ;
- un coût plancher mensuel s'applique dès que `enable_ecs_platform = true`, même sans trafic (NAT
  Gateway, VPC endpoints) — mais sans frais de control plane séparé, contrairement à l'option EKS
  écartée ; à documenter dans l'estimation FinOps du LLD ;
- Helm n'est plus un mécanisme de déploiement pertinent (spécifique à Kubernetes) ; les
  définitions de tâches ECS et les services sont pilotés directement par Terraform, sans couche de
  templating supplémentaire — simplification par rapport à la version EKS de cet ADR, à répercuter
  sur `V2-ADR-009` et la charte (`V2-ARCH-009`) ;
- `scripts/terraform_plan_guard.py` doit être étendu pour couvrir les nouvelles ressources
  réseau/ECS au même titre que DynamoDB et S3 ;
- `V2-ADR-001` peut passer en `Accepted` une fois ce dimensionnement validé, puisqu'il en dépend
  implicitement — sans dépendance inverse : ce dernier décide la frontière logique, pas sa
  réalisation physique.

## Preuves attendues

- `terraform plan` ne modifie ni ne détruit aucune ressource V1 existante (DynamoDB, S3,
  AgentCore natif) lors de l'introduction du VPC/ECS ;
- une tâche FastAPI ne peut atteindre que les endpoints explicitement autorisés par Security Group
  (test d'egress refusé vers un domaine arbitraire) ;
- l'invocation d'AgentCore Runtime depuis une tâche FastAPI utilise exclusivement le rôle IAM de
  tâche associé, sans identifiants statiques ;
- `enable_ecs_platform = false` ne provisionne aucune ressource ECS/VPC (coût nul par défaut) ;
- estimation de coût mensuel documentée et comparée au budget FinOps de la charte, incluant le
  différentiel face à l'option EKS écartée.

## Références AWS

- Amazon ECS avec launch type Fargate ;
- IAM Task Roles (rôle IAM natif par tâche, sans mécanisme d'attribution intermédiaire) ;
- VPC Gateway et Interface Endpoints ;
- Amazon Bedrock AgentCore Runtime avec authentification IAM.
