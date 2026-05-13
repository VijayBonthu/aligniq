provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "aligniq"
      Environment = "staging"
      ManagedBy   = "terraform"
    }
  }
}
