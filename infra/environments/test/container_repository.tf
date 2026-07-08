module "agentcore_container_repository" {
  source = "../../modules/ecr_container_repository"

  name         = "${local.name_prefix}-agentcore-runtime"
  force_delete = true
  tags         = local.common_tags
}
