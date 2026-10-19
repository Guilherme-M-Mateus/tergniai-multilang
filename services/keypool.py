"""
Rotation and cooldown for API keys shared by all upstream providers
"""

import time
from collections import defaultdict
from typing import Dict, Iterable, List, Optional


def mask(key: str) -> str:
    """Safe representation of a key for logs"""
    return f"…{key[-4:]}" if len(key) > 8 else "…"


class KeyPool:
    """Round-robin key selection that skips keys that were recently rejected or rate-limited"""

    def __init__(self) -> None:
        self._counters: Dict[str, int] = defaultdict(int)
        self._cooldown_until: Dict[str, float] = {}

    def order(self, scope: str, keys: Iterable[str]) -> List[str]:
        """Return usable keys for `scope`, starting from the next key in the rotation"""
        keys = list(keys)
        if not keys:
            return []
        start = self._counters[scope] % len(keys)
        self._counters[scope] += 1
        now = time.monotonic()
        rotated = keys[start:] + keys[:start]
        return [k for k in rotated if self._cooldown_until.get(k, 0.0) <= now]

    def cool_down(self, key: str, seconds: float) -> None:
        """Skip `key` for the next `seconds`"""
        self._cooldown_until[key] = time.monotonic() + max(seconds, 0.0)

    def reset(self) -> None:
        self._counters.clear()
        self._cooldown_until.clear()


key_pool = KeyPool()


def retry_after_seconds(value: Optional[str], default: float) -> float:
    """Parse a Retry-After header (seconds form), falling back to `default`"""
    try:
        return float(value) if value else default
    except ValueError:
        return default
