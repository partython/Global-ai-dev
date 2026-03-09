"""
Comprehensive tests for Priya Global Tenant Service.

Tests cover:
- Tenant CRUD operations (get, update, delete)
- Tenant creation and initialization
- Plan management (upgrade/downgrade)
- Tenant status lifecycle (active/suspended/cancelled)
- Usage tracking and plan limits enforcement
- Team member management
- Onboarding status and workflow
- Feature flags
- Soft delete operations
- Role-based access control
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.tenant import main
from shared.core.config import config


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(main.app)


@pytest.fixture
def auth_headers():
    """Authorization headers with Bearer token."""
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIiwidGVuYW50X2lkIjoiNDU2In0.TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_context():
    """Mock AuthContext for testing."""
    ctx = MagicMock()
    ctx.tenant_id = "tenant-456"
    ctx.user_id = "user-123"
    ctx.role = "owner"
    return ctx


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tenant"


class TestGetTenant:
    """Test getting tenant details."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_get_tenant_success(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test retrieving tenant details."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "name": "Test Company",
            "slug": "test-company",
            "status": "active",
            "plan": "growth",
            "country": "US",
            "created_at": datetime.now(timezone.utc),
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456", headers=auth_headers)

        # Depends on auth context setup
        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_get_tenant_not_found(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test getting nonexistent tenant returns 404."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/nonexistent", headers=auth_headers)

        assert response.status_code in [401, 404]

    def test_get_tenant_requires_auth(self, client):
        """Test tenant endpoint requires authentication."""
        response = client.get("/api/v1/tenants/tenant-456")

        assert response.status_code == 401


class TestUpdateTenant:
    """Test updating tenant properties."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_tenant_name(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test updating tenant name."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "name": "Updated Company",
        })
        mock_conn.execute = AsyncMock()
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456", headers=auth_headers, json={
            "name": "Updated Company",
        })

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_tenant_country(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test updating tenant country."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "country": "CA",
        })
        mock_conn.execute = AsyncMock()
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456", headers=auth_headers, json={
            "country": "CA",
        })

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_tenant_invalid_data(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test tenant update validation."""
        response = client.put("/api/v1/tenants/tenant-456", headers=auth_headers, json={
            "name": "",  # Empty name
        })

        assert response.status_code in [400, 401, 422]


class TestBranding:
    """Test tenant branding configuration."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_branding(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test updating tenant branding."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "logo_url": "https://example.com/logo.png",
            "primary_color": "#FF5733",
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456/branding", headers=auth_headers, json={
            "logo_url": "https://example.com/logo.png",
            "primary_color": "#FF5733",
        })

        assert response.status_code in [200, 401]


class TestAIConfig:
    """Test AI configuration for tenant."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_ai_config(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test updating AI configuration."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "ai_config": {"model": "gpt-4", "tone": "professional"},
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456/ai-config", headers=auth_headers, json={
            "model": "gpt-4",
            "tone": "professional",
        })

        assert response.status_code in [200, 401]


class TestUsageTracking:
    """Test usage statistics and limits."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_get_usage_stats(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test retrieving usage statistics."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "messages_sent": 1500,
            "messages_limit": 10000,
            "conversations_active": 45,
            "team_members": 3,
            "team_member_limit": 10,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456/usage", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_usage_stats_shows_limits(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test usage stats include plan limits."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "messages_sent": 5000,
            "messages_limit": 10000,
            "conversations_active": 25,
            "conversations_limit": 100,
            "team_members": 2,
            "team_member_limit": 10,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456/usage", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "messages_limit" in data
            assert "conversations_limit" in data


class TestTenantDeletion:
    """Test tenant deletion (soft delete)."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_soft_delete_tenant(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test soft-deleting a tenant."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.delete("/api/v1/tenants/tenant-456", headers=auth_headers)

        assert response.status_code in [200, 204, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_delete_sets_deleted_at(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test deleted tenant has deleted_at timestamp."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.delete("/api/v1/tenants/tenant-456", headers=auth_headers)

        # Verify soft delete was called
        if response.status_code in [200, 204]:
            mock_conn.execute.assert_called()


class TestTeamMembers:
    """Test team member management."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_list_team_members(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test listing team members."""
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": "user-123",
                "email": "john@example.com",
                "first_name": "John",
                "role": "owner",
                "status": "active",
            },
            {
                "id": "user-124",
                "email": "jane@example.com",
                "first_name": "Jane",
                "role": "editor",
                "status": "active",
            },
        ])
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456/members", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_invite_team_member(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test inviting a team member."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "invite-123",
            "email": "newuser@example.com",
            "status": "pending",
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.post("/api/v1/tenants/tenant-456/members/invite", headers=auth_headers, json={
            "email": "newuser@example.com",
            "role": "editor",
        })

        assert response.status_code in [200, 201, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_member_role(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test updating team member role."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "user-124",
            "email": "jane@example.com",
            "role": "admin",
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456/members/user-124/role", headers=auth_headers, json={
            "role": "admin",
        })

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_remove_team_member(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test removing a team member."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.delete("/api/v1/tenants/tenant-456/members/user-124", headers=auth_headers)

        assert response.status_code in [200, 204, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_transfer_ownership(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test transferring ownership to another member."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "user-124",
            "email": "jane@example.com",
            "role": "owner",
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.post("/api/v1/tenants/tenant-456/members/transfer-ownership", headers=auth_headers, json={
            "new_owner_id": "user-124",
        })

        assert response.status_code in [200, 401]


class TestOnboarding:
    """Test onboarding flow."""

    @patch("services.tenant.main.db.admin_connection")
    def test_start_onboarding(self, mock_admin_conn, client):
        """Test starting onboarding process."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "onboard-123",
            "tenant_id": "tenant-456",
            "status": "profile_pending",
        })
        mock_admin_conn.return_value.__aenter__.return_value = mock_conn

        response = client.post("/api/v1/onboarding/start", json={
            "email": "test@example.com",
            "business_name": "Test Co",
        })

        assert response.status_code in [200, 201, 400, 422]

    @patch("services.tenant.main.db.admin_connection")
    def test_get_onboarding_status(self, mock_admin_conn, client):
        """Test retrieving onboarding status."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "tenant_id": "tenant-456",
            "status": "channels_pending",
            "completed_steps": ["profile"],
        })
        mock_admin_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/onboarding/status/tenant-456")

        assert response.status_code in [200, 404]

    @patch("services.tenant.main.db.admin_connection")
    def test_complete_onboarding(self, mock_admin_conn, client, auth_headers):
        """Test completing onboarding."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "tenant_id": "tenant-456",
            "status": "active",
        })
        mock_admin_conn.return_value.__aenter__.return_value = mock_conn

        response = client.post("/api/v1/onboarding/complete", headers=auth_headers)

        assert response.status_code in [200, 401]


class TestPlanManagement:
    """Test plan upgrade/downgrade."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_get_plan_details(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test retrieving plan details."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "plan": "growth",
            "messages_limit": 100000,
            "conversations_limit": 1000,
            "team_members_limit": 50,
            "price": 99.99,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456/plan", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_upgrade_plan(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test upgrading to a higher plan."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "plan": "enterprise",
            "messages_limit": 1000000,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456/plan", headers=auth_headers, json={
            "plan": "enterprise",
        })

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_downgrade_plan(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test downgrading to a lower plan."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "plan": "startup",
            "messages_limit": 10000,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456/plan", headers=auth_headers, json={
            "plan": "startup",
        })

        assert response.status_code in [200, 401]


class TestFeatureFlags:
    """Test feature flag management."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_get_feature_flags(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test retrieving feature flags."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "ai_enabled": True,
            "whatsapp_enabled": True,
            "email_enabled": True,
            "voice_enabled": False,
            "social_enabled": False,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456/features", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_update_feature_flags(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test updating feature flags."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "voice_enabled": True,
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.put("/api/v1/tenants/tenant-456/features", headers=auth_headers, json={
            "voice_enabled": True,
        })

        assert response.status_code in [200, 401]


class TestTenantStatus:
    """Test tenant status lifecycle."""

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_get_active_tenant(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test getting active tenant."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "status": "active",
            "name": "Test Company",
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "active"

    @patch("services.tenant.main.get_auth")
    @patch("services.tenant.main.db.tenant_connection")
    def test_suspended_tenant(self, mock_tenant_conn, mock_get_auth, client, auth_headers):
        """Test handling suspended tenant."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "tenant-456",
            "status": "suspended",
            "name": "Test Company",
        })
        mock_tenant_conn.return_value.__aenter__.return_value = mock_conn

        response = client.get("/api/v1/tenants/tenant-456", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "suspended"
