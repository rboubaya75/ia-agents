# LLD — WildRydes Secure AgentCore V1

- **Version :** 4.1
- **Date :** 2026-07-13
- **Branche :** `migration/secure-agentcore-v1`
- **Environnement :** `test`
- **ADR actif :** ADR-0005

## 1. Contrat frontend

Endpoint :

```http
POST https://<api-gateway>/agent/invoke
Authorization: Bearer <cognito-access-token>
Content-Type: application/json
```

Payload :

```json
{
  "prompt": "Planifie un voyage à Tokyo",
  "sessionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

Contraintes :

- prompt : chaîne non vide, maximum 4 000 caractères ;
- sessionId : 33 à 128 caractères `[A-Za-z0-9._:-]` ;
- aucun autre champ accepté ;
- endpoint configuré par `VITE_AGENT_INVOKE_URL` ;
- aucune URL AgentCore Runtime dans le bundle navigateur.

Le `sessionId` frontend est un identifiant fonctionnel externe. Il est conservé dans la réponse HTTP mais n’est jamais utilisé directement comme clé de session Runtime.

## 2. API Gateway

Module :

```text
infra/modules/api_gateway_agent_ingress
```

Configuration :

```text
POST /agent/invoke
JWT authorizer Cognito
AWS_PROXY Lambda payload 2.0
integration timeout 29 s
CORS CloudFront uniquement
throttling 5 req/s, burst 10
access logs CloudWatch
```

Les modes `security_facade_enabled` et `gateway_first_enabled` sont exclusifs. Gateway-first reste historique et désactivé.

## 3. Lambda Security Facade

Module :

```text
infra/modules/agent_api_facade
```

Runtime : Python 3.12 ARM64, mémoire 256 MiB, timeout 28 s, concurrence réservée 5.

### Validation JWT

La façade relit les claims déjà validés par API Gateway et exige :

```text
token_use = access
client_id = Cognito web client ID
sub présent
```

### Session externe et session technique

Après validation du payload et des claims :

```text
externalSessionId = payload.sessionId
actorId = claims.sub
internalSessionId = "sid-v1-" + SHA-256(
  JSON(["agentcore-session-v1", actorId, externalSessionId])
)
```

La sérialisation JSON est canonique, encodée en UTF-8 et utilise les séparateurs compacts. Le résultat a le format :

```text
sid-v1-[a-f0-9]{64}
```

Propriétés attendues :

- déterministe pour un même `actorId` et un même `externalSessionId` ;
- distinct pour deux acteurs utilisant le même `externalSessionId` ;
- compatible avec la contrainte Runtime de 33 à 128 caractères sûrs ;
- ne contient ni `actorId` brut ni `externalSessionId` brut ;
- versionné par le préfixe `sid-v1-`.

### Payload interne

```json
{
  "prompt": "...",
  "sessionId": "sid-v1-<sha256>",
  "trustedIdentity": {
    "actorId": "<claims.sub>"
  }
}
```

La façade utilise `internalSessionId` à deux endroits :

```text
InvokeAgentRuntime.runtimeSessionId
payload.sessionId
```

Elle retourne au navigateur :

```json
{
  "message": "...",
  "sessionId": "<externalSessionId>"
}
```

### IAM

```text
bedrock-agentcore:InvokeAgentRuntime
```

est autorisé uniquement sur :

```text
<runtime-arn>
<runtime-arn>/*
```

`InvokeAgentRuntimeForUser` est explicitement refusé.

## 4. AgentCore Runtime

Fichier :

```text
deploy-agentcore/agents/phase_4.py
```

Image : Python 3.12, `linux/arm64`, utilisateur non root.

Configuration :

```text
MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
MEMORY_ID=<memory-id>
GATEWAY_URL=<mcp-gateway-url>
GATEWAY_AUTH_MODE=aws_iam
REQUIRE_MCP_TOOLS=true
MAX_PROMPT_CHARS=4000
```

Runtime accepte exactement :

```text
prompt
sessionId technique
trustedIdentity.actorId
```

Il ne décode plus de JWT et ne lit plus de header d’identité. Sa resource policy autorise uniquement le rôle de la façade.

Le `sessionId` technique reçu est utilisé par :

```python
FileSessionManager(session_id=session_id, session_dir=SESSION_DIR)
```

Le Runtime ne connaît jamais le `sessionId` externe. Deux acteurs utilisant la même valeur externe ont donc des sessions Strands locales distinctes sur une instance Runtime chaude.

## 5. Bedrock

Actions IAM :

```text
bedrock:InvokeModel
bedrock:InvokeModelWithResponseStream
```

Ressources :

- profil d’inférence EU exact ;
- modèle de fondation Claude Haiku 4.5 exact dans les régions européennes de destination.

## 6. Memory

Actions :

```text
bedrock-agentcore:RetrieveMemoryRecords
bedrock-agentcore:CreateEvent
```

Namespace :

```text
travel/{actorId}/preferences
```

Les erreurs Memory sont journalisées de manière redacted. L’isolation User A/User B doit être prouvée end-to-end.

L’isolation Memory par `actorId` est indépendante de l’isolation de session technique. Les deux contrôles sont nécessaires :

```text
Memory durable      -> namespace actorId
Session Strands      -> internalSessionId actor-scoped
Runtime invocation   -> runtimeSessionId actor-scoped
```

## 7. Client MCP IAM

Le Runtime construit un client HTTPX dont chaque requête est signée :

```text
SigV4 service = bedrock-agentcore
region = eu-west-3
credentials = Runtime execution role
```

Le transport `streamable_http_client` reçoit ce client HTTPX. Le Gateway MCP refuse tout principal autre que le rôle Runtime.

## 8. Target Trip Tools

Terraform :

```text
infra/environments/test/trip_tools.tf
infra/modules/trip_tools_lambda
```

Target MCP Lambda :

```text
create_trip
get_trips
get_trip
update_trip
```

La Gateway assume son rôle IAM et peut invoquer uniquement la Lambda Trips exacte.

## 9. Injection d’identité tool

Avant tout appel Trips :

```python
input["userId"] = actorId
```

Une valeur `userId` proposée par le modèle est toujours écrasée.

La Lambda Trips valide :

- `userId` et `tripId` ;
- longueurs des chaînes ;
- dates `YYYY-MM-DD` ;
- `endDate >= startDate` ;
- champs autorisés ;
- existence lors des mises à jour.

## 10. DynamoDB

```text
PK = userId
SK = tripId
PAY_PER_REQUEST
SSE enabled
PITR enabled
```

IAM Lambda :

```text
dynamodb:GetItem
dynamodb:PutItem
dynamodb:Query
dynamodb:UpdateItem
```

sur la table exacte uniquement.

## 11. CloudFront et S3

- bucket privé ;
- Block Public Access ;
- OAC SigV4 ;
- versioning ;
- AES256 ;
- HTTPS redirect ;
- CSP autorisant uniquement le frontend, Cognito régional et API Gateway régionale ;
- HSTS, anti-framing, nosniff, Referrer-Policy et Permissions-Policy.

## 12. Logs et traces

Les rôles Runtime couvrent :

```text
/aws/bedrock-agentcore/*
/aws/bedrock-agentcore/*:log-stream:*
X-Ray PutTraceSegments / PutTelemetryRecords
```

Les logs applicatifs contiennent uniquement des identifiants hashés, types d’erreur, statuts et durées.

La façade journalise :

```text
actor_hash
session_hash
runtime_session_hash
```

Ces valeurs sont des empreintes tronquées. Aucun token, prompt, `actorId`, `externalSessionId` ou `internalSessionId` brut ne doit être journalisé.

## 13. Tests automatisés

```text
tests/unit/test_agent_api_facade.py
tests/unit/test_runtime_behavior.py
tests/unit/test_runtime_security_contract.py
tests/unit/test_trip_tools.py
```

Les tests façade couvrent notamment :

- même acteur + même session externe = même session technique ;
- acteurs différents + même session externe = sessions techniques différentes ;
- format `sid-v1-<64 hex>` ;
- absence de l’identifiant externe dans le payload Runtime ;
- `runtimeSessionId` identique au `payload.sessionId` technique ;
- réponse HTTP conservant le `sessionId` externe.

Pipeline :

```text
.github/workflows/test-application-quality.yml
```

Elle compile les sources Python 3.12, exécute les tests unitaires et lance `npm ci`, lint et build.

## 14. Contrat de déploiement

```text
scripts/validate_secure_facade_contract.py
```

Il exige :

- `service_url` HTTPS non AgentCore ;
- `agent_invoke_url=/agent/invoke` ;
- URL Runtime technique distincte ;
- Runtime ARN ;
- façade Lambda ;
- Memory ;
- Gateway MCP ;
- Lambda Trip Tools ;
- target Trip Tools ;
- `secure_facade_ready=true`.

## 15. Gates de sortie

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform plan
python -m unittest discover -s tests/unit -p 'test_*.py' -v
npm ci
npm run lint
npm run build
```

Puis :

- déploiement `full` ;
- CORS/JWT navigateur ;
- invocation Runtime directe refusée ;
- User A et User B utilisant le même `sessionId` externe obtiennent des sessions Runtime distinctes ;
- même utilisateur et même `sessionId` externe conservent la continuité de session ;
- Memory A/B isolée ;
- quatre tools MCP validés ;
- absence de données sensibles dans les logs ;
- latence sous 28 secondes.
