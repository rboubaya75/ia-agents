variable "name_prefix" {
  type        = string
  description = "Name prefix used for frontend delivery resources."
}

variable "bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for private frontend assets."
}

variable "force_destroy" {
  type        = bool
  description = "Allow Terraform to delete the frontend bucket even when it contains objects. Test only."
  default     = false
}

variable "price_class" {
  type        = string
  description = "CloudFront price class."
  default     = "PriceClass_100"
}

variable "content_security_policy" {
  type        = string
  description = "Content-Security-Policy applied by CloudFront to frontend responses."

  validation {
    condition     = length(trimspace(var.content_security_policy)) > 0 && can(regex("default-src", var.content_security_policy))
    error_message = "content_security_policy must be non-empty and contain a default-src directive."
  }
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to resources supporting tags."
  default     = {}
}
