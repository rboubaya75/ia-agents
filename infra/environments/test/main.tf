data "aws_caller_identity" "current" {}

module "frontend_static_site" {
  source = "../../modules/frontend_static_site"

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
