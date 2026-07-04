import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_CLIENT_TOKEN =  os.getenv("GOOGLE_CLIENT_TOKEN")
    REDIRECT_URL = os.getenv("REDIRECT_URL")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB = os.getenv("POSTGRES_DB")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT")
    POSTGRES_HOSTNAME = os.getenv("POSTGRES_HOSTNAME")
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOSTNAME}:{POSTGRES_PORT}/{POSTGRES_DB}"
    ALGORITHM=os.getenv("ALGORITHM")
    SECRET_KEY_J=os.getenv("SECRET_KEY_J")
    TOKEN_EXPIRED_TIME_IN_DAYS=os.getenv("TOKEN_EXPIRED_TIME_IN_DAYS")
    # Access token is short-lived and kept in browser memory (Authorization header);
    # the refresh token (httpOnly cookie) silently re-mints it. 30 min balances
    # security vs. refresh chattiness. Refresh token is long so sessions persist.
    ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    FILE_SIZE = os.getenv("FILE_SIZE")
    OPENAI_CHATGPT = os.getenv("OPENAI_CHATGPT")
    IMAGE_TEXT_LANGUAGE=['en']
    JIRA_CLIENT_ID = os.getenv("JIRA_CLIENT_ID")
    JIRA_CLIENT_SECRET = os.getenv("JIRA_CLIENT_SECRET")
    JIRA_REDIRECT_URI=os.getenv("JIRA_REDIRECT_URI")
    # Optional dedicated Fernet key for encrypting stored Jira tokens at rest. If unset,
    # utils/crypto derives a stable key from SECRET_KEY_J (encryption is always on).
    JIRA_TOKEN_ENC_KEY=os.getenv("JIRA_TOKEN_ENC_KEY")
    GOOGLE_JWKS = os.getenv("GOOGLE_JWKS_URL")
    JIRA_JWKS = os.getenv("JIRA_JWKS_URL")

    # GitHub OAuth ("Sign in with GitHub"). Create an OAuth App at
    # github.com/settings/developers; the registered callback must equal GITHUB_REDIRECT_URI.
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")

    # Microsoft OAuth ("Sign in with Microsoft" via the Microsoft identity platform /
    # Entra ID). Register an app at entra.microsoft.com → App registrations. TENANT:
    # "common" = personal + any work/school account (broadest); "organizations" =
    # work/school only; a tenant GUID = a single company (enterprise SSO entry point).
    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
    MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI")
    MICROSOFT_TENANT = os.getenv("MICROSOFT_TENANT", "common")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = os.getenv("REDIS_PORT")
    # REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    REDIS_SSL = os.getenv("REDIS_SSL")

    # Rate limiting (Redis-backed, per identity per window unless noted).
    # Limits are requests-per-window; tune via .env without code changes.
    RATE_LIMIT_ENABLED        = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    RATE_LIMIT_READ           = int(os.getenv("RATE_LIMIT_READ", "240"))      # GET / polling — generous (2s poll = 30/min; 8x headroom)
    RATE_LIMIT_DEFAULT        = int(os.getenv("RATE_LIMIT_DEFAULT", "90"))    # other mutations (save answers, etc.)
    RATE_LIMIT_EXPENSIVE      = int(os.getenv("RATE_LIMIT_EXPENSIVE", "20"))  # LLM / pipeline / upload / report-gen — slow anyway
    RATE_LIMIT_AUTH           = int(os.getenv("RATE_LIMIT_AUTH", "20"))       # login/register/refresh/callback — per IP, anti brute-force
    RATE_LIMIT_PUBLIC         = int(os.getenv("RATE_LIMIT_PUBLIC", "50"))     # public client questionnaire — per IP; higher (autosave) but capped per-token + LLM lifetime cap elsewhere
    RATE_LIMIT_GLOBAL_IP      = int(os.getenv("RATE_LIMIT_GLOBAL_IP", "600")) # per real client IP across ALL routes — DDoS backstop
    CHROMA_API_KEY = os.getenv("CHROMA_API_KEY")
    CHROME_TENANT = os.getenv("CHROMA_TENANT")
    CHROMA_DATABASE = os.getenv("CHROMA_DATABASE")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
    GENERATING_REPORT_MODEL = os.getenv("GENERATING_REPORT_MODEL")
    SUMMARIZATION_MODEL = os.getenv("SUMMARIZATION_MODEL")
    FALL_BACK_MODEL = os.getenv("FALL_BACK_MODEL")
    ANTHROPOIC_KEY = os.getenv("ANTHROPOIC_KEY")

    # Pipeline configuration
    DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
    PIPELINE_TIMEOUT = int(os.getenv("PIPELINE_TIMEOUT", "2000"))  # 10 minutes default
    LLM_CALL_TIMEOUT = int(os.getenv("LLM_CALL_TIMEOUT", "500"))  # 2 minutes per LLM call
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
    LLM_RETRY_MIN_WAIT = int(os.getenv("LLM_RETRY_MIN_WAIT", "1"))  # seconds
    LLM_RETRY_MAX_WAIT = int(os.getenv("LLM_RETRY_MAX_WAIT", "10"))  # seconds

    # Stripe billing
    STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_BASIC_PRICE_ID  = os.getenv("STRIPE_BASIC_PRICE_ID")
    STRIPE_PLUS_PRICE_ID   = os.getenv("STRIPE_PLUS_PRICE_ID")
    # pro is the enterprise CONTACT-SALES tier (SSO, unlimited fair-use) — leave
    # this UNSET so pro stays contact-only (checkout-session rejects it and the UI
    # shows "Contact sales"). Set it only if you ever want pro self-serve. The
    # $70 self-serve tier is now `plus` (STRIPE_PLUS_PRICE_ID must point to $70/mo).
    STRIPE_PRO_PRICE_ID    = os.getenv("STRIPE_PRO_PRICE_ID")
    # Launch discount: id of a Stripe Coupon (percent_off=70, duration=repeating,
    # duration_in_months=2). Auto-applied to a FIRST-TIME subscriber's Checkout so
    # their first 2 invoices are 70% off, then Stripe charges full price. Unset = off.
    # Create the coupon in BOTH test and live mode (ids differ per mode).
    STRIPE_LAUNCH_COUPON_ID = os.getenv("STRIPE_LAUNCH_COUPON_ID")
    # Pin the Stripe API version so request/response shapes are stable. Kept at a
    # version where `current_period_end` still lives on the Subscription object
    # (it moved onto subscription *items* in 2025-03-31+). Webhook payloads use the
    # account/endpoint version, so handlers still read the field defensively.
    STRIPE_API_VERSION     = os.getenv("STRIPE_API_VERSION", "2024-06-20")

    # Credit packs — one-time top-ups (Stripe mode=payment). Each pack grants
    # credits to the user's wallet on checkout.session.completed. Prices live in
    # the Stripe dashboard; the price-id → credit-grant map is built in billing.py
    # from these ids + CREDIT_PACK_GRANTS (falsy/unset ids are skipped).
    STRIPE_CREDIT_PACK_10_PRICE_ID  = os.getenv("STRIPE_CREDIT_PACK_10_PRICE_ID")
    STRIPE_CREDIT_PACK_25_PRICE_ID  = os.getenv("STRIPE_CREDIT_PACK_25_PRICE_ID")
    STRIPE_CREDIT_PACK_50_PRICE_ID  = os.getenv("STRIPE_CREDIT_PACK_50_PRICE_ID")
    STRIPE_CREDIT_PACK_100_PRICE_ID = os.getenv("STRIPE_CREDIT_PACK_100_PRICE_ID")
    # Credits granted per pack ($-size key). Bonus on bigger packs amortizes the
    # $0.30 Stripe fixed fee and lifts average top-up. At 1 credit = $0.10 list
    # value: $10→100 (par), $25→275 (+10%), $50→575 (+15%), $100→1250 (+25%).
    CREDIT_PACK_GRANTS = {"10": 100, "25": 275, "50": 575, "100": 1250}

    # Credit economics. 1 credit = $0.10 of list value; à-la-carte actions cost
    # CREDIT_MULTIPLIER × our measured COGS (see utils/subscription.CREDIT_COSTS).
    # Prepaid → no bill shock, ~75% gross margin. The multiplier is a fair 4×
    # (not a punitive 10×): upgrade pressure comes from model-gating + features,
    # not credit price, so credits can be priced fairly without leaking upgrades.
    CREDIT_VALUE_USD  = float(os.getenv("CREDIT_VALUE_USD", "0.10"))
    CREDIT_MULTIPLIER = float(os.getenv("CREDIT_MULTIPLIER", "4"))

    ADMIN_SECRET_KEY       = os.getenv("ADMIN_SECRET_KEY")
    FRONTEND_URL           = os.getenv("FRONTEND_URL", "http://localhost:5173")
    # The API's own public origin (no trailing path). Used to build email links that hit
    # the backend directly — e.g. the email-verification link is a server-rendered GET so
    # it works even in JS-blocked/sandboxed email previews & link scanners. Set to the api
    # subdomain in prod (e.g. https://api.grounded-iq.com).
    BACKEND_URL            = os.getenv("BACKEND_URL", "http://localhost:8080")

    # Session cookie flags for the httpOnly refresh-token cookie (and the CSRF cookie,
    # which the middleware reads directly). COOKIE_DOMAIN scopes the cookie across
    # sub-domains (e.g. ".grounded-iq.com" so app.* sends it to api.*); leave unset in
    # local dev. SameSite=lax blocks the cross-site POST that CSRF needs while still
    # riding cross-subdomain XHR, so it doubles as CSRF protection for /auth/refresh —
    # valid only while the SPA and API share a registrable domain. COOKIE_SECURE must
    # be true wherever the site is HTTPS (staging/prod); false on http://localhost.
    COOKIE_SECURE          = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    COOKIE_SAMESITE        = os.getenv("COOKIE_SAMESITE", "lax")
    COOKIE_DOMAIN          = os.getenv("COOKIE_DOMAIN") or None

    # Anti-abuse at signup. Cloudflare Turnstile (free bot challenge) — if
    # TURNSTILE_SECRET_KEY is unset, verification is SKIPPED so local dev works without
    # keys (mirrors RESEND fallback). Frontend uses VITE_TURNSTILE_SITE_KEY.
    TURNSTILE_SECRET_KEY        = os.getenv("TURNSTILE_SECRET_KEY", "")
    # Device/IP velocity soft-flag thresholds (signups per identity per 24h). Exceeding
    # these only FLAGS the signup_events row for review — it never blocks (the signal is
    # spoofable). Disposable email + failed captcha are the hard blocks.
    SIGNUP_MAX_PER_DEVICE_PER_DAY = int(os.getenv("SIGNUP_MAX_PER_DEVICE_PER_DAY", "3"))
    SIGNUP_MAX_PER_IP_PER_DAY     = int(os.getenv("SIGNUP_MAX_PER_IP_PER_DAY", "5"))
    # Verification-email resend throttle (per user, Redis-backed, fail-open): a cooldown
    # between sends + an hourly cap, so a user can't spam "resend" and run up email cost.
    VERIFY_RESEND_COOLDOWN_SECONDS = int(os.getenv("VERIFY_RESEND_COOLDOWN_SECONDS", "60"))
    VERIFY_RESEND_HOURLY_CAP       = int(os.getenv("VERIFY_RESEND_HOURLY_CAP", "5"))

    # Public client-questionnaire "Check readiness" throttle — this is the only
    # UNAUTHENTICATED endpoint that triggers an LLM call, so it's the real cost/DDoS
    # surface. Three layers: per-IP (middleware), per-token cooldown + hourly cap
    # (Redis, fail-open), and a durable per-token LIFETIME cap (DB, never fails open).
    PUBLIC_READINESS_COOLDOWN_SECONDS = int(os.getenv("PUBLIC_READINESS_COOLDOWN_SECONDS", "20"))
    PUBLIC_READINESS_HOURLY_CAP       = int(os.getenv("PUBLIC_READINESS_HOURLY_CAP", "10"))
    PUBLIC_READINESS_MAX_CHECKS       = int(os.getenv("PUBLIC_READINESS_MAX_CHECKS", "40"))

    # Transactional email (password reset, etc.) via Resend — a single HTTPS POST,
    # wrapped in utils/email.py so the provider is swappable. If RESEND_API_KEY is
    # unset, utils/email logs the message (including any reset link) at WARNING and
    # does NOT send, so the flow stays testable locally without provisioning email.
    RESEND_API_KEY         = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM             = os.getenv("EMAIL_FROM", "GroundedIQ <noreply@grounded-iq.com>")
    # Inbox that in-app Help & Support requests are emailed to. The notification is
    # sent with reply_to set to the requester, so the team can reply straight from
    # their inbox.
    SUPPORT_INBOX          = os.getenv("SUPPORT_INBOX", "support@grounded-iq.com")
    # Inbox for general/sales enquiries from the public contact form (topic = sales).
    # Support-type topics still route to SUPPORT_INBOX; sales/pricing go here so the
    # right team sees them. Same reply_to-the-requester pattern.
    SALES_INBOX            = os.getenv("SALES_INBOX", "hello@grounded-iq.com")
    # Svix signing secret (whsec_...) for the Resend INBOUND email webhook
    # (/api/v1/webhooks/resend-inbound). When a user replies to a support email, Resend
    # parses it and POSTs an `email.received` event we verify with this secret. Unset →
    # the webhook fails closed (rejects) so it can't be spoofed. Set per environment.
    RESEND_WEBHOOK_SECRET  = os.getenv("RESEND_WEBHOOK_SECRET", "")

    # Schema management. Local dev lets SQLAlchemy create tables from models.
    # Staging/prod set AUTO_CREATE_TABLES=false and rely solely on `alembic upgrade head`.
    AUTO_CREATE_TABLES     = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"

    # Feature flags
    USE_TOOL_BASED_CHAT = os.getenv("USE_TOOL_BASED_CHAT", "false").lower() == "true"
    USE_STREAMING_CHAT = os.getenv("USE_STREAMING_CHAT", "false").lower() == "true"
    STREAMING_TIMEOUT = int(os.getenv("STREAMING_TIMEOUT", "300"))  # 5 minutes default for streaming

    # Bet 2 — first-impression protection
    ENABLE_PREFLIGHT_GATE     = os.getenv("ENABLE_PREFLIGHT_GATE", "false").lower() == "true"
    ENABLE_PARALLEL_BRIEF     = os.getenv("ENABLE_PARALLEL_BRIEF", "false").lower() == "true"
    ENABLE_RESUMABLE_PIPELINE = os.getenv("ENABLE_RESUMABLE_PIPELINE", "false").lower() == "true"

    # Bet 3 — firm context (rate cards, tech preferences, team templates, past-project RAG)
    ENABLE_FIRM_CONTEXT       = os.getenv("ENABLE_FIRM_CONTEXT", "false").lower() == "true"

    # Contract pipeline (plan -> parallel section writers -> judge). Replaces the
    # 8-agent linear pipeline. Off by default; the runner branches on this flag.
    # See design/plans + the_generate_full_pipeline plan for the redesign rationale.
    USE_CONTRACT_PIPELINE     = os.getenv("USE_CONTRACT_PIPELINE", "false").lower() == "true"
    # Smart model for the planner + judge nodes. Defaults to the same model as
    # the writers so the new path is runnable without provisioning a new key;
    # flip SMART_MODEL_NAME to Sonnet 4.6 / GPT-5 once the path is validated.
    SMART_MODEL_PROVIDER      = os.getenv("SMART_MODEL_PROVIDER", "openai")  # openai | anthropic
    SMART_MODEL_NAME          = os.getenv("SMART_MODEL_NAME") or os.getenv("GENERATING_REPORT_MODEL")
    # Cap section-writer revisions to 1 per section. Surfaced as a setting so
    # eval runs can test the loop is genuinely bounded.
    CONTRACT_JUDGE_MAX_REVISIONS_PER_SECTION = int(os.getenv("CONTRACT_JUDGE_MAX_REVISIONS_PER_SECTION", "1"))

    # Slice 2 — Tavily-backed "known issues & integration gotchas". Off by default;
    # the known_issues sub-step is inert without both the flag AND a key, so the
    # report renders normally when either is missing.
    ENABLE_KNOWN_ISSUES        = os.getenv("ENABLE_KNOWN_ISSUES", "false").lower() == "true"
    TAVILY_API_KEY             = os.getenv("TAVILY_API_KEY", "")
    KNOWN_ISSUES_MAX_QUERIES   = int(os.getenv("KNOWN_ISSUES_MAX_QUERIES", "6"))
    KNOWN_ISSUES_RESULTS_PER_QUERY = int(os.getenv("KNOWN_ISSUES_RESULTS_PER_QUERY", "3"))

    # Model-pricing auto-refresh — a daily job Tavily-extracts the official OpenAI
    # pricing page, validates, and updates the model_pricing table. The cost path
    # always reads the TABLE (deterministic, never the web). On fetch/parse failure
    # the existing table/seed rates stay in force and an alert is sent. Reuses
    # TAVILY_API_KEY; inert without it. Off by default — flip on once verified.
    PRICING_PAGE_URL           = os.getenv("PRICING_PAGE_URL", "https://developers.openai.com/api/docs/pricing")
    PRICING_AUTO_REFRESH       = os.getenv("PRICING_AUTO_REFRESH", "false").lower() == "true"
    PRICING_REFRESH_HOURS      = int(os.getenv("PRICING_REFRESH_HOURS", "24"))
    # A known model's rate changing by more than this fraction is NOT auto-applied
    # (likely a parse error) — it is flagged + alerted for human review instead.
    PRICING_CHANGE_FLAG_PCT    = float(os.getenv("PRICING_CHANGE_FLAG_PCT", "0.5"))
    PRICING_ALERT_EMAIL        = os.getenv("PRICING_ALERT_EMAIL", "")

    # Cut 2 — retrieval-as-spine. The planner emits crux-targeted research_queries;
    # the research stage runs them (before decide) so approaches/feasibility are
    # grounded in the current real world, not just the client doc. Reuses the
    # Tavily key. Inert without the key, like known-issues. Default ON so full
    # reports get grounded substance; flip off to fall back to doc-only behavior.
    ENABLE_RESEARCH            = os.getenv("ENABLE_RESEARCH", "true").lower() == "true"
    RESEARCH_MAX_QUERIES       = int(os.getenv("RESEARCH_MAX_QUERIES", "6"))
    RESEARCH_RESULTS_PER_QUERY = int(os.getenv("RESEARCH_RESULTS_PER_QUERY", "3"))
    # Depth Cut — the iterative deep-research agent (frontier tiers only).
    # ROUNDS counts search→reflect cycles including the first fan-out; EXTRACTS
    # caps full-page tavily_extract reads per run (the expensive, high-signal
    # part); EXTRACT_CHARS clips each extracted page before it enters a prompt.
    RESEARCH_MAX_ROUNDS           = int(os.getenv("RESEARCH_MAX_ROUNDS", "3"))
    RESEARCH_MAX_EXTRACTS         = int(os.getenv("RESEARCH_MAX_EXTRACTS", "6"))
    RESEARCH_EXTRACT_CHARS        = int(os.getenv("RESEARCH_EXTRACT_CHARS", "4000"))
    RESEARCH_MAX_FOLLOWUP_QUERIES = int(os.getenv("RESEARCH_MAX_FOLLOWUP_QUERIES", "6"))


settings = Settings()