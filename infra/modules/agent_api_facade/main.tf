locals {
  facade_package_base64 = "UEsDBBQAAAAIALVU4lz5zSlt/QQAABMOAAASAAAAbGFtYmRhX2Z1bmN0aW9uLnB5lVZtb9s2EP7uX0HoSyRA8dqgLQYDGZA2zuahTQcnG1AUhUBLZ5upTGkklcQL/N93R1IWJSdelw+xyHt97o0nNnWlDFtzvS7FYiTc8U5Xsv2u9Gipqg0z21rIFfO3F3KbskuRm9FoNP/z+nb2aZrNpxeXX9g5SoxXYEDex1GPFKUsWvJSQ5SMy+oBVJyw83MWGdVANLr4dXp9m7UCF/PrvqYDMmmLEjR/9Xn+fnZ5Ob3OZvjvdnb7JbuaTT9e3qCCpxHDv4jnplKzIkqDYyb250ZDQKVTQBQFSCPMtj2jt9pAMXv+OgvYd+hcAUuWKdB1JTXE2nDT6CyvCpgwIU3Kar4tK15MbCy/aqNSCu23hJ3+MriaWDsKTKOkx2UNO50fUGU0YYGBtGNZAy9AaaR3cpaQVxKja04xtyQd8bouRc6NqORPVANRp2QX6FtUxRbZiWNcNJtaxx5GyjTUXHEMrz6Po5RyNImSxMnu40HVltkkxG0qyHVlUeNvD6ovzbFe87O37/YCY5CEMo4aszz9GW2M1/BYiBVoEydfJ6/PvrXW8pKLjY7hHpH+cJx5Y9aVEv+AwiqyolSJcaTg7wZNfKDAPRrE97RLHKWTcLdWzd2DQfmO5FjxNuBx/iEbXju6uwlYfCg8p1gyoYXEXMscYneZsgJRJAywvVCsxd5GK6MWbiPhfp4NxT74rSC65didZ7pZRM4ldEJWpuOrlD0HjrWk1KZ2si8fxQX6+BcvG5gqhTUQfRJa02yhOFH3YAVC4VQzbMReDFqtLUIsNw0ZVeT/zLDiD1asn19b2gmhiZ52UYs0YBD6Pdfw7s3Ulh86FwDzvYnRp6NR247mLdmWoU7RcWvfoYPHHGo3eMe/33y+vgRSb+PDuCbysQDO5D0vMQkkyTwEO7RRbhSmK0gPsfmqOaZ67greAdg09AWMO0vV4g5yQ0M4gE+MbXKsV5jMzM8Ha/SHM7Ss1EIUOE8xcBofHSjiF2f9GKcpjjh0B2eXNTP+DlsdJ8m+XPfqjsH9UAoaiLqhSYhF2I5zthRQFppxBa7uS3rBihZ7jcGuqdWtZVso7qrfLUH4Hdn1Rts87m6MV6KOj2blirxhJ07gBPUyGkxCdR5pwJ6qpGvhzit/PSs6xwJO1EN+XFcScyyLoc8d53/3tPdwb+8kKB4CKFeDugmeNB+6ySAgwQvUwZgE/vefmTUiKHHJeHYspCx3I3xCxxdLsNfD+0Hde1KSPT2YmccGbzIcCgczrOPwfUNMz/aSD2FnnV5L4n7miQ20YvhNHDzfg7XAOmH3gRV+ZELeV98Bt5gcxD0UwVJgua3+39AeSnRODJhUg220gTluIrQ69PbCAStK3wTpXVRV2e4XBzUc1MQuCYLh+62/mfouO9gkJz37vhy7pe3s1at0sDi5GrS7FoXJg8tQO4oRwvSQfYNeYzyJ/4LCyrxU23QF1GW1xZGzBTNmt2vAws4bHDcXf8xwV1yhP9o25Ue+WRScXfEctzo7kNBmvuaLEsYDw7sgJAe43r56PcT1DCaaqytlV8KsBllQ4w4SdoBs3iLrZNmDKEvqfpDkKI4ayfCx37M69BuSLisT4mgx+BeymzGH7+IQ4ZvDzAUIF7zI/Dr3MiKcBzEa6dVZ6M7U/iDAyZHueqGhGulGVJEB4Yl2SXIsW8ew2NdP8tJrejlBM8+IxaXucbkd8iO6fwFQSwECFAMUAAAACAC1VOJc+c0pbf0EAAATDgAAEgAAAAAAAAAAAAAAgAEAAAAAbGFtYmRhX2Z1bmN0aW9uLnB5UEsFBgAAAAABAAEAQAAAAC0FAAAAAA=="
  facade_package_hash   = "CSctGjownBVBG+Z176P8aVDfg2ps8zcGSIFzlC7408k="
  facade_package_key    = "agent-api-facade/lambda_facade.zip"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

data "aws_iam_policy_document" "logs" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "${var.function_name}-logs"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.logs.json
}

resource "aws_s3_bucket" "code" {
  bucket        = var.code_bucket_name
  force_destroy = true

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "code" {
  bucket = aws_s3_bucket.code.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "code" {
  bucket = aws_s3_bucket.code.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "package" {
  bucket         = aws_s3_bucket.code.id
  key            = local.facade_package_key
  content_base64 = local.facade_package_base64
  source_hash    = local.facade_package_hash

  server_side_encryption = "AES256"

  depends_on = [
    aws_s3_bucket_public_access_block.code,
    aws_s3_bucket_server_side_encryption_configuration.code
  ]
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = aws_iam_role.this.arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256
  s3_bucket        = aws_s3_bucket.code.id
  s3_key           = aws_s3_object.package.key
  source_code_hash = local.facade_package_hash

  environment {
    variables = {
      AGENT_RUNTIME_ARN = var.agent_runtime_arn
      LOG_LEVEL         = var.log_level
      RUNTIME_READY     = tostring(var.runtime_ready)
    }
  }

  tags = var.tags

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.logs,
    aws_s3_object.package
  ]
}
