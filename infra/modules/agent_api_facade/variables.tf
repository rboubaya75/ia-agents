variable "function_name" {
  type        = string
  description = "Facade function name."
}

variable "code_bucket_name" {
  type        = string
  description = "Private bucket used to store the facade deployment package."
}

variable "runtime_ready" {
  type        = bool
  description = "Whether the AgentCore Runtime integration is active."
  default     = false
}

variable "agent_runtime_arn" {
  type        = string
  description = "AgentCore Runtime ARN. Empty until the runtime lot is deployed."
  default     = ""
}

variable "log_level" {
  type        = string
  description = "Facade log level."
  default     = "INFO"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention in days."
  default     = 14
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
