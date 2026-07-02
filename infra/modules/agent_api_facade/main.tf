locals {
  facade_package_base64 = "UEsDBBQAAAAIAHBS4lwlGE8OwgUAAIkRAAASAAAAbGFtYmRhX2Z1bmN0aW9uLnB5pVdtb9s2EP7uX0FoHyphspcN7TAYyAA3djYPbjK4aYGiKARaOjtMZdIjqThekP++O1KyJVv2ktYfbIs83ttz9/AkliulLbszSnaE/5+rxULIRfWoTGeu1ZLZzQpXWbk6kJuYDUVqY3ZTrHLodOgYaHZene8twE7cWhiVmz2DS3APeagMbYO8D4PJ9R/JZPRxNAliFoyvLq+DKOp0Lq+nb8fD4egqGePXzfjmU3I5Hk2G79HAY4fhJ+CpVXqcBXHtMRHb58JAbZeeapsiA2mF3VTPVhfGQjZuX05q4k+dznB0OfgwuUn+HA2Go2nNo1RJjMl2MVUQ9NGl1SoXKbdCyZ8ow5XalKe30CVprXISlKpr0Hvw+jsZzFmiwayUNBAay21hklRl0GdCYsZnXK5kNQciRdFI0mVcX+KWkwjLPocW1Iq3Txj0nGMBEETrMpknr5eZYvZT8sJmcjVpMk7L7Lsa4pgUL09fr1kwuBnMNhm9/eUu0OV4GpQS/bX0sjvL4cCuqjWy+yYA3ONdKpRe0yGF0EPcUX9fr7V08J2+BsPp9M87rmRmrvV0YIApmWljPMy7VbFhjZ5SU+8WgqmSjF9HUGMuR6sAgBLCHeCm4DSO120sxIgBGfYTKQk10WDwhUNk8hvyDpAmFpRrLqWMWFDFTujQ6MSipCWycPNvqTQ1AV7lHhYLNTTBDDzUW+wKCVrkk4WnjUiu14NoG6zM2/54KCwtZ5ZFhdQyhPkcH52LqthqafR08oTgu+FtUwgQdAzfn59fvHdeALP5g3zJr/HoOo7wLthzzafz/8XeNv2GSZy+0fELh+ACaVRzs/pjxp0RU5hXYK1/MYymBK1EBzIBW3Zvfr4LON0G+3Eah34S0x5oHnVeXXZtKxJS4jRKRPbqpswU6gWYALmMToin4N/AkwcwW1gVS1nYc4iqIqlZpHKnFKv7li3Da4d1tH0L2kFbFsMhCaRRVD7G4GdPY4XbPiINcg+UFkRnHDF0ekBIewfG3CnqxPse9YSZbpw+BXS3CIdjQwOpdaw5Q2xkI33I2xVE0Y9hU7Liw+FPquG6xAv56S30lSoM9nHP+bs1VqvpwxJuYZlcb2c+LJjxVEkYIcwRWovxk0Ih4Eccr9rH7DZcAxSH8cwPn3vF3tFyA1x8rBTdYO7enYQ8hSQqsewIfbLwfqH7VRWIHgQ3xIEB/9rcHNwG8pqrF19uLg17d3D77e3bz26t83jrV583vQLdu+59rwHUKtXbuS3Gu/gPZ1176CKPxN4vUU2ueEZq3ncgRNOG7OBqszXzb5bbu0lhHr+23wqa3VsipnNa3cnBfRZtbl4jr7DUlgSyGywXRP7n5qKp6klnBNktYh7hf0B+sW/e2Gg5T8+AfTYOeEh/YyajlGqUNvOXq13JcHbRsMfICCnupEXzglpUnJMgI+kKawSIyhIkXUK2ylNSs0qktbOQNtVoKOGURmPI+EzGK2bVOR93gVXVUvw3CwnuyXWAeY2aLjpZSTyWVtwgwDChwWEQKfOglCs5t3LE8xIj8sUzwyEXCvdWn61kSQkBYwvNWWsmGakciVSscxxsXO20+4Vl+FL+hlD9AlyHidCQaV78ykPdv37CzRUzHMsyKDUk4fmd3lHYxSIYmvPMFJYR3RlDjqy45e6V99cxs+yCXmKmqVMpnXiqLxDXUOHybHjRZvqTvSM9QrYh6ypE2j9fT7c3Tptj0XokJ5umtcSk6RTmo24e0Q+7+goR2rbF7Cu99zYNjQHNj9uBz/wFQSwECFAMUAAAACABwUuJcJRhPDsIFAACJEQAAEgAAAAAAAAAAAAAApIEAAAAAbGFtYmRhX2Z1bmN0aW9uLnB5UEsFBgAAAAABAAEAQAAAAOIFAAD/AAAAAAA="
  facade_package_hash   = "fMGIpOGgD8NNddZSJcP3OEL+ZSIdPwcxdndEEl+aAnY="
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
