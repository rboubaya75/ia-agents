# ADR-0007 — Récupération contrôlée d'une Lambda de test marquée tainted

## Statut

Accepté pour l'environnement `test`.

## Contexte

Des apply Terraform partiels ont créé des fonctions Lambda avant d'échouer dans une étape suivante. Terraform a marqué ces objets comme `tainted`, puis les plans suivants ont proposé leur remplacement. Le guard de Phase 3 a correctement bloqué ces opérations sur des ressources critiques.

Les seules fonctions concernées par cette procédure sont :

```text
module.agent_api_facade.aws_lambda_function.this
module.trip_tools_lambda.aws_lambda_function.this
```

## Décision

Le guard normal reste inchangé et continue de bloquer toutes les suppressions et tous les remplacements critiques.

Un workflow séparé, approuvé via l'environnement GitHub `test`, peut retirer uniquement le marqueur tainted de la Lambda explicitement sélectionnée (`facade` ou `trip-tools`).

La récupération est autorisée seulement lorsque :

- le plan contient exactement une opération destructive ;
- cette opération concerne l'adresse exacte sélectionnée ;
- `action_reason` vaut `replace_because_tainted` ;
- aucun `replace_path` fournisseur n'est présent ;
- le nom, le rôle, le handler, le runtime et l'architecture sont identiques avant/après ;
- la Lambda AWS réelle est `Active`, avec `LastUpdateStatus=Successful` ;
- son nom, rôle, handler, runtime et architecture correspondent au contrat Terraform.

Après `terraform untaint`, un nouveau plan est produit avec les mêmes paramètres de préservation AgentCore que la pipeline Terraform normale, puis analysé par le guard normal. Le workflow de récupération n'applique aucune infrastructure.

## Conséquences

- aucun bypass permanent n'est ajouté au guard ;
- aucune destruction Lambda n'est autorisée automatiquement ;
- la mutation du state est explicite, ciblée, approuvée et auditée ;
- le déploiement normal doit ensuite être relancé avec `action=plan`, puis `action=apply` ;
- toute divergence réelle ou toute seconde opération destructive continue de bloquer la récupération.
