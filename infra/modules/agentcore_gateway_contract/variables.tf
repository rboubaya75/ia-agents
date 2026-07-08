variable "gateway_url" {
  type        = string
  description = "AgentCore Gateway HTTPS invoke URL used by API Gateway HTTP API."
  default     = ""

  validation {
    condition     = var.gateway_url == "" || can(regex("^https://", var.gateway_url))
    error_message = "gateway_url must be empty or start with https://."
  }
}

variable "gateway_mcp_url" {
  type        = string
  description = "AgentCore Gateway MCP endpoint URL used by AgentCore Runtime for tools."
  default     = ""

  validation {
    condition     = var.gateway_mcp_url == "" || can(regex("^https://", var.gateway_mcp_url))
    error_message = "gateway_mcp_url must be empty or start with https://."
  }
}

variable "memory_id" {
  type        = string
  description = "AgentCore Memory identifier used by AgentCore Runtime."
  default     = ""
}

variable "auth_mode" {
  type        = string
  description = "Runtime-to-Gateway auth mode."
  default     = "oauth"
}

variable "app_secret_name" {
  type        = string
  description = "Optional Secrets Manager secret name used by Runtime/Gateway auth."
  default     = ""
}
