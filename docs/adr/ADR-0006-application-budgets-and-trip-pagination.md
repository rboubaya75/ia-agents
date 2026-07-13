# ADR-0006 — Budgets synchrones, taille des requêtes et pagination Trips

- **Statut :** Accepté
- **Date :** 2026-07-13
- **Branche :** `migration/secure-agentcore-v1`
- **Décision liée :** ADR-0005, façade Lambda de sécurité devant AgentCore Runtime

## Contexte

Le chemin synchrone traverse API Gateway, la façade Lambda, AgentCore Runtime, le Gateway MCP et la Lambda Trip Tools. Sans budgets descendants, un composant aval peut continuer à travailler après l’expiration de son appelant. Par ailleurs, une requête HTTP volumineuse et une requête DynamoDB non paginée augmentent la latence, la mémoire consommée et la taille des réponses.

## Décision

### Taille du body

La façade limite le body JSON à **16 384 octets UTF-8** avant le décodage JSON. Un dépassement retourne :

```json
{"error":"payload_too_large"}
```

avec le statut HTTP `413`. La limite du prompt reste indépendante et fixée à 4 000 caractères.

### Budgets synchrones

```text
Façade Lambda                    28 s
Connexion façade -> Runtime       2 s
Lecture façade <- Runtime        23 s
Marge façade                      3 s
Connexion Runtime -> MCP          2 s
Lecture Runtime <- MCP            6 s
Écriture Runtime -> MCP           5 s
Pool Runtime -> MCP               2 s
Lambda Trip Tools                 5 s
```

Le budget d’un composant aval reste inférieur au budget de son appelant. Les appels Runtime ne sont pas retentés automatiquement afin d’éviter la duplication d’actions agentiques ou d’outils non idempotents.

### Pagination Trips

`get_trips` accepte :

```json
{
  "userId": "<injecté par le Runtime>",
  "limit": 20,
  "nextToken": "<optionnel>"
}
```

Règles :

- `limit` vaut 20 par défaut ;
- `limit` est compris entre 1 et 50 ;
- une seule requête DynamoDB `Query` est exécutée par appel ;
- `LastEvaluatedKey` est converti en curseur URL-safe opaque ;
- le curseur ne contient pas le `userId` en clair ;
- le `userId` de l’`ExclusiveStartKey` est toujours reconstruit depuis l’identité serveur ;
- un curseur invalide est rejeté avant tout accès DynamoDB.

Réponse :

```json
{
  "trips": [],
  "count": 0,
  "nextToken": "<présent uniquement si une page suivante existe>"
}
```

## Alternatives rejetées

- **Retourner tous les Trips :** latence et taille de réponse non bornées.
- **Exposer directement `LastEvaluatedKey` :** fuite de détails de stockage et contrat frontend couplé à DynamoDB.
- **Augmenter les timeouts à 120 secondes :** incompatible avec le chemin HTTP synchrone et masque les dépendances lentes.
- **Retenter automatiquement les invocations Runtime :** risque de créer ou mettre à jour deux fois une ressource.

## Conséquences

- Le frontend et l’agent doivent suivre `nextToken` pour parcourir toutes les pages.
- Les opérations longues devront faire l’objet d’un ADR asynchrone distinct.
- Les métriques `413`, `504`, latence Runtime et latence Trip Tools devront être surveillées dans CloudWatch.
