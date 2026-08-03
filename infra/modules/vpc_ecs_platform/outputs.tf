output "vpc_id" {
  description = "Platform VPC id."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "Platform VPC CIDR block."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet ids, NAT Gateway only."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet ids hosting the Fargate tasks and the internal ALB."
  value       = aws_subnet.private[*].id
}

output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "ECS fastapi service name."
  value       = aws_ecs_service.fastapi.name
}

output "task_definition_arn" {
  description = "ECS fastapi task definition ARN, revision included."
  value       = aws_ecs_task_definition.fastapi.arn
}

output "alb_arn" {
  description = "Internal ALB ARN."
  value       = aws_lb.internal.arn
}

output "alb_dns_name" {
  description = "Internal ALB DNS name, reachable through the VPC Link only."
  value       = aws_lb.internal.dns_name
}

output "target_group_arn" {
  description = "Target group ARN of the fastapi service."
  value       = aws_lb_target_group.fastapi.arn
}

output "security_group_ids" {
  description = "Security group ids by role."
  value = {
    alb_internal  = aws_security_group.alb_internal.id
    fastapi       = aws_security_group.fastapi.id
    vpc_endpoints = aws_security_group.vpc_endpoints.id
    vpc_link      = aws_security_group.vpc_link.id
  }
}

output "task_role_arn" {
  description = "ARN of ecs-task-role-fastapi."
  value       = aws_iam_role.fastapi.arn
}

output "execution_role_arn" {
  description = "ARN of the ECS task execution role."
  value       = aws_iam_role.execution.arn
}

output "logs_kms_key_arn" {
  description = "CMK protecting the ECS log groups."
  value       = local.logs_kms_key_arn
}

output "fastapi_log_group_name" {
  description = "CloudWatch log group of the fastapi service."
  value       = aws_cloudwatch_log_group.fastapi.name
}
