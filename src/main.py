import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, Request
import uvicorn
from dotenv import load_dotenv
import models
from models import engine
from config import settings
from fastapi.middleware.cors import CORSMiddleware
from routers import authentication, services, third_party_integrations, billing, firm_admin, admin_ops
from utils.logger import setup_logger
from utils.rate_limit import lifespan as rate_limit_lifespan
from utils.middleware import CSRFMiddleware, RateLimitMiddleware, MaintenanceMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from utils.ids import new_id

# Setup logging once at application startup
logger = setup_logger()

load_dotenv()

# Local dev creates tables straight from the models. Staging/prod set
# AUTO_CREATE_TABLES=false and manage schema exclusively via Alembic
# (`alembic upgrade head` runs as a discrete deploy step before this serves traffic),
# so create_all never races a migration or silently diverges from versioned history.
if settings.AUTO_CREATE_TABLES:
    models.Base.metadata.create_all(bind=engine)
else:
    logger.info("AUTO_CREATE_TABLES=false — schema managed by Alembic")


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


async def _pricing_refresh_loop() -> None:
    """Daily-ish refresh of model_pricing from the official OpenAI page.

    Each worker checks staleness first (max updated_at of openai-sourced rows) so
    redundant fetches across workers/restarts are avoided; the update itself is
    idempotent. Re-ticks every <=6h so the cadence survives long-lived processes.
    """
    from utils.pricing_feed import refresh_openai_pricing, pricing_is_stale
    from utils.llm_pricing import load_pricing_from_db
    tick = min(settings.PRICING_REFRESH_HOURS, 6) * 3600
    while True:
        try:
            if pricing_is_stale(settings.PRICING_REFRESH_HOURS):
                await refresh_openai_pricing(apply=True)  # fetch + write + reload this worker
            else:
                # Fresh in the DB already — but another worker (or an external cron)
                # may have written it. Reload this process's in-memory book so every
                # worker converges to the same rates without a restart.
                load_pricing_from_db()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"pricing refresh loop error: {e}")
        await asyncio.sleep(tick)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _reconcile_stuck_pipeline_runs()
    # Load the model price book from DB (seeding it from SEED_PRICES on first run),
    # then surface any configured model still missing — otherwise its cost is
    # silently billed at gpt-4o-mini rates (understated 10-40x).
    try:
        from utils.llm_pricing import load_pricing_from_db, assert_pricing_coverage
        load_pricing_from_db()
        assert_pricing_coverage()
    except Exception as e:
        logger.warning(f"pricing load/coverage check failed: {e}")

    pricing_task = None
    if settings.PRICING_AUTO_REFRESH and settings.TAVILY_API_KEY:
        pricing_task = asyncio.create_task(_pricing_refresh_loop())
        logger.info(f"pricing auto-refresh ON (every {settings.PRICING_REFRESH_HOURS}h from OpenAI page)")

    async with rate_limit_lifespan(app):
        yield
        if pricing_task:
            pricing_task.cancel()


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
    "http://192.168.2.26:3002",
    "https://staging.grounded-iq.com",
]
_env_origins = os.getenv("CORS_ORIGINS", "")
origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _default_local_origins
)
# Middleware order: Starlette wraps last-added on the outside, so request flow is
# CORS -> Maintenance -> CSRF -> RateLimit -> handler. CORS is outermost so rejected
# responses (503 maintenance, 429 rate-limit, 403 CSRF) still carry Access-Control-*
# headers and stay readable by the browser instead of surfacing as opaque CORS/network
# errors. Maintenance runs before CSRF/RateLimit so a maintenance/read-only block
# neither 403s on a missing CSRF token nor consumes rate-limit quota.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(MaintenanceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

app.include_router(authentication.router, prefix="/api/v1", tags=["authentication"])
app.include_router(services.router, prefix="/api/v1", tags=["services"])
app.include_router(third_party_integrations.router, prefix="/api/v1", tags=["third party integrations"])
app.include_router(billing.router, prefix="/api/v1", tags=["billing"])
app.include_router(firm_admin.router, prefix="/api/v1", tags=["firm"])
app.include_router(admin_ops.router, prefix="/api/v1", tags=["ops"])


# ---------------------------------------------------------------------------
# Friendly errors. Users never see stack traces or internal codes; the full
# detail is logged with an incident_id so support can find it by reference.
# 4xx details are author-written for users (e.g. "Incorrect email or password",
# EMAIL_NOT_VERIFIED / NOT_STAFF, rate-limit) so they pass through unchanged.
# ---------------------------------------------------------------------------
_GENERIC_500 = ("Something went wrong on our end. Please try again — if it keeps "
                "happening, contact support with this reference.")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    headers = getattr(exc, "headers", None) or {}
    if exc.status_code >= 500:
        incident_id = new_id()
        logger.error(f"HTTP {exc.status_code} incident={incident_id} "
                     f"{request.method} {request.url.path}: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": "internal_error", "message": _GENERIC_500, "incident_id": incident_id},
            headers=headers,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Keep `detail` for any existing client code that reads it; add a friendly message.
    return JSONResponse(
        status_code=422,
        content={"error": "invalid_request",
                 "message": "Some of the submitted details look invalid. Please check and try again.",
                 "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    incident_id = new_id()
    logger.exception(f"UNHANDLED incident={incident_id} {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": _GENERIC_500, "incident_id": incident_id},
    )


@app.get("/")
async def home():
    return "Welcome to Oauth testing login page"


@app.get("/health")
async def health():
    """Liveness probe — Cloudflare and CloudWatch poll this. No auth, no rate-limit."""
    return {"ok": True}
    
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level='info', reload=True, reload_excludes=["*.log"])