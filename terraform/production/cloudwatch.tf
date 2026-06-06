# Container stdout/stderr streams here via the awslogs Docker log driver
# (configured in ec2.tf user-data). LOG_LEVEL=WARNING in prod SSM keeps this quiet.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/groundediq/production/api"
  retention_in_days = var.log_retention_days
  tags              = { Name = "${local.name_prefix}-api-logs" }
}
