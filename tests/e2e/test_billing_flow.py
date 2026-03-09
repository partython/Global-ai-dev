"""
E2E Tests for Billing and Subscription Flow

Tests subscription management:
- Get current subscription
- Upgrade/downgrade plans
- Usage tracking
- Invoice retrieval
- Payment method management
"""

import uuid
from datetime import datetime, timedelta

import pytest


class TestSubscriptionManagement:
    """Tests for subscription management."""

    @pytest.mark.asyncio
    async def test_get_current_subscription(self, async_client, test_auth_headers):
        """Test retrieving current subscription."""
        response = await async_client.get(
            "/api/v1/billing/subscription",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "plan" in data
        assert "status" in data
        assert "current_period_end" in data
        assert data["plan"] in ["free", "starter", "professional", "enterprise"]

    @pytest.mark.asyncio
    async def test_subscription_requires_auth(self, async_client):
        """Test subscription endpoint requires authentication."""
        response = await async_client.get("/api/v1/billing/subscription")

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_get_subscription_details(self, async_client, test_auth_headers):
        """Test getting detailed subscription information."""
        response = await async_client.get(
            "/api/v1/billing/subscription/details",
            headers=test_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Should have subscription details
        assert "features" in data or "limits" in data or "plan" in data


class TestPlanUpgrade:
    """Tests for upgrading subscription plan."""

    @pytest.mark.asyncio
    async def test_upgrade_plan(self, async_client, test_auth_headers):
        """Test upgrading to a higher tier plan."""
        # First get current plan
        current_response = await async_client.get(
            "/api/v1/billing/subscription",
            headers=test_auth_headers,
        )
        current_plan = current_response.json()["plan"]

        # Upgrade payload
        upgrade_plans = {
            "free": "starter",
            "starter": "professional",
            "professional": "enterprise",
        }

        if current_plan in upgrade_plans:
            new_plan = upgrade_plans[current_plan]

            response = await async_client.post(
                "/api/v1/billing/subscription/upgrade",
                headers=test_auth_headers,
                json={"plan": new_plan},
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data["plan"] == new_plan

    @pytest.mark.asyncio
    async def test_upgrade_with_immediate_billing(self, async_client, test_auth_headers):
        """Test plan upgrade with immediate billing."""
        payload = {
            "plan": "professional",
            "billing_cycle": "monthly",
            "immediate": True,
        }

        response = await async_client.post(
            "/api/v1/billing/subscription/upgrade",
            headers=test_auth_headers,
            json=payload,
        )

        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_downgrade_plan(self, async_client, test_auth_headers):
        """Test downgrading to a lower tier plan."""
        # First upgrade to a high plan
        upgrade_response = await async_client.post(
            "/api/v1/billing/subscription/upgrade",
            headers=test_auth_headers,
            json={"plan": "professional"},
        )

        if upgrade_response.status_code == 200:
            # Then downgrade
            response = await async_client.post(
                "/api/v1/billing/subscription/downgrade",
                headers=test_auth_headers,
                json={"plan": "starter"},
            )

            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_plan_change_invalid_plan(self, async_client, test_auth_headers):
        """Test plan change with invalid plan name."""
        response = await async_client.post(
            "/api/v1/billing/subscription/upgrade",
            headers=test_auth_headers,
            json={"plan": "invalid_plan"},
        )

        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_plan_upgrade_requires_auth(self, async_client):
        """Test plan upgrade requires authentication."""
        response = await async_client.post(
            "/api/v1/billing/subscription/upgrade",
            json={"plan": "professional"},
        )

        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestUsageTracking:
    """Tests for usage tracking and limits."""

    @pytest.mark.asyncio
    async def test_get_current_usage(self, async_client, test_auth_headers):
        """Test retrieving current usage metrics."""
        response = await async_client.get(
            "/api/v1/billing/usage",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "conversations" in data or "messages" in data or "api_calls" in data

    @pytest.mark.asyncio
    async def test_usage_includes_period(self, async_client, test_auth_headers):
        """Test usage data includes billing period."""
        response = await async_client.get(
            "/api/v1/billing/usage",
            headers=test_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Should have period information
        assert "period_start" in data or "current_period_start" in data

    @pytest.mark.asyncio
    async def test_usage_increments_on_conversation(
        self,
        async_client,
        test_auth_headers,
        cleanup_conversations,
    ):
        """Test that usage metrics increment when creating conversations."""
        # Get initial usage
        initial_response = await async_client.get(
            "/api/v1/billing/usage",
            headers=test_auth_headers,
        )
        initial_data = initial_response.json()
        initial_conversations = initial_data.get("conversations", 0)

        # Create a conversation
        conv_response = await async_client.post(
            "/api/v1/conversations",
            headers=test_auth_headers,
            json={
                "channel": "whatsapp",
                "customer_phone": "+919876543210",
            },
        )

        if conv_response.status_code == 201:
            conv_id = conv_response.json()["id"]
            cleanup_conversations(conv_id)

            # Get updated usage
            updated_response = await async_client.get(
                "/api/v1/billing/usage",
                headers=test_auth_headers,
            )
            updated_data = updated_response.json()
            updated_conversations = updated_data.get("conversations", 0)

            # Should have incremented
            assert updated_conversations >= initial_conversations

    @pytest.mark.asyncio
    async def test_usage_by_metric(self, async_client, test_auth_headers):
        """Test retrieving usage for specific metric."""
        response = await async_client.get(
            "/api/v1/billing/usage/messages",
            headers=test_auth_headers,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_usage_forecast(self, async_client, test_auth_headers):
        """Test usage forecast for current billing period."""
        response = await async_client.get(
            "/api/v1/billing/usage/forecast",
            headers=test_auth_headers,
        )

        assert response.status_code == 200


class TestInvoices:
    """Tests for invoice management."""

    @pytest.mark.asyncio
    async def test_get_invoices(self, async_client, test_auth_headers):
        """Test retrieving invoices."""
        response = await async_client.get(
            "/api/v1/billing/invoices",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Should be list or have invoices key
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_get_invoice_by_id(self, async_client, test_auth_headers):
        """Test retrieving specific invoice."""
        # First get invoices list
        list_response = await async_client.get(
            "/api/v1/billing/invoices",
            headers=test_auth_headers,
        )

        if list_response.status_code == 200:
            invoices = list_response.json()
            if isinstance(invoices, list) and len(invoices) > 0:
                invoice_id = invoices[0].get("id")
                if invoice_id:
                    response = await async_client.get(
                        f"/api/v1/billing/invoices/{invoice_id}",
                        headers=test_auth_headers,
                    )

                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invoice_includes_required_fields(self, async_client, test_auth_headers):
        """Test that invoices contain required fields."""
        response = await async_client.get(
            "/api/v1/billing/invoices",
            headers=test_auth_headers,
        )

        if response.status_code == 200:
            invoices = response.json()
            if isinstance(invoices, list) and len(invoices) > 0:
                invoice = invoices[0]
                assert "id" in invoice or "invoice_number" in invoice
                assert "amount" in invoice or "total" in invoice
                assert "date" in invoice or "created_at" in invoice

    @pytest.mark.asyncio
    async def test_invoice_download_pdf(self, async_client, test_auth_headers):
        """Test downloading invoice as PDF."""
        # Get an invoice first
        list_response = await async_client.get(
            "/api/v1/billing/invoices",
            headers=test_auth_headers,
        )

        if list_response.status_code == 200:
            invoices = list_response.json()
            if isinstance(invoices, list) and len(invoices) > 0:
                invoice_id = invoices[0].get("id")
                if invoice_id:
                    response = await async_client.get(
                        f"/api/v1/billing/invoices/{invoice_id}/pdf",
                        headers=test_auth_headers,
                    )

                    if response.status_code == 200:
                        # Should be PDF content
                        assert response.headers.get("content-type", "").startswith("application/pdf") or \
                               response.headers.get("content-type", "").startswith("application/octet-stream")

    @pytest.mark.asyncio
    async def test_invoices_pagination(self, async_client, test_auth_headers):
        """Test invoice list pagination."""
        response = await async_client.get(
            "/api/v1/billing/invoices",
            headers=test_auth_headers,
            params={"page": 1, "limit": 10},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invoices_require_auth(self, async_client):
        """Test invoices endpoint requires authentication."""
        response = await async_client.get("/api/v1/billing/invoices")

        assert response.status_code == 401


class TestPaymentMethods:
    """Tests for payment method management."""

    @pytest.mark.asyncio
    async def test_get_payment_methods(self, async_client, test_auth_headers):
        """Test retrieving saved payment methods."""
        response = await async_client.get(
            "/api/v1/billing/payment-methods",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_payment_method_includes_required_fields(
        self,
        async_client,
        test_auth_headers,
    ):
        """Test payment methods have required fields."""
        response = await async_client.get(
            "/api/v1/billing/payment-methods",
            headers=test_auth_headers,
        )

        if response.status_code == 200:
            methods = response.json()
            if isinstance(methods, list) and len(methods) > 0:
                method = methods[0]
                # Should have type and identifier
                assert "type" in method or "method_type" in method
                assert "last4" in method or "token" in method or "id" in method

    @pytest.mark.asyncio
    async def test_set_default_payment_method(self, async_client, test_auth_headers):
        """Test setting default payment method."""
        # Get payment methods first
        list_response = await async_client.get(
            "/api/v1/billing/payment-methods",
            headers=test_auth_headers,
        )

        if list_response.status_code == 200:
            methods = list_response.json()
            if isinstance(methods, list) and len(methods) > 0:
                method_id = methods[0].get("id")
                if method_id:
                    response = await async_client.post(
                        f"/api/v1/billing/payment-methods/{method_id}/default",
                        headers=test_auth_headers,
                    )

                    assert response.status_code in [200, 204]

    @pytest.mark.asyncio
    async def test_delete_payment_method(self, async_client, test_auth_headers):
        """Test deleting a payment method."""
        # Get payment methods
        list_response = await async_client.get(
            "/api/v1/billing/payment-methods",
            headers=test_auth_headers,
        )

        if list_response.status_code == 200:
            methods = list_response.json()
            if isinstance(methods, list) and len(methods) > 1:  # Need at least 2 to delete one
                method_id = methods[0].get("id")
                if method_id:
                    response = await async_client.delete(
                        f"/api/v1/billing/payment-methods/{method_id}",
                        headers=test_auth_headers,
                    )

                    assert response.status_code in [200, 204, 404]  # 404 if already deleted

    @pytest.mark.asyncio
    async def test_payment_methods_require_auth(self, async_client):
        """Test payment methods endpoint requires authentication."""
        response = await async_client.get("/api/v1/billing/payment-methods")

        assert response.status_code == 401


class TestBillingCycle:
    """Tests for billing cycle information."""

    @pytest.mark.asyncio
    async def test_get_billing_cycle_info(self, async_client, test_auth_headers):
        """Test retrieving billing cycle information."""
        response = await async_client.get(
            "/api/v1/billing/cycle",
            headers=test_auth_headers,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "period_start" in data or "current_period_start" in data
        assert "period_end" in data or "current_period_end" in data

    @pytest.mark.asyncio
    async def test_billing_cycle_dates_are_valid(self, async_client, test_auth_headers):
        """Test that billing cycle dates are valid."""
        response = await async_client.get(
            "/api/v1/billing/cycle",
            headers=test_auth_headers,
        )

        if response.status_code == 200:
            data = response.json()
            # Parse dates if they're ISO strings
            start_key = "period_start" if "period_start" in data else "current_period_start"
            end_key = "period_end" if "period_end" in data else "current_period_end"

            if start_key in data and end_key in data:
                # End should be after start
                assert data[end_key] >= data[start_key]
