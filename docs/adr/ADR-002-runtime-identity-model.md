# ADR-002 — Runtime Identity Model

## Statut

Accepted for V1.

## Décision

`actorId` est dérivé côté serveur depuis le claim Cognito `sub`.

```text
actorId = claims.sub
```

## Règles

Le navigateur ne doit pas fournir :

- `actorId` ;
- `userId` ;
- `tenantId` ;
- `trustedIdentity`.

Ces champs doivent être rejetés par la Lambda Facade.
