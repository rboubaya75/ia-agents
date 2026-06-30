# HLD — WildRydes Agentic AI Application Landing Zone

**Version :** 1.1 complète  
**Langue :** Français  
**Branche de test :** `migration/secure-agentcore-v1`  
**Branche future prod :** `main`  
**Périmètre V1 :** environnement `test` production-like  
**IaC cible :** Terraform  
**CI/CD cible :** GitHub Actions avec OIDC  
**Runtime cible :** `phase_4.py`  
**RAG :** future capability, non livré en V1

---

## 1. Résumé exécutif

WildRydes est une application IA agentique destinée à démontrer puis industrialiser un parcours agentique sécurisé sur AWS.

La cible V1 n’est pas une mise en production. Elle constitue un environnement `test` production-like permettant de valider :

- l’architecture applicative ;
- le delivery sécurisé du frontend via CloudFront et S3 privé ;
- l’identité utilisateur ;
- le modèle de sécurité ;
- l’invocation AgentCore Runtime ;
- l’intégration AgentCore Memory ;
- l’intégration AgentCore Gateway et tools ;
- la persistance DynamoDB ;
- l’observabilité ;
- les coûts ;
- la CI/CD avec GitHub Actions et OIDC ;
- la trajectoire future vers la production.

Le projet est une **application landing zone**, pas une plateforme landing zone. Les sujets AWS Organizations, Control Tower, SCP, hub-and-spoke réseau ou landing zone entreprise sont considérés comme dépendances externes ou hors périmètre V1.

---

## 2. Décisions structurantes

| Sujet | Décision V1 |
|---|---|
| Environnement | `test` uniquement |
| Branche par défaut en phase test | `migration/secure-agentcore-v1` |
| Branche production future | `main` |
| Frontend delivery | Amazon CloudFront devant S3 privé |
| Ingress API externe | Amazon API Gateway HTTP API |
| Authentification web | Amazon Cognito JWT |
| Invocation AgentCore | Lambda Agent Invocation Facade |
| Runtime agent | AgentCore Runtime exécutant `phase_4.py` |
| Identité runtime | `actorId` dérivé côté serveur depuis `claims.sub` |
| IaC | Terraform natif |
| CI/CD | GitHub Actions avec OIDC |
| RAG | Future capability, désactivée par défaut |
| WAF | Hors V1 |
| Guardrails | Hors V1 par défaut |
| Production | V2 / phase ultérieure |

---

## 3. Architecture logique cible

L’architecture V1 distingue deux flux complémentaires :

1. le **delivery du frontend statique** ;
2. le **flux applicatif agentique**.

### 3.1 Delivery du frontend statique

```text
User Browser
  |
  | HTTPS
  v
Amazon CloudFront
  |
  | Origin Access Control / private origin access
  v
Amazon S3 private bucket
  |
  v
React / TypeScript / Vite static assets
```

CloudFront est le point d’accès public du frontend. S3 héberge les assets statiques, mais le bucket doit rester privé. L’accès utilisateur au frontend doit passer par CloudFront.

### 3.2 Flux applicatif agentique

```text
React App loaded in Browser
  |
  | HTTPS + Cognito Access Token
  v
Amazon API Gateway HTTP API
  |
  | JWT Authorizer validates issuer, audience, expiry, scopes
  v
Lambda Agent Invocation Facade
  |
  | derives actorId = claims.sub
  | rejects actorId/userId/trustedIdentity from browser payload
  | invokes AgentCore Runtime using IAM/SigV4
  v
Amazon Bedrock AgentCore Runtime
  |
  | executes phase_4.py
  | receives trustedIdentity.actorId
  | orchestrates model, memory, tools
  v
Amazon Bedrock Model
  |
  +--> AgentCore Memory
  |
  +--> AgentCore Gateway MCP
            |
            v
        Lambda Trip Tools
            |
            v
        DynamoDB Trips Table
```

Cette séparation évite l’ambiguïté entre :

- CloudFront, qui sert le frontend depuis S3 ;
- API Gateway, qui sert de point d’entrée applicatif API ;
- AgentCore Gateway, qui reste une médiation interne MCP pour les tools.

---

## 4. Parcours d’exécution applicatif

1. L’utilisateur charge l’application via CloudFront.
2. CloudFront récupère les assets statiques depuis le bucket S3 privé.
3. L’utilisateur est invité dans Cognito.
4. L’utilisateur se connecte via le frontend React.
5. Le frontend récupère un token Cognito.
6. Le frontend appelle API Gateway avec le token.
7. API Gateway valide le JWT avec un authorizer Cognito/JWT.
8. API Gateway transmet les claims validés à la Lambda Facade.
9. La Lambda Facade extrait `claims.sub`.
10. La Lambda Facade construit `trustedIdentity.actorId`.
11. La Lambda Facade rejette tout champ d’identité fourni dans le body.
12. La Lambda Facade invoque AgentCore Runtime.
13. AgentCore Runtime exécute `phase_4.py`.
14. L’agent utilise Memory pour les préférences utilisateur.
15. L’agent utilise Gateway pour appeler les tools métier.
16. Les tools lisent/écrivent dans DynamoDB.
17. La réponse est retournée au frontend via la Facade.

---

## 5. Modèle d’identité

La règle V1 est stricte :

```text
actorId = Cognito claims.sub
```

Le navigateur ne doit jamais fournir :

- `actorId` ;
- `userId` ;
- `tenantId` ;
- `trustedIdentity` ;
- groupes ou rôles applicatifs.

Ces informations sont dérivées côté serveur.

### V1 B2C simple

```text
actorId = Cognito sub
DynamoDB PK = userId / actorId
Memory namespace = travel/{actorId}/preferences
```

### V2 B2B / SaaS future

```text
tenantId = attribut Cognito ou groupe validé côté serveur
actorId  = Cognito sub
DynamoDB PK = tenantId#actorId
Memory namespace = travel/{tenantId}/{actorId}/preferences
```

La V2 n’est pas livrée en V1 mais doit rester compatible avec le design.

---

## 6. Composants applicatifs

### 6.1 Frontend static delivery

Le frontend est une application React / TypeScript / Vite, compilée en assets statiques.

Flux cible :

```text
Browser -> CloudFront -> S3 private bucket -> static assets
```

Responsabilités :

- héberger les assets frontend dans S3 privé ;
- exposer l’application via CloudFront ;
- empêcher l’accès public direct au bucket S3 ;
- fournir les headers et comportements SPA nécessaires ;
- injecter `VITE_API_BASE_URL` lors du build ;
- ne jamais exposer `VITE_AGENT_ARN`.

### 6.2 Frontend runtime behavior

Cible V1 :

- utiliser `VITE_API_BASE_URL` ;
- ne plus exposer `VITE_AGENT_ARN` ;
- ne jamais transmettre `actorId` ;
- envoyer uniquement `prompt` et `sessionId` ;
- gérer les erreurs normalisées de la Facade.

### 6.3 API Gateway

Rôle : point d’entrée applicatif externe pour les appels API.

Responsabilités :

- exposer `/agent/invoke` ;
- valider le JWT Cognito ;
- transmettre les claims validés à Lambda ;
- appliquer CORS ;
- gérer throttling et limites payload ;
- journaliser les accès sans données sensibles.

### 6.4 Lambda Agent Invocation Facade

Rôle : frontière de sécurité entre le web et AgentCore Runtime.

Responsabilités :

- valider la requête ;
- extraire `claims.sub` ;
- construire `trustedIdentity` ;
- refuser les identités client-side ;
- appeler AgentCore Runtime avec IAM/SigV4 ;
- normaliser erreurs et réponses ;
- émettre logs redacted, métriques et traces.

### 6.5 AgentCore Runtime

Rôle : exécution de l’agent.

Cible :

```text
phase_4.py
```

Responsabilités :

- orchestrer le modèle Bedrock ;
- utiliser AgentCore Memory ;
- utiliser AgentCore Gateway ;
- appliquer les règles prompt/tool ;
- ne pas faire confiance au payload utilisateur pour l’identité ;
- émettre logs et métriques.

### 6.6 AgentCore Memory

Rôle : mémoire utilisateur contrôlée.

Namespace V1 :

```text
travel/{actorId}/preferences
```

La Memory stocke les préférences et éléments contextuels utilisateur. Elle ne remplace pas DynamoDB.

### 6.7 AgentCore Gateway

Rôle : médiation MCP vers les tools.

Responsabilités :

- exposer les tools métier à l’agent ;
- protéger les invocations ;
- limiter les cibles autorisées ;
- centraliser l’accès aux Lambda tools.

### 6.8 Lambda Trip Tools

Rôle : opérations métier trips.

Tools cibles :

- `create_trip` ;
- `get_trips` ;
- `get_trip` ;
- `update_trip`.

Chaque tool doit recevoir l’identité injectée côté serveur et ne doit pas accepter un `userId` arbitraire non validé.

### 6.9 DynamoDB Trips

Rôle : persistance transactionnelle.

Cible :

- table par environnement ;
- chiffrement activé ;
- PITR activé ;
- clés compatibles user isolation ;
- IAM limité aux actions nécessaires.

---

## 7. Sécurité

### 7.1 Principes

- least privilege IAM ;
- pas de `AdministratorAccess` ;
- pas de secret dans Git ;
- bucket S3 frontend privé ;
- accès au frontend via CloudFront ;
- pas de JWT dans les logs ;
- pas de prompt brut dans les logs ;
- pas d’identité client-side ;
- OIDC GitHub limité à test ;
- séparation future test/prod.

### 7.2 Sécurité CI/CD

Pendant la phase test :

- branche par défaut : `migration/secure-agentcore-v1` ;
- GitHub Environment : `test` ;
- reviewer obligatoire ;
- rôle AWS OIDC test-only ;
- `apply` manuel ;
- `destroy` manuel avec confirmation ;
- pas d’accès prod.

### 7.3 Sécurité runtime

La Lambda Facade constitue la frontière de confiance.

Elle doit rejeter toute requête contenant :

```text
actorId
userId
tenantId
trustedIdentity
```

si ces champs proviennent du navigateur.

---

## 8. Observabilité

Composants attendus :

- CloudFront standard logs ou métriques CloudFront selon besoin test ;
- S3 access posture validée ;
- CloudWatch Logs ;
- métriques Lambda ;
- métriques API Gateway ;
- métriques Runtime ;
- X-Ray ou tracing distribué si applicable ;
- dashboards test ;
- alarmes sur erreurs, latence et throttling.

Métriques minimales :

- `InvocationCount` ;
- `InvocationErrorCount` ;
- `LatencyP50/P95/P99` ;
- `UnauthorizedCount` ;
- `RejectedIdentityPayloadCount` ;
- `ToolInvocationCount` ;
- `ToolErrorCount` ;
- coût estimé par environnement.

---

## 9. Performance et résilience

Risques principaux :

- invalidations CloudFront trop fréquentes ;
- mauvais cache headers frontend ;
- cold start Lambda ;
- latence AgentCore Runtime ;
- timeout API Gateway ;
- appels tools longs ;
- erreurs modèle ;
- throttling Bedrock ou Lambda.

Mesures V1 :

- cache policy CloudFront adaptée aux assets statiques ;
- SPA fallback contrôlé ;
- timeouts cohérents entre API Gateway, Lambda et Runtime ;
- retries limités et contrôlés ;
- circuit breaker applicatif si nécessaire ;
- dashboards latence ;
- test p95/p99 ;
- provisioned concurrency optionnelle sur Lambda Facade si nécessaire.

---

## 10. Coûts

Principes :

- environnement test uniquement ;
- budgets et alertes ;
- logs avec rétention limitée ;
- CloudFront et S3 dimensionnés pour le test ;
- modèle Haiku-class par défaut si compatible ;
- escalade Sonnet uniquement si nécessaire ;
- RAG désactivé par défaut ;
- pas de WAF/Guardrails actifs en V1 sauf décision client.

---

## 11. RAG future capability

Le RAG est une capacité future distincte de :

- AgentCore Memory ;
- DynamoDB ;
- tools ;
- historique de conversation.

Architecture cible future :

```text
AgentCore Runtime
  -> RAG Retrieval Layer
  -> Amazon Bedrock Knowledge Bases
  -> S3 Document Repository
  -> Vector Store
```

La V1 doit rester compatible avec un module futur :

```hcl
enable_rag = false
```

Activation future conditionnée à :

- corpus documentaire validé ;
- classification documentaire ;
- règles d’accès ;
- tests de retrieval ;
- citations ;
- coût estimé ;
- sécurité prompt injection documentaire.

---

## 12. Modules industriels cibles

Les modules sont détaillés dans :

```text
docs/specifications/module-specifications-fr.md
```

Domaine cible :

```text
identity
frontend static delivery with CloudFront and S3
ingress
facade
agent packaging
agentcore runtime
agentcore memory
agentcore gateway
tools
data
secrets
iam
observability
cost
tests
rag future
```

---

## 13. Hors périmètre V1

- production go-live ;
- custom domain ;
- WAF actif ;
- Guardrails actifs ;
- RAG actif ;
- streaming/WebSocket ;
- admin portal ;
- multi-tenant B2B avancé ;
- promotion automatique vers `main`.

---

## 14. Critères d’acceptation HLD

Le HLD est accepté si :

- l’architecture V1 est claire ;
- le flux frontend `Browser -> CloudFront -> S3 privé` est explicite ;
- le flux API `Browser app -> API Gateway -> Lambda Facade -> AgentCore Runtime` est explicite ;
- le périmètre test est explicite ;
- `main` est documentée comme future prod ;
- l’identity model est server-side ;
- API Gateway et Lambda Facade sont retenus ;
- Runtime cible `phase_4.py` est documenté ;
- Memory, Gateway, tools et DynamoDB sont distingués ;
- RAG est documenté comme future capability ;
- les exclusions V1 sont explicites ;
- la trajectoire production est séparée.

---

## 15. Roadmap

| Phase | Objectif |
|---|---|
| V1.0 test | Fondations, CI/CD test, Terraform skeleton, docs |
| V1.1 test | CloudFront/S3 frontend, API Gateway, Lambda Facade, Runtime invocation |
| V1.2 test | AgentCore Memory/Gateway/Tools Terraform |
| V1.3 test | tests sécurité, observabilité, coût |
| V2 | production, multi-tenant, WAF/Guardrails selon besoin |
| V2+ | RAG actif après corpus validé |
