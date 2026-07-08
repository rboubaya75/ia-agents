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
    condition     = length(var.allowed_origins) > 0
    error_message = "allowed_origins must contain at least one origin."
  }
}

variable "agentcore_gateway_url" {
  type        = string
  description = "AgentCore Gateway HTTPS invoke URL used by POST /agent/invoke. Leave empty until the Gateway-first contract is validated."
  default     = ""

  validation {
    condition     = var.agentcore_gateway_url == "" || can(regex("^https://", var.agentcore_gateway_url))
    error_message = "agentcore_gateway_url must be empty or start with https://."
  }
}

variable "p0_agentcore_gateway_url" {
  type        = string
  description = "Deprecated alias for the isolated P0 route POST /p0/agent/invoke. Prefer agentcore_gateway_url."
  default     = ""

  validation {
    condition     = var.p0_agentcore_gateway_url == "" || can(regex("^https://", var.p0_agentcore_gateway_url))
    error_message = "p0_agentcore_gateway_url must be empty or start with https://."
  }
}

variable "enable_legacy_facade" {
  type        = bool
  description = "Legacy fallback only. Enables API Gateway -> Lambda Facade -> Runtime if an ADR explicitly approves it."
  default     = false
}

variable "facade_lambda_invoke_arn" {
  type        = string
  description = "Legacy fallback Lambda Facade invoke ARN. Required only when enable_legacy_facade=true."
  default     = ""
}

variable "facade_lambda_function_name" {
  type        = string
  description = "Legacy fallback Lambda Facade function name. Required only when enable_legacy_facade=true."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
