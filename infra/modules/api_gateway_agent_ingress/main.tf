locals {
  agentcore_gateway_base_url = var.agentcore_gateway_url != "" ? trimsuffix(var.agentcore_gateway_url, "/") : trimsuffix(var.p0_agentcore_gateway_url, "/")
  agentcore_runtime_invoke_url = (
    local.agentcore_gateway_base_url != "" && var.agentcore_runtime_target_name != ""
    ? "${local.agentcore_gateway_base_url}/${var.agentcore_runtime_target_name}/invocations"
    : local.agentcore_gateway_base_url
  )
  gateway_first_enabled = var.gateway_first_enabled
  legacy_facade_enabled = var.enable_legacy_facade && var.facade_lambda_invoke_arn != "" && var.facade_lambda_function_name != ""
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["authorization", "content-type", "x-correlation-id"]
    allow_methods     = ["GET", "OPTIONS", "POST"]
    allow_origins     = var.allowed_origins
    max_age           = 300
  }

  tags = var.tags
}

resource "aws_apigatewayv2_authorizer" "cognito_jwt" {
  api_id           = aws_apigatewayv2_api.this.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${var.name}-cognito-jwt"

  jwt_configuration {
    audience = var.jwt_audience
    issuer   = var.jwt_issuer
  }
}

resource "aws_apigatewayv2_integration" "agentcore_gateway" {
  count = local.gateway_first_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "POST"
  integration_uri    = local.agentcore_runtime_invoke_url
}

resource "aws_apigatewayv2_route" "agent_invoke_gateway_first" {
  count = local.gateway_first_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /agent/invoke"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.agentcore_gateway[0].id}"
}

resource "aws_apigatewayv2_route" "p0_agent_invoke_gateway_first" {
  count = local.gateway_first_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /p0/agent/invoke"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.agentcore_gateway[0].id}"
}

resource "aws_apigatewayv2_integration" "legacy_agent_facade" {
  count = local.legacy_facade_enabled ? 1 : 0

  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = var.facade_lambda_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "legacy_agent_invoke" {
  count = local.legacy_facade_enabled && !local.gateway_first_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /agent/invoke"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.legacy_agent_facade[0].id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  tags = var.tags
}

resource "aws_lambda_permission" "allow_api_gateway_agent_invoke" {
  count = local.legacy_facade_enabled ? 1 : 0

  statement_id  = "AllowAgentInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.facade_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*/agent/invoke"
}
