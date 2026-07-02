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

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
