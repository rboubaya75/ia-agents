# Remédiation V1 — API Gateway devant AgentCore Runtime JWT

- **Statut :** plan approuvé, implémentation non commencée
- **Date :** 2026-07-12
- **Branche :** `migration/secure-agentcore-v1`
- **Référence :** ADR-0004

## 1. Objectif

Passer de l’état actuel :

```text
Browser -> AgentCore Runtime direct JWT
```

à la cible V1 :

```text
Browser
  -> Amazon API Gateway HTTP API
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

Le chemin tools reste :

```text
Runtime -> AgentCore Gateway MCP -> tools -> DynamoDB / APIs métier
```

Aucune réintroduction d’AgentCore Gateway comme intermédiaire d’ingress utilisateur.

## 2. État actuel vérifié

### Présent

- S3 privé + CloudFront ;
- Cognito ;
- API Gateway HTTP API et JWT authorizer ;
- Runtime JWT natif ;
- Authorization allowlist ;
- AgentCore Memory ;
- AgentCore Gateway MCP ;
- Claude Haiku 4.5 ;
- ECR immutable et scan on push ;
- DynamoDB SSE/PITR ;
- CI Terraform et application.

### Écarts

- API Gateway n’a pas de route agentique active ;
- frontend et pipeline utilisent l’URL Runtime directe ;
- CORS API Gateway ne contient pas le header de session Runtime ;
- pas de throttling/access logs finalisés ;
- auth MCP Terraform/code incohérente ;
- pas de target MCP validé ;
- IAM trop large ;
- tests P0 historiques désalignés ;
- noms `gateway_first` encore présents ;
- documentation ancienne Gateway-first remplacée par ADR-0004.

## 3. Phase 1 — Front-door API Gateway

### Terraform module

Fichiers :

```text
infra/modules/api_gateway_agent_ingress/main.tf
infra/modules/api_gateway_agent_ingress/variables.tf
infra/modules/api_gateway_agent_ingress/outputs.tf
infra/environments/test/api_gateway.tf
infra/environments/test/outputs.tf
```

Actions :

1. ajouter `runtime_direct_enabled` ;
2. ajouter `agentcore_runtime_invoke_url` ;
3. créer une intégration `HTTP_PROXY` directe vers Runtime ;
4. créer `POST /agent/invoke` avec JWT authorizer ;
5. conserver Gateway-first désactivé ;
6. conserver Lambda Facade désactivée ;
7. faire retourner `agent_invoke_url` lorsque le proxy Runtime direct est actif.

### CORS

Autoriser uniquement :

```text
Origin: domaine CloudFront test
Methods: OPTIONS, POST
Headers:
  authorization
  content-type
  x-amzn-bedrock-agentcore-runtime-session-id
  x-correlation-id
```

### Sécurité

- ne pas mapper ou réécrire `Authorization` ;
- ne pas fabriquer de header `x-amzn-*` ;
- conserver le JWT authorizer Runtime ;
- ajouter throttling ;
- ajouter access logs redacted.

### Gate de sortie phase 1

- `terraform fmt` ;
- `terraform validate` ;
- plan sans remplacement Runtime inattendu ;
- route `/agent/invoke` visible ;
- preflight CORS validé ;
- appel JWT valide atteint Runtime ;
- appel sans JWT rejeté.

## 4. Phase 2 — Frontend et pipeline

Fichiers :

```text
frontend/src/services/chatService.ts
frontend/.env.example
.github/workflows/test-application-deploy.yml
scripts/preflight_application_deploy.py
scripts/validate_gateway_first_contract.py
```

Actions :

1. introduire `VITE_AGENT_INVOKE_URL` ;
2. utiliser l’URL API Gateway comme nominale ;
3. conserver temporairement le fallback Runtime direct ;
4. générer l’environnement frontend depuis `agent_invoke_url` ;
5. renommer les contrôles `gateway_first` devenus obsolètes ;
6. valider que les headers Runtime restent envoyés ;
7. ajouter un smoke test navigateur/API Gateway.

Gate de sortie phase 2 :

- `npm ci` ;
- `npm run lint` ;
- `npm run build` ;
- frontend déployé ;
- Network tab montre API Gateway, pas l’URL Runtime directe ;
- CORS et JWT passent depuis CloudFront.

## 5. Phase 3 — Identité et tests contractuels

Actions :

- aligner les `sessionId` de test sur 33+ caractères ;
- rejeter explicitement tous les champs d’identité client-side ;
- décider la suppression du fallback `trustedIdentity` ;
- adapter le test contractuel au chemin API Gateway -> Runtime ;
- tester User A / User B ;
- vérifier les logs redacted.

Cas obligatoires :

- sans JWT ;
- JWT invalide ;
- mauvais client ;
- session trop courte ;
- `actorId` client ;
- `userId` client ;
- `tenantId` client ;
- `trustedIdentity` client ;
- `groups` client ;
- isolation Memory ;
- isolation DynamoDB.

## 6. Phase 4 — AgentCore Gateway MCP et tools

Décision préalable : choisir un contrat unique.

### Option recommandée

```text
Runtime IAM role -> SigV4 -> AgentCore Gateway MCP AWS_IAM
```

ou, si l’adapter Strands/MCP ne le permet pas proprement :

```text
Runtime -> OAuth client credentials -> AgentCore Gateway MCP
```

Dans les deux cas :

- secrets hors Git ;
- target explicite ;
- permissions minimales ;
- test de list tools ;
- test d’exécution ;
- `userId` injecté côté serveur ;
- refus cross-user.

Gate de sortie phase 4 :

```text
Runtime -> AgentCore Gateway MCP -> tool réel -> DynamoDB/API
```

fonctionne avec logs redacted.

## 7. Phase 5 — IAM et durcissement

Actions :

- remplacer `bedrock-agentcore:*` ;
- restreindre les inference profiles ;
- restreindre Memory et Gateway ;
- restreindre log groups ;
- restreindre Secrets Manager ;
- supprimer les permissions Gateway d’invocation Runtime devenues inutiles ;
- vérifier trust policies avec `SourceAccount` et `SourceArn` ;
- documenter chaque wildcard techniquement incompressible.

## 8. Phase 6 — Observabilité et exploitation

Ajouter :

- API Gateway access logs ;
- métriques 401/403/429/5xx ;
- alarmes Runtime 5xx ;
- alarmes Bedrock AccessDenied/ValidationException ;
- latence ;
- erreurs tools ;
- correlation ID non sensible.

Ne jamais logger :

- JWT ;
- Authorization ;
- prompt brut ;
- réponse brute si PII ;
- actorId brut ;
- sessionId brut ;
- secret.

## 9. Phase 7 — Nettoyage documentation et legacy

- renommer `gateway_first_ready` ;
- renommer `enforce_gateway_first` ;
- renommer `validate_gateway_first_contract.py` ;
- archiver les scripts P0 Gateway-first ;
- identifier clairement le module Lambda Facade comme legacy ;
- supprimer les commentaires qui décrivent une architecture inactive ;
- maintenir README, HLD, LLD et ADR alignés.

## 10. Critères de sortie V1

- frontend -> API Gateway -> Runtime JWT ;
- Runtime direct non nominal ;
- AgentCore Gateway uniquement MCP/tools ;
- CORS strict ;
- throttling et logs ;
- identité JWT et tests négatifs validés ;
- Claude Haiku 4.5 streaming/tools validé ;
- Memory isolée ;
- tool MCP réel validé ;
- IAM durci ;
- Terraform validate/plan passe ;
- frontend lint/build passe ;
- smoke test navigateur passe ;
- documentation alignée.

## 11. Gouvernance des changements

Chaque phase doit suivre :

1. plan présenté ;
2. fichiers proposés ;
3. validation explicite ;
4. modification ;
5. tests ;
6. résumé des changements et échecs ;
7. validation avant la phase suivante.
