# HLD — WildRydes Agentic AI Application Landing Zone

**Version :** 2.0 — Gateway-first avec Amazon API Gateway conservé  
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

Cette version corrige l’ambiguïté de la proposition Gateway-first : **Gateway-first ne signifie pas suppression d’Amazon API Gateway**.

La cible V1 corrigée est :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
  -> Amazon Bedrock AgentCore Gateway
  -> HTTP Target: Amazon Bedrock AgentCore Runtime
```

Puis, pour les tools :

```text
AgentCore Runtime / phase_4.py
  -> AgentCore Gateway MCP endpoint
  -> MCP Targets: Lambda / API Gateway REST API / OpenAPI tools
  -> DynamoDB Trips Table
```

Amazon API Gateway reste la frontière d’entrée applicative web : JWT Cognito, CORS, throttling, logs, custom domain futur et WAF futur. AgentCore Gateway devient la brique native de médiation agentique : HTTP target vers Runtime et MCP targets vers les outils métier.

La Lambda Agent Invocation Facade n’est plus une brique nominale. Elle devient une option de repli uniquement si un écart fonctionnel est démontré sur la transformation d’identité, l’audit, les quotas ou des règles d’autorisation très spécifiques.

Le projet reste une **application landing zone**, pas une platform landing zone. Les sujets AWS Organizations, Control Tower, SCP, hub-and-spoke réseau ou landing zone entreprise sont hors périmètre V1.

---

## 2. Décisions structurantes

| Sujet | Décision V1 corrigée |
|---|---|
| Environnement | `test` uniquement |
| Branche par défaut en phase test | `migration/secure-agentcore-v1` |
| Branche production future | `main` |
| Frontend delivery | Amazon CloudFront devant S3 privé |
| Ingress web externe | Amazon API Gateway HTTP API |
| Authentification web | Amazon Cognito JWT |
| Gateway agentique | Amazon Bedrock AgentCore Gateway |
| Invocation Runtime | API Gateway appelle AgentCore Gateway ; AgentCore Gateway route vers Runtime via HTTP Target |
| Runtime agent | AgentCore Runtime exécutant `phase_4.py` |
| Tools métier | AgentCore Gateway MCP Targets vers Lambda, API Gateway REST API ou OpenAPI tools |
| Identité runtime | `actorId` dérivé d’un Cognito `sub` validé |
| Lambda Facade | Retirée du chemin nominal ; fallback uniquement avec ADR explicite |
| IaC | Terraform natif |
| CI/CD | GitHub Actions avec OIDC |
| RAG | Future capability, désactivée par défaut |
| WAF | Hors V1, préparé pour V2 via API Gateway |
| Guardrails | Hors V1 par défaut |
| Production | V2 / phase ultérieure |

---

## 3. Clarification : deux gateways, deux responsabilités

| Brique | Rôle | Pourquoi elle reste utile |
|---|---|---|
| Amazon API Gateway | Ingress HTTP public pour le frontend | JWT web, CORS, throttling, custom domain futur, WAF futur, access logs, contrôle d’exposition Internet |
| Amazon Bedrock AgentCore Gateway | Gateway agentique managée pour Runtime, tools, agents et modèles | HTTP target vers Runtime, MCP targets, conversion API/OpenAPI/Lambda en tools, auth inbound/outbound, observabilité agentique |
| Lambda Facade | Façade applicative custom | Non nominale ; à garder seulement si une règle non couverte nativement est prouvée |

La confusion précédente venait du fait que la Lambda Facade avait été utilisée à la fois comme frontière d’identité et comme mécanisme d’invocation Runtime. Dans la cible corrigée, cette responsabilité est rebasculée vers la combinaison native : Amazon API Gateway pour l’ingress web, AgentCore Gateway pour la médiation agentique.

---

## 4. Architecture logique cible

### 4.1 Delivery du frontend statique

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

### 4.2 Ingress utilisateur vers l’agent

```text
React App loaded in Browser
  |
  | HTTPS + Cognito Access Token
  v
Amazon API Gateway HTTP API
  |
  | JWT Authorizer validates issuer, audience, expiry, scopes
  | CORS / throttling / access logs
  v
Amazon Bedrock AgentCore Gateway
  |
  | HTTP Target: AgentCore Runtime
  v
Amazon Bedrock AgentCore Runtime
  |
  | executes phase_4.py
  | orchestrates model and memory
  v
Amazon Bedrock Model + AgentCore Memory
```

### 4.3 Flux agent vers tools métier

```text
AgentCore Runtime / phase_4.py
  |
  | MCP client
  v
Amazon Bedrock AgentCore Gateway MCP endpoint
  |
  +--> MCP Target: Lambda Trip Tools
  |
  +--> MCP Target: API Gateway REST API + OpenAPI specification
  |
  +--> MCP Target: future enterprise APIs / Smithy / MCP servers
  |
  v
DynamoDB Trips Table, through tools only
```

Cette séparation évite l’ambiguïté entre :

- CloudFront, qui sert le frontend depuis S3 ;
- Amazon API Gateway, qui sert de point d’entrée applicatif web ;
- AgentCore Gateway, qui sert de médiation agentique native vers Runtime et tools.

---

## 5. Parcours d’exécution applicatif

1. L’utilisateur charge l’application via CloudFront.
2. CloudFront récupère les assets statiques depuis le bucket S3 privé.
3. L’utilisateur est invité dans Cognito.
4. L’utilisateur se connecte via le frontend React.
5. Le frontend récupère un token Cognito.
6. Le frontend appelle Amazon API Gateway avec le token.
7. API Gateway valide le JWT avec un authorizer Cognito/JWT.
8. API Gateway applique CORS, throttling, limites payload et logs d’accès redacted.
9. API Gateway transmet la requête vers AgentCore Gateway selon l’intégration retenue.
10. AgentCore Gateway applique son authorizer inbound et route vers l’HTTP Target Runtime.
11. AgentCore Runtime exécute `phase_4.py`.
12. Runtime vérifie ou reconstruit l’identité de confiance selon le contrat validé en P0.
13. L’agent utilise Memory pour les préférences utilisateur.
14. L’agent utilise AgentCore Gateway MCP pour appeler les tools métier.
15. Les tools lisent/écrivent dans DynamoDB.
16. La réponse est retournée au frontend via AgentCore Gateway puis API Gateway.

---

## 6. Modèle d’identité

La règle V1 est stricte :

```text
actorId = Cognito claims.sub
```

Le navigateur ne doit jamais fournir comme source de confiance :

- `actorId` ;
- `userId` ;
- `tenantId` ;
- `trustedIdentity` ;
- groupes ou rôles applicatifs.

Ces informations doivent être dérivées ou vérifiées côté serveur.

### 6.1 V1 B2C simple

```text
actorId = Cognito sub
DynamoDB PK = userId / actorId
Memory namespace = travel/{actorId}/preferences
```

### 6.2 V2 B2B / SaaS future

```text
tenantId = attribut Cognito ou groupe validé côté serveur
actorId  = Cognito sub
DynamoDB PK = tenantId#actorId
Memory namespace = travel/{tenantId}/{actorId}/preferences
```

### 6.3 Validation P0 obligatoire

Avant l’implémentation complète, un spike doit valider le contrat exact :

```text
Amazon API Gateway
  -> AgentCore Gateway
  -> AgentCore Runtime
  -> phase_4.py
```

Le spike doit prouver :

- JWT Cognito validé ;
- `actorId = claims.sub` dérivé ou vérifié dans le chemin de confiance ;
- rejet des champs `actorId`, `userId`, `tenantId`, `trustedIdentity` dans le body client ;
- Runtime refuse les payloads legacy ;
- Runtime n’utilise jamais `sessionId` comme identité ;
- tools reçoivent une identité validée ;
- isolation User A / User B.

---

## 7. Composants applicatifs

### 7.1 Frontend static delivery

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
- ne jamais exposer `VITE_AGENT_ARN`, Runtime ARN, AgentCore Gateway URL ou secret.

### 7.2 Amazon API Gateway

Rôle : point d’entrée applicatif externe pour les appels API du frontend.

Responsabilités :

- exposer `/agent/invoke` ;
- valider le JWT Cognito ;
- appliquer CORS limité au domaine CloudFront ;
- appliquer throttling et limites payload ;
- journaliser les accès sans données sensibles ;
- préparer WAF et custom domain en V2 ;
- transmettre la requête vers AgentCore Gateway.

### 7.3 AgentCore Gateway

Rôle : gateway agentique native.

Responsabilités :

- exposer un endpoint d’entrée vers l’HTTP Target Runtime ;
- exposer des MCP targets vers les tools métier ;
- gérer les credentials et authorizers des targets ;
- limiter les targets autorisés ;
- fournir une observabilité agentique ;
- convertir APIs, Lambda functions, OpenAPI specs ou services existants en tools MCP-compatible.

### 7.4 AgentCore Runtime

Rôle : exécution de l’agent.

Cible :

```text
phase_4.py
```

Responsabilités :

- orchestrer le modèle Bedrock ;
- utiliser AgentCore Memory ;
- utiliser AgentCore Gateway MCP pour les tools ;
- appliquer les règles prompt/tool ;
- ne pas faire confiance au payload utilisateur pour l’identité ;
- rejeter toute requête sans identité de confiance ;
- émettre logs et métriques redacted.

### 7.5 AgentCore Memory

Rôle : mémoire utilisateur contrôlée.

Namespace V1 :

```text
travel/{actorId}/preferences
```

La Memory stocke les préférences et éléments contextuels utilisateur. Elle ne remplace pas DynamoDB.

### 7.6 Lambda Trip Tools ou API métier existante

Rôle : opérations métier trips.

Tools cibles :

- `create_trip` ;
- `get_trips` ;
- `get_trip` ;
- `update_trip`.

Chaque tool doit recevoir l’identité injectée ou vérifiée côté serveur et ne doit pas accepter un `userId` arbitraire non validé.

### 7.7 DynamoDB Trips

Rôle : persistance transactionnelle.

Cible :

- table par environnement ;
- chiffrement activé ;
- PITR activé ;
- clés compatibles user isolation ;
- IAM limité aux actions nécessaires.

---

## 8. Sécurité

### 8.1 Principes

- least privilege IAM ;
- pas de `AdministratorAccess` ;
- pas de secret dans Git ;
- bucket S3 frontend privé ;
- accès au frontend via CloudFront ;
- API Gateway comme ingress web public ;
- AgentCore Gateway comme gateway agentique ;
- pas de JWT dans les logs ;
- pas de prompt brut dans les logs ;
- pas d’identité client-side ;
- OIDC GitHub limité à test ;
- séparation future test/prod.

### 8.2 Sécurité runtime

Le chemin de confiance devient :

```text
Cognito JWT
  -> API Gateway JWT Authorizer
  -> AgentCore Gateway authorizer / target context
  -> AgentCore Runtime
  -> phase_4.py
```

Le Runtime doit rejeter toute requête contenant des champs d’identité client-side non fiables.

---

## 9. Observabilité

V1 doit fournir :

- CloudFront metrics ;
- API Gateway access logs, 4xx/5xx, latency et throttling ;
- AgentCore Gateway target latency, tool count, auth failures et target errors ;
- Runtime logs et metrics ;
- Trip tools logs ;
- DynamoDB throttles ;
- dashboards test ;
- budget alarm ;
- correlationId ;
- hashedActorId ;
- hashedSessionId.

Logs interdits :

- JWT ;
- Authorization header ;
- prompt brut ;
- réponse brute avec PII ;
- secrets ;
- actorId brut ;
- sessionId brut ;
- email complet.

---

## 10. Performance et résilience

Risques principaux :

- invalidations CloudFront trop fréquentes ;
- mauvais cache headers frontend ;
- latence AgentCore Runtime ;
- timeout API Gateway ;
- latence AgentCore Gateway target ;
- appels tools longs ;
- erreurs modèle ;
- throttling Bedrock, Gateway, Lambda ou DynamoDB.

La suppression du chemin nominal Lambda Facade réduit un hop custom et le risque de cold start façade. La latence réelle doit toutefois être mesurée par des tests p50/p95/p99.

---

## 11. CI/CD

GitHub Actions gère :

- Terraform plan ;
- Terraform apply test ;
- build Lambda artifacts si tools Lambda ;
- build agent Docker image ;
- push image ECR ;
- création ou mise à jour AgentCore Gateway ;
- création ou mise à jour HTTP Target Runtime ;
- création ou mise à jour MCP Targets tools ;
- build frontend ;
- deploy frontend S3 ;
- CloudFront invalidation ;
- smoke tests ;
- negative security tests ;
- latency tests ;
- automated validation gates.

Le gate automatisé doit valider :

- API Gateway -> AgentCore Gateway ;
- AgentCore Gateway -> Runtime ;
- Runtime -> AgentCore Gateway MCP ;
- Gateway -> tools ;
- payload identité ;
- IAM minimal ;
- logs redacted ;
- timeouts ;
- erreurs.

---

## 12. Roadmap V2

V2 inclura :

- environnement production ;
- promotion test vers prod ;
- WAF ;
- Bedrock Guardrails ;
- custom domain ;
- ACM ;
- Route 53 ;
- quotas par utilisateur ;
- quotas par tenant ;
- streaming ou WebSocket si nécessaire ;
- portail admin/support ;
- runbooks production ;
- rollback avancé.

---

## 13. Critères d’acceptation HLD

Le HLD est accepté si :

- Amazon API Gateway reste explicitement dans le chemin utilisateur ;
- AgentCore Gateway est la gateway agentique centrale ;
- Lambda Facade n’est plus le chemin nominal ;
- le flux frontend `Browser -> CloudFront -> S3 privé` est explicite ;
- le flux API `Browser app -> API Gateway -> AgentCore Gateway -> Runtime` est explicite ;
- le flux tools `Runtime -> AgentCore Gateway MCP -> Lambda/API Gateway REST/OpenAPI tools` est explicite ;
- le périmètre test est explicite ;
- `main` est documentée comme future prod ;
- l’identity model est server-side ;
- Runtime cible `phase_4.py` est documenté ;
- Memory, Gateway, tools et DynamoDB sont distingués ;
- RAG est documenté comme future capability ;
- les exclusions V1 sont explicites ;
- la trajectoire production est séparée.

---

## 14. Roadmap

| Phase | Objectif |
|---|---|
| V1.0 test | Fondations, CI/CD test, Terraform skeleton, docs |
| V1.1 test | CloudFront/S3 frontend, Cognito, API Gateway web ingress |
| V1.2 test | AgentCore Gateway HTTP Target vers Runtime |
| V1.3 test | AgentCore Memory/Gateway MCP/Tools Terraform |
| V1.4 test | tests sécurité, observabilité, coût |
| V2 | production, multi-tenant, WAF/Guardrails selon besoin |
| V2+ | RAG actif après corpus validé |
