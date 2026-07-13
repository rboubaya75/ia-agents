# ADR-0005 — Lambda Security Facade devant AgentCore Runtime IAM

- **Statut :** accepté
- **Date :** 2026-07-13
- **Périmètre :** environnement `test`, branche `migration/secure-agentcore-v1`
- **Remplace :** ADR-0004 pour l’ingress utilisateur
- **Complète :** ADR-0003 pour le provisioning AgentCore natif Terraform

## Contexte

Les expérimentations précédentes ont successivement utilisé :

```text
API Gateway -> AgentCore Gateway ingress -> Runtime
Browser -> Runtime JWT direct
API Gateway -> HTTP proxy direct -> Runtime JWT
```

Le premier chemin ne propageait pas correctement l’identité Cognito jusqu’au Runtime. Le deuxième retirait API Gateway sans décision explicite. Le troisième rétablissait API Gateway, mais restait un proxy transparent : il ne constituait pas une frontière applicative capable de filtrer le contrat, de reconstruire l’identité de confiance et de limiter les paramètres transmis à AgentCore.

L’architecture AWS de référence analysée place une fonction Lambda entre le navigateur et AgentCore pour créer cette frontière de sécurité.

## Décision

La cible V1 est :

```text
Browser / React
  -> CloudFront / S3 privé
  -> Cognito User Pool
  -> API Gateway HTTP API
       - JWT authorizer Cognito
       - CORS strict
       - throttling
       - access logs redacted
  -> Lambda Agent Invocation Security Facade
       - schéma strict prompt + sessionId
       - actorId dérivé de claims.sub
       - rejet de toute identité ou configuration client arbitraire
       - invocation IAM/SigV4
  -> AgentCore Runtime IAM-only
       - trustedIdentity générée exclusivement par la façade
       - Claude Haiku 4.5 EU
       - AgentCore Memory
       - tools Strands
  -> AgentCore Gateway MCP AWS_IAM
  -> Lambda Trip Tools
  -> DynamoDB Trips
```

AgentCore Gateway reste exclusivement sur le chemin des tools. Il n’est pas utilisé comme ingress utilisateur.

## Contrat d’identité

La seule source d’identité utilisateur est :

```text
actorId = API Gateway validated Cognito access-token claim `sub`
```

Le navigateur envoie uniquement :

```json
{
  "prompt": "Planifie un voyage à Tokyo",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

La façade construit :

```json
{
  "prompt": "Planifie un voyage à Tokyo",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000",
  "trustedIdentity": {
    "actorId": "<cognito-sub>"
  }
}
```

Sont interdits depuis le navigateur : `actorId`, `userId`, `tenantId`, `trustedIdentity`, `groups`, `modelOverride`, `systemPrompt` et tout nom de tool arbitraire.

## Authentification et autorisation

- Browser vers API Gateway : Cognito access token JWT.
- API Gateway vers Lambda : intégration AWS proxy, invocation limitée à `POST /agent/invoke`.
- Lambda vers Runtime : IAM/SigV4 avec `bedrock-agentcore:InvokeAgentRuntime` sur le Runtime exact.
- Resource policy Runtime : seul le rôle de la façade est autorisé ; les autres principals sont explicitement refusés.
- Runtime vers Gateway MCP : IAM/SigV4 avec `bedrock-agentcore:InvokeGateway` sur le Gateway exact.
- Resource policy Gateway : seul le rôle Runtime est autorisé.
- Gateway vers Trip Tools : rôle Gateway limité à la Lambda Trips exacte.
- Trip Tools vers DynamoDB : opérations CRUD minimales sur la table Trips exacte.

## Défense applicative

La façade :

- impose une longueur maximale de prompt ;
- impose un `sessionId` de 33 à 128 caractères sûrs ;
- vérifie `token_use=access`, `client_id` et `sub` ;
- n’enregistre ni token ni prompt brut ;
- limite la concurrence Lambda ;
- désactive les retries cachés de l’appel Runtime ;
- termine avant le timeout maximal API Gateway.

Le Runtime :

- ne décode plus de JWT navigateur ;
- exige exactement `prompt`, `sessionId` et `trustedIdentity.actorId` ;
- écrase toujours `userId` avant un appel tool Trips ;
- isole Memory par `travel/{actorId}/preferences` ;
- signe les appels MCP en SigV4 ;
- refuse de démarrer le chemin agentique si les tools MCP V1 sont indisponibles.

## Conséquences positives

- véritable frontière de sécurité applicative ;
- Runtime non invocable directement par le navigateur ;
- découplage du frontend et de l’API AgentCore ;
- schéma et identité contrôlés côté serveur ;
- IAM least privilege sur chaque hop ;
- target MCP métier réel ;
- logs redacted et contrôles de coût via throttling/concurrence.

## Tradeoffs

- un hop Lambda supplémentaire ;
- coût et latence supplémentaires ;
- timeout synchrone limité par API Gateway HTTP API ;
- maintenance d’un contrat interne façade/Runtime ;
- un smoke test end-to-end est indispensable pour valider le client MCP SigV4 et la latence réelle.

## Critères de sortie V1

- Terraform `fmt`, `validate` et `plan` passent ;
- aucune destruction inattendue du Runtime, Cognito, CloudFront ou DynamoDB ;
- tests unitaires façade, Runtime et tools passent ;
- frontend lint/build passe ;
- déploiement `full` passe ;
- CORS CloudFront vers API Gateway passe ;
- sans JWT et JWT invalide sont rejetés ;
- les champs d’identité client sont rejetés ;
- le Runtime direct est refusé à un principal autre que la façade ;
- Memory User A/User B est isolée ;
- `create_trip`, `get_trips`, `get_trip` et `update_trip` fonctionnent via MCP ;
- le frontend n’expose aucune URL Runtime ;
- aucun token, prompt brut ou identité brute n’apparaît dans les logs.

## Hors périmètre V1

- RAG applicatif complet ;
- production et multi-région ;
- WAF avancé et custom domain ;
- architecture asynchrone pour les traitements supérieurs à 28 secondes ;
- migration vers AgentCore Harness.
