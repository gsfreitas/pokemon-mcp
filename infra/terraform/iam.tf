data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Role usada pelo agente do ECS: puxar imagem, escrever logs, ler o secret.
resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_auth_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.auth_tokens.arn]
  }
}

resource "aws_iam_role_policy" "execution_read_secret" {
  name   = "read-auth-tokens"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_auth_secret.json
}

# Role da aplicação: sem permissões, pois o servidor só chama a PokeAPI.
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
