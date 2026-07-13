locals {
  agentcore_gateway_base_url = var.agentcore_gateway_url != "" ? trimsuffix(var.agentcore_gateway_url, "/") : trimsuffix(var.p0_agentcore_gateway_url, "/")
  agentcore_runtime_invoke_url = (
    local.agentcore_gateway_base_url != "" && var.agentcore_runtime_target_name != ""
    ? "${local.agentcore_gateway_base_url}/${var.agentcore_runtime_target_name}/invocations"
    : local.agentcore_gateway_base_url
  )

  security_facade_enabled = (
    var.security_facade_enabled &&
    var.facade_lambda_invoke_arn != "" &&
    var.facade_lambda_function_name != ""
  )
  gateway_first_enabled = var.gateway_first_enabled
}

check "security_facade_configuration" {
  assert {
    condition = (
      !var.security_facade_enabled ||
      (var.facade_lambda_invoke_arn != "" && var.facade_lambda_function_name != "")
    )
    error_message = "security_facade_enabled requires the Lambda invoke ARN and function name."
  }
}

check "exclusive_agent_ingress_mode" {
  assert {
    condition     = !(local.security_facade_enabled && local.gateway_first_enabled)
    error_message = "Security facade and historical Gateway-first ingress cannot be enabled together."
  }
}

resource "aws_cloudwatch_log_group" "access_logs" {
  name              = "/aws/apigateway/${var.name}"
  retention_in_days = var.access_log_retention_days

  tags = var.tags
}

resource "aws_apigatewayv2_api" "this" {
  name          = var.name
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["authorization", "content-type", "x-correlation-id"]
    allow_methods     = ["OPTIONS", "POST"]
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

resource "aws_apigatewayv2_integration" "security_facade" {
  count = local.security_facade_enabled ? 1 : 0

  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = var.facade_lambda_invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "agent_invoke_security_facade" {
  count = local.security_facade_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /agent/invoke"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.security_facade[0].id}"
}

resource "aws_apigatewayv2_integration" "agentcore_gateway" {
  count = local.gateway_first_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "POST"
  integration_uri    = local.agentcore_runtime_invoke_url
  timeout_milliseconds = 29000
}

resource "aws_apigatewayv2_route" "agent_invoke_gateway_first" {
  count = local.gateway_first_enabled ? 1 : 0

  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "POST /p0/agent/invoke"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.agentcore_gateway[0].id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access_logs.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
      responseLength          = "$context.responseLength"
      integrationErrorMessage = "$context.integrationErrorMessage"
      sourceIp                = "$context.identity.sourceIp"
      userAgent               = "$context.identity.userAgent"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = var.throttling_burst_limit
    throttling_rate_limit    = var.throttling_rate_limit
  }

  tags = var.tags
}

resource "aws_lambda_permission" "allow_api_gateway_agent_invoke" {
  count = local.security_facade_enabled ? 1 : 0

  statement_id  = "AllowAgentInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.facade_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/POST/agent/invoke"
}
