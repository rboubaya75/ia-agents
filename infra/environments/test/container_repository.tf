module "agentcore_container_repository" {
  source = "../../modules/container_repository"

  name         = "${local.name_prefix}-agentcore-runtime"
  force_delete = true
  common_tags  = local.common_tags
}
