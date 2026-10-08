# Token Bearer que os agentes enviam em `Authorization: Bearer <token>`.
# O valor é gerado aqui só na criação; rotações são feitas direto no Secrets
# Manager (veja o README) e o Terraform não as reverte (ignore_changes).
resource "random_password" "initial_token" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "auth_tokens" {
  name                    = "${var.name}/auth-tokens"
  description             = "Tokens Bearer aceitos pelo ${var.name} (separados por virgula)."
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "auth_tokens" {
  secret_id     = aws_secretsmanager_secret.auth_tokens.id
  secret_string = random_password.initial_token.result

  lifecycle {
    ignore_changes = [secret_string]
  }
}
