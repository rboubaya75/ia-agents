# ADR-003 — Automated Runtime Contract Validation Gate

## Statut

Accepted for V1.

## Décision

Le POC manuel est remplacé par un gate automatisé.

Ce gate doit valider :

- invocation Lambda Facade vers AgentCore Runtime ;
- `runtimeSessionId` ;
- propagation `trustedIdentity` ;
- lecture de la réponse ;
- IAM minimal ;
- logs redacted.

## Note

Le workflow GitHub Actions existant avec OIDC sera revu ultérieurement.
