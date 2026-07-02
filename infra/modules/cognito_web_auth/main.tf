resource "aws_cognito_user_pool" "this" {
  name = var.name

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 5
      max_length = 2048
    }
  }

  tags = local.module_tags
}

resource "aws_cognito_user_pool_client" "web" {
  name         = var.app_client_name
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user" "invited" {
  for_each = var.invited_users

  user_pool_id = aws_cognito_user_pool.this.id
  username     = each.value.email
  enabled      = each.value.enabled

  desired_delivery_mediums = ["EMAIL"]

  attributes = merge(
    {
      email          = each.value.email
      email_verified = "true"
    },
    each.value.given_name != null ? { given_name = each.value.given_name } : {},
    each.value.family_name != null ? { family_name = each.value.family_name } : {}
  )
}
