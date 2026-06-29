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
from jose import jwt, JWTError
from config import settings
from utils import ops_state

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
    # Public (unauthenticated) endpoints — the client questionnaire. No identity to
    # key on, so rate-limit per-IP. Its own (higher) bucket so client autosave has
    # headroom without weakening the auth/brute-force limit; the LLM-bearing
    # check-readiness is further capped per-token (Redis + DB lifetime) elsewhere.
    if path.startswith("/api/v1/public/"):
        return "public", settings.RATE_LIMIT_PUBLIC, True
    # Public contact form — unauthenticated and triggers email, so a tight per-IP
    # ceiling (the auth bucket) backstops the Turnstile + honeypot guards on it.
    if path == "/api/v1/contact":
        return "auth", settings.RATE_LIMIT_AUTH, True
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
            # CSRF-exempt: cookieless server-to-server POSTs authenticated by their own
            # secret/signature, where a browser CSRF token can't (and needn't) exist —
            # the Stripe webhook (HMAC), the Resend inbound-email webhook (Svix HMAC,
            # verified in support.py), and the X-Admin-Key break-glass admin endpoints.
            # Public client-questionnaire POSTs come from an anonymous visitor who
            # holds no CSRF cookie; the opaque share token in the URL is the secret.
            # The public contact form is likewise anonymous (no session to forge) and
            # is gated by Turnstile + honeypot + a tight per-IP limit instead.
            if request.url.path in ["/api/v1/login", "/api/v1/registration", "/api/v1/auth/callback", "/api/v1/auth/jira/callback", "/api/v1/auth/github/callback", "/api/v1/auth/microsoft/callback", "/api/v1/auth/refresh", "/api/v1/auth/forgot-password", "/api/v1/auth/reset-password", "/api/v1/auth/verify-email", "/api/v1/webhooks/stripe", "/api/v1/webhooks/resend-inbound", "/api/v1/admin/set-staff", "/api/v1/admin/grant-comp", "/api/v1/contact"] or request.url.path.startswith("/api/v1/public/"):
                return await call_next(request)

            # Validate CSRF token. Return a clean 403 (NOT raise) — an HTTPException
            # raised inside BaseHTTPMiddleware escapes the exception handlers and
            # surfaces as an opaque 500. Mirrors RateLimitMiddleware returning a 429.
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                logger.warning(f"CSRF validation failed for {request.url.path} - Cookie: {csrf_cookie and 'present' or 'missing'}, Header: {csrf_header and 'present' or 'missing'}")
                return JSONResponse(
                    status_code=403,
                    content={"error": "csrf", "message": "Your session security token is missing or expired. Please refresh the page and try again."},
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


# ---------------------------------------------------------------------------
# Maintenance / read-only / feature kill switches
# ---------------------------------------------------------------------------
# Dynamic, no-restart enforcement driven by utils.ops_state (Postgres-backed,
# TTL-cached). Runs just inside CORS (so 503s keep Access-Control headers) and
# before CSRF/RateLimit (so a maintenance block neither 403s nor burns quota).
def _bearer(request: Request):
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


class MaintenanceMiddleware(BaseHTTPMiddleware):
    # Always reachable even in maintenance: infra probes, the public config the SPA
    # polls, the whole admin console (staff manage from there), and the auth endpoints
    # needed to actually sign in as staff and turn maintenance back off.
    _ALWAYS_OK_EXACT = {"/", "/health", "/api/v1/site-config", "/api/v1/my-site-config"}
    _ALWAYS_OK_PREFIX = ("/api/v1/admin/",)
    _AUTH_BYPASS = {
        "/api/v1/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/callback",
        "/api/v1/auth/github/login",
        "/api/v1/auth/github/callback",
        "/api/v1/auth/microsoft/login",
        "/api/v1/auth/microsoft/callback",
    }
    # Identity/session establishment must stay reachable even for a blocked user so the SPA
    # can finish login → identify them → SHOW them the maintenance page, rather than the
    # login silently failing on a 503. (Targeted maintenance: a user is only known to be a
    # target AFTER they authenticate.) `decode_token/{token}` is prefix-matched (path param).
    _AUTH_BYPASS_PREFIX = ("/api/v1/decode_token/",)

    def _auth_bypass(self, path: str) -> bool:
        return path in self._AUTH_BYPASS or any(path.startswith(p) for p in self._AUTH_BYPASS_PREFIX)

    def _claims(self, request: Request) -> dict:
        """Decode the bearer once. Returns the JWT claims (incl. `is_staff`, `email`)
        or {} when there's no/invalid token. Trusting the claim for the bypass is fine:
        it's minted from the DB at login/refresh, and authoritative DB checks live on the
        admin endpoints (require_staff) — a stale claim only affects maintenance bypass."""
        token = _bearer(request)
        if not token:
            return {}
        try:
            return jwt.decode(token, settings.SECRET_KEY_J, algorithms=[settings.ALGORITHM]) or {}
        except JWTError:
            return {}

    async def _ip_allowed(self, request: Request, maint: dict) -> bool:
        allow = maint.get("allowlist_ips") or []
        if not allow:
            return False
        try:
            return (await get_client_ip(request)) in allow
        except Exception:
            return False

    @staticmethod
    def _blocked(status_code: int, error: str, message: str, extra: dict | None = None):
        body = {"error": error, "message": message}
        if extra:
            body.update(extra)
        headers = {"Retry-After": "300"}
        if error == "maintenance":
            headers["X-Maintenance"] = "1"
        return JSONResponse(status_code=status_code, content=body, headers=headers)

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        if method == "OPTIONS" or path in self._ALWAYS_OK_EXACT \
                or any(path.startswith(p) for p in self._ALWAYS_OK_PREFIX):
            return await call_next(request)

        try:
            state = ops_state.get_ops_state()
        except Exception as e:
            # Fail open — a config-read hiccup must never block the whole site.
            logger.error(f"ops_state read failed in middleware: {e}")
            return await call_next(request)

        maint = state.get("maintenance", {})
        read_only = state.get("read_only", {})
        flags = state.get("feature_flags", {})

        # Granular kill switches first (don't require full downtime).
        if path == "/api/v1/registration" and not flags.get("signups_enabled", True):
            return self._blocked(503, "signups_disabled",
                                 "New sign-ups are temporarily paused. Please check back soon.")
        if path == "/api/v1/login" and not flags.get("logins_enabled", True):
            return self._blocked(503, "logins_disabled",
                                 "Sign-in is temporarily unavailable. Please try again shortly.")
        if method in ("POST", "PUT", "PATCH") and not flags.get("pipeline_enabled", True) and _is_expensive(path):
            return self._blocked(503, "pipeline_paused",
                                 "Report generation is paused for maintenance — your projects are safe. Try again soon.")

        # Maintenance — the `on` toggle is the master switch; `target_emails` scopes WHO it
        # applies to: a non-empty list = only those accounts (everyone else, incl. anonymous
        # visitors, use the site normally), empty = the whole site. Token is only decoded
        # while maintenance is on.
        if bool(maint.get("on")):
            target_emails = {str(e).strip().lower() for e in (maint.get("target_emails") or [])}
            claims = self._claims(request)
            is_staff = bool(claims.get("is_staff"))
            email = (claims.get("email") or "").strip().lower()
            in_maint = (email in target_emails) if target_emails else True
            if in_maint:
                if self._auth_bypass(path):
                    return await call_next(request)
                # Staff always bypass; allowlisted IPs bypass site-wide downtime.
                if is_staff or await self._ip_allowed(request, maint):
                    response = await call_next(request)
                    response.headers["X-Maintenance-Bypass"] = "1"
                    return response
                return self._blocked(
                    503, "maintenance",
                    maint.get("message") or "GroundedIQ is down for brief maintenance. We'll be back shortly.",
                    extra={"title": maint.get("title") or "We'll be right back", "eta": maint.get("eta") or ""},
                )

        # Read-only — allow reads, block state changes (except staff / auth).
        if read_only.get("on") and method in ("POST", "PUT", "PATCH", "DELETE"):
            if self._auth_bypass(path) or bool(self._claims(request).get("is_staff")):
                return await call_next(request)
            return self._blocked(
                503, "read_only",
                read_only.get("message") or "We're in read-only mode for brief maintenance — changes are temporarily disabled.",
            )

        return await call_next(request)

