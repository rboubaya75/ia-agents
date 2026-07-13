variable "name" {
  type        = string
  description = "HTTP API name."
}

variable "jwt_issuer" {
  type        = string
  description = "JWT issuer URL, for example the Cognito User Pool issuer."
}

variable "jwt_audience" {
  type        = list(string)
  description = "Allowed JWT audiences, usually the Cognito Web Client ID."

  validation {
    condition     = length(var.jwt_audience) > 0
    error_message = "jwt_audience must contain at least one audience."
  }
}

variable "allowed_origins" {
  type        = list(string)
  description = "Allowed CORS origins for the frontend."

  validation {
    condition     = length(var.allowed_origins) > 0 && alltrue([for origin in var.allowed_origins : startswith(origin, "https://")])
    error_message = "allowed_origins must contain at least one HTTPS origin."
  }
}

variable "security_facade_enabled" {
  type        = bool
  description = "Create the protected API Gateway route to the Lambda security facade."
  default     = true
}

variable "facade_lambda_invoke_arn" {
  type        = string
  description = "Lambda security facade invoke ARN."
  default     = ""
}

variable "facade_lambda_function_name" {
  type        = string
  description = "Lambda security facade function name."
  default     = ""
}

variable "gateway_first_enabled" {
  type        = bool
  description = "Historical P0 only. Create routes that proxy to AgentCore Gateway."
  default     = false
}

variable "agentcore_gateway_url" {
  type        = string
  description = "Historical P0 AgentCore Gateway base HTTPS URL."
  default     = ""
}

variable "agentcore_runtime_target_name" {
  type        = string
  description = "Historical P0 Runtime HTTP target name."
  default     = ""
}

variable "p0_agentcore_gateway_url" {
  type        = string
  description = "Deprecated alias for the isolated P0 route."
  default     = ""

  validation {
    condition     = var.p0_agentcore_gateway_url == "" || can(regex("^https://", var.p0_agentcore_gateway_url))
    error_message = "p0_agentcore_gateway_url must be empty or start with https://."
  }
}

variable "throttling_rate_limit" {
  type        = number
  description = "Steady-state requests per second for the test API."
  default     = 5

  validation {
    condition     = var.throttling_rate_limit > 0 && var.throttling_rate_limit <= 1000
    error_message = "throttling_rate_limit must be between 0 and 1000."
  }
}

variable "throttling_burst_limit" {
  type        = number
  description = "Burst request limit for the test API."
  default     = 10

  validation {
    condition     = var.throttling_burst_limit >= 1 && var.throttling_burst_limit <= 5000
    error_message = "throttling_burst_limit must be between 1 and 5000."
  }
}

variable "access_log_retention_days" {
  type        = number
  description = "API Gateway access log retention."
  default     = 30
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
