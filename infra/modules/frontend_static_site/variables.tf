variable "name_prefix" {
  type        = string
  description = "Name prefix used for frontend delivery resources."
}

variable "bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for private frontend assets."
}

variable "force_destroy" {
  type        = bool
  description = "Allow Terraform to delete the frontend bucket even when it contains objects. Test only."
  default     = false
}

variable "price_class" {
  type        = string
  description = "CloudFront price class."
  default     = "PriceClass_100"
}

variable "content_security_policy" {
  type        = string
  description = "Content-Security-Policy applied by CloudFront to frontend responses."

  validation {
    condition     = length(trimspace(var.content_security_policy)) > 0 && can(regex("default-src", var.content_security_policy))
    error_message = "content_security_policy must be non-empty and contain a default-src directive."
  }
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to resources supporting tags."
  default     = {}
}

# V2-LLD-001 §7, §7.4 — origine API optionnelle.
#
# Renseignée, elle ajoute un comportement `/api/*` visant API Gateway et injecte
# l'en-tête secret que la politique de ressource de la passerelle exige. C'est ce qui
# fait de CloudFront le seul chemin joignable (V2-ADR-016, précondition 9 de §16.5).
#
# Elle sert aussi le front : servi et appelé depuis la même origine, le chemin
# conversationnel n'a aucun préflight CORS à négocier, et le jeton ne traverse jamais
# une frontière d'origine.
#
# Nulle par défaut : le chemin V1 ne déclare pas d'origine API et n'est pas modifié.
#
# Le secret est porté par `api_origin_verify_secret` et non par un champ de cet objet.
# Une valeur sensible contamine toute expression qui la touche — y compris le simple
# test « une origine API est-elle déclarée ? » — et Terraform refuse une valeur sensible
# en `for_each`. Séparer garde la marque de sensibilité sur le seul secret.
variable "api_origin" {
  type = object({
    domain_name        = string
    origin_path        = string
    verify_header_name = string
  })
  description = "Origine API Gateway servie sous /api/*. Null pour ne pas en déclarer."
  default     = null
}

variable "api_origin_verify_secret" {
  type        = string
  description = "Valeur de l'en-tête de vérification injecté vers l'origine API. Requis dès que api_origin est renseigné."
  default     = ""
  sensitive   = true
}
