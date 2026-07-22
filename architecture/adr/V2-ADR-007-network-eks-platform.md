# V2-ADR-007 — Architecture réseau et calcul EKS

- **Statut :** Proposed
- **Branche cible :** `migration/secure-agentcore-v2`
- **Gate :** V2-G1
- **Dépendances :** V2-ADR-001, V2-ADR-006, V2-ADR-009

## Contexte

La V1 est entièrement serverless (API Gateway, Lambda, DynamoDB, Cognito, AgentCore natif) : aucun
VPC, subnet ou cluster EKS n'existe dans l'infrastructure actuelle. `V2-ADR-001` fixe déjà le
chemin réseau cible pour l'ingress (`API Gateway → intégration privée VPC Link → load balancer
interne → FastAPI sur EKS → AgentCore Runtime IAM-only`) mais ne dimensionne pas le VPC, les
subnets, le calcul EKS ni les endpoints qu'il présuppose. Cet ADR comble ce vide.

## Exigences

- multi-AZ (HLD section 8) ;
- Runtime jamais exposé directement à internet ;
- workloads FastAPI et workers d'ingestion identifiés par IAM (Pod Identity) ;
- egress par défaut refusé, ouvert explicitement par cas d'usage ;
- coût contrôlable pour un environnement `test` jetable (cohérent avec le pattern
  `force_destroy = true` déjà utilisé pour le frontend) ;
- aucune ressource EKS ne doit être provisionnée avant que FastAPI soit prêt à être déployé.

## Options

### Option A — Node groups EC2 managés

Cluster EKS avec node groups EC2 (Cluster Autoscaler ou Karpenter).

**Avantages :** contrôle fin des instances, coût par vCPU/GB inférieur à Fargate à charge
constante, familiarité opérationnelle large.

**Limites :** coût fixe dès la première instance même sans trafic, patching OS à la charge du
projet, dimensionnement initial à deviner pour un environnement de démonstration à trafic
imprévisible.

### Option B — EKS Fargate uniquement

Cluster EKS dont tous les pods (FastAPI et workers d'ingestion) tournent sur des profils Fargate,
sans node group EC2.

**Avantages :** aucune gestion de nœud, aucun patching OS, facturation au pod exécuté cohérente
avec un environnement `test` à trafic intermittent, aligné avec l'objectif FinOps de la charte.

**Limites :** coût par unité de calcul plus élevé qu'EC2 à charge soutenue, pas d'accès GPU ni
DaemonSet, temps de démarrage de pod légèrement supérieur.

### Option C — Hybride Fargate + node group

Fargate par défaut, avec un node group EC2 réservé aux futurs besoins non couverts (GPU,
DaemonSet réseau).

**Rejet proposé pour la V2 initiale :** aucun besoin actuel ne justifie un node group EC2 ; son
ajout prématuré augmente le coût de base et la surface d'exploitation sans bénéfice démontré.

## Décision proposée

Retenir **l'option B**. Le node group EC2 reste une option future explicitement différée, à
justifier par un besoin concret (GPU, DaemonSet) avant tout ajout.

```text
VPC dédié V2 (nouveau, eu-west-3, ≥ 2 AZ)
  ├── subnets publics   (NAT Gateway uniquement, pas d'ALB internet-facing)
  ├── subnets privés    (pods Fargate EKS, load balancer interne)
  └── VPC endpoints      (S3, DynamoDB, ECR API/DKR, Secrets Manager, STS,
                           CloudWatch Logs, KMS — trafic AWS sans passer par le NAT)

EKS (control plane régional)
  ├── namespace `fastapi`    — profil Fargate, exposé par le load balancer interne
  └── namespace `ingestion`  — profil Fargate, workers déclenchés par SQS (V2-ADR-004)
```

Le provisionnement EKS/VPC est gouverné par un flag Terraform `enable_eks_platform` (même
convention que `enable_rag`), permettant de garder l'environnement `test` 100 % serverless tant
que FastAPI n'est pas prêt à être déployé — le vote de cet ADR n'engage pas de coût immédiat.

## Réseau et sécurité

- **Subnets :** privés pour tous les workloads et le load balancer interne ; publics réservés au
  NAT Gateway (1 par défaut en `test` pour limiter le coût, 1 par AZ recommandé pour la
  disponibilité en environnement de production future — compromis documenté comme risque accepté
  pour `test`) ;
- **VPC endpoints (Gateway pour S3/DynamoDB, Interface pour le reste) :** réduisent la dépendance
  au NAT Gateway pour le trafic AWS et limitent la surface d'exfiltration ;
- **Network Policies :** refus par défaut entre pods ; autorisations explicites FastAPI → DNS,
  FastAPI → AgentCore Runtime (IAM, pas de règle réseau spécifique nécessaire au-delà du LB),
  workers ingestion → S3/DynamoDB/Bedrock ;
- **IAM :** EKS Pod Identity (pas IRSA) pour associer un rôle IAM dédié à chaque ServiceAccount,
  conformément au HLD ; le rôle FastAPI est limité à l'invocation IAM d'AgentCore Runtime et aux
  accès applicatifs nécessaires, jamais à une administration IAM large ;
- **Autoscaling :** HPA sur le déploiement FastAPI (métriques de requêtes/CPU) ; les workers
  d'ingestion sont dimensionnés par la profondeur de la file SQS (mécanisme précis différé au
  LLD-001/LLD-002, ex. KEDA).

## Conséquences

- un nouveau module Terraform (`infra/modules/vpc_eks_platform` ou équivalent) est nécessaire,
  suivant la convention documentée dans `infra/modules/README.md` (versions.tf, variables.tf,
  locals.tf, main.tf, outputs.tf, README.md, tags communs, IAM least privilege) ;
- de nouvelles variables Terraform sont ajoutées à `infra/environments/test/variables.tf`
  (`enable_eks_platform`, CIDR VPC, zones de disponibilité, nombre de NAT Gateway) ;
- un coût plancher mensuel (control plane EKS, endpoints, NAT Gateway) s'applique dès que
  `enable_eks_platform = true`, même sans trafic — à documenter dans l'estimation FinOps du LLD ;
- `scripts/terraform_plan_guard.py` doit être étendu pour couvrir les nouvelles ressources
  réseau/EKS au même titre que DynamoDB et S3 ;
- `V2-ADR-001` peut passer en `Accepted` une fois ce dimensionnement validé, puisqu'il en dépend
  implicitement.

## Preuves attendues

- `terraform plan` ne modifie ni ne détruit aucune ressource V1 existante (DynamoDB, S3,
  AgentCore natif) lors de l'introduction du VPC/EKS ;
- un pod FastAPI ne peut atteindre que les endpoints explicitement autorisés par Network Policy
  (test d'egress refusé vers un domaine arbitraire) ;
- l'invocation d'AgentCore Runtime depuis un pod FastAPI utilise exclusivement l'identité IAM Pod
  Identity, sans identifiants statiques ;
- `enable_eks_platform = false` ne provisionne aucune ressource EKS/VPC (coût nul par défaut) ;
- estimation de coût mensuel documentée et comparée au budget FinOps de la charte.

## Références AWS

- Amazon EKS avec profils Fargate ;
- Amazon EKS Pod Identity ;
- VPC Gateway et Interface Endpoints ;
- Amazon Bedrock AgentCore Runtime avec authentification IAM.
