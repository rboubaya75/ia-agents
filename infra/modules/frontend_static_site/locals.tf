locals {
  origin_id     = "${var.name_prefix}-frontend-s3-origin"
  api_origin_id = "${var.name_prefix}-api-gateway-origin"

  tags = merge(
    var.common_tags,
    {
      Module = "frontend_static_site"
    }
  )
}
