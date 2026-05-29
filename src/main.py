import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, Request
import uvicorn
from dotenv import load_dotenv
import models
from models import engine
from fastapi.middleware.cors import CORSMiddleware
from routers import authentication, services, third_party_integrations, billing, firm_admin
from utils.logger import setup_logger
from utils.rate_limit import lifespan as rate_limit_lifespan
from utils.middleware import CSRFMiddleware, RateLimitMiddleware

# Setup logging once at application startup
logger = setup_logger()

load_dotenv()

models.Base.metadata.create_all(bind=engine)


# Threshold for reaping stuck `running` pipeline_runs after a backend restart.
# Must exceed `PIPELINE_TIMEOUT` so a healthy long-running row on another worker
# is never stolen. 30 min is the safe ceiling for current pipeline durations.
_STUCK_RUN_THRESHOLD_MINUTES = 30
_RESTART_RECOVERY_MSG = (
    "Backend restarted before this run completed — click Retry to resume from last checkpoint."
)


def _reconcile_stuck_pipeline_runs() -> None:
    """Flip pipeline_runs left in 'running' across a backend restart to 'failed'.

    BackgroundTasks die with the worker process, so any row still marked
    `running` after our threshold is orphaned. Idempotent across multi-worker
    startups: the first worker flips eligible rows; subsequent workers find none.
    Healthy mid-flight rows on other workers are protected by the threshold.
    """
    db = models.sessionlocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STUCK_RUN_THRESHOLD_MINUTES)
        stuck = (
            db.query(models.PipelineRun)
            .filter(models.PipelineRun.status == models.PipelineRunStatus.RUNNING)
            .filter(models.PipelineRun.started_at < cutoff)
            .all()
        )
        if not stuck:
            return
        now = datetime.now(timezone.utc)
        for run in stuck:
            run.status = models.PipelineRunStatus.FAILED
            run.error = _RESTART_RECOVERY_MSG
            run.completed_at = now
        db.commit()
        logger.info(f"Reconciled {len(stuck)} stuck pipeline run(s) on startup")
    except Exception as e:
        db.rollback()
        logger.error(f"Pipeline run reconciliation failed: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _reconcile_stuck_pipeline_runs()
    async with rate_limit_lifespan(app):
        yield


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
    "http://192.168.2.26:3001",
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
app.include_router(firm_admin.router, prefix="/api/v1", tags=["firm"])

@app.get("/")
async def home():
    return "Welcome to Oauth testing login page"


@app.get("/health")
async def health():
    """Liveness probe — Cloudflare and CloudWatch poll this. No auth, no rate-limit."""
    return {"ok": True}
    
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level='info', reload=True, reload_excludes=["*.log"])