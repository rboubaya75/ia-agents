data "aws_caller_identity" "current" {}

module "frontend_static_site" {
  source = "../../modules/frontend_static_site"

  name_prefix   = local.name_prefix
  bucket_name   = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}-${var.region}"
  price_class   = "PriceClass_100"
  common_tags   = local.common_tags
  force_destroy = false
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
  tags            = local.common_tags
}
