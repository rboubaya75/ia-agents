resource "archive_file" "this" {
  type             = "zip"
  output_path      = "${path.module}/trip_tools.zip"
  output_file_mode = "0666"

  source {
    content  = file(var.source_file)
    filename = "lambda_function_code.py"
  }

  source {
    content  = file(var.hardened_source_file)
    filename = "lambda_function_hardened.py"
  }

  source {
    content  = file(var.phase2_source_file)
    filename = "lambda_function_phase2.py"
  }
}

resource "aws_kms_key" "pagination_hmac" {
  description              = "HMAC key for authenticated ${var.function_name} pagination cursors."
  customer_master_key_spec = "HMAC_256"
  key_usage                = "GENERATE_VERIFY_MAC"
  enable_key_rotation      = false
  deletion_window_in_days  = 7
  tags                     = var.tags
}

resource "aws_kms_alias" "pagination_hmac" {
  name          = "alias/${var.function_name}-pagination-hmac"
  target_key_id = aws_kms_key.pagination_hmac.key_id
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
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
  tags               = var.tags
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

data "aws_iam_policy_document" "execution" {
  statement {
    sid    = "WriteFunctionLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["${aws_cloudwatch_log_group.this.arn}:*"]
  }

  statement {
    sid    = "WriteFunctionTraces"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ReadWriteOwnTripsTable"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
      "dynamodb:TransactWriteItems"
    ]
    resources = [var.trips_table_arn]
  }

  statement {
    sid    = "UsePaginationHmacKey"
    effect = "Allow"
    actions = [
      "kms:GenerateMac",
      "kms:VerifyMac"
    ]
    resources = [aws_kms_key.pagination_hmac.arn]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "${var.function_name}-execution"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.execution.json
}

resource "aws_lambda_function" "this" {
  function_name                  = var.function_name
  role                           = aws_iam_role.this.arn
  handler                        = "lambda_function_phase2.lambda_handler"
  runtime                        = "python3.12"
  architectures                  = ["arm64"]
  timeout                        = 5
  memory_size                    = 256
  reserved_concurrent_executions = var.reserved_concurrent_executions
  filename                       = archive_file.this.output_path
  source_code_hash               = archive_file.this.output_base64sha256

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      TRIPS_TABLE_NAME           = var.trips_table_name
      TRIPS_DEFAULT_PAGE_SIZE    = "20"
      TRIPS_MAX_PAGE_SIZE        = "50"
      TRIPS_CURSOR_HMAC_KEY_ID   = aws_kms_key.pagination_hmac.arn
      TRIPS_CURSOR_TTL_SECONDS   = "900"
      IDEMPOTENCY_TTL_SECONDS    = tostring(var.idempotency_ttl_seconds)
      LOG_LEVEL                  = "INFO"
    }
  }

  tags = var.tags

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy.execution
  ]
}
