variable "function_name" {
  type        = string
  description = "Trip tools Lambda function name."
}

variable "source_file" {
  type        = string
  description = "Absolute path to the trip tools Python source file."
}

variable "hardened_source_file" {
  type        = string
  description = "Absolute path to the hardened mutation wrapper source file."
}

variable "trips_table_name" {
  type        = string
  description = "DynamoDB trips table name."
}

variable "trips_table_arn" {
  type        = string
  description = "DynamoDB trips table ARN."
}

variable "idempotency_ttl_seconds" {
  type        = number
  description = "Retention period for update idempotency ledger entries."
  default     = 604800

  validation {
    condition = (
      var.idempotency_ttl_seconds >= 3600 &&
      var.idempotency_ttl_seconds <= 2592000
    )
    error_message = "idempotency_ttl_seconds must be between 3600 and 2592000."
  }
}

variable "reserved_concurrent_executions" {
  type        = number
  description = "Optional reserved concurrency. Null uses the account unreserved concurrency pool."
  default     = null

  validation {
    condition = var.reserved_concurrent_executions == null ? true : (
      var.reserved_concurrent_executions >= 1 && var.reserved_concurrent_executions <= 100
    )
    error_message = "reserved_concurrent_executions must be null or between 1 and 100."
  }
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention in days."
  default     = 30
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags applied to the Lambda."
  default     = {}
}
