# SSM Parameter Store — every secret the app reads at boot. Terraform creates
# them with placeholder values; you fill them via the console or:
#
#   aws ssm put-parameter --name "/groundediq/staging/OPENAI_CHATGPT" \
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

    # --- Social login: GitHub + Microsoft ("Sign in with ...") ---
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "GITHUB_REDIRECT_URI",
    "MICROSOFT_CLIENT_ID",
    "MICROSOFT_CLIENT_SECRET",
    "MICROSOFT_REDIRECT_URI",
    "MICROSOFT_TENANT", # "common" (personal+work) | "organizations" | a tenant GUID

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
    # pro stays contact-sales → STRIPE_PRO_PRICE_ID is intentionally NOT here
    # (a value would make pro self-serve). Credit packs are one-time top-ups.
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_BASIC_PRICE_ID",
    "STRIPE_PLUS_PRICE_ID",
    "STRIPE_CREDIT_PACK_10_PRICE_ID",
    "STRIPE_CREDIT_PACK_25_PRICE_ID",
    "STRIPE_CREDIT_PACK_50_PRICE_ID",
    "STRIPE_CREDIT_PACK_100_PRICE_ID",
    "ADMIN_SECRET_KEY",

    # --- Transactional email (Resend) — verification + password reset ---
    # REPLACE_ME here means emails are SENT with a bad key (401). If you are NOT
    # launching email yet, delete these two so the code logs links instead.
    "RESEND_API_KEY",
    "EMAIL_FROM", # e.g. "GroundedIQ <noreply@grounded-iq.com>"

    # --- Anti-bot at signup (Cloudflare Turnstile) ---
    # REPLACE_ME here BLOCKS every signup (bad secret fails siteverify). Fill it
    # or delete this line — never leave it as the placeholder. The frontend needs
    # the matching VITE_TURNSTILE_SITE_KEY (a GitHub Environment variable).
    "TURNSTILE_SECRET_KEY",

    # --- Web research (Tavily) — research-as-spine + known-issues grounding ---
    # Fails safe (empty) if absent, but REPLACE_ME calls Tavily with a bad key.
    "TAVILY_API_KEY",

    # --- Frontend wiring ---
    "FRONTEND_URL",
    # The API's own public origin (no trailing path), used for server-rendered
    # email links. MUST be the api subdomain — defaults to localhost otherwise.
    "BACKEND_URL", # e.g. https://api-staging.grounded-iq.com
    "CORS_ORIGINS",
    "COOKIE_DOMAIN",
    "COOKIE_SECURE",

    # --- Runtime feature flags (set the VALUE to "true", not REPLACE_ME) ---
    # These default to false in config.py and gate the SHIPPED product:
    #   USE_CONTRACT_PIPELINE → the 4-stage plan/decide/write/judge pipeline
    #   USE_STREAMING_CHAT    → /chat-with-doc-stream (frontend ships VITE_USE_STREAMING=true)
    # Set both to "true" so the deployed app runs the new pipeline/chat.
    "USE_CONTRACT_PIPELINE",
    "USE_STREAMING_CHAT",

    # --- Pipeline tuning (optional overrides; defaults live in config.py) ---
    "PIPELINE_TIMEOUT",
    "LLM_CALL_TIMEOUT",
    "LLM_MAX_RETRIES",
  ]
}

resource "aws_ssm_parameter" "staging" {
  for_each = toset(local.staging_param_keys)

  name  = "/groundediq/staging/${each.value}"
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
