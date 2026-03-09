"""
Security Utilities — NEVER COMPROMISE

Provides:
- Password hashing (bcrypt, 12 rounds)
- JWT token creation and validation (RS256)
- API key generation and validation
- PII detection and masking
- Rate limiting helpers
- Input sanitization
"""

import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt

from .config import config

logger = logging.getLogger("priya.security")


# ─── Password Hashing ───

def hash_password(password: str) -> str:
    """Hash password with bcrypt. 12 rounds = ~250ms on modern hardware."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=config.security.bcrypt_rounds)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash. Constant-time comparison."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── JWT Tokens (RS256) ───

def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    plan: str,
    permissions: list[str] | None = None,
    extra_claims: dict | None = None,
) -> str:
    """
    Create a short-lived access token (15 min default).

    Claims include tenant_id for RLS enforcement and role for RBAC.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "plan": plan,
        "permissions": permissions or [],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=config.jwt.access_token_expiry)).timestamp()),
        "iss": config.jwt.issuer,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, config.jwt.secret_key, algorithm=config.jwt.algorithm)


def create_refresh_token(user_id: str, tenant_id: str) -> Tuple[str, str]:
    """
    Create a long-lived refresh token (7 days default).
    Returns (token_string, token_hash) — store the hash, send the token.
    """
    token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "jti": token_hash[:16],  # JWT ID for revocation tracking
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=config.jwt.refresh_token_expiry)).timestamp()),
        "iss": config.jwt.issuer,
        "type": "refresh",
    }

    jwt_token = jwt.encode(payload, config.jwt.secret_key, algorithm=config.jwt.algorithm)
    return jwt_token, token_hash


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    Raises jwt.ExpiredSignatureError, jwt.InvalidTokenError on failure.
    """
    return jwt.decode(
        token,
        config.jwt.public_key or config.jwt.secret_key,
        algorithms=[config.jwt.algorithm],
        issuer=config.jwt.issuer,
    )


def validate_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate access token and return claims, or None if invalid."""
    try:
        claims = decode_token(token)
        if claims.get("type") != "access":
            return None
        return claims
    except jwt.ExpiredSignatureError:
        logger.debug("Access token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid access token: %s", str(e))
        return None


# ─── API Key Management ───

def generate_api_key(prefix: str = "pk_live_") -> Tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (full_key, key_prefix, key_hash).
    The full_key is shown once to the user, then only the hash is stored.
    """
    key_body = secrets.token_urlsafe(32)
    full_key = f"{prefix}{key_body}"
    key_prefix = full_key[:12]
    key_hash = bcrypt.hashpw(full_key.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")
    return full_key, key_prefix, key_hash


def verify_api_key(key: str, key_hash: str) -> bool:
    """Verify an API key against its stored hash."""
    return verify_password(key, key_hash)


# ─── PII Detection & Masking ───

# Patterns for common PII
_PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\+?\d[\d\s-]{8,}\d"),
    "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
}


def mask_pii(text: str) -> str:
    """
    Mask PII in text for logging. NEVER log raw PII.

    'john@example.com' → 'j***@e***.com'
    '+91 98765 43210' → '+91 ******* 3210'
    """
    if not config.security.pii_masking_enabled:
        return text

    masked = text
    for pii_type, pattern in _PII_PATTERNS.items():
        for match in pattern.finditer(masked):
            value = match.group()
            if pii_type == "email":
                parts = value.split("@")
                replacement = f"{parts[0][0]}***@{parts[1][0]}***.{parts[1].split('.')[-1]}"
            elif pii_type == "phone":
                digits = re.sub(r"\D", "", value)
                replacement = f"{digits[:3]}****{digits[-4:]}"
            elif pii_type == "credit_card":
                replacement = f"****-****-****-{value[-4:]}"
            else:
                replacement = "***REDACTED***"
            masked = masked.replace(value, replacement)

    return masked


# ─── Input Sanitization ───

def sanitize_input(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input. Remove dangerous characters, limit length.
    Used for all user-facing text inputs.
    """
    if not text:
        return ""
    # Truncate
    text = text[:max_length]
    # Remove null bytes
    text = text.replace("\x00", "")
    # Strip control characters (keep newlines, tabs)
    text = "".join(ch for ch in text if ch in "\n\t\r" or (ord(ch) >= 32 and ord(ch) != 127))
    return text.strip()


def sanitize_email(email: str) -> Optional[str]:
    """Validate and normalize email address."""
    email = email.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return None
    return email


def sanitize_slug(text: str) -> str:
    """Convert text to URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:64]


# ─── Rate Limiting ───

def get_rate_limit(plan: str) -> int:
    """Get rate limit (req/min) based on plan."""
    limits = {
        "trial": config.security.rate_limit_starter,
        "starter": config.security.rate_limit_starter,
        "growth": config.security.rate_limit_growth,
        "enterprise": config.security.rate_limit_enterprise,
    }
    return limits.get(plan, config.security.rate_limit_starter)


# ─── HMAC Webhook Signature ───

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook HMAC-SHA256 signature."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def create_webhook_signature(payload: bytes, secret: str) -> str:
    """Create HMAC-SHA256 signature for outgoing webhooks."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


# ─── Credential Encryption (AES-256-GCM via Fernet) ───

import base64
import json
import os
from cryptography.fernet import Fernet, InvalidToken

# Derive Fernet key from CREDENTIALS_ENCRYPTION_KEY env var
_CREDENTIALS_KEY = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")


def _get_fernet() -> Fernet:
    """Get Fernet cipher for credential encryption.

    CREDENTIALS_ENCRYPTION_KEY must be a 32-byte base64-encoded key.
    Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    if not _CREDENTIALS_KEY:
        env = os.getenv("ENVIRONMENT", "development")
        if env in ("production", "staging"):
            raise RuntimeError(
                "CRITICAL: CREDENTIALS_ENCRYPTION_KEY must be set in production/staging"
            )
        # In development, use a deterministic key (NOT secure — dev only)
        logger.warning("Using insecure dev credential key — set CREDENTIALS_ENCRYPTION_KEY in production")
        dev_key = base64.urlsafe_b64encode(b"dev_only_key_32_bytes_padding!!")
        return Fernet(dev_key)
    return Fernet(_CREDENTIALS_KEY.encode())


def encrypt_credentials(credentials: dict) -> str:
    """Encrypt credential dict to an opaque string for database storage.

    Args:
        credentials: Dict of credentials (API keys, OAuth tokens, etc.)

    Returns:
        Encrypted, base64-encoded string safe for JSONB/text storage.
    """
    plaintext = json.dumps(credentials).encode("utf-8")
    return _get_fernet().encrypt(plaintext).decode("utf-8")


def decrypt_credentials(encrypted: str) -> dict:
    """Decrypt credential string back to dict.

    Args:
        encrypted: The encrypted string from encrypt_credentials()

    Returns:
        Original credentials dict.

    Raises:
        ValueError: If decryption fails (wrong key or tampered data).
    """
    try:
        plaintext = _get_fernet().decrypt(encrypted.encode("utf-8"))
        return json.loads(plaintext.decode("utf-8"))
    except InvalidToken:
        logger.error("credential_decryption_failed — wrong key or tampered data")
        raise ValueError("Failed to decrypt credentials — encryption key mismatch or data corrupted")
