data "archive_file" "facade" {
  type        = "zip"
  source_file = "${path.module}/src/lambda_function.py"
  output_path = "${path.module}/lambda_facade.zip"
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

    # Test stabilisation: AgentCore Runtime currently evaluates InvokeAgentRuntime
    # against a resource shape that may differ from the runtime ARN returned by
    # CreateAgentRuntime. Keep the action scoped to the Facade role only and
    # tighten the resource after validating the exact ARN in CloudTrail.
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "runtime_invoke" {
  count = var.runtime_ready && var.agent_runtime_arn != "" ? 1 : 0

  name   = "${var.function_name}-runtime-invoke"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.runtime_invoke.json
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = aws_iam_role.this.arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  timeout          = var.request_timeout_seconds
  memory_size      = 256
  filename         = data.archive_file.facade.output_path
  source_code_hash = data.archive_file.facade.output_base64sha256

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
    aws_iam_role_policy.logs
  ]
}
