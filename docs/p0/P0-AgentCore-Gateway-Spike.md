# P0 — Spike API Gateway -> AgentCore Gateway -> Runtime

- **Statut :** terminé — NO-GO pour l’ingress utilisateur
- **Résultat repris par :** ADR-0004
- **Valeur historique :** conservation des constats et leçons du spike

## 1. Hypothèse testée

Remplacer le chemin legacy :

```text
API Gateway -> Lambda Facade -> AgentCore Runtime
```

par :

```text
API Gateway -> AgentCore Gateway ingress -> HTTP Target Runtime
```

avec la contrainte :

```text
actorId = Cognito sub
```

sans accepter d’identité fournie par le navigateur.

## 2. Résultat

Le chaînage Gateway-first a permis de valider la création des briques AgentCore, mais n’a pas satisfait le contrat d’identité Runtime.

AgentCore Gateway validait l’identité inbound puis invoquait Runtime avec son rôle IAM. Le Runtime ne recevait pas l’identité Cognito utilisateur dans le format attendu par `phase_4.py`.

Symptômes observés :

```text
Authenticated actor identity is unavailable from Gateway-first context
trustedIdentity.actorId is required from the server-side facade
```

## 3. Décision

### NO-GO

```text
API Gateway -> AgentCore Gateway ingress -> Runtime
```

n’est pas retenu pour l’ingress utilisateur V1.

### GO

```text
API Gateway
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

est la cible V1 approuvée.

### Conservé

```text
Runtime -> AgentCore Gateway MCP -> tools
```

reste le chemin tools nominal.

## 4. Leçons

- API Gateway et AgentCore Gateway ont des rôles différents.
- Abandonner AgentCore Gateway ingress ne justifie pas de retirer API Gateway.
- Le contrat d’identité doit être testé dans le Runtime réel.
- Un JWT validé en amont n’est utile au Runtime que si son identité reste disponible.
- Aucun `actorId`, `userId`, `tenantId`, `trustedIdentity` ou groupe ne doit provenir du body.
- `sessionId` ne doit jamais être utilisé comme identité.
- Les logs doivent rester redacted.

## 5. Artefacts historiques

Les éléments suivants sont conservés pour traçabilité mais ne décrivent plus le chemin nominal :

```text
scripts/p0_gateway_contract_check.py
tests/p0/identity-contract-cases.json
docs/p0/P0-Execution-Commands.md
```

Ils doivent être adaptés ou archivés avant réutilisation, notamment parce que :

- ils ciblent encore Gateway-first ;
- certains `sessionId` de test sont trop courts ;
- le contrat `trustedIdentity` n’est pas aligné avec le fallback legacy encore présent dans le code.

## 6. Références

- ADR-0002 — historique Gateway-first, superseded ;
- ADR-0003 — provisioning AgentCore natif Terraform ;
- ADR-0004 — API Gateway devant AgentCore Runtime JWT ;
- plan de remédiation V1.
