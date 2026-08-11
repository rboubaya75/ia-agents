variable "name_prefix" {
  type        = string
  description = "Prefix applied to every resource name, e.g. wildrydes-test."
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to every resource of the module."
  default     = {}
}

# ---------------------------------------------------------------------------
# Network (V2-LLD-001 §2)
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  type        = string
  description = "CIDR block of the platform VPC (V2-LLD-001 §2.1)."
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones hosting the subnets. Exactly two are expected (V2-LLD-001 §2.1)."
  default     = ["eu-west-3a", "eu-west-3b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "V2-LLD-001 §2.1 requires exactly two availability zones."
  }
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks of the public subnets, ordered as availability_zones (V2-LLD-001 §2.2)."
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks of the private subnets, ordered as availability_zones (V2-LLD-001 §2.2)."
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "nat_gateway_count" {
  type        = number
  description = "Number of NAT Gateways. One is the accepted cost trade-off in test; one per AZ is the production recommendation (V2-LLD-001 §2.1)."
  default     = 1

  validation {
    condition     = var.nat_gateway_count >= 1 && var.nat_gateway_count <= 2
    error_message = "nat_gateway_count must be 1 or 2, one per declared availability zone."
  }
}

variable "enable_ingestion_service" {
  type        = bool
  description = "V3 target (V2-ADR-019). Never true in V2: it gates the SQS interface endpoint that only the V3 ingestion service consumes."
  default     = false
}

variable "enable_agentcore_privatelink" {
  type        = bool
  description = "Set to true once the AgentCore Runtime PrivateLink endpoint is confirmed available (V2-LLD-001 §16.5 precondition 2). While false, sg-fastapi keeps its conditional 0.0.0.0/0 egress exception."
  default     = false
}

# ---------------------------------------------------------------------------
# ECS service fastapi (V2-LLD-001 §4.1, §9, §10)
# ---------------------------------------------------------------------------

variable "fastapi_image" {
  type        = string
  description = "Fully qualified container image for the fastapi service, pinned by digest (V2-LLD-001 §4.1)."
  default     = ""
}

variable "fastapi_cpu" {
  type        = number
  description = "Fargate task CPU units for the fastapi service (V2-LLD-001 §4.1)."
  default     = 512
}

variable "fastapi_memory" {
  type        = number
  description = "Fargate task memory in MiB for the fastapi service (V2-LLD-001 §4.1)."
  default     = 1024
}

variable "fastapi_container_port" {
  type        = number
  description = "Container port exposed by the fastapi service (V2-LLD-001 §4.1)."
  default     = 8000
}

variable "fastapi_desired_count" {
  type        = number
  description = "Desired number of fastapi tasks."
  default     = 1
}

variable "fastapi_min_capacity" {
  type        = number
  description = "Autoscaling floor for the fastapi service (V2-LLD-001 §9.1)."
  default     = 1
}

variable "fastapi_max_capacity" {
  type        = number
  description = "Autoscaling ceiling for the fastapi service (V2-LLD-001 §9.1)."
  default     = 5
}

variable "fastapi_requests_per_target" {
  type        = number
  description = "Target tracking objective on ALBRequestCountPerTarget (V2-LLD-001 §9.1)."
  default     = 50
}

variable "fastapi_secrets" {
  type        = map(string)
  description = "Secrets injected into the fastapi container, mapping environment variable name to a Secrets Manager ARN. V2-LLD-001 §4.1 expects AGENTCORE_RUNTIME_ARN, DB_TABLE_PREFIX and BEDROCK_MODEL_ID. Never plain environment variables."
  default     = {}
}

variable "log_retention_days" {
  type        = number
  description = "Retention of the ECS log groups in days (V2-LLD-001 §4.1)."
  default     = 30
}

# ---------------------------------------------------------------------------
# Ingress and timeouts (V2-LLD-001 §7.3)
# ---------------------------------------------------------------------------

variable "alb_idle_timeout_seconds" {
  type        = number
  description = "Internal ALB idle timeout. Bound to sse_keepalive_seconds by the §7.3 invariant and enforced on the plan by terraform_plan_guard rule 3."
  default     = 240

  validation {
    condition     = var.alb_idle_timeout_seconds < 300
    error_message = "V2-LLD-001 §7.3: an ALB idle timeout of 300 s or more moves the cut to API Gateway, outside our observability."
  }
}

variable "sse_keepalive_seconds" {
  type        = number
  description = "SSE keep-alive period, also consumed by the fastapi container as a single source of truth (V2-LLD-001 §7.3, §16.4)."
  default     = 15
}

variable "alb_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the internal ALB HTTPS listener (V2-LLD-001 §7)."
  default     = ""
}

# Écart assumé à §7, réservé aux environnements de test.
#
# §7 veut un listener HTTPS 443 avec certificat ACM. ACM n'émet pas de certificat pour
# le nom généré de l'ALB (`internal-*.eu-west-3.elb.amazonaws.com`) : il faudrait un
# domaine possédé et validé, ou une CA privée. Tant qu'aucun des deux n'existe, la
# seule alternative à « pas de listener du tout » est un listener en clair.
#
# Ce que cela dégrade exactement : le tronçon VPC Link → ALB circule en HTTP dans les
# sous-réseaux privés du VPC, au lieu d'être chiffré de bout en bout. TLS reste terminé
# à CloudFront puis à API Gateway ; aucun trafic en clair ne sort du VPC. Le risque
# résiduel est l'observation intra-VPC, que §6 borne déjà par les Security Groups.
#
# Le drapeau est explicite et vaut faux par défaut, précisément pour que la dégradation
# soit décidée et non constatée.
variable "alb_plaintext_listener_enabled" {
  type        = bool
  description = "Crée un listener HTTP 80 sur l'ALB interne lorsque aucun certificat ACM n'est disponible. Écart assumé à V2-LLD-001 §7, réservé au test."
  default     = false

  validation {
    condition     = !(var.alb_plaintext_listener_enabled && var.alb_certificate_arn != "")
    error_message = "alb_plaintext_listener_enabled et alb_certificate_arn s'excluent : fournir un certificat, ou assumer le listener en clair, jamais les deux."
  }
}

variable "alb_deregistration_delay_seconds" {
  type        = number
  description = "Target group deregistration delay (V2-LLD-001 §7)."
  default     = 30
}

# ---------------------------------------------------------------------------
# Identity parameters consumed by the fastapi container (V2-LLD-001 §7.1)
# ---------------------------------------------------------------------------

variable "cognito_issuer" {
  type        = string
  description = "Expected iss claim. A parameter, never derived from the received token (V2-LLD-001 §7.1.3)."
  default     = ""
}

variable "cognito_app_client_id" {
  type        = string
  description = "Expected aud claim. A parameter, never derived from the received token (V2-LLD-001 §7.1.3)."
  default     = ""
}

variable "jwks_cache_ttl_seconds" {
  type        = number
  description = "JWKS cache lifetime (V2-LLD-001 §7.1.4)."
  default     = 3600
}

variable "jwks_stale_tolerance_seconds" {
  type        = number
  description = "How long a stale JWKS may still be trusted when the endpoint is unreachable. V2-ADR-020 bounds it in hours, never days; enforced on the plan by terraform_plan_guard rule 5."
  default     = 21600

  validation {
    condition     = var.jwks_stale_tolerance_seconds <= 86400
    error_message = "V2-ADR-020 bounds the JWKS stale tolerance in hours, never days: 86400 s maximum."
  }
}

variable "jwks_refresh_min_interval_seconds" {
  type        = number
  description = "Minimum interval between two JWKS refreshes, anti-amplification (V2-LLD-001 §7.1.4)."
  default     = 60
}

# ---------------------------------------------------------------------------
# Encryption and IAM scoping (V2-LLD-001 §5.1, §12.1)
# ---------------------------------------------------------------------------

variable "logs_kms_key_arn" {
  type        = string
  description = "CMK encrypting the ECS log groups. Empty means the module creates its own CMK (V2-LLD-001 §12.1)."
  default     = ""
}

variable "erasure_audit_log_group_name" {
  type        = string
  description = "Erasure audit log group covered by the same CMK key policy. It does not live under /ecs/, so it is listed explicitly (V2-LLD-001 §12.1.1)."
  default     = ""
}

variable "agentcore_runtime_arn" {
  type        = string
  description = "AgentCore Runtime ARN invoked by fastapi. Empty removes the statement from the task role (V2-LLD-001 §5.1)."
  default     = ""
}

variable "agent_runtime_endpoint_name" {
  type        = string
  description = "AgentCore Runtime endpoint qualifier forwarded to fastapi. Matches AGENT_RUNTIME_ENDPOINT_NAME in the Lambda facade."
  default     = "default"
}

variable "knowledge_base_arn" {
  type        = string
  description = "Knowledge Base ARN targeted by bedrock-agent-runtime:Retrieve. Empty removes the statement (V2-LLD-001 §5.1)."
  default     = ""
}

variable "knowledge_base_data_source_arn" {
  type        = string
  description = "Knowledge Base data source ARN targeted by the ingestion job actions. Empty removes the statement (V2-LLD-001 §5.1)."
  default     = ""
}

variable "dynamodb_table_arns" {
  type        = list(string)
  description = "DynamoDB tables and indexes readable and writable by fastapi, excluding the command store which carries its own narrower statement (V2-LLD-001 §5.1)."
  default     = []
}

variable "commands_table_arns" {
  type        = list(string)
  description = "Command store table and its by-operation index. Deliberately narrower rights than the other tables: GetItem, Query and UpdateItem only (V2-LLD-001 §5.1)."
  default     = []

  # Withholding PutItem and DeleteItem on the command store is a control, not a
  # preference. It only holds while the store stays out of dynamodb_table_arns, whose
  # statement does grant them: listing the same table in both silently restores what
  # §5.1 withholds. Index ARNs are folded back to their table so that naming the table
  # in one list and its index in the other does not slip through.
  validation {
    condition = length(setintersection(
      toset([for arn in var.commands_table_arns : split("/index/", arn)[0]]),
      toset([for arn in var.dynamodb_table_arns : split("/index/", arn)[0]]),
    )) == 0

    error_message = "Une table figure a la fois dans commands_table_arns et dans dynamodb_table_arns. Le statement DynamoDBAccess accorde PutItem et DeleteItem, ce que CommandStoreConfirmationOnly retire deliberement (V2-LLD-001 §5.1) : le magasin de commandes doit etre absent de dynamodb_table_arns."
  }
}

variable "documents_bucket_arn" {
  type        = string
  description = "S3 bucket holding source documents. Empty removes the statement (V2-LLD-001 §5.1)."
  default     = ""
}

variable "documents_cmk_arn" {
  type        = string
  description = "CMK protecting the documents bucket. Empty removes the statement (V2-LLD-001 §5.1)."
  default     = ""
}

variable "secrets_path_prefix" {
  type        = string
  description = "Secrets Manager path prefix readable by the task role (V2-LLD-001 §5.1)."
  default     = "/v2/fastapi"
}
