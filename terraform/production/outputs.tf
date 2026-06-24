output "ec2_public_ip" {
  description = "EIP attached to the backend EC2. Point the Cloudflare api.grounded-iq.com A-record here (proxy ON)."
  value       = aws_eip.api.public_ip
}

output "ec2_instance_id" {
  description = "Set as the production EC2_INSTANCE_ID GitHub Environment secret; also `aws ssm start-session --target <id>`."
  value       = aws_instance.api.id
}

output "ecr_repo_url" {
  description = "Production ECR repo. The prod deploy workflow pushes images here."
  value       = aws_ecr_repository.api.repository_url
}

output "rds_endpoint" {
  description = "Postgres host. Set /groundediq/production/POSTGRES_HOSTNAME to this value."
  value       = aws_db_instance.main.address
}

output "frontend_bucket" {
  description = "S3 bucket for the built React app. Set as the production FRONTEND_BUCKET GitHub Environment secret."
  value       = aws_s3_bucket.frontend.bucket
}

output "docs_bucket" {
  description = "S3 bucket for uploaded user documents. Set /groundediq/production/S3_BUCKET_NAME to this."
  value       = aws_s3_bucket.docs.bucket
}

output "frontend_website_endpoint" {
  description = "S3 static-website endpoint. Cloudflare CNAMEs grounded-iq.com here (proxy ON). Use Full(strict) once an origin cert is installed."
  value       = aws_s3_bucket_website_configuration.frontend.website_endpoint
}

output "github_deploy_role_arn" {
  description = "Set as the production AWS_DEPLOY_ROLE_ARN GitHub Environment secret."
  value       = aws_iam_role.github_deploy.arn
}

output "api_log_group" {
  description = "CloudWatch log group for container stdout."
  value       = aws_cloudwatch_log_group.api.name
}

output "alerts_topic_arn" {
  description = "SNS topic for CloudWatch alarms. Confirm the email subscription from your inbox."
  value       = aws_sns_topic.alerts.arn
}
