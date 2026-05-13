# SSM Parameter Store — every secret the app reads at boot. Terraform creates
# them with placeholder values; you fill them via the console or:
#
#   aws ssm put-parameter --name "/aligniq/staging/OPENAI_CHATGPT" \
#     --value "sk-..." --type SecureString --overwrite
#
# `lifecycle.ignore_changes = [value]` means Terraform won't clobber what you
# set out-of-band. The KEY exists so the IAM policy resource path is valid; the
# VALUE is yours to manage.

locals {
  # Group by purpose so it's obvious which group each secret belongs to.
  staging_param_keys = [
    # --- Postgres (host comes from RDS output; you paste it after first apply) ---
    "POSTGRES_HOSTNAME",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",

    # --- Auth / JWT ---
    "SECRET_KEY_J",
    "ALGORITHM",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "TOKEN_EXPIRED_TIME_IN_DAYS",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "REDIRECT_URL",
    "GOOGLE_JWKS_URL",
    "JIRA_CLIENT_ID",
    "JIRA_CLIENT_SECRET",
    "JIRA_REDIRECT_URI",
    "JIRA_JWKS_URL",

    # --- LLM / vector ---
    "OPENAI_CHATGPT",
    "GENERATING_REPORT_MODEL",
    "EMBEDDING_MODEL",
    "SUMMARIZATION_MODEL",
    "FALL_BACK_MODEL",
    "CHROMA_API_KEY",
    "CHROMA_TENANT",
    "CHROMA_DATABASE",

    # --- Storage (S3 bucket name comes from s3.tf output) ---
    "S3_BUCKET_NAME",
    "AWS_S3_REGION",
    "FILE_SIZE",

    # --- Stripe (sandbox keys/price IDs until prod cutover) ---
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_BASIC_PRICE_ID",
    "STRIPE_PLUS_PRICE_ID",
    "ADMIN_SECRET_KEY",

    # --- Frontend wiring ---
    "FRONTEND_URL",
    "CORS_ORIGINS",
    "COOKIE_DOMAIN",
    "COOKIE_SECURE",

    # --- Pipeline tuning (optional overrides; defaults live in config.py) ---
    "PIPELINE_TIMEOUT",
    "LLM_CALL_TIMEOUT",
    "LLM_MAX_RETRIES",
  ]
}

resource "aws_ssm_parameter" "staging" {
  for_each = toset(local.staging_param_keys)

  name  = "/aligniq/staging/${each.value}"
  type  = "SecureString"
  value = "REPLACE_ME"

  tags = {
    Name        = each.value
    Environment = var.environment
  }

  lifecycle {
    ignore_changes = [value]
  }
}
