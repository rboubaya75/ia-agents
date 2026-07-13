variable "function_name" {
  type        = string
  description = "Trip tools Lambda function name."
}

variable "source_file" {
  type        = string
  description = "Absolute path to the trip tools Python source file."
}

variable "trips_table_name" {
  type        = string
  description = "DynamoDB trips table name."
}

variable "trips_table_arn" {
  type        = string
  description = "DynamoDB trips table ARN."
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
  description = "Common resource tags."
  default     = {}
}
