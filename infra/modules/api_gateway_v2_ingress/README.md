# `api_gateway_v2_ingress`

Chemin d'ingress du socle V2 (`V2-LLD-001` §7) : **CloudFront → API Gateway REST
Regional → VPC Link V2 → ALB interne → tâches ECS `fastapi`**.

Ce module porte le segment API Gateway et VPC Link. L'ALB, le cluster et les tâches
appartiennent à `vpc_ecs_platform` ; le comportement CloudFront `/api/*` appartient à
`frontend_static_site`, qui l'ajoute lorsque son entrée `api_origin` est renseignée.

---

## Décisions portées

**Un seul REST API Regional pour toutes les routes** (§7.0). Le motif n'est pas
l'identité — `V2-ADR-020` rend le contrat d'identité invariant au type d'API — mais
l'attachement du WAF et le point d'application unique de l'exigence de chemin unique
(§7.4). Un HTTP API n'accepte ni web ACL au stage ni politique de ressource : la
précondition 9 de §16.5 y resterait sans mécanisme vérifiable au plan.

**`responseTransferMode` réglé par méthode** (§7.0). `STREAM` sur la route
conversationnelle, `BUFFERED` sur l'annulation. Les deux routes sont déclarées
nommément plutôt que couvertes par un `{proxy+}` : le mode se règle par méthode, et une
route générique n'aurait aucun réglage opposable au plan Terraform.

**Le jeton traverse sans être consommé** (§7.1.2). L'authorizer Cognito lit
`Authorization` et le laisse intact pour l'intégration ; FastAPI revérifie la signature
par JWKS. Aucun mapping d'en-têtes de claims — c'est l'option A rejetée par
`V2-ADR-020`.

**Le type de jeton accepté se déclare par `authorizationScopes`** (§7.1.1). Un authorizer
`COGNITO_USER_POOLS` sans scope déclaré traite l'en-tête comme un jeton d'**identité** et
refuse tout jeton d'accès — 401 au bord, sans jamais appeler l'intégration. Le front
présentant un jeton d'accès, les méthodes déclarent `aws.cognito.signin.user.admin`.

Ce scope figure sur tout jeton d'accès du pool : il atteste « jeton d'accès valide de ce
pool », pas un droit métier. C'est indépassable tant que l'authentification passe par SRP
— les scopes d'un *resource server* n'existent que dans le flux OAuth2 code
d'autorisation. La finalité du contrôle au bord reste la disponibilité (§7.1.1) ;
l'identité de confiance est établie par FastAPI.

**Chemin unique par adresse source** (§7.4, précondition 9 de §16.5). La politique de
ressource refuse toute requête dont l'adresse source n'appartient pas à la liste de
préfixes gérée `com.amazonaws.global.cloudfront.origin-facing`.

Le filtre ne porte **pas** sur l'en-tête secret : une politique de ressource API Gateway
ne sait pas lire un en-tête arbitraire — `aws:RequestHeader` n'existe pas parmi les clés
de condition globales. Une condition bâtie dessus ne serait pas trop permissive, elle
serait fermée : la clé étant absente, `StringNotEquals` vaudrait vrai à chaque requête et
le `Deny` couperait tout le monde.

L'en-tête secret reste injecté par CloudFront comme second facteur, opposable seulement
par une règle WAF — donc une fois la précondition 8 levée. Tant que `web_acl_arn` est
vide, l'adresse source porte seule le contrôle.

La politique établit la *présence* du mécanisme ; son efficacité se démontre par l'appel
direct de §15, pas par lecture du plan — c'est exactement ce que constate la règle de
garde 4.

**Le rôle de journalisation est réglé au compte, pas au stage.** Un REST API n'écrit
aucun journal tant que le compte ne désigne pas, pour la région, un rôle que CloudWatch
Logs accepte : `UpdateStage` refuse `accessLogSettings` par *CloudWatch Logs role ARN
must be set in account settings to enable logging*. Le chemin V1 ne l'a jamais rencontré
parce qu'il repose sur un HTTP API, où la journalisation d'accès ne passe pas par ce
réglage.

Le module le provisionne — sans lui, son propre stage échoue. Mais
`aws_api_gateway_account` est un **singleton compte + région**, et le fournisseur 6.x
remet `/cloudwatchRoleArn` à null à la destruction, sans réglage pour s'y soustraire.
Deux instances de ce module dans la même région s'écraseraient donc, et retirer celle-ci
priverait de journaux toute autre REST API de la région. D'où
`manage_account_cloudwatch_role`, vrai par défaut, à passer à faux dès qu'une autre
autorité porte ce réglage.

---

## Écarts assumés

| Écart | Attendu | État livré | Motif |
|---|---|---|---|
| Listener ALB en clair | §7 : HTTPS 443, certificat ACM | HTTP 80 sur activation explicite | ACM n'émet pas pour le nom généré de l'ALB. Sans domaine possédé ni CA privée, l'alternative est « aucun listener », donc aucun chemin. Porté par `alb_plaintext_listener_enabled` du socle, faux par défaut. |
| WAF au stage | §7.4, précondition 8 | Optionnel, `web_acl_arn` vide par défaut | La précondition n'est pas vérifiée. Vide, le WAF ne subsiste que sur CloudFront et le risque résiduel est acté — pas constaté. |
| Repli VPC Link V1 + NLB | Précondition 4 de §16.5 | Non implémenté | Le module prend la voie nominale, VPC Link V2 direct vers l'ALB. Le repli ajoute un NLB, un saut réseau et un coût que §14.4 n'a pas provisionnés : il doit rester une décision, pas un glissement d'implémentation. Si l'apply échoue sur la précondition 4, c'est ce repli qu'il faut écrire. |
| Route 53 et domaine personnalisé | §8 | Absents | Aucun domaine n'est possédé. L'entrée publique est le domaine CloudFront. |
| Plafond d'intégration à 29 s | §7.3 : borne `deadlineEpochMs`, jusqu'à 15 min | 29 000 ms | Le plafond est un quota de compte, `Maximum integration timeout in milliseconds`, à 29 000 par défaut. Il est relevable sur une REST API Regional — le type retenu en §7.0 — mais au prix d'une réduction du quota de débit du compte, et sur demande dans Service Quotas. Tant qu'elle n'est pas obtenue, une réponse conversationnelle dépassant 29 s est coupée par la passerelle. Porté par `integration_timeout_quota_milliseconds` ; une valeur demandée au-delà échoue au plan, pas au `PutIntegration`. |

Ce que dégrade exactement le listener en clair : le tronçon VPC Link → ALB circule en
HTTP **dans les sous-réseaux privés du VPC**. TLS reste terminé à CloudFront puis à API
Gateway ; aucun trafic en clair ne quitte le VPC. Le risque résiduel est l'observation
intra-VPC, que les Security Groups de §6 bornent déjà.

---

## Entrées principales

| Variable | Rôle |
|---|---|
| `vpc_link_subnet_ids`, `vpc_link_security_group_ids` | ENIs du VPC Link — les sous-réseaux privés et `sg-vpc-link` du socle |
| `alb_dns_name`, `alb_arn`, `alb_listener_scheme`, `alb_listener_port` | Cible de l'intégration privée, fournis par les sorties du socle. `alb_arn` alimente `integration_target`, exigé par PutIntegration dès que `connection_id` référence un VPC Link v2 |
| `cognito_user_pool_arn` | Pool adossant l'authorizer (§7.1) |
| `authorization_scopes` | Non vide = la passerelle attend un **jeton d'accès** ; vide = un jeton d'identité. Ce réglage choisit le type de jeton, pas un droit métier |
| `conversation_response_transfer_mode` | `STREAM` par défaut ; `BUFFERED` est le repli de la précondition 3 |
| `origin_verify_secret` | Valeur partagée avec CloudFront, 32 caractères minimum |
| `manage_account_cloudwatch_role` | Vrai par défaut. Faux suppose que la région porte déjà un rôle de journalisation valide |
| `web_acl_arn` | Web ACL du stage ; vide = WAF sur CloudFront seul |

## Sorties principales

`rest_api_id`, `stage_arn`, `invoke_url`, `api_host_name`, `origin_path`, `vpc_link_id`,
`access_log_group_name`.

`api_host_name` et `origin_path` alimentent directement `api_origin` de
`frontend_static_site` : le découpage de l'URL d'invocation est fait ici plutôt que
recopié à chaque site d'appel.

---

## Ce que le module ne fait pas

- **Il ne prouve pas que le flux est progressif.** La précondition 5 de §16.5 demande une
  mesure de bout en bout ; les réglages de cache CloudFront sont nécessaires, pas
  suffisants.
- **Il ne prouve pas que le chemin unique est effectif.** La politique existe ; seul
  l'appel direct de §15 démontre qu'elle mord.
- **Il ne provisionne aucune route documentaire ni d'administration.** Seules les deux
  routes servies par le socle Lot A sont déclarées.
