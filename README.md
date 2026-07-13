# WildRydes — Secure AgentCore V1 Landing Zone

- **Branche et environnement :** `migration/secure-agentcore-v1` / `test`
- **IaC :** Terraform
- **CI/CD :** GitHub Actions avec OIDC AWS
- **Runtime :** Python 3.12, `deploy-agentcore/agents/phase_4.py`
- **Modèle :** `eu.anthropic.claude-haiku-4-5-20251001-v1:0`
- **RAG :** hors V1, désactivé par défaut

## Architecture V1 implémentée

```text
Browser / React
  -> CloudFront / S3 privé
  -> Cognito User Pool
  -> API Gateway HTTP API
       - Cognito JWT authorizer
       - CORS limité au domaine CloudFront
       - throttling et access logs
  -> Lambda Agent Invocation Security Facade
       - payload strict prompt + sessionId
       - actorId = claims.sub
       - rejet de toute identité ou configuration client arbitraire
  -> AgentCore Runtime IAM-only
       - trustedIdentity produite par la façade
       - Claude Haiku 4.5 EU
       - AgentCore Memory
       - tools Strands
  -> AgentCore Gateway MCP AWS_IAM
  -> Lambda Trip Tools
  -> DynamoDB Trips
```

Le navigateur ne connaît et n’utilise jamais l’URL technique AgentCore Runtime.

## Contrat d’identité

La seule source de confiance est :

```text
actorId = Cognito access-token claim `sub`
```

Le frontend envoie uniquement :

```json
{
  "prompt": "Planifie un voyage à Tokyo",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

La façade rejette notamment :

```text
actorId
userId
tenantId
trustedIdentity
groups
modelOverride
systemPrompt
toolName
```

Elle construit ensuite `trustedIdentity.actorId` pour l’appel IAM vers Runtime. Runtime écrase toujours `userId` avant un appel aux tools Trips.

## Contrôles de sécurité

- S3 Block Public Access et CloudFront OAC ;
- HTTPS et headers CloudFront : CSP, HSTS, anti-framing, `nosniff`, Referrer-Policy et Permissions-Policy ;
- Cognito access token vérifié par API Gateway puis contrôlé par la façade (`token_use`, `client_id`, `sub`) ;
- façade Lambda Python 3.12 ARM64, concurrence réservée et timeout inférieur à API Gateway ;
- Runtime IAM-only avec resource policy limitée au rôle de la façade ;
- Gateway MCP IAM avec resource policy limitée au rôle Runtime ;
- IAM Runtime limité au modèle, à Memory, au Gateway, à ECR et aux logs nécessaires ;
- Lambda Trip Tools limitée à la table DynamoDB exacte ;
- ECR immutable et scan on push ;
- DynamoDB SSE, PITR et partitionnement par `userId` ;
- logs sans JWT, prompt brut, secret, actorId brut ou sessionId brut.

## Tools V1

AgentCore Gateway expose un target Lambda réel :

```text
create_trip
get_trips
get_trip
update_trip
```

Les entrées sont validées : formats d’identifiants, tailles, dates ISO, ordre des dates et rejet des champs inconnus. Toutes les opérations DynamoDB sont contraintes à la partition `userId` injectée par Runtime.

## CI/CD

### Qualité automatique

```text
.github/workflows/test-application-quality.yml
```

- compilation Python 3.12 ;
- tests unitaires de la façade, du contrat Runtime et des tools ;
- frontend `npm ci`, lint et build.

### Infrastructure

```text
.github/workflows/test-terraform-stack.yml
```

- Gitleaks ;
- lockfile ;
- Terraform fmt/init/validate ;
- plan ;
- apply et destroy contrôlés.

### Déploiement applicatif

```text
.github/workflows/test-application-deploy.yml
```

Modes : `frontend-only`, `image-only`, `runtime-only`, `full`.

Le frontend reçoit :

```text
VITE_AGENT_INVOKE_URL=<API Gateway /agent/invoke>
```

L’output `agent_runtime_invoke_url` reste technique et ne doit jamais être injecté dans le navigateur.

## État de la V1

L’implémentation du code et de l’IaC V1 est présente sur la branche. La V1 ne doit être déclarée **validée** qu’après les preuves suivantes :

1. pipeline qualité verte ;
2. Terraform fmt/validate/plan vert et plan revu ;
3. déploiement `full` réussi ;
4. tests navigateur CORS/JWT ;
5. refus d’invocation Runtime directe ;
6. isolation Memory User A/User B ;
7. exécution end-to-end des quatre tools MCP ;
8. vérification des logs redacted et de la latence inférieure à 28 secondes.

## Documentation

- `docs/adr/ADR-0004-api-gateway-direct-agentcore-runtime-jwt.md` — historique, superseded ;
- `docs/adr/ADR-0005-lambda-security-facade-agentcore-runtime-iam.md` — décision active ;
- `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` ;
- `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` ;
- `docs/migration/REMEDIATION-Gateway-First-APIGW.md` ;
- `docs/runbooks/ci-cd-rationalisation-test.md`.

## Gouvernance

Toute modification du chemin d’ingress, de l’identité, du modèle, de Memory ou des tools doit être présentée avec ses tradeoffs, documentée dans un ADR et validée explicitement avant application.
