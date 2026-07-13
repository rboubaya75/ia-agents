# ADR-0007 — Idempotence durable par mutation et confirmation contrôlée

- **Statut :** proposé pour validation
- **Date :** 2026-07-13
- **Décideurs :** Solution Architecture AWS / Lead IA Agentique
- **Périmètre :** frontend React, AgentCore Runtime, Gateway MCP, Lambda Trip Tools et DynamoDB Trips
- **Complète :** ADR-0006

## Contexte

La première implémentation de l’ADR-0006 associait un `operationId` à un message utilisateur complet. Elle couvrait le retry HTTP 401, mais pas tous les scénarios distribués :

- perte de la page ou réponse réseau ambiguë avant que le frontend ait mémorisé l’identifiant ;
- plusieurs mutations produites par le modèle dans un même tour ;
- replay tardif d’une mise à jour après qu’une autre mise à jour a modifié l’item ;
- lecture éventuellement cohérente juste après un échec conditionnel DynamoDB ;
- instruction de confirmation uniquement déclarative dans le system prompt.

## Décision

### 1. Identifiant de requête persisté avant l’appel

Le frontend calcule l’empreinte SHA-256 de `sessionId + prompt`, génère un UUID de requête et le stocke dans `sessionStorage` **avant** l’appel HTTP.

- aucune donnée de prompt brute n’est stockée ;
- un timeout, une erreur réseau ou un HTTP ambigu (`408`, `425`, `429`, `5xx`) conserve l’UUID ;
- le renvoi du même message dans la même session réutilise cet UUID ;
- un succès ou une erreur non ambiguë supprime l’entrée.

### 2. Identifiant distinct pour chaque mutation

Le Runtime conserve le `operationId` frontend comme identifiant de requête. Pour chaque `create_trip` ou `update_trip`, il dérive un UUID v5 distinct à partir de :

```text
requestOperationId
+ nom canonique du tool
+ hash canonique du payload métier
+ rang d’occurrence du même tool/payload dans le tour
```

Le Runtime écrase ensuite `operationId` dans l’entrée MCP avec cet identifiant de mutation. Deux mutations différentes dans un même message ne partagent donc plus la même clé.

### 3. Retry MCP borné par l’état de mutation

Le Runtime peut rejouer l’agent une fois uniquement lorsqu’aucune mutation confirmée n’a commencé.

Dès qu’un appel mutatif confirmé est préparé, `mutation_started=true`. Toute erreur de transport ultérieure est remontée au client ; le Runtime ne rejoue pas automatiquement le modèle et ses outils.

### 4. Ledger durable dans la table Trips

Les mises à jour utilisent une entrée technique dans la table existante :

```text
userId = IDEMPOTENCY#<actorId>
tripId = MUTATION#<mutationOperationId>
```

Cette partition n’est jamais interrogée par `get_trips`, qui reste limité à la partition métier `<actorId>`.

L’entrée contient :

- `operationType` ;
- `operationHash` ;
- `targetTripId` ;
- `createdAt` ;
- `expiresAt` pour DynamoDB TTL.

`update_trip` exécute dans une même transaction DynamoDB :

1. la mise à jour optimiste du voyage ;
2. la création conditionnelle de l’entrée de ledger.

`ClientRequestToken` reçoit également l’identifiant de mutation pour bénéficier de l’idempotence native de `TransactWriteItems` pendant sa fenêtre AWS.

### 5. Replays et lectures cohérentes

Les lectures utilisées pour arbitrer un replay sont exécutées avec `ConsistentRead=true` :

- lecture du voyage après conflit de création ;
- lecture du ledger avant une mise à jour ;
- lecture du ledger et du voyage après annulation de transaction.

Un replay tardif reste reconnu tant que l’entrée TTL existe, même si d’autres mises à jour ont été appliquées depuis.

### 6. Confirmation vérifiée côté serveur

Le Runtime vérifie la **requête utilisateur courante**, avant la mutation. Une confirmation est acceptée seulement si le message commence explicitement par une formulation contrôlée telle que :

```text
Je confirme la création...
Je confirme la modification...
I confirm the creation...
I confirm the update...
```

Le Runtime injecte `confirmationVerified=true|false`. La Lambda Trip Tools refuse toute mutation dont la valeur n’est pas exactement `true`.

Cette mesure empêche une simple décision autonome du modèle de déclencher un effet de bord. Elle ne remplace pas encore un workflow métier de confirmation signé et lié à un plan précis ; ce renforcement pourra être traité dans une phase dédiée.

## Conséquences

### Positives

- reprise après timeout ou fermeture de page avec la même opération ;
- plusieurs mutations possibles dans un même tour ;
- absence de réapplication d’une ancienne mise à jour ;
- arbitrage DynamoDB cohérent après concurrence ;
- confirmation imposée par le Runtime et la Lambda, pas uniquement par le prompt ;
- aucune nouvelle table DynamoDB.

### Négatives et limites

- ajout d’items techniques et de transactions dans la table Trips ;
- permission `dynamodb:TransactWriteItems` supplémentaire ;
- coût transactionnel DynamoDB supérieur à un `UpdateItem` simple ;
- la stabilité d’un replay agentique suppose que le modèle reproduise le même ordre et le même payload métier ;
- la confirmation textuelle est liée au tour courant, mais pas encore à un objet de commande signé.

## Contrôles de validation

- deux créations différentes dans un même tour produisent deux identifiants ;
- deux créations identiques dans le même tour sont distinguées par leur rang ;
- un replay reproduisant la même séquence dérive les mêmes identifiants ;
- aucun retry automatique après `mutation_started=true` ;
- persistance frontend avant l’appel réseau ;
- replay tardif `update_trip` via le ledger ;
- transaction atomique voyage + ledger ;
- lectures d’arbitrage cohérentes ;
- refus d’une mutation sans `confirmationVerified=true` ;
- Terraform fmt/init/validate/plan sans remplacement de la table.
