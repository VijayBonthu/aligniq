variable "aws_region" {
  description = "AWS region for all staging resources."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used as a prefix on most resources."
  type        = string
  default     = "aligniq"
}

variable "environment" {
  description = "Environment label."
  type        = string
  default     = "staging"
}

variable "root_domain" {
  description = "Apex domain managed in Cloudflare."
  type        = string
  default     = "grounded-iq.com"
}

variable "frontend_subdomain" {
  description = "Subdomain that serves the React app. Cloudflare → S3 static-website endpoint."
  type        = string
  default     = "staging.grounded-iq.com"
}

variable "api_subdomain" {
  description = "Subdomain that points at the EC2 backend. Single-level so Cloudflare Universal SSL wildcard covers it."
  type        = string
  default     = "api-staging.grounded-iq.com"
}

variable "dev_ip_cidr" {
  description = "Your home/office IP in CIDR form (e.g. 1.2.3.4/32). Used to allowlist SSM port-forward egress checks; not strictly required since SSM is sessionless, but documents intent."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository for the OIDC trust policy, in the form <owner>/<repo>."
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type for the backend."
  type        = string
  default     = "t3.medium"
}

variable "db_username" {
  description = "Postgres master username."
  type        = string
  default     = "aligniq"
}

variable "db_password" {
  description = "Postgres master password. Generate with `openssl rand -base64 24` and pass via -var or terraform.tfvars."
  type        = string
  sensitive   = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention. 14 days is plenty for staging."
  type        = number
  default     = 14
}
