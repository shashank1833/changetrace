from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from .config import get_settings

logger = logging.getLogger("changetrace.ratelimit")


class DistributedRateLimiter:
    """Sliding-window distributed rate limiter using Redis with local memory fallback."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.settings = get_settings()
        self.redis_url = redis_url or self.settings.redis_url
        self._redis_client: Any | None = None
        self._redis_failed = False
        # Local fallback state
        self._local_windows: dict[str, deque[float]] = defaultdict(deque)
        self._local_lock = Lock()

    def _get_redis(self) -> Any | None:
        if self._redis_failed or not self.redis_url:
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            import redis
            client = redis.Redis.from_url(self.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
            client.ping()
            self._redis_client = client
            return self._redis_client
        except Exception as exc:
            logger.debug("Redis rate limiter unavailable (%s); using local in-memory limiter", exc)
            self._redis_failed = True
            return None

    def is_allowed(self, client_key: str, limit: int | None = None, window_seconds: int = 60) -> bool:
        max_requests = limit if limit is not None else self.settings.rate_limit_per_minute
        r = self._get_redis()
        now = time.time()

        if r is not None:
            try:
                key = f"changetrace:ratelimit:{client_key}"
                clear_before = now - window_seconds
                member = f"{now}:{uuid.uuid4().hex[:8]}"

                pipe = r.pipeline()
                pipe.zremrangebyscore(key, 0, clear_before)
                pipe.zcard(key)
                pipe.zadd(key, {member: now})
                pipe.expire(key, window_seconds + 10)
                results = pipe.execute()

                current_count = results[1]
                if current_count >= max_requests:
                    r.zrem(key, member)
                    return False
                return True
            except Exception as exc:
                logger.warning("Redis rate limit operation failed (%s); falling back to local memory", exc)

        # Fallback: thread-safe in-memory sliding window
        monotonic_now = time.monotonic()
        with self._local_lock:
            window = self._local_windows[client_key]
            while window and window[0] < monotonic_now - window_seconds:
                window.popleft()
            if len(window) >= max_requests:
                return False
            window.append(monotonic_now)
            return True

    def reset(self) -> None:
        with self._local_lock:
            self._local_windows.clear()
        r = self._get_redis()
        if r is not None:
            try:
                keys = list(r.scan_iter("changetrace:ratelimit:*"))
                if keys:
                    r.delete(*keys)
            except Exception:
                pass


_limiter_instance: DistributedRateLimiter | None = None


def get_rate_limiter() -> DistributedRateLimiter:
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = DistributedRateLimiter()
    return _limiter_instance
