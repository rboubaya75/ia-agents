# ADR-0004 — Amazon API Gateway devant AgentCore Runtime JWT

- **Statut :** accepté
- **Date :** 2026-07-12
- **Périmètre :** environnement `test`, branche par défaut `migration/secure-agentcore-v1`
- **Remplace pour l’ingress utilisateur :** ADR-0002 Gateway-first
- **Complète :** ADR-0003 provisioning AgentCore natif Terraform

## Contexte

La première cible V1 utilisait le chemin suivant :

```text
Browser -> Amazon API Gateway -> AgentCore Gateway ingress -> AgentCore Runtime
```

Le spike et les tests d’intégration ont montré que ce chaînage ne permettait pas au Runtime de disposer de l’identité utilisateur Cognito dans le format attendu par `phase_4.py`. AgentCore Gateway consommait l’identité inbound puis invoquait le Runtime avec son identité IAM de service.

Une remédiation intermédiaire a déplacé l’authorizer JWT vers AgentCore Runtime et fait appeler le Runtime directement par le navigateur :

```text
Browser -> AgentCore Runtime JWT
```

Cette remédiation a permis de valider l’identité Runtime et l’appel Bedrock, mais elle a retiré Amazon API Gateway du chemin agentique sans décision explicite préalable. Elle réduit également les capacités de front-door applicatif : CORS centralisé, throttling, access logs, URL stable et future protection edge.

## Décision

La cible V1 approuvée est :

```text
Browser / React App
  -> Amazon API Gateway HTTP API
      - Cognito JWT authorizer
      - CORS strict
      - throttling
      - access logs redacted
  -> HTTP proxy direct
  -> Amazon Bedrock AgentCore Runtime
      - authorizer JWT Cognito natif
      - Authorization allowlist
      - phase_4.py
```

Le chemin des tools reste séparé :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP
  -> targets tools autorisés
  -> DynamoDB / APIs métier
```

AgentCore Gateway n’est plus utilisé comme intermédiaire d’ingress utilisateur. Il reste la gateway native pour les tools MCP.

## Modèle d’identité

La règle V1 est :

```text
actorId = Cognito access token claim `sub`
```

Le navigateur ne doit jamais être source de vérité pour :

```text
actorId
userId
tenantId
trustedIdentity
groups
```

API Gateway valide le token en première barrière. AgentCore Runtime conserve son authorizer JWT comme barrière finale. Le header `Authorization` est transmis en pass-through et allowlisté par Runtime.

## Justification

Amazon API Gateway reste utile comme front-door pour :

- une URL applicative stable `/agent/invoke` ;
- la validation JWT Cognito en amont ;
- CORS limité au domaine CloudFront ;
- throttling et protection contre les abus Bedrock ;
- access logs et métriques d’ingress ;
- une future intégration CloudFront/WAF/custom domain ;
- le découplage entre le frontend et l’URL technique AgentCore Runtime.

AgentCore Runtime conserve la validation JWT native pour éviter qu’une erreur de configuration du proxy devienne un bypass d’identité.

## Conséquences positives

- Amazon API Gateway reste dans le chemin nominal V1.
- L’identité utilisateur est validée deux fois, sans être reconstruite depuis le body.
- AgentCore Gateway est recentré sur MCP/tools.
- Le frontend n’a plus besoin de connaître l’ARN ou l’URL directe du Runtime.
- Les contrôles CORS, throttling et logs sont centralisés.

## Tradeoffs

- Un hop réseau et un coût API Gateway supplémentaires.
- Une configuration CORS et proxy à maintenir.
- Les headers `Authorization`, `Content-Type` et `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` doivent être transmis sans transformation.
- Le chemin Runtime direct peut rester temporairement comme rollback technique, mais il n’est pas le chemin nominal V1.

## Contraintes d’implémentation

1. L’intégration API Gateway doit être un HTTP proxy direct vers l’URL Runtime :

```text
https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<url-encoded-arn>/invocations?qualifier=DEFAULT
```

2. API Gateway ne doit pas fabriquer ou réécrire `Authorization` ou les headers `x-amzn-*`.
3. CORS doit autoriser uniquement le domaine CloudFront connu et les headers nécessaires.
4. Le frontend doit utiliser une URL applicative générique, par exemple `VITE_AGENT_INVOKE_URL`.
5. Le code Python Runtime ne doit pas être modifié pour cette remise en place du front-door.
6. AgentCore Gateway MCP doit avoir un mode d’authentification cohérent entre Terraform et `phase_4.py`.

## Critères d’acceptation V1

- `OPTIONS /agent/invoke` passe depuis le domaine CloudFront autorisé.
- Appel sans JWT : rejet 401/403.
- JWT invalide ou mauvais client : rejet 401/403.
- JWT valide : requête transmise au Runtime.
- Runtime dérive `actorId` depuis le JWT validé.
- Les champs d’identité fournis dans le body sont rejetés.
- Claude Haiku 4.5 répond via `ConverseStream` et supporte les tools.
- Les logs ne contiennent ni JWT, ni prompt brut, ni identifiants utilisateur bruts.
- AgentCore Gateway MCP reste hors du chemin d’ingress utilisateur.

## Hors périmètre immédiat V1

- ALB ou PrivateLink devant AgentCore Runtime ;
- RAG applicatif complet ;
- architecture multi-région ;
- WAF avancé et custom domain de production ;
- refonte complète des tools métier.
