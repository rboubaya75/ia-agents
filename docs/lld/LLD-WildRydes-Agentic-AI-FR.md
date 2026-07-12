# LLD — WildRydes Agentic AI Application Landing Zone

- **Version :** 3.0
- **Date :** 2026-07-12
- **Branche par défaut :** `migration/secure-agentcore-v1`
- **Périmètre :** environnement `test`
- **IaC :** Terraform
- **CI/CD :** GitHub Actions avec OIDC AWS
- **Runtime :** `deploy-agentcore/agents/phase_4.py`

## 1. Objet

Ce document décrit :

- le contrat technique courant ;
- la cible V1 approuvée ;
- les écarts entre le code actuel et la cible ;
- les critères de validation avant clôture V1.

Architecture nominale cible :

```text
Frontend React
  -> API Gateway HTTP API
  -> HTTP_PROXY direct
  -> AgentCore Runtime JWT
```

Tools :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP
  -> targets tools
  -> DynamoDB / APIs métier
```

## 2. Modules et composants existants

| Domaine | Implémentation actuelle | Statut |
|---|---|---|
| Frontend | `infra/modules/frontend_static_site` | présent |
| Identity | `infra/modules/cognito_web_auth` | présent |
| API ingress | `infra/modules/api_gateway_agent_ingress` | présent, route agent inactive |
| ECR | `infra/modules/ecr_container_repository` | présent |
| DynamoDB | `infra/modules/dynamodb_trips` | présent |
| Runtime/Memory/Gateway | ressources natives dans `agentcore_native.tf` | présents |
| Runtime code | `deploy-agentcore/agents/phase_4.py` | présent |
| Lambda Facade | `infra/modules/agent_api_facade` | legacy, non nominal |
| CI Terraform | `test-terraform-stack.yml` | présent |
| CI application | `test-application-deploy.yml` | présent, frontend sur URL Runtime directe |

## 3. Contrat frontend

### 3.1 Authentification

Le frontend utilise Cognito SRP et récupère un **access token** pour les appels API.

L’ID token peut être utilisé pour l’affichage utilisateur, mais ne doit pas être utilisé comme source d’autorisation backend.

### 3.2 Endpoint cible

```http
POST https://<api-gateway-domain>/agent/invoke
Authorization: Bearer <cognito_access_token>
Content-Type: application/json
X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: <uuid-v4>
```

### 3.3 Payload

```json
{
  "prompt": "Plan a trip to Tokyo",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 3.4 Champs interdits

```text
actorId
actor_id
userId
user_id
tenantId
tenant_id
trustedIdentity
trusted_identity
groups
```

Le body ne doit jamais être une source d’identité.

### 3.5 Configuration frontend cible

Variable nominale :

```text
VITE_AGENT_INVOKE_URL=https://<api-gateway-domain>/agent/invoke
```

Fallback temporaire de rollback :

```text
VITE_AGENT_RUNTIME_INVOKE_URL=<runtime-direct-url>
```

Le fallback Runtime direct ne doit pas être la configuration nominale après remédiation.

## 4. API Gateway HTTP API

### 4.1 État actuel

Le module crée :

- `aws_apigatewayv2_api` ;
- authorizer JWT Cognito ;
- stage `$default` ;
- CORS ;
- intégration Gateway-first conditionnelle ;
- intégration Lambda Facade conditionnelle.

Dans l’environnement test :

```hcl
gateway_first_enabled         = false
agentcore_gateway_url         = ""
agentcore_runtime_target_name = ""
```

Aucune route `/agent/invoke` active n’est donc créée dans l’état actuel.

### 4.2 Modification V1 requise

Ajouter au module :

```hcl
runtime_direct_enabled       = bool
agentcore_runtime_invoke_url = string
```

Créer :

```hcl
resource "aws_apigatewayv2_integration" "agentcore_runtime_direct" {
  integration_type   = "HTTP_PROXY"
  integration_method = "POST"
  integration_uri    = var.agentcore_runtime_invoke_url
}
```

Créer la route :

```text
POST /agent/invoke
```

avec :

```text
authorization_type = JWT
```

### 4.3 URL Runtime cible

```text
https://bedrock-agentcore.eu-west-3.amazonaws.com/runtimes/<url-encoded-runtime-arn>/invocations?qualifier=DEFAULT
```

### 4.4 Règles de proxy

Ne pas réécrire :

```text
Authorization
X-Amzn-Bedrock-AgentCore-Runtime-Session-Id
```

Ces headers doivent être transmis naturellement par le proxy HTTP.

### 4.5 CORS

Origine autorisée :

```text
https://<cloudfront-domain>
```

Méthodes :

```text
OPTIONS
POST
```

Headers :

```text
authorization
content-type
x-amzn-bedrock-agentcore-runtime-session-id
x-correlation-id
```

Pas de wildcard d’origine dans la cible V1.

### 4.6 Throttling et logs

À ajouter en V1 :

- throttling stage/route ;
- logs d’accès structurés ;
- métriques 4xx, 5xx, 429 et latence ;
- aucune journalisation du token ou du prompt brut.

## 5. AgentCore Runtime

### 5.1 Terraform

La ressource Runtime configure :

- image ECR ;
- `MODEL_ID` ;
- `MEMORY_ID` ;
- `GATEWAY_URL` ;
- authorizer JWT Cognito ;
- claim `token_use = access` ;
- `request_header_allowlist = ["Authorization"]` ;
- `network_mode = PUBLIC` ;
- endpoint Runtime nommé `default`.

### 5.2 Contrat identité

Ordre nominal de résolution :

1. claims du contexte Runtime ;
2. claims du JWT transmis dans `Authorization` après validation Runtime ;
3. aucun champ issu du body.

Le fallback `trustedIdentity.actorId` encore présent dans le code est une dette legacy. Il doit être supprimé ou explicitement justifié avant clôture V1.

### 5.3 Session

Le `sessionId` doit faire au moins 33 caractères. Le frontend génère un UUID v4 de 36 caractères.

Le même identifiant est envoyé :

- dans le header Runtime ;
- dans le body applicatif.

Il ne sert jamais d’identité utilisateur.

### 5.4 Modèle

```text
MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_REGION=eu-west-3
```

Le modèle a été validé avec `ConverseStream` et `toolConfig`.

### 5.5 Tools

Le Runtime construit actuellement :

```text
tools = [web_search] + initialize_mcp_tools()
```

Le tool local `web_search` est disponible.

Le chemin MCP n’est chargé que si les paramètres suivants sont présents :

```text
GATEWAY_URL
CLIENT_ID
CLIENT_SECRET
TOKEN_URL
SCOPE_STRING
```

Terraform n’injecte actuellement que :

```text
GATEWAY_URL
GATEWAY_AUTH_MODE=aws_iam
```

Il faut choisir et implémenter un seul contrat :

- SigV4/IAM de bout en bout ; ou
- OAuth client credentials avec Secrets Manager.

Le mélange actuel n’est pas valide comme cible finale.

## 6. AgentCore Gateway MCP

### 6.1 Rôle

Exposer les tools à l’agent Runtime.

### 6.2 État actuel

Une Gateway MCP native existe avec :

```text
authorizer_type = AWS_IAM
protocol_type   = MCP
```

Aucun target tool métier n’est encore validé end-to-end.

### 6.3 Cible V1 minimale

- un target tool réel ;
- IAM limité à ce target ;
- test Runtime -> MCP Gateway -> tool ;
- injection serveur de `userId` ;
- contrôle d’appartenance des données ;
- erreurs normalisées ;
- aucun secret dans les logs.

## 7. AgentCore Memory

Namespace :

```text
travel/{actorId}/preferences
```

Règles :

- isolation par `actorId` ;
- pas de secrets ;
- pas de paiement ;
- pas de données transactionnelles ;
- échec Memory non bloquant pour une réponse simple ;
- tests User A / User B obligatoires.

## 8. DynamoDB Trips

```text
PK = userId
SK = tripId
billing = PAY_PER_REQUEST
PITR = enabled
SSE = enabled
```

Chaque opération tool doit utiliser le `userId` injecté par le Runtime et appliquer des conditions empêchant les accès cross-user.

## 9. ECR et image Runtime

### 9.1 Repository

- tags immuables ;
- scan on push ;
- chiffrement AES256 ;
- lifecycle : suppression des images non taggées après 7 jours ;
- conservation d’un nombre limité d’images récentes.

### 9.2 Image

Cible AgentCore :

```text
linux/arm64
```

Le conteneur s’exécute avec un utilisateur non root.

Dette détectée : l’image de base actuelle est Python 3.13 alors que la règle de projet cible Python 3.12. Ce point doit être arbitré et aligné avant clôture V1.

## 10. IAM

### 10.1 Dette actuelle

Plusieurs statements utilisent encore :

```text
Resource = "*"
bedrock-agentcore:*
```

### 10.2 Cible

Runtime :

- pull ECR repository précis ;
- modèles/inference profiles précis ;
- Memory précise ;
- MCP Gateway précise ;
- log groups précis ;
- secret précis si utilisé.

Gateway :

- targets Lambda/API précis ;
- logs précis ;
- aucune permission Runtime ingress devenue inutile.

## 11. Frontend CloudFront / S3

Contrôles déjà présents :

- S3 Block Public Access ;
- OAC CloudFront ;
- HTTPS redirect ;
- versioning ;
- SSE ;
- SPA fallback.

À ajouter ou vérifier :

- security headers policy ;
- CSP ;
- HSTS ;
- `X-Content-Type-Options` ;
- `Referrer-Policy` ;
- future WAF si retenu.

## 12. CI/CD

### 12.1 Terraform

Workflow :

```text
.github/workflows/test-terraform-stack.yml
```

Contrôles :

- Gitleaks ;
- lockfile ;
- fmt ;
- validate ;
- plan ;
- apply manuel ;
- destroy contrôlé.

### 12.2 Application

Workflow :

```text
.github/workflows/test-application-deploy.yml
```

À modifier :

- lire `agent_invoke_url` API Gateway ;
- ne plus générer uniquement `VITE_AGENT_RUNTIME_INVOKE_URL` ;
- renommer les mentions `gateway_first` obsolètes ;
- ajouter un gate API Gateway -> Runtime ;
- ajouter CORS smoke test ;
- ajouter tool smoke test.

## 13. Tests V1

### 13.1 Infrastructure

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform plan
```

### 13.2 Frontend

```bash
npm ci
npm run lint
npm run build
```

### 13.3 API et sécurité

- `OPTIONS /agent/invoke` depuis CloudFront ;
- sans JWT : rejet ;
- JWT invalide : rejet ;
- mauvais client : rejet ;
- JWT valide : 2xx ou erreur Runtime métier explicite ;
- `actorId`, `userId`, `tenantId`, `trustedIdentity`, `groups` dans body : rejet ;
- session courte : rejet ;
- User A ne lit pas Memory/trips User B ;
- aucun token ou prompt brut dans les logs.

### 13.4 Bedrock

- Claude Haiku 4.5 accessible ;
- streaming ;
- tool use ;
- erreurs de modèle normalisées.

### 13.5 MCP

- Gateway accessible depuis Runtime ;
- target réel listé ;
- tool exécuté ;
- identité injectée ;
- accès cross-user refusé.

## 14. Critères de sortie

La V1 est clôturable uniquement si :

- le frontend utilise API Gateway ;
- API Gateway proxyfie Runtime direct ;
- Runtime valide encore le JWT ;
- CORS, throttling et logs sont en place ;
- le modèle fonctionne ;
- Memory est isolée ;
- au moins un tool MCP fonctionne ;
- IAM est réduit ;
- CI et smoke tests passent ;
- documentation et code sont alignés.
