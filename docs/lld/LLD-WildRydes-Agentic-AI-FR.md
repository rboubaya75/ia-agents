# LLD — WildRydes Agentic AI Application Landing Zone

**Version :** française initiale  
**Statut :** base de structuration repository  
**Périmètre V1 :** `test`  
**PR courante :** non-déployante  
**GitHub Actions :** non modifié dans cette PR

## 1. Objectif

Ce LLD décrit la structure cible de l’implémentation V1.

La première PR ne crée aucune ressource AWS. Elle prépare uniquement :

- documentation ;
- structure Terraform ;
- structure Lambda ;
- structure tests ;
- ADR ;
- runbooks.

## 2. Structure cible

```text
infra/
├── environments/test/
└── modules/

lambda/
├── agent_facade/
└── trip_tools/

tests/
├── integration/
├── security/
├── smoke/
└── latency/
```

## 3. Terraform

La cible Terraform est native.

La PR initiale crée uniquement le squelette :

```text
infra/environments/test/backend.tf
infra/environments/test/providers.tf
infra/environments/test/versions.tf
infra/environments/test/variables.tf
infra/environments/test/locals.tf
infra/environments/test/main.tf
infra/environments/test/outputs.tf
infra/environments/test/terraform.tfvars.example
```

Aucun `terraform apply` n’est ajouté.

## 4. Lambda Agent Invocation Facade

La Lambda Facade sera ajoutée dans une PR ultérieure.

Son rôle cible :

- extraire `claims.sub` ;
- construire `trustedIdentity.actorId` ;
- rejeter `actorId`, `userId`, `trustedIdentity` envoyés par le navigateur ;
- invoquer AgentCore Runtime.

## 5. AgentCore Runtime

Le Runtime cible doit utiliser `phase_4.py`.

Le payload cible contient :

```json
{
  "prompt": "...",
  "sessionId": "...",
  "trustedIdentity": {
    "actorId": "..."
  },
  "correlationId": "..."
}
```

## 6. Sécurité

Principes V1 :

- IAM least privilege ;
- pas de `AdministratorAccess` dans la cible ;
- pas de secrets dans le dépôt ;
- pas de prompt brut dans les logs ;
- pas de JWT dans les logs ;
- pas de `actorId` brut dans les logs.

## 7. RAG

Le RAG est prévu comme capacité future.

Variable future :

```hcl
enable_rag = false
```

Aucune ressource RAG n’est obligatoire pour la V1.

## 8. Tests futurs

Les tests cibles incluent :

- smoke tests ;
- negative security tests ;
- runtime contract validation ;
- latency tests.

## 9. GitHub Actions

Le client dispose déjà d’un workflow GitHub Actions avec OIDC. Il sera soumis pour vérification ultérieure.

Cette PR ne crée pas de workflow.
