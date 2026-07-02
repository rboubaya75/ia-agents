module "agent_runtime_execution" {
  source = "../../modules/agentcore_runtime"

  name               = "${local.name_prefix}-agentcore-runtime"
  ecr_repository_arn = module.agentcore_container_repository.repository_arn
  ecr_repository_url = module.agentcore_container_repository.repository_url
  image_tag          = var.agentcore_image_tag
  model_id           = var.agentcore_model_id
  common_tags        = local.common_tags
}
