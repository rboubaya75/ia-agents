data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.region

  cluster_name = "${var.name_prefix}-v2"

  fastapi_log_group_name = "/ecs/${local.cluster_name}/fastapi"

  # V2-LLD-001 §12.1 — the module owns a CMK unless the environment supplies one.
  # one() rather than [0]: the index would be evaluated even on the branch that is
  # not taken in some expression contexts, and an empty list index is a hard error.
  create_logs_cmk  = var.logs_kms_key_arn == ""
  logs_kms_key_arn = local.create_logs_cmk ? one(aws_kms_key.logs[*].arn) : var.logs_kms_key_arn

  # V2-LLD-001 §2.3 — interface endpoints reachable from the private subnets.
  # xray is deliberately absent: it exists only to serve the ADOT sidecar, which the
  # MVP does not deploy. sqs is V3 only and gated by enable_ingestion_service.
  # bedrock-agentcore is absent until precondition 2 of §16.5 is verified.
  interface_endpoint_services = concat(
    [
      "ecr.api",
      "ecr.dkr",
      "secretsmanager",
      "kms",
      "bedrock-agent-runtime",
      "bedrock-agent",
      "bedrock-runtime",
      "logs",
      "monitoring",
      "sts",
    ],
    var.enable_agentcore_privatelink ? ["bedrock-agentcore"] : [],
    var.enable_ingestion_service ? ["sqs"] : [],
  )

  # Environment given to the fastapi container. sse_keepalive_seconds and the three JWKS
  # parameters have a single source of truth here — V2-LLD-001 §16.4 forbids duplicating
  # them as code constants.
  fastapi_environment = {
    SSE_KEEPALIVE_SECONDS             = tostring(var.sse_keepalive_seconds)
    COGNITO_ISSUER                    = var.cognito_issuer
    COGNITO_APP_CLIENT_ID             = var.cognito_app_client_id
    JWKS_CACHE_TTL_SECONDS            = tostring(var.jwks_cache_ttl_seconds)
    JWKS_STALE_TOLERANCE_SECONDS      = tostring(var.jwks_stale_tolerance_seconds)
    JWKS_REFRESH_MIN_INTERVAL_SECONDS = tostring(var.jwks_refresh_min_interval_seconds)
    # ARN is not a secret (V2-LLD-003 §12.1). Empty leaves the adapter in stub mode.
    AGENTCORE_RUNTIME_ARN        = var.agentcore_runtime_arn
    AGENT_RUNTIME_ENDPOINT_NAME  = var.agent_runtime_endpoint_name
  }
}
