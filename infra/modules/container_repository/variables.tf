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

variable "force_delete" {
  type        = bool
  description = "Delete the ECR repository even if it still contains images. Use true only for ephemeral environments."
  default     = false
}

variable "common_tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
