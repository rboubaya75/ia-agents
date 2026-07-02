module "agent_api_facade" {
  source = "../../modules/agent_api_facade"

  function_name    = "${local.name_prefix}-agent-api-facade"
  code_bucket_name = "${local.name_prefix}-facade-code-${data.aws_caller_identity.current.account_id}-${var.region}"
  runtime_ready    = false
  tags             = local.common_tags
}
