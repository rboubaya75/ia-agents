module "agent_api_facade" {
  source = "../../modules/agent_api_facade"

  function_name = "${local.name_prefix}-agent-invocation-facade"

  runtime_ready              = var.enable_agentcore_control_plane
  agent_runtime_arn          = try(aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn, "")
  agent_runtime_endpoint_name = var.agent_runtime_endpoint_name
  cognito_client_id          = module.cognito_web_auth.client_id

  request_timeout_seconds       = 29
  max_prompt_chars              = 4000
  reserved_concurrent_executions = 5
  log_retention_days            = 30
  log_level                     = "INFO"

  tags = local.common_tags
}
