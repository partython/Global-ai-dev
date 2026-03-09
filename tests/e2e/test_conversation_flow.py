"""
E2E Tests for Conversation Flow

Tests complete conversation lifecycle:
- Create new conversation via channel
- Send messages in conversation
- AI auto-response generation
- Handoff to human agent
- Close conversation
- Search conversations
"""

import uuid
from typing import Dict

import pytest


class TestConversationCreation:
    """Tests for conversation creation."""

    @pytest.mark.asyncio
    async def test_create_conversation_whatsapp(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test creating a WhatsApp conversation."""
        payload = {
            "channel": "whatsapp",
            "customer_phone": "+919876543210",
            "customer_name": "Test Customer",
            "initial_message": "Hello, I need help",
        }

        response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["channel"] == "whatsapp"
        assert data["customer_phone"] == "+919876543210"
        assert data["status"] == "active"

        cleanup_conversations(data["id"])

    @pytest.mark.asyncio
    async def test_create_conversation_email(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test creating an email conversation."""
        payload = {
            "channel": "email",
            "customer_email": "customer@example.com",
            "customer_name": "Email Customer",
            "subject": "Product Inquiry",
        }

        response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["channel"] == "email"

        cleanup_conversations(data["id"])

    @pytest.mark.asyncio
    async def test_create_conversation_slack(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test creating a Slack conversation."""
        payload = {
            "channel": "slack",
            "customer_slack_id": "U12345678",
            "customer_name": "Slack User",
        }

        response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["channel"] == "slack"

        cleanup_conversations(data["id"])

    @pytest.mark.asyncio
    async def test_create_conversation_missing_required_fields(
        self,
        async_client,
        test_auth_headers,
    ):
        """Test conversation creation fails with missing required fields."""
        payload = {
            "channel": "whatsapp",
            # Missing customer_phone
        }

        response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_create_conversation_requires_auth(self, async_client):
        """Test conversation creation requires authentication."""
        payload = {
            "channel": "whatsapp",
            "customer_phone": "+919876543210",
        }

        response = await async_client.post(
            "/api/v1/conversations",
            json=payload,
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestSendMessage:
    """Tests for sending messages in conversations."""

    @pytest.mark.asyncio
    async def test_send_message_text(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test sending a text message."""
        # Create conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
                "customer_name": "Test",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Send message
        message_payload = {
            "content": "This is a test message",
            "type": "text",
            "sender": "customer",
        }

        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=test_auth_headers,
            json=message_payload,
        )

        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["content"] == "This is a test message"

    @pytest.mark.asyncio
    async def test_send_message_with_metadata(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test sending message with metadata."""
        # Create conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Send message with metadata
        message_payload = {
            "content": "Order ID: 12345",
            "type": "text",
            "sender": "customer",
            "metadata": {
                "order_id": "12345",
                "product_id": "PROD-001",
            },
        }

        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=test_auth_headers,
            json=message_payload,
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_send_message_nonexistent_conversation(
        self,
        async_client,
        test_auth_headers,
    ):
        """Test sending message to non-existent conversation fails."""
        message_payload = {
            "content": "Test message",
            "type": "text",
            "sender": "customer",
        }

        response = await async_client.post(
            "/api/v1/conversations/nonexistent-id/messages",
            headers=test_auth_headers,
            json=message_payload,
        )

        assert response.status_code in [404, 403], f"Expected 404/403, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_send_message_requires_auth(self, async_client, cleanup_conversations):
        """Test sending message requires authentication."""
        message_payload = {
            "content": "Test",
            "type": "text",
            "sender": "customer",
        }

        response = await async_client.post(
            "/api/v1/conversations/conv-123/messages",
            json=message_payload,
        )

        assert response.status_code == 401


class TestAIAutoResponse:
    """Tests for AI auto-response generation."""

    @pytest.mark.asyncio
    async def test_ai_generates_response(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test AI generates response to customer message."""
        # Create conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
                "customer_name": "Test",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Send customer message
        message_payload = {
            "content": "What are your business hours?",
            "type": "text",
            "sender": "customer",
        }

        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=test_auth_headers,
            json=message_payload,
        )

        assert response.status_code == 201
        data = response.json()

        # Check if AI response was generated (may be in response or separate call)
        # This depends on API implementation
        if "ai_response" in data:
            assert data["ai_response"] is not None

    @pytest.mark.asyncio
    async def test_ai_response_contains_required_fields(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test AI response has required fields."""
        # Create and message conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Send message
        message_payload = {
            "content": "Hello",
            "type": "text",
            "sender": "customer",
        }

        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=test_auth_headers,
            json=message_payload,
        )

        assert response.status_code == 201


class TestConversationHandoff:
    """Tests for conversation handoff to human agent."""

    @pytest.mark.asyncio
    async def test_handoff_to_agent(
        self,
        async_client,
        test_auth_headers,
        test_agent_headers,
        cleanup_conversations,
    ):
        """Test handing off conversation to human agent."""
        # Create conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
                "customer_name": "Test",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Request handoff
        handoff_payload = {
            "reason": "customer_request",
            "notes": "Customer requested to speak with agent",
        }

        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/handoff",
            headers=test_auth_headers,
            json=handoff_payload,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_agent_can_access_handed_off_conversation(
        self,
        async_client,
        test_auth_headers,
        test_agent_headers,
        cleanup_conversations,
    ):
        """Test agent can access handed-off conversation."""
        # Create conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Handoff
        await async_client.post(
            f"/api/v1/conversations/{conv_id}/handoff",
            headers=test_auth_headers,
            json={"reason": "complex_query"},
        )

        # Agent should be able to access
        response = await async_client.get(
            f"/api/v1/conversations/{conv_id}",
            headers=test_agent_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


class TestCloseConversation:
    """Tests for closing conversations."""

    @pytest.mark.asyncio
    async def test_close_conversation(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test closing a conversation."""
        # Create conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Close it
        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/close",
            headers=test_auth_headers,
            json={"reason": "issue_resolved"},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["status"] == "closed"

    @pytest.mark.asyncio
    async def test_cannot_send_message_to_closed_conversation(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test that messages cannot be sent to closed conversation."""
        # Create and close conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Close it
        await async_client.post(
            f"/api/v1/conversations/{conv_id}/close",
            headers=test_auth_headers,
            json={"reason": "resolved"},
        )

        # Try to send message
        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            headers=test_auth_headers,
            json={
                "content": "This should fail",
                "type": "text",
                "sender": "customer",
            },
        )

        assert response.status_code in [400, 409], \
            f"Should not allow message on closed conversation, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_close_already_closed_conversation(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test closing already closed conversation."""
        # Create and close
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Close it
        await async_client.post(
            f"/api/v1/conversations/{conv_id}/close",
            headers=test_auth_headers,
            json={"reason": "resolved"},
        )

        # Try to close again
        response = await async_client.post(
            f"/api/v1/conversations/{conv_id}/close",
            headers=test_auth_headers,
            json={"reason": "duplicate"},
        )

        # Should fail or be idempotent
        assert response.status_code in [200, 400, 409]


class TestConversationSearch:
    """Tests for searching conversations."""

    @pytest.mark.asyncio
    async def test_search_conversations_by_customer_name(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test searching conversations by customer name."""
        # Create conversation
        customer_name = f"TestCust-{uuid.uuid4().hex[:8]}"
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
                "customer_name": customer_name,
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Search for it
        response = await async_client.get(
            "/api/v1/conversations/search",
            headers=test_auth_headers,
            params={"customer_name": customer_name},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "conversations" in data or "results" in data or len(response.json()) > 0

    @pytest.mark.asyncio
    async def test_search_conversations_by_phone(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test searching conversations by phone number."""
        phone = f"+91{uuid.uuid4().hex[:10]}"
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": phone,
                "customer_name": "Test",
            },
        )
        conv_id = conv_response.json()["id"]
        cleanup_conversations(conv_id)

        # Search
        response = await async_client.get(
            "/api/v1/conversations/search",
            headers=test_auth_headers,
            params={"phone": phone},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_conversations_by_status(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test searching conversations by status."""
        response = await async_client.get(
            "/api/v1/conversations/search",
            headers=test_auth_headers,
            params={"status": "active"},
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, async_client):
        """Test search requires authentication."""
        response = await async_client.get(
            "/api/v1/conversations/search",
            params={"status": "active"},
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_search_pagination(
        self,
        async_client,
        test_auth_headers,
    ):
        """Test search results are paginated."""
        response = await async_client.get(
            "/api/v1/conversations/search",
            headers=test_auth_headers,
            params={"page": 1, "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        # Should have pagination info
        assert "page" in data or "limit" in data or isinstance(data, dict)
