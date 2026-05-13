import os
from fastapi import FastAPI, Depends, Request
import uvicorn
from dotenv import load_dotenv
import models
from models import engine
from fastapi.middleware.cors import CORSMiddleware
from routers import authentication, services, third_party_integrations, billing
from utils.logger import setup_logger
from utils.rate_limit import lifespan
from utils.middleware import CSRFMiddleware, RateLimitMiddleware

# Setup logging once at application startup
logger = setup_logger()

load_dotenv()

models.Base.metadata.create_all(bind=engine)

app = FastAPI(lifespan=lifespan)
# app = FastAPI()

# Origins come from CORS_ORIGINS env var (comma-separated). In staging/prod this
# is set via SSM to the real frontend URL(s). Falls back to local dev defaults.
_default_local_origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5173",
    "https://staging.grounded-iq.com",
]
_env_origins = os.getenv("CORS_ORIGINS", "")
origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _default_local_origins
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Middleware order: Starlette wraps last-added on the outside, so request flow is
# CSRF -> RateLimit -> CORS -> handler. Reject CSRF-invalid requests before they
# consume rate-limit quota.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CSRFMiddleware)

app.include_router(authentication.router, prefix="/api/v1", tags=["authentication"])
app.include_router(services.router, prefix="/api/v1", tags=["services"])
app.include_router(third_party_integrations.router, prefix="/api/v1", tags=["third party integrations"])
app.include_router(billing.router, prefix="/api/v1", tags=["billing"])

@app.get("/")
async def home():
    return "Welcome to Oauth testing login page"


@app.get("/health")
async def health():
    """Liveness probe — Cloudflare and CloudWatch poll this. No auth, no rate-limit."""
    return {"ok": True}
    
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level='info', reload=True, reload_excludes=["*.log"])