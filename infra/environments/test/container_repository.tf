module "agentcore_container_repository" {
  source = "../../modules/container_repository"

  name        = "${local.name_prefix}-agentcore-runtime"
  common_tags = local.common_tags
}
