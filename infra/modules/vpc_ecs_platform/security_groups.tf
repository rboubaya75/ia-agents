# V2-LLD-001 §6 — Security Groups.
# sg-ingestion (§6.3) is a V3 target and is deliberately not created here.

resource "aws_security_group" "vpc_link" {
  name        = "${var.name_prefix}-sg-vpc-link"
  description = "ENIs of the API Gateway VPC Link fronting the internal ALB (V2-LLD-001 §6.1)."
  vpc_id      = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-sg-vpc-link"
  })
}

resource "aws_security_group" "alb_internal" {
  name        = "${var.name_prefix}-sg-alb-internal"
  description = "Internal ALB in front of the fastapi tasks (V2-LLD-001 §6.1)."
  vpc_id      = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-sg-alb-internal"
  })
}

resource "aws_security_group" "fastapi" {
  name        = "${var.name_prefix}-sg-fastapi"
  description = "ECS fastapi tasks (V2-LLD-001 §6.2)."
  vpc_id      = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-sg-fastapi"
  })
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-sg-vpc-endpoints"
  description = "Interface VPC endpoints, HTTPS from the ECS tasks only (V2-LLD-001 §6.4)."
  vpc_id      = aws_vpc.this.id

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-sg-vpc-endpoints"
  })
}

# §6.1 — sg-alb-internal
resource "aws_vpc_security_group_ingress_rule" "alb_from_vpc_link" {
  count = var.alb_plaintext_listener_enabled ? 0 : 1

  security_group_id            = aws_security_group.alb_internal.id
  description                  = "HTTPS from API Gateway through the VPC Link."
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.vpc_link.id
}

# Le port suit le listener retenu. Ouvrir les deux en permanence laisserait 443 béant
# sur un ALB qui n'y écoute pas, et 80 ouvert sur celui qui termine TLS.
resource "aws_vpc_security_group_ingress_rule" "alb_from_vpc_link_plaintext" {
  count = var.alb_plaintext_listener_enabled ? 1 : 0

  security_group_id            = aws_security_group.alb_internal.id
  description                  = "HTTP from API Gateway through the VPC Link (plaintext fallback)."
  ip_protocol                  = "tcp"
  from_port                    = 80
  to_port                      = 80
  referenced_security_group_id = aws_security_group.vpc_link.id
}

# Le VPC Link doit pouvoir sortir vers l'ALB : sans règle d'egress, les ENIs du lien
# n'atteignent rien et l'intégration expire au lieu d'échouer franchement.
resource "aws_vpc_security_group_egress_rule" "vpc_link_to_alb" {
  security_group_id            = aws_security_group.vpc_link.id
  description                  = "Reach the internal ALB listener."
  ip_protocol                  = "tcp"
  from_port                    = var.alb_plaintext_listener_enabled ? 80 : 443
  to_port                      = var.alb_plaintext_listener_enabled ? 80 : 443
  referenced_security_group_id = aws_security_group.alb_internal.id
}

resource "aws_vpc_security_group_egress_rule" "alb_to_fastapi" {
  security_group_id            = aws_security_group.alb_internal.id
  description                  = "Forward to the fastapi tasks."
  ip_protocol                  = "tcp"
  from_port                    = var.fastapi_container_port
  to_port                      = var.fastapi_container_port
  referenced_security_group_id = aws_security_group.fastapi.id
}

# §6.2 — sg-fastapi
resource "aws_vpc_security_group_ingress_rule" "fastapi_from_alb" {
  security_group_id            = aws_security_group.fastapi.id
  description                  = "Application traffic from the internal ALB."
  ip_protocol                  = "tcp"
  from_port                    = var.fastapi_container_port
  to_port                      = var.fastapi_container_port
  referenced_security_group_id = aws_security_group.alb_internal.id
}

resource "aws_vpc_security_group_egress_rule" "fastapi_to_endpoints" {
  security_group_id            = aws_security_group.fastapi.id
  description                  = "AWS API calls through the interface endpoints."
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.vpc_endpoints.id
}

# §6.2 third rule and §2.3 note — conditional exception. It exists only while the
# AgentCore Runtime PrivateLink endpoint is unavailable, and disappears the moment
# enable_agentcore_privatelink flips to true. Precondition 2 of §16.5.
resource "aws_vpc_security_group_egress_rule" "fastapi_agentcore_via_nat" {
  count = var.enable_agentcore_privatelink ? 0 : 1

  security_group_id = aws_security_group.fastapi.id
  description       = "Conditional exception: AgentCore Runtime through the NAT Gateway while no PrivateLink endpoint exists (V2-LLD-001 §2.3, §6.2)."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# §6.4 — sg-vpc-endpoints
resource "aws_vpc_security_group_ingress_rule" "endpoints_from_fastapi" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  description                  = "HTTPS from the fastapi tasks."
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.fastapi.id
}
