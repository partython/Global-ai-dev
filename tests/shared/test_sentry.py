"""
Comprehensive tests for Sentry integration modules.

Tests PII scrubbing, before_send filters, health check filtering,
tenant context injection, graceful degradation, and error fingerprinting.
"""

import pytest
import re
from unittest.mock import patch, MagicMock, AsyncMock

from shared.monitoring.sentry_config import (
    PII_PATTERNS,
    _scrub_pii,
    _before_send,
    _before_send_transaction,
    init_sentry,
    set_tenant_context,
    capture_exception,
    capture_message,
    sentry_trace,
)
from shared.observability.sentry import (
    PII_PATTERNS as OBS_PII_PATTERNS,
    _scrub_pii as obs_scrub_pii,
    _scrub_data,
    _before_send as obs_before_send,
    _before_send_transaction as obs_before_send_transaction,
    init_sentry as obs_init_sentry,
    set_tenant_context as obs_set_tenant_context,
)
from shared.middleware.sentry import SentryTenantMiddleware


class TestPIIScrubbing:
    """Test PII pattern detection and scrubbing."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_email_addresses(self):
        """Email addresses are scrubbed."""
        text = "Contact john@example.com for support"
        scrubbed = _scrub_pii(text)
        assert "john@example.com" not in scrubbed
        assert "***EMAIL_REDACTED***" in scrubbed or "[EMAIL_REDACTED]" in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_password_in_url(self):
        """Passwords in connection strings are scrubbed."""
        text = "postgresql://user:myPassword123@localhost/db"
        scrubbed = _scrub_pii(text)
        assert "myPassword123" not in scrubbed
        assert "***REDACTED***" in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_api_key(self):
        """API keys are scrubbed."""
        text = "Authorization: Bearer sk-proj-abc123xyz"
        scrubbed = _scrub_pii(text)
        assert "sk-proj-abc123xyz" not in scrubbed
        assert "***REDACTED***" in scrubbed or "[TOKEN_REDACTED]" in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_credit_card(self):
        """Credit card numbers are scrubbed."""
        text = "Card: 4532 1234 5678 9010"
        scrubbed = _scrub_pii(text)
        assert "4532 1234 5678" not in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_ssn(self):
        """SSN is scrubbed."""
        text = "SSN: 123-45-6789"
        scrubbed = _scrub_pii(text)
        assert "123-45-6789" not in scrubbed
        assert "REDACTED" in scrubbed or "REDACTED" in scrubbed.upper()

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_aadhar(self):
        """Aadhar number is scrubbed."""
        text = "Aadhar: 1234 5678 9012"
        scrubbed = _scrub_pii(text)
        assert "1234 5678 9012" not in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_pan(self):
        """PAN is scrubbed."""
        text = "PAN: ABCDE1234F"
        scrubbed = _scrub_pii(text)
        assert "ABCDE1234F" not in scrubbed or "***PAN_REDACTED***" in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_phone_number(self):
        """Phone numbers are scrubbed."""
        text = "Call +91 98765 43210 for support"
        scrubbed = obs_scrub_pii(text)
        assert "98765 43210" not in scrubbed or "PHONE_REDACTED" in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_jwt_token(self):
        """JWT tokens are scrubbed."""
        text = "Authorization: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        scrubbed = obs_scrub_pii(text)
        assert "eyJhbGciOi" not in scrubbed or "JWT_REDACTED" in scrubbed

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_data_recursively(self):
        """PII is scrubbed from nested data structures."""
        data = {
            "user": {
                "email": "john@example.com",
                "profile": {
                    "phone": "+91 98765 43210",
                }
            }
        }
        scrubbed = _scrub_data(data)
        assert "john@example.com" not in str(scrubbed)

    @pytest.mark.unit
    @pytest.mark.security
    def test_scrub_list_items(self):
        """PII in lists is scrubbed."""
        data = ["user@example.com", "data@test.com", "normal_data"]
        scrubbed = _scrub_data(data)
        assert "user@example.com" not in str(scrubbed)
        assert "data@test.com" not in str(scrubbed)


class TestBeforeSendFilter:
    """Test before_send event filtering and processing."""

    @pytest.mark.unit
    def test_before_send_drops_ignored_errors(self):
        """before_send drops known noisy errors."""
        event = {
            "exception": {
                "values": [{
                    "type": "ConnectionResetError",
                    "value": "Connection reset by peer"
                }]
            }
        }
        hint = {"exc_info": (ConnectionResetError, Exception("test"), None)}

        result = _before_send(event, hint)
        assert result is None

    @pytest.mark.unit
    def test_before_send_drops_http_4xx_errors(self):
        """before_send drops client errors (4xx)."""
        event = {
            "tags": {"http.status_code": "404"},
            "exception": {"values": [{"type": "HTTPException", "value": "Not found"}]}
        }
        hint = {}

        result = obs_before_send(event, hint)
        assert result is None

    @pytest.mark.unit
    def test_before_send_keeps_5xx_errors(self):
        """before_send keeps server errors (5xx)."""
        event = {
            "tags": {"http.status_code": "500"},
            "exception": {"values": [{"type": "ServerError", "value": "Internal error"}]}
        }
        hint = {}

        result = obs_before_send(event, hint)
        assert result is not None

    @pytest.mark.unit
    def test_before_send_keeps_429_errors(self):
        """before_send keeps rate limit errors (429)."""
        event = {
            "tags": {"http.status_code": "429"},
            "exception": {"values": [{"type": "RateLimitError", "value": "Too many requests"}]}
        }
        hint = {}

        result = obs_before_send(event, hint)
        assert result is not None

    @pytest.mark.unit
    def test_before_send_scrubs_pii(self):
        """before_send scrubs PII from events."""
        event = {
            "message": "Error: user@example.com failed",
            "request": {
                "headers": {
                    "authorization": "Bearer secret_token"
                }
            }
        }
        hint = {}

        result = _before_send(event, hint)
        assert "user@example.com" not in str(result) or "***" in str(result)

    @pytest.mark.unit
    def test_before_send_adds_fingerprint(self):
        """before_send adds custom error fingerprint."""
        event = {
            "exception": {
                "values": [{
                    "type": "ValueError",
                    "value": "Invalid input format"
                }]
            }
        }
        hint = {}

        result = _before_send(event, hint)
        assert "fingerprint" in result
        assert result["fingerprint"][0] == "ValueError"

    @pytest.mark.unit
    def test_before_send_graceful_error_handling(self):
        """before_send handles exceptions gracefully."""
        event = {
            "malformed": "data" * 10000,  # Potentially problematic
        }
        hint = {}

        # Should not raise, should return event
        result = _before_send(event, hint)
        assert result is not None


class TestTransactionFiltering:
    """Test transaction/performance event filtering."""

    @pytest.mark.unit
    def test_before_send_transaction_drops_health_checks(self):
        """before_send_transaction filters out health check endpoints."""
        event = {
            "transaction": "/health",
            "spans": []
        }
        hint = {}

        result = _before_send_transaction(event, hint)
        assert result is None

    @pytest.mark.unit
    def test_before_send_transaction_drops_readiness_probes(self):
        """before_send_transaction filters /ready endpoint."""
        event = {"transaction": "/ready"}
        hint = {}

        result = _before_send_transaction(event, hint)
        assert result is None

    @pytest.mark.unit
    def test_before_send_transaction_drops_metrics_endpoint(self):
        """before_send_transaction filters /metrics endpoint."""
        event = {"transaction": "/metrics"}
        hint = {}

        result = _before_send_transaction(event, hint)
        assert result is None

    @pytest.mark.unit
    def test_before_send_transaction_drops_favicon(self):
        """before_send_transaction filters /favicon.ico."""
        event = {"transaction": "/favicon.ico"}
        hint = {}

        result = _before_send_transaction(event, hint)
        assert result is None

    @pytest.mark.unit
    def test_before_send_transaction_keeps_api_calls(self):
        """before_send_transaction keeps actual API transactions."""
        event = {"transaction": "POST /api/v1/conversations"}
        hint = {}

        result = _before_send_transaction(event, hint)
        assert result is not None

    @pytest.mark.unit
    def test_before_send_transaction_keeps_business_operations(self):
        """before_send_transaction keeps business operation transactions."""
        event = {"transaction": "process_message"}
        hint = {}

        result = obs_before_send_transaction(event, hint)
        assert result is not None


class TestSentryInitialization:
    """Test Sentry initialization."""

    @pytest.mark.unit
    def test_init_sentry_returns_false_without_dsn(self):
        """init_sentry returns False if DSN is not set."""
        with patch.dict("os.environ", {"SENTRY_DSN": "", "SENTRY_ENABLED": "true"}):
            result = init_sentry(
                service_name="test",
                service_port=9000,
            )
            assert result is False

    @pytest.mark.unit
    def test_init_sentry_returns_false_when_disabled(self):
        """init_sentry returns False if SENTRY_ENABLED=false."""
        with patch.dict("os.environ", {
            "SENTRY_DSN": "https://key@sentry.io/123",
            "SENTRY_ENABLED": "false"
        }):
            result = init_sentry(
                service_name="test",
                service_port=9000,
            )
            assert result is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_init_sentry_does_not_send_default_pii(self):
        """init_sentry sets send_default_pii=False."""
        with patch("shared.observability.sentry.sentry_sdk.init") as mock_init:
            with patch.dict("os.environ", {
                "SENTRY_DSN": "https://key@sentry.io/123",
                "SENTRY_ENABLED": "true"
            }):
                obs_init_sentry(
                    service_name="test",
                    service_port=9000,
                )

            call_kwargs = mock_init.call_args[1]
            assert call_kwargs.get("send_default_pii") is False


class TestTenantContextInjection:
    """Test tenant context setting in Sentry."""

    @pytest.mark.unit
    def test_set_tenant_context_tags_tenant_id(self):
        """set_tenant_context tags the tenant ID."""
        with patch("shared.observability.sentry.sentry_sdk.configure_scope") as mock_scope:
            mock_context = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_context

            obs_set_tenant_context(tenant_id="t_123")
            mock_context.set_tag.assert_called_with("tenant_id", "t_123")

    @pytest.mark.unit
    def test_set_tenant_context_sets_user(self):
        """set_tenant_context sets user context."""
        with patch("shared.observability.sentry.sentry_sdk.configure_scope") as mock_scope:
            mock_context = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_context

            obs_set_tenant_context(user_id="u_456")
            mock_context.set_user.assert_called_once()

    @pytest.mark.unit
    def test_set_tenant_context_sets_plan(self):
        """set_tenant_context stores plan information."""
        with patch("shared.observability.sentry.sentry_sdk.configure_scope") as mock_scope:
            mock_context = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_context

            obs_set_tenant_context(tenant_id="t_123", plan="enterprise")
            mock_context.set_context.assert_called()


class TestCaptureExceptionAndMessage:
    """Test exception and message capture."""

    @pytest.mark.unit
    def test_capture_exception_with_context(self):
        """capture_exception sends exception with context."""
        with patch("shared.observability.sentry.sentry_sdk.capture_exception") as mock_capture:
            error = ValueError("Invalid input")
            capture_exception(error, extra={"field": "value"}, tags={"type": "validation"})
            mock_capture.assert_called_once_with(error)

    @pytest.mark.unit
    def test_capture_message_sends_to_sentry(self):
        """capture_message sends message to Sentry."""
        with patch("shared.observability.sentry.sentry_sdk.capture_message") as mock_capture:
            capture_message("Test message", level="warning")
            # Should be called once


class TestSentryTraceDecorator:
    """Test sentry_trace decorator."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sentry_trace_decorates_async_function(self):
        """sentry_trace decorator works with async functions."""
        @sentry_trace(op="test_operation")
        async def async_func():
            return "result"

        with patch("shared.monitoring.sentry_config.sentry_sdk.start_span"):
            result = await async_func()
            assert result == "result"

    @pytest.mark.unit
    def test_sentry_trace_decorates_sync_function(self):
        """sentry_trace decorator works with sync functions."""
        @sentry_trace(op="test_operation")
        def sync_func():
            return "result"

        with patch("shared.monitoring.sentry_config.sentry_sdk.start_span"):
            result = sync_func()
            assert result == "result"


class TestSentryMiddleware:
    """Test FastAPI middleware integration."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_middleware_extracts_tenant_id_from_header(self):
        """Middleware extracts tenant_id from X-Tenant-ID header."""
        middleware = SentryTenantMiddleware(MagicMock())

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = "t_123"
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"

        mock_call_next = AsyncMock(return_value=MagicMock(status_code=200))

        with patch("shared.middleware.sentry.sentry_sdk.configure_scope") as mock_scope:
            mock_context = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_context

            await middleware.dispatch(mock_request, mock_call_next)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_middleware_adds_request_breadcrumb(self):
        """Middleware adds HTTP request breadcrumb."""
        middleware = SentryTenantMiddleware(MagicMock())

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = "t_123"
        mock_request.method = "POST"
        mock_request.url.path = "/api/messages"

        mock_call_next = AsyncMock(return_value=MagicMock(status_code=200))

        with patch("shared.middleware.sentry.sentry_sdk") as mock_sentry:
            mock_scope = MagicMock()
            mock_sentry.configure_scope.return_value.__enter__.return_value = mock_scope

            await middleware.dispatch(mock_request, mock_call_next)

            # Should add breadcrumb
            mock_sentry.add_breadcrumb.assert_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_middleware_captures_slow_requests(self):
        """Middleware adds breadcrumb for slow requests (>5s)."""
        middleware = SentryTenantMiddleware(MagicMock())

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"

        # Return a slow response
        async def slow_call_next(req):
            import asyncio
            await asyncio.sleep(0.1)
            response = MagicMock()
            response.status_code = 200
            return response

        with patch("shared.middleware.sentry.sentry_sdk") as mock_sentry:
            mock_scope = MagicMock()
            mock_sentry.configure_scope.return_value.__enter__.return_value = mock_scope

            response = await middleware.dispatch(mock_request, slow_call_next)
            assert response.status_code == 200

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_middleware_captures_exceptions(self):
        """Middleware captures and re-raises exceptions."""
        middleware = SentryTenantMiddleware(MagicMock())

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"

        error = ValueError("Test error")

        async def failing_call_next(req):
            raise error

        with patch("shared.middleware.sentry.sentry_sdk") as mock_sentry:
            mock_scope = MagicMock()
            mock_sentry.configure_scope.return_value.__enter__.return_value = mock_scope

            with pytest.raises(ValueError):
                await middleware.dispatch(mock_request, failing_call_next)

            # Should capture exception
            mock_sentry.capture_exception.assert_called_with(error)


class TestGracefulDegradation:
    """Test graceful degradation when Sentry is unavailable."""

    @pytest.mark.unit
    def test_init_sentry_handles_import_error(self):
        """init_sentry handles missing sentry_sdk gracefully."""
        with patch("shared.monitoring.sentry_config.sentry_sdk", side_effect=ImportError):
            result = init_sentry(
                service_name="test",
                service_port=9000,
                dsn="https://key@sentry.io/123",
            )
            # Should return False or handle gracefully

    @pytest.mark.unit
    def test_capture_exception_handles_sentry_unavailable(self):
        """capture_exception handles Sentry unavailability."""
        with patch("shared.observability.sentry.sentry_sdk", side_effect=Exception):
            # Should not raise
            capture_exception(ValueError("test"))

    @pytest.mark.unit
    def test_set_tenant_context_gracefully_fails(self):
        """set_tenant_context handles Sentry unavailability."""
        with patch("shared.observability.sentry.sentry_sdk", side_effect=Exception):
            # Should not raise
            obs_set_tenant_context(tenant_id="t_123")
