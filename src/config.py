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
    ACCESS_TOKEN_EXPIRE_MINUTES=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1"))
    REFRESH_TOKEN_EXPIRE_DAYS=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "2"))
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
    ADMIN_SECRET_KEY       = os.getenv("ADMIN_SECRET_KEY")
    FRONTEND_URL           = os.getenv("FRONTEND_URL", "http://localhost:5173")

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


settings = Settings()