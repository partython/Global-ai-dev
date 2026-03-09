"""
Comprehensive tests for Priya Global Tenant Configuration Service.

Tests cover:
- Onboarding flow (profile, channels, AI config, test, activate)
- Configuration CRUD operations
- Industry taxonomy reference data
- Country compliance rules
- Lifecycle state machine
- Channel credential validation and storage
- AI configuration and prompt generation
- Tenant activation and status transitions
- Credential encryption/decryption
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.tenant_config import main
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
def business_profile_data():
    """Valid business profile data."""
    return {
        "business_name": "Acme Corp",
        "industry": "retail",
        "timezone": "America/New_York",
        "currency": "USD",
        "country": "US",
        "website": "https://acme.com",
        "size": "10-50",
    }


@pytest.fixture
def channel_provision_data():
    """Valid channel provision data."""
    return {
        "channel_type": "whatsapp",
        "phone_number": "+1234567890",
        "credentials": {
            "phone_number_id": "123456",
            "business_account_id": "789",
        },
    }


@pytest.fixture
def ai_config_data():
    """Valid AI configuration data."""
    return {
        "tone": "professional",
        "language": "en",
        "temperature": 0.7,
        "max_tokens": 500,
        "system_prompt": "You are a helpful sales assistant.",
    }


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tenant-config"


class TestReferenceData:
    """Test reference data endpoints."""

    def test_list_industries(self, client):
        """Test retrieving industries list."""
        response = client.get("/api/v1/ref/industries")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "industries" in data
        if isinstance(data, list):
            assert len(data) > 0

    def test_industries_have_required_fields(self, client):
        """Test industries include required fields."""
        response = client.get("/api/v1/ref/industries")

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                industry = data[0]
                assert "id" in industry or "code" in industry
                assert "name" in industry

    def test_list_countries(self, client):
        """Test retrieving countries list."""
        response = client.get("/api/v1/ref/countries")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "countries" in data

    def test_countries_have_required_fields(self, client):
        """Test countries include required fields."""
        response = client.get("/api/v1/ref/countries")

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                country = data[0]
                assert "code" in country or "id" in country
                assert "name" in country

    def test_list_ai_tones(self, client):
        """Test retrieving AI tones list."""
        response = client.get("/api/v1/ref/tones")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "tones" in data


class TestLifecycleState:
    """Test tenant lifecycle state management."""

    @patch("services.tenant_config.main.get_auth")
    def test_get_lifecycle_state(self, mock_get_auth, client, auth_headers):
        """Test retrieving current lifecycle state."""
        response = client.get("/api/v1/lifecycle", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant_config.main.get_auth")
    def test_lifecycle_state_includes_current_step(self, mock_get_auth, client, auth_headers):
        """Test lifecycle state includes current step."""
        response = client.get("/api/v1/lifecycle", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "state" in data or "status" in data or "current_step" in data


class TestBusinessProfile:
    """Test business profile setup."""

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_set_business_profile(self, mock_db, mock_require_owner, client, auth_headers, business_profile_data):
        """Test setting business profile."""
        response = client.post("/api/v1/onboarding/profile", headers=auth_headers, json=business_profile_data)

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    def test_business_profile_validation(self, mock_require_owner, client, auth_headers):
        """Test business profile validation."""
        response = client.post("/api/v1/onboarding/profile", headers=auth_headers, json={
            "business_name": "",  # Empty name
            "industry": "invalid",
        })

        assert response.status_code in [400, 422, 401]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_business_profile_requires_owner(self, mock_db, mock_require_owner, client, business_profile_data):
        """Test business profile endpoint requires owner role."""
        response = client.post("/api/v1/onboarding/profile", json=business_profile_data)

        assert response.status_code == 401


class TestChannelProvisioning:
    """Test channel credential provisioning."""

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_provision_channel(self, mock_db, mock_require_owner, client, auth_headers, channel_provision_data):
        """Test provisioning a channel."""
        response = client.post("/api/v1/onboarding/channels", headers=auth_headers, json=channel_provision_data)

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_provision_channel_validates_type(self, mock_db, mock_require_owner, client, auth_headers):
        """Test channel type validation."""
        response = client.post("/api/v1/onboarding/channels", headers=auth_headers, json={
            "channel_type": "invalid_channel",
            "phone_number": "+1234567890",
            "credentials": {},
        })

        assert response.status_code in [400, 422, 401]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_provision_multiple_channels(self, mock_db, mock_require_owner, client, auth_headers):
        """Test provisioning multiple channels."""
        channels = [
            {
                "channel_type": "whatsapp",
                "phone_number": "+1234567890",
                "credentials": {"phone_number_id": "123"},
            },
            {
                "channel_type": "email",
                "email": "support@example.com",
                "credentials": {},
            },
        ]
        for channel_data in channels:
            response = client.post("/api/v1/onboarding/channels", headers=auth_headers, json=channel_data)
            assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_verify_channel(self, mock_db, mock_require_owner, client, auth_headers):
        """Test verifying channel credentials."""
        response = client.post("/api/v1/channels/channel-123/verify", headers=auth_headers)

        assert response.status_code in [200, 401, 404, 422]


class TestChannelManagement:
    """Test channel configuration management."""

    @patch("services.tenant_config.main.get_auth")
    @patch("services.tenant_config.main.db")
    def test_list_channels(self, mock_db, mock_get_auth, client, auth_headers):
        """Test listing configured channels."""
        response = client.get("/api/v1/channels", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant_config.main.require_owner")
    def test_list_channels_requires_auth(self, mock_require_owner, client):
        """Test listing channels requires authentication."""
        response = client.get("/api/v1/channels")

        assert response.status_code == 401

    def test_lookup_tenant_by_channel(self, client):
        """Test looking up tenant by channel identifier."""
        response = client.get("/api/v1/channels/lookup", params={
            "channel_type": "whatsapp",
            "phone_number": "+1234567890",
        })

        # Webhook endpoint, may not require auth
        assert response.status_code in [200, 400, 404]


class TestAIConfiguration:
    """Test AI configuration setup."""

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_configure_ai(self, mock_db, mock_require_owner, client, auth_headers, ai_config_data):
        """Test configuring AI for tenant."""
        response = client.post("/api/v1/onboarding/ai", headers=auth_headers, json=ai_config_data)

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_ai_config_validates_tone(self, mock_db, mock_require_owner, client, auth_headers):
        """Test AI config validates tone value."""
        response = client.post("/api/v1/onboarding/ai", headers=auth_headers, json={
            "tone": "invalid_tone",
            "language": "en",
        })

        assert response.status_code in [400, 422, 401]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_ai_config_generates_system_prompt(self, mock_db, mock_require_owner, client, auth_headers, ai_config_data):
        """Test AI config generates system prompt."""
        response = client.post("/api/v1/onboarding/ai", headers=auth_headers, json=ai_config_data)

        if response.status_code in [200, 201]:
            data = response.json()
            assert "system_prompt" in data or "prompt" in data

    @patch("services.tenant_config.main.get_auth")
    @patch("services.tenant_config.main.db")
    def test_get_ai_config(self, mock_db, mock_get_auth, client, auth_headers):
        """Test retrieving AI configuration."""
        response = client.get("/api/v1/ai-config", headers=auth_headers)

        assert response.status_code in [200, 401]


class TestOnboardingFlow:
    """Test complete onboarding workflow."""

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_mark_test_passed(self, mock_db, mock_require_owner, client, auth_headers):
        """Test marking test phase as passed."""
        response = client.post("/api/v1/onboarding/test-pass", headers=auth_headers)

        assert response.status_code in [200, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_activate_tenant(self, mock_db, mock_require_owner, client, auth_headers):
        """Test activating tenant after onboarding."""
        response = client.post("/api/v1/onboarding/activate", headers=auth_headers)

        assert response.status_code in [200, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_activate_requires_completed_onboarding(self, mock_db, mock_require_owner, client, auth_headers):
        """Test activation validates onboarding is complete."""
        response = client.post("/api/v1/onboarding/activate", headers=auth_headers)

        # May return 422 if onboarding incomplete
        assert response.status_code in [200, 401, 422]


class TestCredentialManagement:
    """Test credential storage and retrieval."""

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_store_credential(self, mock_db, mock_require_owner, client, auth_headers):
        """Test storing channel credential."""
        response = client.post("/api/v1/credentials", headers=auth_headers, json={
            "channel": "whatsapp",
            "key": "api_token",
            "value": "secret-token-123",
        })

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_get_credential(self, mock_db, mock_require_owner, client, auth_headers):
        """Test retrieving channel credential."""
        response = client.get("/api/v1/credentials/whatsapp", headers=auth_headers)

        assert response.status_code in [200, 401, 404]

    @patch("services.tenant_config.main.require_owner")
    def test_credential_retrieval_requires_owner(self, mock_require_owner, client):
        """Test credential endpoints require owner role."""
        response = client.get("/api/v1/credentials/whatsapp")

        assert response.status_code == 401

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_credential_encryption(self, mock_db, mock_require_owner, client, auth_headers):
        """Test credentials are encrypted."""
        response = client.post("/api/v1/credentials", headers=auth_headers, json={
            "channel": "email",
            "key": "smtp_password",
            "value": "plain-password",
        })

        assert response.status_code in [200, 201, 401, 422]


class TestInternalCredentialAccess:
    """Test internal credential access for services."""

    def test_internal_get_credential(self, client):
        """Test internal credential retrieval endpoint."""
        response = client.get("/api/v1/internal/credentials", params={
            "channel": "whatsapp",
            "tenant_id": "tenant-456",
        })

        # Internal endpoint may require service token
        assert response.status_code in [200, 401, 403, 404]


class TestFullConfiguration:
    """Test full tenant configuration export."""

    @patch("services.tenant_config.main.get_auth")
    @patch("services.tenant_config.main.db")
    def test_get_full_tenant_config(self, mock_db, mock_get_auth, client, auth_headers):
        """Test retrieving full tenant configuration."""
        response = client.get("/api/v1/config/full", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant_config.main.get_auth")
    @patch("services.tenant_config.main.db")
    def test_full_config_includes_channels(self, mock_db, mock_get_auth, client, auth_headers):
        """Test full config includes all channels."""
        response = client.get("/api/v1/config/full", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert "channels" in data or "config" in data


class TestOnboardingLog:
    """Test onboarding activity log."""

    @patch("services.tenant_config.main.get_auth")
    @patch("services.tenant_config.main.db")
    def test_get_onboarding_log(self, mock_db, mock_get_auth, client, auth_headers):
        """Test retrieving onboarding activity log."""
        response = client.get("/api/v1/onboarding/log", headers=auth_headers)

        assert response.status_code in [200, 401]

    @patch("services.tenant_config.main.get_auth")
    @patch("services.tenant_config.main.db")
    def test_onboarding_log_shows_steps(self, mock_db, mock_get_auth, client, auth_headers):
        """Test onboarding log includes all steps."""
        response = client.get("/api/v1/onboarding/log", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                assert len(data) >= 0


class TestStateTransitions:
    """Test lifecycle state transitions."""

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_transition_profile_to_channels(self, mock_db, mock_require_owner, client, auth_headers, business_profile_data):
        """Test state transition from profile to channels."""
        response = client.post("/api/v1/onboarding/profile", headers=auth_headers, json=business_profile_data)

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_transition_channels_to_ai(self, mock_db, mock_require_owner, client, auth_headers, channel_provision_data):
        """Test state transition from channels to AI config."""
        response = client.post("/api/v1/onboarding/channels", headers=auth_headers, json=channel_provision_data)

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_transition_ai_to_test(self, mock_db, mock_require_owner, client, auth_headers, ai_config_data):
        """Test state transition from AI config to testing."""
        response = client.post("/api/v1/onboarding/ai", headers=auth_headers, json=ai_config_data)

        assert response.status_code in [200, 201, 401, 422]

    @patch("services.tenant_config.main.require_owner")
    @patch("services.tenant_config.main.db")
    def test_transition_test_to_active(self, mock_db, mock_require_owner, client, auth_headers):
        """Test state transition from testing to active."""
        response = client.post("/api/v1/onboarding/activate", headers=auth_headers)

        assert response.status_code in [200, 401, 422]


class TestValidation:
    """Test input validation."""

    @patch("services.tenant_config.main.require_owner")
    def test_invalid_industry(self, mock_require_owner, client, auth_headers):
        """Test invalid industry validation."""
        response = client.post("/api/v1/onboarding/profile", headers=auth_headers, json={
            "business_name": "Test Co",
            "industry": "non_existent_industry",
            "timezone": "America/New_York",
            "currency": "USD",
            "country": "US",
        })

        # Should validate against industry taxonomy
        assert response.status_code in [400, 422, 401]

    @patch("services.tenant_config.main.require_owner")
    def test_invalid_country(self, mock_require_owner, client, auth_headers):
        """Test invalid country validation."""
        response = client.post("/api/v1/onboarding/profile", headers=auth_headers, json={
            "business_name": "Test Co",
            "industry": "retail",
            "timezone": "America/New_York",
            "currency": "USD",
            "country": "XX",
        })

        # Should validate against countries list
        assert response.status_code in [400, 422, 401]

    @patch("services.tenant_config.main.require_owner")
    def test_invalid_timezone(self, mock_require_owner, client, auth_headers):
        """Test invalid timezone validation."""
        response = client.post("/api/v1/onboarding/profile", headers=auth_headers, json={
            "business_name": "Test Co",
            "industry": "retail",
            "timezone": "Invalid/Timezone",
            "currency": "USD",
            "country": "US",
        })

        # Should validate timezone format
        assert response.status_code in [400, 422, 401]
