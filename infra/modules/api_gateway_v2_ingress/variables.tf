variable "name_prefix" {
  type        = string
  description = "Prefix applied to every resource name."
}

variable "common_tags" {
  type        = map(string)
  description = "Tags applied to every resource."
  default     = {}
}

# ---------------------------------------------------------------------------
# Cible privée — V2-LLD-001 §7
# ---------------------------------------------------------------------------

variable "vpc_link_subnet_ids" {
  type        = list(string)
  description = "Sous-reseaux prives portant les ENIs du VPC Link (V2-LLD-001 §2.2)."
}

variable "vpc_link_security_group_ids" {
  type        = list(string)
  description = "Security groups des ENIs du VPC Link, `sg-vpc-link` du socle (V2-LLD-001 §6.1)."
}

variable "alb_dns_name" {
  type        = string
  description = "Nom DNS de l'ALB interne, cible de l'integration privee."
}

# Le Host attendu par les taches (`uri`) et la cible reellement joignable par le VPC
# Link v2 (`integration_target`) sont deux informations distinctes depuis que l'API
# Gateway REST route au travers d'un VPC Link v2 : l'ARN designe l'ALB au niveau
# reseau, le DNS reste la valeur d'en-tete Host vue par l'integration HTTP_PROXY.
variable "alb_arn" {
  type        = string
  description = "ARN de l'ALB interne. Requis par `integration_target` pour toute integration REST API adossee a un VPC Link v2 (V2-LLD-001 §7)."
}

variable "alb_listener_scheme" {
  type        = string
  description = "Schema de l'URI d'integration : https en nominal, http sur le repli en clair du socle."

  validation {
    condition     = contains(["http", "https"], var.alb_listener_scheme)
    error_message = "alb_listener_scheme doit valoir http ou https."
  }
}

variable "alb_listener_port" {
  type        = number
  description = "Port du listener actif de l'ALB interne."
}

# ---------------------------------------------------------------------------
# Identité — V2-LLD-001 §7.1
# ---------------------------------------------------------------------------

variable "cognito_user_pool_arn" {
  type        = string
  description = "ARN du pool Cognito adossant l'authorizer de la passerelle (V2-LLD-001 §7.1)."
}

# ---------------------------------------------------------------------------
# Streaming — V2-LLD-001 §7.0, §7.3
# ---------------------------------------------------------------------------

# §7.0 regle `responseTransferMode` par methode. STREAM est le mode nominal de la route
# conversationnelle ; la precondition 3 de §16.5 prevoit le repli `BUFFERED`, ou le flux
# reste servi mais arrive d'un bloc — le client l'apprend par le champ `streaming` de
# l'evenement `meta`, jamais par surprise.
variable "conversation_response_transfer_mode" {
  type        = string
  description = "Mode de transfert de la route conversationnelle (V2-LLD-001 §7.0)."
  default     = "STREAM"

  validation {
    condition     = contains(["STREAM", "BUFFERED"], var.conversation_response_transfer_mode)
    error_message = "conversation_response_transfer_mode doit valoir STREAM ou BUFFERED."
  }
}

variable "integration_timeout_milliseconds" {
  type        = number
  description = "Plafond d'une invocation d'integration. Borne `deadlineEpochMs` de V2-LLD-003 §5.2.2 (V2-LLD-001 §7.3)."
  default     = 29000

  validation {
    condition     = var.integration_timeout_milliseconds >= 50 && var.integration_timeout_milliseconds <= 900000
    error_message = "Le plafond d'integration doit valoir au moins 50 ms et tenir dans les 15 minutes de V2-LLD-001 §7.3."
  }
}

# Le plafond d'integration n'est pas une constante d'API Gateway mais un quota de
# compte : « Maximum integration timeout in milliseconds » vaut 29 000 par defaut et
# n'est relevable que pour les REST API Regional et privees — le type retenu en §7.0 —
# au prix d'une reduction du quota de debit du compte.
#
# Le declarer en variable rend l'ecart opposable au plan. Sans lui, un plafond
# superieur au quota ne se decouvre qu'au PutIntegration, c'est-a-dire au milieu d'un
# apply deja partiellement joue.
variable "integration_timeout_quota_milliseconds" {
  type        = number
  description = "Quota « Maximum integration timeout in milliseconds » du compte. 29000 est le defaut AWS ; relever cette valeur une fois l'augmentation obtenue."
  default     = 29000

  validation {
    condition     = var.integration_timeout_quota_milliseconds >= 50
    error_message = "Le quota d'integration d'API Gateway ne descend pas sous 50 ms."
  }
}

# ---------------------------------------------------------------------------
# Chemin unique — V2-ADR-016, V2-LLD-001 §7.4, precondition 9 de §16.5
# ---------------------------------------------------------------------------

variable "origin_verify_header_name" {
  type        = string
  description = "En-tete injecte par CloudFront et exige par la politique de ressource de la passerelle (V2-LLD-001 §7.4)."
  default     = "x-origin-verify"
}

variable "origin_verify_secret" {
  type        = string
  description = "Valeur partagee entre CloudFront et la politique de ressource. Rend CloudFront seul chemin joignable."
  sensitive   = true

  validation {
    condition     = length(var.origin_verify_secret) >= 32
    error_message = "Le secret de chemin unique doit faire au moins 32 caracteres : il est le seul obstacle a l'appel direct de la passerelle."
  }
}

# ---------------------------------------------------------------------------
# Exploitation
# ---------------------------------------------------------------------------

variable "stage_name" {
  type        = string
  description = "Nom du stage de la passerelle."
  default     = "v1"
}

variable "log_retention_days" {
  type        = number
  description = "Retention des journaux d'acces du stage."
  default     = 30
}

variable "logs_kms_key_arn" {
  type        = string
  description = "CMK chiffrant les journaux d'acces (V2-LLD-001 §12.1). La cle doit autoriser logs.<region>.amazonaws.com sur le contexte /aws/apigateway/* : celle du socle ne couvre que /ecs/ et le journal d'effacement."
  default     = ""
}

# Le role de journalisation d'API Gateway est un singleton compte + region, pas une
# propriete du stage. Le module le provisionne parce que sans lui son propre stage
# echoue ; la variable existe pour le cas ou le compte le porte deja — seconde instance
# du module dans la region, ou role gere par une autre equipe.
variable "manage_account_cloudwatch_role" {
  type        = bool
  description = "Cree le role de journalisation d'API Gateway et le designe au compte. Faux suppose qu'un role valide est deja regle pour la region, sans quoi le stage echoue a l'apply."
  default     = true
}

variable "throttling_rate_limit" {
  type        = number
  description = "Debit soutenu autorise sur le stage."
  default     = 20
}

variable "throttling_burst_limit" {
  type        = number
  description = "Rafale autorisee sur le stage."
  default     = 40
}

variable "web_acl_arn" {
  type        = string
  description = "ARN du web ACL WAF associe au stage (V2-ADR-016, precondition 8 de §16.5). Vide = aucune association."
  default     = ""
}
