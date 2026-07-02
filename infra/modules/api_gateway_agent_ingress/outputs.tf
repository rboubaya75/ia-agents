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
