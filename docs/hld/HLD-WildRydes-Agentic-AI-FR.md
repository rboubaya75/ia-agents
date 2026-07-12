# HLD — WildRydes Agentic AI Application Landing Zone

- **Version :** 3.0
- **Date :** 2026-07-12
- **Branche par défaut :** `migration/secure-agentcore-v1`
- **Périmètre :** environnement `test`
- **IaC :** Terraform
- **CI/CD :** GitHub Actions avec OIDC AWS
- **Runtime :** `phase_4.py`
- **Modèle :** `eu.anthropic.claude-haiku-4-5-20251001-v1:0`
- **RAG :** hors V1, désactivé par défaut

## 1. Résumé exécutif

WildRydes est une application agentique de voyage déployée sur AWS. La V1 vise un environnement `test` sécurisé, reproductible et observable.

La documentation distingue volontairement :

1. **l’état actuel de la branche** ;
2. **la cible V1 approuvée** ;
3. **les écarts à fermer avant clôture V1**.

La cible V1 approuvée est :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
  -> HTTP proxy direct
  -> Amazon Bedrock AgentCore Runtime JWT
  -> Amazon Bedrock Claude Haiku 4.5
  -> AgentCore Memory
```

Le chemin tools est indépendant :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP
  -> targets tools autorisés
  -> DynamoDB / APIs métier
```

AgentCore Gateway n’est plus utilisé comme intermédiaire d’ingress utilisateur.

## 2. État actuel AS-IS

### 2.1 Delivery frontend

```text
Browser
  -> CloudFront
  -> S3 privé
  -> React / TypeScript / Vite
```

Le bucket S3 est privé, versionné, chiffré et accessible via CloudFront Origin Access Control.

### 2.2 Authentification

```text
Browser
  -> Cognito User Pool
  -> Cognito access token
```

Le User Pool fonctionne en mode utilisateurs invités uniquement. L’app client SPA n’a pas de secret et utilise SRP.

### 2.3 Ingress agent actuel

```text
Browser
  -> AgentCore Runtime direct HTTPS
      - Authorization: Bearer <access token>
      - X-Amzn-Bedrock-AgentCore-Runtime-Session-Id
  -> Runtime custom JWT authorizer
```

Le frontend privilégie actuellement l’URL directe Runtime.

Amazon API Gateway existe dans Terraform, mais aucune route agentique n’est active :

- `gateway_first_enabled = false` ;
- `agentcore_gateway_url = ""` ;
- `agentcore_runtime_target_name = ""` ;
- la Lambda Facade est désactivée.

### 2.4 Runtime

AgentCore Runtime :

- exécute `phase_4.py` ;
- valide le JWT Cognito nativement ;
- allowliste `Authorization` ;
- rejette les champs d’identité client-side ;
- dérive `actorId` depuis les claims JWT ;
- utilise AgentCore Memory ;
- construit un agent Strands avec Bedrock `ConverseStream` ;
- utilise Claude Haiku 4.5 EU ;
- fournit au moins le tool local `web_search`.

### 2.5 Tools

Une Gateway AgentCore MCP est créée par Terraform, mais le chemin tools n’est pas encore validé end-to-end.

Écart actuel :

- Terraform annonce `GATEWAY_AUTH_MODE=aws_iam` ;
- `phase_4.py` exige encore `CLIENT_ID`, `CLIENT_SECRET`, `TOKEN_URL` et `SCOPE_STRING` pour initialiser MCP ;
- en leur absence, le Runtime journalise `gateway_tools_not_configured`.

### 2.6 Données

DynamoDB Trips utilise :

```text
PK = userId
SK = tripId
```

La table est chiffrée et PITR est activé.

## 3. Cible V1 TO-BE

### 3.1 Architecture logique

```text
User Browser
  |
  +--> Cognito User Pool
  |      -> access token JWT
  |
  +--> CloudFront
  |      -> S3 private frontend bucket
  |
  +--> API Gateway HTTP API
          - Cognito JWT authorizer
          - CORS strict CloudFront
          - throttling
          - access logs redacted
          |
          v
      HTTP proxy direct
          |
          v
      AgentCore Runtime
          - custom JWT authorizer
          - Authorization allowlist
          - phase_4.py
          |
          +--> Claude Haiku 4.5 via Bedrock
          +--> AgentCore Memory
          +--> AgentCore Gateway MCP
                    -> tools autorisés
                    -> DynamoDB / APIs métier
```

### 3.2 Responsabilités

| Composant | Responsabilité V1 |
|---|---|
| CloudFront | Distribution HTTPS du frontend statique |
| S3 | Stockage privé des assets |
| Cognito | Authentification utilisateurs et émission des tokens |
| API Gateway HTTP API | Front-door : JWT, CORS, throttling, logs, URL stable |
| AgentCore Runtime | Validation JWT finale et exécution agentique |
| Bedrock | Exécution du modèle Claude Haiku 4.5 |
| AgentCore Memory | Mémoire utilisateur isolée |
| AgentCore Gateway MCP | Gouvernance et exposition des tools |
| DynamoDB | Persistance transactionnelle trips |
| ECR | Images Runtime immuables et scannées |
| GitHub Actions | Déploiements test via OIDC AWS |

## 4. Décisions d’architecture

### 4.1 API Gateway reste le front-door

L’abandon d’AgentCore Gateway comme intermédiaire ne justifie pas l’abandon d’Amazon API Gateway.

API Gateway est conservé pour :

- JWT Cognito en première barrière ;
- CORS centralisé ;
- throttling ;
- access logs ;
- URL applicative stable ;
- future protection CloudFront/WAF/custom domain ;
- découplage du frontend et de l’URL Runtime.

### 4.2 Runtime conserve son authorizer JWT

La double validation est volontaire :

```text
API Gateway JWT authorizer
+
AgentCore Runtime JWT authorizer
```

Elle évite qu’une erreur de proxy ne devienne un bypass d’identité.

### 4.3 AgentCore Gateway est réservé aux tools

Le rôle nominal d’AgentCore Gateway en V1 est :

```text
Runtime -> Gateway MCP -> tools
```

Il ne sert plus de proxy d’ingress utilisateur.

### 4.4 Lambda Facade

La Lambda Agent Invocation Facade reste legacy/fallback uniquement. Elle ne doit pas être activée sans nouvel ADR.

### 4.5 Modèle Bedrock

Le modèle retenu est :

```text
eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

Il a été validé dans le compte AWS avec :

```text
ConverseStream + toolConfig
```

Les modèles testés et écartés :

- Claude 3 Haiku legacy : accès refusé car modèle legacy ;
- Pixtral Large : ne supporte pas tool use en streaming ;
- ancien profile US : invalide dans `eu-west-3`.

## 5. Modèle d’identité

Règle V1 :

```text
actorId = Cognito access token claim `sub`
```

Le client ne doit pas imposer :

- `actorId` ;
- `userId` ;
- `tenantId` ;
- `trustedIdentity` ;
- `groups`.

Le Runtime doit :

1. refuser les champs d’identité du body ;
2. extraire l’identité du contexte JWT validé ;
3. injecter `userId = actorId` dans les appels tools ;
4. isoler Memory par `travel/{actorId}/preferences` ;
5. ne jamais utiliser `sessionId` comme identité.

## 6. Sécurité

### 6.1 Contrôles déjà présents

- S3 Block Public Access ;
- CloudFront OAC ;
- HTTPS ;
- S3 versioning et chiffrement ;
- Cognito invité uniquement ;
- app client sans secret ;
- ECR immutable et scan on push ;
- DynamoDB SSE et PITR ;
- logs Runtime avec hashes ;
- rejet des identités client-side ;
- GitHub Actions OIDC.

### 6.2 Contrôles à terminer en V1

- API Gateway proxy direct vers Runtime ;
- CORS avec le header de session Runtime ;
- throttling route `/agent/invoke` ;
- access logs API Gateway redacted ;
- réduction des IAM wildcards ;
- alignement auth MCP ;
- target tool réel ;
- tests d’isolation User A / User B ;
- suppression du fallback `trustedIdentity` si aucun usage legacy approuvé ;
- validation que les prompts et tokens ne sont jamais loggés.

### 6.3 Network mode

Le Runtime est actuellement en `network_mode = PUBLIC` pour permettre l’invocation JWT HTTPS.

Le passage à un mode privé, ALB ou PrivateLink n’est pas décidé en V1. Toute évolution doit être vérifiée contre les capacités AgentCore réelles et faire l’objet d’un ADR séparé.

## 7. Fiabilité et données

- DynamoDB est en `PAY_PER_REQUEST` ;
- PITR est activé ;
- la clé de partition permet l’isolation par utilisateur ;
- ECR conserve un historique limité via lifecycle policy ;
- le frontend S3 est versionné ;
- AgentCore Memory ne remplace pas DynamoDB pour les données transactionnelles.

## 8. CI/CD

### Infrastructure

`test-terraform-stack.yml` :

- secret scan ;
- lockfile check ;
- fmt/validate ;
- plan ;
- apply manuel ;
- destroy contrôlé.

### Application

`test-application-deploy.yml` :

- build image `linux/arm64` ;
- push ECR ;
- apply control plane AgentCore ;
- génération environnement frontend ;
- build frontend ;
- publication S3 ;
- invalidation CloudFront.

Écart actuel : le workflow injecte encore l’URL Runtime directe. Il doit être réaligné sur l’URL API Gateway.

## 9. Critères de sortie V1

La V1 est considérée terminée lorsque :

- API Gateway est le seul endpoint agentique nominal utilisé par le frontend ;
- Runtime conserve la validation JWT ;
- CORS navigateur est validé ;
- JWT invalide et identité client-side sont rejetés ;
- Claude Haiku 4.5 répond en streaming avec tools ;
- Memory est isolée par utilisateur ;
- un tool MCP réel fonctionne ;
- IAM est réduit au nécessaire ;
- Terraform validate/plan passe ;
- frontend lint/build passe ;
- smoke test navigateur passe ;
- logs et alarmes minimales sont présents.

## 10. Hors périmètre V1

- RAG complet ;
- OpenSearch Serverless ;
- multi-région ;
- production ;
- ALB/PrivateLink ;
- WAF avancé ;
- architecture B2B multi-tenant.

## 11. Références

- ADR-0002 — historique Gateway-first, superseded ;
- ADR-0003 — provisioning AgentCore natif Terraform ;
- ADR-0004 — API Gateway devant AgentCore Runtime JWT ;
- LLD WildRydes Agentic AI ;
- plan de remédiation V1.
