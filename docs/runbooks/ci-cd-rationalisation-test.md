# Rationalisation CI/CD — environnement test

## Objectif

L'objectif est de réduire la complexité opérationnelle côté client.

Pendant la phase de construction, plusieurs workflows techniques ont été introduits pour isoler les risques : frontend, image AgentCore, runtime, activation de la Facade. Ces workflows sont utiles pour le diagnostic, mais ils ne constituent pas la cible d'exploitation.

La cible test devient :

1. une pipeline infrastructure ;
2. une pipeline applicative consolidée ;
3. une procédure destroy contrôlée dans la pipeline infrastructure.

## Workflows cibles

### 1. Infrastructure

Workflow :

```text
.github/workflows/test-terraform-stack.yml
```

Rôle :

```text
plan
apply
destroy-plan
destroy
```

Cette pipeline reste responsable du socle Terraform : Cognito, DynamoDB, S3/CloudFront, API Gateway, Lambda Facade, ECR, IAM Runtime.

### 2. Application

Workflow :

```text
.github/workflows/test-application-deploy.yml
```

Rôle :

```text
frontend-only
image-only
runtime-only
full
```

Modes :

| Mode | Usage |
|---|---|
| `frontend-only` | Rebuild et redéploie uniquement le frontend React vers S3/CloudFront. |
| `image-only` | Build et push uniquement l'image AgentCore vers ECR. |
| `runtime-only` | Déploie ou met à jour AgentCore Runtime avec une image déjà poussée. |
| `full` | Build/push image, déploie Runtime, active Facade -> Runtime, puis redéploie le frontend. |

## Workflow recommandé de redéploiement complet

Pré-requis : la pipeline infrastructure a déjà été appliquée avec succès.

Ensuite lancer :

```text
Actions -> Test Application Deploy
```

Avec :

```text
deploy_mode = full
image_tag = test
endpoint_name = default
activate_facade = true
confirm_deploy = true
```

Le workflow exécute :

```text
1. lecture des outputs Terraform ;
2. build/push de l'image AgentCore vers ECR ;
3. création ou mise à jour d'AgentCore Runtime ;
4. activation Lambda Facade -> Runtime ;
5. génération du .env.production frontend ;
6. build React ;
7. sync S3 ;
8. invalidation CloudFront.
```

## Workflow recommandé frontend seul

Pour une correction purement frontend :

```text
Actions -> Test Application Deploy
deploy_mode = frontend-only
confirm_deploy = true
```

## Workflows transitoires

Les workflows historiques dédiés par lot peuvent être conservés temporairement pour diagnostic, mais ils ne doivent plus être présentés comme point d'entrée principal au client.

La documentation et les échanges client doivent privilégier :

```text
Test Terraform Stack      = infrastructure
Test Application Deploy   = application
```

## Destroy test

Le destroy reste dans :

```text
.github/workflows/test-terraform-stack.yml
```

La cible est de garder une seule procédure destroy contrôlée par :

```text
action = destroy
confirm_destroy = true
```

Pour un environnement test destructible, les ressources de type bucket applicatif doivent être conçues pour être détruites proprement, notamment les buckets S3 versionnés.
