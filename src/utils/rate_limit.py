from fastapi import Depends,FastAPI, HTTPException, status, Request, Response
from utils.token_generation import validate_token_incoming_requests
from fastapi_limiter.depends import RateLimiter
from fastapi_limiter import FastAPILimiter
from redis.asyncio import Redis
from contextlib import asynccontextmanager
import os
from config import settings
from ipaddress import ip_address
from utils.logger import logger
from fastapi.responses import JSONResponse


PREMIUM_LIMIT = "100/minute"
FREE_LIMIT = "30/minute"

#this is for ip check
async def get_client_ip(request:Request) -> str:
    """Dynamic Rate limiter based on user tier"""
    headers = request.headers

    #cloud flair client ip extraction
    if "cf-connecting-ip" in headers:
        return headers["cf-connecting-ip"]
    
    #standard proxy client ip extraction
    if "x-forwarded-for" in headers:
        ips = headers["x-forwarded-for"].split(",")
        for ip in ips:
            clean_ip = ip.split(":")[0].strip()
            try:
                if not ip_address(clean_ip).is_private:
                    return clean_ip
            except ValueError:
                continue
    return request.client.host if request.client else "unknown"

    
async def rate_limit_key(request:Request):
    try:
        logger.info(f"request received in rate_limit_key: {request.headers}")
        payload = await validate_token_incoming_requests(request.headers.get('authorization').split(" ")[1])
        logger.info(f"payload received by request in rate_limit_key: {payload}")
        user_id = payload.get('id')
        logger.info(f"user_id frompayload received by request in rate_limit_key: {user_id}")
        if user_id:
            ip = await get_client_ip(request)
            logger.info(f"Rate limiting based on user_id: {user_id}")
            return f"ip_{ip}_user_{user_id}"
    except Exception as e:
        logger.debug(f"No valid token, falling back to IP: {e}")

    ip = await get_client_ip(request)
    ua_hash = request.headers.get('user-agent', '')[:20]
    key = f"ip_{ip}_ua{ua_hash}"
    logger.info(f"Rate limiting with key: {key}")
    return key


async def rate_limit_exceeded_callback(request: Request, response: Response, peerid: str):
    logger.warning(f"Rate limit exceeded for {peerid}")
    return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "rate_limit_exceeded", "message": "Too many requests"},
            headers={"Retry-After": "60"}
        )


class CustomRateLimiter:
    def __init__(self, times: int = 1, seconds: int = 60):
        self.times = times
        self.seconds = seconds
    
    async def __call__(self, request: Request):
        redis = await FastAPILimiter.redis
        key = await rate_limit_key(request)
        full_key = f"{FastAPILimiter.prefix}{key}"
        
        # Get current count
        pipe = redis.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, self.seconds)
        result = await pipe.execute()
        
        current_count = result[0]
        logger.info(f"Custom limiter - Key: {full_key}, Count: {current_count}, Limit: {self.times}")
        
        # If count exceeds limit, raise HTTP exception
        if current_count > self.times:
            logger.warning(f"Rate limit exceeded for {key}, count: {current_count}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, 
                detail={"error": "rate_limit_exceeded", "message": "Too many requests"},
                headers={"Retry-After": str(self.seconds)}
            )
        
        return None

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Loaded with rate limiter")
    # Initialize Redis connection pool
    redis = Redis(
        host=settings.REDIS_HOST,
        port=int(settings.REDIS_PORT),
        # password=settings.REDIS_PASSWORD,
        # ssl=False,
        decode_responses=True
        # max_connections=1000  # Adjust based on load
    )

    # Test Redis connection
    try:
        await redis.ping()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    logger.info("Redis initialized")
    await FastAPILimiter.init(
                            redis,identifier=rate_limit_key,
                            http_callback=rate_limit_exceeded_callback, 
                            prefix="fastapi-limiter:"
                            )
    yield
    await redis.close()
    await FastAPILimiter.close()

