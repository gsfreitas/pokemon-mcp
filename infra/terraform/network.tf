locals {
  listener_port = var.certificate_arn == null ? 80 : 443
}

# ------------------------------------------------------------------- ALB

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "ALB interno: aceita apenas as redes dos agentes"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cidrs" {
  for_each = toset(var.allowed_cidr_blocks)

  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = local.listener_port
  to_port           = local.listener_port
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_sgs" {
  for_each = toset(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = local.listener_port
  to_port                      = local.listener_port
}

resource "aws_vpc_security_group_egress_rule" "alb_to_service" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.service.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

# ----------------------------------------------------------------- tasks

resource "aws_security_group" "service" {
  name        = "${var.name}-service"
  description = "Tasks do MCP: recebem trafego apenas do ALB"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "service_from_alb" {
  security_group_id            = aws_security_group.service.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

# HTTPS de saída: PokeAPI, ECR, Secrets Manager e CloudWatch Logs.
resource "aws_vpc_security_group_egress_rule" "service_https_out" {
  security_group_id = aws_security_group.service.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
