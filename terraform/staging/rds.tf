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

  # Force TLS — no plaintext connections even on private subnets.
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name_prefix}-db"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = "db.t4g.micro"

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "aligniq"
  username = var.db_username
  password = var.db_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.pg16.name
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = 7
  backup_window           = "07:00-08:00"
  maintenance_window      = "sun:08:00-sun:09:00"

  # Staging-only: lets `terraform destroy` actually destroy it. Flip both
  # before promoting this stack to prod.
  deletion_protection = false
  skip_final_snapshot = true

  performance_insights_enabled = false
  apply_immediately            = true

  tags = { Name = "${local.name_prefix}-db" }
}
