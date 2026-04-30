"""
Token-bucket rate limiter for REST (300/min) and WebSocket (120/min).
Non-blocking async — never stalls the event loop.
"""
import asyncio
import time


class RateLimiter:
    """Async token-bucket rate limiter."""

    def __init__(self, max_tokens: int, refill_period: float = 60.0):
        self.max_tokens = max_tokens
        self.refill_period = refill_period
        self.tokens = float(max_tokens)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        added = elapsed * (self.max_tokens / self.refill_period)
        self.tokens = min(self.max_tokens, self.tokens + added)
        self.last_refill = now

    async def acquire(self, tokens: int = 1):
        """Wait until tokens are available. Non-blocking via asyncio.sleep."""
        async with self._lock:
            while True:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                # Calculate wait time until enough tokens are available
                deficit = tokens - self.tokens
                wait = deficit * (self.refill_period / self.max_tokens)
                await asyncio.sleep(wait)


# Pre-configured limiters
rest_limiter = RateLimiter(max_tokens=280, refill_period=60.0)   # 280 to stay under 300
ws_limiter = RateLimiter(max_tokens=100, refill_period=60.0)     # 100 to stay under 120
