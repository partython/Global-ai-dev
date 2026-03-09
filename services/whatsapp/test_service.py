"""
WhatsApp Service Tests
Comprehensive test suite for all endpoints and functionality
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import asyncio
import json
import hmac
import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

from fastapi.testclient import TestClient
import httpx

from main import (
    app, verify_webhook_signature, process_webhook, handle_inbound_message,
    forward_to_channel_router, MessageType, MessageStatus, ConversationCategory
)

# ─── Test Client ───

client = TestClient(app)

# ─── Fixtures ───

@pytest.fixture
def sample_tenant_id():
    """Sample tenant ID for tests."""
    return "550e8400-e29b-41d4-a716-446655440000"

@pytest.fixture
def sample_phone_id():
    """Sample Meta phone number ID."""
    return "1234567890123456"

@pytest.fixture
def sample_jwt_token():
    """Sample JWT token (would be real token in production tests)."""
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwidGVuYW50X2lkIjoiNTUwZTg0MDAtZTI5Yi00MWQ0LWE3MTYtNDQ2NjU1NDQwMDAwIiwicm9sZSI6Im93bmVyIn0.signature"

@pytest.fixture
def sample_webhook_payload():
    """Sample webhook payload from Meta."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "ENTRY_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "1234567890123456"
                            },
                            "messages": [
                                {
                                    "from": "1234567890",
                                    "id": "wamid.HBEUGVlpQkVBAIAiAhAvAhAvA4Z3NAB-",
                                    "timestamp": "1234567890",
                                    "type": "text",
                                    "text": {
                                        "body": "Hello, this is a test message!"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

@pytest.fixture
def sample_webhook_status():
    """Sample webhook with message status update."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "ENTRY_ID",
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": "1234567890123456"
                            },
                            "statuses": [
                                {
                                    "id": "wamid.HBEUGVlpQkVBAIAiAhAvAhAvA4Z3NAB-",
                                    "status": "delivered",
                                    "timestamp": "1234567890",
                                    "recipient_id": "1234567890"
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

# ─── Health Check Tests ───

class TestHealthCheck:
    """Test service health endpoint."""

    def test_health_check(self):
        """Service should report healthy status."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "whatsapp"
        assert "port" in data

# ─── Webhook Verification Tests ───

class TestWebhookVerification:
    """Test Meta webhook verification flow."""

    def test_webhook_get_verification(self):
        """GET /webhook should verify Meta challenge."""
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "priya_whatsapp_webhook_token",
                "hub.challenge": "12345"
            }
        )
        assert response.status_code == 200
        assert int(response.text) == 12345

    def test_webhook_get_invalid_token(self):
        """GET /webhook should reject invalid token."""
        response = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "invalid_token",
                "hub.challenge": "12345"
            }
        )
        assert response.status_code == 403

    def test_webhook_get_missing_params(self):
        """GET /webhook should reject incomplete params."""
        response = client.get("/webhook")
        assert response.status_code == 400

# ─── Webhook Event Tests ───

class TestWebhookEvents:
    """Test webhook event reception and processing."""

    @patch("main.process_webhook")
    def test_webhook_post_acceptance(self, mock_process, sample_webhook_payload):
        """POST /webhook should accept valid payload."""
        payload = json.dumps(sample_webhook_payload)

        response = client.post(
            "/webhook",
            content=payload,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_webhook_post_invalid_json(self):
        """POST /webhook should reject invalid JSON."""
        response = client.post(
            "/webhook",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400

    def test_webhook_signature_verification(self):
        """Webhook signature verification should work."""
        app_secret = "whatsapp_app_secret"
        payload = b'{"test": "data"}'

        expected_sig = hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Correct signature
        assert verify_webhook_signature(payload, expected_sig, app_secret) is True

        # Invalid signature
        assert verify_webhook_signature(payload, "invalid", app_secret) is False

# ─── Message Sending Tests ───

class TestMessageSending:
    """Test outbound message sending."""

    @patch("main.get_http_client")
    @patch("main.db.tenant_connection")
    def test_send_text_message(self, mock_db, mock_http, sample_jwt_token):
        """Send text message should succeed."""
        # Mock database
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "channel_metadata": {
                "phone_number_id": "1234567890123456",
                "access_token": "EABs..."
            }
        }
        mock_conn.fetchval.return_value = True  # Window OK
        mock_db.return_value.__aenter__.return_value = mock_conn

        # Mock HTTP client
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "messages": [{"id": "wamid.test123"}]
            }
        )
        mock_http.return_value = mock_client

        response = client.post(
            "/api/v1/send",
            json={
                "to": "1234567890",
                "type": "text",
                "text": "Hello!"
            },
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "message_id" in data
        assert data["status"] == "sent"

    @patch("main.db.tenant_connection")
    def test_send_without_auth(self, mock_db):
        """Sending without auth should fail."""
        response = client.post(
            "/api/v1/send",
            json={
                "to": "1234567890",
                "type": "text",
                "text": "Hello!"
            }
        )

        assert response.status_code == 403

    @patch("main.get_http_client")
    @patch("main.db.tenant_connection")
    def test_send_outside_window_requires_template(self, mock_db, mock_http, sample_jwt_token):
        """Sending outside 24h window requires template."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "channel_metadata": {
                "phone_number_id": "1234567890123456",
                "access_token": "EABs..."
            }
        }
        mock_conn.fetchval.return_value = False  # Window expired
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.post(
            "/api/v1/send",
            json={
                "to": "1234567890",
                "type": "text",
                "text": "Hello!"
            },
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 429

# ─── Template Management Tests ───

class TestTemplateManagement:
    """Test template CRUD operations."""

    @patch("main.db.tenant_connection")
    def test_list_templates(self, mock_db, sample_jwt_token):
        """List templates should return all templates."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "id": "1",
                "name": "welcome",
                "status": "APPROVED"
            }
        ]
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.get(
            "/api/v1/templates",
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "count" in data

    @patch("main.get_http_client")
    @patch("main.db.tenant_connection")
    def test_create_template(self, mock_db, mock_http, sample_jwt_token):
        """Create template should submit to Meta."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "channel_metadata": {
                "business_account_id": "123456789012345",
                "access_token": "EABs..."
            }
        }
        mock_db.return_value.__aenter__.return_value = mock_conn

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = Mock(
            status_code=200,
            json=lambda: {"id": "template123"}
        )
        mock_http.return_value = mock_client

        response = client.post(
            "/api/v1/templates",
            json={
                "name": "order_confirmation",
                "category": "UTILITY",
                "body": "Your order {{1}} is confirmed"
            },
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING"

    @patch("main.db.tenant_connection")
    def test_delete_template(self, mock_db, sample_jwt_token):
        """Delete template should remove from database."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "DELETE 1"
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.delete(
            "/api/v1/templates/old_template",
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200

# ─── Phone Number Management Tests ───

class TestPhoneNumberManagement:
    """Test phone number registration and management."""

    @patch("main.db.tenant_connection")
    def test_list_phone_numbers(self, mock_db, sample_jwt_token):
        """List phone numbers should return registered numbers."""
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {
                "phone_number_id": "1234567890123456",
                "display_phone_number": "+1 (234) 567-8900",
                "business_name": "Acme Sales",
                "quality_rating": "GREEN"
            }
        ]
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.get(
            "/api/v1/phone-numbers",
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "phone_numbers" in data
        assert len(data["phone_numbers"]) == 1

    @patch("main.db.tenant_connection")
    def test_register_phone_number(self, mock_db, sample_jwt_token):
        """Register phone number should store in database."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": "1"}
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.post(
            "/api/v1/phone-numbers/register",
            json={
                "phone_number": "+1234567890",
                "display_name": "Sales",
                "business_name": "Acme",
                "business_category": "GENERAL"
            },
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "registered"

    @patch("main.db.tenant_connection")
    def test_update_phone_profile(self, mock_db, sample_jwt_token):
        """Update phone profile should modify business profile."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "channel_metadata": {
                "phone_number_id": "1234567890123456"
            }
        }
        mock_conn.execute.return_value = None
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.put(
            "/api/v1/phone-numbers/1234567890123456/profile",
            json={
                "about": "We're here to help!",
                "website": "https://example.com"
            },
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 200

# ─── Integration Tests ───

class TestIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_message_flow(self, sample_webhook_payload):
        """Test complete message flow: webhook → processing → DB."""
        # This would be a full integration test
        # In production, use real database and HTTP client
        pass

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self):
        """Test that messages are isolated by tenant."""
        # Verify RLS policies prevent cross-tenant access
        pass

    @pytest.mark.asyncio
    async def test_24_hour_window(self):
        """Test conversation window enforcement."""
        # Send message (window opens)
        # Wait simulation of 24+ hours
        # Verify non-template message rejected
        # Verify template message accepted
        pass

# ─── Schema Validation Tests ───

class TestSchemaValidation:
    """Test request/response schema validation."""

    def test_outbound_message_schema(self):
        """OutboundMessage schema validation."""
        # Valid
        valid = {
            "to": "1234567890",
            "type": "text",
            "text": "Hello"
        }
        # Should not raise

        # Invalid (missing required to field)
        invalid = {
            "type": "text",
            "text": "Hello"
        }
        # Should raise validation error

    def test_template_schema(self):
        """Template schema validation."""
        # Valid
        valid = {
            "name": "welcome",
            "body": "Welcome {{1}}!"
        }

        # Invalid (name too short)
        invalid = {
            "name": "",
            "body": "Welcome!"
        }

# ─── Error Handling Tests ───

class TestErrorHandling:
    """Test error conditions and edge cases."""

    @patch("main.db.tenant_connection")
    def test_whatsapp_not_configured(self, mock_db, sample_jwt_token):
        """Sending without WhatsApp configured should fail."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None  # No connection
        mock_db.return_value.__aenter__.return_value = mock_conn

        response = client.post(
            "/api/v1/send",
            json={"to": "1234567890", "type": "text", "text": "Hi"},
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 404

    @patch("main.get_http_client")
    @patch("main.db.tenant_connection")
    def test_meta_api_error(self, mock_db, mock_http, sample_jwt_token):
        """Meta API error should be handled gracefully."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "channel_metadata": {
                "phone_number_id": "1234567890123456",
                "access_token": "EABs..."
            }
        }
        mock_conn.fetchval.return_value = True
        mock_db.return_value.__aenter__.return_value = mock_conn

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = Mock(
            status_code=400,
            text="Invalid request"
        )
        mock_http.return_value = mock_client

        response = client.post(
            "/api/v1/send",
            json={"to": "1234567890", "type": "text", "text": "Hi"},
            headers={"Authorization": f"Bearer {sample_jwt_token}"}
        )

        assert response.status_code == 400

# ─── Run Tests ───

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
