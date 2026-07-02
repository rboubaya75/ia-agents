output "runtime_name" {
  value = var.name
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "execution_role_name" {
  value = aws_iam_role.execution.name
}

output "image_uri" {
  value = local.image_uri
}

output "model_id" {
  value = var.model_id
}

output "log_level" {
  value = var.log_level
}
