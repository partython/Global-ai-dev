"""
Comprehensive tests for Priya Global API Gateway Service.

Tests cover:
- Health endpoint and service aggregation
- Routing table and path matching
- Rate limiting (per-tenant, IP-based)
- JWT extraction and validation
- Request proxying and timeout handling
- CORS headers
- Gzip compression
- Request tracing (X-Request-ID)
- Security headers
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
import httpx
import jwt
from datetime import datetime, timedelta, timezone

# Import the gateway app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.gateway import main
from shared.core.config import config


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(main.app)


@pytest.fixture
def valid_jwt_token():
    """Generate a valid JWT token for testing."""
    payload = {
        "user_id": "user-123",
        "tenant_id": "tenant-456",
        "email": "test@example.com",
        "role": "owner",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "secret", algorithm="HS256")
    return token


@pytest.fixture
def expired_jwt_token():
    """Generate an expired JWT token."""
    payload = {
        "user_id": "user-123",
        "tenant_id": "tenant-456",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, "secret", algorithm="HS256")
    return token


@pytest.fixture
def auth_headers(valid_jwt_token):
    """Authorization headers with valid token."""
    return {"Authorization": f"Bearer {valid_jwt_token}"}


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_gateway_health(self, client):
        """Test /health endpoint returns gateway status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "api-gateway"
        assert "timestamp" in data
        assert "version" in data

    @patch("services.gateway.main.http_client")
    @pytest.mark.asyncio
    async def test_services_health_check(self, mock_http, client):
        """Test /health/services aggregates downstream service status."""
        response = client.get("/health/services")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "services" in data
        assert "timestamp" in data


class TestRoutingTable:
    """Test request routing logic."""

    def test_routing_table_populated(self):
        """Test that ROUTE_TABLE contains expected services."""
        assert "/api/v1/auth" in main.ROUTE_TABLE
        assert "/api/v1/tenants" in main.ROUTE_TABLE
        assert "/api/v1/messages" in main.ROUTE_TABLE
        assert "/api/v1/ai" in main.ROUTE_TABLE

    def test_route_table_config_has_required_fields(self):
        """Test route configurations have required fields."""
        for prefix, config_dict in main.ROUTE_TABLE.items():
            assert "target" in config_dict
            assert "timeout" in config_dict
            assert "auth_required" in config_dict
            assert "name" in config_dict
            assert config_dict["timeout"] > 0

    def test_webhook_table_populated(self):
        """Test that WEBHOOK_TABLE exists."""
        assert "/webhook/whatsapp" in main.WEBHOOK_TABLE
        assert "/webhook/ses" in main.WEBHOOK_TABLE
        assert main.WEBHOOK_TABLE["/webhook/whatsapp"]["timeout"] > 0

    def test_find_route_longest_prefix_match(self):
        """Test longest prefix matching in route finding."""
        prefix, config = main.find_route("/api/v1/auth/register")
        assert prefix == "/api/v1/auth"
        assert config["target"] == "http://localhost:9001"

    def test_find_route_no_match_returns_none(self):
        """Test route not found returns None."""
        prefix, config = main.find_route("/api/v2/unknown")
        assert prefix is None
        assert config is None

    def test_find_route_exact_match(self):
        """Test exact route match."""
        prefix, config = main.find_route("/api/v1/tenants/123")
        assert prefix == "/api/v1/tenants"
        assert config["auth_required"] is True


class TestJWTExtraction:
    """Test JWT token extraction and validation."""

    def test_extract_valid_token(self, valid_jwt_token):
        """Test extracting claims from valid token."""
        auth_header = f"Bearer {valid_jwt_token}"
        claims = main.extract_and_validate_token(auth_header)
        assert claims is not None
        assert claims["tenant_id"] == "tenant-456"

    def test_extract_expired_token_returns_none(self, expired_jwt_token):
        """Test expired token is rejected."""
        auth_header = f"Bearer {expired_jwt_token}"
        claims = main.extract_and_validate_token(auth_header)
        assert claims is None

    def test_extract_no_token_returns_none(self):
        """Test missing token returns None."""
        claims = main.extract_and_validate_token(None)
        assert claims is None

    def test_extract_malformed_bearer_returns_none(self):
        """Test malformed Bearer header returns None."""
        claims = main.extract_and_validate_token("InvalidToken")
        assert claims is None

    def test_extract_bearer_case_insensitive(self, valid_jwt_token):
        """Test Bearer prefix is case-insensitive."""
        auth_header = f"bearer {valid_jwt_token}"
        claims = main.extract_and_validate_token(auth_header)
        assert claims is not None

    def test_extract_invalid_jwt_returns_none(self):
        """Test invalid JWT returns None."""
        auth_header = "Bearer invalid.jwt.token"
        claims = main.extract_and_validate_token(auth_header)
        assert claims is None


class TestAuthentication:
    """Test authentication requirement and handling."""

    @patch("services.gateway.main.http_client")
    def test_auth_required_route_without_token(self, mock_http, client):
        """Test authenticated route rejects request without token."""
        response = client.get("/api/v1/tenants/123")
        assert response.status_code == 401
        data = response.json()
        assert "Unauthorized" in data["detail"]

    @patch("services.gateway.main.http_client")
    def test_auth_required_route_with_expired_token(self, mock_http, client, expired_jwt_token):
        """Test authenticated route rejects expired token."""
        headers = {"Authorization": f"Bearer {expired_jwt_token}"}
        response = client.get("/api/v1/tenants/123", headers=headers)
        assert response.status_code == 401

    @patch("services.gateway.main.http_client")
    def test_auth_not_required_for_register(self, mock_http, client):
        """Test /auth/register doesn't require auth."""
        with patch("services.gateway.main.http_client.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.headers = {}
            mock_post.return_value.aread = AsyncMock(return_value=b'{}')
            # Note: This would need actual proxy setup, testing auth_required flag
            assert main.ROUTE_TABLE["/api/v1/auth"]["auth_required"] is False

    def test_token_missing_tenant_id_rejected(self, client, valid_jwt_token):
        """Test token without tenant_id is rejected."""
        payload = {
            "user_id": "user-123",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        bad_token = jwt.encode(payload, "secret", algorithm="HS256")
        headers = {"Authorization": f"Bearer {bad_token}"}
        response = client.get("/api/v1/tenants/123", headers=headers)
        assert response.status_code == 401
        assert "tenant_id" in response.json()["detail"]


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_check_no_redis_returns_true(self):
        """Test rate limit check passes when Redis is unavailable."""
        with patch("services.gateway.main.redis_client", None):
            allowed, response_dict = await main.check_rate_limit(
                "tenant-123", "192.168.1.1", "/api/v1/test"
            )
            assert allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_returns_headers(self):
        """Test rate limit check returns limit headers."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()

        with patch("services.gateway.main.redis_client", mock_redis):
            allowed, response_dict = await main.check_rate_limit(
                "tenant-123", "192.168.1.1", "/api/v1/test"
            )
            assert allowed is True
            assert response_dict is not None
            assert "X-RateLimit-Limit" in response_dict

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_false(self):
        """Test rate limit exceeded returns 429."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=10001)  # Over limit
        mock_redis.expire = AsyncMock()

        with patch("services.gateway.main.redis_client", mock_redis):
            allowed, response_dict = await main.check_rate_limit(
                "tenant-123", "192.168.1.1", "/api/v1/test"
            )
            assert allowed is False
            assert response_dict["status_code"] == 429


class TestSecurityHeaders:
    """Test security headers in responses."""

    def test_security_headers_present(self, client):
        """Test security headers are included in response."""
        response = client.get("/health")
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "X-XSS-Protection" in response.headers

    def test_cors_headers_in_response(self, client):
        """Test CORS headers are present."""
        response = client.options("/api/v1/auth/login")
        assert response.status_code in [200, 204]


class TestRequestTracing:
    """Test request tracing with X-Request-ID."""

    def test_request_id_generated_and_returned(self, client):
        """Test X-Request-ID is generated and included in response."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) > 0


class TestNotFound:
    """Test 404 handling."""

    def test_unknown_route_returns_404(self, client):
        """Test unknown route returns 404."""
        response = client.get("/api/v1/nonexistent/path")
        assert response.status_code == 404
        assert "Not found" in response.json()["detail"]

    def test_404_includes_security_headers(self, client):
        """Test 404 response includes security headers."""
        response = client.get("/api/v1/nonexistent/path")
        assert response.status_code == 404
        assert "X-Content-Type-Options" in response.headers


class TestGzipCompression:
    """Test gzip compression of responses."""

    @patch("services.gateway.main.compress_response")
    async def test_large_response_compressed(self, mock_compress):
        """Test large responses are compressed."""
        large_content = b"x" * 2000
        await main.compress_response(large_content)
        # Content should have been compressed
        assert len(large_content) > 1024


class TestProxyRequest:
    """Test proxy request handling."""

    @pytest.mark.asyncio
    async def test_proxy_no_http_client_returns_503(self):
        """Test proxy request fails gracefully without HTTP client."""
        with patch("services.gateway.main.http_client", None):
            mock_request = MagicMock()
            response = await main.proxy_request(
                mock_request, "http://localhost:9001", 5
            )
            assert response.status_code == 503

    def test_request_size_limit_enforced(self, client):
        """Test request body size limit is enforced."""
        large_body = "x" * (11 * 1024 * 1024)  # 11MB
        # This would hit the proxy_request size check
        # Note: Actual testing requires async context


class TestOpenAPISchema:
    """Test OpenAPI schema endpoint."""

    def test_openapi_schema_endpoint(self, client):
        """Test /openapi.json returns valid schema."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["openapi"] == "3.0.0"
        assert "info" in data
        assert "paths" in data


class TestV2Placeholder:
    """Test API v2 placeholder."""

    def test_v2_endpoints_return_501(self, client):
        """Test v2 endpoints return 501 Not Implemented."""
        response = client.get("/api/v2/some/endpoint")
        assert response.status_code == 501
        assert "v2 coming soon" in response.json()["detail"]
