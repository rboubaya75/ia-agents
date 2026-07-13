variable "function_name" {
  type        = string
  description = "Facade function name."
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

variable "agent_runtime_endpoint_name" {
  type        = string
  description = "AgentCore Runtime invocation qualifier. V1 uses the reserved DEFAULT qualifier."
  default     = "DEFAULT"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]{1,64}$", var.agent_runtime_endpoint_name))
    error_message = "agent_runtime_endpoint_name must be a valid AgentCore qualifier."
  }
}

variable "cognito_client_id" {
  type        = string
  description = "Expected Cognito access-token client_id claim."
}

variable "request_timeout_seconds" {
  type        = number
  description = "Facade request timeout in seconds. Keep below the API Gateway HTTP API timeout."
  default     = 28

  validation {
    condition     = var.request_timeout_seconds >= 5 && var.request_timeout_seconds <= 28
    error_message = "request_timeout_seconds must be between 5 and 28 seconds."
  }
}

variable "max_prompt_chars" {
  type        = number
  description = "Maximum accepted prompt length."
  default     = 4000

  validation {
    condition     = var.max_prompt_chars >= 1 && var.max_prompt_chars <= 20000
    error_message = "max_prompt_chars must be between 1 and 20000."
  }
}

variable "reserved_concurrent_executions" {
  type        = number
  description = "Optional reserved Lambda concurrency. Null uses the account unreserved concurrency pool."
  default     = null

  validation {
    condition = var.reserved_concurrent_executions == null ? true : (
      var.reserved_concurrent_executions >= 1 && var.reserved_concurrent_executions <= 100
    )
    error_message = "reserved_concurrent_executions must be null or between 1 and 100."
  }
}

variable "log_level" {
  type        = string
  description = "Facade log level."
  default     = "INFO"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention in days."
  default     = 30
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
