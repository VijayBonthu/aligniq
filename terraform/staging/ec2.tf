# Cloudflare edge IPv4 ranges. Source: https://www.cloudflare.com/ips-v4
# Hardcoded instead of fetched at plan time because the fetch can be flaky
# from some networks. Re-check the URL every ~6 months and update this list.
locals {
  cloudflare_ipv4 = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
  ]
}

# Amazon Linux 2023 — has SSM agent preinstalled. Pick the latest official AMI.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "ec2" {
  name        = "${local.name_prefix}-ec2-sg"
  description = "Backend EC2 - HTTP from Cloudflare only, egress open."
  vpc_id      = aws_vpc.main.id

  # Cloudflare proxies user :443 -> origin :80. Cloudflare's edge IPs are the
  # only source allowed to reach the container's host port.
  ingress {
    description = "HTTP from Cloudflare edge"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = local.cloudflare_ipv4
  }

  # Allow your dev IP on 80 too, for direct curl while debugging origin.
  # If you don't want this, drop the block — SSM Session Manager still works
  # without any inbound port open.
  ingress {
    description = "HTTP from dev IP (debug)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.dev_ip_cidr]
  }

  egress {
    description = "All outbound - needs ECR, SSM, S3, OpenAI, Chroma, Stripe"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-ec2-sg" }
}

# IAM: EC2 needs SSM (Session Manager + Parameter Store read), ECR pull,
# CloudWatch Logs write, and access to the docs S3 bucket.
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${local.name_prefix}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# Managed policies for SSM (Session Manager + agent) and ECR read-only.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Inline policy: read SecureString params under /aligniq/staging/*, decrypt with
# the default SSM KMS key, and read/write the docs bucket.
data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "ec2_inline" {
  statement {
    sid     = "ReadStagingParams"
    actions = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/aligniq/staging/*"
    ]
  }

  statement {
    sid       = "DecryptParams"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"]
  }

  statement {
    sid = "DocsBucketRW"
    actions = [
      "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.docs.arn,
      "${aws_s3_bucket.docs.arn}/*",
    ]
  }

  statement {
    sid       = "WriteContainerLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "ec2_inline" {
  name   = "${local.name_prefix}-ec2-inline"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_inline.json
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${local.name_prefix}-ec2-profile"
  role = aws_iam_role.ec2.name
}

# user-data: install Docker + compose plugin, write the compose file, log in
# to ECR, pull, and start. Subsequent deploys happen via SSM Run-Command from
# GitHub Actions (docker compose pull api && up -d api).
locals {
  ecr_repo_url = aws_ecr_repository.api.repository_url

  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail

    dnf update -y
    dnf install -y docker
    systemctl enable --now docker
    usermod -aG docker ec2-user

    # docker compose v2 plugin
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -SL https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64 \
      -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

    # App directory
    mkdir -p /opt/aligniq
    cd /opt/aligniq

    cat >/opt/aligniq/docker-compose.yml <<'COMPOSE'
    services:
      api:
        image: ${local.ecr_repo_url}:latest
        restart: unless-stopped
        ports:
          - "80:8080"
        environment:
          - AWS_REGION=${var.aws_region}
          - SSM_PATH=/aligniq/staging/
          - REDIS_HOST=redis
          - REDIS_PORT=6379
          - REDIS_SSL=false
        depends_on:
          - redis
        logging:
          driver: awslogs
          options:
            awslogs-region: ${var.aws_region}
            awslogs-group: ${aws_cloudwatch_log_group.api.name}
            awslogs-stream: api
            awslogs-create-group: "true"
      redis:
        image: redis:7-alpine
        restart: unless-stopped
        command: ["redis-server", "--save", "", "--appendonly", "no"]
        logging:
          driver: awslogs
          options:
            awslogs-region: ${var.aws_region}
            awslogs-group: ${aws_cloudwatch_log_group.api.name}
            awslogs-stream: redis
            awslogs-create-group: "true"
    COMPOSE

    # ECR login + first pull (image must exist; CI pushes it before first apply)
    aws ecr get-login-password --region ${var.aws_region} \
      | docker login --username AWS --password-stdin ${local.ecr_repo_url} || true

    /usr/local/lib/docker/cli-plugins/docker-compose -f /opt/aligniq/docker-compose.yml pull || true
    /usr/local/lib/docker/cli-plugins/docker-compose -f /opt/aligniq/docker-compose.yml up -d || true
  EOT
}

resource "aws_instance" "api" {
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  associate_public_ip_address = true
  user_data                   = local.user_data

  metadata_options {
    http_tokens   = "required" # IMDSv2 only — blocks SSRF-style IMDS theft
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${local.name_prefix}-api" }

  # Changing user_data shouldn't recreate the box once it's running — we deploy
  # new container versions via SSM Run-Command, not by replacing the host.
  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "api" {
  domain   = "vpc"
  instance = aws_instance.api.id
  tags     = { Name = "${local.name_prefix}-api-eip" }
}
