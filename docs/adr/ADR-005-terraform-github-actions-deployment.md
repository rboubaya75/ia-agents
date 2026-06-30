# ADR-005 — Terraform and GitHub Actions Deployment Strategy

## Statut

Accepted.

## Contexte

Le client a decide de travailler exclusivement sur la branche `migration/secure-agentcore-v1` pendant la phase de test.

Cette branche est devenue la branche par defaut du depot pendant cette phase.

La branche `main` est reservee a la future phase production. Le switch vers `main` sera realise manuellement ulterieurement apres validation client.

## Decision

La cible utilise Terraform et GitHub Actions avec OIDC.

Pendant la phase test :

```text
migration/secure-agentcore-v1 = branche par defaut et environnement test
main                         = future branche production
```

Le workflow test peut executer :

- validation ;
- scans securite ;
- plan Terraform ;
- apply Terraform test ;
- destroy Terraform test.

`apply` et `destroy` sont autorises uniquement si :

- ils sont lances manuellement via `workflow_dispatch` ;
- ils ciblent la branche `migration/secure-agentcore-v1` ;
- ils utilisent l environnement GitHub `test` ;
- ils passent par les reviewers configures sur l environnement `test` ;
- le role AWS OIDC est limite a l environnement test ;
- aucune ressource prod n est accessible.

## Implications

- Aucun deploiement test ne depend de `main` pendant la phase actuelle.
- La branche `main` ne doit pas recevoir automatiquement les changements test.
- La promotion vers `main` sera une operation manuelle de production readiness.
- Un role AWS prod separe devra etre cree pour la phase production.
- Un environnement GitHub prod separe devra etre cree pour la phase production.

## Criteres d acceptation

- Le workflow GitHub Actions est visible depuis la branche par defaut.
- OIDC fonctionne sans credentials AWS statiques.
- `terraform plan` fonctionne sur test.
- `terraform apply` fonctionne uniquement avec approbation environment `test`.
- `terraform destroy` exige une confirmation explicite.
- Aucun job ne deploie sur `main` pendant la phase test.
- Les logs CI/CD ne contiennent aucun secret.
