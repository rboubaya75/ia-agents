# V2-LLD-001 §7, §11.2 — internal ALB in front of the fastapi tasks.
#
# No public DNS: the ALB is reachable through the VPC Link only (§8). The VPC Link
# resource itself is not created here — precondition 4 of §16.5 (VPC Link V2 to an
# ALB in eu-west-3) is not yet verified, and its fallback changes the topology of §7.

resource "aws_lb" "internal" {
  name               = substr("${var.name_prefix}-int", 0, 32)
  internal           = true
  load_balancer_type = "application"
  subnets            = aws_subnet.private[*].id
  security_groups    = [aws_security_group.alb_internal.id]

  # §7.3 — bound to sse_keepalive_seconds. Both are checked together on the plan by
  # terraform_plan_guard rule 3, because a tfvars overriding one without the other is
  # exactly the case a per-variable validation cannot catch.
  idle_timeout = var.alb_idle_timeout_seconds

  drop_invalid_header_fields = true

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-alb-internal"
  })
}

resource "aws_lb_target_group" "fastapi" {
  name        = substr("${var.name_prefix}-fastapi", 0, 32)
  port        = var.fastapi_container_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.this.id

  deregistration_delay = var.alb_deregistration_delay_seconds

  # §11.2
  health_check {
    path                = "/health"
    protocol            = "HTTP"
    port                = "traffic-port"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  tags = merge(var.common_tags, {
    Name = "${var.name_prefix}-tg-fastapi"
  })
}

# The listener is HTTPS only (§7). It is created once an ACM certificate is supplied;
# without one there is nothing to terminate TLS with, and an HTTP listener would
# silently downgrade the VPC Link leg.
resource "aws_lb_listener" "https" {
  count = var.alb_certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.internal.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.alb_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.fastapi.arn
  }

  tags = var.common_tags
}
