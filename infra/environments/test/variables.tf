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
