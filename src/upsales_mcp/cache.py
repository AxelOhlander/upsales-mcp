"""Simple TTL cache for Upsales API responses."""

import hashlib
import json
import time

_cache: dict[str, tuple[float, str]] = {}
_DEFAULT_TTL = 300  # 5 minutes


def make_key(prefix: str, api_key: str, *args, **kwargs) -> str:
    """Create a cache key from function arguments and API key."""
    raw = json.dumps(
        {"prefix": prefix, "args": args, "kwargs": kwargs}, sort_keys=True, default=str
    )
    # Include API key hash so hosted-mode users don't share caches
    key_hash = hashlib.sha256((api_key + raw).encode()).hexdigest()[:16]
    return f"{prefix}:{key_hash}"


def get(key: str) -> str | None:
    """Get a cached value if it exists and hasn't expired."""
    if key in _cache:
        ts, value = _cache[key]
        if time.time() - ts < _DEFAULT_TTL:
            return value
        del _cache[key]
    return None


def put(key: str, value: str) -> None:
    """Store a value in the cache."""
    # Evict expired entries if cache grows large
    if len(_cache) > 500:
        now = time.time()
        expired = [k for k, (ts, _) in _cache.items() if now - ts >= _DEFAULT_TTL]
        for k in expired:
            del _cache[k]
    _cache[key] = (time.time(), value)


def clear() -> None:
    """Clear the entire cache."""
    _cache.clear()
