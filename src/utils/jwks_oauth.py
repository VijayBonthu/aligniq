import httpx
import time
import asyncio
from config import settings

class AsyncJWKSFetcher:

    def __init__(self,url:str, cache_duration:int = 3600):
        self.url = url
        self.cache_duration = cache_duration
        self._jwks = None
        self._cache_time = 0

    async def get_jwks(self):
        current_time = time.time()

        if self._jwks is None or (current_time - self._cache_time) > self.cache_duration:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url)
                if response.status_code == 200:
                    self._jwks = response.json()
                    self._cache_time = current_time
                else:
                    raise Exception(f"Error fetching JWKS from {self.url}: HTTP {response.status_code}")
        return self._jwks
    
google_fetcher_async = AsyncJWKSFetcher(settings.GOOGLE_JWKS)
jira_fetcher_async = AsyncJWKSFetcher(settings.JIRA_JWKS)

async def get_google_certs_async() -> dict:
    return await google_fetcher_async.get_jwks()

async def get_jira_certs_async() -> dict:
    return await jira_fetcher_async.get_jwks()