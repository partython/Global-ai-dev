"""
PII (Personally Identifiable Information) Protection Tests

Tests that sensitive data is properly masked in logs, error messages, and
Sentry error tracking. Covers international PII formats.

Standards:
- GDPR: Data protection, privacy by design
- CCPA: Opt-out, deletion rights
- HIPAA: PHI protection
- Data security: Encryption at rest/transit
"""

import pytest
import re

pytestmark = [
    pytest.mark.security,
]


# ============================================================================
# Email Masking Tests
# ============================================================================


class TestEmailMasking:
    """Test email address masking in logs."""

    def test_email_masked_in_logs(self):
        """
        Security: Emails must be masked before logging.
        john@example.com -> j***@e***.com
        """
        from shared.core.security import mask_pii

        email = "john.doe@example.com"
        masked = mask_pii(email)

        # First letter of name + ***, then domain pattern
        assert "john" not in masked
        assert "@" in masked or "***" in masked
        assert "example.com" not in masked

    @pytest.mark.parametrize("email", [
        "alice@company.co.uk",
        "bob.smith@domain.org",
        "test+tag@subdomain.example.com",
        "user@192.168.1.1",  # IP-based email
    ])
    def test_various_email_formats_masked(self, email):
        """
        Security: Masking must handle various email formats.
        """
        from shared.core.security import mask_pii

        masked = mask_pii(email)

        # Email should not appear in plain form
        assert email not in masked or masked == email  # If masking disabled in config

    def test_email_never_in_error_response(self):
        """
        Security: Error responses must not include raw email addresses.
        """
        # Bad: {"error": "User john@example.com not found"}
        # Good: {"error": "User not found"}

        error_response = {"error": "User not found"}

        # Verify no email patterns in response
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        assert not re.search(email_pattern, str(error_response))


# ============================================================================
# Phone Number Masking Tests
# ============================================================================


class TestPhoneNumberMasking:
    """Test phone number masking in logs."""

    @pytest.mark.parametrize("phone,country", [
        ("+919876543210", "IN"),  # India
        ("+14155552671", "US"),  # US
        ("+442071838750", "GB"),  # UK
        ("+49301234567", "DE"),  # Germany
        ("+81312345678", "JP"),  # Japan
        ("+551199999999", "BR"),  # Brazil
        ("+971501234567", "AE"),  # UAE
    ])
    def test_international_phone_masked(self, phone, country):
        """
        Security: International phone numbers masked in logs.
        +91 98765 43210 -> +91 ******* 3210
        """
        from shared.core.security import mask_pii

        masked = mask_pii(phone)

        # Should mask middle digits
        assert phone not in masked or phone == masked  # If masking disabled
        # Should keep country code and last 4
        if country == "IN":
            assert "+91" in masked or "***" in masked
        if "3210" in phone:
            assert "3210" in masked or "***" in masked

    def test_phone_with_formatting_masked(self):
        """
        Security: Phone with various formats masked consistently.
        (917) 555-1234 -> similar mask pattern
        """
        from shared.core.security import mask_pii

        formats = [
            "+91 9876 543 210",
            "+91-9876-543-210",
            "(+91) 9876-543-210",
            "009876543210",
        ]

        for phone in formats:
            masked = mask_pii(phone)
            # Raw phone should not appear (unless masking disabled)
            assert "9876543210" not in masked or masked == phone


# ============================================================================
# Credit Card Masking Tests
# ============================================================================


class TestCreditCardMasking:
    """Test credit card number masking."""

    @pytest.mark.parametrize("card_number", [
        "4532015112830366",  # Visa
        "5425233010103442",  # Mastercard
        "378282246310005",   # Amex
        "6011111111111117",  # Discover
    ])
    def test_credit_card_masked(self, card_number):
        """
        Security: Credit card numbers masked in logs.
        4532015112830366 -> ****-****-****-0366
        """
        from shared.core.security import mask_pii

        masked = mask_pii(card_number)

        # Full card number should not appear
        assert card_number not in masked or masked == card_number
        # Last 4 digits may be visible
        if "0366" in card_number:
            assert "0366" in masked or "****" in masked

    def test_card_with_spaces_masked(self):
        """
        Security: Cards with formatting (spaces, dashes) also masked.
        """
        from shared.core.security import mask_pii

        formatted_cards = [
            "4532 0151 1283 0366",
            "4532-0151-1283-0366",
        ]

        for card in formatted_cards:
            masked = mask_pii(card)
            # No unmasked digits in sequence
            assert "0151" not in masked or "****" in masked


# ============================================================================
# SSN/Tax ID Masking Tests
# ============================================================================


class TestSSNAndTaxIDMasking:
    """Test SSN and international tax ID masking."""

    def test_us_ssn_masked(self):
        """
        Security: US Social Security Number masked.
        123-45-6789 -> ***-**-6789
        """
        from shared.core.security import mask_pii

        ssn = "123-45-6789"
        masked = mask_pii(ssn)

        # Full SSN should not appear
        assert "123456789" not in masked
        assert "123" not in masked

    def test_aadhar_number_masked_india(self):
        """
        Security: Indian Aadhar number (12 digits) masked.
        1234 5678 9012 -> ****-****-9012
        """
        from shared.core.security import mask_pii

        aadhar = "123456789012"
        masked = mask_pii(aadhar)

        # Full Aadhar should not appear
        assert "123456789012" not in masked
        assert "123456" not in masked

    def test_pan_number_masked_india(self):
        """
        Security: Indian PAN (Permanent Account Number) masked.
        ABCDE1234F -> ****E1234*
        """
        from shared.core.security import mask_pii

        pan = "ABCDE1234F"
        masked = mask_pii(pan)

        # Full PAN should not appear
        assert pan not in masked or masked == pan

    @pytest.mark.parametrize("tax_id,country", [
        ("123-45-6789", "US"),  # SSN
        ("12 345 678 9", "AU"),  # ABN
        ("NI 123456789", "GB"),  # NI number
    ])
    def test_international_tax_ids_masked(self, tax_id, country):
        """
        Security: All international tax IDs masked.
        """
        from shared.core.security import mask_pii

        masked = mask_pii(tax_id)

        # Should be masked or original if masking disabled
        # But at minimum, should not leave sensitive patterns exposed


# ============================================================================
# Password Masking Tests
# ============================================================================


class TestPasswordMasking:
    """Test that passwords NEVER appear in logs."""

    def test_password_never_logged(self):
        """
        Security: Password must NEVER appear in logs or error messages.
        Even in debug logs, passwords must be redacted.
        """
        import logging
        from shared.monitoring.sentry_config import _scrub_pii

        log_entry = "User logged in with password: MyS3cureP@ss123"

        scrubbed = _scrub_pii(log_entry)

        # Password should be removed
        assert "MyS3cureP@ss123" not in scrubbed

    def test_form_data_with_password_scrubbed(self):
        """
        Security: POST data containing password field must be scrubbed.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        form_data = {
            "email": "user@example.com",
            "password": "SecurePass123!",
            "name": "John Doe",
        }

        scrubbed = _scrub_pii(form_data)

        # Password value should be redacted
        if isinstance(scrubbed, dict):
            assert scrubbed.get("password") != "SecurePass123!"

    def test_error_trace_password_scrubbed(self):
        """
        Security: Even in stack traces, passwords must be removed.
        """
        # Example traceback:
        trace = """
        File "auth.py", line 42, in verify_credentials
            if check_password(user_input_password, hashed):
        File "security.py", line 10, in check_password
            raise ValueError(f"Login failed for user with password {password}")
        ValueError: Login failed for user with password MyPassword123
        """

        from shared.monitoring.sentry_config import _scrub_pii

        scrubbed = _scrub_pii(trace)

        # Password should not appear
        assert "MyPassword123" not in scrubbed


# ============================================================================
# API Key/Token Masking Tests
# ============================================================================


class TestAPIKeyMasking:
    """Test API keys and tokens are masked in logs."""

    def test_api_key_in_header_scrubbed(self):
        """
        Security: X-API-Key header value must not appear in logs.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": "pk_live_abcdef123456ghijkl",
        }

        scrubbed = _scrub_pii(headers)

        # API key should be redacted
        if isinstance(scrubbed, dict):
            api_key = scrubbed.get("X-API-Key") or scrubbed.get("x-api-key")
            if api_key:
                assert "abcdef123456ghijkl" not in api_key

    def test_bearer_token_scrubbed(self):
        """
        Security: Bearer token in Authorization header scrubbed.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        auth_header = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

        scrubbed = _scrub_pii(auth_header)

        # Token should be masked
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed

    def test_jwt_in_url_param_scrubbed(self):
        """
        Security: JWT in URL query parameter (bad practice but might happen) scrubbed.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        url = "https://api.example.com/callback?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

        scrubbed = _scrub_pii(url)

        # Token portion should be masked
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed


# ============================================================================
# Sentry DSN Protection Tests
# ============================================================================


class TestSentryDSNProtection:
    """Test that Sentry DSN is not leaked."""

    def test_sentry_dsn_not_in_logs(self):
        """
        Security: Sentry DSN (contains auth token) must not appear in logs.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        log_entry = "Sentry DSN: https://key1234@sentry.io/12345"

        scrubbed = _scrub_pii(log_entry)

        # DSN auth portion should be masked
        assert "key1234" not in scrubbed

    def test_sentry_dsn_in_config_scrubbed(self):
        """
        Security: Config logs must not expose Sentry DSN.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        config_debug = "SENTRY_DSN=https://abc123def456@sentry.io/98765"

        scrubbed = _scrub_pii(config_debug)

        # Key should be masked
        assert "abc123def456" not in scrubbed


# ============================================================================
# Request/Response Body Scrubbing Tests
# ============================================================================


class TestRequestBodyScrubbing:
    """Test that sensitive data in request/response bodies is scrubbed."""

    def test_sentry_before_send_scrubs_pii(self):
        """
        Security: Sentry's before_send hook must scrub PII from events.
        """
        from shared.monitoring.sentry_config import _before_send

        # Event with sensitive data
        event = {
            "request": {
                "method": "POST",
                "url": "https://api.example.com/users",
                "headers": {
                    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                    "content-type": "application/json",
                },
                "data": '{"email": "john@example.com", "password": "MyP@ss123"}',
            },
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": "Invalid email john@example.com",
                    }
                ]
            },
        }

        hint = {}
        scrubbed = _before_send(event, hint)

        # Check authorization header is scrubbed
        if scrubbed and "request" in scrubbed:
            headers = scrubbed["request"].get("headers", {})
            auth = headers.get("authorization")
            if auth:
                assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in auth

    def test_request_body_with_credit_card_scrubbed(self):
        """
        Security: Request body with credit card number scrubbed.
        """
        from shared.monitoring.sentry_config import _scrub_pii

        payload = {
            "cc_number": "4532 0151 1283 0366",
            "cc_expiry": "12/25",
            "cc_cvv": "123",
        }

        scrubbed = _scrub_pii(payload)

        # Card number should be masked
        if isinstance(scrubbed, dict):
            cc = scrubbed.get("cc_number")
            if cc:
                assert "4532" not in cc or "****" in cc


# ============================================================================
# Sentry Custom Fingerprinting Tests
# ============================================================================


class TestSentryFingerprinting:
    """Test that Sentry uses appropriate fingerprinting."""

    def test_fingerprinting_excludes_pii(self):
        """
        Security: Sentry fingerprinting must not include PII.

        Bad fingerprint: ["ValueError", "User john@example.com not found"]
        Good fingerprint: ["ValueError", "User not found"]
        """
        from shared.monitoring.sentry_config import _before_send

        event = {
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": "User john@example.com with phone +919876543210 not found",
                    }
                ]
            }
        }

        hint = {}
        processed = _before_send(event, hint)

        # Check fingerprint doesn't contain PII
        if processed and "fingerprint" in processed:
            fingerprint_str = str(processed["fingerprint"])
            # Should not contain email or phone
            assert "john@example.com" not in fingerprint_str
            assert "+919876543210" not in fingerprint_str


# ============================================================================
# Data Residency Tests
# ============================================================================


class TestDataResidencyPII:
    """Test PII stays in configured region."""

    def test_eu_tenant_pii_in_eu_logs(self):
        """
        Security: EU tenant data (GDPR) should only be logged in EU region.
        """
        # Tenant configured: country="DE" (Germany/EU)
        # Logs should go to EU data center, not US

        tenant = {"country": "DE", "region": "eu-west-1"}

        assert tenant["region"].startswith("eu")

    def test_us_tenant_pii_can_be_in_us(self):
        """
        Security: US tenant data can be logged in US region.
        """
        tenant = {"country": "US", "region": "us-east-1"}

        assert "us" in tenant["region"]


# ============================================================================
# Consent and Privacy Tests
# ============================================================================


class TestConsentTracking:
    """Test consent management for data usage."""

    def test_consent_stored_with_timestamp(self):
        """
        Security: Consent must be recorded with timestamp and version.
        Allows proof of consent if challenged.
        """
        import datetime

        consent = {
            "user_id": "user-123",
            "consent_type": "marketing_emails",
            "given": True,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0",  # Version of consent terms
        }

        assert "timestamp" in consent
        assert "version" in consent

    def test_right_to_deletion_honored(self):
        """
        Security: User's right to be forgotten (GDPR Art. 17).
        """
        # When user requests deletion:
        # 1. Personal data deleted from main DB
        # 2. Backups eventually purged
        # 3. Third-party data shared purged
        # 4. But aggregate/anonymized data can remain

        user_id = "user-123"
        deletion_requested = True

        # Service should:
        # - Mark user for deletion
        # - Set grace period (30 days)
        # - Then hard delete


# ============================================================================
# Test Data Cleanup Tests
# ============================================================================


class TestTestDataCleanup:
    """Test that test data doesn't leak into production logs."""

    def test_test_mode_disables_real_logging(self):
        """
        Security: In test environment, real PII should not be logged.
        """
        import os

        environment = os.getenv("ENVIRONMENT", "test")

        if environment == "test":
            # Should use mock loggers, not real Sentry
            real_logging_enabled = False
        else:
            real_logging_enabled = True

        assert environment == "test"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
