# V1 — Validation Trips Phase 2

> Périmètre : `get_trip`, `update_trip`, isolation A/B, idempotence, pagination et preuves redacted.
>
> Cette PR n’exécute aucun déploiement AWS et ne transforme pas un test de contrat en preuve E2E.

## 1. Objectif

La Phase 2 doit démontrer que les quatre tools Trips restent contraints à l’identité injectée par le Runtime et que les retries ne produisent pas de double effet de bord.

```text
create_trip
get_trips
get_trip
update_trip
```

Les propriétés recherchées sont :

- lecture limitée à la partition DynamoDB de l’utilisateur authentifié ;
- réponse identique pour un voyage inexistant et un voyage appartenant à un autre utilisateur ;
- confirmation serveur obligatoire avant mutation ;
- replay idempotent avec le même `operationId` ;
- conflit si le même `operationId` est réutilisé avec un autre payload ;
- pagination sans doublon ;
- rejet d’un curseur provenant d’un autre utilisateur ;
- logs exploitables sans identifiant personnel brut.

## 2. Écart corrigé

Le token de pagination historique contenait uniquement :

```json
{
  "v": 1,
  "tripId": "..."
}
```

Lors du décodage, le `userId` courant était réinjecté côté serveur. Cette conception empêchait une lecture inter-utilisateur, mais un token émis pour A pouvait influencer la position de lecture dans la partition de B au lieu d’être explicitement rejeté.

Le token Phase 2 contient désormais :

```json
{
  "v": 2,
  "actorHash": "empreinte tronquée",
  "tripId": "..."
}
```

Le wrapper compare `actorHash` avec l’empreinte de l’utilisateur authentifié avant tout appel DynamoDB. Un token de A présenté par B produit une erreur de validation et aucune requête DynamoDB.

Le token reste un curseur, pas un mécanisme d’autorisation. L’autorisation repose toujours sur l’identité serveur et la clé de partition DynamoDB.

## 3. Wrapper déployable

Le handler Lambda devient :

```text
lambda_function_phase2.lambda_handler
```

Le wrapper :

- délègue `create_trip` et `update_trip` au handler durci existant ;
- conserve la confirmation et le ledger d’idempotence existants ;
- effectue `get_trip` avec `ConsistentRead=true` ;
- lie les tokens de pagination à l’acteur authentifié ;
- conserve la suppression des champs internes dans les réponses ;
- ajoute des événements redacted pour les lectures, mutations, validations et conflits.

## 4. Événements d’observabilité

```text
trip_tool_invocation
trip_read
trips_listed
trip_mutation_outcome
trip_validation_rejected
trip_idempotency_conflict
```

Les événements peuvent contenir :

- `request_id` ;
- `actor_hash` ;
- `operation_hash` ;
- `trip_hash` ;
- `count` ;
- `has_more` ;
- `successful` ;
- `replayed`.

Ils ne doivent pas contenir :

```text
userId brut
tripId brut
operationId brut
prompt
réponse du modèle
JWT
Authorization
secret
```

## 5. Matrice des contrats automatisés

| Contrat | Niveau | Statut dans la PR | Preuve attendue |
|---|---|---|---|
| A lit son voyage | unité/contrat | À VALIDER PAR CI | clé `{userId=A, tripId}` et `ConsistentRead=true` |
| B lit un `tripId` de A | unité/contrat | À VALIDER PAR CI | clé construite avec B, réponse générique `Trip not found` |
| voyage inexistant | unité/contrat | À VALIDER PAR CI | même réponse que le cas inter-utilisateur |
| pagination A page 1 puis page 2 | unité/contrat | À VALIDER PAR CI | aucun doublon, `ExclusiveStartKey` attendu |
| curseur A présenté par B | unité/contrat | À VALIDER PAR CI | `validation_error`, aucune requête DynamoDB |
| curseur altéré | unité/contrat | À VALIDER PAR CI | `validation_error`, aucune requête DynamoDB |
| update sans confirmation | unité/contrat | À VALIDER PAR CI | aucune lecture ni transaction DynamoDB |
| B modifie un voyage de A | unité/contrat | À VALIDER PAR CI | `Trip not found`, aucune transaction |
| replay create | unité/contrat | À VALIDER PAR CI | un seul essai d’écriture, `replayed=true` |
| payload différent avec même opération | régression | À VALIDER PAR CI | `idempotency_conflict` |
| update atomique et replay tardif | régression | À VALIDER PAR CI | transaction + ledger TTL existants |
| packaging Terraform | contrat IaC | À VALIDER PAR CI | wrapper inclus et handler Phase 2 configuré |
| logs redacted | unité/contrat | À VALIDER PAR CI | absence des identifiants bruts |

## 6. Gate CI dédiée

Workflow :

```text
.github/workflows/test-trip-tools-phase2.yml
```

Il exécute :

1. installation des dépendances Runtime verrouillées ;
2. compilation Python 3.12 ;
3. tous les tests `test_trip_tools*.py` ;
4. génération d’une preuve JSON focalisée Phase 2 ;
5. vérification `terraform fmt -check` ;
6. archivage des logs et de la matrice JSON pendant 14 jours.

Commande reproductible sous Ubuntu 24.04 :

```bash
python -m pip install -r deploy-agentcore/requirements.txt
python -m unittest discover -s tests/unit -p "test_trip_tools*.py" -v
python scripts/run_trip_tools_phase2_validation.py \
  --output trip-tools-phase2-results.json
terraform fmt -check \
  infra/environments/test/trip_tools.tf \
  infra/modules/trip_tools_lambda/main.tf \
  infra/modules/trip_tools_lambda/variables.tf
```

## 7. Scénarios AWS E2E restant à exécuter

Ces contrôles restent `NON TESTÉ E2E` tant qu’un déploiement contrôlé n’a pas été exécuté.

| Scénario | Statut | Preuve minimale |
|---|---|---|
| A appelle `get_trip` sur son voyage | NON TESTÉ E2E | réponse API, `requestId`, événement `trip_read found=true` |
| B appelle `get_trip` avec le `tripId` de A | NON TESTÉ E2E | réponse générique, `trip_read found=false`, actor hashes distincts |
| update sans confirmation depuis l’agent | NON TESTÉ E2E | aucune transaction DynamoDB |
| update confirmé persistant | NON TESTÉ E2E | réponse, item DynamoDB après mutation, événement outcome |
| replay du même update | NON TESTÉ E2E | `replayed=true`, un seul effet métier |
| perte de réponse après create puis retry | NON TESTÉ E2E | un seul item voyage, même `operationId` |
| même opération avec payload différent | NON TESTÉ E2E | conflit contrôlé |
| plusieurs pages sans doublon | NON TESTÉ E2E | listes des IDs par page et curseurs |
| token A réutilisé par B | NON TESTÉ E2E | rejet avant DynamoDB |
| audit CloudWatch redacted | NON TESTÉ E2E | requête Logs Insights et extraits minimaux |

## 8. Critères de passage à la Phase 3

La Phase 3 ne doit commencer qu’après :

- CI complète verte ;
- review de la PR ;
- merge explicite ;
- déploiement contrôlé demandé par l’utilisateur ;
- scénarios AWS E2E exécutés ;
- preuves archivées ;
- matrice sans échec non traité.

Aucun merge, déploiement, `terraform apply` ou `terraform destroy` n’est inclus dans cette phase documentaire et de code.
