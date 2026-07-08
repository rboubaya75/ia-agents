data "aws_iam_policy_document" "agentcore_service_assume_role" {
  statement {
    sid     = "AgentCoreAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "agentcore_runtime" {
  name               = "${local.name_prefix}-agentcore-runtime-role"
  assume_role_policy = data.aws_iam_policy_document.agentcore_service_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "agentcore_runtime" {
  statement {
    sid = "ReadRuntimeImageFromEcr"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer"
    ]
    resources = [module.agentcore_container_repository.repository_arn]
  }

  statement {
    sid       = "GetEcrAuthorizationToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "InvokeBedrockModels"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = ["*"]
  }

  statement {
    sid = "UseAgentCoreServices"
    actions = [
      "bedrock-agentcore:*"
    ]
    resources = ["*"]
  }

  statement {
    sid = "WriteRuntimeLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }

  statement {
    sid = "ReadConfiguredApplicationSecret"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "agentcore_runtime" {
  name   = "${local.name_prefix}-agentcore-runtime-policy"
  policy = data.aws_iam_policy_document.agentcore_runtime.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "agentcore_runtime" {
  role       = aws_iam_role.agentcore_runtime.name
  policy_arn = aws_iam_policy.agentcore_runtime.arn
}

resource "aws_iam_role" "agentcore_gateway" {
  name               = "${local.name_prefix}-agentcore-gateway-role"
  assume_role_policy = data.aws_iam_policy_document.agentcore_service_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "agentcore_gateway" {
  statement {
    sid = "InvokeAgentCoreRuntimeTarget"
    actions = [
      "bedrock-agentcore:InvokeAgentRuntime",
      "bedrock-agentcore:*"
    ]
    resources = ["*"]
  }

  statement {
    sid = "InvokeMcpToolBackends"
    actions = [
      "lambda:InvokeFunction",
      "execute-api:Invoke"
    ]
    resources = ["*"]
  }

  statement {
    sid = "WriteGatewayLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "agentcore_gateway" {
  name   = "${local.name_prefix}-agentcore-gateway-policy"
  policy = data.aws_iam_policy_document.agentcore_gateway.json
  tags   = local.common_tags
}

resource "aws_iam_role_policy_attachment" "agentcore_gateway" {
  role       = aws_iam_role.agentcore_gateway.name
  policy_arn = aws_iam_policy.agentcore_gateway.arn
}
