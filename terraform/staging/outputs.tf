output "ec2_public_ip" {
  description = "EIP attached to the backend EC2. Point Cloudflare api.staging A-record at this."
  value       = aws_eip.api.public_ip
}

output "ec2_instance_id" {
  description = "Use with `aws ssm start-session --target <id>` to shell into the box."
  value       = aws_instance.api.id
}

output "ecr_repo_url" {
  description = "Tag and push container images here."
  value       = aws_ecr_repository.api.repository_url
}

output "rds_endpoint" {
  description = "Postgres host. Set /aligniq/staging/POSTGRES_HOSTNAME to this value."
  value       = aws_db_instance.main.address
}

output "frontend_bucket" {
  description = "S3 bucket for the built React app (CI syncs `dist/` here)."
  value       = aws_s3_bucket.frontend.bucket
}

output "docs_bucket" {
  description = "S3 bucket for uploaded user documents. Set /aligniq/staging/S3_BUCKET_NAME to this."
  value       = aws_s3_bucket.docs.bucket
}

output "frontend_website_endpoint" {
  description = "S3 static-website endpoint. Cloudflare CNAMEs staging.<domain> here (proxy ON, SSL=Flexible)."
  value       = aws_s3_bucket_website_configuration.frontend.website_endpoint
}

output "github_deploy_role_arn" {
  description = "Set as the `role-to-assume` in the configure-aws-credentials GH Action step."
  value       = aws_iam_role.github_deploy.arn
}

output "api_log_group" {
  description = "CloudWatch log group for container stdout."
  value       = aws_cloudwatch_log_group.api.name
}
