# V2-LLD-001 §7 — chemin d'ingress V2 : CloudFront -> API Gateway -> VPC Link -> ALB.
#
# Conditionné par `enable_ecs_ingress`, lui-même sans effet tant que le socle n'est pas
# provisionné : la passerelle n'a rien à viser sans ALB. Le chemin V1 conserve sa propre
# passerelle (api_gateway.tf) et n'est pas touché.

# Le secret de chemin unique n'est ni saisi ni versionné : il est tiré une fois et vit
# dans l'état Terraform, comme toute valeur générée. Le mettre dans un tfvars le ferait
# transiter par un dépôt, et Secrets Manager demanderait à CloudFront de le lire à
# l'exécution, ce qu'une origine custom ne sait pas faire — l'en-tête est statique.
resource "random_password" "origin_verify" {
  count = var.enable_ecs_ingress ? 1 : 0

  length  = 48
  special = false
}

module "api_gateway_v2_ingress" {
  source = "../../modules/api_gateway_v2_ingress"
  count  = var.enable_ecs_ingress && var.enable_ecs_platform ? 1 : 0

  name_prefix = local.name_prefix
  common_tags = local.common_tags

  # §7 — cible privée. Les trois valeurs viennent du socle : le module d'ingress ne
  # redécouvre rien et ne peut pas viser un ALB dont il aurait deviné le nom.
  vpc_link_subnet_ids         = module.vpc_ecs_platform[0].private_subnet_ids
  vpc_link_security_group_ids = [module.vpc_ecs_platform[0].security_group_ids.vpc_link]
  alb_dns_name                = module.vpc_ecs_platform[0].alb_dns_name
  alb_arn                     = module.vpc_ecs_platform[0].alb_arn
  alb_listener_scheme         = module.vpc_ecs_platform[0].alb_listener_scheme
  alb_listener_port           = module.vpc_ecs_platform[0].alb_listener_port

  # §7.1 — le pool V1 est réutilisé : c'est le même utilisateur qui se connecte, et
  # dupliquer le pool dupliquerait les identités sans rien isoler.
  cognito_user_pool_arn = module.cognito_web_auth.user_pool_arn

  conversation_response_transfer_mode = var.apigw_response_transfer_mode
  integration_timeout_milliseconds    = var.apigw_integration_timeout_milliseconds

  # Le quota du compte est passe au module pour que le depassement echoue au plan et
  # non au PutIntegration, en plein apply.
  integration_timeout_quota_milliseconds = var.apigw_integration_timeout_quota_milliseconds

  origin_verify_secret = one(random_password.origin_verify[*].result)

  log_retention_days = var.log_retention_days
  logs_kms_key_arn   = var.logs_kms_key_arn
  web_acl_arn        = var.apigw_web_acl_arn
}
