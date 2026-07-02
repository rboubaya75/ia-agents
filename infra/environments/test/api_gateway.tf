module "api_gateway_agent_ingress" {
  source = "../../modules/api_gateway_agent_ingress"

  name            = "${local.name_prefix}-agent-api"
  jwt_issuer      = format("https://cognito-idp.%s.amazonaws.com/%s", var.region, module.cognito_web_auth.user_pool_id)
  jwt_audience    = [module.cognito_web_auth.client_id]
  allowed_origins = ["https://${module.frontend_static_site.cloudfront_domain_name}"]
  tags            = local.common_tags
}
