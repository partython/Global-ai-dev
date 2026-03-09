"""
Priya Global E2E Tests Configuration

Provides fixtures for End-to-End testing via httpx.AsyncClient:
- API base URL and authentication
- Test user accounts and tokens
- Test data creation and cleanup
- AsyncClient fixtures for making HTTP requests
- Multi-tenant test setup

Usage:
    async def test_something(async_client, test_auth_headers, test_tenant):
        response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={"channel": "whatsapp", "phone": "+919876543210"}
        )
        assert response.status_code == 201
"""

import asyncio
import json
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import jwt
import pytest

# Path setup
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# Environment setup for E2E tests
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:9000")
JWT_SECRET = os.environ.get("JWT_SECRET_KEY", secrets.token_urlsafe(32))
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")


# ============================================================
# JWT Token Management
# ============================================================


def create_auth_token(
    user_id: str = "e2e-user-001",
    tenant_id: str = "e2e-tenant-001",
    role: str = "admin",
    email: str = "admin@test.local",
    expires_in_hours: int = 24,
) -> str:
    """Create a valid JWT token for E2E testing."""
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": email,
        "permissions": ["read", "write", "admin"],
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        "iss": "priya-auth",
        "aud": "priya-api",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ============================================================
# HTTP Client Fixtures
# ============================================================


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an async HTTP client for API testing."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture
async def async_client_with_auth(
    async_client: httpx.AsyncClient,
    test_auth_headers: Dict[str, str],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an async HTTP client with default auth headers."""
    async_client.headers.update(test_auth_headers)
    yield async_client


# ============================================================
# Authentication Fixtures
# ============================================================


@pytest.fixture
def test_tenant_id() -> str:
    """Test tenant ID."""
    return f"e2e-tenant-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_user_id() -> str:
    """Test user ID."""
    return f"e2e-user-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_user_token(test_user_id: str, test_tenant_id: str) -> str:
    """Valid JWT token for test user."""
    return create_auth_token(
        user_id=test_user_id,
        tenant_id=test_tenant_id,
        role="admin",
    )


@pytest.fixture
def test_auth_headers(test_user_token: str) -> Dict[str, str]:
    """Auth headers with valid token."""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def test_agent_headers(test_tenant_id: str) -> Dict[str, str]:
    """Auth headers for agent role."""
    token = create_auth_token(
        user_id=f"agent-{uuid.uuid4().hex[:8]}",
        tenant_id=test_tenant_id,
        role="agent",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_viewer_headers(test_tenant_id: str) -> Dict[str, str]:
    """Auth headers for viewer role."""
    token = create_auth_token(
        user_id=f"viewer-{uuid.uuid4().hex[:8]}",
        tenant_id=test_tenant_id,
        role="viewer",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def expired_token_headers() -> Dict[str, str]:
    """Auth headers with expired token."""
    payload = {
        "sub": "expired-user",
        "tenant_id": "e2e-tenant-001",
        "role": "admin",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tampered_token_headers() -> Dict[str, str]:
    """Headers with tampered JWT (invalid signature)."""
    payload = {
        "sub": "attacker",
        "tenant_id": "e2e-tenant-999",
        "role": "admin",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_tenant_headers(test_tenant_id: str) -> Dict[str, str]:
    """Headers for a different tenant (cross-tenant isolation test)."""
    other_tenant = f"other-tenant-{uuid.uuid4().hex[:8]}"
    token = create_auth_token(
        user_id=f"user-{uuid.uuid4().hex[:8]}",
        tenant_id=other_tenant,
        role="admin",
    )
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# Test Data Fixtures
# ============================================================


@pytest.fixture
def test_tenant(test_tenant_id: str) -> Dict:
    """Test tenant data."""
    return {
        "id": test_tenant_id,
        "business_name": "E2E Test Business",
        "plan": "enterprise",
        "country": "IN",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "status": "active",
    }


@pytest.fixture
def test_user(test_user_id: str, test_tenant_id: str) -> Dict:
    """Test user data."""
    return {
        "id": test_user_id,
        "tenant_id": test_tenant_id,
        "email": f"{test_user_id}@test.local",
        "name": "E2E Test User",
        "role": "admin",
        "is_active": True,
    }


@pytest.fixture
def test_agent(test_tenant_id: str) -> Dict:
    """Test agent data."""
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    return {
        "id": agent_id,
        "tenant_id": test_tenant_id,
        "email": f"{agent_id}@test.local",
        "name": "E2E Test Agent",
        "role": "agent",
        "is_active": True,
    }


@pytest.fixture
def test_conversation_payload() -> Dict:
    """Test conversation creation payload."""
    return {
        "channel": "whatsapp",
        "customer_name": "Test Customer",
        "customer_phone": "+919876543210",
        "initial_message": "Hello, I need help with my order",
        "metadata": {
            "source": "e2e_test",
            "region": "IN",
        },
    }


@pytest.fixture
def test_message_payload() -> Dict:
    """Test message payload."""
    return {
        "content": "This is a test message for E2E testing",
        "type": "text",
        "metadata": {
            "e2e_test": True,
        },
    }


@pytest.fixture
def test_document_payload() -> Dict:
    """Test document upload payload."""
    return {
        "title": "Test Knowledge Base Document",
        "content": "This is test content for knowledge base testing. " * 100,
        "document_type": "product_guide",
        "tags": ["test", "e2e"],
    }


@pytest.fixture
def test_subscription_payload() -> Dict:
    """Test subscription update payload."""
    return {
        "plan": "professional",
        "billing_cycle": "monthly",
        "auto_renew": True,
    }


# ============================================================
# Cleanup Fixtures
# ============================================================


@pytest.fixture
async def cleanup_conversations(async_client: httpx.AsyncClient, test_auth_headers: Dict[str, str]):
    """Fixture to cleanup created conversations after test."""
    created_ids = []

    def register_for_cleanup(conversation_id: str):
        created_ids.append(conversation_id)

    yield register_for_cleanup

    # Cleanup
    for conv_id in created_ids:
        try:
            await async_client.delete(
                f"/api/v1/conversations/{conv_id}",
                headers=test_auth_headers,
            )
        except Exception as e:
            print(f"Warning: Failed to cleanup conversation {conv_id}: {e}")


@pytest.fixture
async def cleanup_documents(async_client: httpx.AsyncClient, test_auth_headers: Dict[str, str]):
    """Fixture to cleanup created documents after test."""
    created_ids = []

    def register_for_cleanup(document_id: str):
        created_ids.append(document_id)

    yield register_for_cleanup

    # Cleanup
    for doc_id in created_ids:
        try:
            await async_client.delete(
                f"/api/v1/knowledge-base/documents/{doc_id}",
                headers=test_auth_headers,
            )
        except Exception as e:
            print(f"Warning: Failed to cleanup document {doc_id}: {e}")


@pytest.fixture
async def cleanup_users(async_client: httpx.AsyncClient, test_auth_headers: Dict[str, str]):
    """Fixture to cleanup created users after test."""
    created_ids = []

    def register_for_cleanup(user_id: str):
        created_ids.append(user_id)

    yield register_for_cleanup

    # Cleanup
    for user_id in created_ids:
        try:
            await async_client.delete(
                f"/api/v1/users/{user_id}",
                headers=test_auth_headers,
            )
        except Exception as e:
            print(f"Warning: Failed to cleanup user {user_id}: {e}")


# ============================================================
# Utility Fixtures
# ============================================================


@pytest.fixture
def assert_valid_json_response():
    """Helper to assert valid JSON response."""
    def _assert(response: httpx.Response) -> Dict:
        assert response.headers.get("content-type", "").startswith("application/json"), \
            f"Expected JSON response, got {response.headers.get('content-type')}"
        return response.json()
    return _assert


@pytest.fixture
def assert_status_code():
    """Helper to assert specific HTTP status codes."""
    def _assert(response: httpx.Response, expected: int) -> httpx.Response:
        assert response.status_code == expected, \
            f"Expected status {expected}, got {response.status_code}. Body: {response.text}"
        return response
    return _assert
