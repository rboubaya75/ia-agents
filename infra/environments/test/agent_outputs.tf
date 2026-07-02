output "agent_service_name" {
  value = module.agent_runtime_execution.runtime_name
}

output "agent_service_role_arn" {
  value = module.agent_runtime_execution.execution_role_arn
}

output "agent_service_image_uri" {
  value = module.agent_runtime_execution.image_uri
}

output "agent_service_model_id" {
  value = module.agent_runtime_execution.model_id
}
