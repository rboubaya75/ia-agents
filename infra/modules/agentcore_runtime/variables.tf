variable "name" {
  type        = string
  description = "AgentCore Runtime name."
}

variable "ecr_repository_arn" {
  type        = string
  description = "ECR repository ARN containing the AgentCore image."
}

variable "ecr_repository_url" {
  type        = string
  description = "ECR repository URL containing the AgentCore image."
}

variable "image_tag" {
  type        = string
  description = "Image tag used for the AgentCore Runtime deployment."
  default     = "test"
}

variable "model_id" {
  type        = string
  description = "Default Bedrock model identifier exposed to the runtime container."
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "log_level" {
  type        = string
  description = "Runtime application log level."
  default     = "INFO"
}

variable "common_tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
