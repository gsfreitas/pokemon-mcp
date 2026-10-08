variable "name" {
  description = "Prefixo dos recursos."
  type        = string
  default     = "pokemon-mcp"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "tags" {
  type    = map(string)
  default = {}
}

# ------------------------------------------------------------------ rede

variable "vpc_id" {
  description = "VPC onde o serviço e o ALB interno vão rodar."
  type        = string
}

variable "private_subnet_ids" {
  description = "Subnets privadas (>= 2 AZs). Precisam de saída para a internet (NAT) para alcançar a PokeAPI."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "O ALB exige subnets em pelo menos duas AZs."
  }
}

variable "allowed_cidr_blocks" {
  description = "CIDRs das redes dos agentes internos (outras VPCs, VPN, Direct Connect) que podem chamar o MCP."
  type        = list(string)
  default     = []
}

variable "allowed_security_group_ids" {
  description = "Security groups dos agentes (na mesma VPC) que podem chamar o MCP."
  type        = list(string)
  default     = []
}

# ----------------------------------------------------------- TLS e DNS

variable "certificate_arn" {
  description = "Certificado ACM para HTTPS no ALB. Fortemente recomendado: sem ele o token trafega em texto puro."
  type        = string
  default     = null
}

variable "private_zone_id" {
  description = "Hosted zone privada do Route 53 para criar o nome DNS (opcional)."
  type        = string
  default     = null
}

variable "dns_name" {
  description = "Nome DNS completo, ex.: pokemon-mcp.interno.empresa.com (usado com private_zone_id)."
  type        = string
  default     = null
}

# --------------------------------------------------------------- runtime

variable "image_tag" {
  description = "Tag da imagem no ECR a ser implantada (o repositório é imutável: use versões, não 'latest')."
  type        = string
}

variable "cpu_architecture" {
  description = "X86_64 ou ARM64 (ARM64 é mais barato; a imagem precisa ser construída para essa arquitetura)."
  type        = string
  default     = "X86_64"

  validation {
    condition     = contains(["X86_64", "ARM64"], var.cpu_architecture)
    error_message = "Use X86_64 ou ARM64."
  }
}

variable "cpu" {
  type    = number
  default = 256
}

variable "memory" {
  type    = number
  default = 512
}

variable "desired_count" {
  description = "Mínimo de tasks (2 = uma por AZ, para alta disponibilidade)."
  type        = number
  default     = 2
}

variable "max_count" {
  type    = number
  default = 6
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "log_retention_days" {
  type    = number
  default = 30
}
