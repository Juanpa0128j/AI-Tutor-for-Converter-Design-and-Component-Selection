"""Base adapter with rate limiting for catalog APIs."""

from __future__ import annotations

import asyncio
import time
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter for API calls."""
    
    def __init__(self, max_requests: int, period_seconds: int):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed in the period
            period_seconds: Time period in seconds
        """
        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self.tokens = max_requests
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            await self._refill_tokens()
            
            while self.tokens < 1:
                await asyncio.sleep(0.1)
                await self._refill_tokens()
            
            self.tokens -= 1
    
    async def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        
        # Add tokens based on elapsed time
        new_tokens = elapsed * (self.max_requests / self.period_seconds)
        self.tokens = min(self.max_requests, self.tokens + new_tokens)
        self.last_update = now


class BaseCatalogAdapter:
    """Base class for catalog adapters with common functionality."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_requests: int = 100,
        rate_limit_period: int = 60
    ):
        """Initialize adapter with rate limiting."""
        self.api_key = api_key
        self.rate_limiter = RateLimiter(rate_limit_requests, rate_limit_period)
    
    async def _make_request(self) -> None:
        """Make rate-limited request."""
        await self.rate_limiter.acquire()
