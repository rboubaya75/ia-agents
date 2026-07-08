# WildRydes — Secure AgentCore V1 Landing Zone

Ce dépôt porte la migration de WildRydes vers une **application landing zone AWS sécurisée** pour un agent IA basé sur **Amazon Bedrock AgentCore**.

La branche de travail par défaut pendant la phase de test est :

```text
migration/secure-agentcore-v1
```

La branche `main` est conservée pour la future phase production. La bascule vers `main` sera réalisée manuellement après validation client.

---

## 1. Objectif du projet

L’objectif est d’industrialiser l’ancien workshop WildRydes AgentCore vers une cible exploitable en environnement `test`, avec une trajectoire claire vers la production.

La cible V1 corrigée met en place :

- un frontend statique servi par **Amazon CloudFront** depuis un bucket **Amazon S3 privé** ;
- un point d’entrée applicatif web via **Amazon API Gateway HTTP API** ;
- une authentification web via **Amazon Cognito** ;
- **Amazon Bedrock AgentCore Gateway** comme couche agentique native ;
- un **AgentCore Gateway HTTP ingress** vers **AgentCore Runtime** ;
- un **AgentCore Gateway MCP tools** pour les tools appelés par le Runtime ;
- un Runtime AgentCore exécutant `phase_4.py` ;
- AgentCore Memory pour les préférences utilisateur ;
- des MCP targets vers les tools métier ;
- des Lambda tools ou APIs REST/OpenAPI pour la gestion des trips ;
- DynamoDB pour la persistance ;
- Terraform natif pour l’IaC AgentCore ;
- GitHub Actions avec OIDC pour la CI/CD test ;
- une base documentaire HLD, LLD, ADR, runbooks et spécifications modules.

> Décision structurante : **Gateway-first ne signifie pas suppression d’Amazon API Gateway**. Amazon API Gateway reste l’ingress web externe. AgentCore Gateway devient la médiation agentique native entre l’ingress, le Runtime et les tools.

---

## 2. Architecture cible V1 corrigée

La V1 distingue trois flux :

1. **Delivery du frontend statique** ;
2. **Ingress utilisateur vers l’agent** ;
3. **Flux agent vers tools métier**.

### 2.1 Delivery du frontend

```text
User Browser
  -> Amazon CloudFront
  -> Amazon S3 private bucket
  -> React / TypeScript / Vite static assets
```

### 2.2 Ingress utilisateur vers l’agent

```text
React App loaded in Browser
  -> Amazon API Gateway HTTP API
      - Cognito JWT Authorizer
      - CORS limité au domaine CloudFront
      - throttling et access logs
  -> Amazon Bedrock AgentCore Gateway ingress
      - HTTP Target: AgentCore Runtime
  -> Amazon Bedrock AgentCore Runtime
      - phase_4.py
      - Amazon Bedrock model
      - AgentCore Memory
```

Amazon API Gateway reste donc dans le chemin nominal. Il sert de frontière HTTP publique pour le frontend et prépare les besoins V2 : WAF, custom domain, quotas et observabilité d’ingress.

### 2.3 Flux agent vers tools métier

```text
AgentCore Runtime / phase_4.py
  -> AgentCore Gateway MCP tools endpoint
      -> MCP Target: Lambda Trip Tools
      -> MCP Target: API Gateway REST API + OpenAPI specification
      -> MCP Target: future enterprise APIs / Smithy / MCP servers
  -> DynamoDB Trips Table via tools only
```

AgentCore Gateway est la brique native qui expose les APIs, Lambda functions, OpenAPI specs et services existants comme tools compatibles MCP. La Lambda Facade n’est plus le chemin nominal.

---

## 3. Responsabilités des gateways

| Brique | Rôle | Statut V1 corrigé |
|---|---|---|
| Amazon API Gateway | Ingress web public pour le frontend : JWT Cognito, CORS, throttling, logs, futur WAF/custom domain | Conservé |
| AgentCore Gateway ingress | Gateway AgentCore sans `protocol_type`, utilisée pour HTTP Target vers Runtime | Central |
| AgentCore Gateway tools MCP | Gateway AgentCore `protocol_type = MCP`, utilisée par le Runtime pour les tools | Central |
| Lambda Agent Invocation Facade | Ancienne façade d’invocation Runtime | Retirée du chemin nominal ; fallback seulement si un gap est prouvé |

---

## 4. Modèle d’identité

Règle clé :

```text
actorId = Cognito JWT sub
```

Le navigateur ne doit jamais être source de vérité pour :

```text
actorId
userId
tenantId
trustedIdentity
groups
```

Le contrat exact **API Gateway -> AgentCore Gateway -> Runtime** doit être validé par un spike P0 avant l’ouverture production. Ce spike doit prouver que `actorId` est dérivé d’une identité Cognito validée, que les champs d’identité client-side sont rejetés, et que Runtime n’utilise jamais `sessionId` comme identité.

---

## 5. Documentation

| Document | Objectif |
|---|---|
| `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` | Architecture de haut niveau Gateway-first avec API Gateway conservé |
| `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` | Design détaillé technique Gateway-first avec API Gateway conservé |
| `docs/adr/ADR-0002-agentcore-gateway-first-with-api-gateway.md` | Décision d’architecture : conserver API Gateway et retirer la Lambda Facade du nominal |
| `docs/adr/ADR-0003-native-agentcore-terraform-provisioning.md` | Décision d’architecture : provisionner AgentCore avec Terraform natif |
| `docs/migration/REMEDIATION-Gateway-First-APIGW.md` | Plan de remédiation repo/code/pipelines |
| `docs/specifications/module-specifications-fr.md` | Spécifications modules à réaligner avec ADR-0002 et ADR-0003 |

---

## 6. Stratégie CI/CD cible

La pipeline applicative suit maintenant le parcours suivant :

```text
1. Lire les outputs Terraform de base
2. Build/push l’image AgentCore Runtime vers ECR
3. Relancer Terraform avec enable_agentcore_control_plane=true et agentcore_image_tag=<tag>
4. Terraform crée/met à jour AgentCore Memory, Runtime, Runtime Endpoint, Gateways et HTTP Target
5. Relire les outputs Terraform natifs
6. Exécuter le gate Gateway-first
7. Rebuilder et redéployer le frontend avec l’API Gateway réelle
8. Invalider CloudFront
```

L’ancien mécanisme `activate_facade` est supprimé du workflow nominal. Le script Runtime Boto3 historique est legacy ; le chemin cible est Terraform natif.

---

## 7. Points P0 avant ouverture production

Avant une ouverture au-delà du test, valider explicitement :

- l’intégration **API Gateway HTTP API -> AgentCore Gateway ingress -> Runtime** ;
- l’authorizer Cognito/JWT côté AgentCore Gateway ingress ;
- la propagation ou reconstruction de `actorId = Cognito sub` ;
- le contrat Runtime attendu par `phase_4.py` ;
- l’appel Runtime -> AgentCore Gateway MCP -> tool ;
- les MCP targets métiers réelles ;
- les tests négatifs d’identité ;
- l’absence de JWT, prompt brut, secret, actorId brut et sessionId brut dans les logs.
