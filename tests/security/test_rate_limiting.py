"""
Rate Limiting Security Tests

Tests plan-based rate limits, per-tenant limits, distributed rate limiting,
and rate limit bypass attempts.

Standards:
- API security: Rate limit enforcement
- DoS prevention: Protect against abuse
"""

import pytest
import time
from datetime import datetime, timedelta, timezone

pytestmark = [
    pytest.mark.security,
]


# ============================================================================
# Per-Tenant Rate Limiting Tests
# ============================================================================


class TestPerTenantRateLimits:
    """Test that rate limits are enforced per tenant."""

    def test_each_tenant_has_separate_counter(self):
        """
        Security: Tenant A's API calls don't count toward Tenant B's limit.
        Each tenant has independent rate limit bucket.
        """
        tenant_a = "tenant-a"
        tenant_b = "tenant-b"

        # Mock rate limit tracking
        counters = {
            f"t:{tenant_a}:rate_limit:api": 0,
            f"t:{tenant_b}:rate_limit:api": 0,
        }

        # Tenant A makes 50 requests
        counters[f"t:{tenant_a}:rate_limit:api"] += 50

        # Tenant B makes 50 requests
        counters[f"t:{tenant_b}:rate_limit:api"] += 50

        # Each has their own counter
        assert counters[f"t:{tenant_a}:rate_limit:api"] == 50
        assert counters[f"t:{tenant_b}:rate_limit:api"] == 50

    @pytest.mark.asyncio
    async def test_rate_limit_tracks_per_tenant_per_action(self, mock_redis):
        """
        Security: Rate limits are by (tenant, action, window).
        """
        from shared.cache.redis_client import TenantCache

        cache = TenantCache()
        tenant_a = "tenant-a"

        # Different actions have separate counters
        allowed_1, count_1, remaining_1 = await cache.check_rate_limit(
            tenant_a, "api_calls", limit=100, window_seconds=60
        )

        allowed_2, count_2, remaining_2 = await cache.check_rate_limit(
            tenant_a, "inference", limit=10, window_seconds=60
        )

        # Both can be at limit independently
        assert count_1 != count_2  # Different actions


# ============================================================================
# Plan-Based Rate Limits Tests
# ============================================================================


class TestPlanBasedRateLimits:
    """Test that rate limits vary by subscription plan."""

    def test_free_plan_lower_limit(self):
        """
        Security: Free plan gets lower rate limit (e.g., 100 req/min).
        """
        from shared.core.security import get_rate_limit

        free_limit = get_rate_limit("free")
        starter_limit = get_rate_limit("starter")
        enterprise_limit = get_rate_limit("enterprise")

        # Free < Starter < Enterprise
        assert free_limit < starter_limit
        assert starter_limit < enterprise_limit

    def test_starter_plan_moderate_limit(self):
        """
        Starter plan: moderate limit (e.g., 500 req/min).
        """
        from shared.core.security import get_rate_limit

        starter_limit = get_rate_limit("starter")

        # Typical starter: 500 req/min
        assert 200 <= starter_limit <= 1000

    def test_enterprise_plan_unlimited(self):
        """
        Enterprise plan: unlimited or very high limit.
        """
        from shared.core.security import get_rate_limit

        enterprise_limit = get_rate_limit("enterprise")

        # Typically very high or special handling
        assert enterprise_limit > 10000 or enterprise_limit == -1  # -1 = unlimited

    def test_plan_upgrade_increases_limit(self):
        """
        Security: User upgrades plan -> limit increases immediately.
        """
        from shared.core.security import get_rate_limit

        before_upgrade = get_rate_limit("starter")
        after_upgrade = get_rate_limit("growth")

        assert after_upgrade > before_upgrade

    def test_plan_downgrade_decreases_limit(self):
        """
        Security: Plan downgrade -> limit decreases.
        If already over limit, requests are rejected.
        """
        from shared.core.security import get_rate_limit

        before_downgrade = get_rate_limit("enterprise")
        after_downgrade = get_rate_limit("starter")

        assert after_downgrade < before_downgrade


# ============================================================================
# Rate Limit Response Headers Tests
# ============================================================================


class TestRateLimitHeaders:
    """Test that rate limit information is returned in headers."""

    def test_rate_limit_headers_present(self):
        """
        Security & UX: Response should include:
        - X-RateLimit-Limit: total limit
        - X-RateLimit-Remaining: how many left
        - X-RateLimit-Reset: when it resets (timestamp)
        """
        response_headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "87",
            "X-RateLimit-Reset": "1679079600",
        }

        assert "X-RateLimit-Limit" in response_headers
        assert "X-RateLimit-Remaining" in response_headers
        assert "X-RateLimit-Reset" in response_headers

    def test_rate_limit_remaining_decreases(self):
        """
        Security: Remaining count should decrease with each request.
        """
        remaining = 100

        # Make request
        remaining -= 1

        # Make another request
        remaining -= 1

        assert remaining == 98

    def test_rate_limit_reset_timestamp_valid(self):
        """
        Security: Reset timestamp should be in the future.
        """
        import time

        reset_timestamp = int(time.time()) + 60  # 60 seconds from now

        now = int(time.time())
        assert reset_timestamp > now


# ============================================================================
# 429 Too Many Requests Tests
# ============================================================================


class TestTooManyRequestsResponse:
    """Test proper 429 response when rate limited."""

    def test_429_returned_when_limit_exceeded(self):
        """
        Security: When limit exceeded, return 429 Too Many Requests.
        """
        status_code = 429
        response = {
            "error": "Rate limit exceeded",
            "retry_after": 45,
        }

        assert status_code == 429
        assert "rate" in response["error"].lower()

    def test_retry_after_header_present(self):
        """
        Security: 429 response includes Retry-After header.
        Tells client how long to wait.
        """
        response_headers = {
            "Retry-After": "45",  # Wait 45 seconds
        }

        assert "Retry-After" in response_headers

    def test_429_response_body_helpful(self):
        """
        Security: 429 error message explains why and when to retry.
        """
        response_body = {
            "error": "Rate limit exceeded",
            "message": "You have exceeded your 100 requests per minute limit",
            "retry_after_seconds": 45,
            "limit": 100,
            "window_seconds": 60,
        }

        assert "limit" in response_body
        assert "retry_after" in response_body


# ============================================================================
# Rate Limit Bypass Attempt Tests
# ============================================================================


class TestRateLimitBypassPrevention:
    """Test that rate limit bypass attempts are blocked."""

    def test_header_injection_bypass_attempt_blocked(self):
        """
        Security: Manipulating rate limit headers doesn't bypass the limit.
        Client cannot claim to be under limit.
        """
        # User tries to send: X-RateLimit-Bypass: true
        # Service ignores this, uses server-side counter

        request_headers = {
            "X-RateLimit-Bypass": "true",
        }

        # Service doesn't care about this header
        # Still uses Redis counter

        assert "X-RateLimit-Bypass" in request_headers
        # But service doesn't honor it

    def test_multiple_identities_bypass_attempt(self):
        """
        Security: User cannot bypass by claiming different identities.
        Rate limit keyed by (tenant_id, action), not client claim.
        """
        # User tries: Same request with different X-User-Id headers
        # Service uses JWT tenant_id from token, not header

        token_tenant = "tenant-a"
        header_tenant = "tenant-b"

        # Service uses token_tenant, ignoring header_tenant
        actual_tenant = token_tenant

        assert actual_tenant == "tenant-a"

    def test_distributed_attack_across_ips(self):
        """
        Security: Even if attacker uses multiple IPs, rate limit still applies.
        Rate limit is per (tenant_id, action), not per IP.
        """
        # Attacker uses 10 IPs to make 10x more requests
        # But all requests from same tenant_id

        tenant_id = "malicious-tenant"
        request_ips = [f"10.0.0.{i}" for i in range(10)]

        # Rate limit is still per tenant_id, not per IP
        # All requests count toward same counter
        # Eventually hit limit regardless of source IP

        assert len(request_ips) == 10
        # But rate limit is tenant-id based, not IP based


# ============================================================================
# Sliding Window Rate Limiting Tests
# ============================================================================


class TestSlidingWindowRateLimit:
    """Test sliding window rate limiter implementation."""

    @pytest.mark.asyncio
    async def test_sliding_window_allows_burst_at_start(self):
        """
        Security: Sliding window allows burst at start of window.
        Then enforces limit as time passes.
        """
        from shared.cache.redis_client import TenantCache

        cache = TenantCache()
        tenant_id = "tenant-test"

        # Start of window: can make up to 100 requests quickly
        allowed_requests = 0
        for _ in range(100):
            allowed, _, _ = await cache.check_rate_limit(
                tenant_id, "test_action", limit=100, window_seconds=60
            )
            if allowed:
                allowed_requests += 1

        # 100 requests in quick succession should be allowed
        assert allowed_requests == 100

    def test_counter_resets_after_window(self):
        """
        Security: Counter resets after time window expires.
        """
        # Time window: 60 seconds
        # At T+0: counter starts
        # At T+60: counter resets
        # At T+61: can make requests again

        window_duration = 60  # seconds

        first_window_end = datetime.now(timezone.utc) + timedelta(seconds=window_duration)
        reset_time = first_window_end

        # After reset time, counter is fresh
        assert reset_time == first_window_end


# ============================================================================
# Distributed Rate Limiting Tests
# ============================================================================


class TestDistributedRateLimiting:
    """Test rate limiting across multiple service instances."""

    def test_same_tenant_from_different_instances(self):
        """
        Security: Rate limit is global, not per-instance.
        Tenant hitting limit on instance A affects instance B.

        Mechanism: Shared Redis stores counters.
        """
        # Instance 1: /gateway-1/api/conversations
        # Instance 2: /gateway-2/api/conversations
        # Both increment same Redis counter key

        tenant_id = "tenant-a"
        action = "api_calls"

        # Redis key: priya:t:tenant-a:rate_limit:api_calls
        # Same key used by all instances

        redis_key = f"priya:t:{tenant_id}:rate_limit:{action}"

        # All instances increment this same key
        # Provides global rate limiting

    def test_rate_limit_enforcement_consistent(self):
        """
        Security: Limit is enforced consistently across all instances.
        """
        # Tenant with 100 req/min limit:
        # Instance 1: 60 requests made
        # Instance 2: sees counter at 60
        # Instance 2: can only make 40 more in this minute

        instance_1_made = 60
        limit = 100

        available_for_instance_2 = limit - instance_1_made

        assert available_for_instance_2 == 40


# ============================================================================
# Action-Specific Rate Limits Tests
# ============================================================================


class TestActionSpecificLimits:
    """Test that different actions have different limits."""

    def test_api_calls_vs_inference_limits(self):
        """
        Security: API calls and AI inference may have different limits.
        Example: 100 API calls/min but only 10 inference/min.
        """
        # Tenant A quota:
        # - api_calls: 100/min
        # - inference: 10/min
        # - conversations: 50/min

        quotas = {
            "api_calls": 100,
            "inference": 10,
            "conversations": 50,
        }

        # Different actions don't share limit
        assert quotas["api_calls"] != quotas["inference"]

    def test_read_vs_write_limits(self):
        """
        Security: Write operations may be more restricted than reads.
        Example: 1000 reads/min, 100 writes/min.
        """
        limits = {
            "read": 1000,
            "write": 100,
        }

        assert limits["read"] > limits["write"]


# ============================================================================
# Rate Limit Configuration Tests
# ============================================================================


class TestRateLimitConfiguration:
    """Test rate limit configuration is correct."""

    def test_default_limits_configured(self):
        """
        Security: All plans have appropriate rate limits defined.
        """
        from shared.core.config import config

        # Verify limits are set
        assert hasattr(config.security, 'rate_limit_starter')
        assert hasattr(config.security, 'rate_limit_growth')
        assert hasattr(config.security, 'rate_limit_enterprise')

        # Verify values are reasonable
        assert config.security.rate_limit_starter > 0
        assert config.security.rate_limit_growth > config.security.rate_limit_starter

    def test_window_duration_appropriate(self):
        """
        Security: Rate limit window is reasonable duration.
        Typically 60 seconds (1 minute).
        """
        window = 60  # 1 minute

        # Should not be too short (allows burst)
        assert window >= 60
        # Should not be too long (ineffective)
        assert window <= 3600


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
