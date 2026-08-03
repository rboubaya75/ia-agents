output "rest_api_id" {
  description = "Identifiant du REST API V2."
  value       = aws_api_gateway_rest_api.this.id
}

output "execution_arn" {
  description = "ARN d'execution du REST API, racine des permissions execute-api."
  value       = aws_api_gateway_rest_api.this.execution_arn
}

output "stage_arn" {
  description = "ARN du stage, cible de l'association WAF."
  value       = aws_api_gateway_stage.this.arn
}

output "stage_name" {
  description = "Nom du stage deploye."
  value       = aws_api_gateway_stage.this.stage_name
}

output "invoke_url" {
  description = "URL d'invocation du stage. Joignable seulement a travers CloudFront : la politique de ressource refuse tout appel sans l'en-tete secret."
  value       = aws_api_gateway_stage.this.invoke_url
}

# CloudFront prend un nom d'hote, pas une URL. Le decoupage est fait ici plutot que sur
# le site d'appel, ou il serait recopie a chaque usage.
output "api_host_name" {
  description = "Nom d'hote de la passerelle, a utiliser comme origine CloudFront."
  value       = replace(replace(aws_api_gateway_stage.this.invoke_url, "https://", ""), "/${aws_api_gateway_stage.this.stage_name}", "")
}

output "origin_path" {
  description = "Chemin d'origine CloudFront correspondant au stage."
  value       = "/${aws_api_gateway_stage.this.stage_name}"
}

output "vpc_link_id" {
  description = "Identifiant du VPC Link V2 vers l'ALB interne."
  value       = aws_apigatewayv2_vpc_link.this.id
}

output "access_log_group_name" {
  description = "Groupe de journaux d'acces du stage."
  value       = aws_cloudwatch_log_group.access.name
}
