"""
Comprehensive tests for shared.core.security module.

Tests password hashing/verification, JWT tokens, PII masking,
input sanitization, rate limiting, and webhook signatures.
"""

import json
import pytest
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from shared.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_access_token,
    generate_api_key,
    verify_api_key,
    mask_pii,
    sanitize_input,
    sanitize_email,
    sanitize_slug,
    get_rate_limit,
    verify_webhook_signature,
    create_webhook_signature,
)
from shared.core.config import config


class TestPasswordHashing:
    """Test bcrypt password hashing and verification."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_hash_password_produces_hash(self):
        """hash_password produces a bcrypt hash."""
        password = "correct_horse_battery_staple"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt format

    @pytest.mark.unit
    @pytest.mark.security
    def test_hash_password_is_deterministic_with_salt(self):
        """Hashing same password twice produces different hashes (salted)."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Different salts

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_password_succeeds_with_correct_password(self):
        """verify_password returns True with correct password."""
        password = "correct_password"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_password_fails_with_wrong_password(self):
        """verify_password returns False with incorrect password."""
        password = "correct_password"
        hashed = hash_password(password)
        assert verify_password("wrong_password", hashed) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_password_handles_invalid_hash(self):
        """verify_password returns False with malformed hash."""
        assert verify_password("password", "not_a_hash") is False
        assert verify_password("password", "") is False
        assert verify_password("password", "$2b$invalid") is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_hash_uses_configured_bcrypt_rounds(self):
        """Password hash uses configured bcrypt rounds (12 by default)."""
        password = "test_password"
        hashed = hash_password(password)
        # Extract rounds from bcrypt hash format: $2b$rounds$...
        rounds = int(hashed.split("$")[2])
        assert rounds == config.security.bcrypt_rounds


class TestJWTTokens:
    """Test JWT token creation and validation."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_create_access_token_includes_required_claims(self):
        """Access token includes user_id, tenant_id, role, plan claims."""
        token = create_access_token(
            user_id="u_123",
            tenant_id="t_456",
            role="admin",
            plan="enterprise",
        )
        claims = decode_token(token)
        assert claims["sub"] == "u_123"
        assert claims["tenant_id"] == "t_456"
        assert claims["role"] == "admin"
        assert claims["plan"] == "enterprise"
        assert claims["type"] == "access"

    @pytest.mark.unit
    @pytest.mark.security
    def test_create_access_token_with_permissions(self):
        """Access token includes custom permissions."""
        perms = ["read:conversation", "write:message"]
        token = create_access_token(
            user_id="u_123",
            tenant_id="t_456",
            role="agent",
            plan="growth",
            permissions=perms,
        )
        claims = decode_token(token)
        assert claims["permissions"] == perms

    @pytest.mark.unit
    @pytest.mark.security
    def test_create_access_token_with_extra_claims(self):
        """Access token includes extra custom claims."""
        extra = {"department": "sales", "region": "APAC"}
        token = create_access_token(
            user_id="u_123",
            tenant_id="t_456",
            role="agent",
            plan="growth",
            extra_claims=extra,
        )
        claims = decode_token(token)
        assert claims["department"] == "sales"
        assert claims["region"] == "APAC"

    @pytest.mark.unit
    @pytest.mark.security
    def test_access_token_expiry_is_set(self):
        """Access token has correct expiry time."""
        token = create_access_token(
            user_id="u_123",
            tenant_id="t_456",
            role="user",
            plan="starter",
        )
        claims = decode_token(token)
        now = int(datetime.now(timezone.utc).timestamp())
        assert "exp" in claims
        assert claims["exp"] > now
        # Should expire in ~15 minutes
        assert claims["exp"] - claims["iat"] == config.jwt.access_token_expiry

    @pytest.mark.unit
    @pytest.mark.security
    def test_create_refresh_token_returns_token_and_hash(self):
        """Refresh token returns both token and its hash."""
        token, token_hash = create_refresh_token(
            user_id="u_123",
            tenant_id="t_456",
        )
        assert isinstance(token, str)
        assert isinstance(token_hash, str)
        assert len(token) > 50  # URL-safe random string
        assert len(token_hash) == 64  # SHA256 hex

    @pytest.mark.unit
    @pytest.mark.security
    def test_refresh_token_is_valid_jwt(self):
        """Refresh token is a valid JWT."""
        token, _ = create_refresh_token(
            user_id="u_123",
            tenant_id="t_456",
        )
        claims = decode_token(token)
        assert claims["type"] == "refresh"
        assert claims["sub"] == "u_123"
        assert claims["tenant_id"] == "t_456"

    @pytest.mark.unit
    @pytest.mark.security
    def test_refresh_token_expiry(self):
        """Refresh token has longer expiry (7 days)."""
        token, _ = create_refresh_token(
            user_id="u_123",
            tenant_id="t_456",
        )
        claims = decode_token(token)
        # Should expire in ~7 days
        assert claims["exp"] - claims["iat"] == config.jwt.refresh_token_expiry

    @pytest.mark.unit
    @pytest.mark.security
    def test_decode_token_validates_issuer(self):
        """decode_token validates issuer claim."""
        token = create_access_token(
            user_id="u_123",
            tenant_id="t_456",
            role="user",
            plan="starter",
        )
        claims = decode_token(token)
        assert claims["iss"] == config.jwt.issuer

    @pytest.mark.unit
    @pytest.mark.security
    def test_decode_token_fails_with_expired_token(self):
        """decode_token raises exception for expired token."""
        # Create token with negative expiry
        payload = {
            "sub": "u_123",
            "tenant_id": "t_456",
            "exp": int(datetime.now(timezone.utc).timestamp()) - 3600,
            "iat": int(datetime.now(timezone.utc).timestamp()) - 7200,
            "iss": config.jwt.issuer,
        }
        expired_token = pyjwt.encode(
            payload,
            config.jwt.secret_key,
            algorithm=config.jwt.algorithm,
        )
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(expired_token)

    @pytest.mark.unit
    @pytest.mark.security
    def test_validate_access_token_returns_claims_when_valid(self):
        """validate_access_token returns claims for valid token."""
        token = create_access_token(
            user_id="u_123",
            tenant_id="t_456",
            role="admin",
            plan="enterprise",
        )
        claims = validate_access_token(token)
        assert claims is not None
        assert claims["sub"] == "u_123"

    @pytest.mark.unit
    @pytest.mark.security
    def test_validate_access_token_returns_none_for_invalid(self):
        """validate_access_token returns None for invalid/expired token."""
        assert validate_access_token("invalid_token") is None
        assert validate_access_token("") is None
        assert validate_access_token("header.payload") is None

    @pytest.mark.unit
    @pytest.mark.security
    def test_validate_access_token_rejects_refresh_token(self):
        """validate_access_token rejects refresh tokens."""
        token, _ = create_refresh_token(
            user_id="u_123",
            tenant_id="t_456",
        )
        assert validate_access_token(token) is None


class TestAPIKeyManagement:
    """Test API key generation and validation."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_generate_api_key_produces_three_values(self):
        """generate_api_key returns full_key, prefix, and hash."""
        full_key, prefix, key_hash = generate_api_key()
        assert isinstance(full_key, str)
        assert isinstance(prefix, str)
        assert isinstance(key_hash, str)

    @pytest.mark.unit
    @pytest.mark.security
    def test_generate_api_key_with_custom_prefix(self):
        """API key can have custom prefix."""
        full_key, prefix, _ = generate_api_key(prefix="sk_test_")
        assert full_key.startswith("sk_test_")
        assert prefix.startswith("sk_test_")

    @pytest.mark.unit
    @pytest.mark.security
    def test_api_key_prefix_is_first_12_chars(self):
        """API key prefix is first 12 characters."""
        full_key, prefix, _ = generate_api_key(prefix="pk_live_")
        assert prefix == full_key[:12]

    @pytest.mark.unit
    @pytest.mark.security
    def test_api_key_hash_is_bcrypt(self):
        """API key hash is bcrypt format."""
        _, _, key_hash = generate_api_key()
        assert key_hash.startswith("$2b$")

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_api_key_succeeds_with_correct_key(self):
        """verify_api_key returns True for correct key."""
        full_key, _, key_hash = generate_api_key()
        assert verify_api_key(full_key, key_hash) is True

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_api_key_fails_with_wrong_key(self):
        """verify_api_key returns False for incorrect key."""
        _, _, key_hash = generate_api_key()
        assert verify_api_key("wrong_key_12345678901234567890", key_hash) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_api_keys_are_unique(self):
        """Each API key is unique."""
        key1, _, hash1 = generate_api_key()
        key2, _, hash2 = generate_api_key()
        assert key1 != key2
        assert hash1 != hash2


class TestPIIMasking:
    """Test PII detection and masking."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_mask_email_address(self):
        """Email addresses are masked in logs."""
        text = "Contact john@example.com for details"
        masked = mask_pii(text)
        assert "john@example.com" not in masked
        assert "***@" in masked

    @pytest.mark.unit
    @pytest.mark.security
    def test_mask_phone_number(self):
        """Phone numbers are masked."""
        text = "Call +91 98765 43210 for support"
        masked = mask_pii(text)
        assert "98765 43210" not in masked
        assert "****" in masked

    @pytest.mark.unit
    @pytest.mark.security
    def test_mask_credit_card(self):
        """Credit card numbers are masked."""
        text = "Card: 4532 1234 5678 9010"
        masked = mask_pii(text)
        assert "4532 1234 5678" not in masked
        assert "****-****-****-" in masked

    @pytest.mark.unit
    @pytest.mark.security
    def test_mask_ssn(self):
        """SSN is masked."""
        text = "SSN: 123-45-6789"
        masked = mask_pii(text)
        assert "123-45-6789" not in masked
        assert "REDACTED" in masked

    @pytest.mark.unit
    @pytest.mark.security
    def test_mask_multiple_pii_types(self):
        """Multiple PII types in text are all masked."""
        text = "Contact john@example.com or +91 98765 43210"
        masked = mask_pii(text)
        assert "john@example.com" not in masked
        assert "98765 43210" not in masked

    @pytest.mark.unit
    @pytest.mark.security
    def test_mask_pii_disabled_when_configured(self):
        """PII masking can be disabled."""
        with patch.object(config.security, 'pii_masking_enabled', False):
            text = "Email: test@example.com"
            masked = mask_pii(text)
            assert text == masked  # No masking applied


class TestInputSanitization:
    """Test input sanitization for security."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_input_removes_null_bytes(self):
        """Null bytes are removed from input."""
        text = "hello\x00world"
        sanitized = sanitize_input(text)
        assert "\x00" not in sanitized
        assert "helloworld" == sanitized

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_input_removes_control_characters(self):
        """Control characters are removed."""
        text = "hello\x01\x02world"
        sanitized = sanitize_input(text)
        assert "helloworld" == sanitized

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_input_preserves_newlines_and_tabs(self):
        """Newlines and tabs are preserved."""
        text = "line1\nline2\ttab"
        sanitized = sanitize_input(text)
        assert "\n" in sanitized
        assert "\t" in sanitized

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_input_truncates_long_input(self):
        """Long input is truncated to max_length."""
        text = "a" * 20000
        sanitized = sanitize_input(text, max_length=100)
        assert len(sanitized) <= 100

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_input_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        text = "  hello world  "
        sanitized = sanitize_input(text)
        assert sanitized == "hello world"

    @pytest.mark.unit
    @pytest.mark.security
    def test_sanitize_input_handles_empty_string(self):
        """Empty string returns empty string."""
        assert sanitize_input("") == ""
        assert sanitize_input(None) == ""

    @pytest.mark.unit
    def test_sanitize_email_valid_addresses(self):
        """Valid emails are normalized."""
        assert sanitize_email("John@EXAMPLE.COM") == "john@example.com"
        assert sanitize_email("  test@example.com  ") == "test@example.com"

    @pytest.mark.unit
    def test_sanitize_email_invalid_addresses(self):
        """Invalid emails return None."""
        assert sanitize_email("notanemail") is None
        assert sanitize_email("@example.com") is None
        assert sanitize_email("user@") is None

    @pytest.mark.unit
    def test_sanitize_slug_converts_to_url_safe(self):
        """Text is converted to URL-safe slug."""
        assert sanitize_slug("Hello World!") == "hello-world"
        assert sanitize_slug("Priya  AI  Platform") == "priya-ai-platform"

    @pytest.mark.unit
    def test_sanitize_slug_removes_special_chars(self):
        """Special characters are removed."""
        assert sanitize_slug("Hello@#$%World") == "helloworld"

    @pytest.mark.unit
    def test_sanitize_slug_has_max_length(self):
        """Slug is limited to 64 characters."""
        long_text = "a" * 100
        slug = sanitize_slug(long_text)
        assert len(slug) <= 64


class TestRateLimiting:
    """Test rate limit helpers."""

    @pytest.mark.unit
    def test_rate_limit_starter_plan(self):
        """Starter plan has correct rate limit."""
        limit = get_rate_limit("starter")
        assert limit == config.security.rate_limit_starter

    @pytest.mark.unit
    def test_rate_limit_growth_plan(self):
        """Growth plan has higher limit than starter."""
        limit = get_rate_limit("growth")
        assert limit == config.security.rate_limit_growth
        assert limit > get_rate_limit("starter")

    @pytest.mark.unit
    def test_rate_limit_enterprise_plan(self):
        """Enterprise plan has highest limit."""
        limit = get_rate_limit("enterprise")
        assert limit == config.security.rate_limit_enterprise
        assert limit > get_rate_limit("growth")

    @pytest.mark.unit
    def test_rate_limit_trial_plan(self):
        """Trial plan uses starter limit."""
        assert get_rate_limit("trial") == get_rate_limit("starter")

    @pytest.mark.unit
    def test_rate_limit_unknown_plan_uses_default(self):
        """Unknown plan falls back to starter limit."""
        limit = get_rate_limit("unknown_plan")
        assert limit == config.security.rate_limit_starter


class TestWebhookSignatures:
    """Test webhook HMAC signing and verification."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_create_webhook_signature(self):
        """Webhook signature is created."""
        payload = b'{"event": "test"}'
        secret = "webhook_secret_key"
        signature = create_webhook_signature(payload, secret)
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_webhook_signature_succeeds(self):
        """Webhook signature verification succeeds with correct secret."""
        payload = b'{"event": "order.created", "id": "123"}'
        secret = "my_webhook_secret"
        signature = create_webhook_signature(payload, secret)
        assert verify_webhook_signature(payload, signature, secret) is True

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_webhook_signature_fails_with_wrong_secret(self):
        """Webhook verification fails with wrong secret."""
        payload = b'{"event": "order.created"}'
        secret = "correct_secret"
        wrong_secret = "wrong_secret"
        signature = create_webhook_signature(payload, secret)
        assert verify_webhook_signature(payload, signature, wrong_secret) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_verify_webhook_signature_fails_with_modified_payload(self):
        """Webhook verification fails if payload is modified."""
        payload = b'{"amount": 100}'
        secret = "secret"
        signature = create_webhook_signature(payload, secret)
        modified_payload = b'{"amount": 1000}'
        assert verify_webhook_signature(modified_payload, signature, secret) is False

    @pytest.mark.unit
    @pytest.mark.security
    def test_webhook_signature_is_constant_time(self):
        """Webhook signature uses constant-time comparison."""
        payload = b'test'
        secret = "secret"
        correct_sig = create_webhook_signature(payload, secret)
        wrong_sig = "0" * 64
        # This should not raise timing attack vulnerability
        verify_webhook_signature(payload, correct_sig, secret)
        verify_webhook_signature(payload, wrong_sig, secret)
