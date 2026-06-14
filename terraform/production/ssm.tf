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
    # JIRA_TOKEN_ENC_KEY is intentionally NOT created here. utils/crypto.py does
    # `Fernet(key)` at import when it's set, so a REPLACE_ME value (not a valid
    # 32-byte urlsafe-base64 Fernet key) CRASH-LOOPS the app on boot. Leave it
    # UNSET to derive a stable key from SECRET_KEY_J (encryption is always on).
    # To rotate it independently, create the param out-of-band with a real key:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

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
    "CHROMA_DATABASE", # use a SEPARATE prod database/tenant from staging

    # --- Storage (S3 bucket name from s3.tf output) ---
    "S3_BUCKET_NAME",
    "AWS_S3_REGION",
    "FILE_SIZE",

    # --- Stripe (LIVE keys + live-mode price IDs at prod cutover) ---
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
    "BACKEND_URL", # e.g. https://api.grounded-iq.com
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
