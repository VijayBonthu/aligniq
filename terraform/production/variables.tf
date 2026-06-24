variable "aws_region" {
  description = "AWS region for all production resources."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used as a prefix on most resources."
  type        = string
  default     = "groundediq"
}

variable "environment" {
  description = "Environment label."
  type        = string
  default     = "production"
}

variable "root_domain" {
  description = "Apex domain managed in Cloudflare."
  type        = string
  default     = "grounded-iq.com"
}

variable "frontend_subdomain" {
  description = "Hostname that serves the React app. The S3 frontend bucket is named EXACTLY this (apex; Cloudflare CNAME-flattening covers the apex CNAME)."
  type        = string
  default     = "grounded-iq.com"
}

variable "api_subdomain" {
  description = "Subdomain that points at the EC2 backend."
  type        = string
  default     = "api.grounded-iq.com"
}

variable "dev_ip_cidr" {
  description = "Your home/office IP in CIDR form (e.g. 1.2.3.4/32) for the debug ingress rule. SSM Session Manager works without it; drop to lock origin to Cloudflare only."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository for the OIDC trust policy, in the form <owner>/<repo>."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for the backend. Bump to t3.large when traffic grows."
  type        = string
  default     = "t3.medium"
}

variable "db_username" {
  description = "Postgres master username."
  type        = string
  default     = "groundediq"
}

variable "db_password" {
  description = "Postgres master password. Generate fresh for prod with `openssl rand -hex 32` (do NOT use base64 — RDS forbids slash, at-sign, quote and space, and base64 emits '/') — never reuse staging. Pass via terraform.tfvars (gitignored)."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class. db.t4g.small gives prod a bit more headroom than staging's micro."
  type        = string
  default     = "db.t4g.small"
}

variable "db_multi_az" {
  description = "RDS Multi-AZ standby for HA failover. false at launch (0 users) to halve cost; flip to true once real customers depend on uptime."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Block accidental `terraform destroy` of the production DB. Keep true."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Automated backup retention window (point-in-time restore)."
  type        = number
  default     = 14
}

variable "log_retention_days" {
  description = "CloudWatch log retention for prod."
  type        = number
  default     = 30
}

variable "alarm_email" {
  description = "Email that receives CloudWatch alarm notifications (EC2 down, RDS storage/CPU). Confirm the SNS subscription from your inbox after first apply."
  type        = string
}
