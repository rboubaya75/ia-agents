# V2-LLD-001 §3, §4.1, §9.1, §10.1 — ECS cluster, task definition and service.

resource "aws_ecs_cluster" "this" {
  name = local.cluster_name

  # §3 asks for Container Insights. The MVP leaves it disabled: observability is
  # V2-LLD-007, which is deferred. Flipping this single value is the whole change.
  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(var.common_tags, {
    Name = local.cluster_name
  })
}

# FARGATE is declared available but no default strategy is set: the service states its
# launch type explicitly (§3), and a cluster-level default would only apply to services
# that state neither. Leaving it unset keeps the two from interacting.
resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE"]
}

# §4.1 — a single container. The adot-collector sidecar of §4.1 is absent for the
# same reason Container Insights is: it belongs to V2-LLD-007.
resource "aws_ecs_task_definition" "fastapi" {
  family                   = "${var.name_prefix}-fastapi"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.fastapi_cpu
  memory                   = var.fastapi_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.fastapi.arn

  container_definitions = jsonencode([
    {
      name      = "fastapi"
      image     = var.fastapi_image
      essential = true

      portMappings = [
        {
          containerPort = var.fastapi_container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        for name, value in local.fastapi_environment : {
          name  = name
          value = value
        }
      ]

      # §4.1 — never a plain environment variable.
      secrets = [
        for name, arn in var.fastapi_secrets : {
          name      = name
          valueFrom = arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.fastapi.name
          "awslogs-region"        = local.region
          "awslogs-stream-prefix" = "fastapi"
        }
      }

      # §11.3
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.fastapi_container_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = var.common_tags
}

resource "aws_ecs_service" "fastapi" {
  name            = "fastapi"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.fastapi.arn
  desired_count   = var.fastapi_desired_count
  launch_type     = "FARGATE"

  # §10.1
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.fastapi.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.fastapi.arn
    container_name   = "fastapi"
    container_port   = var.fastapi_container_port
  }

  # desired_count is owned by autoscaling once the service exists.
  lifecycle {
    ignore_changes = [desired_count]
  }

  # Les deux listeners sont mutuellement exclusifs ; la liste concatenee vaut donc
  # toujours un element, et la tache n'est jamais enregistree avant qu'un chemin existe.
  depends_on = [aws_lb_listener.https, aws_lb_listener.http]

  tags = var.common_tags
}

# §9.1 — target tracking on ALBRequestCountPerTarget.
resource "aws_appautoscaling_target" "fastapi" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.fastapi.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.fastapi_min_capacity
  max_capacity       = var.fastapi_max_capacity
}

resource "aws_appautoscaling_policy" "fastapi_requests" {
  name               = "${var.name_prefix}-fastapi-requests"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.fastapi.service_namespace
  resource_id        = aws_appautoscaling_target.fastapi.resource_id
  scalable_dimension = aws_appautoscaling_target.fastapi.scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value       = var.fastapi_requests_per_target
    scale_out_cooldown = 60
    scale_in_cooldown  = 300

    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.internal.arn_suffix}/${aws_lb_target_group.fastapi.arn_suffix}"
    }
  }
}
