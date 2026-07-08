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
  description = "Default Bedrock model identifier for the AgentCore runtime."
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "agentcore_gateway_url" {
  type        = string
  description = "AgentCore Gateway HTTPS invoke URL used by API Gateway /agent/invoke. Required for Gateway-first runtime/full deploy."
  default     = ""

  validation {
    condition     = var.agentcore_gateway_url == "" || can(regex("^https://", var.agentcore_gateway_url))
    error_message = "agentcore_gateway_url must be empty or start with https://."
  }
}

variable "agentcore_gateway_mcp_url" {
  type        = string
  description = "AgentCore Gateway MCP HTTPS endpoint used by Runtime to call tools. Required for Gateway-first runtime/full deploy."
  default     = ""

  validation {
    condition     = var.agentcore_gateway_mcp_url == "" || can(regex("^https://", var.agentcore_gateway_mcp_url))
    error_message = "agentcore_gateway_mcp_url must be empty or start with https://."
  }
}

variable "agentcore_memory_id" {
  type        = string
  description = "AgentCore Memory identifier injected into Runtime. Required for Gateway-first runtime/full deploy."
  default     = ""
}

variable "agentcore_gateway_auth_mode" {
  type        = string
  description = "Runtime-to-Gateway auth mode injected into Runtime."
  default     = "oauth"
}

variable "app_secret_name" {
  type        = string
  description = "Optional Secrets Manager secret name injected into Runtime for Gateway auth or application credentials."
  default     = ""
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

variable "agent_runtime_endpoint_name" {
  type        = string
  description = "Legacy fallback only. Do not use for the nominal Gateway-first path."
  default     = "default"
}

variable "p0_agentcore_gateway_url" {
  type        = string
  description = "Deprecated alias for agentcore_gateway_url. Kept for P0 compatibility."
  default     = ""

  validation {
    condition     = var.p0_agentcore_gateway_url == "" || can(regex("^https://", var.p0_agentcore_gateway_url))
    error_message = "p0_agentcore_gateway_url must be empty or start with https://."
  }
}
