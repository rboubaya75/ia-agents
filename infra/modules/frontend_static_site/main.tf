resource "aws_s3_bucket" "frontend" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy

  tags = local.tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.name_prefix}-frontend-oac"
  description                       = "Origin access control for ${var.name_prefix} frontend assets"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_response_headers_policy" "frontend_security" {
  name    = "${var.name_prefix}-frontend-security"
  comment = "Security headers for ${var.name_prefix} frontend"

  security_headers_config {
    content_security_policy {
      content_security_policy = var.content_security_policy
      override                = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }

    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }

    xss_protection {
      protection = true
      mode_block = true
      override   = true
    }
  }

  custom_headers_config {
    items {
      header   = "Permissions-Policy"
      value    = "camera=(), microphone=(), geolocation=(), payment=()"
      override = true
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Routage des liens profonds du SPA. Il tient la place de la bascule
# `custom_error_response` 403/404 → 200, qui ne se règle que par distribution et
# masquait donc aussi les erreurs de `/api/*`. Une fonction s'associe en revanche à un
# comportement précis, ce qui rend la réécriture opposable au seul contenu statique.
resource "aws_cloudfront_function" "spa_router" {
  name    = "${var.name_prefix}-spa-router"
  runtime = "cloudfront-js-2.0"
  comment = "Deep-link routing for the ${var.name_prefix} SPA"
  publish = true
  code    = file("${path.module}/spa_router.js")
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  comment             = "${var.name_prefix} frontend distribution"
  default_root_object = "index.html"
  price_class         = var.price_class

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
    origin_id                = local.origin_id
  }

  # L'iteration porte sur une cle et non sur l'objet : `api_origin` est sensible, et
  # Terraform refuse une valeur sensible en `for_each`. Le corps du bloc lit la variable
  # directement, ce qui preserve la marque de sensibilite la ou elle compte.
  dynamic "origin" {
    for_each = var.api_origin == null ? [] : ["api"]

    content {
      domain_name = var.api_origin.domain_name
      origin_path = var.api_origin.origin_path
      origin_id   = local.api_origin_id

      custom_origin_config {
        http_port                = 80
        https_port               = 443
        origin_protocol_policy   = "https-only"
        origin_ssl_protocols     = ["TLSv1.2"]
        origin_read_timeout      = 60
        origin_keepalive_timeout = 60
      }

      # Le secret voyage de CloudFront à API Gateway uniquement. Le navigateur ne le voit
      # jamais : c'est ce qui rend l'appel direct de la passerelle inexploitable.
      custom_header {
        name  = var.api_origin.verify_header_name
        value = var.api_origin_verify_secret
      }
    }
  }

  # §7.2 — aucun cache et aucun tampon supplémentaire sur le chemin conversationnel. La
  # précondition 5 de §16.5 demande de le vérifier par mesure et non par lecture : ces
  # réglages sont nécessaires, ils ne suffisent pas à prouver que le flux est progressif.
  dynamic "ordered_cache_behavior" {
    for_each = var.api_origin == null ? [] : ["api"]

    content {
      path_pattern           = "/api/*"
      target_origin_id       = local.api_origin_id
      viewer_protocol_policy = "https-only"
      allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods         = ["GET", "HEAD"]
      compress               = false

      min_ttl     = 0
      default_ttl = 0
      max_ttl     = 0

      forwarded_values {
        query_string = true

        # Authorization doit atteindre l'authorizer de la passerelle puis FastAPI. Sans
        # cette ligne, CloudFront le retire et toute requête authentifiée devient anonyme.
        headers = ["Authorization", "Content-Type", "Accept", "Last-Event-ID"]

        cookies {
          forward = "none"
        }
      }
    }
  }

  default_cache_behavior {
    target_origin_id           = local.origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    response_headers_policy_id = aws_cloudfront_response_headers_policy.frontend_security.id

    # L'association ne porte que sur ce comportement : le comportement `/api/*` n'a
    # aucune fonction attachée et n'est donc jamais réécrit.
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_router.arn
    }

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }
  }

  # Aucun `custom_error_response` ici, délibérément. Ce bloc se règle au niveau de la
  # distribution, jamais par comportement : la bascule 403/404 → 200 + `index.html` qui
  # servait les liens profonds du SPA s'appliquait aussi à `/api/*`. Un refus de la
  # passerelle y ressortait en 200 porteur de HTML — `curl` affichait 200 et le front,
  # attendant du SSE, ne trouvait aucune trame et concluait à un flux tronqué. Le
  # routage SPA est désormais porté par `aws_cloudfront_function.spa_router`, associé au
  # seul comportement par défaut ; les erreurs d'API traversent intactes.
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.tags
}

data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    sid       = "CloudFrontReadAccess"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
