# V2-LLD-001 — socle plateforme ECS/Fargate V2.
#
# Le module est appelé sous condition : `enable_ecs_platform` vaut `false` par défaut,
# donc aucune ressource réseau ni de calcul n'est planifiée tant que l'image FastAPI
# n'existe pas (V2-LLD-001 §3). Le chemin V1 n'est pas touché.

module "vpc_ecs_platform" {
  source = "../../modules/vpc_ecs_platform"
  count  = var.enable_ecs_platform ? 1 : 0

  name_prefix = local.name_prefix
  common_tags = local.common_tags

  # §2 — topologie
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  nat_gateway_count    = var.nat_gateway_count

  # Cible V3 (V2-ADR-019) et précondition 2 de §16.5
  enable_ingestion_service     = var.enable_ingestion_service
  enable_agentcore_privatelink = var.enable_agentcore_privatelink

  # §4.1 — service fastapi
  fastapi_image      = var.fastapi_image
  fastapi_secrets    = var.fastapi_secrets
  log_retention_days = var.log_retention_days

  # §7.3 — les deux valeurs sont liées par l'invariant, jamais réglées séparément
  alb_idle_timeout_seconds = var.alb_idle_timeout_seconds
  sse_keepalive_seconds    = var.sse_keepalive_seconds
  alb_certificate_arn      = var.alb_certificate_arn

  # §7.1 — paramètres d'identité, jamais dérivés du token reçu
  cognito_issuer                    = var.cognito_issuer
  cognito_app_client_id             = var.cognito_app_client_id
  jwks_cache_ttl_seconds            = var.jwks_cache_ttl_seconds
  jwks_stale_tolerance_seconds      = var.jwks_stale_tolerance_seconds
  jwks_refresh_min_interval_seconds = var.jwks_refresh_min_interval_seconds

  # §5.1, §12.1 — cibles de la politique de rôle et chiffrement
  logs_kms_key_arn               = var.logs_kms_key_arn
  erasure_audit_log_group_name   = var.erasure_audit_log_group_name
  agentcore_runtime_arn          = var.fastapi_agentcore_runtime_arn
  knowledge_base_arn             = var.knowledge_base_arn
  knowledge_base_data_source_arn = var.knowledge_base_data_source_arn
  dynamodb_table_arns            = var.fastapi_dynamodb_table_arns
  commands_table_arns            = var.fastapi_commands_table_arns
  documents_bucket_arn           = var.documents_bucket_arn
  documents_cmk_arn              = var.documents_cmk_arn
}
