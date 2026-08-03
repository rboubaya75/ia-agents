data "aws_caller_identity" "current" {}

module "frontend_static_site" {
  source = "../../modules/frontend_static_site"

  # §7, §7.4 — l'origine API n'existe qu'avec l'ingress V2. Le chemin V1 laisse la
  # valeur nulle et conserve la distribution qu'il avait.
  api_origin = var.enable_ecs_ingress && var.enable_ecs_platform ? {
    domain_name        = module.api_gateway_v2_ingress[0].api_host_name
    origin_path        = module.api_gateway_v2_ingress[0].origin_path
    verify_header_name = "x-origin-verify"
  } : null
  api_origin_verify_secret = one(random_password.origin_verify[*].result)

  name_prefix = local.name_prefix
  bucket_name = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}-${var.region}"
  price_class = "PriceClass_100"
  content_security_policy = join("; ", [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "connect-src 'self' https://cognito-idp.${var.region}.amazonaws.com https://*.execute-api.${var.region}.amazonaws.com",
    "manifest-src 'self'",
    "upgrade-insecure-requests"
  ])
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
