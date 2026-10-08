locals {
  scheme = var.certificate_arn == null ? "http" : "https"
  host   = var.private_zone_id != null && var.dns_name != null ? var.dns_name : aws_lb.this.dns_name
}

output "mcp_url" {
  description = "URL que os agentes internos devem usar."
  value       = "${local.scheme}://${local.host}/mcp"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "auth_tokens_secret_arn" {
  description = "Secret com o(s) token(s) Bearer."
  value       = aws_secretsmanager_secret.auth_tokens.arn
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_service_name" {
  value = aws_ecs_service.this.name
}
