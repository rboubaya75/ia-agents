# ADR-0003 — Provisioning AgentCore natif Terraform

- Statut : accepté
- Date : 2026-07-08
- Remplace : contrat manuel `agentcore_gateway_contract` et tfvars P0 manuels
- Complète : ADR-0002 Gateway-first avec Amazon API Gateway

## Contexte

L'architecture cible WildRydes conserve Amazon API Gateway comme ingress web public et utilise Amazon Bedrock AgentCore Gateway pour le trafic agentique.

Le blocage CI/CD `enforce_gateway_first=true` est volontaire : il empêche un déploiement `runtime-only` ou `full` si les ressources AgentCore réelles ne sont pas provisionnées. Ce blocage ne doit pas être contourné par des valeurs manuelles ou des placeholders.

La vérification du provider AWS Terraform montre que les ressources natives AgentCore existent :

- `aws_bedrockagentcore_memory`
- `aws_bedrockagentcore_gateway`
- `aws_bedrockagentcore_agent_runtime`
- `aws_bedrockagentcore_agent_runtime_endpoint`
- `aws_bedrockagentcore_gateway_target`

## Décision

Nous provisionnons le control plane AgentCore avec Terraform natif, pas avec un script Boto3 propriétaire ni avec des variables tfvars manuelles.

La stack `infra/environments/test` est organisée en deux temps :

1. **Base Terraform** avec `enable_agentcore_control_plane=false` :
   - S3 / CloudFront frontend
   - Cognito web auth
   - DynamoDB trips
   - ECR runtime image repository
   - IAM runtime role
   - IAM gateway role
   - Amazon API Gateway HTTP API

2. **Control plane AgentCore Terraform** avec `enable_agentcore_control_plane=true` après publication de l'image Runtime :
   - AgentCore Memory
   - AgentCore Runtime
   - AgentCore Runtime Endpoint
   - AgentCore Gateway HTTP ingress
   - AgentCore Gateway HTTP target vers Runtime
   - AgentCore Gateway MCP tools

La pipeline applicative construit et pousse l'image Runtime dans ECR, puis relance Terraform avec :

```bash
terraform plan \
  -var="enable_agentcore_control_plane=true" \
  -var="agentcore_image_tag=<resolved_tag>" \
  -var="agent_runtime_endpoint_name=<endpoint>"
```

## Raison du choix

Cette approche donne :

- un état Terraform unique pour le control plane AgentCore ;
- un plan/apply/destroy auditable ;
- une détection de drift native ;
- une suppression du provisioning manuel ;
- une séparation claire entre base infra et runtime image lifecycle ;
- un maintien du gate `enforce_gateway_first=true` comme garde-fou de qualité.

## Décisions structurantes

### Deux AgentCore Gateways natifs

Nous utilisons deux Gateways AgentCore distincts :

1. `ingress` sans `protocol_type`, pour le target HTTP vers AgentCore Runtime.
2. `tools_mcp` avec `protocol_type = "MCP"`, pour les tools MCP appelés par le Runtime.

Cette séparation évite de mélanger les contraintes HTTP target et MCP target dans le même gateway.

### API Gateway reste l'ingress web

Le navigateur appelle Amazon API Gateway HTTP API. API Gateway conserve :

- Cognito JWT authorizer ;
- CORS limité au domaine CloudFront ;
- throttling/logging extensibles ;
- futur WAF/custom domain.

API Gateway route `/agent/invoke` vers l'AgentCore Gateway ingress quand `gateway_url` existe.

### Lambda Facade reste hors chemin nominal

La Lambda Facade n'est pas utilisée par la pipeline nominale. Toute réactivation doit passer par une ADR séparée avec justification sécurité, audit ou compatibilité.

## Conséquences

- Le workflow Terraform peut appliquer la base sans image Runtime existante.
- Le workflow applicatif est responsable du build/push image, puis du apply Terraform AgentCore control plane.
- Le déploiement `runtime-only` exige un tag image existant.
- Le déploiement `full` génère un tag immutable, pousse l'image, puis applique AgentCore nativement.
- `enforce_gateway_first=true` reste activé par défaut.

## Critères d'acceptation

- `terraform validate` passe sur `infra/environments/test`.
- Le premier `terraform apply` base crée ECR, IAM, Cognito, API Gateway, S3/CloudFront et DynamoDB.
- Le workflow applicatif `full` pousse l'image puis crée Runtime, Memory, Gateways et HTTP target.
- Les outputs suivants sont non vides après control plane apply :
  - `agentcore_gateway_url`
  - `agentcore_gateway_mcp_url`
  - `agentcore_memory_id`
  - `agent_runtime_arn`
- `POST /agent/invoke` passe par API Gateway puis AgentCore Gateway HTTP target.
- Runtime reçoit `MEMORY_ID`, `GATEWAY_URL` et `GATEWAY_AUTH_MODE=aws_iam`.
- Aucun step nominal ne déploie ou active `Lambda Facade -> Runtime`.

## Travaux restants

- Ajouter les MCP tool targets métiers dès que les Lambda/API tools sont stabilisés.
- Restreindre les IAM policies wildcard utilisées pendant le P0.
- Ajouter un smoke test E2E : API Gateway -> AgentCore Gateway -> Runtime.
- Ajouter un smoke test tools : Runtime -> AgentCore Gateway MCP -> tool.
- Vérifier la propagation d'identité : `actorId = Cognito sub`, aucun champ identité accepté depuis le body client.
