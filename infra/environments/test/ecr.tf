# V2-LLD-001 §4.1 — dépôt ECR du service fastapi.
# Provisionné indépendamment du socle ECS : enable_ecs_platform peut rester faux
# pendant que l'image est construite et poussée dans le registre.

module "fastapi_container_repository" {
  source = "../../modules/ecr_container_repository"

  name         = "${local.name_prefix}-fastapi"
  force_delete = true
  tags         = local.common_tags
}
