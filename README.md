# WildRydes — Secure AgentCore V1 Landing Zone

- **Branche et environnement :** `migration/secure-agentcore-v1` / `test`
- **IaC :** Terraform
- **CI/CD :** GitHub Actions avec OIDC AWS
- **Runtime :** Python 3.12, `deploy-agentcore/agents/phase_4_robust.py`
- **Modèle :** `eu.anthropic.claude-haiku-4-5-20251001-v1:0`
- **RAG :** hors V1, désactivé par défaut

## Architecture V1 implémentée

```text
Browser / React
  -> CloudFront / S3 privé
  -> Cognito User Pool
       - access token résolu avant chaque appel
       - un seul renouvellement/retry sur HTTP 401
  -> API Gateway HTTP API
       - Cognito JWT authorizer
       - CORS limité au domaine CloudFront
       - throttling et access logs
  -> Lambda Agent Invocation Security Facade
       - payload strict prompt + sessionId + operationId
       - actorId = claims.sub
       - requestId et deadlineEpochMs produits côté serveur
       - rejet de toute identité ou configuration client arbitraire
  -> AgentCore Runtime IAM-only
       - trustedIdentity produite par la façade
       - contexte d'opération injecté dans les tools
       - client MCP initialisé à la première invocation et reconnecté une seule fois
       - Claude Haiku 4.5 EU
       - AgentCore Memory
       - tools Strands
  -> AgentCore Gateway MCP AWS_IAM
  -> Lambda Trip Tools
       - deadline vérifiée avant accès DynamoDB
       - create/update idempotents
  -> DynamoDB Trips
```

Le navigateur ne connaît et n’utilise jamais l’URL technique AgentCore Runtime.

## Contrat d’identité et d’opération

La seule source de confiance pour l’identité est :

```text
actorId = Cognito access-token claim `sub`
```

Le frontend envoie uniquement :

```json
{
  "prompt": "Planifie un voyage à Tokyo",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000",
  "operationId": "76e6f404-49de-4dc4-9c60-f2c25a0de91f"
}
```

`operationId` est créé une fois par message. Il reste identique pendant l’unique retry d’authentification afin qu’une mutation déjà exécutée ne soit pas dupliquée.

La façade rejette notamment :

```text
actorId
userId
tenantId
trustedIdentity
requestId
deadlineEpochMs
groups
modelOverride
systemPrompt
toolName
```

Elle construit ensuite :

```text
trustedIdentity.actorId
requestId
deadlineEpochMs
```

Runtime écrase toujours `userId`, `operationId`, `requestId` et `deadlineEpochMs` avant un appel aux tools Trips. `operationId` n’est injecté que dans les tools de mutation.

## Contrôles de sécurité et de résilience

- S3 Block Public Access et CloudFront OAC ;
- HTTPS et headers CloudFront : CSP, HSTS, anti-framing, `nosniff`, Referrer-Policy et Permissions-Policy ;
- Cognito access token vérifié par API Gateway puis contrôlé par la façade (`token_use`, `client_id`, `sub`) ;
- access token récupéré auprès du SDK Cognito avant chaque appel applicatif ;
- façade Lambda Python 3.12 ARM64, concurrence réservée et timeout inférieur à API Gateway ;
- deadline serveur propagée jusqu’à la Lambda Trip Tools ;
- Runtime IAM-only avec resource policy limitée au rôle de la façade ;
- Gateway MCP IAM avec resource policy limitée au rôle Runtime ;
- démarrage HTTP indépendant du Gateway, initialisation MCP lazy, fermeture au shutdown et reconnexion bornée à une tentative ;
- retry MCP utilisant le même `operationId` ;
- IAM Runtime limité au modèle, à Memory, au Gateway, à ECR et aux logs nécessaires ;
- Lambda Trip Tools limitée à la table DynamoDB exacte ;
- créations déterministes par `userId + operationId` et mises à jour rejouables ;
- ECR immutable et scan on push ;
- DynamoDB SSE, PITR et partitionnement par `userId` ;
- logs corrélés par `requestId` et identifiants sensibles hashés ;
- contenu Memory présenté au modèle comme donnée non fiable, jamais comme instruction.

## Tools V1

AgentCore Gateway expose un target Lambda réel :

```text
create_trip
get_trips
get_trip
update_trip
```

Les entrées sont validées : formats d’identifiants, tailles, dates ISO, ordre des dates, deadline et rejet des champs inconnus. Toutes les opérations DynamoDB sont contraintes à la partition `userId` injectée par Runtime.

`create_trip` et `update_trip` nécessitent une confirmation explicite dans le contrat agent. Elles utilisent `operationId` pour retourner le résultat d’une opération déjà terminée plutôt que répéter son effet de bord. La réutilisation d’un même `operationId` avec un payload différent est rejetée.

## CI/CD

### Qualité automatique

```text
.github/workflows/test-application-quality.yml
```

- compilation Python 3.12 ;
- tests unitaires de la façade, du Runtime, du lifecycle MCP et des tools ;
- audit des dépendances Python ;
- frontend `npm ci`, audit, lint et build.

### Qualité industrielle

```text
.github/workflows/test-industrial-quality.yml
```

- fault injection sur les pannes MCP avant et après mutation ;
- vérification de la reconnexion unique et du budget de deadline ;
- initialisation MCP concurrente ;
- contrats IAM Runtime, Gateway, façade et Trip Tools ;
- contrôles de redaction et de corrélation des événements ;
- chaîne de timeouts frontend, API Gateway, façade, Runtime et Lambda ;
- artefact JSON traçable par identifiant de risque, conservé 90 jours.

Le référentiel complet se trouve dans `tests/README.md`.

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
4. tests navigateur CORS/JWT et renouvellement du token ;
5. refus d’invocation Runtime directe ;
6. isolation Memory User A/User B ;
7. exécution end-to-end des quatre tools MCP ;
8. création et mise à jour rejouées avec le même `operationId` sans doublon ;
9. reconnexion MCP après rupture de transport ;
10. vérification des logs redacted, de la corrélation et de la latence inférieure à 28 secondes.

## Documentation

- `tests/README.md` — stratégie, conventions et matrice des tests industriels ;
- `docs/adr/ADR-0004-api-gateway-direct-agentcore-runtime-jwt.md` — historique, superseded ;
- `docs/adr/ADR-0005-lambda-security-facade-agentcore-runtime-iam.md` — décision active ;
- `docs/adr/ADR-0006-idempotency-deadline-mcp-lifecycle.md` — décision active ;
- `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` ;
- `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` ;
- `docs/migration/REMEDIATION-Gateway-First-APIGW.md` ;
- `docs/runbooks/ci-cd-rationalisation-test.md` ;
- `docs/validation/V1-MEMORY-SECURITY-SUMMARY-FR.md` — synthèse entretien et onboarding ;
- `docs/validation/V1-MEMORY-SECURITY-TESTS-FR.md` — annexe des protocoles, statuts et preuves.

## Gouvernance

Toute modification du chemin d’ingress, de l’identité, du modèle, de Memory ou des tools doit être présentée avec ses tradeoffs, documentée dans un ADR et validée explicitement avant application.
