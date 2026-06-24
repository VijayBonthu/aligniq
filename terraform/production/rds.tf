resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = [for s in aws_subnet.private : s.id]
  tags       = { Name = "${local.name_prefix}-db-subnets" }
}

resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Postgres - only EC2 backend can reach 5432."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from app EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-rds-sg" }
}

resource "aws_db_parameter_group" "pg16" {
  name   = "${local.name_prefix}-pg16"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name_prefix}-db"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "groundediq"
  username = var.db_username
  password = var.db_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.pg16.name
  publicly_accessible    = false

  # HA toggle — false at launch to halve cost; flip to true (var.db_multi_az)
  # once paying customers depend on uptime. No network change needed (2 AZ subnets).
  multi_az = var.db_multi_az

  backup_retention_period = var.db_backup_retention_days
  backup_window           = "07:00-08:00"
  maintenance_window      = "sun:08:00-sun:09:00"
  copy_tags_to_snapshot   = true

  # Production safety: block accidental destroy, and ALWAYS take a final snapshot.
  deletion_protection       = var.db_deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name_prefix}-db-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
  apply_immediately            = false

  tags = { Name = "${local.name_prefix}-db" }

  # final_snapshot_identifier uses timestamp() which changes every plan; ignore
  # it so a no-op plan doesn't perpetually want to "change" the DB.
  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}
