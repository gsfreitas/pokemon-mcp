terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configure o backend remoto da empresa (o state contém o token gerado!):
  # backend "s3" {
  #   bucket       = "minha-empresa-terraform-state"
  #   key          = "pokemon-mcp/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      Service   = var.name
      ManagedBy = "terraform"
    })
  }
}
