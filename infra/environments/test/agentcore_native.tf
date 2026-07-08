resource "aws_bedrockagentcore_memory" "agent" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name                  = local.agentcore_memory_name
  description           = "WildRydes ${var.environment} AgentCore Memory"
  event_expiry_duration = var.agentcore_memory_event_expiry_days
  tags                  = local.common_tags
}

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  agent_runtime_name = local.agentcore_runtime_name
  description        = "WildRydes ${var.environment} AgentCore Runtime"
  role_arn           = aws_iam_role.agentcore_runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${module.agentcore_container_repository.repository_url}:${var.agentcore_image_tag}"
    }
  }

  environment_variables = {
    AWS_REGION         = var.region
    AWS_DEFAULT_REGION = var.region
    MODEL_ID           = var.agentcore_model_id
    LOG_LEVEL          = "INFO"
    SESSION_DIR        = "/tmp/sessions"
    ENABLE_RAG         = tostring(var.enable_rag)
    MEMORY_ID          = aws_bedrockagentcore_memory.agent[0].id
    GATEWAY_URL        = aws_bedrockagentcore_gateway.tools_mcp[0].gateway_url
    GATEWAY_AUTH_MODE  = "aws_iam"
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  tags = local.common_tags
}

resource "aws_bedrockagentcore_agent_runtime_endpoint" "default" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name                  = var.agent_runtime_endpoint_name
  agent_runtime_id      = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_id
  agent_runtime_version = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_version
  description           = "Default endpoint for WildRydes ${var.environment} AgentCore Runtime"
  tags                  = local.common_tags
}

resource "aws_bedrockagentcore_gateway" "ingress" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name            = "${local.name_prefix}-ingress-gw"
  description     = "HTTP ingress gateway routing API Gateway traffic to AgentCore Runtime"
  role_arn        = aws_iam_role.agentcore_gateway.arn
  authorizer_type = "CUSTOM_JWT"

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = "https://cognito-idp.${var.region}.amazonaws.com/${module.cognito_web_auth.user_pool_id}/.well-known/openid-configuration"
      allowed_clients = [module.cognito_web_auth.client_id]

      custom_claim {
        inbound_token_claim_name       = "token_use"
        inbound_token_claim_value_type = "STRING"

        authorizing_claim_match_value {
          claim_match_operator = "EQUALS"

          claim_match_value {
            match_value_string = "access"
          }
        }
      }
    }
  }

  tags = local.common_tags
}

resource "aws_bedrockagentcore_gateway_target" "runtime_http" {
  count = var.enable_agentcore_control_plane ? 1 : 0

  name               = "${local.name_prefix}-runtime-http"
  gateway_identifier = aws_bedrockagentcore_gateway.ingress[0].gateway_id
  description        = "HTTP target from AgentCore ingress gateway to AgentCore Runtime"

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    http {
      agentcore_runtime {
        arn = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn
      }
    }
  }
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
