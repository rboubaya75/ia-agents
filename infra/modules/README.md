# Terraform modules

Ce dossier contiendra les modules Terraform industrialises de la landing zone applicative WildRydes Secure AgentCore V1.

Les specifications detaillees, les sous-modules et les criteres d acceptation sont documentes dans :

```text
docs/specifications/module-specifications-fr.md
```

## Regles de module

Chaque module doit contenir au minimum :

```text
versions.tf
variables.tf
locals.tf
main.tf
outputs.tf
README.md
```

Ajouter `iam.tf`, `logging.tf`, `alarms.tf` ou `policies.tf` lorsque le module le justifie.

## Modules cibles V1

| Module | Domaine |
|---|---|
| `cognito_web_auth` | Identity |
| `frontend_static_site` | Frontend hosting |
| `api_gateway_agent_ingress` | External ingress |
| `lambda_agent_facade` | Agent invocation facade |
| `ecr_agent` | Agent container repository |
| `agentcore_runtime` | AgentCore Runtime |
| `agentcore_memory` | AgentCore Memory |
| `agentcore_gateway` | AgentCore Gateway MCP |
| `lambda_trip_tools` | Business tools |
| `dynamodb_trips` | Data persistence |
| `secrets_manager_app` | Secrets |
| `iam_facade_role` | IAM facade |
| `iam_runtime_role` | IAM runtime |
| `iam_gateway_role` | IAM gateway |
| `iam_trip_tools_role` | IAM tools |
| `observability` | Logs metrics dashboards |
| `budgets` | Cost control |
| `agent_rag_knowledge_base` | Future RAG disabled by default |

## Definition of Done

Un module est pret lorsqu il respecte les points suivants :

- variables documentees ;
- outputs documentes ;
- tags communs appliques ;
- IAM least privilege ;
- aucun secret expose ;
- Terraform fmt et validate OK ;
- criteres d acceptation couverts ;
- dependances explicites ;
- tests ou procedure de validation disponibles.
