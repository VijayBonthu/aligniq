from fastapi import FastAPI, Request, Response, Depends, HTTPException, Header, status
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Callable
from starlette.datastructures import MutableHeaders
import secrets
from utils.logger import logger
from utils.rate_limit import lifespan, rate_limit_key, CustomRateLimiter
from fastapi_limiter import FastAPILimiter
from fastapi.responses import JSONResponse

MESSAGE_LIMIT = 30
TIME_LIMIT = 60 #seconds

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
                    path="/"
                )
                logger.info(f"New CSRF token generated for request to {request.url.path}")
            
            return response
        
        # For state-changing methods, validate CSRF token
        elif request.method.upper() in ["POST", "PUT", "DELETE", "PATCH"]:
            # Get CSRF token from cookie and header
            csrf_cookie = request.cookies.get(self.csrf_token_cookie_name)
            csrf_header = request.headers.get(self.csrf_token_header_name)
            
            # Skip validation for authentication endpoints (login, registration)
            if request.url.path in ["/api/v1/login", "/api/v1/registration", "/api/v1/auth/callback", "/api/v1/auth/jira/callback"]:
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
        # Skip rate limiting for preflight requests and health checks
        if request.method.upper() == "OPTIONS" or request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        logger.info(f"request in ratelimitmiddleware: {request.headers}")
        
        try:
            redis = await FastAPILimiter.redis
            key = await rate_limit_key(request)
            full_key = f"{FastAPILimiter.prefix}{key}"
            
            # Atomic increment and check
            current = await redis.incr(full_key)
            if current == 1:
                await redis.expire(full_key, TIME_LIMIT)  # Set expiry only once in seconds
            
            # Configured rate limit (e.g., 100 requests/minute)
            limit = MESSAGE_LIMIT
            if current > limit:
                logger.warning(f"Rate limit exceeded for {key}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "rate_limit_exceeded", "message": "Too many requests"},
                    headers={"Retry-After": "60"}
                )
            
            return await call_next(request)
        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            return await call_next(request)

