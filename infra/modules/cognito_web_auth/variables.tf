variable "name" {
  type        = string
  description = "Cognito User Pool name."
}

variable "app_client_name" {
  type        = string
  description = "Cognito web app client name."
}

variable "invited_users" {
  type = map(object({
    email       = string
    enabled     = optional(bool, true)
    given_name  = optional(string)
    family_name = optional(string)
  }))
  description = "Invitation-only Cognito users to create through AdminCreateUser semantics. Keep empty by default and do not store passwords in Git."
  default     = {}

  validation {
    condition = alltrue([
      for user in values(var.invited_users) : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", user.email))
    ])
    error_message = "Each invited user must have a valid email address."
  }
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
