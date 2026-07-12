# P0 — Commandes d’exécution Gateway-first

- **Statut :** historique — ne pas utiliser pour la cible V1
- **Résultat du spike :** NO-GO pour `API Gateway -> AgentCore Gateway ingress -> Runtime`
- **Architecture active cible :** ADR-0004

## 1. Avertissement

Les commandes de ce document servaient à activer une route temporaire :

```text
POST /p0/agent/invoke
```

vers AgentCore Gateway ingress.

Ce chemin n’est plus retenu pour l’ingress utilisateur et ne doit pas être réactivé comme solution nominale.

## 2. Cible V1

```text
Browser
  -> API Gateway HTTP API
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

Tools :

```text
Runtime -> AgentCore Gateway MCP -> tools
```

## 3. Pourquoi les anciennes commandes sont obsolètes

- `p0_agentcore_gateway_url` ne représente plus la cible d’ingress ;
- la route P0 testait un contrat d’identité qui a échoué ;
- les tests associés utilisent des sessions qui ne respectent pas toujours la contrainte 33+ caractères ;
- le workflow et les outputs actuels ont évolué vers Runtime JWT direct ;
- la prochaine remédiation reconnectera API Gateway directement au Runtime.

## 4. Commandes de validation actuelles

### Terraform

```bash
terraform -chdir=infra/environments/test fmt -check -recursive
terraform -chdir=infra/environments/test init -backend=false
terraform -chdir=infra/environments/test validate
```

### Modèle Bedrock

Le modèle validé est :

```text
eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

### Runtime direct actuel — diagnostic uniquement

L’URL technique est disponible via :

```bash
terraform -chdir=infra/environments/test output -raw agent_runtime_invoke_url
```

Cette URL sert actuellement au frontend, mais elle deviendra un fallback après la remédiation API Gateway.

## 5. Validation après remédiation ADR-0004

Récupérer :

```bash
export AGENT_INVOKE_URL="$(terraform -chdir=infra/environments/test output -raw agent_invoke_url)"
```

Tester CORS :

```bash
curl -i -X OPTIONS "$AGENT_INVOKE_URL" \
  -H "Origin: https://<cloudfront-domain>" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-amzn-bedrock-agentcore-runtime-session-id"
```

Tester l’invocation :

```bash
curl -i -X POST "$AGENT_INVOKE_URL" \
  -H "Authorization: Bearer $COGNITO_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"prompt":"Plan a short trip to Paris.","sessionId":"550e8400-e29b-41d4-a716-446655440000"}'
```

## 6. Tests contractuels à réécrire

Le futur test doit cibler :

```text
API Gateway -> AgentCore Runtime JWT
```

et vérifier :

- JWT requis ;
- session 33+ caractères ;
- rejet `actorId` ;
- rejet `userId` ;
- rejet `tenantId` ;
- rejet `trustedIdentity` après suppression du fallback legacy ;
- rejet `groups` ;
- isolation User A / User B ;
- logs redacted.

## 7. Références

- `docs/p0/P0-AgentCore-Gateway-Spike.md` ;
- `docs/adr/ADR-0004-api-gateway-direct-agentcore-runtime-jwt.md` ;
- `docs/migration/REMEDIATION-Gateway-First-APIGW.md`.
