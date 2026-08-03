variable "project_name" {
  type        = string
  description = "Project name."
  default     = "wildrydes"
}

variable "environment" {
  type        = string
  description = "Environment name."
  default     = "test"
}

variable "region" {
  type        = string
  description = "AWS region."
  default     = "eu-west-3"
}

variable "enable_rag" {
  type        = bool
  description = "Enable the future RAG Knowledge Layer."
  default     = false
}

variable "cognito_invited_users" {
  type = map(object({
    email       = string
    enabled     = optional(bool, true)
    given_name  = optional(string)
    family_name = optional(string)
  }))
  description = "Invitation-only Cognito users for the test environment. Leave empty unless explicitly onboarding approved users."
  default     = {}
}

variable "agentcore_image_tag" {
  type        = string
  description = "AgentCore Runtime image tag to deploy from ECR."
  default     = "test"
}

variable "agentcore_model_id" {
  type        = string
  description = "Bedrock model or inference profile identifier for the AgentCore runtime in eu-west-3."
  default     = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "enable_agentcore_control_plane" {
  type        = bool
  description = "Create the native AgentCore Runtime, Memory, Gateways and Gateway HTTP target. Enable only after the runtime image exists in ECR."
  default     = false
}

variable "agent_runtime_endpoint_name" {
  type        = string
  description = "AgentCore Runtime endpoint name managed by Terraform."
  default     = "default"
}

variable "agentcore_memory_event_expiry_days" {
  type        = number
  description = "Number of days after which AgentCore Memory events expire."
  default     = 30

  validation {
    condition     = var.agentcore_memory_event_expiry_days >= 7 && var.agentcore_memory_event_expiry_days <= 365
    error_message = "agentcore_memory_event_expiry_days must be between 7 and 365."
  }
}

variable "agent_runtime_ready" {
  type        = bool
  description = "Legacy fallback only. Do not use for the nominal Gateway-first path."
  default     = false
}

variable "agent_runtime_arn" {
  type        = string
  description = "Legacy fallback only. Do not use for the nominal Gateway-first path."
  default     = ""
}

variable "p0_agentcore_gateway_url" {
  type        = string
  description = "Deprecated legacy/P0 override. Do not use for the native Gateway-first path."
  default     = ""

  validation {
    condition     = var.p0_agentcore_gateway_url == "" || can(regex("^https://", var.p0_agentcore_gateway_url))
    error_message = "p0_agentcore_gateway_url must be empty or start with https://."
  }
}

# ---------------------------------------------------------------------------
# V2-LLD-001 §16.4 — socle plateforme ECS/Fargate V2.
# ---------------------------------------------------------------------------

variable "enable_ecs_platform" {
  type        = bool
  description = "Provisionne le socle V2 (VPC, ECS, ALB interne, service fastapi). Faux par defaut : aucun cout tant que l'image FastAPI n'existe pas (V2-LLD-001 §3)."
  default     = false
}

variable "enable_ingestion_service" {
  type        = bool
  description = "Cible V3 (V2-ADR-019). Jamais vrai en V2 : la regle 1 du garde de plan le verifie."
  default     = false
}

variable "enable_agentcore_privatelink" {
  type        = bool
  description = "Vrai une fois l'endpoint PrivateLink AgentCore Runtime confirme disponible (precondition 2 de V2-LLD-001 §16.5). Faux conserve l'egress 0.0.0.0/0 conditionnel de sg-fastapi."
  default     = false
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR du VPC plateforme (V2-LLD-001 §2.1)."
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "Zones de disponibilite du socle (V2-LLD-001 §2.1)."
  default     = ["eu-west-3a", "eu-west-3b"]
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR des subnets publics, NAT Gateway uniquement (V2-LLD-001 §2.2)."
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR des subnets prives, taches Fargate et ALB interne (V2-LLD-001 §2.2)."
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "nat_gateway_count" {
  type        = number
  description = "Nombre de NAT Gateway. Un seul est le compromis de cout accepte en test (V2-LLD-001 §2.1)."
  default     = 1
}

variable "fastapi_image" {
  type        = string
  description = "Image du conteneur fastapi, pinnee par digest (V2-LLD-001 §4.1)."
  default     = ""
}

variable "fastapi_secrets" {
  type        = map(string)
  description = "Secrets injectes dans le conteneur fastapi : nom de variable vers ARN Secrets Manager. Jamais de variable d'environnement en clair (V2-LLD-001 §4.1)."
  default     = {}
}

variable "log_retention_days" {
  type        = number
  description = "Retention des groupes de journaux ECS (V2-LLD-001 §4.1)."
  default     = 30
}

variable "alb_idle_timeout_seconds" {
  type        = number
  description = "Idle timeout de l'ALB interne. Lie a sse_keepalive_seconds par l'invariant de V2-LLD-001 §7.3, verifie sur le plan par la regle 3 du garde."
  default     = 240
}

variable "sse_keepalive_seconds" {
  type        = number
  description = "Periode du keep-alive SSE, egalement consommee par le conteneur fastapi comme source unique (V2-LLD-001 §7.3, §16.4)."
  default     = 15
}

variable "alb_certificate_arn" {
  type        = string
  description = "ARN du certificat ACM du listener HTTPS de l'ALB interne (V2-LLD-001 §7, §8)."
  default     = ""
}

variable "apigw_response_transfer_mode" {
  type        = string
  description = "Mode de transfert de reponse d'API Gateway (V2-LLD-001 §7.0, V2-ADR-011). Le repli documente est emulated, declare au client dans l'evenement meta."
  default     = "STREAM"

  validation {
    condition     = contains(["STREAM", "BUFFERED"], var.apigw_response_transfer_mode)
    error_message = "apigw_response_transfer_mode doit valoir STREAM ou BUFFERED."
  }
}

variable "cognito_issuer" {
  type        = string
  description = "Valeur attendue du claim iss. Un parametre, jamais deduit du token recu (V2-LLD-001 §7.1.3)."
  default     = ""
}

variable "cognito_app_client_id" {
  type        = string
  description = "Valeur attendue du claim aud. Un parametre, jamais deduit du token recu (V2-LLD-001 §7.1.3)."
  default     = ""
}

variable "jwks_cache_ttl_seconds" {
  type        = number
  description = "Duree de vie du cache JWKS (V2-LLD-001 §7.1.4)."
  default     = 3600
}

variable "jwks_stale_tolerance_seconds" {
  type        = number
  description = "Tolerance d'usage d'un JWKS perime lorsque l'endpoint est injoignable. V2-ADR-020 la borne en heures, jamais en jours ; regle 5 du garde de plan."
  default     = 21600
}

variable "jwks_refresh_min_interval_seconds" {
  type        = number
  description = "Intervalle minimal entre deux rafraichissements JWKS, anti-amplification (V2-LLD-001 §7.1.4)."
  default     = 60
}

variable "logs_kms_key_arn" {
  type        = string
  description = "CMK des groupes de journaux ECS. Vide : le module cree la sienne (V2-LLD-001 §12.1)."
  default     = ""
}

variable "erasure_audit_log_group_name" {
  type        = string
  description = "Groupe de journaux d'audit d'effacement couvert par la meme CMK. Il ne vit pas sous /ecs/, il est donc liste explicitement (V2-LLD-001 §12.1.1)."
  default     = ""
}

variable "fastapi_agentcore_runtime_arn" {
  type        = string
  description = "ARN du Runtime AgentCore invoque par fastapi. Vide retire le statement du role de tache (V2-LLD-001 §5.1)."
  default     = ""
}

variable "knowledge_base_arn" {
  type        = string
  description = "ARN de la Knowledge Base cible de bedrock-agent-runtime:Retrieve (V2-LLD-001 §5.1)."
  default     = ""
}

variable "knowledge_base_data_source_arn" {
  type        = string
  description = "ARN de la source de donnees KB cible des actions de job d'ingestion (V2-LLD-001 §5.1)."
  default     = ""
}

variable "fastapi_dynamodb_table_arns" {
  type        = list(string)
  description = "Tables et index DynamoDB accessibles a fastapi, hors magasin de commandes qui porte son propre statement plus etroit (V2-LLD-001 §5.1)."
  default     = []
}

variable "fastapi_commands_table_arns" {
  type        = list(string)
  description = "Magasin de commandes et son index by-operation. Droits volontairement plus etroits : GetItem, Query et UpdateItem seulement (V2-LLD-001 §5.1)."
  default     = []
}

variable "documents_bucket_arn" {
  type        = string
  description = "Bucket S3 des documents source (V2-LLD-001 §5.1)."
  default     = ""
}

variable "documents_cmk_arn" {
  type        = string
  description = "CMK protegeant le bucket documents (V2-LLD-001 §5.1)."
  default     = ""
}
