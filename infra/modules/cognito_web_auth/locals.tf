locals {
  module_tags = merge(
    var.tags,
    {
      Module = "cognito_web_auth"
    }
  )
}
