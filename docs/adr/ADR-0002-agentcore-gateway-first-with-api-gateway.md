# ADR-0002 — AgentCore Gateway-first avec Amazon API Gateway conservé

## Statut

Proposé pour validation client.

## Contexte

La version précédente du design WildRydes opposait implicitement Lambda Facade et AgentCore Gateway. Une première correction Gateway-first a ensuite trop simplifié la cible en retirant Amazon API Gateway du chemin utilisateur.

Cette suppression est incorrecte pour la V1 : Amazon API Gateway reste utile comme ingress web externe pour le frontend React/Vite, notamment pour Cognito JWT, CORS, throttling, access logs, custom domain futur et WAF futur.

AgentCore Gateway doit être repositionné non pas comme remplaçant d’Amazon API Gateway, mais comme gateway agentique native : HTTP Target vers AgentCore Runtime et MCP Targets vers les tools.

## Décision

Conserver Amazon API Gateway comme ingress web externe et utiliser AgentCore Gateway comme gateway agentique native.

Le chemin nominal devient :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
  -> AgentCore Gateway
  -> HTTP Target: AgentCore Runtime
```

Le chemin tools devient :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP endpoint
  -> Lambda / API Gateway REST API / OpenAPI tools
```

La Lambda Agent Invocation Facade n’est plus le chemin nominal. Elle ne doit être conservée que comme fallback temporaire si un spike démontre qu’un besoin non couvert par API Gateway + AgentCore Gateway impose une logique custom.

## Conséquences positives

- API Gateway reste visible dans le HLD, le LLD, le README et les pipelines.
- Le design reste compatible avec WAF, custom domain, throttling et observabilité d’ingress.
- AgentCore Gateway est utilisé pour ce qu’il apporte nativement : targets HTTP/MCP, intégration tools et médiation agentique.
- Les API métier peuvent être exposées comme MCP Targets via OpenAPI ou API Gateway REST API.
- La Lambda Facade cesse d’être une dépendance obligatoire et une source de complexité.

## Risques et points à valider

- Le contrat exact d’intégration API Gateway -> AgentCore Gateway doit être validé en P0.
- Le modèle d’identité `actorId = Cognito sub` doit être prouvé par test contractuel.
- Les modes d’authorizer AgentCore Gateway doivent être confirmés sur l’environnement AWS cible.
- Les logs doivent rester redacted sur API Gateway, Gateway, Runtime et tools.

## Décision rejetée

### Browser -> AgentCore Gateway direct

Rejeté en V1, car cela retirerait API Gateway du rôle d’ingress web public et compliquerait les exigences CORS, throttling, custom domain, WAF futur et access logs.

### API Gateway -> Lambda Facade -> Runtime comme nominal

Rejeté pour la nouvelle cible, car cette architecture contourne les capacités natives AgentCore Gateway et entretient une façade custom qui doit être justifiée au cas par cas.

## Gate de validation P0

Avant codage massif, valider :

1. API Gateway HTTP API -> AgentCore Gateway ;
2. AgentCore Gateway -> HTTP Target Runtime ;
3. Runtime -> Gateway MCP -> un tool minimal ;
4. `actorId = Cognito sub` ;
5. rejet des champs identity client-side ;
6. logs redacted ;
7. isolation User A / User B.
