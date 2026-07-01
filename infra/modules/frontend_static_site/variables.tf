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

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to resources supporting tags."
  default     = {}
}
