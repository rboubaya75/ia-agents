# ADR-0007 — Récupération contrôlée d'une façade Lambda marquée tainted

## Statut

Accepté pour l'environnement `test`.

## Contexte

Un apply Terraform a créé la Lambda façade puis a échoué pendant `PutFunctionConcurrency`. Terraform a donc marqué l'objet comme `tainted` et le plan suivant a proposé son remplacement. Le guard de Phase 3 a correctement bloqué cette opération sur une ressource critique.

## Décision

Le guard normal reste inchangé et continue de bloquer toutes les suppressions et tous les remplacements critiques.

Un workflow séparé, approuvé via l'environnement GitHub `test`, peut retirer uniquement le marqueur tainted de l'adresse :

```text
module.agent_api_facade.aws_lambda_function.this
```

La récupération est autorisée seulement lorsque :

- le plan contient exactement une opération destructive ;
- `action_reason` vaut `replace_because_tainted` ;
- aucun `replace_path` fournisseur n'est présent ;
- le nom, le rôle, le handler, le runtime et l'architecture sont identiques avant/après ;
- la Lambda AWS réelle est `Active`, avec `LastUpdateStatus=Successful` ;
- son nom, rôle, handler, runtime et architecture correspondent au contrat Terraform.

Après `terraform untaint`, un nouveau plan est produit et analysé par le guard normal. Le workflow de récupération n'applique aucune infrastructure.

## Conséquences

- aucun bypass permanent n'est ajouté au guard ;
- aucune destruction Lambda n'est autorisée automatiquement ;
- la mutation du state est explicite, approuvée et auditée ;
- le déploiement normal doit ensuite être relancé avec `action=apply` ;
- toute divergence réelle continue de bloquer la récupération.
