# Spécifications modules — WildRydes Secure AgentCore V1

**Version :** 1.0  
**Périmètre :** environnement `test`  
**Branche par défaut phase test :** `migration/secure-agentcore-v1`  
**Branche future prod :** `main`  
**Objectif :** définir les modules, sous-modules, responsabilités, dépendances et critères d’acceptation pour industrialiser la solution.

---

## 1. Principes de modularisation

Chaque module Terraform doit respecter les principes suivants :

- responsabilité unique ;
- inputs explicites ;
- outputs consommables par d’autres modules ;
- tags communs ;
- compatibilité environnement `test` et future `prod` ;
- aucune valeur sensible en clair ;
- IAM least privilege ;
- activation optionnelle des capacités futures ;
- critères d’acceptation testables.

Structure recommandée pour chaque module :

```text
infra/modules/<module_name>/
├── versions.tf
├── variables.tf
├── locals.tf
├── main.tf
├── outputs.tf
├── iam.tf
├── logging.tf
└── README.md
```

Tous les modules ne nécessitent pas forcément `iam.tf` ou `logging.tf`, mais la structure doit rester prévisible.

---

## 2. Catalogue des modules

| Domaine | Module | Statut V1 |
|---|---|---|
| Identity | `cognito_web_auth` | V1 |
| Frontend | `frontend_static_site` | V1 |
| Ingress | `api_gateway_agent_ingress` | V1 |
| Facade | `lambda_agent_facade` | V1 |
| Agent packaging | `ecr_agent` | V1 |
| AgentCore | `agentcore_runtime` | V1 |
| AgentCore | `agentcore_memory` | V1 |
| AgentCore | `agentcore_gateway` | V1 |
| Tools | `lambda_trip_tools` | V1 |
| Data | `dynamodb_trips` | V1 |
| Secrets | `secrets_manager_app` | V1 |
| IAM | `iam_facade_role` | V1 |
| IAM | `iam_runtime_role` | V1 |
| IAM | `iam_gateway_role` | V1 |
| IAM | `iam_trip_tools_role` | V1 |
| Observability | `observability` | V1 |
| Cost | `budgets` | V1 |
| Future RAG | `agent_rag_knowledge_base` | Future, disabled by default |

---

## 3. Module `cognito_web_auth`

### Objectif

Créer l’authentification web utilisateur pour le frontend WildRydes.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| user_pool | créer le User Pool |
| user_pool_client | créer le client web |
| groups | groupes applicatifs futurs |
| invited_users | support du modèle invitation-only |
| outputs | exposer IDs nécessaires au frontend/API Gateway |

### Inputs

- `project_name`
- `environment`
- `callback_urls`
- `logout_urls`
- `password_policy`
- `mfa_mode`
- `tags`

### Outputs

- `user_pool_id`
- `user_pool_arn`
- `user_pool_client_id`
- `issuer_url`
- `jwks_url`

### Critères d’acceptation

- User Pool créé avec nom environnementé.
- Client web créé sans secret côté navigateur.
- Email vérifié ou flux équivalent documenté.
- Self-signup public désactivé ou contrôlé selon décision V1.
- Les outputs permettent de configurer API Gateway et frontend.
- Aucun mot de passe ou secret utilisateur n’est commité.

---

## 4. Module `frontend_static_site`

### Objectif

Héberger le frontend React/Vite de façon sécurisée.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| s3_site_bucket | bucket privé frontend |
| cloudfront_distribution | distribution HTTPS |
| origin_access_control | accès CloudFront vers S3 |
| cache_policy | politiques de cache |
| build_config_outputs | variables de build frontend |

### Inputs

- `project_name`
- `environment`
- `allowed_origins`
- `api_base_url`
- `cognito_user_pool_id`
- `cognito_client_id`
- `tags`

### Outputs

- `frontend_bucket_name`
- `cloudfront_distribution_id`
- `cloudfront_domain_name`
- `frontend_url`

### Critères d’acceptation

- Bucket non public.
- CloudFront utilise OAC ou mécanisme équivalent.
- HTTPS enforced.
- SPA fallback configuré.
- `VITE_API_BASE_URL` configuré.
- Aucun `VITE_AGENT_ARN` exposé.

---

## 5. Module `api_gateway_agent_ingress`

### Objectif

Exposer l’API applicative externe pour le frontend.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| http_api | API Gateway HTTP API |
| jwt_authorizer | validation JWT Cognito |
| routes | routes `/agent/invoke` et health |
| cors | politique CORS |
| throttling | limites de débit |
| access_logs | logs d’accès redacted |

### Inputs

- `project_name`
- `environment`
- `lambda_facade_invoke_arn`
- `cognito_issuer`
- `cognito_audience`
- `allowed_origins`
- `tags`

### Outputs

- `api_id`
- `api_endpoint`
- `agent_invoke_url`
- `authorizer_id`

### Critères d’acceptation

- `/agent/invoke` protégé par JWT.
- Requête sans token rejetée.
- Token invalide rejeté.
- CORS limité au frontend autorisé.
- Logs activés sans JWT ni payload sensible.
- Endpoint API utilisé par le frontend.

---

## 6. Module `lambda_agent_facade`

### Objectif

Créer la Lambda Facade entre API Gateway et AgentCore Runtime.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| source_package | packaging code Lambda |
| lambda_function | fonction Facade |
| alias | alias stable `live` ou équivalent |
| env_vars | configuration runtime |
| log_group | logs et rétention |
| permissions | permission API Gateway invoke |

### Inputs

- `project_name`
- `environment`
- `runtime_arn`
- `runtime_endpoint_arn`
- `iam_role_arn`
- `log_retention_days`
- `timeout_seconds`
- `memory_size`
- `tags`

### Outputs

- `lambda_function_name`
- `lambda_function_arn`
- `lambda_invoke_arn`
- `lambda_alias_arn`

### Critères d’acceptation

- Lambda extrait `claims.sub`.
- Lambda rejette `actorId`, `userId`, `tenantId`, `trustedIdentity` provenant du client.
- Lambda construit `trustedIdentity.actorId`.
- Lambda invoque AgentCore Runtime avec IAM.
- Erreurs normalisées.
- Logs redacted.
- Tests négatifs d’identité passés.

---

## 7. Module `ecr_agent`

### Objectif

Gérer le repository ECR contenant l’image AgentCore Runtime.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| repository | ECR repo |
| lifecycle_policy | rétention images |
| scanning | scan image |
| outputs | URI image |

### Inputs

- `project_name`
- `environment`
- `image_retention_count`
- `scan_on_push`
- `tags`

### Outputs

- `repository_name`
- `repository_url`
- `repository_arn`

### Critères d’acceptation

- Repository ECR créé.
- Scan on push activé si disponible.
- Lifecycle policy configurée.
- L’image Runtime référence `phase_4.py`.
- Aucune image non nécessaire conservée indéfiniment.

---

## 8. Module `agentcore_runtime`

### Objectif

Créer et configurer AgentCore Runtime.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| runtime | AgentCore Runtime |
| runtime_endpoint | endpoint runtime |
| runtime_config | variables et secrets |
| execution_role_binding | rôle runtime custom |
| validation_outputs | outputs pour tests contractuels |

### Inputs

- `project_name`
- `environment`
- `agent_image_uri`
- `runtime_execution_role_arn`
- `memory_id`
- `gateway_url`
- `model_id`
- `secret_arns`
- `tags`

### Outputs

- `runtime_arn`
- `runtime_endpoint_arn`
- `runtime_id`
- `runtime_name`

### Critères d’acceptation

- Runtime créé via Terraform.
- `auto_create_execution_role` désactivé si applicable.
- Rôle custom utilisé.
- Runtime exécute `phase_4.py`.
- Aucune policy `AdministratorAccess` attachée.
- Contract validation Lambda -> Runtime réussie.

---

## 9. Module `agentcore_memory`

### Objectif

Créer AgentCore Memory pour stocker les préférences utilisateur.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| memory_resource | Memory |
| namespace_policy | convention namespace |
| iam_permissions | permissions runtime |
| outputs | IDs/ARNs |

### Inputs

- `project_name`
- `environment`
- `memory_name`
- `retention_policy`
- `tags`

### Outputs

- `memory_id`
- `memory_arn`
- `memory_name`

### Critères d’acceptation

- Memory créée.
- Namespace applicatif documenté : `travel/{actorId}/preferences`.
- Runtime peut lire/écrire uniquement selon permissions prévues.
- Isolation utilisateur testée.
- Aucun secret stocké en Memory.

---

## 10. Module `agentcore_gateway`

### Objectif

Créer AgentCore Gateway pour exposer les tools MCP internes.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| gateway | Gateway MCP |
| auth | auth Gateway |
| lambda_targets | targets Lambda tools |
| tool_schemas | définition tools |
| outputs | endpoint et identifiers |

### Inputs

- `project_name`
- `environment`
- `auth_mode`
- `lambda_tool_arns`
- `tool_schemas`
- `tags`

### Outputs

- `gateway_id`
- `gateway_arn`
- `gateway_url`
- `target_ids`

### Critères d’acceptation

- Gateway créé.
- Tools `create_trip`, `get_trips`, `get_trip`, `update_trip` exposés.
- Auth configurée.
- Runtime peut appeler Gateway.
- Frontend ne peut pas appeler Gateway directement.

---

## 11. Module `lambda_trip_tools`

### Objectif

Créer les Lambda métier pour les opérations trips.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| package | packaging code |
| functions | fonctions tools |
| schemas | input/output schemas |
| log_groups | logs et rétention |
| permissions | invocation par Gateway |

### Inputs

- `project_name`
- `environment`
- `dynamodb_table_name`
- `iam_role_arn`
- `log_retention_days`
- `tags`

### Outputs

- `create_trip_lambda_arn`
- `get_trips_lambda_arn`
- `get_trip_lambda_arn`
- `update_trip_lambda_arn`

### Critères d’acceptation

- Chaque tool fonctionne en test positif.
- Chaque tool refuse une identité arbitraire.
- DynamoDB condition expressions utilisées si nécessaire.
- Logs redacted.
- IAM limité à la table trips test.

---

## 12. Module `dynamodb_trips`

### Objectif

Créer la table DynamoDB des trips.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| table | table principale |
| keys | PK/SK |
| encryption | chiffrement |
| pitr | point-in-time recovery |
| streams | streams si requis |
| alarms | alarmes capacité/erreurs |

### Inputs

- `project_name`
- `environment`
- `billing_mode`
- `pitr_enabled`
- `stream_enabled`
- `tags`

### Outputs

- `table_name`
- `table_arn`
- `stream_arn`

### Critères d’acceptation

- Table créée avec nom environnementé.
- PITR activé.
- SSE activé.
- PK/SK conformes au modèle V1.
- Accès cross-user impossible.
- Tags standards présents.

---

## 13. Module `secrets_manager_app`

### Objectif

Gérer les secrets applicatifs nécessaires au Runtime et au Gateway.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| secret_definitions | création secrets |
| secret_policy | resource policies si nécessaires |
| rotation_placeholder | préparation rotation future |
| outputs | ARNs secrets |

### Inputs

- `project_name`
- `environment`
- `secret_names`
- `kms_key_id`
- `tags`

### Outputs

- `secret_arns`
- `secret_names`

### Critères d’acceptation

- Secrets créés sans valeur sensible hardcodée dans Terraform.
- ARNs exposés aux modules IAM.
- Accès limité aux rôles nécessaires.
- Aucune valeur de secret dans logs ou outputs.

---

## 14. Modules IAM

### Modules

```text
iam_facade_role
iam_runtime_role
iam_gateway_role
iam_trip_tools_role
```

### Objectif

Créer les rôles et policies IAM least privilege.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| trust_policy | relation de confiance |
| permissions_policy | permissions minimales |
| boundary_optional | permission boundary future |
| outputs | ARNs rôles |

### Critères d’acceptation communs

- Aucun rôle avec `AdministratorAccess`.
- Aucun wildcard large non justifié.
- Les policies sont séparées par composant.
- Le rôle Facade peut invoquer uniquement le Runtime attendu.
- Le rôle Runtime peut accéder uniquement aux services nécessaires.
- Le rôle tools peut accéder uniquement à DynamoDB test.
- Les secrets sont limités par ARN.

---

## 15. Module `observability`

### Objectif

Centraliser logs, métriques, traces, dashboards et alarmes.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| log_groups | logs et rétention |
| metrics | métriques custom |
| dashboards | dashboard test |
| alarms | alarmes erreurs/latence |
| tracing | X-Ray ou tracing équivalent |

### Inputs

- `project_name`
- `environment`
- `log_retention_days`
- `alarm_email_optional`
- `tags`

### Outputs

- `dashboard_name`
- `log_group_names`
- `alarm_names`

### Critères d’acceptation

- Logs centralisés.
- Rétention configurée.
- Dashboard test créé.
- Alarmes erreurs/latence/throttling présentes.
- Pas de données sensibles dans les logs.

---

## 16. Module `budgets`

### Objectif

Mettre en place une surveillance des coûts test.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| monthly_budget | budget mensuel test |
| alerts | alertes seuils |
| cost_tags | tags coûts |

### Inputs

- `project_name`
- `environment`
- `monthly_limit_amount`
- `notification_emails`
- `tags`

### Outputs

- `budget_name`
- `budget_id`

### Critères d’acceptation

- Budget test configuré.
- Seuils d’alerte définis.
- Tags coûts appliqués.
- Pas de budget prod dans la branche test.

---

## 17. Module futur `agent_rag_knowledge_base`

### Objectif

Préparer une future capacité RAG sans la livrer en V1.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| source_bucket | documents source |
| knowledge_base | Bedrock Knowledge Base |
| vector_store | vector store |
| ingestion | jobs ingestion |
| retrieval_policy | accès retrieval |
| eval_tests | tests retrieval |

### Inputs futurs

- `enable_rag`
- `rag_source_bucket_name`
- `rag_embedding_model_id`
- `rag_vector_store_type`
- `rag_top_k`
- `rag_allowed_document_prefixes`
- `tags`

### Outputs futurs

- `knowledge_base_id`
- `knowledge_base_arn`
- `rag_enabled`

### Critères d’acceptation V1

- `enable_rag = false` par défaut.
- Aucune ressource RAG créée si désactivé.
- Les IAM futurs sont documentés mais non actifs.
- L’architecture reste compatible avec RAG futur.

### Critères d’acceptation future activation

- corpus validé ;
- documents classifiés ;
- ingestion testée ;
- retrieval testé ;
- citations si applicable ;
- coûts validés ;
- prompt injection documentaire testé ;
- accès documentaires filtrés.

---

## 18. Module `tests`

### Objectif

Industrialiser les tests de validation technique et sécurité.

### Sous-modules logiques

| Sous-module | Responsabilité |
|---|---|
| smoke | validation minimale |
| integration | flux end-to-end |
| security | tests négatifs sécurité |
| latency | p50/p95/p99 |
| contract | Runtime invocation contract |

### Critères d’acceptation

- Smoke test passe après apply test.
- Tests d’identité négatifs passent.
- Contract validation Runtime passe.
- Latence mesurée.
- Rapport de test produit en artifact CI/CD.

---

## 19. Ordre d’implémentation recommandé

| Vague | Modules |
|---|---|
| Wave 1 | IAM, Secrets, DynamoDB |
| Wave 2 | Lambda Trip Tools |
| Wave 3 | AgentCore Gateway, Memory |
| Wave 4 | ECR Agent, AgentCore Runtime |
| Wave 5 | Lambda Facade, API Gateway |
| Wave 6 | Frontend Static Site |
| Wave 7 | Observability, Budgets |
| Wave 8 | Tests automatisés |
| Wave 9 | RAG-ready disabled |

---

## 20. Definition of Done par module

Un module est considéré terminé si :

- README module présent ;
- variables documentées ;
- outputs documentés ;
- tags appliqués ;
- IAM least privilege ;
- aucun secret exposé ;
- Terraform fmt/validate OK ;
- tests minimum présents ;
- critères d’acceptation validés ;
- dépendances explicites ;
- coût et observabilité pris en compte si applicable.

---

## 21. Critères d’acceptation globaux

La phase test est acceptable si :

- tous les modules V1 sont créés par Terraform ;
- la pipeline test peut plan/apply/destroy sous contrôle reviewer ;
- le frontend passe par API Gateway ;
- Lambda Facade protège l’identité ;
- Runtime exécute `phase_4.py` ;
- Memory, Gateway et tools fonctionnent ;
- DynamoDB isole les données ;
- logs et métriques sont exploitables ;
- coûts test visibles ;
- tests sécurité passés ;
- aucune ressource prod impactée ;
- promotion vers `main` reste manuelle.
