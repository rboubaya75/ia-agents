# ADR-0004 — Amazon API Gateway devant AgentCore Runtime JWT

- **Statut :** superseded
- **Date initiale :** 2026-07-12
- **Remplacé par :** ADR-0005 — Lambda Security Facade devant AgentCore Runtime IAM
- **Périmètre historique :** environnement `test`

## Décision historique

Cet ADR proposait :

```text
Browser
  -> API Gateway HTTP API
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

Il corrigeait deux problèmes antérieurs :

- AgentCore Gateway ingress ne propageait pas l’identité Cognito jusqu’au Runtime ;
- le chemin Browser -> Runtime direct avait retiré API Gateway sans décision explicite.

## Raison du remplacement

Le proxy HTTP direct rétablissait API Gateway, mais ne créait pas une frontière de sécurité applicative. Il transmettait directement vers AgentCore le payload et le contexte client sans composant serveur chargé de :

- dériver et reconstruire l’identité de confiance ;
- imposer un schéma minimal ;
- rejeter les paramètres de modèle, prompt système ou tools arbitraires ;
- normaliser les erreurs ;
- limiter précisément l’accès IAM au Runtime ;
- protéger l’API AgentCore des évolutions du frontend.

Après analyse de l’architecture AWS de référence, la Lambda Agent Invocation Facade a été réintroduite comme composant de sécurité nominal.

## Cible de remplacement

```text
Browser
  -> API Gateway JWT
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
```

Le chemin tools reste :

```text
Runtime
  -> AgentCore Gateway MCP AWS_IAM
  -> Trip Tools Lambda
  -> DynamoDB
```

## Leçons conservées

- API Gateway reste le front-door web.
- AgentCore Gateway reste réservé aux tools MCP.
- Le navigateur ne doit jamais fournir l’identité de confiance.
- Toute modification du chemin d’ingress nécessite un ADR explicite.
- Un endpoint techniquement authentifié n’est pas nécessairement une frontière de sécurité applicative.

Voir `ADR-0005-lambda-security-facade-agentcore-runtime-iam.md` pour la décision V1 active.
