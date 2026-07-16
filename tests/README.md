# Stratégie de tests industriels — Secure AgentCore V1

## 1. Objet

Ce répertoire constitue le référentiel de test du projet WildRydes Secure AgentCore V1.

L’objectif n’est pas seulement de vérifier que le code fonctionne dans le cas nominal. La stratégie cherche à démontrer que le système reste sûr, déterministe et observable lors des situations à risque :

- panne ou fermeture du transport MCP ;
- réponse perdue après une mutation ;
- appels concurrents au provider MCP ;
- expiration du budget de temps ;
- tentative d’accès IAM depuis un mauvais principal ;
- injection de contexte de confiance par le client ;
- fuite d’identifiants ou de contenu métier dans les logs ;
- renouvellement d’un token Cognito ;
- replay avec le même `operationId` ;
- altération ou réutilisation d’un curseur de pagination.

Les tests automatisés ne remplacent pas la réception AWS E2E. Ils rendent les contrats vérifiables avant tout déploiement et produisent des preuves reproductibles.

## 2. Principes obligatoires

### 2.1 Traçabilité par risque

Chaque test industriel porte un identifiant stable dans son nom :

```text
V1-RES-001
V1-IAM-002
V1-OBS-003
V1-PERF-001
V1-FE-002
```

Convention Python :

```python
def test_v1_res_001_retry_occurs_once_before_any_mutation(self):
    ...
```

L’identifiant est extrait automatiquement par `scripts/run_industrial_test_suite.py` et placé dans l’artefact JSON.

### 2.2 Déterminisme

Un test industriel doit :

- ne dépendre ni d’Internet ni d’un compte AWS réel dans une PR ;
- ne pas utiliser de `sleep` pour synchroniser un résultat ;
- contrôler explicitement l’heure, les erreurs et les réponses externes ;
- utiliser des valeurs sentinelles reconnaissables ;
- produire le même résultat sur Ubuntu 24.04 et Python 3.12 ;
- nettoyer les clients, handlers et patches créés pendant le test.

### 2.3 Test des frontières, pas des SDK

Les SDK AWS, MCP et HTTP ne sont pas réimplémentés dans les tests.

Les doubles de test sont placés uniquement aux frontières suivantes :

- appel AgentCore Runtime depuis la façade ;
- connexion AgentCore Gateway MCP depuis le Runtime ;
- appels DynamoDB ou KMS depuis les Trip Tools ;
- appels Memory depuis les hooks ;
- `fetch` depuis le frontend.

Le code métier, les règles de retry, les validations, les clés d’idempotence et la construction des événements sont exécutés réellement.

### 2.4 Fail closed

Un résultat ambigu ne doit pas être converti en succès.

Exemples :

- une erreur Runtime autre que `AccessDenied` ne prouve pas une frontière IAM ;
- une panne réseau produit un `FAIL`, pas un `SKIP` ;
- une réponse MCP perdue après le début d’une mutation interdit le replay complet de l’agent ;
- une expiration du budget bloque la seconde tentative ;
- un test sans identifiant de risque apparaît comme `UNMAPPED` et doit être corrigé.

### 2.5 Protection des preuves

Les artefacts de test ne doivent jamais contenir :

```text
JWT
Authorization
refresh token
prompt utilisateur
réponse du modèle
actorId brut
userId brut
sessionId brut
operationId brut
tripId brut
message d’erreur AWS brut
secret ou clé KMS
```

Les éléments acceptés sont :

- `requestId` de corrélation ;
- identifiants hashés ;
- nom du cas ;
- statut ;
- durée ;
- type d’exception ;
- code AWS non sensible ;
- SHA Git et métadonnées de CI.

## 3. Organisation

```text
tests/
├── unit/                  # tests unitaires et contrats locaux rapides
├── industrial/            # fault injection, concurrence, IAM et observabilité
└── README.md              # présent référentiel

scripts/
└── run_industrial_test_suite.py

.github/workflows/
└── test-industrial-quality.yml
```

### `tests/unit`

Couvre notamment :

- validation des payloads ;
- contrats façade et Runtime ;
- isolation Memory ;
- idempotence et pagination Trips ;
- compatibilité des SDK ;
- contrats Terraform ciblés ;
- règles frontend statiques.

### `tests/industrial`

Couvre les interactions entre plusieurs responsabilités et les comportements sous défaillance :

- lifecycle et concurrence MCP ;
- retry borné ;
- non-rejeu après mutation ;
- budget de deadline ;
- schémas d’événements redacted ;
- chaîne de timeouts ;
- frontières IAM complètes ;
- invariants du retry Cognito côté frontend.

### Tests AWS E2E

Les tests AWS actifs restent manuels et soumis à confirmation. Ils utilisent uniquement l’environnement `test` et archivent leurs preuves séparément.

## 4. Matrice industrielle actuelle

| Identifiant | Risque | Niveau | Résultat attendu |
|---|---|---|---|
| `V1-RES-001` | rupture MCP avant mutation | fault injection | une reconnexion unique, même requête |
| `V1-RES-002` | seconde panne MCP | fault injection | aucune troisième tentative |
| `V1-RES-003` | erreur non transport | fault injection | aucun reset MCP |
| `V1-RES-004` | panne après mutation confirmée | fault injection | aucun replay de l’agent |
| `V1-RES-005` | deadline trop courte pour retry | fault injection | seconde tentative bloquée |
| `V1-RES-006` | initialisations MCP concurrentes | concurrence | un seul client et une seule découverte |
| `V1-RES-007` | reset du provider | lifecycle | fermeture et cache vidé |
| `V1-IAM-001` | invocation directe Runtime | contrat IaC | façade seule autorisée, autres refusés |
| `V1-IAM-002` | invocation directe Gateway | contrat IaC | rôle Runtime seul autorisé |
| `V1-IAM-003` | privilèges de la façade | contrat IaC | Runtime exact, délégation utilisateur refusée |
| `V1-IAM-004` | privilèges Trip Tools | contrat IaC | table exacte et clé HMAC exacte |
| `V1-OBS-001` | fuite dans le log d’invocation | contrat dynamique | hashes, durée, type d’erreur uniquement |
| `V1-OBS-002` | fuite lors de l’injection tool | contrat dynamique | contexte écrasé, log redacted |
| `V1-OBS-003` | événement manquant | contrat statique | catalogue opérationnel présent |
| `V1-PERF-001` | timeout incohérent | contrat de budget | timeouts strictement emboîtés |
| `V1-FE-001` | double retry 401 ou nouvelle opération | contrat frontend | un retry, même `operationId` |
| `V1-FE-002` | exposition du Runtime au navigateur | contrat frontend | seule l’URL API Gateway est référencée |

## 5. Pyramide de test

```text
                 Réception navigateur / AWS E2E
                    peu fréquente, coûteuse

              Tests industriels et fault injection
             concurrence, résilience, IAM, preuves

          Tests unitaires et contrats de composants
       rapides, nombreux, exécutés sur chaque changement

     Lint, compilation, audit, analyse Terraform et secrets
```

Un défaut doit être détecté au niveau le moins coûteux capable de le prouver honnêtement.

Exemple :

- la présence d’une resource policy se vérifie hors ligne ;
- le refus effectif du principal CI se vérifie en AWS ;
- la cause exacte du refus repose sur les deux preuves combinées.

## 6. Exécution locale sous Ubuntu 24.04

Depuis la racine du dépôt :

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r deploy-agentcore/requirements.txt
python -m pip check
```

Tests unitaires :

```bash
python -m unittest discover -s tests/unit -v
```

Tests industriels avec preuve JSON :

```bash
PYTHONHASHSEED=0 TZ=UTC \
python scripts/run_industrial_test_suite.py \
  --output industrial-test-results.json
```

Exécution directe d’un fichier :

```bash
python tests/industrial/test_runtime_resilience.py -v
python tests/industrial/test_quality_boundaries.py -v
```

Compilation préalable :

```bash
python -m py_compile \
  scripts/run_industrial_test_suite.py \
  tests/industrial/_industrial_helpers.py \
  tests/industrial/test_runtime_resilience.py \
  tests/industrial/test_quality_boundaries.py
```

## 7. Artefact JSON

Le runner produit un fichier du type :

```json
{
  "schemaVersion": 1,
  "gitSha": "<sha>",
  "suite": {
    "name": "Secure AgentCore V1 Industrial Test Suite",
    "testsRun": 17,
    "statusCounts": {
      "PASS": 17
    },
    "successful": true
  },
  "cases": [
    {
      "caseId": "V1-RES-001",
      "testId": "test_runtime_resilience.RuntimeResilienceIndustrialTests...",
      "status": "PASS",
      "durationMs": 1.234,
      "errorType": null,
      "skipReason": null
    }
  ]
}
```

Le JSON ne contient volontairement aucun traceback. Les logs détaillés restent dans un artefact CI distinct et doivent eux aussi utiliser uniquement des données de test.

## 8. Politique des statuts

| Statut | Signification |
|---|---|
| `PASS` | assertion exécutée et satisfaite |
| `FAIL` | assertion métier ou sécurité non satisfaite |
| `ERROR` | test interrompu par une erreur inattendue |
| `SKIP` | dépendance explicitement absente ; interdit par défaut dans la gate industrielle |
| `UNMAPPED` | nom de test sans identifiant de risque ; dette à corriger |
| `NON TESTÉ E2E` | scénario AWS ou navigateur non encore exécuté |
| `PASS PROUVÉ E2E` | scénario exécuté et preuve archivée |

Le runner échoue sur `FAIL`, `ERROR` et `SKIP`. L’option `--allow-skips` existe uniquement pour un diagnostic local et ne doit pas être utilisée dans la gate de PR.

## 9. Règles d’écriture

Chaque nouveau test doit suivre Arrange / Act / Assert :

```python
def test_v1_res_008_example(self) -> None:
    # Arrange
    dependency = Mock(...)

    # Act
    result = system_under_test(...)

    # Assert
    self.assertEqual(result, expected)
```

Règles supplémentaires :

1. une méthode teste un risque principal ;
2. le nom décrit le comportement observable ;
3. les données de test portent un préfixe `industrial-` ou une valeur sentinelle ;
4. les exceptions sont vérifiées par type et contrat, pas par traceback complet ;
5. les appels externes sont comptés précisément ;
6. les retries vérifient le nombre maximal de tentatives ;
7. les tests concurrents utilisent des primitives de synchronisation ou des locks réels, jamais un délai arbitraire ;
8. les assertions IAM portent sur les actions et ressources exactes ;
9. un test de redaction doit injecter une valeur sensible sentinelle et prouver son absence ;
10. une preuve statique ne doit jamais être présentée comme une preuve E2E.

## 10. CI industrielle

Le workflow dédié :

```text
.github/workflows/test-industrial-quality.yml
```

Il exécute :

1. checkout avec actions épinglées par SHA ;
2. Python 3.12 sur Ubuntu 24.04 ;
3. installation des dépendances Runtime verrouillées ;
4. compilation des sources de test ;
5. exécution de la suite industrielle ;
6. génération de la preuve JSON ;
7. archivage des logs et du JSON pendant 90 jours.

La gate ne possède aucune permission AWS et ne réalise aucun appel réseau actif vers l’environnement `test`.

## 11. Critères de revue d’une PR de tests

Une PR est recevable lorsque :

- chaque test correspond à un risque documenté ;
- le test échoue réellement lorsque le contrat ciblé est rompu ;
- les doubles sont placés à une frontière externe ;
- le test est déterministe et indépendant de l’ordre d’exécution ;
- aucune donnée sensible n’est présente dans les fixtures ou les artefacts ;
- le fichier README est mis à jour si un nouveau domaine ou statut apparaît ;
- la suite unitaire et la suite industrielle sont vertes ;
- le plan Terraform reste vert lorsque les contrats IaC changent ;
- les limites entre contrat hors ligne et preuve E2E restent explicites.

## 12. Prochaines extensions

Les prochains tests industriels à ajouter seront :

- simulation IAM d’une autre table DynamoDB ;
- simulation IAM d’un modèle Bedrock non autorisé ;
- appel direct du Gateway par un principal autre que le Runtime ;
- analyse CloudWatch Logs Insights avec liste d’interdiction ;
- navigateur réel pour CORS, 401 et renouvellement Cognito ;
- perte de réponse après mutation et replay E2E ;
- rupture du transport MCP avant et après mutation en environnement AWS ;
- mesure p50, p95 et maximum de la latence ;
- campagne Memory A, nouvelle session A et utilisateur B ;
- test de charge contrôlé avec limites de concurrence documentées.

Ces scénarios ne doivent être activés qu’avec une demande explicite de test sur l’environnement AWS.
