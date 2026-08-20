"""
Simple in-memory LRU-style query cache.
Caches search results so identical queries are instant on repeat.
Max 200 entries; oldest evicted first.
"""
from collections import OrderedDict
import time

_CACHE: OrderedDict = OrderedDict()
_MAX   = 200
_TTL   = 300   # seconds — invalidate after 5 min


def cache_get(key: str):
    """Return cached value or None if missing/expired."""
    entry = _CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > _TTL:
        _CACHE.pop(key, None)
        return None
    # Move to end (most-recently-used)
    _CACHE.move_to_end(key)
    return entry["value"]


def cache_set(key: str, value) -> None:
    """Store value. Evicts oldest entry when over capacity."""
    if key in _CACHE:
        _CACHE.move_to_end(key)
    _CACHE[key] = {"value": value, "ts": time.time()}
    if len(_CACHE) > _MAX:
        _CACHE.popitem(last=False)


def cache_clear() -> None:
    _CACHE.clear()


def cache_stats() -> dict:
    return {"size": len(_CACHE), "max": _MAX, "ttl_seconds": _TTL}