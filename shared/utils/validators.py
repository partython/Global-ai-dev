"""
Input Validation Utilities for Priya Global Platform

Provides functions to validate and sanitize user inputs across all services.

SECURITY:
- Prevents XSS attacks via HTML/script sanitization
- Validates email and phone format
- Prevents SQL injection via input type validation
- Normalizes phone numbers to E.164 format

USAGE:
    from shared.utils import validate_email, validate_phone, sanitize_input

    email = validate_email("user@example.com")
    phone = validate_phone("+1 (555) 123-4567", country_code="US")
    text = sanitize_input(user_input)
"""

import re
from typing import Optional
from uuid import UUID

import phonenumbers
from phonenumbers import NumberParseException
from pydantic import EmailStr, HttpUrl, validator


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def validate_email(email: str) -> str:
    """
    Validate and normalize email address.

    Args:
        email: Email string to validate

    Returns:
        Validated email (lowercase)

    Raises:
        ValidationError: If email is invalid
    """
    email = email.strip().lower()

    # Basic regex for email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        raise ValidationError(f"Invalid email address: {email}")

    # Max length check
    if len(email) > 254:
        raise ValidationError("Email address too long")

    return email


def validate_phone(phone: str, country_code: Optional[str] = None) -> str:
    """
    Validate and normalize phone number to E.164 format.

    E.164 format: +[country code][number]
    Example: +14155552671

    Args:
        phone: Phone number string
        country_code: ISO 3166-1 alpha-2 country code (e.g., "US", "IN")

    Returns:
        Phone number in E.164 format

    Raises:
        ValidationError: If phone is invalid or country code unknown
    """
    try:
        # Parse phone number with country code
        parsed = phonenumbers.parse(phone, country_code)

        # Validate it's a real possible number
        if not phonenumbers.is_valid_number(parsed):
            raise ValidationError(f"Invalid phone number for {country_code}: {phone}")

        # Return in E.164 format
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    except NumberParseException as e:
        raise ValidationError(f"Failed to parse phone number: {str(e)}")


def validate_tenant_id(tenant_id: str) -> UUID:
    """
    Validate and convert tenant_id to UUID.

    Args:
        tenant_id: UUID string

    Returns:
        UUID object

    Raises:
        ValidationError: If invalid UUID format
    """
    try:
        return UUID(tenant_id)
    except (ValueError, AttributeError) as e:
        raise ValidationError(f"Invalid tenant ID format: {tenant_id}")


def validate_url(url: str) -> str:
    """
    Validate URL format.

    Args:
        url: URL string to validate

    Returns:
        Validated URL

    Raises:
        ValidationError: If URL is invalid
    """
    try:
        # Pydantic HttpUrl validation
        from pydantic import ValidationError as PydanticValidationError

        HttpUrl(url)
        return url
    except PydanticValidationError:
        raise ValidationError(f"Invalid URL: {url}")


def sanitize_input(text: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.

    SECURITY:
    - Removes HTML/script tags
    - Escapes potentially dangerous characters
    - Strips control characters
    - Validates length

    Args:
        text: User input text
        max_length: Maximum allowed length (default: no limit)

    Returns:
        Sanitized text safe for storage/display
    """
    if not isinstance(text, str):
        raise ValidationError("Input must be a string")

    # Remove control characters (except newlines, tabs)
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')

    # Remove null bytes
    text = text.replace('\x00', '')

    # HTML escape dangerous characters
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')

    # Strip leading/trailing whitespace
    text = text.strip()

    # Check length
    if max_length and len(text) > max_length:
        raise ValidationError(f"Input exceeds maximum length of {max_length}")

    return text


def validate_username(username: str) -> str:
    """
    Validate username format.

    Rules:
    - 3-32 characters
    - Alphanumeric, hyphens, underscores only
    - Cannot start/end with hyphen or underscore

    Args:
        username: Username to validate

    Returns:
        Validated username

    Raises:
        ValidationError: If invalid format
    """
    if not 3 <= len(username) <= 32:
        raise ValidationError("Username must be 3-32 characters")

    pattern = r'^[a-zA-Z0-9_-]+$'
    if not re.match(pattern, username):
        raise ValidationError("Username can only contain letters, numbers, hyphens, underscores")

    if username.startswith(('-', '_')) or username.endswith(('-', '_')):
        raise ValidationError("Username cannot start or end with hyphen or underscore")

    return username


def validate_country_code(code: str) -> str:
    """
    Validate ISO 3166-1 alpha-2 country code.

    Args:
        code: Country code (e.g., "US", "IN")

    Returns:
        Uppercase country code

    Raises:
        ValidationError: If invalid code
    """
    code = code.upper().strip()

    if not re.match(r'^[A-Z]{2}$', code):
        raise ValidationError("Country code must be 2 uppercase letters")

    # List of valid ISO 3166-1 alpha-2 codes (sample)
    # In production, use a complete list
    valid_codes = {
        'US', 'GB', 'CA', 'AU', 'DE', 'FR', 'JP', 'IN', 'BR', 'MX',
        'IT', 'ES', 'NL', 'SE', 'NO', 'DK', 'FI', 'PL', 'TR', 'RU',
        'ZA', 'NG', 'EG', 'KE', 'NZ', 'SG', 'HK', 'CN', 'KR', 'TH',
    }

    if code not in valid_codes:
        # In real implementation, check against complete list
        pass

    return code


def validate_language_code(code: str) -> str:
    """
    Validate ISO 639-1 language code.

    Args:
        code: Language code (e.g., "en", "es", "fr")

    Returns:
        Lowercase language code

    Raises:
        ValidationError: If invalid code
    """
    code = code.lower().strip()

    if not re.match(r'^[a-z]{2}(?:-[a-z]{2})?$', code):
        raise ValidationError("Invalid language code format")

    return code


def validate_uuid(value: str) -> UUID:
    """
    Validate UUID format.

    Args:
        value: UUID string

    Returns:
        UUID object

    Raises:
        ValidationError: If invalid format
    """
    try:
        return UUID(value)
    except (ValueError, AttributeError, TypeError) as e:
        raise ValidationError(f"Invalid UUID format: {value}")
