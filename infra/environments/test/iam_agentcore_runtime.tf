data "aws_partition" "current" {}

locals {
  agentcore_base_model_id = trimprefix(var.agentcore_model_id, "eu.")
  agentcore_memory_arn = try(
    aws_bedrockagentcore_memory.agent[0].arn,
    "arn:${data.aws_partition.current.partition}:bedrock-agentcore:${var.region}:${data.aws_caller_identity.current.account_id}:memory/not-created"
  )
  agentcore_tools_gateway_arn = try(
    aws_bedrockagentcore_gateway.tools_mcp[0].gateway_arn,
    "arn:${data.aws_partition.current.partition}:bedrock-agentcore:${var.region}:${data.aws_caller_identity.current.account_id}:gateway/not-created"
  )
}

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
    sid = "InvokeConfiguredBedrockModel"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.agentcore_model_id}",
      "arn:${data.aws_partition.current.partition}:bedrock:eu-*::foundation-model/${local.agentcore_base_model_id}"
    ]
  }

  statement {
    sid = "UseConfiguredAgentCoreMemory"
    actions = [
      "bedrock-agentcore:CreateEvent",
      "bedrock-agentcore:RetrieveMemoryRecords"
    ]
    resources = [local.agentcore_memory_arn]
  }

  statement {
    sid       = "InvokeConfiguredToolsGateway"
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [local.agentcore_tools_gateway_arn]
  }

  statement {
    sid = "WriteRuntimeLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/*",
      "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/*:log-stream:*"
    ]
  }

  statement {
    sid = "WriteRuntimeTraces"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords"
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
