module "agent_api_facade" {
  source = "../../modules/agent_api_facade"

  function_name               = "${local.name_prefix}-agent-api-facade"
  code_bucket_name            = "${local.name_prefix}-facade-code-${data.aws_caller_identity.current.account_id}-${var.region}"
  runtime_ready               = var.agent_runtime_ready
  agent_runtime_arn           = var.agent_runtime_arn
  agent_runtime_endpoint_name = var.agent_runtime_endpoint_name
  request_timeout_seconds     = 120
  tags                        = local.common_tags
}
