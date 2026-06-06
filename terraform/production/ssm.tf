# SSM Parameter Store — every secret the app reads at boot, under
# /groundediq/production/*. Terraform creates them with placeholder values; you set
# the real values out-of-band (console or CLI) and Terraform never clobbers them
# (lifecycle.ignore_changes = [value]).
#
#   aws ssm put-parameter --name "/groundediq/production/STRIPE_SECRET_KEY" \
#     --value "sk_live_..." --type SecureString --overwrite
#
# Non-secret runtime config (LOG_LEVEL, AUTO_CREATE_TABLES) is set directly in the
# docker-compose environment in ec2.tf, not here.
#
# PROD-SPECIFIC reminders (see PRODUCTION_RUNBOOK.md):
#   - STRIPE_* must be LIVE keys + live-mode price IDs + the live webhook secret.
#   - GOOGLE_/JIRA_ OAuth: register prod redirect URIs (api.grounded-iq.com).
#   - FRONTEND_URL=https://grounded-iq.com, CORS_ORIGINS=https://grounded-iq.com,
#     COOKIE_DOMAIN=.grounded-iq.com, COOKIE_SECURE=true.
#   - SECRET_KEY_J / ADMIN_SECRET_KEY / POSTGRES_PASSWORD: fresh, never reuse staging.

locals {
  production_param_keys = [
    # --- Postgres (host from RDS output; paste after first apply) ---
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
    "JIRA_TOKEN_ENC_KEY", # Fernet key for Jira tokens at rest (else derived from SECRET_KEY_J)

    # --- LLM / vector ---
    "OPENAI_CHATGPT",
    "GENERATING_REPORT_MODEL",
    "EMBEDDING_MODEL",
    "SUMMARIZATION_MODEL",
    "FALL_BACK_MODEL",
    "CHROMA_API_KEY",
    "CHROMA_TENANT",
    "CHROMA_DATABASE", # use a SEPARATE prod database/tenant from staging

    # --- Storage (S3 bucket name from s3.tf output) ---
    "S3_BUCKET_NAME",
    "AWS_S3_REGION",
    "FILE_SIZE",

    # --- Stripe (LIVE keys + live-mode price IDs at prod cutover) ---
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

resource "aws_ssm_parameter" "production" {
  for_each = toset(local.production_param_keys)

  name  = "/groundediq/production/${each.value}"
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
