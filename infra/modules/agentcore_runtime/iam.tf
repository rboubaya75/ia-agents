data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  partition  = data.aws_partition.current.partition
  image_uri  = "${var.ecr_repository_url}:${var.image_tag}"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "AllowAgentCoreRuntimeAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock-agentcore:${local.region}:${local.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  description        = "Execution role for the Secure AgentCore runtime."

  tags = var.common_tags
}

data "aws_iam_policy_document" "execution" {
  statement {
    sid    = "PullRuntimeImageFromEcr"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer"
    ]

    resources = [var.ecr_repository_arn]
  }

  statement {
    sid    = "GetEcrAuthorizationToken"
    effect = "Allow"

    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "InvokeBedrockModels"
    effect = "Allow"

    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]

    resources = [
      "arn:${local.partition}:bedrock:*::foundation-model/*",
      "arn:${local.partition}:bedrock:*:${local.account_id}:inference-profile/*"
    ]
  }

  statement {
    sid    = "WriteRuntimeLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents"
    ]

    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:*"]
  }

  statement {
    sid    = "EmitRuntimeTraces"
    effect = "Allow"

    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords"
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "${var.name}-execution-policy"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}
