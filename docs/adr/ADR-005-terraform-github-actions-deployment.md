# ADR-005 — Stratégie de déploiement Terraform et GitHub Actions

- **Statut :** accepté
- **Périmètre :** environnement `test`
- **Branche par défaut :** `migration/secure-agentcore-v1`

## Contexte

Le travail courant, les validations, les plans et les déploiements concernent exclusivement l’environnement `test` porté par la branche par défaut :

```text
migration/secure-agentcore-v1
```

Aucune autre branche n’entre dans le périmètre opérationnel de cet ADR.

## Décision

La cible utilise :

- Terraform ;
- GitHub Actions ;
- OIDC GitHub vers AWS ;
- environnement GitHub `test` ;
- confirmations explicites pour les actions destructives.

Le workflow infrastructure peut exécuter :

- secret scan ;
- lockfile check ;
- `terraform fmt` ;
- `terraform validate` ;
- `terraform plan` ;
- `terraform apply` ;
- `terraform destroy-plan` ;
- `terraform destroy`.

Le workflow application peut exécuter :

- `frontend-only` ;
- `image-only` ;
- `runtime-only` ;
- `full`.

## Conditions d’exécution

`apply` et `destroy` sont autorisés uniquement si :

- ils sont déclenchés manuellement via `workflow_dispatch` ;
- ils ciblent `migration/secure-agentcore-v1` ;
- ils utilisent l’environnement GitHub `test` ;
- ils passent par les reviewers configurés sur cet environnement ;
- le rôle AWS OIDC est limité aux ressources test ;
- `destroy` reçoit une confirmation explicite.

## Sécurité

- aucune clé AWS statique dans GitHub ;
- permissions workflow minimales ;
- rôle OIDC limité au repository, à la branche et à l’environnement test ;
- aucun secret dans les logs ;
- plans Terraform conservés comme artifacts à durée courte ;
- apply exécuté sur le plan produit ;
- destruction séparée et confirmée.

## Architecture applicative

La pipeline doit suivre ADR-0004 :

```text
Frontend -> API Gateway -> AgentCore Runtime JWT
Runtime -> AgentCore Gateway MCP -> tools
```

Après remédiation, le frontend doit être construit avec l’URL API Gateway nominale, pas avec l’URL Runtime directe.

## Critères d’acceptation

- les workflows sont visibles depuis la branche par défaut ;
- OIDC fonctionne sans credentials AWS statiques ;
- Terraform fmt/validate/plan passent ;
- apply exige l’environnement `test` ;
- destroy exige `confirm_destroy=true` ;
- le workflow application déploie une image ECR immuable ;
- le frontend est publié via S3/CloudFront ;
- les logs CI/CD ne contiennent aucun secret ;
- aucune étape nominale n’active la Lambda Facade ou AgentCore Gateway ingress.
