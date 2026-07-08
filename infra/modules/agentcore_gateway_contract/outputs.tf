output "gateway_url" {
  value = var.gateway_url
}

output "gateway_mcp_url" {
  value = var.gateway_mcp_url
}

output "memory_id" {
  value = var.memory_id
}

output "auth_mode" {
  value = var.auth_mode
}

output "app_secret_name" {
  value = var.app_secret_name
}

output "gateway_first_ready" {
  value = local.gateway_first_ready
}
