# Runbook CI/CD — Secure AgentCore V1 test

- **Branche :** `migration/secure-agentcore-v1`
- **Environnement :** `test`
- **Architecture :** ADR-0005

## 1. Pipeline qualité

```text
.github/workflows/test-application-quality.yml
```

Déclenchement : push/PR sur le code Runtime, façade, frontend, scripts, tests ou workflows applicatifs. Ce workflow expose également `workflow_call` afin d’être exécuté comme gate obligatoire par la pipeline de déploiement sur le même commit.

Contrôles :

- Python 3.12 `py_compile` ;
- vérification des imports Runtime réels ;
- tests unitaires façade, Runtime, contrat de déploiement et Trip Tools ;
- `pip check` et `pip-audit --strict` ;
- frontend `npm ci` ;
- `npm audit --omit=dev --audit-level=high` ;
- frontend lint ;
- frontend build.

Aucune promotion ne doit être effectuée si cette pipeline est rouge. La pipeline application ne peut pas atteindre le job de déploiement tant que le workflow qualité réutilisable n’est pas vert sur le même SHA.

## 2. Pipeline Terraform

```text
.github/workflows/test-terraform-stack.yml
```

Actions :

```text
plan
apply
destroy-plan
destroy
```

Contrôles : Gitleaks, lockfile, fmt, init, validate, plan, analyse JSON et artifacts immuables du plan.

Chaque plan publie pendant 14 jours :

```text
tfplan                         plan binaire appliqué
tfplan.txt                     représentation lisible
tfplan.json                    représentation machine
tfplan-summary.md              compteurs et décision de sécurité
tfplan-metadata.json           SHA Git, stack, run ID, version Terraform et SHA-256 du plan
```

Le script `scripts/terraform_plan_guard.py` bloque automatiquement toute suppression ou tout remplacement d’une ressource critique : Cognito, CloudFront, S3, DynamoDB, API Gateway, Lambda, IAM, AgentCore Runtime, Memory, Gateway, target MCP, resource policies, KMS et WAF.

### Plan

Lancer `workflow_dispatch` avec :

```text
stack_path = infra/environments/test
action = plan
```

Revue obligatoire :

- aucun destroy inattendu ;
- aucune réactivation Gateway-first ;
- Runtime IAM-only ;
- façade Lambda active ;
- target Trip Tools présent ;
- frontend security headers policy présente ;
- IAM sans `bedrock-agentcore:*`.

### Apply

Après revue du plan :

```text
action = apply
```

Le job apply télécharge l’artifact nommé avec le SHA Git et l’identifiant d’exécution, vérifie `tfplan-metadata.json`, recalcule le SHA-256 du plan puis applique exactement le binaire publié. Aucun nouveau `terraform plan` n’est exécuté dans le job apply.

L’environnement GitHub `test` et ses reviewers restent obligatoires avant l’apply.

## 3. Pipeline application

```text
.github/workflows/test-application-deploy.yml
```

Modes :

- `frontend-only` ;
- `image-only` ;
- `runtime-only` ;
- `full`.

Pour clôturer la V1 :

```text
deploy_mode = full
image_tag = test
endpoint_name = default
confirm_deploy = true
```

Le contrôle du contrat sécurisé est obligatoire et non désactivable. L’ancien input `enforce_secure_facade` et le wrapper Gateway-first ont été supprimés.

La pipeline doit :

1. valider la demande de déploiement et ses inputs ;
2. exécuter la pipeline qualité réutilisable sur le même SHA ;
3. valider Terraform ;
4. construire l’image ARM64 immutable ;
5. produire le plan AgentCore dans le job `application-plan` ;
6. publier le plan binaire, texte, JSON, résumé et métadonnées ;
7. bloquer les destructions ou remplacements critiques ;
8. demander l’approbation de l’environnement GitHub `test` ;
9. vérifier puis appliquer exactement le plan publié dans `application-apply-and-publish` ;
10. relire tous les outputs du chemin V1 ;
11. exécuter `validate_secure_facade_contract.py --enforce` ;
12. construire le frontend avec `VITE_AGENT_INVOKE_URL` ;
13. publier S3 et invalider CloudFront.

Pour `runtime-only` et `full`, aucun `terraform apply` ne peut s’exécuter sans l’artifact `agentcore-tfplan-<git-sha>-<run-id>` produit par le job de plan du même workflow.

## 4. Outputs à contrôler

```bash
terraform -chdir=infra/environments/test output
```

Obligatoires :

```text
service_url
agent_invoke_url
agent_api_facade_function_name
agent_api_facade_role_arn
agent_runtime_arn
agentcore_memory_id
agentcore_gateway_mcp_url
agentcore_trip_tools_target_id
trip_tools_lambda_function_name
secure_facade_ready = true
```

`agent_runtime_invoke_url` est technique et ne doit jamais être injecté dans le frontend.

## 5. Smoke tests

### CORS

```bash
curl -i -X OPTIONS "$AGENT_INVOKE_URL" \
  -H "Origin: https://<cloudfront-domain>" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
```

### Sécurité

- sans JWT : 401/403 ;
- JWT invalide : 401/403 ;
- mauvais client : rejet ;
- `actorId`, `userId`, `tenantId`, `trustedIdentity`, `groups` : rejet ;
- URL Runtime directe depuis un autre rôle : AccessDenied.

### Fonctionnel

- réponse simple ;
- Memory User A/User B ;
- création d’un trip ;
- liste du trip ;
- lecture du trip ;
- mise à jour du trip ;
- impossibilité de lire un trip d’un autre utilisateur.

### Logs

Vérifier :

```text
facade_invocation
agent_invocation
gateway_tools_loaded
tool_identity_injection
trip_tool_invocation
```

Absence obligatoire de JWT, prompt brut, actorId brut, sessionId brut et secret.

## 6. Limite de temps

Le chemin synchrone doit répondre en moins de 28 secondes. Si Memory ou un tool dépasse régulièrement cette limite, ne pas augmenter artificiellement le timeout : ouvrir un ADR pour une architecture asynchrone.

## 7. Destroy

```text
action = destroy
confirm_destroy = true
```

Uniquement pour l’environnement `test`, après vérification des données et artifacts nécessaires. Le destroy-plan publie les mêmes preuves pendant 14 jours en mode `report-only`; le job destroy vérifie le SHA Git, le run ID, la stack et le SHA-256 du plan avant application.
