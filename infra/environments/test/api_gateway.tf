module "api_gateway_agent_ingress" {
  source = "../../modules/api_gateway_agent_ingress"

  name            = "${local.name_prefix}-agent-api"
  jwt_issuer      = format("https://cognito-idp.%s.amazonaws.com/%s", var.region, module.cognito_web_auth.user_pool_id)
  jwt_audience    = [module.cognito_web_auth.client_id]
  allowed_origins = ["https://${module.frontend_static_site.cloudfront_domain_name}"]

  security_facade_enabled     = true
  facade_lambda_invoke_arn    = module.agent_api_facade.invoke_arn
  facade_lambda_function_name = module.agent_api_facade.function_name
  throttling_rate_limit       = 5
  throttling_burst_limit      = 10
  access_log_retention_days   = 30

  gateway_first_enabled         = false
  agentcore_gateway_url         = ""
  agentcore_runtime_target_name = ""

  tags = local.common_tags
}
