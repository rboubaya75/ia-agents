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

output "api_gateway_access_log_group_name" {
  value = module.api_gateway_agent_ingress.access_log_group_name
}

output "agent_api_facade_function_name" {
  value = module.agent_api_facade.function_name
}

output "agent_api_facade_role_arn" {
  value = module.agent_api_facade.role_arn
}

output "agent_api_facade_log_group_name" {
  value = module.agent_api_facade.log_group_name
}

output "trip_tools_lambda_function_name" {
  value = module.trip_tools_lambda.function_name
}

output "trip_tools_lambda_function_arn" {
  value = module.trip_tools_lambda.function_arn
}

output "trip_tools_lambda_log_group_name" {
  value = module.trip_tools_lambda.log_group_name
}

output "agent_service_name" {
  value = local.agentcore_runtime_name
}

output "agent_service_role_arn" {
  value = aws_iam_role.agentcore_runtime.arn
}

output "agent_service_model_id" {
  value = var.agentcore_model_id
}

output "agent_runtime_arn" {
  value = try(aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn, "")
}

output "agent_runtime_id" {
  value = try(aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_id, "")
}

output "agent_runtime_endpoint_arn" {
  value = try(aws_bedrockagentcore_agent_runtime_endpoint.default[0].agent_runtime_endpoint_arn, "")
}

output "agent_runtime_invoke_url" {
  description = "Technical IAM-authenticated Runtime URL. It must not be exposed to the browser."
  value       = try("https://bedrock-agentcore.${var.region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn)}/invocations?qualifier=DEFAULT", "")
}

output "agentcore_gateway_url" {
  description = "Deprecated user-ingress Gateway output. AgentCore Gateway is tools-only in V1."
  value       = ""
}

output "agentcore_gateway_mcp_url" {
  value = try(aws_bedrockagentcore_gateway.tools_mcp[0].gateway_url, "")
}

output "agentcore_gateway_arn" {
  value = try(aws_bedrockagentcore_gateway.tools_mcp[0].gateway_arn, "")
}

output "agentcore_trip_tools_target_id" {
  value = try(aws_bedrockagentcore_gateway_target.trip_tools[0].target_id, "")
}

output "agentcore_memory_id" {
  value = try(aws_bedrockagentcore_memory.agent[0].id, "")
}

output "agentcore_memory_arn" {
  value = try(aws_bedrockagentcore_memory.agent[0].arn, "")
}

output "agentcore_gateway_auth_mode" {
  value = "aws_iam"
}

output "app_secret_name" {
  value = ""
}

output "secure_facade_ready" {
  value = (
    var.enable_agentcore_control_plane &&
    module.api_gateway_agent_ingress.security_facade_enabled &&
    module.api_gateway_agent_ingress.agent_invoke_url != "" &&
    module.agent_api_facade.function_name != "" &&
    try(aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn, "") != "" &&
    try(aws_bedrockagentcore_memory.agent[0].id, "") != "" &&
    try(aws_bedrockagentcore_gateway.tools_mcp[0].gateway_url, "") != "" &&
    try(aws_bedrockagentcore_gateway_target.trip_tools[0].target_id, "") != ""
  )
}

output "gateway_first_ready" {
  description = "Deprecated compatibility alias. Use secure_facade_ready."
  value       = false
}
