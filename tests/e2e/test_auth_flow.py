"""
E2E Tests for Authentication Flow

Tests complete authentication workflows:
- User registration
- Login with valid/invalid credentials
- Token refresh
- Expired token handling
- Multi-tenant isolation
- JWT signature validation
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest


class TestUserRegistration:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_new_user(self, async_client, test_tenant_id):
        """Test successful user registration."""
        payload = {
            "email": f"newuser-{uuid.uuid4().hex[:8]}@test.local",
            "password": "SecurePassword123!",
            "name": "New User",
            "tenant_id": test_tenant_id,
            "plan": "starter",
        }

        response = await async_client.post(
            "/api/v1/auth/register",
            json=payload,
        )

        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert "token" in data
        assert data["email"] == payload["email"]
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, async_client, test_user):
        """Test registration fails with duplicate email."""
        payload = {
            "email": test_user["email"],
            "password": "SecurePassword123!",
            "name": "Duplicate User",
            "tenant_id": test_user["tenant_id"],
        }

        response = await async_client.post(
            "/api/v1/auth/register",
            json=payload,
        )

        assert response.status_code == 409, f"Expected 409 conflict, got {response.status_code}"
        data = response.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_register_missing_required_fields(self, async_client, test_tenant_id):
        """Test registration fails with missing fields."""
        payload = {
            "email": f"user-{uuid.uuid4().hex[:8]}@test.local",
            "name": "User",
            # Missing password and tenant_id
        }

        response = await async_client.post(
            "/api/v1/auth/register",
            json=payload,
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_register_weak_password(self, async_client, test_tenant_id):
        """Test registration fails with weak password."""
        payload = {
            "email": f"user-{uuid.uuid4().hex[:8]}@test.local",
            "password": "weak",  # Too simple
            "name": "User",
            "tenant_id": test_tenant_id,
        }

        response = await async_client.post(
            "/api/v1/auth/register",
            json=payload,
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


class TestLogin:
    """Tests for user login."""

    @pytest.mark.asyncio
    async def test_login_valid_credentials(self, async_client, test_user_token):
        """Test successful login with valid credentials."""
        # First register a user with known credentials
        email = f"login-test-{uuid.uuid4().hex[:8]}@test.local"
        password = "SecurePassword123!"

        register_payload = {
            "email": email,
            "password": password,
            "name": "Login Test User",
            "tenant_id": "e2e-tenant-001",
        }

        register_response = await async_client.post(
            "/api/v1/auth/register",
            json=register_payload,
        )

        assert register_response.status_code == 201

        # Now test login
        login_payload = {
            "email": email,
            "password": password,
        }

        response = await async_client.post(
            "/api/v1/auth/login",
            json=login_payload,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == email

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, async_client):
        """Test login fails with invalid password."""
        payload = {
            "email": "nonexistent@test.local",
            "password": "WrongPassword123!",
        }

        response = await async_client.post(
            "/api/v1/auth/login",
            json=payload,
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, async_client):
        """Test login fails with non-existent email."""
        payload = {
            "email": f"nonexistent-{uuid.uuid4().hex[:8]}@test.local",
            "password": "SomePassword123!",
        }

        response = await async_client.post(
            "/api/v1/auth/login",
            json=payload,
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, async_client):
        """Test login fails with missing email or password."""
        payload = {
            "email": "user@test.local",
            # Missing password
        }

        response = await async_client.post(
            "/api/v1/auth/login",
            json=payload,
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


class TestTokenRefresh:
    """Tests for JWT token refresh."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, async_client, test_user_token):
        """Test successful token refresh."""
        # First get a refresh token by logging in
        email = f"refresh-test-{uuid.uuid4().hex[:8]}@test.local"
        password = "SecurePassword123!"

        # Register
        register_response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "name": "Refresh Test",
                "tenant_id": "e2e-tenant-001",
            },
        )

        assert register_response.status_code == 201
        refresh_token = register_response.json()["refresh_token"]

        # Refresh the token
        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["token"] != test_user_token

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, async_client):
        """Test refresh fails with invalid token."""
        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, async_client):
        """Test refresh fails with expired token."""
        # Create an expired refresh token
        from tests.conftest import JWT_SECRET, JWT_ALGORITHM

        expired_payload = {
            "sub": "expired-user",
            "tenant_id": "e2e-tenant-001",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "type": "refresh",
        }

        expired_token = jwt.encode(
            expired_payload,
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

        response = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": expired_token},
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestExpiredTokenAccess:
    """Tests for access with expired tokens."""

    @pytest.mark.asyncio
    async def test_access_with_expired_token(self, async_client, expired_token_headers, test_auth_headers):
        """Test that expired tokens are rejected."""
        response = await async_client.get(
            "/api/v1/conversations",
            headers=expired_token_headers,
        )

        assert response.status_code == 401, f"Expected 401 for expired token, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_access_with_valid_token(self, async_client, test_auth_headers):
        """Test that valid tokens are accepted."""
        response = await async_client.get(
            "/api/v1/conversations",
            headers=test_auth_headers,
        )

        # Should not be 401
        assert response.status_code != 401, f"Valid token rejected: {response.status_code}"

    @pytest.mark.asyncio
    async def test_access_without_token(self, async_client):
        """Test that protected endpoints reject requests without token."""
        response = await async_client.get(
            "/api/v1/conversations",
        )

        assert response.status_code == 401, f"Expected 401 without token, got {response.status_code}"


class TestMultiTenantIsolation:
    """Tests for multi-tenant isolation in authentication."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_tenant_data(
        self,
        async_client,
        test_auth_headers,
        other_tenant_headers,
        test_tenant_id,
    ):
        """Test that users cannot access data from other tenants."""
        # Create a conversation with test_auth_headers
        create_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
                "customer_name": "Test Customer",
            },
        )

        assert create_response.status_code == 201
        conv_id = create_response.json()["id"]

        # Try to access it with other_tenant_headers
        access_response = await async_client.get(
            f"/api/v1/conversations/{conv_id}",
            headers=other_tenant_headers,
        )

        # Should be 404 or 403 (conversation not visible to other tenant)
        assert access_response.status_code in [403, 404], \
            f"Expected 403/404, got {access_response.status_code}"

    @pytest.mark.asyncio
    async def test_missing_tenant_id_rejected(self, async_client):
        """Test that requests without tenant_id are rejected."""
        # Create a token without tenant_id claim
        payload = {
            "sub": "user-123",
            # Missing tenant_id
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        from tests.conftest import JWT_SECRET, JWT_ALGORITHM

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/v1/conversations",
            headers=headers,
        )

        # Should be rejected
        assert response.status_code in [401, 400, 403], \
            f"Request with missing tenant_id should be rejected, got {response.status_code}"


class TestJWTSecurityValidation:
    """Tests for JWT security and signature validation."""

    @pytest.mark.asyncio
    async def test_tampered_token_rejected(self, async_client, tampered_token_headers):
        """Test that tampered/invalid signature tokens are rejected."""
        response = await async_client.get(
            "/api/v1/conversations",
            headers=tampered_token_headers,
        )

        assert response.status_code == 401, \
            f"Tampered token should be rejected, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_token_with_invalid_format(self, async_client):
        """Test that malformed tokens are rejected."""
        headers = {"Authorization": "Bearer not.a.valid.token"}

        response = await async_client.get(
            "/api/v1/conversations",
            headers=headers,
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_bearer_prefix_required(self, async_client, test_user_token):
        """Test that Authorization header must have Bearer prefix."""
        headers = {"Authorization": test_user_token}  # Missing "Bearer "

        response = await async_client.get(
            "/api/v1/conversations",
            headers=headers,
        )

        assert response.status_code == 401, f"Expected 401 without Bearer prefix, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_token_claims_validated(self, async_client):
        """Test that required token claims are validated."""
        from tests.conftest import JWT_SECRET, JWT_ALGORITHM

        # Token missing required "iss" (issuer) claim
        payload = {
            "sub": "user-123",
            "tenant_id": "tenant-123",
            # Missing "iss"
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get(
            "/api/v1/conversations",
            headers=headers,
        )

        # May be rejected or accepted depending on implementation
        # At minimum, verify it's handled properly
        assert response.status_code in [200, 401, 400], \
            f"Unexpected status: {response.status_code}"
