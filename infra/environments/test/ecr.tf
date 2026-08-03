# V2-LLD-001 §4.1 — dépôt ECR du service fastapi.
# Provisionné indépendamment du socle ECS : enable_ecs_platform peut rester faux
# pendant que l'image est construite et poussée dans le registre.

module "fastapi_container_repository" {
  source = "../../modules/ecr_container_repository"

  name         = "${local.name_prefix}-fastapi"
  force_delete = true
  tags         = local.common_tags

  # ecs_platform.tf resout fastapi_image_tag en digest a chaque plan. Une expiration
  # par comptage pourrait supprimer l'image ainsi referencee — un tag epingle dans un
  # tfvars et depasse par les pushes suivants suffit — et le plan echouerait alors sur
  # une modification sans rapport. Seules les images sans tag expirent ici.
  #
  # Le depot croit donc sans borne. C'est le compromis accepte en test : borner
  # demanderait un nettoyage conscient des task definitions actives, qu'une politique
  # de cycle de vie ECR ne sait pas exprimer. A traiter avant la production.
  expire_tagged_images = false
}
