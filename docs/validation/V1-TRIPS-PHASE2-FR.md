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

| Contrat | Niveau | Statut | Preuve |
|---|---|---|---|
| A lit son voyage | unité/contrat | PASS PROUVÉ | clé `{userId=A, tripId}` et `ConsistentRead=true` |
| B lit un `tripId` de A | unité/contrat | PASS PROUVÉ | clé construite avec B, réponse générique |
| pagination A page 1 puis page 2 | unité/contrat | PASS PROUVÉ | IDs distincts et `ExclusiveStartKey` exact |
| curseur A présenté par B | unité/contrat | PASS PROUVÉ | rejet avant KMS et DynamoDB |
| `actorHash` altéré | unité/contrat | PASS PROUVÉ | rejet avant KMS et DynamoDB |
| `tripId` seul altéré | unité/contrat | PASS PROUVÉ | `KMSInvalidMacException` convertie en `validation_error` |
| curseur expiré | unité/contrat | PASS PROUVÉ | rejet avant KMS et DynamoDB |
| token V2 non signé | unité/contrat | PASS PROUVÉ | demande de recommencer la pagination |
| update sans confirmation | unité/contrat | PASS PROUVÉ | aucune lecture ni transaction DynamoDB |
| B modifie un voyage de A | unité/contrat | PASS PROUVÉ | aucune transaction |
| replay create | unité/contrat | PASS PROUVÉ | un seul essai d’écriture, `replayed=true` |
| payload différent avec même opération | régression | PASS PROUVÉ | `idempotency_conflict` |
| update atomique et replay tardif | régression | PASS PROUVÉ | transaction et ledger TTL existants |
| packaging Terraform et clé HMAC | contrat IaC | PASS PROUVÉ | handler, clé KMS, IAM et variables attendus |
| logs redacted | unité/contrat | PASS PROUVÉ | absence des identifiants bruts |

## 8. Preuves automatisées archivées

Code validé :

```text
e376d2f45980c663a1e4ad03422a56e64f771bf5
```

Gate Trip Tools Phase 2 :

```text
Workflow : Test Trip Tools Phase 2
Run ID   : 29492100107
Artefact : trip-tools-phase2-e5d6de7b59544b53b126d25ffbd936be8561a8f3-29492100107
Digest   : sha256:6f0d10d0c9869511e70783b899c3351d75c62c5d3e49faca749978861f197871
Expire   : 14 octobre 2026
```

Plan Terraform et analyse de sécurité :

```text
Workflow : Test Terraform Stack
Run ID   : 29492100085
Artefact : tfplan-e5d6de7b59544b53b126d25ffbd936be8561a8f3-29492100085
Digest   : sha256:5543ebbfe493181d13ce3a92a39bada24338a930613d13d85f48dbd08d629e35
Expire   : 30 juillet 2026
```

Le plan Terraform doit être copié dans le stockage de preuves V1 avant son expiration GitHub. L’artefact fonctionnel Phase 2 est conservé pendant 90 jours.

## 9. Gate CI dédiée

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

## 10. Scénarios AWS E2E restant à exécuter

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

## 11. Critères de passage à la Phase 3

La Phase 3 ne doit commencer qu’après :

- CI complète verte ;
- review de la PR ;
- merge explicite ;
- déploiement contrôlé demandé par l’utilisateur ;
- scénarios AWS E2E exécutés ;
- preuves archivées ;
- matrice sans échec non traité.

Aucun merge, déploiement, `terraform apply` ou `terraform destroy` n’est inclus dans cette PR.
