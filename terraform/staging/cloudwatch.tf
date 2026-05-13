# Container stdout/stderr stream here via the awslogs Docker log driver
# (configured in ec2.tf user-data).
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aligniq/staging/api"
  retention_in_days = var.log_retention_days
  tags              = { Name = "${local.name_prefix}-api-logs" }
}
