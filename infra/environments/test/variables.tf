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
