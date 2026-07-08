module "api_gateway_agent_ingress" {
  source = "../../modules/api_gateway_agent_ingress"

  name                  = "${local.name_prefix}-agent-api"
  jwt_issuer            = format("https://cognito-idp.%s.amazonaws.com/%s", var.region, module.cognito_web_auth.user_pool_id)
  jwt_audience          = [module.cognito_web_auth.client_id]
  allowed_origins       = ["https://${module.frontend_static_site.cloudfront_domain_name}"]
  gateway_first_enabled = var.enable_agentcore_control_plane || var.p0_agentcore_gateway_url != ""
  agentcore_gateway_url = try(aws_bedrockagentcore_gateway.ingress[0].gateway_url, var.p0_agentcore_gateway_url)
  tags                  = local.common_tags
}
