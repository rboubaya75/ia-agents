# P0 — Commandes d'exécution

## Objectif

Activer une route temporaire isolée :

```text
POST /p0/agent/invoke
```

Cette route pointe vers l'URL AgentCore Gateway fournie via Terraform :

```text
p0_agentcore_gateway_url
```

La route nominale reste inchangée :

```text
POST /agent/invoke -> Lambda Facade -> Runtime
```

## 1. Préparer la stack

```bash
cd infra/environments/test
terraform init
terraform validate
```

## 2. Plan sans activer la route P0

```bash
terraform plan
```

La variable `p0_agentcore_gateway_url` est vide par défaut. Dans ce cas, la route `/p0/agent/invoke` n'est pas créée.

## 3. Activer la route P0

Quand l'URL AgentCore Gateway est disponible :

```bash
terraform plan \
  -var='p0_agentcore_gateway_url=https://<agentcore-gateway-invoke-url>' \
  -out=tfplan-p0-gateway
```

Puis :

```bash
terraform apply tfplan-p0-gateway
```

## 4. Récupérer l'URL de test

```bash
terraform output -raw p0_agent_invoke_url
```

Exporter :

```bash
export P0_AGENT_INVOKE_URL="$(terraform output -raw p0_agent_invoke_url)"
```

## 5. Lancer les tests contractuels

```bash
python3 ../../scripts/p0_gateway_contract_check.py \
  --api-url "$P0_AGENT_INVOKE_URL" \
  --token "$COGNITO_ACCESS_TOKEN" \
  --cases ../../tests/p0/identity-contract-cases.json
```

Si la commande est lancée depuis la racine du repo :

```bash
python3 scripts/p0_gateway_contract_check.py \
  --api-url "$P0_AGENT_INVOKE_URL" \
  --token "$COGNITO_ACCESS_TOKEN" \
  --cases tests/p0/identity-contract-cases.json
```

## 6. Critère de succès immédiat

- Le cas positif retourne 2xx.
- Les cas avec `actorId`, `userId`, `tenantId`, `trustedIdentity` ou `groups` retournent 400 ou 403.
- Les logs ne contiennent pas le JWT, le header Authorization, le prompt brut, `actorId` brut ou `sessionId` brut.

## 7. Rollback P0

Pour désactiver la route P0 :

```bash
terraform apply -var='p0_agentcore_gateway_url='
```

La route legacy `/agent/invoke` reste intacte pendant tout le spike.
