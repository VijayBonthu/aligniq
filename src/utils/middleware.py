from fastapi import FastAPI, Request, Response, Depends, HTTPException, Header, status
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Callable
from starlette.datastructures import MutableHeaders
import secrets
import os
from utils.logger import logger
from utils.rate_limit import lifespan, rate_limit_key, CustomRateLimiter
from fastapi_limiter import FastAPILimiter
from fastapi.responses import JSONResponse

# Rate-limit budgets per 60s window. Tuned so a normal SPA session
# (status polling every 2s + nav + chat) stays well under the authenticated
# ceiling, while the anonymous bucket stays tight against brute-force.
# Override via env for tenant-specific tuning without redeploying.
TIME_LIMIT = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
AUTH_RATE_LIMIT = int(os.getenv("RATE_LIMIT_AUTHED_PER_MIN", "180"))
ANON_RATE_LIMIT = int(os.getenv("RATE_LIMIT_ANON_PER_MIN", "30"))

# Endpoints that the frontend polls or that are otherwise cheap and
# UI-driven. Excluded from rate limiting because limiting them punishes the
# user for our polling cadence, not for actual abuse. Match by prefix.
RATE_LIMIT_SKIP_PREFIXES = (
    "/api/v1/full-pipeline/status",
    "/health",
    "/metrics",
)
RATE_LIMIT_SKIP_EXACT = {"/"}

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

    # Endpoints that authenticate via their own unguessable bearer secret
    # (refresh_token, oauth state) and therefore don't need CSRF protection.
    CSRF_BYPASS_PATHS = {
        "/api/v1/login",
        "/api/v1/registration",
        "/api/v1/auth/callback",
        "/api/v1/auth/jira/callback",
        "/api/v1/auth/refresh",
    }

    # 30 days — long enough to survive browser restarts for logged-in users.
    CSRF_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

    def _set_csrf_cookie(self, response: Response) -> None:
        response.set_cookie(
            key=self.csrf_token_cookie_name,
            value=secrets.token_hex(32),
            max_age=self.CSRF_COOKIE_MAX_AGE,
            httponly=False,  # Must be accessible from JavaScript
            samesite="lax",
            secure=self.cookie_secure,
            domain=self.cookie_domain,
            path="/",
        )

    @staticmethod
    def _has_bearer_auth(request: Request) -> bool:
        # `Authorization: Bearer <token>` is not auto-attached cross-site by
        # the browser, so a request carrying one cannot be a CSRF forgery —
        # the attacker would need same-origin JS to read the token from
        # localStorage, which the same-origin policy already prevents.
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return len(auth) > len("Bearer ")

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()

        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            path = request.url.path
            # Skip CSRF when the request authenticates via Authorization header
            # (Bearer tokens are immune to CSRF) or when the endpoint carries
            # its own unguessable bearer secret (refresh_token / oauth state).
            needs_csrf = (
                path not in self.CSRF_BYPASS_PATHS
                and not self._has_bearer_auth(request)
            )
            if needs_csrf:
                csrf_cookie = request.cookies.get(self.csrf_token_cookie_name)
                csrf_header = request.headers.get(self.csrf_token_header_name)
                valid = (
                    csrf_cookie
                    and csrf_header
                    and secrets.compare_digest(csrf_cookie, csrf_header)
                )
                if not valid:
                    logger.warning(
                        f"CSRF validation failed for {path} - "
                        f"Cookie: {'present' if csrf_cookie else 'missing'}, "
                        f"Header: {'present' if csrf_header else 'missing'}"
                    )
                    # Don't echo cookie/header presence to the client — it
                    # leaks state to an attacker probing the endpoint.
                    raise HTTPException(status_code=403, detail="CSRF token missing or invalid")

        response = await call_next(request)

        # Reseed the CSRF cookie when absent so cookie-authenticated flows
        # (none today, but defense-in-depth for future endpoints) and any
        # client that still wants to double-submit can do so.
        if self.csrf_token_cookie_name not in request.cookies:
            self._set_csrf_cookie(response)

        return response


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
        path = request.url.path

        # Skip preflight, health checks, and frontend-polling endpoints.
        if request.method.upper() == "OPTIONS":
            return await call_next(request)
        if path in RATE_LIMIT_SKIP_EXACT or path.startswith(RATE_LIMIT_SKIP_PREFIXES):
            return await call_next(request)

        try:
            redis = await FastAPILimiter.redis
            key = await rate_limit_key(request)
            full_key = f"{FastAPILimiter.prefix}{key}"

            # Authenticated keys (ip_<x>_user_<y>) get the higher ceiling;
            # anonymous keys (ip_<x>_ua<z>) get the tighter brute-force budget.
            limit = AUTH_RATE_LIMIT if key.startswith("ip_") and "_user_" in key else ANON_RATE_LIMIT

            current = await redis.incr(full_key)
            if current == 1:
                await redis.expire(full_key, TIME_LIMIT)

            if current > limit:
                logger.warning(f"Rate limit exceeded for {key} ({current}/{limit} in {TIME_LIMIT}s) on {path}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "rate_limit_exceeded", "message": "Too many requests"},
                    headers={"Retry-After": str(TIME_LIMIT)},
                )

            return await call_next(request)
        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            return await call_next(request)

