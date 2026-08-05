# V2-LLD-001 §7 — chemin d'ingress V2 : REST API Regional -> VPC Link -> ALB interne.
#
# Le type d'API suit la décision de §7.0 : un seul REST API Regional pour toutes les
# routes. Le motif n'est pas l'identité — `V2-ADR-020` rend le contrat d'identité
# invariant au type d'API — mais l'attachement du WAF et le point d'application unique
# de l'exigence de chemin unique (§7.4). Un HTTP API n'accepte ni web ACL au stage ni
# politique de ressource, et laisserait la précondition 9 de §16.5 sans mécanisme
# vérifiable au plan.

locals {
  api_name = "${var.name_prefix}-v2-api"

  # §7 — l'intégration vise le listener de l'ALB par son nom DNS. Le VPC Link porte le
  # trafic dans le VPC ; le nom n'est jamais résolu depuis l'internet.
  alb_origin = "${var.alb_listener_scheme}://${var.alb_dns_name}:${var.alb_listener_port}"

  # Les deux routes servies par le socle. §7.0 les nomme plutôt que de les laisser à une
  # ligne générique, parce que `responseTransferMode` se règle par méthode : une route
  # couverte par un `{proxy+}` n'aurait aucun réglage opposable au plan Terraform.
  routes = {
    messages = {
      path_parts     = ["api", "v1", "conversations", "{conversation_id}", "messages"]
      http_method    = "POST"
      transfer_mode  = var.conversation_response_transfer_mode
      request_params = { "method.request.path.conversation_id" = true }
      integration_params = {
        "integration.request.path.conversation_id" = "method.request.path.conversation_id"
      }
      uri = "${local.alb_origin}/api/v1/conversations/{conversation_id}/messages"
    }
    cancel = {
      path_parts     = ["api", "v1", "operations", "{operation_id}", "cancel"]
      http_method    = "POST"
      transfer_mode  = "BUFFERED"
      request_params = { "method.request.path.operation_id" = true }
      integration_params = {
        "integration.request.path.operation_id" = "method.request.path.operation_id"
      }
      uri = "${local.alb_origin}/api/v1/operations/{operation_id}/cancel"
    }
  }

  # Les segments de chemin sont créés une seule fois et partagés : `api`, `api/v1` et la
  # suite sont communs aux deux routes. La clé est le chemin complet, la valeur son
  # parent.
  #
  # Un seul bloc for_each dont les instances se référencent mutuellement via
  # aws_api_gateway_resource.this[each.value.parent].id forme un cycle dans le graphe
  # de dépendances Terraform (le bloc entier est un nœud unique). Le découpage par
  # profondeur rompt le cycle : chaque bloc de profondeur N ne référence que le bloc
  # de profondeur N-1, qui est un type de ressource distinct.
  path_segments = {
    for path in distinct(flatten([
      for route in local.routes : [
        for index in range(length(route.path_parts)) :
        join("/", slice(route.path_parts, 0, index + 1))
      ]
      ])) : path => {
      part   = element(split("/", path), length(split("/", path)) - 1)
      parent = length(split("/", path)) == 1 ? "" : join("/", slice(split("/", path), 0, length(split("/", path)) - 1))
      depth  = length(split("/", path))
    }
  }

  path_depth_1 = { for k, v in local.path_segments : k => v if v.depth == 1 }
  path_depth_2 = { for k, v in local.path_segments : k => v if v.depth == 2 }
  path_depth_3 = { for k, v in local.path_segments : k => v if v.depth == 3 }
  path_depth_4 = { for k, v in local.path_segments : k => v if v.depth == 4 }
  path_depth_5 = { for k, v in local.path_segments : k => v if v.depth == 5 }
}

resource "aws_api_gateway_rest_api" "this" {
  name        = local.api_name
  description = "Ingress V2 vers le service FastAPI sur ECS (V2-LLD-001 sec. 7)."

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.common_tags

  # Le découpage s'arrête à `depth_5`, ce que les deux routes de §7.0 saturent
  # exactement. Un segment plus profond ne serait créé par aucun bloc et n'échouerait
  # qu'au moment du lookup dans `local.all_resources` — une clé absente, loin de sa
  # cause. La précondition ramène l'échec ici, avec le geste à faire.
  lifecycle {
    precondition {
      condition     = length([for segment in local.path_segments : segment if segment.depth > 5]) == 0
      error_message = "Un segment de chemin dépasse la profondeur 5 couverte par aws_api_gateway_resource.depth_1 à depth_5. Ajouter un bloc depth_6 et l'inclure dans local.all_resources."
    }
  }
}

# §7 — VPC Link V2 : cible directe l'ALB, sans NLB intermédiaire. C'est la précondition
# 4 de §16.5 ; son repli, VPC Link V1 devant un NLB, ajoute un composant, un saut réseau
# et un coût que §14.4 n'a pas provisionnés — il n'est pas implémenté ici, précisément
# pour qu'il reste une décision et non un glissement.
resource "aws_apigatewayv2_vpc_link" "this" {
  name               = "${var.name_prefix}-v2-link"
  subnet_ids         = var.vpc_link_subnet_ids
  security_group_ids = var.vpc_link_security_group_ids

  tags = var.common_tags
}

resource "aws_api_gateway_resource" "depth_1" {
  for_each    = local.path_depth_1
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = each.value.part
}

resource "aws_api_gateway_resource" "depth_2" {
  for_each    = local.path_depth_2
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.depth_1[each.value.parent].id
  path_part   = each.value.part
}

resource "aws_api_gateway_resource" "depth_3" {
  for_each    = local.path_depth_3
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.depth_2[each.value.parent].id
  path_part   = each.value.part
}

resource "aws_api_gateway_resource" "depth_4" {
  for_each    = local.path_depth_4
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.depth_3[each.value.parent].id
  path_part   = each.value.part
}

resource "aws_api_gateway_resource" "depth_5" {
  for_each    = local.path_depth_5
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.depth_4[each.value.parent].id
  path_part   = each.value.part
}

locals {
  all_resources = merge(
    aws_api_gateway_resource.depth_1,
    aws_api_gateway_resource.depth_2,
    aws_api_gateway_resource.depth_3,
    aws_api_gateway_resource.depth_4,
    aws_api_gateway_resource.depth_5,
  )
}

# §7.1 — l'authorizer rejette le non authentifié au bord. FastAPI revérifie la signature
# par JWKS derrière : la passerelle ne remplace pas cette vérification, elle épargne au
# socle le trafic anonyme.
resource "aws_api_gateway_authorizer" "cognito" {
  name          = "${var.name_prefix}-v2-cognito"
  rest_api_id   = aws_api_gateway_rest_api.this.id
  type          = "COGNITO_USER_POOLS"
  provider_arns = [var.cognito_user_pool_arn]

  # §7.1.2 — l'en-tête est transmis tel quel à l'intégration, jamais consommé ni
  # retraduit en claims. C'est l'option A explicitement rejetée par V2-ADR-020.
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_method" "this" {
  for_each = local.routes

  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = local.all_resources[join("/", each.value.path_parts)].id
  http_method   = each.value.http_method
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id

  request_parameters = each.value.request_params
}

resource "aws_api_gateway_integration" "this" {
  for_each = local.routes

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = local.all_resources[join("/", each.value.path_parts)].id
  http_method = aws_api_gateway_method.this[each.key].http_method

  type                    = "HTTP_PROXY"
  integration_http_method = each.value.http_method
  uri                     = each.value.uri

  connection_type = "VPC_LINK"
  connection_id   = aws_apigatewayv2_vpc_link.this.id

  # Le VPC Link v2 ne porte pas seul la cible : PutIntegration exige `integration_target`
  # des lors que `connection_id` reference un VPC Link v2 (l'ARN de l'ALB), faute de quoi
  # l'API renvoie « IntegrationTarget is required for VpcLinkV2 ». `uri` reste la valeur
  # d'en-tete Host, elle ne route plus la requete.
  integration_target = var.alb_arn

  # §7.0 — réglage par méthode et non par API.
  response_transfer_mode = each.value.transfer_mode

  timeout_milliseconds = var.integration_timeout_milliseconds

  request_parameters = each.value.integration_params

  lifecycle {
    precondition {
      condition     = var.integration_timeout_milliseconds <= var.integration_timeout_quota_milliseconds
      error_message = "Le plafond d'integration demande depasse le quota du compte. Relever « Maximum integration timeout in milliseconds » dans Service Quotas pour API Gateway, puis porter integration_timeout_quota_milliseconds a la meme valeur."
    }
  }
}

# §7.4, précondition 9 de §16.5 — mécanisme de chemin unique.
#
# Le filtre porte sur l'adresse source et non sur l'en-tête secret injecté par
# CloudFront. Une politique de ressource API Gateway ne sait pas lire un en-tête
# arbitraire : `aws:RequestHeader` n'existe pas parmi les clés de condition globales, et
# une condition bâtie dessus ne serait pas « permissive à tort » — la clé étant absente,
# un `StringNotEquals` vaudrait vrai à chaque requête et le `Deny` fermerait la
# passerelle à tout le monde. Le seul mécanisme déclaratif disponible ici est la liste
# de préfixes gérée `com.amazonaws.global.cloudfront.origin-facing`, qu'AWS maintient et
# qui énumère les adresses par lesquelles CloudFront joint une origine.
#
# L'en-tête secret est conservé côté CloudFront comme second facteur : il n'est opposable
# qu'à travers une règle WAF, donc seulement une fois la précondition 8 levée. Tant que
# `web_acl_arn` est vide, c'est l'adresse source qui porte seule le contrôle.
#
# La politique établit la présence du mécanisme ; son efficacité se démontre par l'appel
# direct de §15, pas par lecture du plan.
data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

data "aws_iam_policy_document" "single_path" {
  statement {
    sid       = "AllowInvokeThroughAnyCaller"
    effect    = "Allow"
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.this.execution_arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
  }

  statement {
    sid       = "DenyWhenNotThroughCloudFront"
    effect    = "Deny"
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.this.execution_arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "NotIpAddress"
      variable = "aws:SourceIp"
      values   = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.entries[*].cidr
    }
  }
}

resource "aws_api_gateway_rest_api_policy" "single_path" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  policy      = data.aws_iam_policy_document.single_path.json
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${local.api_name}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_kms_key_arn == "" ? null : var.logs_kms_key_arn

  tags = var.common_tags
}

# Un REST API n'ecrit aucun journal — ni d'acces, ni d'execution — tant que le compte
# ne designe pas, pour la region, un role que CloudWatch Logs accepte. Ce n'est pas un
# reglage du stage : `UpdateStage` refuse `accessLogSettings` par « CloudWatch Logs role
# ARN must be set in account settings to enable logging ». Le chemin V1 ne l'a jamais
# rencontre parce qu'il est bati sur un HTTP API, ou la journalisation d'acces ne passe
# pas par ce reglage.
#
# La ressource est un singleton compte + region, et le fournisseur 6.x remet
# /cloudwatchRoleArn a null a la destruction, sans reglage pour s'y soustraire. Deux
# instances de ce module dans la meme region s'ecraseraient donc, et retirer celle-ci
# priverait de journaux toute autre REST API de la region. C'est pourquoi elle est
# desactivable plutot que systematique, et pourquoi le motif est ecrit ici : il ne se
# lit pas sur le plan, qui ne montre qu'une ressource de plus.
data "aws_partition" "current" {}

data "aws_iam_policy_document" "account_cloudwatch_assume" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  statement {
    sid     = "ApiGatewayAssumeRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "account_cloudwatch" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  name               = "${var.name_prefix}-apigw-cloudwatch"
  description        = "Role assume par API Gateway pour ecrire les journaux du compte (V2-LLD-001 sec. 12.1)."
  assume_role_policy = data.aws_iam_policy_document.account_cloudwatch_assume[0].json

  tags = var.common_tags
}

# La politique geree est celle qu'AWS designe pour cet usage. Une politique ecrite a la
# main devrait enumerer les actions Describe/Get/Put des journaux et serait un doublon
# silencieusement decale des que le service en ajoute une.
resource "aws_iam_role_policy_attachment" "account_cloudwatch" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  role       = aws_iam_role.account_cloudwatch[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "this" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  cloudwatch_role_arn = aws_iam_role.account_cloudwatch[0].arn

  # L'attachement n'est reference par aucun attribut : sans cette arete, Terraform peut
  # designer le role au compte avant que la politique n'y soit attachee, et API Gateway
  # rejette alors un role qui ne peut rien ecrire.
  depends_on = [aws_iam_role_policy_attachment.account_cloudwatch]
}

# Le redéploiement suit le contenu de l'API. Sans ce déclencheur, une modification de
# route ou d'intégration resterait dans la définition sans jamais atteindre le stage —
# le plan serait vert et le comportement inchangé.
resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode([
      local.all_resources,
      aws_api_gateway_method.this,
      aws_api_gateway_integration.this,
      aws_api_gateway_authorizer.cognito,
      aws_api_gateway_rest_api_policy.single_path.policy,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationErr = "$context.integration.error"
      # Jamais le corps ni l'en-tête Authorization : le jeton s'arrête à FastAPI (§7.1.2)
      # et un journal d'accès qui le porterait le ferait vivre bien au-delà.
    })
  }

  tags = var.common_tags

  # Le reglage du compte n'est lie au stage par aucun attribut, alors qu'il le
  # conditionne entierement : `access_log_settings` echoue sans lui.
  depends_on = [aws_api_gateway_account.this]
}

resource "aws_api_gateway_method_settings" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.throttling_rate_limit
    throttling_burst_limit = var.throttling_burst_limit

    # Le cache reste désactivé : une réponse conversationnelle est propre à un acteur et
    # à une conversation, la mettre en cache la servirait à un autre.
    caching_enabled = false
  }
}

# §7.4, précondition 8 de §16.5 — l'association se fait au stage d'un REST API. Sur
# échec de la précondition, le WAF ne subsiste que sur CloudFront et le risque résiduel
# est acté ; la variable vide traduit exactement cet état.
resource "aws_wafv2_web_acl_association" "this" {
  count = var.web_acl_arn == "" ? 0 : 1

  resource_arn = aws_api_gateway_stage.this.arn
  web_acl_arn  = var.web_acl_arn
}
