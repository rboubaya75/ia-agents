# HLD — WildRydes Secure AgentCore V1

- **Version :** 4.0
- **Date :** 2026-07-13
- **Branche :** `migration/secure-agentcore-v1`
- **Environnement :** `test`
- **Décision active :** ADR-0005

## 1. Résumé exécutif

WildRydes est une application agentique de voyage sécurisée sur AWS. La V1 implémente une frontière de sécurité serveur entre le navigateur et Amazon Bedrock AgentCore.

```text
Browser / React
  -> CloudFront / S3 privé
  -> Cognito User Pool
  -> API Gateway HTTP API
  -> Lambda Agent Invocation Security Facade
  -> AgentCore Runtime IAM-only
  -> Bedrock Claude Haiku 4.5 EU
  -> AgentCore Memory
  -> AgentCore Gateway MCP AWS_IAM
  -> Lambda Trip Tools
  -> DynamoDB Trips
```

Le navigateur n’appelle jamais directement AgentCore Runtime. AgentCore Gateway n’est jamais utilisé comme ingress utilisateur.

## 2. Composants

| Composant | Responsabilité V1 |
|---|---|
| React / Vite | Interface et envoi de `prompt` + `sessionId` uniquement |
| S3 privé | Stockage des assets frontend |
| CloudFront | Distribution HTTPS, OAC et headers de sécurité |
| Cognito | Authentification et émission des access tokens |
| API Gateway HTTP API | JWT, CORS, throttling, access logs, URL stable |
| Lambda Security Facade | Validation du contrat, dérivation de l’identité, appel IAM vers Runtime |
| AgentCore Runtime | Orchestration Strands, modèle, Memory et tools |
| Bedrock | Claude Haiku 4.5 via profil d’inférence EU |
| AgentCore Memory | Préférences isolées par acteur |
| AgentCore Gateway MCP | Exposition gouvernée des tools |
| Lambda Trip Tools | CRUD Trips avec validation stricte |
| DynamoDB | Persistance transactionnelle par `userId` |
| ECR | Image Runtime ARM64 immutable et scannée |
| GitHub Actions | Qualité, Terraform et déploiement via OIDC |

## 3. Flux d’authentification

```text
1. Browser -> Cognito : authentification
2. Cognito -> Browser : access token
3. Browser -> API Gateway : Authorization Bearer + prompt + sessionId
4. API Gateway : validation JWT
5. Lambda Facade : vérification token_use, client_id, sub
6. Lambda Facade -> Runtime : IAM/SigV4 + trustedIdentity.actorId
7. Runtime -> Gateway MCP : IAM/SigV4
8. Runtime -> Trip tool : userId écrasé avec actorId authentifié
```

La règle d’identité est :

```text
actorId = Cognito access-token claim `sub`
```

## 4. Frontière de confiance

### Zone non fiable

Le navigateur peut fournir uniquement :

```text
prompt
sessionId
```

### Zone de confiance

La Lambda Facade fabrique :

```text
trustedIdentity.actorId
```

Runtime accepte cette valeur uniquement parce que sa resource policy autorise exclusivement le rôle IAM de la façade.

## 5. Sécurité

### Frontend

- S3 Block Public Access ;
- CloudFront Origin Access Control ;
- HTTPS redirect ;
- CSP ;
- HSTS ;
- `X-Frame-Options: DENY` ;
- `X-Content-Type-Options: nosniff` ;
- Referrer-Policy ;
- Permissions-Policy.

### Ingress

- JWT Cognito ;
- origine CORS CloudFront unique ;
- route unique `POST /agent/invoke` ;
- throttling test : 5 req/s, burst 10 ;
- logs d’accès sans token ni prompt.

### Façade

- Python 3.12 ARM64 ;
- payload allowlist ;
- prompt maximum 4 000 caractères ;
- session 33 à 128 caractères sûrs ;
- concurrence réservée à 5 ;
- timeout 28 secondes ;
- aucun retry Runtime caché ;
- logs avec hashes uniquement.

### Runtime et tools

- Runtime IAM-only ;
- resource policy limitée au rôle façade ;
- Gateway MCP IAM limité au rôle Runtime ;
- IAM least privilege sur modèle, Memory, Gateway, ECR et logs ;
- target MCP limité à la Lambda Trips ;
- Lambda Trips limitée à la table DynamoDB exacte ;
- `userId` toujours injecté côté Runtime.

## 6. Données

### DynamoDB

```text
PK = userId
SK = tripId
```

- SSE activé ;
- PITR activé ;
- `PAY_PER_REQUEST` ;
- conditions d’existence sur create/update ;
- aucun accès cross-user sans connaître la partition authentifiée.

### Memory

```text
travel/{actorId}/preferences
```

Memory ne remplace pas DynamoDB pour les données transactionnelles.

## 7. Disponibilité et limites

- Architecture serverless et managée ;
- aucune dépendance à une instance permanente ;
- Runtime et tools limités par throttling/concurrence ;
- chemin synchrone limité à moins de 28 secondes ;
- un dépassement régulier impose une architecture asynchrone hors V1.

## 8. Observabilité

Événements attendus :

```text
API Gateway access log
facade_invocation
facade_rejected
agent_invocation
memory_retrieved
memory_saved
gateway_tools_loaded
tool_identity_injection
trip_tool_invocation
```

Ne jamais journaliser : JWT, Authorization, prompt brut, réponse brute contenant des données personnelles, actorId brut, sessionId brut ou secret.

## 9. CI/CD

- `test-application-quality.yml` : Python, tests unitaires, frontend lint/build ;
- `test-terraform-stack.yml` : secret scan, fmt, validate, plan, apply/destroy contrôlés ;
- `test-application-deploy.yml` : image, Runtime, façade, frontend et contrat V1.

## 10. Statut

L’architecture et l’IaC V1 sont implémentées. La validation finale nécessite encore les preuves d’exécution : pipelines vertes, plan revu, apply, CORS/JWT navigateur, isolation Memory, refus Runtime direct et tools MCP end-to-end.

## 11. Hors périmètre

- RAG applicatif complet ;
- production ;
- multi-région applicatif ;
- WAF avancé/custom domain ;
- PrivateLink/ALB ;
- traitements asynchrones ;
- AgentCore Harness.
