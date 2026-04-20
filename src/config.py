import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
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


settings = Settings()