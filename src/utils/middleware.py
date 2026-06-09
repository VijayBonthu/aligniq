from fastapi import FastAPI, Request, Response, Depends, HTTPException, Header, status
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Callable
from starlette.datastructures import MutableHeaders
import secrets
import os
from utils.logger import logger
from utils.rate_limit import lifespan, rate_limit_key, get_client_ip, CustomRateLimiter
from fastapi_limiter import FastAPILimiter
from fastapi.responses import JSONResponse
from config import settings

# ---------------------------------------------------------------------------
# Rate-limit route classification
# ---------------------------------------------------------------------------
# Requests are sorted into buckets, each with its own ceiling (see config.py).
# A global per-IP backstop is checked on every request regardless of bucket.

# Auth endpoints — keyed per IP (no user yet), tight to blunt credential stuffing.
AUTH_PATHS = {
    "/api/v1/login",
    "/api/v1/registration",
    "/api/v1/auth/refresh",
    "/api/v1/auth/callback",
    "/api/v1/auth/jira/callback",
    "/api/v1/auth/github/login",
    "/api/v1/auth/github/callback",
    "/api/v1/auth/microsoft/login",
    "/api/v1/auth/microsoft/callback",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/resend-verification",
}

# Expensive: anything that triggers the LLM pipeline, document upload, or report
# generation. Matched by substring so path params don't matter.
_EXPENSIVE_SUBSTRINGS = (
    "/upload",
    "/generate-presales-report",
    "/presales-report",
    "/full-pipeline/start",
    "/full-pipeline/resume",
    "/chat-with-doc",            # covers -v3 and -stream variants too
)


def _is_expensive(path: str) -> bool:
    if any(s in path for s in _EXPENSIVE_SUBSTRINGS):
        return True
    # Presales sub-actions that hit the LLM (NOT the plain /chat DB-save endpoint).
    if "/presales/" in path and (path.endswith("/chat") or path.endswith("/analyze")):
        return True
    # Pre-mortem panel turns and deliverable polish are LLM-driven.
    if "/pre-mortem/" in path and (path.endswith("/turn") or path.endswith("/panelist")):
        return True
    if path.endswith("/polish"):
        return True
    return False


def _classify(method: str, path: str):
    """Return (bucket_name, limit, per_ip). per_ip=True keys by IP, else by identity."""
    if path in AUTH_PATHS:
        return "auth", settings.RATE_LIMIT_AUTH, True
    if method in ("POST", "PUT", "PATCH") and _is_expensive(path):
        return "expensive", settings.RATE_LIMIT_EXPENSIVE, False
    if method == "GET":
        return "read", settings.RATE_LIMIT_READ, False
    return "default", settings.RATE_LIMIT_DEFAULT, False

class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        csrf_token_cookie_name: str = "csrf_token",
        csrf_token_header_name: str = "X-CSRF-Token"
    ):
        super().__init__(app)
        self.csrf_token_cookie_name = csrf_token_cookie_name
        self.csrf_token_header_name = csrf_token_header_name
        # Cross-subdomain config: in staging/prod, frontend at staging.<domain>
        # must be able to read the cookie set by api.staging.<domain>.
        self.cookie_domain = os.getenv("COOKIE_DOMAIN") or None
        self.cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"

    async def dispatch(self, request: Request, call_next):
        # For GET requests and other "safe" methods, ensure a CSRF token exists
        if request.method.upper() in ["GET", "HEAD", "OPTIONS"]:
            response = await call_next(request)

            # Generate and set a CSRF token if not already present
            if self.csrf_token_cookie_name not in request.cookies:
                csrf_token = secrets.token_hex(32)
                response.set_cookie(
                    key=self.csrf_token_cookie_name,
                    value=csrf_token,
                    httponly=False,  # Must be accessible from JavaScript
                    samesite="lax",
                    secure=self.cookie_secure,
                    domain=self.cookie_domain,
                    path="/",
                    max_age=60 * 60 * 24 * 30,
                )
                logger.debug(f"New CSRF token generated for request to {request.url.path}")

            return response
        
        # For state-changing methods, validate CSRF token
        elif request.method.upper() in ["POST", "PUT", "DELETE", "PATCH"]:
            # Get CSRF token from cookie and header
            csrf_cookie = request.cookies.get(self.csrf_token_cookie_name)
            csrf_header = request.headers.get(self.csrf_token_header_name)
            
            # Skip validation for authentication endpoints (login, registration).
            # Forgot/reset are unauthenticated POSTs from users who may not hold a
            # CSRF cookie yet; the reset token in the URL is the unforgeable secret.
            # The Stripe webhook is a server-to-server POST with no browser/cookie —
            # it is authenticated by its Stripe-Signature HMAC (verified in billing.py),
            # so CSRF does not apply (and must be skipped, or it 403s → 500 in middleware).
            if request.url.path in ["/api/v1/login", "/api/v1/registration", "/api/v1/auth/callback", "/api/v1/auth/jira/callback", "/api/v1/auth/github/callback", "/api/v1/auth/microsoft/callback", "/api/v1/auth/refresh", "/api/v1/auth/forgot-password", "/api/v1/auth/reset-password", "/api/v1/auth/verify-email", "/api/v1/webhooks/stripe"]:
                return await call_next(request)
            
            # Validate CSRF token
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                logger.warning(f"CSRF validation failed for {request.url.path} - Cookie: {csrf_cookie}, Header: {csrf_header}")
                raise HTTPException(
                    status_code=403, 
                    detail=f"CSRF token missing or invalid. Cookie: {csrf_cookie and 'present' or 'missing'}, Header: {csrf_header and 'present' or 'missing'}"
                )
            
            return await call_next(request)
        
        # For other methods, just pass through
        return await call_next(request)


# Helper function to get CSRF token from request (for use in dependencies if needed)
def get_csrf_token(
    csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token")
) -> str:
    if not csrf_token:
        raise HTTPException(
            status_code=403,
            detail="CSRF token is missing"
        )
    return csrf_token


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        # Skip preflight + infra probes (never rate-limited).
        if method == "OPTIONS" or path in ["/health", "/metrics", "/"]:
            return await call_next(request)

        # Instant kill switch.
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        try:
            redis = await FastAPILimiter.redis
            window = settings.RATE_LIMIT_WINDOW_SECONDS
            global_limit = settings.RATE_LIMIT_GLOBAL_IP

            bucket, bucket_limit, per_ip = _classify(method, path)
            client_ip = await get_client_ip(request)
            # Auth bucket keys per IP (pre-login); everything else per user (falls
            # back to IP+UA when there's no valid token) via the shared keyer.
            identity = client_ip if per_ip else await rate_limit_key(request)

            prefix = FastAPILimiter.prefix or "fastapi-limiter:"
            bucket_key = f"{prefix}rl:{bucket}:{identity}"
            ip_key = f"{prefix}rl:global:{client_ip}"

            # One atomic MULTI/EXEC: increment both counters and guarantee a TTL
            # is set exactly once (EXPIRE ... NX) — never leaves a key without an
            # expiry, which would lock an identity out permanently.
            pipe = redis.pipeline()
            pipe.incr(bucket_key)
            pipe.expire(bucket_key, window, nx=True)
            pipe.incr(ip_key)
            pipe.expire(ip_key, window, nx=True)
            res = await pipe.execute()
            bucket_count, ip_count = res[0], res[2]

            bucket_exceeded = bucket_count > bucket_limit
            ip_exceeded = ip_count > global_limit
            if bucket_exceeded or ip_exceeded:
                scope = bucket if bucket_exceeded else "global-ip"
                effective_limit = bucket_limit if bucket_exceeded else global_limit
                logger.warning(
                    f"Rate limit exceeded [{scope}] path={path} ip={client_ip} "
                    f"bucket={bucket_count}/{bucket_limit} global={ip_count}/{global_limit}"
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "rate_limit_exceeded", "message": "Too many requests"},
                    headers={
                        "Retry-After": str(window),
                        "X-RateLimit-Limit": str(effective_limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            return await call_next(request)
        except Exception as e:
            # Fail open: a Redis hiccup must not take down the app. Cloudflare
            # remains the outer guard.
            logger.error(f"Rate limit error: {e}")
            return await call_next(request)

