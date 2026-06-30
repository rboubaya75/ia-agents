# ADR-004 — RAG Future Capability

## Statut

Accepted for future version.

## Décision

Le RAG est intégré comme capacité future et n’est pas livré en V1.

La V1 doit rester RAG-ready avec :

```hcl
enable_rag = false
```

## Justification

RAG permettra à l’agent de rechercher des informations dans une base documentaire WildRydes. Cette capacité ne remplace pas AgentCore Memory, les tools ou DynamoDB.
