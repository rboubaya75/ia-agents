# ADR-0002 — AgentCore Gateway-first avec Amazon API Gateway conservé

- **Statut :** superseded
- **Remplacé par :** `ADR-0004-api-gateway-direct-agentcore-runtime-jwt.md`
- **Périmètre historique :** spike P0 de l’environnement `test`

## Contexte historique

Cet ADR a corrigé une première dérive qui consistait à retirer Amazon API Gateway du chemin utilisateur. Il a proposé le chemin suivant :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
  -> AgentCore Gateway ingress
  -> HTTP Target: AgentCore Runtime
```

Le chemin tools prévu était :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP
  -> Lambda / API Gateway REST API / OpenAPI tools
```

Amazon API Gateway devait rester l’ingress web externe pour Cognito JWT, CORS, throttling, access logs et future protection edge. AgentCore Gateway devait assurer la médiation agentique vers Runtime et les tools.

## Résultat du spike

Le spike Gateway-first a permis de confirmer plusieurs éléments :

- Amazon API Gateway est utile et ne doit pas être confondu avec AgentCore Gateway ;
- AgentCore Gateway MCP reste pertinent pour exposer les tools ;
- la Lambda Agent Invocation Facade peut rester hors du chemin nominal ;
- l’identité ne doit jamais provenir du body client.

En revanche, le chaînage d’ingress suivant n’a pas satisfait le contrat d’identité attendu par `phase_4.py` :

```text
API Gateway -> AgentCore Gateway ingress -> Runtime
```

AgentCore Gateway validait l’identité inbound puis invoquait le Runtime avec son identité IAM de service. Le Runtime ne recevait donc pas l’identité Cognito utilisateur dans le format requis pour dériver `actorId = sub`.

## Décision remplacée

La partie suivante est abandonnée pour l’ingress utilisateur :

```text
API Gateway -> AgentCore Gateway ingress -> Runtime
```

La cible V1 est désormais définie par ADR-0004 :

```text
Browser
  -> API Gateway HTTP API
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

AgentCore Gateway reste utilisé uniquement pour :

```text
Runtime -> AgentCore Gateway MCP -> tools
```

## Leçons conservées

- Gateway-first ne signifie pas suppression d’Amazon API Gateway.
- Amazon API Gateway et AgentCore Gateway répondent à des responsabilités différentes.
- Toute modification du chemin d’ingress doit faire l’objet d’un ADR et d’une validation explicite.
- Le contrat d’identité doit être prouvé par des tests négatifs et d’isolation utilisateur.
- Les logs doivent rester redacted sur chaque hop.

## Références

- ADR-0003 : provisioning AgentCore natif Terraform.
- ADR-0004 : Amazon API Gateway devant AgentCore Runtime JWT.
- `docs/p0/P0-AgentCore-Gateway-Spike.md` : historique du spike et décision NO-GO sur Gateway ingress.
