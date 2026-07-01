locals {
  origin_id = "${var.name_prefix}-frontend-s3-origin"

  tags = merge(
    var.common_tags,
    {
      Module = "frontend_static_site"
    }
  )
}
