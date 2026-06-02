"""Простой in-process rate limiter (token-bucket per key).

Для прототипа / single-process деплоя. В мульти-инстанс / проде заменить
на Redis-бэкенд (`limits[aiohttp]`/slowapi + Redis).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    """Скользящее окно: не более `max_calls` за `window_sec` секунд на `key`."""

    def __init__(self, max_calls: int, window_sec: int) -> None:
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Вернёт (allowed, retry_after_sec).

        `retry_after_sec` > 0 если запрос отклонён.
        """
        now = time.monotonic()
        cutoff = now - self.window_sec
        with self._lock:
            bucket = self._buckets[key]
            # выкидываем просроченные
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_calls:
                # ближайшая разблокировка = время, когда самый старый вызов "протухнет"
                retry_after = max(1, int(self.window_sec - (now - bucket[0])) + 1)
                return False, retry_after
            bucket.append(now)
            return True, 0


# Глобальный лимитер на логин: 5 попыток в минуту на IP.
login_limiter = RateLimiter(max_calls=5, window_sec=60)
