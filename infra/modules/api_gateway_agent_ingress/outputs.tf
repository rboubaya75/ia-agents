output "api_id" {
  value = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.this.api_endpoint
}

output "execution_arn" {
  value = aws_apigatewayv2_api.this.execution_arn
}

output "stage_name" {
  value = aws_apigatewayv2_stage.default.name
}

output "jwt_authorizer_id" {
  value = aws_apigatewayv2_authorizer.cognito_jwt.id
}

output "jwt_issuer" {
  value = var.jwt_issuer
}

output "jwt_audience" {
  value = var.jwt_audience
}

output "security_facade_enabled" {
  value = local.security_facade_enabled
}

output "gateway_first_enabled" {
  value = local.gateway_first_enabled
}

output "agent_invoke_url" {
  value = local.security_facade_enabled ? "${aws_apigatewayv2_api.this.api_endpoint}/agent/invoke" : ""
}

output "access_log_group_name" {
  value = aws_cloudwatch_log_group.access_logs.name
}

output "p0_agentcore_gateway_enabled" {
  value = local.gateway_first_enabled
}

output "p0_agent_invoke_url" {
  value = local.gateway_first_enabled ? "${aws_apigatewayv2_api.this.api_endpoint}/p0/agent/invoke" : ""
}
