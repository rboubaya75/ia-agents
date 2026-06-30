# ADR-005 — Terraform and GitHub Actions Deployment Strategy

## Statut

Accepted for target architecture.

## Décision

La cible utilise Terraform et GitHub Actions.

## Contrainte actuelle

Le client dispose déjà d’un workflow GitHub Actions avec OIDC. Aucun workflow n’est ajouté dans la PR initiale.

## Principe

Les futures PRs devront séparer :

- validation ;
- plan ;
- apply bootstrap ;
- build artifacts ;
- apply application ;
- tests.
