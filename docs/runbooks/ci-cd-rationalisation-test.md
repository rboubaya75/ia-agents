# Runbook CI/CD — Secure AgentCore V1 test

- **Branche :** `migration/secure-agentcore-v1`
- **Environnement :** `test`
- **Architecture :** ADR-0005

## 1. Pipeline qualité

```text
.github/workflows/test-application-quality.yml
```

Déclenchement : push/PR sur le code Runtime, façade, frontend, scripts ou tests.

Contrôles :

- Python 3.12 `py_compile` ;
- tests unitaires façade ;
- contrat de sécurité Runtime ;
- tests Trip Tools ;
- frontend `npm ci` ;
- frontend lint ;
- frontend build.

Aucune promotion ne doit être effectuée si cette pipeline est rouge.

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

Contrôles : Gitleaks, lockfile, fmt, init, validate, plan et artifacts du plan.

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

L’environnement GitHub `test` et ses reviewers restent obligatoires.

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
enforce_secure_facade = true
confirm_deploy = true
```

La pipeline doit :

1. valider Terraform ;
2. construire l’image ARM64 immutable ;
3. appliquer Runtime, resource policies, Gateway et target ;
4. vérifier le contrat sécurisé ;
5. construire le frontend avec `VITE_AGENT_INVOKE_URL` ;
6. publier S3 et invalider CloudFront.

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

Uniquement pour l’environnement `test`, après vérification des données et artifacts nécessaires.
