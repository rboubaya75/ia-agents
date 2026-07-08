# P0 — Spike API Gateway -> AgentCore Gateway -> Runtime

## Statut

GO P0.

## Objectif

Prouver ou invalider le remplacement du chemin legacy :

```text
Amazon API Gateway HTTP API -> Lambda Facade -> AgentCore Runtime
```

par la cible :

```text
Amazon API Gateway HTTP API -> AgentCore Gateway -> HTTP Target AgentCore Runtime
```

Le point clef est l'identité : la P0 doit prouver que `actorId = Cognito sub` reste contrôlé côté serveur sans dépendre d'une valeur envoyée par le navigateur.

## Contexte technique

AgentCore Gateway supporte trois familles de targets : MCP, HTTP et inference. Les HTTP targets envoient le trafic directement vers une cible HTTP, par exemple un AgentCore Runtime. Les MCP targets servent à agréger des tools tels que Lambda, OpenAPI, API Gateway REST APIs ou MCP servers.

## Hypothèse P0

La combinaison suivante peut remplacer la Lambda Facade dans le chemin nominal :

```text
Cognito JWT
  -> API Gateway JWT Authorizer
  -> AgentCore Gateway inbound authorizer
  -> AgentCore Gateway HTTP Target Runtime
  -> Runtime identity contract
```

## Non-objectifs P0

- Ne pas basculer la production.
- Ne pas supprimer immédiatement la Lambda Facade.
- Ne pas créer toute la stack Terraform définitive avant validation du contrat.
- Ne pas activer RAG.
- Ne pas exposer AgentCore Gateway directement au navigateur.

## Pré-requis

- Branche `migration/secure-agentcore-v1` à jour.
- Stack test Terraform appliquée.
- Frontend accessible via CloudFront.
- Cognito User Pool et app client disponibles.
- Token Cognito valide pour un utilisateur test.
- Runtime AgentCore déployé avec image `phase_4.py`.
- Accès AWS permettant de créer ou tester AgentCore Gateway et targets.

## Étapes P0

### 1. Baseline legacy

Valider le chemin existant :

```text
API Gateway -> Lambda Facade -> Runtime
```

Critères :

- appel authentifié OK ;
- appel sans token rejeté ;
- injection `actorId` rejetée ;
- injection `userId` rejetée ;
- injection `trustedIdentity` rejetée.

### 2. Créer AgentCore Gateway de test

Créer un Gateway isolé, nommé par exemple :

```text
wildrydes-test-agentcore-gateway-p0
```

Configurer l'authorizer inbound retenu pour le spike : OAuth/JWT, IAM SigV4 ou authenticate-only selon capacité disponible sur le compte.

### 3. Créer HTTP Target vers Runtime

Créer un HTTP Target pointant vers l'endpoint Runtime AgentCore.

Valider :

```text
AgentCore Gateway -> Runtime
```

### 4. Brancher API Gateway vers AgentCore Gateway

Tester l'appel :

```text
API Gateway -> AgentCore Gateway -> Runtime
```

Cette étape peut se faire avec une route temporaire de test, par exemple :

```text
POST /p0/agent/invoke
```

La route nominale `/agent/invoke` ne doit pas être cassée pendant le spike.

### 5. Valider le contrat identité

Cas à prouver :

- `actorId` dérive du `sub` Cognito validé ;
- le body client ne peut pas imposer `actorId` ;
- le body client ne peut pas imposer `userId` ;
- le body client ne peut pas imposer `tenantId` ;
- le body client ne peut pas imposer `trustedIdentity` ;
- `sessionId` n'est jamais utilisé comme identité ;
- User A ne peut pas lire les données de User B.

### 6. Valider Runtime -> Gateway MCP -> tool minimal

Créer ou utiliser un tool minimal pour valider :

```text
Runtime -> AgentCore Gateway MCP endpoint -> tool
```

Le tool peut retourner un résultat non sensible :

```json
{
  "ok": true,
  "tool": "p0_echo",
  "actorIdSource": "server"
}
```

### 7. Valider logs et observabilité

Les logs ne doivent jamais contenir :

- JWT ;
- header Authorization ;
- prompt brut ;
- secret ;
- actorId brut ;
- sessionId brut ;
- email complet.

## Go / No-Go

### GO Gateway-first si

- API Gateway peut appeler AgentCore Gateway proprement ;
- AgentCore Gateway peut appeler Runtime via HTTP Target ;
- Runtime reçoit ou reconstruit une identité fiable ;
- `actorId = Cognito sub` est prouvé ;
- les champs d'identité client-side sont rejetés ;
- Runtime peut appeler un tool via Gateway MCP ;
- logs redacted validés.

### NO-GO temporaire si

- l'identité fiable ne peut pas être transmise ou reconstruite ;
- l'intégration API Gateway -> AgentCore Gateway est instable ;
- le mode d'authorizer ne correspond pas aux besoins ;
- les erreurs ou logs exposent des informations sensibles ;
- Runtime nécessite encore une transformation custom non couverte.

Dans ce cas, conserver temporairement :

```text
API Gateway -> Lambda Facade -> Runtime
```

mais uniquement comme fallback documenté par ADR.

## Livrables P0

- Résultat des tests de `scripts/p0_gateway_contract_check.py`.
- Capture ou export des endpoints Gateway/targets.
- Décision Go/No-Go.
- Liste des modules Terraform définitifs à créer ou modifier.
- Liste des changements pipeline à implémenter.
