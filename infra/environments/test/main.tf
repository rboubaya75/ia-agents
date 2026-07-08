data "aws_caller_identity" "current" {}

module "frontend_static_site" {
  source = "../../modules/frontend_static_site"

  name_prefix   = local.name_prefix
  bucket_name   = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}-${var.region}"
  price_class   = "PriceClass_100"
  common_tags   = local.common_tags
  force_destroy = true
}

module "dynamodb_trips" {
  source = "../../modules/dynamodb_trips"

  table_name   = "${local.name_prefix}-trips"
  pitr_enabled = true
  common_tags  = local.common_tags
}

module "cognito_web_auth" {
  source = "../../modules/cognito_web_auth"

  name            = "${local.name_prefix}-users"
  app_client_name = "${local.name_prefix}-web"
  invited_users   = var.cognito_invited_users
  tags            = local.common_tags
}

module "agentcore_container_repository" {
  source = "../../modules/ecr_container_repository"

  name         = "${local.name_prefix}-agentcore-runtime"
  force_delete = true
  tags         = local.common_tags
}

module "api_gateway_agent_ingress" {
  source = "../../modules/api_gateway_agent_ingress"

  name                  = "${local.name_prefix}-agent-ingress"
  jwt_issuer            = "https://cognito-idp.${var.region}.amazonaws.com/${module.cognito_web_auth.user_pool_id}"
  jwt_audience          = [module.cognito_web_auth.client_id]
  allowed_origins       = ["https://${module.frontend_static_site.cloudfront_domain_name}"]
  gateway_first_enabled = var.enable_agentcore_control_plane || var.p0_agentcore_gateway_url != ""
  agentcore_gateway_url = try(aws_bedrockagentcore_gateway.ingress[0].gateway_url, var.p0_agentcore_gateway_url)
  tags                  = local.common_tags
}
