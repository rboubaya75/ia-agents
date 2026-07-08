module "api_gateway_agent_ingress" {
  source = "../../modules/api_gateway_agent_ingress"

  name            = "${local.name_prefix}-agent-api"
  jwt_issuer      = format("https://cognito-idp.%s.amazonaws.com/%s", var.region, module.cognito_web_auth.user_pool_id)
  jwt_audience    = [module.cognito_web_auth.client_id]
  allowed_origins = ["https://${module.frontend_static_site.cloudfront_domain_name}"]

  # Solution 4: browser invokes AgentCore Runtime directly with Cognito Bearer token.
  # API Gateway remains available for future non-Runtime application APIs, but it no
  # longer proxies user agent ingress through AgentCore Gateway.
  gateway_first_enabled         = false
  agentcore_gateway_url         = ""
  agentcore_runtime_target_name = ""

  tags = local.common_tags
}
