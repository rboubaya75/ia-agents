locals {
  name_prefix = "${var.project_name}-${var.environment}"

  agentcore_name_prefix  = replace(local.name_prefix, "-", "_")
  agentcore_runtime_name = substr("${local.agentcore_name_prefix}_runtime", 0, 48)
  agentcore_memory_name  = substr("${local.agentcore_name_prefix}_memory", 0, 48)

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
