output "name_prefix" {
  value = local.name_prefix
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "frontend_bucket_name" {
  value = module.frontend_static_site.bucket_name
}

output "cloudfront_distribution_id" {
  value = module.frontend_static_site.cloudfront_distribution_id
}

output "cloudfront_domain_name" {
  value = module.frontend_static_site.cloudfront_domain_name
}

output "trips_table_name" {
  value = module.dynamodb_trips.table_name
}

output "trips_table_arn" {
  value = module.dynamodb_trips.table_arn
}

output "cognito_user_pool_id" {
  value = module.cognito_web_auth.user_pool_id
}

output "cognito_user_pool_arn" {
  value = module.cognito_web_auth.user_pool_arn
}

output "cognito_web_client_id" {
  value = module.cognito_web_auth.client_id
}

output "agentcore_ecr_repository_name" {
  value = module.agentcore_container_repository.repository_name
}

output "agentcore_ecr_repository_url" {
  value = module.agentcore_container_repository.repository_url
}

output "agentcore_ecr_repository_arn" {
  value = module.agentcore_container_repository.repository_arn
}
