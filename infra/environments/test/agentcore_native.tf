locals {
  agentcore_memory_strategy_name       = "TravelPreferences"
  agentcore_memory_namespace_template = "/travel/{actorId}/preferences"
}

resource "aws_bedrockagentcore_memory" "agent" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name                  = local.agentcore_memory_name
  description           = "WildRydes ${var.environment} AgentCore Memory"
  event_expiry_duration = var.agentcore_memory_event_expiry_days
  tags                  = local.common_tags
}

resource "terraform_data" "agentcore_memory_preferences_strategy" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  triggers_replace = {
    memory_id          = aws_bedrockagentcore_memory.agent[0].id
    strategy_name      = local.agentcore_memory_strategy_name
    namespace_template = local.agentcore_memory_namespace_template
    script_sha256      = filesha256("${path.root}/../../../scripts/configure_agentcore_memory_strategy.py")
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOT
      python3 "$SCRIPT_PATH" ensure \
        --memory-id "$MEMORY_ID" \
        --strategy-name "$STRATEGY_NAME" \
        --namespace-template "$NAMESPACE_TEMPLATE" \
        --region "$AWS_REGION"
    EOT

    environment = {
      SCRIPT_PATH        = "${path.root}/../../../scripts/configure_agentcore_memory_strategy.py"
      MEMORY_ID          = aws_bedrockagentcore_memory.agent[0].id
      STRATEGY_NAME      = local.agentcore_memory_strategy_name
      NAMESPACE_TEMPLATE = local.agentcore_memory_namespace_template
      AWS_REGION         = var.region
    }
  }

  depends_on = [aws_bedrockagentcore_memory.agent]
}

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  agent_runtime_name = local.agentcore_runtime_name
  description        = "WildRydes ${var.environment} AgentCore Runtime with IAM-only inbound invocation"
  role_arn           = aws_iam_role.agentcore_runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${module.agentcore_container_repository.repository_url}:${var.agentcore_image_tag}"
    }
  }

  environment_variables = {
    AWS_REGION                  = var.region
    AWS_DEFAULT_REGION          = var.region
    MODEL_ID                    = var.agentcore_model_id
    LOG_LEVEL                   = "INFO"
    SESSION_DIR                 = "/tmp/sessions"
    ENABLE_RAG                  = tostring(var.enable_rag)
    MEMORY_ID                   = aws_bedrockagentcore_memory.agent[0].id
    MEMORY_NAMESPACE_TEMPLATE   = local.agentcore_memory_namespace_template
    GATEWAY_URL                 = aws_bedrockagentcore_gateway.tools_mcp[0].gateway_url
    GATEWAY_AUTH_MODE           = "aws_iam"
    REQUIRE_MCP_TOOLS           = "true"
    MAX_PROMPT_CHARS            = "4000"
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  tags = local.common_tags

  depends_on = [
    aws_iam_role_policy_attachment.agentcore_runtime,
    terraform_data.agentcore_memory_preferences_strategy,
  ]
}

data "aws_iam_policy_document" "agent_runtime_invocation_boundary" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  statement {
    sid     = "AllowOnlySecurityFacadeRole"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]

    principals {
      type        = "AWS"
      identifiers = [module.agent_api_facade.role_arn]
    }

    resources = [aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn]
  }

  statement {
    sid     = "DenyOtherRuntimeInvokers"
    effect  = "Deny"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn]

    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = [module.agent_api_facade.role_arn]
    }
  }

  statement {
    sid     = "DenyUnverifiedRuntimeUserDelegation"
    effect  = "Deny"
    actions = ["bedrock-agentcore:InvokeAgentRuntimeForUser"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn]
  }
}

resource "aws_bedrockagentcore_resource_policy" "agent_runtime_invocation_boundary" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  resource_arn = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn
  policy       = data.aws_iam_policy_document.agent_runtime_invocation_boundary[0].json
}

resource "aws_bedrockagentcore_agent_runtime_endpoint" "default" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name                  = var.agent_runtime_endpoint_name
  agent_runtime_id      = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_id
  agent_runtime_version = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_version
  description           = "Default endpoint for WildRydes ${var.environment} AgentCore Runtime"
  tags                  = local.common_tags
}

resource "aws_bedrockagentcore_gateway" "tools_mcp" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name            = "${local.name_prefix}-tools-mcp-gw"
  description     = "MCP tools gateway for WildRydes Runtime tool calls"
  role_arn        = aws_iam_role.agentcore_gateway.arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"

  protocol_configuration {
    mcp {
      instructions       = "WildRydes tools gateway for trip and application tools."
      supported_versions = ["2025-03-26", "2025-06-18"]
      session_configuration {
        session_timeout_in_seconds = 3600
      }
    }
  }

  tags = local.common_tags
}

data "aws_iam_policy_document" "tools_gateway_invocation_boundary" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  statement {
    sid     = "AllowOnlyRuntimeRole"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeGateway"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.agentcore_runtime.arn]
    }

    resources = [aws_bedrockagentcore_gateway.tools_mcp[0].gateway_arn]
  }

  statement {
    sid     = "DenyOtherGatewayInvokers"
    effect  = "Deny"
    actions = ["bedrock-agentcore:InvokeGateway"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [aws_bedrockagentcore_gateway.tools_mcp[0].gateway_arn]

    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = [aws_iam_role.agentcore_runtime.arn]
    }
  }
}

resource "aws_bedrockagentcore_resource_policy" "tools_gateway_invocation_boundary" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  resource_arn = aws_bedrockagentcore_gateway.tools_mcp[0].gateway_arn
  policy       = data.aws_iam_policy_document.tools_gateway_invocation_boundary[0].json
}
