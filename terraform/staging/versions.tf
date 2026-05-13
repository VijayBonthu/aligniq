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

  # Bootstrap once by hand:
  #   aws s3api create-bucket --bucket aligniq-tfstate --region us-east-1
  #   aws s3api put-bucket-versioning --bucket aligniq-tfstate \
  #     --versioning-configuration Status=Enabled
  #   aws dynamodb create-table --table-name aligniq-tflocks \
  #     --attribute-definitions AttributeName=LockID,AttributeType=S \
  #     --key-schema AttributeName=LockID,KeyType=HASH \
  #     --billing-mode PAY_PER_REQUEST --region us-east-1
  backend "s3" {
    bucket         = "aligniq-tfstate"
    key            = "staging/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "aligniq-tflocks"
    encrypt        = true
  }
}
