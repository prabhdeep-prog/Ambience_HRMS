"""
horilla/cache_utils.py

Low-level cache API utilities with Thundering Herd (dog-pile) protection.

Problem: Cache Stampede / Thundering Herd
──────────────────────────────────────────
When a cached key expires and 50 HR managers refresh the dashboard at the
same moment, every one of their requests finds a cache miss and fires the
same expensive DB query simultaneously.  This doubles the load at exactly
the worst time — just after the cache gave out.

Solution: Lock + Stale-While-Revalidate
────────────────────────────────────────
We maintain THREE Redis keys per logical cache entry:

  PRIMARY  ({prefix})         TTL = timeout (e.g. 5 min)
                              The value served on cache hits.

  STALE    ({prefix}:stale)   TTL = timeout × STALE_MULTIPLIER (50 min)
                              An older copy kept around as fallback.

  LOCK     ({prefix}:lock)    TTL = lock_timeout (30 s)
                              Set with SET NX — only ONE process can hold it.

On PRIMARY miss:
  1. Try cache.add(LOCK) — Django's cache.add() is atomic SET NX EX.
  2. If lock acquired (we won):
       → compute value
       → write PRIMARY (TTL=5 min) and STALE (TTL=50 min)
       → release lock
  3. If lock NOT acquired (another worker is already recomputing):
       → immediately return STALE (slightly old, but instant)
       → if no stale either (absolute cold start) → compute synchronously

This means at most ONE DB query fires per cache-miss cycle regardless of how
many concurrent requests arrive.  The other 49 users get a ≤5-minute-old
result with zero additional load.

Usage
─────
  from horilla.cache_utils import stampede_cache

  def _compute_stats():
      return {"active": Employee.objects.filter(is_active=True).count(), ...}

  stats = stampede_cache.get_or_compute(
      key="horilla:dashboard:employee:stats",
      compute_fn=_compute_stats,
      timeout=300,
  )

Or use the decorator form:

  @stampede_cache.cached("horilla:dashboard:employee:stats", timeout=300)
  def _compute_stats():
      ...

Cache key naming conventions used in this project
──────────────────────────────────────────────────
  horilla:dashboard:<module>:<variant>
  e.g.
    horilla:dashboard:employee:active_inactive
    horilla:dashboard:employee:gender
    horilla:dashboard:employee:department
    horilla:dashboard:attendance:stats:{YYYY-MM-DD}
    horilla:dashboard:leave:stats:{YYYY-MM}
    horilla:dashboard:recruitment:main
"""

import logging
import time
from functools import wraps

from django.core.cache import cache

logger = logging.getLogger(__name__)


class StampedeProtectedCache:
    """
    Wraps Django's low-level cache API with dog-pile protection.

    Parameters
    ──────────
    stale_multiplier : int
        How many times longer the stale copy lives versus the primary.
        Default 10 means if TTL=300 s the stale copy survives 3 000 s (50 min).
    lock_timeout : int
        How long (seconds) the recompute lock is held before auto-expiry.
        Should be longer than the slowest possible compute_fn() call.
        Default 30 s — if a compute hangs for >30 s other workers will
        re-attempt rather than waiting forever.
    """

    STALE_SUFFIX = ":stale"
    LOCK_SUFFIX = ":lock"

    def __init__(self, stale_multiplier: int = 10, lock_timeout: int = 30):
        self.stale_multiplier = stale_multiplier
        self.lock_timeout = lock_timeout

    # ── Core API ──────────────────────────────────────────────────────────────

    def get_or_compute(
        self,
        key: str,
        compute_fn,
        timeout: int = 300,
        version=None,
    ):
        """
        Return cached value for `key`, computing it if necessary.

        Parameters
        ──────────
        key         Cache key string.
        compute_fn  Zero-argument callable that returns the value to cache.
        timeout     Primary TTL in seconds (default 300 = 5 min).
        version     Optional Django cache versioning integer.

        Returns
        ───────
        The cached (or freshly computed) value.
        """
        # ── Fast path: primary cache hit ──────────────────────────────────────
        cached = cache.get(key, version=version)
        if cached is not None:
            return cached

        lock_key = key + self.LOCK_SUFFIX
        stale_key = key + self.STALE_SUFFIX

        # ── Try to win the recompute lock (atomic SET NX EX) ──────────────────
        # cache.add() returns True only if the key did NOT already exist.
        lock_acquired = cache.add(lock_key, 1, timeout=self.lock_timeout)

        if lock_acquired:
            # We are the designated recomputer for this cache miss.
            t0 = time.monotonic()
            try:
                value = compute_fn()
                cache.set(key, value, timeout=timeout, version=version)
                cache.set(
                    stale_key,
                    value,
                    timeout=timeout * self.stale_multiplier,
                    version=version,
                )
                elapsed = time.monotonic() - t0
                logger.debug(
                    "Cache miss → recomputed %s in %.3f s (TTL=%d s)", key, elapsed, timeout
                )
                return value
            except Exception as exc:
                logger.exception("Cache compute_fn failed for key=%s: %s", key, exc)
                raise
            finally:
                # Always release the lock so other workers don't wait 30 s.
                cache.delete(lock_key)
        else:
            # Another worker holds the lock and is currently recomputing.
            # Serve the stale copy immediately (zero added DB load).
            stale = cache.get(stale_key, version=version)
            if stale is not None:
                logger.debug(
                    "Cache miss for %s — lock held by another worker, serving stale", key
                )
                return stale

            # Absolute cold start: no primary, no stale, no lock we hold.
            # This only happens on first-ever boot or after a Redis flush.
            # We must compute synchronously — unavoidable.
            logger.warning(
                "Cache cold-start for %s — computing synchronously (no stale available)", key
            )
            value = compute_fn()
            cache.set(key, value, timeout=timeout, version=version)
            cache.set(
                stale_key, value,
                timeout=timeout * self.stale_multiplier,
                version=version,
            )
            return value

    def invalidate(self, key: str, version=None) -> None:
        """Delete primary, stale and lock keys for `key`."""
        cache.delete(key, version=version)
        cache.delete(key + self.STALE_SUFFIX, version=version)
        cache.delete(key + self.LOCK_SUFFIX, version=version)
        logger.debug("Cache invalidated: %s", key)

    # ── Decorator form ────────────────────────────────────────────────────────

    def cached(self, key: str, timeout: int = 300, version=None):
        """
        Decorator.  Wraps a zero-argument function with stampede protection.

        Example::

            @stampede_cache.cached("horilla:dashboard:employee:gender", timeout=300)
            def _compute_gender_chart():
                ...
        """
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                return self.get_or_compute(
                    key=key,
                    compute_fn=lambda: fn(*args, **kwargs),
                    timeout=timeout,
                    version=version,
                )
            wrapper.invalidate = lambda: self.invalidate(key, version=version)
            return wrapper
        return decorator


# ── Module-level singleton — import this everywhere ───────────────────────────
stampede_cache = StampedeProtectedCache(stale_multiplier=10, lock_timeout=30)
