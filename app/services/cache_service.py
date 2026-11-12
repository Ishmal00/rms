import json
import logging
import time
from functools import wraps
import redis

logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis caching service with graceful in-memory TTL fallback.
    Supports JSON serialization, pattern-based invalidation, and decorators.
    """

    def __init__(self, redis_url=None):
        self.redis_client = None
        self._memory_cache = {}  # key -> (value, expiry_timestamp)
        self.is_redis_connected = False
        if redis_url:
            self.init_app(redis_url)

    def init_app(self, redis_url):
        try:
            self.redis_client = redis.from_url(
                redis_url,
                socket_timeout=1.5,
                socket_connect_timeout=1.5,
                decode_responses=True
            )
            # Test ping
            self.redis_client.ping()
            self.is_redis_connected = True
            logger.info("Connected successfully to Redis at %s", redis_url)
        except Exception as e:
            self.is_redis_connected = False
            self.redis_client = None
            logger.warning("Redis not available (%s). Utilizing resilient in-memory cache.", e)

    def get(self, key):
        """Retrieve value from cache."""
        if self.is_redis_connected and self.redis_client:
            try:
                val = self.redis_client.get(key)
                if val is not None:
                    return json.loads(val)
                return None
            except Exception as e:
                logger.error("Redis get error for %s: %s", key, e)

        # Fallback to in-memory cache
        item = self._memory_cache.get(key)
        if item:
            val, expiry = item
            if expiry is None or time.time() < expiry:
                return val
            else:
                del self._memory_cache[key]
        return None

    def set(self, key, value, timeout=300):
        """Store value in cache with timeout in seconds."""
        if self.is_redis_connected and self.redis_client:
            try:
                self.redis_client.set(key, json.dumps(value), ex=timeout)
                return True
            except Exception as e:
                logger.error("Redis set error for %s: %s", key, e)

        # Fallback to in-memory cache
        expiry = (time.time() + timeout) if timeout else None
        self._memory_cache[key] = (value, expiry)
        return True

    def delete(self, key):
        """Delete specific key from cache."""
        if self.is_redis_connected and self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.error("Redis delete error for %s: %s", key, e)

        self._memory_cache.pop(key, None)
        return True

    def delete_pattern(self, pattern):
        """Invalidate all keys matching pattern (e.g. 'menu:*')."""
        if self.is_redis_connected and self.redis_client:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                logger.error("Redis delete_pattern error for %s: %s", pattern, e)

        # In-memory pattern cleanup
        clean_pattern = pattern.replace('*', '')
        to_del = [k for k in self._memory_cache if clean_pattern in k]
        for k in to_del:
            del self._memory_cache[k]
        return True

    def clear(self):
        """Flush cache."""
        if self.is_redis_connected and self.redis_client:
            try:
                self.redis_client.flushdb()
            except Exception:
                pass
        self._memory_cache.clear()


cache = CacheService()


def cached(key_prefix, timeout=300):
    """
    Decorator for caching function return values.
    Usage: @cached(key_prefix='menu_categories', timeout=600)
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Build cache key from function arguments
            arg_str = ":".join(str(a) for a in args) + ":" + ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = f"{key_prefix}:{arg_str}" if arg_str.strip(":") else key_prefix

            data = cache.get(cache_key)
            if data is not None:
                return data

            result = f(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            return result
        return wrapper
    return decorator


def invalidate_menu_cache():
    """Invalidates menu, category, and subcategory caches."""
    cache.delete_pattern("menu:*")
    cache.delete_pattern("categories:*")


def invalidate_dashboard_cache():
    """Invalidates dashboard metrics cache."""
    cache.delete_pattern("dashboard:*")


def invalidate_report_cache():
    """Invalidates financial reports and KPI caches."""
    cache.delete_pattern("reports:*")


def invalidate_settings_cache():
    """Invalidates system settings caches."""
    cache.delete_pattern("settings:*")


def invalidate_inventory_cache():
    """Invalidates inventory and stock caches."""
    cache.delete_pattern("inventory:*")

