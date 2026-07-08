variable "name" {
  type        = string
  description = "ECR repository name."
}

variable "image_tag_mutability" {
  type        = string
  description = "ECR image tag mutability."
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["MUTABLE", "IMMUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be MUTABLE or IMMUTABLE."
  }
}

variable "scan_on_push" {
  type        = bool
  description = "Enable image scan on push."
  default     = true
}

variable "force_delete" {
  type        = bool
  description = "Allow Terraform destroy to delete the repository even when images exist. Test environment only."
  default     = true
}

variable "keep_last_images" {
  type        = number
  description = "Number of tagged images to retain."
  default     = 20
}

variable "tags" {
  type        = map(string)
  description = "Common tags."
  default     = {}
}
