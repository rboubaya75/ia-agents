locals {
  facade_package_base64 = "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"
  facade_package_hash   = "3ICuv0Ugtv/2VCOY6n29qPrc99Sojlh+Oo03vFEoa2c="
  facade_package_key    = "agent-api-facade/lambda_facade.zip"

  runtime_invoke_resources = var.agent_runtime_arn != "" ? [var.agent_runtime_arn] : ["*"]
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

data "aws_iam_policy_document" "runtime_invoke" {
  statement {
    sid    = "InvokeAgentRuntime"
    effect = "Allow"

    actions = [
      "bedrock-agentcore:InvokeAgentRuntime"
    ]

    resources = local.runtime_invoke_resources
  }
}

resource "aws_iam_role_policy" "runtime_invoke" {
  count = var.runtime_ready && var.agent_runtime_arn != "" ? 1 : 0

  name   = "${var.function_name}-runtime-invoke"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.runtime_invoke.json
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
  timeout          = var.request_timeout_seconds
  memory_size      = 256
  s3_bucket        = aws_s3_bucket.code.id
  s3_key           = aws_s3_object.package.key
  source_code_hash = local.facade_package_hash

  environment {
    variables = {
      AGENT_RUNTIME_ARN           = var.agent_runtime_arn
      AGENT_RUNTIME_ENDPOINT_NAME = var.agent_runtime_endpoint_name
      LOG_LEVEL                   = var.log_level
      REQUEST_TIMEOUT_SECONDS     = tostring(var.request_timeout_seconds)
      RUNTIME_READY               = tostring(var.runtime_ready)
    }
  }

  tags = var.tags

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.logs,
    aws_s3_object.package
  ]
}
