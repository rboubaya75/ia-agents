# ADR-0003 — Provisioning AgentCore natif Terraform

- **Statut :** accepté avec amendement ADR-0004
- **Date initiale :** 2026-07-08
- **Amendement :** 2026-07-12
- **Périmètre :** environnement `test`, branche par défaut `migration/secure-agentcore-v1`

## Contexte

Le control plane AgentCore doit être provisionné de manière auditable et reproductible. Le provider AWS Terraform expose les ressources natives nécessaires :

- `aws_bedrockagentcore_memory` ;
- `aws_bedrockagentcore_gateway` ;
- `aws_bedrockagentcore_agent_runtime` ;
- `aws_bedrockagentcore_agent_runtime_endpoint` ;
- `aws_bedrockagentcore_gateway_target` lorsque des targets sont créés.

La décision de provisioning Terraform reste valide. La décision d’ingress Gateway-first initialement associée à cet ADR a en revanche été remplacée par ADR-0004.

## Décision

Le control plane AgentCore est provisionné avec Terraform natif, pas avec un script Boto3 propriétaire ni avec des valeurs manuelles servant de source de vérité.

La stack `infra/environments/test` suit deux étapes :

### 1. Socle Terraform

Avec `enable_agentcore_control_plane=false` :

- frontend S3 privé et CloudFront ;
- Cognito web auth ;
- DynamoDB trips ;
- ECR Runtime ;
- IAM ;
- Amazon API Gateway HTTP API.

### 2. Control plane AgentCore

Après publication de l’image Runtime, avec `enable_agentcore_control_plane=true` :

- AgentCore Memory ;
- AgentCore Runtime ;
- AgentCore Runtime Endpoint ;
- AgentCore Gateway MCP pour les tools.

La cible V1 d’ingress approuvée est :

```text
Browser
  -> Amazon API Gateway HTTP API
  -> HTTP proxy direct
  -> AgentCore Runtime JWT
```

Le chemin tools est :

```text
AgentCore Runtime
  -> AgentCore Gateway MCP
  -> targets tools autorisés
```

AgentCore Gateway ingress et son HTTP target vers Runtime ne sont plus des composants nominaux.

## Raisons du choix Terraform natif

- état Terraform unique et auditable ;
- plan/apply/destroy contrôlés ;
- détection de drift ;
- suppression des placeholders manuels ;
- séparation entre socle infra et cycle de vie de l’image Runtime ;
- outputs réutilisables par la pipeline applicative ;
- destruction test contrôlée.

## Pipeline applicative

Le workflow applicatif doit :

1. lire les outputs Terraform du socle ;
2. construire l’image `linux/arm64` ;
3. pousser une image immuable vers ECR ;
4. appliquer le control plane AgentCore ;
5. relire les outputs Runtime, Memory, MCP Gateway et API Gateway ;
6. valider le contrat V1 ;
7. construire le frontend avec l’URL API Gateway `/agent/invoke` ;
8. publier sur S3 et invalider CloudFront.

## Outputs attendus

Après application complète :

- `agent_runtime_arn` ;
- `agent_runtime_invoke_url` — output technique, non nominal pour le frontend ;
- `agentcore_memory_id` ;
- `agentcore_gateway_mcp_url` ;
- `service_url` ;
- `agent_invoke_url` — URL nominale frontend après remédiation API Gateway.

## Sécurité et garde-fous

- Le rôle Runtime doit être restreint aux modèles, logs, Memory, Gateway et secrets nécessaires.
- Le rôle Gateway doit être restreint aux targets tools explicitement autorisés.
- Les policies wildcard actuelles sont une dette P0 à supprimer avant clôture V1.
- ECR doit rester immutable avec scan on push.
- GitHub Actions utilise OIDC AWS, sans clés d’accès longues durées.
- Un apply ne doit jamais être exécuté sans revue du plan.

## Critères d’acceptation

- `terraform fmt -check -recursive` passe ;
- `terraform init -backend=false` passe ;
- `terraform validate` passe ;
- le plan ne détruit pas involontairement le control plane existant ;
- l’image Runtime est disponible dans ECR ;
- Runtime, Endpoint, Memory et MCP Gateway sont présents ;
- API Gateway expose `/agent/invoke` vers Runtime direct ;
- le frontend utilise l’URL API Gateway ;
- aucun step nominal n’active la Lambda Facade ;
- aucun step nominal ne recrée AgentCore Gateway comme ingress utilisateur.

## Travaux restants V1

- implémenter le proxy API Gateway vers Runtime direct ;
- aligner le mode d’authentification MCP entre Terraform et `phase_4.py` ;
- créer au moins un target tool réel et le tester ;
- supprimer les IAM wildcards non nécessaires ;
- ajouter access logs, throttling et alarmes API Gateway ;
- exécuter les tests contractuels JWT, identité, CORS et tools ;
- mettre à jour les noms de scripts et outputs hérités de `gateway_first`.
