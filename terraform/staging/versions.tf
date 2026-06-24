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
  #   aws s3api create-bucket --bucket groundediq-tfstate --region us-east-1
  #   aws s3api put-bucket-versioning --bucket groundediq-tfstate \
  #     --versioning-configuration Status=Enabled
  #   aws dynamodb create-table --table-name groundediq-tflocks \
  #     --attribute-definitions AttributeName=LockID,AttributeType=S \
  #     --key-schema AttributeName=LockID,KeyType=HASH \
  #     --billing-mode PAY_PER_REQUEST --region us-east-1
  backend "s3" {
    bucket         = "groundediq-tfstate"
    key            = "staging/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "groundediq-tflocks"
    encrypt        = true
  }
}
