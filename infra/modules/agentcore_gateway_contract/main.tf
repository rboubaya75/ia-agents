locals {
  gateway_first_ready = var.gateway_url != "" && var.gateway_mcp_url != "" && var.memory_id != ""
}
