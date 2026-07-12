# Rationalisation CI/CD — environnement test

- **Branche :** `migration/secure-agentcore-v1`
- **Périmètre :** environnement `test`
- **Architecture cible :** ADR-0004

## 1. Objectif

Conserver deux points d’entrée opérationnels :

1. une pipeline infrastructure ;
2. une pipeline application.

Les workflows historiques ou scripts de spike ne sont pas des points d’entrée nominaux.

## 2. Pipeline infrastructure

Workflow :

```text
.github/workflows/test-terraform-stack.yml
```

Responsabilités :

- Gitleaks ;
- vérification lockfile ;
- `terraform fmt` ;
- `terraform validate` ;
- `terraform plan` ;
- `terraform apply` manuel ;
- `destroy-plan` ;
- `destroy` avec confirmation.

Actions disponibles :

```text
plan
apply
destroy-plan
destroy
```

### Règles

- `apply` uniquement sur la branche par défaut de test ;
- credentials AWS via GitHub OIDC ;
- revue du plan obligatoire ;
- `destroy` exige `confirm_destroy=true` ;
- le workflow protège les ressources AgentCore existantes en conservant l’image Runtime actuelle lorsqu’elles sont déjà dans le state.

## 3. Pipeline application

Workflow :

```text
.github/workflows/test-application-deploy.yml
```

Modes :

| Mode | Usage |
|---|---|
| `frontend-only` | Rebuild et redéploie uniquement React vers S3/CloudFront. |
| `image-only` | Build et push uniquement l’image AgentCore vers ECR. |
| `runtime-only` | Met à jour Runtime avec un tag image existant. |
| `full` | Build/push image, applique le control plane AgentCore, puis redéploie le frontend. |

### Déploiement complet actuel

```text
Actions -> Test Application Deploy
```

Paramètres :

```text
deploy_mode = full
image_tag = test
endpoint_name = default
confirm_deploy = true
```

Le workflow actuel :

1. lit les outputs Terraform ;
2. construit l’image `linux/arm64` ;
3. pousse deux tags ECR uniques ;
4. applique Runtime, Endpoint, Memory et Gateway MCP ;
5. relit les outputs Terraform ;
6. exécute le gate Runtime JWT ;
7. génère `.env.production` ;
8. construit React ;
9. synchronise S3 ;
10. invalide CloudFront.

### Écart actuel

Le workflow injecte encore :

```text
VITE_AGENT_RUNTIME_INVOKE_URL
```

avec l’URL Runtime directe.

Après remédiation ADR-0004, il devra injecter en priorité :

```text
VITE_AGENT_INVOKE_URL=<API Gateway /agent/invoke>
```

Le Runtime direct restera au maximum un fallback temporaire de rollback.

## 4. Workflow recommandé frontend seul

```text
Actions -> Test Application Deploy

deploy_mode = frontend-only
confirm_deploy = true
```

Précondition actuelle : une URL d’invocation valide doit être disponible dans les outputs ou fournie en override.

Après remédiation, l’URL nominale sera `agent_invoke_url` depuis API Gateway.

## 5. Workflow recommandé runtime seul

```text
Actions -> Test Application Deploy

deploy_mode = runtime-only
image_tag = <tag-immutable-existant>
endpoint_name = default
confirm_deploy = true
```

Ne pas utiliser `image_tag=test` en `runtime-only`, car ce mode ne construit pas l’image.

## 6. Modèle Bedrock

Le modèle V1 courant est :

```text
eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

Il a été validé avec :

```text
ConverseStream + toolConfig
```

Ne pas changer le modèle sans test préalable et validation explicite.

## 7. Tests après déploiement

### Infrastructure

```bash
terraform -chdir=infra/environments/test output
```

Vérifier :

```text
agent_runtime_arn
agent_runtime_invoke_url
agentcore_memory_id
agentcore_gateway_mcp_url
service_url
agent_invoke_url après remédiation
```

### Runtime

Vérifier dans CloudWatch :

```text
request_accepted
agent_invocation
memory_retrieved / memory_saved
gateway_tools_loaded ou gateway_tools_not_configured
```

Ne jamais afficher de token ou prompt brut.

### Frontend

- login Cognito ;
- nouveau mot de passe si requis ;
- envoi message ;
- session UUID 36 caractères ;
- réponse Runtime ;
- aucun appel direct Runtime après remédiation API Gateway.

### CORS après remédiation

```bash
curl -i -X OPTIONS "$AGENT_INVOKE_URL" \
  -H "Origin: https://<cloudfront-domain>" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-amzn-bedrock-agentcore-runtime-session-id"
```

## 8. Destroy test

Workflow :

```text
.github/workflows/test-terraform-stack.yml
```

Paramètres :

```text
action = destroy
confirm_destroy = true
```

L’environnement test est destructible. Les buckets versionnés et repositories ECR sont configurés avec des options de destruction adaptées au test ; toute utilisation hors test doit revoir ces paramètres.

## 9. Workflows et scripts historiques

À considérer comme historiques ou diagnostic uniquement :

- activation Lambda Facade ;
- P0 Gateway-first ;
- scripts Boto3 historiques de création Runtime ;
- variables manuelles P0.

Ils ne doivent pas être présentés comme procédure nominale.

## 10. Évolutions requises V1

- réaligner la pipeline frontend sur API Gateway ;
- renommer les paramètres `gateway_first` obsolètes ;
- ajouter smoke test API Gateway -> Runtime ;
- ajouter CORS smoke test ;
- ajouter test identité négatif ;
- ajouter test Runtime -> MCP Gateway -> tool ;
- publier les résultats de tests et plans en artifacts.
