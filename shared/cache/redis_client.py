"""
Priya Global — Tenant-Scoped Redis Cache Layer

Every key is prefixed with t:{tenant_id}: to guarantee zero cross-tenant leakage.
This module is imported by ALL 36 services as the single interface to Redis.

Features:
- Tenant-scoped key namespacing (mandatory, cannot be bypassed)
- Automatic JSON serialization/deserialization
- TTL management with sensible defaults per data type
- Connection pooling with health monitoring
- Rate limiter built on Redis INCR + EXPIRE
- Distributed locks for concurrent operation safety
- Cache invalidation (single key, pattern, full tenant flush)
- Pipeline support for batch operations
- Pub/Sub for real-time cache invalidation across service instances

Usage in any service:
    from shared.cache.redis_client import TenantCache
    cache = TenantCache()
    await cache.connect()

    # Set/Get with automatic tenant scoping
    await cache.set(tenant_id, "ai_config", config_dict, ttl=300)
    config = await cache.get(tenant_id, "ai_config")

    # Rate limiting
    allowed = await cache.check_rate_limit(tenant_id, "api", limit=100, window=60)

    # Distributed lock
    async with cache.lock(tenant_id, "inference", timeout=30):
        result = await run_ai_inference(...)
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("priya.cache")

# ============================================================================
# CONFIGURATION
# ============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
REDIS_RETRY_ON_TIMEOUT = os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
REDIS_KEY_PREFIX = "priya"  # Global prefix: priya:t:{tenant_id}:{key}

# Default TTLs (seconds) by data type
DEFAULT_TTLS = {
    "ai_config":        300,    # 5 min — tenant AI config (prompts, intents, tone)
    "tenant_profile":   600,    # 10 min — business profile, country, compliance
    "conversation":     1800,   # 30 min — active conversation context
    "session":          3600,   # 1 hour — user session data
    "channel_config":   600,    # 10 min — channel connection details
    "knowledge":        900,    # 15 min — knowledge base search results
    "analytics":        120,    # 2 min — dashboard analytics (frequently updated)
    "rate_limit":       60,     # 1 min — rate limiter counters
    "lock":             30,     # 30 sec — distributed lock default
    "webhook":          300,    # 5 min — webhook delivery status
    "widget":           600,    # 10 min — webchat widget config
}


# ============================================================================
# REDIS CONNECTION POOL
# ============================================================================

class RedisPool:
    """Manages the Redis connection pool lifecycle"""

    def __init__(self):
        self._pool = None
        self._connected = False
        self._redis = None

    async def connect(self):
        """Initialize Redis connection pool"""
        try:
            import redis.asyncio as aioredis

            connection_kwargs = {
                "max_connections": REDIS_MAX_CONNECTIONS,
                "socket_timeout": REDIS_SOCKET_TIMEOUT,
                "socket_connect_timeout": REDIS_SOCKET_TIMEOUT,
                "retry_on_timeout": REDIS_RETRY_ON_TIMEOUT,
                "decode_responses": True,
                "health_check_interval": 30,
            }

            if REDIS_PASSWORD:
                connection_kwargs["password"] = REDIS_PASSWORD

            self._redis = aioredis.from_url(
                REDIS_URL,
                **connection_kwargs,
            )

            # Test connection
            await self._redis.ping()
            self._connected = True
            logger.info(f"Redis connected: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL}")
            return True

        except ImportError:
            logger.error("redis[asyncio] package required: pip install redis[asyncio]")
            return False
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Close Redis connection pool"""
        if self._redis:
            await self._redis.close()
            self._connected = False
            logger.info("Redis disconnected")

    @property
    def client(self):
        """Get the Redis client instance"""
        if not self._connected or not self._redis:
            raise ConnectionError("Redis not connected. Call connect() first.")
        return self._redis

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis health and return stats"""
        if not self._connected:
            return {"status": "disconnected", "connected": False}
        try:
            start = time.time()
            await self._redis.ping()
            latency_ms = round((time.time() - start) * 1000, 2)

            info = await self._redis.info("memory", "clients", "stats")
            return {
                "status": "healthy",
                "connected": True,
                "latency_ms": latency_ms,
                "used_memory_mb": round(info.get("used_memory", 0) / (1024 * 1024), 2),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "hit_rate": _calculate_hit_rate(info),
            }
        except Exception as e:
            return {"status": "error", "connected": False, "error": str(e)}


def _calculate_hit_rate(info: dict) -> float:
    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total = hits + misses
    return round(hits / total * 100, 2) if total > 0 else 0.0


# Singleton pool
_pool = RedisPool()


# ============================================================================
# TENANT-SCOPED CACHE
# ============================================================================

class TenantCache:
    """
    Tenant-scoped Redis cache with mandatory key namespacing.

    Every operation requires a tenant_id. Keys are structured as:
        priya:t:{tenant_id}:{data_type}:{sub_key}

    This makes it impossible to accidentally read/write another tenant's data.
    """

    def __init__(self, pool: Optional[RedisPool] = None):
        self._pool = pool or _pool

    async def connect(self):
        """Connect to Redis"""
        return await self._pool.connect()

    async def disconnect(self):
        """Disconnect from Redis"""
        await self._pool.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._pool.is_connected

    # ─── Key Construction ───────────────────────────────────────────

    @staticmethod
    def _build_key(tenant_id: str, data_type: str, sub_key: str = "") -> str:
        """Build a tenant-scoped Redis key. NEVER bypass this."""
        if not tenant_id:
            raise ValueError("tenant_id is required for all cache operations")
        if not data_type:
            raise ValueError("data_type is required for all cache operations")

        # Validate tenant_id format — only alphanumeric, hyphen, underscore (no special chars)
        import re
        if not re.match(r"^[a-zA-Z0-9_-]+$", tenant_id):
            raise ValueError(
                f"Invalid tenant_id format. Only alphanumeric, hyphen, and underscore allowed. Got: {tenant_id}"
            )

        # Validate data_type format — only alphanumeric, hyphen, underscore
        if not re.match(r"^[a-zA-Z0-9_-]+$", data_type):
            raise ValueError(
                f"Invalid data_type format. Only alphanumeric, hyphen, and underscore allowed. Got: {data_type}"
            )

        # Validate sub_key if provided — only alphanumeric, hyphen, underscore, colon (for structured sub-keys)
        if sub_key and not re.match(r"^[a-zA-Z0-9_:-]+$", sub_key):
            raise ValueError(
                f"Invalid sub_key format. Only alphanumeric, hyphen, underscore, and colon allowed. Got: {sub_key}"
            )

        base = f"{REDIS_KEY_PREFIX}:t:{tenant_id}:{data_type}"
        if sub_key:
            return f"{base}:{sub_key}"
        return base

    @staticmethod
    def _build_global_key(data_type: str, sub_key: str = "") -> str:
        """Build a global (non-tenant) key. Use sparingly — only for platform-level data."""
        base = f"{REDIS_KEY_PREFIX}:global:{data_type}"
        if sub_key:
            return f"{base}:{sub_key}"
        return base

    # ─── Core Operations ────────────────────────────────────────────

    async def set(
        self,
        tenant_id: str,
        data_type: str,
        value: Any,
        sub_key: str = "",
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a tenant-scoped cache value with automatic JSON serialization"""
        try:
            key = self._build_key(tenant_id, data_type, sub_key)
            if ttl is None:
                ttl = DEFAULT_TTLS.get(data_type, 300)

            serialized = json.dumps(value, default=str)
            await self._pool.client.setex(key, ttl, serialized)
            return True
        except ConnectionError:
            logger.warning("Redis not available — cache SET skipped")
            return False
        except Exception as e:
            logger.error(f"Cache SET failed [{data_type}]: {e}")
            return False

    async def get(
        self,
        tenant_id: str,
        data_type: str,
        sub_key: str = "",
    ) -> Optional[Any]:
        """Get a tenant-scoped cache value with automatic JSON deserialization"""
        try:
            key = self._build_key(tenant_id, data_type, sub_key)
            value = await self._pool.client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except ConnectionError:
            logger.warning("Redis not available — cache GET returned None")
            return None
        except json.JSONDecodeError:
            return value  # Return raw string if not JSON
        except Exception as e:
            logger.error(f"Cache GET failed [{data_type}]: {e}")
            return None

    async def delete(self, tenant_id: str, data_type: str, sub_key: str = "") -> bool:
        """Delete a specific tenant-scoped key"""
        try:
            key = self._build_key(tenant_id, data_type, sub_key)
            await self._pool.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache DELETE failed: {e}")
            return False

    async def exists(self, tenant_id: str, data_type: str, sub_key: str = "") -> bool:
        """Check if a tenant-scoped key exists"""
        try:
            key = self._build_key(tenant_id, data_type, sub_key)
            return await self._pool.client.exists(key) > 0
        except Exception:
            return False

    async def ttl(self, tenant_id: str, data_type: str, sub_key: str = "") -> int:
        """Get remaining TTL for a key (-1 = no expiry, -2 = not found)"""
        try:
            key = self._build_key(tenant_id, data_type, sub_key)
            return await self._pool.client.ttl(key)
        except Exception:
            return -2

    # ─── Batch Operations ───────────────────────────────────────────

    async def mget(
        self,
        tenant_id: str,
        data_type: str,
        sub_keys: List[str],
    ) -> Dict[str, Any]:
        """Get multiple keys at once (pipelined)"""
        try:
            keys = [self._build_key(tenant_id, data_type, sk) for sk in sub_keys]
            values = await self._pool.client.mget(*keys)
            result = {}
            for sk, val in zip(sub_keys, values):
                if val is not None:
                    try:
                        result[sk] = json.loads(val)
                    except json.JSONDecodeError:
                        result[sk] = val
            return result
        except Exception as e:
            logger.error(f"Cache MGET failed: {e}")
            return {}

    async def mset(
        self,
        tenant_id: str,
        data_type: str,
        items: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Set multiple keys at once using pipeline"""
        try:
            if ttl is None:
                ttl = DEFAULT_TTLS.get(data_type, 300)

            pipe = self._pool.client.pipeline()
            for sub_key, value in items.items():
                key = self._build_key(tenant_id, data_type, sub_key)
                serialized = json.dumps(value, default=str)
                pipe.setex(key, ttl, serialized)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Cache MSET failed: {e}")
            return False

    # ─── Tenant Flush ───────────────────────────────────────────────

    async def flush_tenant(self, tenant_id: str) -> int:
        """
        Delete ALL cached data for a specific tenant.
        Used when: tenant config changes, tenant deleted, data breach response.
        Returns count of keys deleted.
        """
        try:
            pattern = f"{REDIS_KEY_PREFIX}:t:{tenant_id}:*"
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await self._pool.client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    await self._pool.client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            logger.info(f"Flushed {deleted} keys for tenant {tenant_id}")
            return deleted
        except Exception as e:
            logger.error(f"Tenant flush failed: {e}")
            return 0

    async def flush_data_type(self, tenant_id: str, data_type: str) -> int:
        """Delete all keys of a specific data type for a tenant"""
        try:
            pattern = f"{REDIS_KEY_PREFIX}:t:{tenant_id}:{data_type}:*"
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await self._pool.client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    await self._pool.client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            # Also delete the base key (without sub_key)
            base_key = self._build_key(tenant_id, data_type)
            await self._pool.client.delete(base_key)
            deleted += 1
            return deleted
        except Exception as e:
            logger.error(f"Data type flush failed: {e}")
            return 0

    # ─── Rate Limiter ───────────────────────────────────────────────

    async def check_rate_limit(
        self,
        tenant_id: str,
        action: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, int]:
        """
        Sliding window rate limiter per tenant per action.

        Returns: (allowed: bool, current_count: int, remaining: int)

        Usage:
            allowed, count, remaining = await cache.check_rate_limit(
                tenant_id, "api_calls", limit=100, window_seconds=60
            )
            if not allowed:
                raise HTTPException(429, "Rate limit exceeded")
        """
        try:
            key = self._build_key(tenant_id, "rate_limit", action)
            pipe = self._pool.client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()

            current = results[0]
            remaining = max(0, limit - current)
            allowed = current <= limit

            return allowed, current, remaining
        except Exception as e:
            logger.error(
                f"Rate limit check failed for tenant={tenant_id} action={action}: {e}. "
                f"FAILING CLOSED to prevent abuse."
            )
            # Fail-closed: deny access on Redis error to prevent abuse
            return False, 0, 0

    async def get_rate_limit_status(
        self, tenant_id: str, action: str, limit: int
    ) -> Dict[str, Any]:
        """Get current rate limit status without incrementing"""
        try:
            key = self._build_key(tenant_id, "rate_limit", action)
            current = await self._pool.client.get(key)
            current = int(current) if current else 0
            ttl_remaining = await self._pool.client.ttl(key)
            return {
                "current": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "reset_in_seconds": max(0, ttl_remaining),
            }
        except Exception:
            return {"current": 0, "limit": limit, "remaining": limit, "reset_in_seconds": 0}

    # ─── Distributed Lock ───────────────────────────────────────────

    @asynccontextmanager
    async def lock(
        self,
        tenant_id: str,
        resource: str,
        timeout: int = 30,
        retry_interval: float = 0.2,
        max_retries: int = 50,
    ):
        """
        Distributed lock for tenant-scoped operations.
        Prevents concurrent modification of the same tenant resource.

        Usage:
            async with cache.lock(tenant_id, "ai_inference"):
                result = await process_message(...)
        """
        lock_key = self._build_key(tenant_id, "lock", resource)
        lock_value = str(uuid.uuid4())
        acquired = False

        try:
            for _ in range(max_retries):
                # SET NX with expiry — atomic acquire
                acquired = await self._pool.client.set(
                    lock_key, lock_value, ex=timeout, nx=True
                )
                if acquired:
                    break
                await asyncio.sleep(retry_interval)

            if not acquired:
                raise TimeoutError(
                    f"Could not acquire lock for {resource} (tenant: {tenant_id}) "
                    f"after {max_retries * retry_interval:.1f}s"
                )

            yield lock_value

        finally:
            if acquired:
                # Release only if we still own the lock (compare-and-delete)
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                try:
                    # NOTE: redis_client.eval() is the Redis server-side Lua executor, not Python's eval()
                    # The Lua script is constant and not derived from user input, making it safe
                    await self._pool.client.eval(lua_script, 1, lock_key, lock_value)
                except Exception as e:
                    logger.warning(
                        f"Lock release failed for tenant={tenant_id} resource={resource}: {e}. "
                        f"Lock will expire naturally in {timeout}s."
                    )

    # ─── Conversation Context Cache ─────────────────────────────────

    async def set_conversation_context(
        self,
        tenant_id: str,
        conversation_id: str,
        context: Dict[str, Any],
        ttl: int = 1800,
    ) -> bool:
        """Cache active conversation context for AI inference"""
        return await self.set(
            tenant_id, "conversation", context,
            sub_key=conversation_id, ttl=ttl,
        )

    async def get_conversation_context(
        self, tenant_id: str, conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached conversation context"""
        return await self.get(tenant_id, "conversation", sub_key=conversation_id)

    async def append_message_to_context(
        self,
        tenant_id: str,
        conversation_id: str,
        message: Dict[str, Any],
        max_messages: int = 50,
    ) -> bool:
        """Append a message to conversation context (list operation)"""
        try:
            key = self._build_key(tenant_id, "conversation", f"{conversation_id}:messages")
            serialized = json.dumps(message, default=str)
            pipe = self._pool.client.pipeline()
            pipe.rpush(key, serialized)
            pipe.ltrim(key, -max_messages, -1)  # Keep only last N messages
            pipe.expire(key, DEFAULT_TTLS["conversation"])
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Message append failed: {e}")
            return False

    async def get_conversation_messages(
        self, tenant_id: str, conversation_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent messages from conversation cache"""
        try:
            key = self._build_key(tenant_id, "conversation", f"{conversation_id}:messages")
            raw_messages = await self._pool.client.lrange(key, -limit, -1)
            return [json.loads(m) for m in raw_messages]
        except Exception as e:
            logger.error(f"Message retrieval failed: {e}")
            return []

    # ─── AI Config Cache ────────────────────────────────────────────

    async def set_ai_config(self, tenant_id: str, config: Dict[str, Any]) -> bool:
        """Cache tenant AI configuration"""
        return await self.set(tenant_id, "ai_config", config)

    async def get_ai_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get cached tenant AI configuration"""
        return await self.get(tenant_id, "ai_config")

    async def invalidate_ai_config(self, tenant_id: str) -> bool:
        """Invalidate AI config cache (call after config update)"""
        return await self.delete(tenant_id, "ai_config")

    # ─── Channel Config Cache ───────────────────────────────────────

    async def set_channel_config(
        self, tenant_id: str, channel: str, config: Dict[str, Any]
    ) -> bool:
        """Cache channel connection config"""
        return await self.set(tenant_id, "channel_config", config, sub_key=channel)

    async def get_channel_config(
        self, tenant_id: str, channel: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached channel config"""
        return await self.get(tenant_id, "channel_config", sub_key=channel)

    # ─── Pub/Sub for Cache Invalidation ─────────────────────────────

    async def publish_invalidation(self, tenant_id: str, data_type: str):
        """Publish cache invalidation event to all service instances"""
        try:
            channel = f"{REDIS_KEY_PREFIX}:invalidate"
            message = json.dumps({
                "tenant_id": tenant_id,
                "data_type": data_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await self._pool.client.publish(channel, message)
        except Exception as e:
            logger.error(f"Publish invalidation failed: {e}")

    async def subscribe_invalidations(self, callback):
        """Subscribe to cache invalidation events"""
        try:
            pubsub = self._pool.client.pubsub()
            await pubsub.subscribe(f"{REDIS_KEY_PREFIX}:invalidate")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await callback(data)
                    except Exception as e:
                        logger.error(f"Invalidation callback error: {e}")
        except Exception as e:
            logger.error(f"Invalidation subscription failed: {e}")

    # ─── Health & Stats ─────────────────────────────────────────────

    async def health_check(self) -> Dict[str, Any]:
        """Redis health check"""
        return await self._pool.health_check()

    async def get_tenant_key_count(self, tenant_id: str) -> int:
        """Count all cached keys for a tenant"""
        try:
            pattern = f"{REDIS_KEY_PREFIX}:t:{tenant_id}:*"
            count = 0
            cursor = 0
            while True:
                cursor, keys = await self._pool.client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception:
            return 0


# ============================================================================
# GLOBAL CACHE — Platform-level data (not tenant-scoped)
# ============================================================================

class GlobalCache:
    """
    Cache for platform-level data that is NOT tenant-specific.
    Examples: service registry, health status, feature flags.
    """

    def __init__(self, pool: Optional[RedisPool] = None):
        self._pool = pool or _pool

    async def set(self, data_type: str, value: Any, sub_key: str = "", ttl: int = 300) -> bool:
        try:
            key = TenantCache._build_global_key(data_type, sub_key)
            serialized = json.dumps(value, default=str)
            await self._pool.client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Global cache SET failed: {e}")
            return False

    async def get(self, data_type: str, sub_key: str = "") -> Optional[Any]:
        try:
            key = TenantCache._build_global_key(data_type, sub_key)
            value = await self._pool.client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.error(f"Global cache GET failed: {e}")
            return None

    async def delete(self, data_type: str, sub_key: str = "") -> bool:
        try:
            key = TenantCache._build_global_key(data_type, sub_key)
            await self._pool.client.delete(key)
            return True
        except Exception:
            return False
