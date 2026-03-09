"""
Priya Global Platform — Root Test Configuration

Shared fixtures for all test modules. Provides:
- Mock database connections (tenant-scoped + admin)
- Pre-signed JWT tokens for auth testing
- Redis mock client
- Kafka mock producer/consumer
- Multi-tenant test data factories
- International market test data (currencies, timezones, locales)

Usage:
    def test_something(auth_headers, mock_db, tenant_factory):
        tenant = tenant_factory(plan="enterprise", country="IN")
        response = client.get("/api/v1/data", headers=auth_headers)
"""

import asyncio
import json
import os
import secrets as _secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

# ─── Path Setup ───
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ─── Environment for testing ───
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://priya:test@localhost:5432/priya_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("SENTRY_ENABLED", "false")
os.environ.setdefault("JWT_SECRET_KEY", _secrets.token_urlsafe(32))
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("LOG_LEVEL", "WARNING")


# ============================================================
# JWT Token Fixtures
# ============================================================

JWT_SECRET = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")


def create_test_token(
    user_id: str = "test-user-001",
    tenant_id: str = "test-tenant-001",
    role: str = "admin",
    plan: str = "enterprise",
    permissions: list = None,
    expires_delta: timedelta = timedelta(hours=1),
) -> str:
    """Create a signed JWT token for testing."""
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "plan": plan,
        "permissions": permissions or ["read", "write", "admin"],
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iss": "priya-auth-test",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def test_token():
    """Default admin token."""
    return create_test_token()


@pytest.fixture
def auth_headers():
    """Authorization headers with admin token."""
    return {"Authorization": f"Bearer {create_test_token()}"}


@pytest.fixture
def viewer_headers():
    """Authorization headers with viewer role."""
    return {
        "Authorization": f"Bearer {create_test_token(role='viewer', permissions=['read'])}"
    }


@pytest.fixture
def agent_headers():
    """Authorization headers with agent role."""
    return {
        "Authorization": f"Bearer {create_test_token(role='agent', permissions=['read', 'write'])}"
    }


@pytest.fixture
def expired_headers():
    """Expired token headers."""
    return {
        "Authorization": f"Bearer {create_test_token(expires_delta=timedelta(hours=-1))}"
    }


@pytest.fixture
def other_tenant_headers():
    """Headers for a different tenant (cross-tenant test)."""
    return {
        "Authorization": f"Bearer {create_test_token(tenant_id='other-tenant-999', user_id='other-user-999')}"
    }


# ============================================================
# Database Fixtures
# ============================================================


class MockDB:
    """Mock database that simulates tenant-scoped queries."""

    def __init__(self):
        self._data: Dict[str, list] = {}
        self.queries: list = []

    async def fetch_one(self, query: str, *args, **kwargs) -> Optional[Dict]:
        self.queries.append(("fetch_one", query, args))
        return self._data.get("fetch_one")

    async def fetch_all(self, query: str, *args, **kwargs) -> list:
        self.queries.append(("fetch_all", query, args))
        return self._data.get("fetch_all", [])

    async def execute(self, query: str, *args, **kwargs) -> Optional[str]:
        self.queries.append(("execute", query, args))
        return self._data.get("execute", str(uuid.uuid4()))

    def set_response(self, method: str, data: Any):
        self._data[method] = data

    def assert_tenant_scoped(self, tenant_id: str):
        """Verify all queries included tenant_id (RLS check)."""
        for method, query, args in self.queries:
            if "SET app.current_tenant" in query or tenant_id in str(args):
                continue
            if "tenant_id" not in query.lower() and method != "execute":
                raise AssertionError(
                    f"Query missing tenant_id scope: {query[:100]}..."
                )


@pytest.fixture
def mock_db():
    """Mock database connection."""
    return MockDB()


@pytest.fixture
def mock_admin_db():
    """Mock admin (cross-tenant) database connection."""
    db = MockDB()
    db._admin = True
    return db


# ============================================================
# Redis Fixtures
# ============================================================


class MockRedis:
    """Mock Redis client with tenant-scoped key support."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._ttls: Dict[str, int] = {}
        self.commands: list = []

    async def get(self, key: str) -> Optional[str]:
        self.commands.append(("GET", key))
        val = self._store.get(key)
        return json.dumps(val) if val is not None else None

    async def set(self, key: str, value: Any, ex: int = None):
        self.commands.append(("SET", key, value, ex))
        self._store[key] = json.loads(value) if isinstance(value, str) else value
        if ex:
            self._ttls[key] = ex

    async def delete(self, *keys):
        for key in keys:
            self.commands.append(("DEL", key))
            self._store.pop(key, None)

    async def incr(self, key: str) -> int:
        self.commands.append(("INCR", key))
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key: str, seconds: int):
        self.commands.append(("EXPIRE", key, seconds))
        self._ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self._ttls.get(key, -1)

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def ping(self) -> bool:
        return True

    def assert_tenant_scoped(self, tenant_id: str):
        """Verify all keys are tenant-scoped."""
        for cmd in self.commands:
            key = cmd[1] if len(cmd) > 1 else ""
            if isinstance(key, str) and key and f"t:{tenant_id}:" not in key:
                if not key.startswith("global:"):
                    raise AssertionError(
                        f"Redis key not tenant-scoped: {key}"
                    )


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return MockRedis()


# ============================================================
# Kafka Fixtures
# ============================================================


class MockKafkaProducer:
    """Mock Kafka producer."""

    def __init__(self):
        self.messages: list = []

    async def send(self, topic: str, value: Dict, key: str = None, partition_key: str = None):
        self.messages.append({
            "topic": topic,
            "key": key or partition_key,
            "value": value,
        })

    async def flush(self):
        pass

    def get_messages(self, topic: str = None) -> list:
        if topic:
            return [m for m in self.messages if m["topic"] == topic]
        return self.messages


class MockKafkaConsumer:
    """Mock Kafka consumer."""

    def __init__(self):
        self._messages: list = []
        self._position = 0

    def add_message(self, topic: str, value: Dict, key: str = None):
        self._messages.append({"topic": topic, "key": key, "value": value})

    async def __aiter__(self):
        for msg in self._messages[self._position:]:
            self._position += 1
            yield MagicMock(
                topic=msg["topic"],
                key=msg.get("key", "").encode() if msg.get("key") else None,
                value=json.dumps(msg["value"]).encode(),
            )


@pytest.fixture
def mock_kafka_producer():
    return MockKafkaProducer()


@pytest.fixture
def mock_kafka_consumer():
    return MockKafkaConsumer()


# ============================================================
# Tenant & Data Factories
# ============================================================

# International market data
MARKET_DATA = {
    "IN": {"currency": "INR", "timezone": "Asia/Kolkata", "locale": "en-IN", "phone_prefix": "+91", "tax_name": "GST"},
    "US": {"currency": "USD", "timezone": "America/New_York", "locale": "en-US", "phone_prefix": "+1", "tax_name": "Sales Tax"},
    "GB": {"currency": "GBP", "timezone": "Europe/London", "locale": "en-GB", "phone_prefix": "+44", "tax_name": "VAT"},
    "DE": {"currency": "EUR", "timezone": "Europe/Berlin", "locale": "de-DE", "phone_prefix": "+49", "tax_name": "MwSt"},
    "JP": {"currency": "JPY", "timezone": "Asia/Tokyo", "locale": "ja-JP", "phone_prefix": "+81", "tax_name": "Consumption Tax"},
    "BR": {"currency": "BRL", "timezone": "America/Sao_Paulo", "locale": "pt-BR", "phone_prefix": "+55", "tax_name": "ICMS"},
    "AE": {"currency": "AED", "timezone": "Asia/Dubai", "locale": "ar-AE", "phone_prefix": "+971", "tax_name": "VAT"},
    "SG": {"currency": "SGD", "timezone": "Asia/Singapore", "locale": "en-SG", "phone_prefix": "+65", "tax_name": "GST"},
    "AU": {"currency": "AUD", "timezone": "Australia/Sydney", "locale": "en-AU", "phone_prefix": "+61", "tax_name": "GST"},
    "CA": {"currency": "CAD", "timezone": "America/Toronto", "locale": "en-CA", "phone_prefix": "+1", "tax_name": "HST"},
    "FR": {"currency": "EUR", "timezone": "Europe/Paris", "locale": "fr-FR", "phone_prefix": "+33", "tax_name": "TVA"},
    "SA": {"currency": "SAR", "timezone": "Asia/Riyadh", "locale": "ar-SA", "phone_prefix": "+966", "tax_name": "VAT"},
}

PLAN_LIMITS = {
    "free": {"max_conversations": 100, "max_channels": 1, "max_agents": 1, "ai_messages": 500},
    "starter": {"max_conversations": 1000, "max_channels": 3, "max_agents": 5, "ai_messages": 5000},
    "professional": {"max_conversations": 10000, "max_channels": 7, "max_agents": 25, "ai_messages": 50000},
    "enterprise": {"max_conversations": -1, "max_channels": -1, "max_agents": -1, "ai_messages": -1},
}


@pytest.fixture
def tenant_factory():
    """Factory for creating test tenant data."""

    def _create(
        tenant_id: str = None,
        business_name: str = "Test Business",
        plan: str = "enterprise",
        country: str = "IN",
        status: str = "active",
        industry: str = "technology",
    ) -> Dict:
        tid = tenant_id or f"tenant-{uuid.uuid4().hex[:8]}"
        market = MARKET_DATA.get(country, MARKET_DATA["US"])
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["enterprise"])
        return {
            "id": tid,
            "business_name": business_name,
            "plan": plan,
            "status": status,
            "country": country,
            "industry": industry,
            "currency": market["currency"],
            "timezone": market["timezone"],
            "locale": market["locale"],
            "phone_prefix": market["phone_prefix"],
            "tax_name": market["tax_name"],
            "limits": limits,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "onboarding_completed": True,
        }

    return _create


@pytest.fixture
def user_factory():
    """Factory for creating test user data."""

    def _create(
        user_id: str = None,
        tenant_id: str = "test-tenant-001",
        email: str = None,
        role: str = "admin",
    ) -> Dict:
        uid = user_id or f"user-{uuid.uuid4().hex[:8]}"
        return {
            "id": uid,
            "tenant_id": tenant_id,
            "email": email or f"{uid}@test.com",
            "role": role,
            "name": f"Test User {uid[:8]}",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    return _create


@pytest.fixture
def conversation_factory():
    """Factory for creating test conversation data."""

    def _create(
        tenant_id: str = "test-tenant-001",
        channel: str = "whatsapp",
        status: str = "active",
        customer_name: str = "Test Customer",
        customer_phone: str = "+919876543210",
    ) -> Dict:
        return {
            "id": f"conv-{uuid.uuid4().hex[:8]}",
            "tenant_id": tenant_id,
            "channel": channel,
            "status": status,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "messages": [],
            "assigned_agent": None,
            "ai_handled": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "sentiment_score": 0.75,
            "language": "en",
        }

    return _create


@pytest.fixture
def message_factory():
    """Factory for creating test message data."""

    def _create(
        conversation_id: str = "conv-test-001",
        sender: str = "customer",
        content: str = "Hello, I need help",
        channel: str = "whatsapp",
    ) -> Dict:
        return {
            "id": f"msg-{uuid.uuid4().hex[:8]}",
            "conversation_id": conversation_id,
            "sender": sender,
            "content": content,
            "channel": channel,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
        }

    return _create


# ============================================================
# Service Client Fixtures
# ============================================================


def make_service_client(service_module_path: str) -> TestClient:
    """Import a service's main module and return a TestClient."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("main", service_module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return TestClient(module.app)


# ============================================================
# Cleanup
# ============================================================


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment between tests."""
    yield
    # Cleanup if needed
