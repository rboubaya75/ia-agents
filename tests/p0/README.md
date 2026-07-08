# P0 contract tests

Ces tests valident le contrat d'identité de la route temporaire :

```text
POST /p0/agent/invoke
```

## Fichiers

- `identity-contract-cases.json` : cas positifs et négatifs.
- `../../scripts/p0_gateway_contract_check.py` : runner HTTP.

## Exécution

Depuis la racine du repo :

```bash
python3 scripts/p0_gateway_contract_check.py \
  --api-url "$P0_AGENT_INVOKE_URL" \
  --token "$COGNITO_ACCESS_TOKEN" \
  --cases tests/p0/identity-contract-cases.json
```

## Attendus

- Le cas nominal est accepté.
- Les payloads qui contiennent `actorId`, `userId`, `tenantId`, `trustedIdentity` ou `groups` sont rejetés.
- Le Runtime ne doit pas utiliser `sessionId` comme identité.
