# Remédiation V1 — Ingress sécurisé AgentCore

- **Statut :** implémentation terminée, validation de déploiement en attente
- **Date :** 2026-07-13
- **Branche :** `migration/secure-agentcore-v1`
- **Décision active :** ADR-0005

## 1. Architecture implémentée

```text
Browser
  -> API Gateway JWT
  -> Lambda Security Facade
  -> AgentCore Runtime IAM-only
  -> AgentCore Gateway MCP AWS_IAM
  -> Trip Tools Lambda
  -> DynamoDB
```

AgentCore Gateway ingress et le proxy direct Runtime JWT sont abandonnés.

## 2. Travaux réalisés

### Ingress

- route `POST /agent/invoke` ;
- JWT authorizer Cognito ;
- CORS CloudFront ;
- throttling ;
- access logs ;
- Lambda Facade en intégration AWS proxy.

### Identité

- `actorId = claims.sub` dans la façade ;
- rejet des identités client-side ;
- `trustedIdentity.actorId` produit côté serveur ;
- Runtime IAM-only ;
- resource policy Runtime limitée au rôle façade.

### Runtime et MCP

- Python 3.12 ARM64 ;
- suppression du décodage JWT navigateur ;
- client MCP SigV4 ;
- Gateway MCP limitée au rôle Runtime ;
- échec explicite si les tools MCP V1 sont absents.

### Tools et données

- Lambda Trip Tools ;
- target MCP réel ;
- `create_trip`, `get_trips`, `get_trip`, `update_trip` ;
- injection serveur de `userId` ;
- validation stricte ;
- IAM DynamoDB limité à la table exacte.

### Sécurité et exploitation

- IAM Runtime réduit ;
- CSP et headers CloudFront ;
- ECR immutable ;
- concurrence Lambda limitée ;
- logs redacted ;
- tests unitaires ;
- pipeline qualité ;
- validateur du contrat de déploiement.

## 3. Gates encore à exécuter

L’implémentation ne vaut pas validation opérationnelle. Les preuves suivantes restent obligatoires :

1. pipeline `Test Application Quality` verte ;
2. Terraform fmt/init/validate vert ;
3. Terraform plan revu sans destruction inattendue ;
4. déploiement `full` réussi ;
5. CORS depuis CloudFront ;
6. appels sans JWT, JWT invalide et mauvais client refusés ;
7. identité client-side refusée ;
8. invocation Runtime directe refusée ;
9. isolation Memory User A/User B ;
10. quatre tools MCP exécutés end-to-end ;
11. logs sans données sensibles ;
12. latence des parcours nominaux inférieure à 28 secondes.

## 4. Commandes locales

```bash
terraform -chdir=infra/environments/test fmt -check -recursive
terraform -chdir=infra/environments/test init -backend=false
terraform -chdir=infra/environments/test validate
python3 -m unittest discover -s tests/unit -p 'test_*.py' -v
cd frontend && npm ci && npm run lint && npm run build
```

Le plan et l’apply doivent être exécutés par les workflows GitHub Actions avec OIDC AWS.

## 5. Critère de clôture

La V1 sera clôturée uniquement après un déploiement `full` vert et un rapport de smoke tests couvrant ingress, identité, Runtime, Memory, MCP, DynamoDB, logs et latence.
