variable "name" {
  type        = string
  description = "ECR repository name."
}

variable "image_tag_mutability" {
  type        = string
  description = "ECR image tag mutability. Use IMMUTABLE for promoted artifacts."
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "scan_on_push" {
  type        = bool
  description = "Enable ECR image scanning on push."
  default     = true
}

variable "max_image_count" {
  type        = number
  description = "Maximum number of images kept by the lifecycle policy."
  default     = 10

  validation {
    condition     = var.max_image_count >= 1
    error_message = "max_image_count must be at least 1."
  }
}

variable "force_delete" {
  type        = bool
  description = "Whether to force delete the repository even if it contains images."
  default     = false
}

variable "common_tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
