terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Reuses the SAME state bucket + lock table as staging (bootstrapped once by
  # hand — see terraform/staging/versions.tf). Only the state KEY differs, so
  # production has its own isolated state file.
  backend "s3" {
    bucket         = "groundediq-tfstate"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "groundediq-tflocks"
    encrypt        = true
  }
}
