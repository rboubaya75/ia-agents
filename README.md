# WildRydes — Secure AgentCore V1 Landing Zone

Ce dépôt contient le projet WildRydes Agentic AI et sert de base à la migration vers une application landing zone AWS sécurisée avec Amazon Bedrock AgentCore.

## Statut

Branche de migration : `migration/secure-agentcore-v1`.

Cette première étape est non-déployante. Elle prépare uniquement la structure documentaire et technique du dépôt. Elle ne lance aucun déploiement AWS.

## Cible V1

```text
Browser -> Amazon API Gateway HTTP API -> Lambda Agent Invocation Facade -> AgentCore Runtime -> phase_4.py
```

Composants principaux :

- Amazon API Gateway HTTP API ;
- Cognito JWT Authorizer ;
- Lambda Agent Invocation Facade ;
- AgentCore Runtime ;
- AgentCore Memory ;
- AgentCore Gateway ;
- Lambda Trip Tools ;
- DynamoDB ;
- Terraform ;
- GitHub Actions.

## RAG

La capacité RAG — Retrieval-Augmented Generation est prévue comme évolution future. Elle n’est pas livrée en V1.

La V1 doit rester RAG-ready, avec une future variable Terraform `enable_rag = false` par défaut.

## Organisation cible

```text
docs/
infra/
lambda/
tests/
scripts/
```

Les éléments workshop existants sont conservés temporairement pour référence.

## Règles de migration

- Ne pas travailler directement sur `main`.
- Utiliser des branches et des PRs de migration.
- Ne pas modifier les ressources AWS sans validation.
- Garder la première PR non-déployante.
- Ne pas ajouter de workflow GitHub Actions dans cette PR, le client fournira son workflow OIDC ultérieurement.
