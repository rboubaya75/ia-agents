# HLD — WildRydes Agentic AI Application Landing Zone

**Version :** française initiale  
**Statut :** base de revue client  
**Périmètre V1 :** environnement `test` production-like  
**IaC cible :** Terraform  
**CI/CD cible :** GitHub Actions existant côté client, à vérifier ultérieurement  
**RAG :** capacité future, non livrée en V1

## 1. Résumé exécutif

WildRydes est une application IA agentique sur AWS. La cible V1 est une application landing zone sécurisée permettant à un utilisateur invité de s’authentifier, d’échanger avec un agent IA, de gérer ses voyages et de bénéficier d’une mémoire utilisateur.

La V1 n’est pas une production go-live. Elle sert à valider les fondations techniques, sécurité, identité, observabilité et delivery.

## 2. Architecture cible V1

```text
Browser
  -> Amazon API Gateway HTTP API
  -> Cognito JWT Authorizer
  -> Lambda Agent Invocation Facade
  -> AgentCore Runtime
  -> phase_4.py
  -> Bedrock / AgentCore Memory / AgentCore Gateway
  -> Lambda Trip Tools
  -> DynamoDB
```

## 3. Décision d’ingress

L’option retenue en V1 est :

```text
Browser -> API Gateway -> Lambda Facade -> AgentCore Runtime
```

Cette option permet de ne pas exposer le Runtime directement au navigateur, de dériver `actorId` côté serveur depuis les claims Cognito, de valider le payload, de centraliser l’observabilité et de préparer les quotas futurs.

## 4. Modèle d’identité

Règle obligatoire :

```text
actorId = Cognito JWT sub claim
```

Le navigateur ne doit jamais fournir `actorId`, `userId`, `tenantId` ou `trustedIdentity`.

## 5. AgentCore Runtime

Le Runtime cible exécute :

```text
phase_4.py
```

Il reçoit un payload contenant `trustedIdentity.actorId`.

## 6. AgentCore Memory

AgentCore Memory stocke les préférences utilisateur.

Namespace cible :

```text
travel/{actorId}/preferences
```

## 7. AgentCore Gateway

AgentCore Gateway expose les tools MCP internes :

- `create_trip` ;
- `get_trips` ;
- `get_trip` ;
- `update_trip`.

## 8. RAG future capability

La capacité RAG est ajoutée à la roadmap, mais n’est pas livrée en V1.

La version ultérieure pourra ajouter :

```text
AgentCore Runtime -> Bedrock Knowledge Base -> Vector Store -> S3 Document Repository
```

Le RAG doit rester distinct de Memory, DynamoDB et tools.

## 9. Hors périmètre V1

- production ;
- WAF ;
- Bedrock Guardrails ;
- custom domain ;
- admin portal ;
- RAG actif ;
- streaming/WebSocket ;
- multi-tenant B2B avancé.

## 10. Conclusion

La V1 doit rester simple, sécurisée et mesurable. Elle prépare la trajectoire production et la future capacité RAG sans les livrer immédiatement.
