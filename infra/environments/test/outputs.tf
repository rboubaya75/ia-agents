output "name_prefix" {
  value = local.name_prefix
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "frontend_bucket_name" {
  value = module.frontend_static_site.bucket_name
}

output "cloudfront_distribution_id" {
  value = module.frontend_static_site.cloudfront_distribution_id
}

output "cloudfront_domain_name" {
  value = module.frontend_static_site.cloudfront_domain_name
}

output "trips_table_name" {
  value = module.dynamodb_trips.table_name
}

output "trips_table_arn" {
  value = module.dynamodb_trips.table_arn
}

output "cognito_user_pool_id" {
  value = module.cognito_web_auth.user_pool_id
}

output "cognito_user_pool_arn" {
  value = module.cognito_web_auth.user_pool_arn
}

output "cognito_web_client_id" {
  value = module.cognito_web_auth.client_id
}

output "agentcore_ecr_repository_name" {
  value = module.agentcore_container_repository.repository_name
}

output "agentcore_ecr_repository_url" {
  value = module.agentcore_container_repository.repository_url
}

output "agentcore_ecr_repository_arn" {
  value = module.agentcore_container_repository.repository_arn
}

output "service_url" {
  value = module.api_gateway_agent_ingress.api_endpoint
}

output "agent_invoke_url" {
  value = module.api_gateway_agent_ingress.agent_invoke_url
}

output "api_gateway_api_id" {
  value = module.api_gateway_agent_ingress.api_id
}

output "api_gateway_stage_name" {
  value = module.api_gateway_agent_ingress.stage_name
}

output "agent_service_name" {
  value = "${local.name_prefix}-runtime"
}

output "agent_service_role_arn" {
  value = aws_iam_role.agentcore_runtime.arn
}

output "agent_service_model_id" {
  value = var.agentcore_model_id
}

output "agentcore_gateway_url" {
  value = module.agentcore_gateway_contract.gateway_url
}

output "agentcore_gateway_mcp_url" {
  value = module.agentcore_gateway_contract.gateway_mcp_url
}

output "agentcore_memory_id" {
  value = module.agentcore_gateway_contract.memory_id
}

output "agentcore_gateway_auth_mode" {
  value = module.agentcore_gateway_contract.auth_mode
}

output "app_secret_name" {
  value = module.agentcore_gateway_contract.app_secret_name
}

output "gateway_first_ready" {
  value = module.agentcore_gateway_contract.gateway_first_ready
}

output "p0_agentcore_gateway_enabled" {
  value = module.api_gateway_agent_ingress.p0_agentcore_gateway_enabled
}

output "p0_agent_invoke_url" {
  value = module.api_gateway_agent_ingress.p0_agent_invoke_url
}
