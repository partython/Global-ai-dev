"""
Comprehensive tests for shared.cache.redis_client module.

Tests tenant-scoped key generation, cache operations, rate limiting,
distributed locking, and graceful degradation.
"""

import json
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from shared.cache.redis_client import (
    TenantCache,
    GlobalCache,
    RedisPool,
    DEFAULT_TTLS,
)


class TestTenantCacheKeyConstruction:
    """Test tenant-scoped key generation."""

    @pytest.mark.unit
    def test_build_key_format(self):
        """Keys are formatted as priya:t:{tenant_id}:{data_type}"""
        key = TenantCache._build_key("tenant_123", "ai_config")
        assert key == "priya:t:tenant_123:ai_config"

    @pytest.mark.unit
    def test_build_key_with_sub_key(self):
        """Keys with sub_key include it as suffix."""
        key = TenantCache._build_key("tenant_123", "conversation", "conv_456")
        assert key == "priya:t:tenant_123:conversation:conv_456"

    @pytest.mark.unit
    def test_build_key_requires_tenant_id(self):
        """tenant_id is required."""
        with pytest.raises(ValueError, match="tenant_id is required"):
            TenantCache._build_key("", "ai_config")

    @pytest.mark.unit
    def test_build_key_requires_data_type(self):
        """data_type is required."""
        with pytest.raises(ValueError, match="data_type is required"):
            TenantCache._build_key("tenant_123", "")

    @pytest.mark.unit
    @pytest.mark.security
    def test_build_key_validates_tenant_id_format(self):
        """tenant_id only allows alphanumeric, hyphen, underscore."""
        # Valid
        TenantCache._build_key("tenant-123_abc", "ai_config")

        # Invalid - special characters
        with pytest.raises(ValueError, match="Invalid tenant_id format"):
            TenantCache._build_key("tenant@123", "ai_config")

        with pytest.raises(ValueError, match="Invalid tenant_id format"):
            TenantCache._build_key("tenant.123", "ai_config")

    @pytest.mark.unit
    @pytest.mark.security
    def test_build_key_validates_data_type_format(self):
        """data_type only allows alphanumeric, hyphen, underscore."""
        # Valid
        TenantCache._build_key("tenant_123", "ai-config_v2")

        # Invalid
        with pytest.raises(ValueError, match="Invalid data_type format"):
            TenantCache._build_key("tenant_123", "ai:config")

    @pytest.mark.unit
    def test_build_key_validates_sub_key_format(self):
        """sub_key allows alphanumeric, hyphen, underscore, colon."""
        # Valid
        TenantCache._build_key("tenant_123", "conversation", "conv:456:msg")

        # Invalid
        with pytest.raises(ValueError, match="Invalid sub_key format"):
            TenantCache._build_key("tenant_123", "conversation", "conv@456")

    @pytest.mark.unit
    def test_build_global_key_format(self):
        """Global keys use 'global' instead of tenant_id."""
        key = TenantCache._build_global_key("feature_flags")
        assert key == "priya:global:feature_flags"

    @pytest.mark.unit
    def test_build_global_key_with_sub_key(self):
        """Global keys can have sub_keys."""
        key = TenantCache._build_global_key("feature_flags", "dark_mode")
        assert key == "priya:global:feature_flags:dark_mode"


class TestTenantCacheCoreOperations:
    """Test basic cache get/set operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_set_and_get_string_value(self):
        """Cache can set and retrieve string values."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.is_connected = True

        # Mock the Redis operations
        cache._pool.client.setex = AsyncMock()
        cache._pool.client.get = AsyncMock(return_value='{"test": "value"}')

        await cache.set("tenant_1", "config", {"test": "value"})
        cache._pool.client.setex.assert_called_once()

        result = await cache.get("tenant_1", "config")
        assert result == {"test": "value"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_set_with_default_ttl(self):
        """Cache uses data_type-specific TTL."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.is_connected = True
        cache._pool.client.setex = AsyncMock()

        await cache.set("tenant_1", "ai_config", {"test": "value"})

        # Should use DEFAULT_TTLS["ai_config"] = 300
        call_args = cache._pool.client.setex.call_args
        assert call_args[0][1] == 300

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self):
        """Cache uses custom TTL when provided."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.is_connected = True
        cache._pool.client.setex = AsyncMock()

        await cache.set("tenant_1", "ai_config", {"test": "value"}, ttl=600)

        call_args = cache._pool.client.setex.call_args
        assert call_args[0][1] == 600

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_key(self):
        """Cache returns None for non-existent keys."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.get = AsyncMock(return_value=None)

        result = await cache.get("tenant_1", "nonexistent")
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_key(self):
        """Cache can delete keys."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.delete = AsyncMock()

        await cache.delete("tenant_1", "ai_config")
        cache._pool.client.delete.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_exists_check(self):
        """Cache can check if key exists."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.exists = AsyncMock(return_value=1)

        exists = await cache.exists("tenant_1", "ai_config")
        assert exists is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ttl_check(self):
        """Cache can get remaining TTL."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.ttl = AsyncMock(return_value=300)

        ttl = await cache.ttl("tenant_1", "ai_config")
        assert ttl == 300


class TestTenantCacheBatchOperations:
    """Test batch get/set operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_mget_multiple_keys(self):
        """MGET retrieves multiple keys at once."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.mget = AsyncMock(return_value=[
            '{"value": 1}',
            '{"value": 2}',
            None,
        ])

        result = await cache.mget("tenant_1", "data", ["key1", "key2", "key3"])
        assert result["key1"] == {"value": 1}
        assert result["key2"] == {"value": 2}
        assert "key3" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_mset_multiple_keys(self):
        """MSET sets multiple keys with pipeline."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        pipe = AsyncMock()
        pipe.setex = AsyncMock()
        pipe.execute = AsyncMock()
        cache._pool.client.pipeline = MagicMock(return_value=pipe)

        items = {"key1": {"v": 1}, "key2": {"v": 2}}
        await cache.mset("tenant_1", "data", items)

        assert pipe.setex.call_count == 2
        pipe.execute.assert_called_once()


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self):
        """Rate limit check succeeds when under limit."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        pipe = AsyncMock()
        pipe.incr = AsyncMock()
        pipe.expire = AsyncMock()
        pipe.execute = AsyncMock(return_value=[5, True])  # 5 requests, within 100 limit
        cache._pool.client.pipeline = MagicMock(return_value=pipe)

        allowed, current, remaining = await cache.check_rate_limit(
            "tenant_1", "api", limit=100, window_seconds=60
        )

        assert allowed is True
        assert current == 5
        assert remaining == 95

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """Rate limit check fails when over limit."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        pipe = AsyncMock()
        pipe.incr = AsyncMock()
        pipe.expire = AsyncMock()
        pipe.execute = AsyncMock(return_value=[101, True])  # Over 100 limit
        cache._pool.client.pipeline = MagicMock(return_value=pipe)

        allowed, current, remaining = await cache.check_rate_limit(
            "tenant_1", "api", limit=100, window_seconds=60
        )

        assert allowed is False
        assert current == 101
        assert remaining == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_failure_denies_access(self):
        """Rate limit fails closed on Redis error (deny access for safety)."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.pipeline = AsyncMock(side_effect=Exception("Redis error"))

        allowed, current, remaining = await cache.check_rate_limit(
            "tenant_1", "api", limit=100
        )

        # Fail-closed: deny access
        assert allowed is False
        assert current == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_rate_limit_status(self):
        """Can query rate limit status without incrementing."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.get = AsyncMock(return_value="25")
        cache._pool.client.ttl = AsyncMock(return_value=35)

        status = await cache.get_rate_limit_status("tenant_1", "api", limit=100)

        assert status["current"] == 25
        assert status["limit"] == 100
        assert status["remaining"] == 75
        assert status["reset_in_seconds"] == 35


class TestDistributedLocking:
    """Test distributed locking mechanism."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lock_acquisition(self):
        """Lock can be acquired."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.set = AsyncMock(return_value=True)
        cache._pool.client.eval = AsyncMock(return_value=1)

        async with cache.lock("tenant_1", "resource"):
            # Lock should be held here
            cache._pool.client.set.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lock_timeout_error(self):
        """Lock acquisition times out if resource is held."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.set = AsyncMock(return_value=False)  # Lock not acquired

        with pytest.raises(TimeoutError, match="Could not acquire lock"):
            async with cache.lock("tenant_1", "resource", timeout=1, max_retries=2, retry_interval=0.01):
                pass

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_lock_release(self):
        """Lock is properly released after use."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.set = AsyncMock(return_value=True)
        cache._pool.client.eval = AsyncMock(return_value=1)

        async with cache.lock("tenant_1", "resource"):
            pass

        # Should call eval (Lua script) to release
        cache._pool.client.eval.assert_called_once()


class TestTenantFlush:
    """Test cache invalidation operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_flush_tenant_deletes_all_tenant_keys(self):
        """Flush tenant deletes all keys for that tenant."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        # Mock scan to return some keys
        cache._pool.client.scan = AsyncMock(
            side_effect=[(0, ["priya:t:tenant_1:key1", "priya:t:tenant_1:key2"])]
        )
        cache._pool.client.delete = AsyncMock()

        deleted = await cache.flush_tenant("tenant_1")
        assert deleted == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_flush_data_type_deletes_specific_type(self):
        """Flush data type deletes specific data type for tenant."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        cache._pool.client.scan = AsyncMock(
            side_effect=[(0, ["priya:t:tenant_1:ai_config:key1"])]
        )
        cache._pool.client.delete = AsyncMock()

        deleted = await cache.flush_data_type("tenant_1", "ai_config")
        assert deleted >= 1


class TestConversationContext:
    """Test conversation context caching."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_set_conversation_context(self):
        """Can cache conversation context."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.setex = AsyncMock()

        context = {
            "messages": ["Hi", "Hello"],
            "user_id": "u_123",
        }

        result = await cache.set_conversation_context("tenant_1", "conv_456", context)
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_conversation_context(self):
        """Can retrieve conversation context."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        context = {"messages": ["Hi", "Hello"]}
        cache._pool.client.get = AsyncMock(return_value=json.dumps(context))

        result = await cache.get_conversation_context("tenant_1", "conv_456")
        assert result == context

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_append_message_to_context(self):
        """Can append message to conversation."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        pipe = AsyncMock()
        pipe.rpush = AsyncMock()
        pipe.ltrim = AsyncMock()
        pipe.expire = AsyncMock()
        pipe.execute = AsyncMock()
        cache._pool.client.pipeline = MagicMock(return_value=pipe)

        message = {"role": "user", "text": "Hi"}
        result = await cache.append_message_to_context("tenant_1", "conv_456", message)
        assert result is True


class TestAIConfigCache:
    """Test AI config caching."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_set_ai_config(self):
        """Can cache AI config."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.setex = AsyncMock()

        config_data = {
            "model": "claude-3-5-sonnet",
            "temperature": 0.7,
        }

        result = await cache.set_ai_config("tenant_1", config_data)
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_ai_config(self):
        """Can retrieve AI config."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        config_data = {"model": "claude-3-5-sonnet"}
        cache._pool.client.get = AsyncMock(return_value=json.dumps(config_data))

        result = await cache.get_ai_config("tenant_1")
        assert result == config_data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalidate_ai_config(self):
        """Can invalidate AI config."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.delete = AsyncMock()

        result = await cache.invalidate_ai_config("tenant_1")
        assert result is True


class TestGlobalCache:
    """Test platform-level cache (non-tenant-scoped)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_global_cache_set(self):
        """Global cache can set values."""
        cache = GlobalCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.setex = AsyncMock()

        result = await cache.set("feature_flags", {"dark_mode": True})
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_global_cache_get(self):
        """Global cache can retrieve values."""
        cache = GlobalCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        data = {"dark_mode": True}
        cache._pool.client.get = AsyncMock(return_value=json.dumps(data))

        result = await cache.get("feature_flags")
        assert result == data


class TestJSONSerialization:
    """Test JSON serialization/deserialization."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_set_serializes_to_json(self):
        """Cache serializes Python objects to JSON."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()
        cache._pool.client.setex = AsyncMock()

        data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        await cache.set("tenant_1", "config", data)

        # Check that data was JSON-serialized
        call_args = cache._pool.client.setex.call_args
        serialized = call_args[0][2]
        assert isinstance(serialized, str)
        assert json.loads(serialized) == data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_deserializes_json(self):
        """Cache deserializes JSON back to Python objects."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        data = {"key": "value", "number": 42}
        cache._pool.client.get = AsyncMock(return_value=json.dumps(data))

        result = await cache.get("tenant_1", "config")
        assert result == data
        assert isinstance(result, dict)


class TestConnectionHandling:
    """Test connection and error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_graceful_degradation_on_connection_error(self):
        """Cache operations fail gracefully when Redis is unavailable."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock(side_effect=Exception("Connection refused"))

        # SET should return False gracefully
        result = await cache.set("tenant_1", "config", {"test": "value"})
        assert result is False

        # GET should return None gracefully
        result = await cache.get("tenant_1", "config")
        assert result is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_json_decode_error_handling(self):
        """Cache handles malformed JSON gracefully."""
        cache = TenantCache()
        cache._pool = MagicMock()
        cache._pool.client = AsyncMock()

        cache._pool.client.get = AsyncMock(return_value="not valid json")

        # Should return raw string if JSON decode fails
        result = await cache.get("tenant_1", "config")
        assert result == "not valid json"
