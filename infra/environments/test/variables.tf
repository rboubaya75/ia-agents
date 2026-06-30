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
