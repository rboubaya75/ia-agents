# ADR-0006 — Idempotence des mutations, deadline propagée et lifecycle MCP

- **Statut :** proposé pour validation
- **Date :** 2026-07-13
- **Décideurs :** Solution Architecture AWS / Lead IA Agentique
- **Périmètre :** frontend React, façade Lambda, AgentCore Runtime, Gateway MCP et Trip Tools Lambda

## Contexte

Une invocation agentique peut dépasser le délai de la façade ou perdre la réponse après qu’un outil de mutation a déjà modifié DynamoDB. Un retry applicatif ou une reconnexion MCP peut alors répéter `create_trip` ou `update_trip`.

Le frontend conservait également une copie d’access token pendant toute la durée de la page. Enfin, le client MCP était ouvert globalement sans stratégie explicite de préchauffage, de fermeture ou de reconnexion.

## Décision

### 1. Identifiant d’opération

Le frontend produit un UUID `operationId` pour chaque message envoyé. Cet identifiant est réutilisé pendant l’unique retry HTTP 401 du même appel.

La façade valide `operationId`, dérive l’identité depuis Cognito et transmet au Runtime :

- `operationId` ;
- `requestId` produit par Lambda ;
- `deadlineEpochMs` calculée à partir du budget de lecture Runtime ;
- `trustedIdentity.actorId`.

Le Runtime refuse tout champ inattendu et écrase le contexte des outils avant leur exécution.

### 2. Idempotence de `create_trip`

Le `tripId` est un UUID v5 déterministe calculé à partir de `userId` et `operationId`.

L’item stocke :

- `creationOperationId` ;
- `creationOperationHash`.

Un second appel avec le même identifiant et le même payload retourne le résultat déjà créé. Le même identifiant avec un payload différent produit `idempotency_conflict`.

### 3. Idempotence de `update_trip`

L’item stocke :

- `lastOperationId` ;
- `lastOperationHash`.

Une opération déjà appliquée retourne `replayed=true`. La concurrence reste protégée par la condition optimiste sur `updatedAt`. Après un échec conditionnel, l’outil relit l’item afin de distinguer un replay réussi d’une modification concurrente différente.

### 4. Deadline

La façade réserve une marge de sécurité avant son timeout de lecture et transmet une échéance absolue.

Le Runtime vérifie cette échéance :

- à la validation ;
- avant l’appel agent ;
- avant chaque tool call ;
- avant un retry MCP.

La Lambda Trip Tools la vérifie à nouveau avant tout accès DynamoDB.

### 5. Lifecycle MCP

Le Runtime possède un `MCPToolProvider` process-wide :

- initialisation avant `app.run()` ;
- réutilisation sur conteneur chaud ;
- fermeture via `atexit` ;
- remise à zéro après erreur de transport ;
- une seule reconnexion et une seule réexécution de l’agent.

Le retry conserve le même `operationId`, ce qui rend les mutations rejouables.

### 6. Authentification frontend

Le frontend demande un access token valide au SDK Cognito avant chaque appel. Un HTTP 401 déclenche un seul renouvellement et un seul retry avec le même `operationId`.

## Alternatives rejetées

### Identifiant dérivé uniquement du contenu du voyage

Rejeté, car deux voyages métier légitimes peuvent avoir les mêmes dates et destination.

### Retry MCP sans idempotence

Rejeté, car une réponse perdue après un effet de bord pourrait créer un doublon.

### Stockage d’idempotence dans une seconde table

Non retenu pour cette phase : il ajouterait une ressource et un cycle de déploiement supplémentaires. Le schéma DynamoDB existant permet de porter les métadonnées nécessaires dans les items Trips.

### Augmentation seule des timeouts

Rejetée : elle réduit la fréquence des erreurs mais ne résout ni les effets de bord après timeout ni les transports MCP cassés.

## Conséquences

### Positives

- absence de doublon lors d’un retry du même appel ;
- corrélation façade, Runtime et tools ;
- arrêt des effets de bord lorsque le budget est expiré ;
- reconnexion MCP bornée ;
- suppression de l’access token figé côté React.

### Négatives

- ajout de métadonnées techniques dans les items DynamoDB ;
- contrat MCP enrichi de champs injectés côté serveur ;
- un retry MCP peut refaire un appel modèle, avec coût et latence supplémentaires ;
- la persistance conversationnelle locale et la Memory structurée restent à traiter dans une phase suivante.

## Contrôles de validation

- tests unitaires de replay create/update ;
- test de conflit sur réutilisation de `operationId` ;
- test d’échéance expirée avant DynamoDB ;
- test de reconnexion MCP avec le même identifiant d’opération ;
- frontend lint/build ;
- Terraform fmt/init/validate/plan ;
- test E2E : réponse perdue après mutation puis retry sans doublon.
