import math
import threading
import time

from flask import g, request

from app.errors import too_many_requests


class RateLimiter:
    """
    Limite por IP em janela fixa, guardado em memória (por processo).
    Equivalente ao express-rate-limit com o store padrão.
    """

    def __init__(self, *, window_seconds, limit, message, clock=time.monotonic):
        self.window_seconds = window_seconds
        self.limit = limit
        self.message = message
        self._clock = clock
        self._hits = {}
        self._lock = threading.Lock()
        self._next_cleanup = clock() + window_seconds

    def _cleanup(self, now):
        expired = [key for key, (_, reset_at) in self._hits.items() if reset_at <= now]
        for key in expired:
            del self._hits[key]
        self._next_cleanup = now + self.window_seconds

    def hit(self, key=None):
        key = key or request.remote_addr or "unknown"
        with self._lock:
            now = self._clock()
            if now >= self._next_cleanup:
                self._cleanup(now)

            count, reset_at = self._hits.get(key, (0, now + self.window_seconds))
            if now >= reset_at:
                count, reset_at = 0, now + self.window_seconds
            count += 1
            self._hits[key] = (count, reset_at)

        reset_in = max(1, math.ceil(reset_at - now))
        window = math.ceil(self.window_seconds)
        policy = f'"{self.limit}-in-{window}sec"'
        # Cabeçalhos no formato draft-8 do IETF (o mesmo do express-rate-limit).
        g.rate_limit_headers = {
            "RateLimit-Policy": f"{policy}; q={self.limit}; w={window}",
            "RateLimit": f"{policy}; r={max(0, self.limit - count)}; t={reset_in}",
        }

        if count > self.limit:
            raise too_many_requests(self.message, reset_in)
