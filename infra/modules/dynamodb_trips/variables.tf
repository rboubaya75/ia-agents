variable "table_name" {
  type        = string
  description = "DynamoDB table name for user trip persistence."
}

variable "pitr_enabled" {
  type        = bool
  description = "Enable table point-in-time restore capability."
  default     = true
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to the table."
  default     = {}
}
