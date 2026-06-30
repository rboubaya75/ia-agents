# ADR-001 — API Gateway + Lambda Agent Invocation Facade

## Statut

Accepted for V1.

## Décision

La V1 utilise :

```text
Browser -> Amazon API Gateway HTTP API -> Lambda Agent Invocation Facade -> AgentCore Runtime
```

## Justification

Cette option permet de centraliser l’identité, la validation payload, l’observabilité et la sécurité d’invocation Runtime.

## Conséquences

- le Runtime n’est pas appelé directement par le frontend ;
- le frontend utilise `VITE_API_BASE_URL` ;
- `VITE_AGENT_ARN` doit être supprimé dans une PR ultérieure.
