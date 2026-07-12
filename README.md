# WildRydes — Secure AgentCore V1 Landing Zone

Ce dépôt porte la migration de WildRydes vers une application agentique sécurisée sur AWS, basée sur Amazon Bedrock AgentCore.

- **Branche par défaut et environnement de travail :** `migration/secure-agentcore-v1`
- **Périmètre :** environnement `test`
- **IaC :** Terraform
- **CI/CD :** GitHub Actions avec OIDC AWS
- **Runtime :** `deploy-agentcore/agents/phase_4.py`
- **Modèle courant :** `eu.anthropic.claude-haiku-4-5-20251001-v1:0`
- **RAG :** prévu ultérieurement, désactivé par défaut

## 1. Objectif V1

Industrialiser l’ancien workshop WildRydes avec :

- frontend React / TypeScript / Vite ;
- S3 privé et CloudFront ;
- Cognito pour l’authentification ;
- API Gateway comme front-door web ;
- AgentCore Runtime avec JWT natif ;
- AgentCore Memory ;
- AgentCore Gateway MCP pour les tools ;
- DynamoDB pour les trips ;
- image Runtime ECR `linux/arm64` ;
- Terraform et pipelines GitHub Actions.

## 2. État actuel de la branche

Le code actuellement présent met en œuvre :

```text
Browser / React App
  -> AgentCore Runtime direct HTTPS
      - Cognito access token Bearer
      - Runtime custom JWT authorizer
      - Authorization header allowlist
  -> Claude Haiku 4.5 EU
  -> AgentCore Memory
```

Le frontend utilise actuellement `VITE_AGENT_RUNTIME_INVOKE_URL` en priorité.

Amazon API Gateway existe toujours dans Terraform, avec un authorizer JWT Cognito et une configuration CORS, mais il n’expose plus de route agentique active car le mode Gateway-first est désactivé.

AgentCore Gateway existe actuellement comme Gateway MCP. Il n’est plus utilisé comme intermédiaire d’ingress utilisateur.

### Écarts connus dans l’état actuel

- le navigateur appelle encore directement AgentCore Runtime ;
- API Gateway n’est pas encore reconnecté au Runtime direct ;
- le CORS API Gateway ne contient pas encore le header de session Runtime ;
- la pipeline frontend injecte encore l’URL Runtime directe ;
- le code MCP attend des credentials OAuth alors que Terraform configure `GATEWAY_AUTH_MODE=aws_iam` ;
- aucun target MCP métier réel n’est encore validé end-to-end ;
- plusieurs permissions IAM sont encore larges ;
- certains noms de scripts, outputs et variables contiennent encore `gateway_first` ;
- les tests P0 historiques ne sont pas encore alignés avec le contrat Runtime actuel.

## 3. Cible V1 approuvée

La cible V1 est définie par ADR-0004 :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
      - Cognito JWT authorizer
      - CORS strict
      - throttling
      - access logs redacted
  -> HTTP proxy direct
  -> Amazon Bedrock AgentCore Runtime
      - custom JWT authorizer Cognito
      - Authorization allowlist
      - phase_4.py
  -> Amazon Bedrock Claude Haiku 4.5
  -> AgentCore Memory
```

Chemin tools :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP
  -> targets tools autorisés
  -> DynamoDB / APIs métier
```

### Responsabilités des gateways

| Brique | Rôle V1 |
|---|---|
| Amazon API Gateway | Front-door web : JWT, CORS, throttling, logs, URL stable, future protection edge |
| AgentCore Gateway MCP | Exposition et gouvernance des tools appelés par Runtime |
| AgentCore Gateway ingress | Non nominal ; abandonné pour l’ingress utilisateur |
| Lambda Agent Invocation Facade | Legacy/fallback uniquement, non utilisée dans le chemin nominal |

## 4. Modèle d’identité

Règle V1 :

```text
actorId = Cognito access token claim `sub`
```

Le navigateur ne doit jamais être source de confiance pour :

```text
actorId
userId
tenantId
trustedIdentity
groups
```

Le Runtime rejette les champs d’identité client-side et injecte l’identité serveur dans les appels tools.

## 5. Sécurité déjà en place

- S3 frontend privé avec Block Public Access ;
- CloudFront Origin Access Control ;
- HTTPS côté CloudFront ;
- versioning et chiffrement S3 ;
- Cognito en mode utilisateurs invités uniquement ;
- app client SPA sans secret ;
- ECR immutable avec scan on push et lifecycle policy ;
- DynamoDB chiffré avec PITR ;
- GitHub Actions avec OIDC AWS ;
- logs Runtime avec hashes d’acteur et de session ;
- rejet des champs d’identité fournis dans le body ;
- modèle Claude Haiku 4.5 validé avec `ConverseStream + toolConfig`.

## 6. Prochaines étapes V1

1. implémenter `API Gateway -> Runtime direct JWT` ;
2. corriger CORS avec `x-amzn-bedrock-agentcore-runtime-session-id` ;
3. faire utiliser `agent_invoke_url` par le frontend et la pipeline ;
4. ajouter throttling et access logs API Gateway ;
5. aligner l’authentification AgentCore Gateway MCP ;
6. créer et valider au moins un target tool réel ;
7. réduire les IAM wildcards ;
8. aligner les tests contractuels d’identité ;
9. exécuter Terraform validate/plan, build frontend et smoke tests navigateur ;
10. clôturer la V1 uniquement après validation CORS, JWT, Runtime, Memory et tools.

## 7. CI/CD

### Infrastructure

```text
.github/workflows/test-terraform-stack.yml
```

Responsabilités :

- secret scan ;
- lockfile check ;
- Terraform fmt/validate ;
- plan ;
- apply contrôlé ;
- destroy-plan et destroy avec confirmation.

### Application

```text
.github/workflows/test-application-deploy.yml
```

Modes :

- `frontend-only` ;
- `image-only` ;
- `runtime-only` ;
- `full`.

Le workflow doit être réaligné pour injecter l’URL API Gateway comme endpoint nominal frontend.

## 8. Documentation de référence

| Document | Rôle |
|---|---|
| `docs/adr/ADR-0002-agentcore-gateway-first-with-api-gateway.md` | Historique du design Gateway-first, désormais superseded |
| `docs/adr/ADR-0003-native-agentcore-terraform-provisioning.md` | Provisioning AgentCore natif Terraform |
| `docs/adr/ADR-0004-api-gateway-direct-agentcore-runtime-jwt.md` | Architecture V1 approuvée |
| `docs/hld/HLD-WildRydes-Agentic-AI-FR.md` | Architecture de haut niveau AS-IS et cible V1 |
| `docs/lld/LLD-WildRydes-Agentic-AI-FR.md` | Design détaillé et contrats techniques |
| `docs/migration/REMEDIATION-Gateway-First-APIGW.md` | Plan de remédiation V1 |
| `docs/runbooks/ci-cd-rationalisation-test.md` | Exploitation des workflows test |

## 9. Règle de gouvernance

Toute modification structurante du chemin d’ingress, de l’identité, du Runtime, des tools ou du modèle doit :

1. être décrite dans un ADR ou un amendement ;
2. être présentée avec ses tradeoffs ;
3. recevoir une validation explicite avant modification du code ou de Terraform ;
4. être suivie d’un plan, de tests et d’un résumé des fichiers changés.
