# V1 — Validation Trips Phase 2

> Périmètre : `get_trip`, `update_trip`, isolation A/B, idempotence, pagination signée et preuves redacted.
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
- réponse générique pour un voyage inexistant ou appartenant à un autre utilisateur ;
- confirmation serveur obligatoire avant mutation ;
- replay idempotent avec le même `operationId` ;
- conflit si le même `operationId` est réutilisé avec un autre payload ;
- pagination sans doublon et avec `ExclusiveStartKey` prouvé ;
- rejet d’un curseur provenant d’un autre utilisateur ;
- rejet de toute altération de `tripId`, expiration ou MAC ;
- logs exploitables sans identifiant personnel brut.

## 2. PR #13 annulée et cause

La PR #13 liait le curseur à `actorHash`, mais ne protégeait pas l’intégrité du `tripId`. Un utilisateur pouvait conserver son empreinte et remplacer uniquement le `tripId` par un autre UUID valide. La requête restait dans sa propre partition, mais pouvait démarrer à une position arbitraire.

Cette PR remplace donc le token non signé par un token V3 authentifié avec AWS KMS.

## 3. Contrat du token V3

Le token exposé au client contient uniquement :

```json
{
  "v": 3,
  "actorHash": "empreinte tronquée",
  "tripId": "UUID",
  "expiresAt": 1780000000,
  "mac": "HMAC encodé en base64url"
}
```

La MAC KMS est calculée sur le payload canonique suivant :

```json
{
  "v": 3,
  "userId": "identité serveur complète",
  "tripId": "UUID",
  "expiresAt": 1780000000
}
```

Le `userId` brut n’est jamais placé dans le token. Il est toutefois inclus dans la donnée authentifiée afin qu’une collision éventuelle de l’empreinte tronquée ne permette pas de réutiliser un curseur entre utilisateurs.

### Ordre des contrôles

1. structure JSON et version exactes ;
2. correspondance de `actorHash` avec l’utilisateur authentifié ;
3. format UUID du `tripId` ;
4. expiration du token ;
5. vérification KMS de la MAC ;
6. construction de l’`ExclusiveStartKey` ;
7. requête DynamoDB dans la partition serveur.

Aucune requête DynamoDB n’est exécutée si l’un de ces contrôles échoue.

## 4. Clé KMS dédiée

Le module Terraform crée une clé KMS :

```text
KeySpec  : HMAC_256
KeyUsage : GENERATE_VERIFY_MAC
Algorithm: HMAC_SHA_256
```

Le rôle Lambda possède uniquement les opérations cryptographiques nécessaires sur cette clé :

```text
kms:GenerateMac
kms:VerifyMac
```

La matière secrète HMAC ne sort jamais de KMS et n’est stockée ni dans le code, ni dans une variable Terraform, ni dans l’environnement Lambda.

Les variables non sensibles exposées au Runtime sont :

```text
TRIPS_CURSOR_HMAC_KEY_ID
TRIPS_CURSOR_TTL_SECONDS=900
```

Les curseurs expirent après quinze minutes. Les tokens historiques V1 et V2 sont rejetés avec une demande explicite de recommencer la pagination.

## 5. Wrapper déployable

Le handler Lambda est :

```text
lambda_function_phase2.lambda_handler
```

Le wrapper :

- délègue `create_trip` et `update_trip` au handler durci existant ;
- conserve la confirmation et le ledger d’idempotence existants ;
- effectue `get_trip` avec `ConsistentRead=true` ;
- authentifie les tokens de pagination avec KMS ;
- conserve la suppression des champs internes dans les réponses ;
- ajoute des événements redacted pour les lectures, mutations, validations et conflits.

## 6. Événements d’observabilité

```text
trip_tool_invocation
trip_read
trips_listed
trip_mutation_outcome
trip_validation_rejected
trip_idempotency_conflict
```

Les événements peuvent contenir `request_id`, des empreintes tronquées, des compteurs et des booléens de résultat. Ils ne doivent pas contenir :

```text
userId brut
tripId brut
operationId brut
prompt
réponse du modèle
JWT
Authorization
clé ou MAC brute
```

## 7. Matrice des contrats automatisés

| Contrat | Niveau | Statut dans la PR | Preuve attendue |
|---|---|---|---|
| A lit son voyage | unité/contrat | À VALIDER PAR CI | clé `{userId=A, tripId}` et `ConsistentRead=true` |
| B lit un `tripId` de A | unité/contrat | À VALIDER PAR CI | clé construite avec B, réponse générique |
| pagination A page 1 puis page 2 | unité/contrat | À VALIDER PAR CI | IDs distincts et `ExclusiveStartKey` exact |
| curseur A présenté par B | unité/contrat | À VALIDER PAR CI | rejet avant KMS et DynamoDB |
| `actorHash` altéré | unité/contrat | À VALIDER PAR CI | rejet avant KMS et DynamoDB |
| `tripId` seul altéré | unité/contrat | À VALIDER PAR CI | `KMSInvalidMacException` convertie en `validation_error` |
| curseur expiré | unité/contrat | À VALIDER PAR CI | rejet avant KMS et DynamoDB |
| token V2 non signé | unité/contrat | À VALIDER PAR CI | demande de recommencer la pagination |
| update sans confirmation | unité/contrat | À VALIDER PAR CI | aucune lecture ni transaction DynamoDB |
| B modifie un voyage de A | unité/contrat | À VALIDER PAR CI | aucune transaction |
| replay create | unité/contrat | À VALIDER PAR CI | un seul essai d’écriture, `replayed=true` |
| payload différent avec même opération | régression | À VALIDER PAR CI | `idempotency_conflict` |
| update atomique et replay tardif | régression | À VALIDER PAR CI | transaction et ledger TTL existants |
| packaging Terraform et clé HMAC | contrat IaC | À VALIDER PAR CI | handler, clé KMS, IAM et variables attendus |
| logs redacted | unité/contrat | À VALIDER PAR CI | absence des identifiants bruts |

## 8. Gate CI dédiée

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
6. archivage des logs et de la matrice JSON pendant 90 jours.

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

## 9. Scénarios AWS E2E restant à exécuter

Ces contrôles restent `NON TESTÉ E2E` tant qu’un déploiement contrôlé n’a pas été exécuté.

| Scénario | Statut | Preuve minimale |
|---|---|---|
| A appelle `get_trip` sur son voyage | NON TESTÉ E2E | réponse API, `requestId`, `trip_read found=true` |
| B appelle `get_trip` avec le `tripId` de A | NON TESTÉ E2E | réponse générique et actor hashes distincts |
| update sans confirmation depuis l’agent | NON TESTÉ E2E | aucune transaction DynamoDB |
| update confirmé persistant | NON TESTÉ E2E | réponse, item DynamoDB et événement outcome |
| replay du même update | NON TESTÉ E2E | `replayed=true`, un seul effet métier |
| perte de réponse après create puis retry | NON TESTÉ E2E | un seul item et même `operationId` |
| même opération avec payload différent | NON TESTÉ E2E | conflit contrôlé |
| plusieurs pages sans doublon | NON TESTÉ E2E | IDs par page et curseurs |
| token A réutilisé par B | NON TESTÉ E2E | rejet avant KMS et DynamoDB |
| `tripId` du token altéré | NON TESTÉ E2E | rejet KMS avant DynamoDB |
| token expiré | NON TESTÉ E2E | rejet et reprise depuis la première page |
| audit CloudWatch redacted | NON TESTÉ E2E | requête Logs Insights et extraits minimaux |

## 10. Critères de passage à la Phase 3

La Phase 3 ne doit commencer qu’après :

- CI complète verte ;
- review de la PR ;
- merge explicite ;
- déploiement contrôlé demandé par l’utilisateur ;
- scénarios AWS E2E exécutés ;
- preuves archivées ;
- matrice sans échec non traité.

Aucun merge, déploiement, `terraform apply` ou `terraform destroy` n’est inclus dans cette PR.
