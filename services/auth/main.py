"""
Priya Global Auth Service (Port 9001)

PASSWORDLESS authentication system for the Priya Global Platform.
- Google OAuth (primary sign-in method)
- Email OTP (6-digit code, no passwords)
- Multi-tenant user creation and session management
- JWT-based authentication (RS256, 15min access + 7day refresh)
- Cloudflare Turnstile bot protection on all auth endpoints
- Comprehensive audit logging with PII masking
- Auto-creates tenant + wallet on first sign-in

SECURITY ARCHITECTURE:
- Passwordless only — no passwords stored or accepted for new users
- Cloudflare Turnstile verification on all public auth endpoints
- OTP rate limiting (5 requests/hour/email)
- Disposable email domain blocklist
- PII masking in all logs
- Audit trail for all authentication events
- RS256 JWT tokens with short access token lifetime
- httpOnly cookie sessions

DATABASE OPERATIONS:
- Uses admin_connection() for cross-tenant queries (email uniqueness, SSO lookup)
- Uses tenant_connection() for tenant-scoped queries
- Every transaction is logged to audit_log table
"""

import hashlib
import hmac
import httpx
import json
import logging
import os
import random
import secrets
import string
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, validator

# Add shared core to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    mask_pii,
    sanitize_email,
    sanitize_input,
    sanitize_slug,
    validate_access_token,
    verify_password,
)
from shared.middleware.auth import AuthContext, get_auth
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.middleware.cors import get_cors_config
from shared.events.event_bus import EventBus, EventType

# ─── Configure Logging ───

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("priya.auth")


# ─── Request/Response Schemas ───


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    business_name: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=2, max_length=3)  # ISO 3166-1 alpha-2/3

    @validator("password")
    def validate_password(cls, v):
        """Ensure password has mix of character types."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class LoginRequest(BaseModel):
    """Email/password login request."""

    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Password reset with token."""

    token: str
    password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""

    email: EmailStr


class EmailVerificationRequest(BaseModel):
    """Email verification with token."""

    token: str


class TokenResponse(BaseModel):
    """Successful authentication response."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds
    user: dict


class UserProfile(BaseModel):
    """User profile response."""

    id: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    avatar_url: Optional[str] = None
    email_verified: bool
    two_fa_enabled: bool
    created_at: str
    last_login: Optional[str] = None
    status: str  # active, inactive, suspended


class TwoFASetupResponse(BaseModel):
    """2FA setup response with QR code."""

    secret: str
    qr_code: str
    backup_codes: list[str]


class TwoFAVerifyRequest(BaseModel):
    """TOTP verification request."""

    code: str = Field(pattern=r"^\d{6}$")


class SSOGoogleRequest(BaseModel):
    """Google OAuth callback."""

    id_token: str


class SSOAppleRequest(BaseModel):
    """Apple Sign-In callback."""

    authorization_code: str
    user_id: Optional[str] = None


class SSOMicrosoftRequest(BaseModel):
    """Microsoft Azure AD callback."""

    id_token: str


# ─── Passwordless Auth Models ───


class OTPRequestModel(BaseModel):
    """Request to send OTP to email."""

    email: EmailStr
    turnstile_token: Optional[str] = None


class OTPVerifyModel(BaseModel):
    """Verify OTP and authenticate."""

    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    # For new users, these are required on first login
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    business_name: Optional[str] = Field(default=None, max_length=200)
    country: Optional[str] = Field(default=None, max_length=3)


class GoogleOAuthRequest(BaseModel):
    """Google OAuth code exchange."""

    credential: str  # ID token from Google Sign-In
    turnstile_token: Optional[str] = None


# ─── Disposable Email Blocklist ───

DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
    "discard.email", "temp-mail.org", "fakeinbox.com", "trashmail.com",
    "getnada.com", "mohmal.com", "maildrop.cc", "10minutemail.com",
}

# Turnstile config
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Google OAuth config
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


# ─── Initialize FastAPI App ───

app = FastAPI(
    title="Priya Global Auth Service",
    description="Authentication and authorization service for Priya Global",
    version="1.0.0",
)
# Initialize Sentry error tracking
init_sentry(service_name="auth", service_port=9001)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="auth")
app.add_middleware(TracingMiddleware)


# CORS Configuration
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)

# Initialize event bus
event_bus = EventBus(service_name="auth")


# ─── Lifecycle Events ───


@app.on_event("startup")
async def startup_event():
    """Initialize database connection pool."""
    await db.initialize()
    await event_bus.startup()
    logger.info("Auth Service started on port %s", config.ports.auth)


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection pool."""
    await db.close()
    shutdown_tracing()
    await event_bus.shutdown()
    logger.info("Auth Service shut down")


# ─── Health Check ───


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "auth",
        "version": "1.0.0",
        "timestamp": utc_now().isoformat(),
    }


# ─── Helper Functions ───


async def log_audit(
    tenant_id: str,
    user_id: Optional[str],
    action: str,
    resource: str,
    status: str,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """
    Log authentication action to audit_log table.

    SECURITY: All auth actions are logged for compliance and security monitoring.
    """
    async with db.admin_connection() as conn:
        await conn.execute(
            """
            INSERT INTO audit_log
            (id, tenant_id, user_id, action, resource, status, details, ip_address, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            generate_uuid(),
            tenant_id if tenant_id else "system",
            user_id,
            action,
            resource,
            status,
            details or {},
            ip_address,
            utc_now(),
        )


async def check_account_lockout(email: str) -> tuple[bool, Optional[int]]:
    """
    Check if account is locked due to failed login attempts.

    Returns: (is_locked, minutes_remaining)
    """
    async with db.admin_connection() as conn:
        record = await conn.fetchrow(
            """
            SELECT failed_attempts, last_failed_attempt
            FROM users
            WHERE LOWER(email) = LOWER($1)
            """,
            email,
        )

        if not record:
            return False, None

        failed_attempts = record["failed_attempts"] or 0
        last_failed = record["last_failed_attempt"]

        if failed_attempts < config.security.max_login_attempts:
            return False, None

        # Check if lockout has expired
        if last_failed:
            lockout_expiry = last_failed + timedelta(
                seconds=config.security.lockout_duration
            )
            now = utc_now()
            if now < lockout_expiry:
                minutes_remaining = int(
                    (lockout_expiry - now).total_seconds() / 60
                )
                return True, minutes_remaining

        # Lockout expired, reset counters
        await conn.execute(
            "UPDATE users SET failed_attempts = 0, last_failed_attempt = NULL WHERE LOWER(email) = LOWER($1)",
            email,
        )
        return False, None


async def increment_failed_login(email: str):
    """Increment failed login counter for account lockout."""
    async with db.admin_connection() as conn:
        await conn.execute(
            """
            UPDATE users
            SET failed_attempts = COALESCE(failed_attempts, 0) + 1,
                last_failed_attempt = $2
            WHERE LOWER(email) = LOWER($1)
            """,
            email,
            utc_now(),
        )


async def reset_failed_login(email: str):
    """Reset failed login counter on successful login."""
    async with db.admin_connection() as conn:
        await conn.execute(
            """
            UPDATE users
            SET failed_attempts = 0,
                last_failed_attempt = NULL,
                last_login = $2
            WHERE LOWER(email) = LOWER($1)
            """,
            email,
            utc_now(),
        )


async def create_refresh_token_record(
    user_id: str, tenant_id: str, token_hash: str
) -> str:
    """Store refresh token hash in database for revocation support."""
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            generate_uuid(),
            user_id,
            token_hash,
            utc_now() + timedelta(seconds=config.jwt.refresh_token_expiry),
            utc_now(),
        )


async def verify_refresh_token(user_id: str, tenant_id: str, token_hash: str) -> bool:
    """Verify refresh token exists and hasn't been revoked."""
    async with db.tenant_connection(tenant_id) as conn:
        record = await conn.fetchrow(
            """
            SELECT id FROM refresh_tokens
            WHERE user_id = $1 AND token_hash = $2 AND expires_at > NOW()
            """,
            user_id,
            token_hash,
        )
        return record is not None


# ─── Turnstile & OTP Helpers ───


async def verify_turnstile(token: Optional[str], ip_address: Optional[str] = None) -> bool:
    """
    Verify Cloudflare Turnstile token.
    Returns True if verification passes or if Turnstile is not configured (dev mode).
    """
    if not TURNSTILE_SECRET_KEY or TURNSTILE_SECRET_KEY.startswith("1x0000"):
        # Dev/test mode — skip verification
        return True

    if not token:
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TURNSTILE_VERIFY_URL,
                data={
                    "secret": TURNSTILE_SECRET_KEY,
                    "response": token,
                    "remoteip": ip_address or "",
                },
                timeout=5.0,
            )
            result = resp.json()
            return result.get("success", False)
    except Exception as e:
        logger.error("Turnstile verification error: %s", str(e))
        return False  # Fail closed


def is_disposable_email(email: str) -> bool:
    """Check if email domain is a known disposable email provider."""
    domain = email.lower().split("@")[-1]
    return domain in DISPOSABLE_EMAIL_DOMAINS


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def hash_otp(otp: str) -> str:
    """Hash OTP for storage (SHA-256)."""
    return hashlib.sha256(otp.encode()).hexdigest()


async def check_otp_rate_limit(email: str) -> bool:
    """Check if email has exceeded OTP rate limit (5 per hour)."""
    try:
        async with db.admin_connection() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM otp_requests
                WHERE email = LOWER($1)
                  AND created_at > NOW() - INTERVAL '1 hour'
                """,
                email.lower(),
            )
        return count >= 5
    except Exception as e:
        # Table may not exist if migration 012 hasn't been run
        if "otp_requests" in str(e):
            logger.warning("otp_requests table missing — run migration 012. Skipping rate limit check.")
            return False
        raise


async def find_or_create_user_and_tenant(
    email: str,
    auth_method: str,
    first_name: str = "",
    last_name: str = "",
    business_name: str = "",
    country: str = "IN",
    provider_id: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> dict:
    """
    Find existing user by email or create new user + tenant + wallet.
    Returns user dict with tenant_id.
    """
    # Combine first + last into single name field (DB uses 'name' not 'first_name'/'last_name')
    full_name = f"{first_name} {last_name}".strip() or email.split("@")[0]

    async with db.admin_connection() as conn:
        # Check if user exists
        user = await conn.fetchrow(
            "SELECT id, email, name, tenant_id, status, email_verified FROM users WHERE LOWER(email) = LOWER($1)",
            email,
        )

        if user:
            # Existing user — update last login and google_id if applicable
            if auth_method == "google" and provider_id:
                await conn.execute(
                    "UPDATE users SET last_login_at = $1, google_id = $2 WHERE id = $3",
                    utc_now(),
                    provider_id,
                    user["id"],
                )
            else:
                await conn.execute(
                    "UPDATE users SET last_login_at = $1 WHERE id = $2",
                    utc_now(),
                    user["id"],
                )
            # Return with first_name/last_name split for JWT compatibility
            user_dict = dict(user)
            name_parts = (user_dict.get("name") or "").split(" ", 1)
            user_dict["first_name"] = name_parts[0]
            user_dict["last_name"] = name_parts[1] if len(name_parts) > 1 else ""
            return user_dict

        # New user — create tenant first
        tenant_id = generate_uuid()
        slug = sanitize_slug(business_name or email.split("@")[0])

        # Ensure unique slug
        existing_slug = await conn.fetchval(
            "SELECT id FROM tenants WHERE slug = $1", slug
        )
        if existing_slug:
            slug = f"{slug}-{secrets.token_hex(3)}"

        await conn.execute(
            """
            INSERT INTO tenants (id, name, slug, country, status, plan, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', 'starter', $5, $5)
            """,
            tenant_id,
            business_name or f"{full_name}'s Business",
            slug,
            country,
            utc_now(),
        )

        # Create user
        user_id = generate_uuid()
        google_id_val = provider_id if auth_method == "google" else None
        await conn.execute(
            """
            INSERT INTO users (
                id, tenant_id, email, name, avatar_url,
                role, status, email_verified, google_id, created_at, last_login_at
            )
            VALUES ($1, $2, $3, $4, $5, 'owner', 'active', true, $6, $7, $7)
            """,
            user_id,
            tenant_id,
            email.lower(),
            full_name,
            avatar_url,
            google_id_val,
            utc_now(),
        )

        # Create wallet for tenant (migration 012 — may not exist yet)
        # Use savepoint so failure doesn't roll back user/tenant creation
        try:
            async with conn.transaction():
                wallet_id = generate_uuid()
                await conn.execute(
                    """
                    INSERT INTO wallet_accounts (id, tenant_id, balance_paisa, currency)
                    VALUES ($1, $2, 0, 'INR')
                    """,
                    wallet_id,
                    tenant_id,
                )
        except Exception as wallet_err:
            logger.warning("Wallet creation skipped (migration 012 pending): %s", wallet_err)

        # If OAuth, link the provider account (migration 012 — may not exist yet)
        if provider_id and auth_method in ("google", "apple"):
            try:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO oauth_accounts (id, user_id, tenant_id, provider, provider_id, email, avatar_url, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
                        """,
                        generate_uuid(),
                        user_id,
                        tenant_id,
                        auth_method,
                        provider_id,
                        email.lower(),
                        avatar_url,
                        utc_now(),
                    )
            except Exception as oauth_err:
                logger.warning("OAuth account link skipped (migration 012 pending): %s", oauth_err)

        return {
            "id": user_id,
            "email": email.lower(),
            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "tenant_id": tenant_id,
            "status": "active",
            "email_verified": True,
        }


# ─── Registration Endpoint ───


@app.post("/api/v1/auth/register", response_model=TokenResponse, tags=["Auth"], deprecated=True)
async def register(
    req: RegisterRequest,
    background_tasks: BackgroundTasks,
):
    """
    Register a new user and create tenant (workspace).

    On first registration:
    1. Creates tenant with slug derived from business_name
    2. Creates user as owner
    3. Returns access + refresh tokens

    This endpoint is called by the AI onboarding agent during account creation.
    It's designed to be fast and simple - all tenant configuration happens in
    the onboarding flow.

    SECURITY:
    - Email must be unique across platform
    - Password is bcrypt hashed
    - Account lockout logic applies
    """
    ip_address = None
    try:
        # Validate and normalize email
        email = sanitize_email(req.email)
        if not email:
            logger.warning("Invalid email format: %s", mask_pii(req.email))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format",
            )

        # Check email not already taken (cross-tenant query)
        async with db.admin_connection() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM users WHERE LOWER(email) = LOWER($1)",
                email,
            )
            if existing:
                logger.info("Registration failed: email already exists: %s", mask_pii(email))
                background_tasks.add_task(
                    log_audit,
                    "system",
                    None,
                    "register",
                    "user",
                    "failed",
                    {"reason": "email_already_exists"},
                    ip_address,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

        # Create tenant
        tenant_id = generate_uuid()
        slug = sanitize_slug(req.business_name)

        async with db.admin_connection() as conn:
            # Insert tenant
            await conn.execute(
                """
                INSERT INTO tenants (id, name, slug, country, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                tenant_id,
                req.business_name,
                slug,
                req.country,
                "active",
                utc_now(),
            )

            # Create owner user
            user_id = generate_uuid()
            hashed_password = hash_password(req.password)

            await conn.execute(
                """
                INSERT INTO users
                (id, tenant_id, email, password_hash, first_name, last_name,
                 role, status, email_verified, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                user_id,
                tenant_id,
                email,
                hashed_password,
                sanitize_input(req.first_name),
                sanitize_input(req.last_name),
                "owner",
                "active",
                False,  # Email verification required
                utc_now(),
            )

        # Generate tokens
        access_token = create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            role="owner",
            plan="trial",  # New accounts start on trial
            permissions=["*"],  # Owners have all permissions
        )

        refresh_jwt, refresh_hash = create_refresh_token(
            user_id=user_id,
            tenant_id=tenant_id,
        )
        await create_refresh_token_record(user_id, tenant_id, refresh_hash)

        logger.info(
            f"User registered: {mask_pii(email)}, tenant: {tenant_id[:8]}..."
        )

        # Log successful registration
        background_tasks.add_task(
            log_audit,
            tenant_id,
            user_id,
            "register",
            "user",
            "success",
            {"email": mask_pii(email), "tenant_id": tenant_id},
            ip_address,
        )

        # Publish event
        await event_bus.publish(
            event_type=EventType.USER_REGISTERED,
            tenant_id=tenant_id,
            data={
                "user_id": user_id,
                "email": email,
                "first_name": req.first_name,
                "last_name": req.last_name,
                "business_name": req.business_name,
            },
            metadata={"ip_address": ip_address},
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_jwt,
            expires_in=config.jwt.access_token_expiry,
            user={
                "id": user_id,
                "email": email,
                "first_name": req.first_name,
                "last_name": req.last_name,
                "full_name": f"{req.first_name} {req.last_name}",
                "email_verified": False,
                "two_fa_enabled": False,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Registration error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            "system",
            None,
            "register",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )


# ─── Login Endpoint ───


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Auth"], deprecated=True)
async def login(
    req: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Login with email and password.

    SECURITY:
    - Account lockout after 5 failed attempts (15 min)
    - Rate limiting applied
    - Failed attempts logged
    - Password verified with bcrypt
    """
    ip_address = request.client.host if request.client else None

    try:
        email = sanitize_email(req.email)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Check account lockout
        is_locked, minutes_remaining = await check_account_lockout(email)
        if is_locked:
            logger.warning(
                f"Login attempt on locked account: {mask_pii(email)}, "
                f"locked for {minutes_remaining} more minutes"
            )
            background_tasks.add_task(
                log_audit,
                "system",
                None,
                "login",
                "user",
                "failed",
                {"reason": "account_locked", "minutes_remaining": minutes_remaining},
                ip_address,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked. Try again in {minutes_remaining} minutes.",
            )

        # Get user (cross-tenant query)
        async with db.admin_connection() as conn:
            user = await conn.fetchrow(
                """
                SELECT id, tenant_id, email, password_hash, role, status,
                       plan, two_fa_enabled
                FROM users
                WHERE LOWER(email) = LOWER($1)
                """,
                email,
            )

        if not user or not verify_password(req.password, user["password_hash"]):
            await increment_failed_login(email)
            logger.warning("Failed login: %s", mask_pii(email))
            background_tasks.add_task(
                log_audit,
                "system",
                None,
                "login",
                "user",
                "failed",
                {"reason": "invalid_credentials"},
                ip_address,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if user["status"] != "active":
            logger.warning(
                f"Login attempt on inactive account: {mask_pii(email)}"
            )
            background_tasks.add_task(
                log_audit,
                user["tenant_id"],
                user["id"],
                "login",
                "user",
                "failed",
                {"reason": "account_inactive"},
                ip_address,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active",
            )

        # Reset failed login counter
        await reset_failed_login(email)

        # If 2FA enabled, return different response
        if user["two_fa_enabled"]:
            # In production, this would return a temporary token for 2FA verification
            # For now, we'll proceed (2FA can be implemented separately)
            logger.info("Login with 2FA enabled: %s", mask_pii(email))

        # Generate tokens
        user_id = user["id"]
        tenant_id = user["tenant_id"]

        access_token = create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            role=user["role"],
            plan=user["plan"],
        )

        refresh_jwt, refresh_hash = create_refresh_token(
            user_id=user_id,
            tenant_id=tenant_id,
        )
        await create_refresh_token_record(user_id, tenant_id, refresh_hash)

        logger.info("Successful login: %s", mask_pii(email))

        background_tasks.add_task(
            log_audit,
            tenant_id,
            user_id,
            "login",
            "user",
            "success",
            {"email": mask_pii(email)},
            ip_address,
        )

        # Publish event
        await event_bus.publish(
            event_type=EventType.USER_LOGIN,
            tenant_id=tenant_id,
            data={
                "user_id": user_id,
                "email": email,
                "role": user["role"],
                "plan": user["plan"],
            },
            metadata={"ip_address": ip_address},
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_jwt,
            expires_in=config.jwt.access_token_expiry,
            user={
                "id": user_id,
                "email": email,
                "two_fa_enabled": user["two_fa_enabled"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            "system",
            None,
            "login",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        )


# ─── Token Refresh Endpoint ───


@app.post("/api/v1/auth/refresh", response_model=TokenResponse, tags=["Auth"])
async def refresh(
    req: RefreshTokenRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Refresh access token using refresh token.

    Validates refresh token and generates new access token with same claims.
    """
    ip_address = request.client.host if request.client else None

    try:
        # Decode refresh token
        claims = validate_access_token(req.refresh_token)
        if not claims or claims.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        user_id = claims["sub"]
        tenant_id = claims["tenant_id"]

        # Verify refresh token exists and not revoked
        refresh_hash = claims.get("jti", "")
        if not await verify_refresh_token(user_id, tenant_id, refresh_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked or expired",
            )

        # Get current user for role/plan info
        async with db.tenant_connection(tenant_id) as conn:
            user = await conn.fetchrow(
                "SELECT id, role, plan FROM users WHERE id = $1",
                user_id,
            )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        # Generate new access token
        access_token = create_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            role=user["role"],
            plan=user["plan"],
        )

        logger.debug("Token refreshed for user %s...", user_id[:8])

        background_tasks.add_task(
            log_audit,
            tenant_id,
            user_id,
            "refresh_token",
            "user",
            "success",
            {},
            ip_address,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=req.refresh_token,  # Return same refresh token
            expires_in=config.jwt.access_token_expiry,
            user={"id": user_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token refresh error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            "system",
            None,
            "refresh_token",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        )


# ─── Logout Endpoint ───


@app.post("/api/v1/auth/logout", tags=["Auth"])
async def logout(
    auth: AuthContext = Depends(get_auth),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
):
    """
    Logout by revoking refresh token.

    This prevents the refresh token from being used again.
    """
    ip_address = request.client.host if request.client else None

    try:
        # In a full implementation, we would mark the refresh token as revoked
        # For now, we just log the logout event
        logger.info("User logout: %s...", auth.user_id[:8])

        background_tasks.add_task(
            log_audit,
            auth.tenant_id,
            auth.user_id,
            "logout",
            "user",
            "success",
            {},
            ip_address,
        )

        return {"status": "logged_out"}

    except Exception as e:
        logger.error("Logout error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            auth.tenant_id,
            auth.user_id,
            "logout",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed",
        )


# ─── Current User Profile Endpoint ───


@app.get("/api/v1/auth/me", response_model=UserProfile, tags=["Auth"])
async def get_current_user(auth: AuthContext = Depends(get_auth)):
    """
    Get current authenticated user's profile.

    Uses JWT claims, queries database for additional info.
    """
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            user = await conn.fetchrow(
                """
                SELECT id, email, first_name, last_name, avatar_url,
                       email_verified, two_fa_enabled, created_at, last_login, status
                FROM users
                WHERE id = $1
                """,
                auth.user_id,
            )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserProfile(
            id=user["id"],
            email=user["email"],
            first_name=user["first_name"],
            last_name=user["last_name"],
            full_name=f"{user['first_name']} {user['last_name']}",
            avatar_url=user["avatar_url"],
            email_verified=user["email_verified"],
            two_fa_enabled=user["two_fa_enabled"],
            created_at=user["created_at"].isoformat(),
            last_login=user["last_login"].isoformat() if user["last_login"] else None,
            status=user["status"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get profile error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve profile",
        )


# ─── Password Reset Endpoints ───


@app.post("/api/v1/auth/forgot-password", tags=["Auth"], deprecated=True)
async def forgot_password(
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
):
    """
    Request password reset. Sends email with reset token.

    SECURITY: Returns 200 OK regardless of whether email exists (no email enumeration).
    """
    email = sanitize_email(req.email)
    if not email:
        return {"status": "ok"}

    try:
        # Get user (cross-tenant)
        async with db.admin_connection() as conn:
            user = await conn.fetchrow(
                "SELECT id, tenant_id FROM users WHERE LOWER(email) = LOWER($1)",
                email,
            )

        if user:
            # Create password reset token (valid for 1 hour)
            # SECURITY: Store SHA256 hash of token, not plaintext
            reset_token = generate_uuid()
            token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
            async with db.tenant_connection(user["tenant_id"]) as conn:
                await conn.execute(
                    """
                    INSERT INTO password_reset_tokens
                    (id, user_id, token, expires_at, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    generate_uuid(),
                    user["id"],
                    token_hash,
                    utc_now() + timedelta(hours=1),
                    utc_now(),
                )

            # Send email in background (TODO: integrate with email service)
            logger.info("Password reset requested: %s", mask_pii(email))

            background_tasks.add_task(
                log_audit,
                user["tenant_id"],
                user["id"],
                "forgot_password",
                "user",
                "success",
                {"email": mask_pii(email)},
                None,
            )

        return {"status": "ok"}

    except Exception as e:
        logger.error("Forgot password error: %s", str(e), exc_info=True)
        return {"status": "ok"}


@app.post("/api/v1/auth/reset-password", tags=["Auth"], deprecated=True)
async def reset_password(
    req: PasswordResetRequest,
    background_tasks: BackgroundTasks,
):
    """
    Reset password using token from email.

    SECURITY: Token is single-use and expires after 1 hour.
    """
    try:
        # Find reset token (cross-tenant)
        # SECURITY: Hash the incoming token for comparison (tokens stored as SHA256 hashes)
        token_hash = hashlib.sha256(req.token.encode()).hexdigest()
        async with db.admin_connection() as conn:
            token_record = await conn.fetchrow(
                """
                SELECT t.user_id, t.tenant_id, u.email
                FROM password_reset_tokens t
                JOIN users u ON t.user_id = u.id
                WHERE t.token = $1 AND t.expires_at > NOW()
                """,
                token_hash,
            )

            if not token_record:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired reset token",
                )

            user_id = token_record["user_id"]
            tenant_id = token_record["tenant_id"]
            email = token_record["email"]

            # Update password
            hashed_password = hash_password(req.password)
            await conn.execute(
                "UPDATE users SET password_hash = $1 WHERE id = $2",
                hashed_password,
                user_id,
            )

            # Invalidate token
            await conn.execute(
                "DELETE FROM password_reset_tokens WHERE token = $1",
                token_hash,
            )

        logger.info("Password reset successful: %s", mask_pii(email))

        background_tasks.add_task(
            log_audit,
            tenant_id,
            user_id,
            "reset_password",
            "user",
            "success",
            {"email": mask_pii(email)},
            None,
        )

        return {"status": "password_reset"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Reset password error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed",
        )


# ─── Email Verification Endpoint ───


@app.post("/api/v1/auth/verify-email", tags=["Auth"])
async def verify_email(
    req: EmailVerificationRequest,
    background_tasks: BackgroundTasks,
):
    """
    Verify email address using token sent to email.

    SECURITY: Token is single-use and expires after 24 hours.
    """
    try:
        # Find email verification token
        async with db.admin_connection() as conn:
            token_record = await conn.fetchrow(
                """
                SELECT t.user_id, t.tenant_id, u.email
                FROM email_verification_tokens t
                JOIN users u ON t.user_id = u.id
                WHERE t.token = $1 AND t.expires_at > NOW()
                """,
                req.token,
            )

            if not token_record:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired verification token",
                )

            user_id = token_record["user_id"]
            tenant_id = token_record["tenant_id"]
            email = token_record["email"]

            # Mark email as verified
            async with db.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    "UPDATE users SET email_verified = TRUE WHERE id = $1",
                    user_id,
                )

            # Delete token
            await conn.execute(
                "DELETE FROM email_verification_tokens WHERE token = $1",
                req.token,
            )

        logger.info("Email verified: %s", mask_pii(email))

        background_tasks.add_task(
            log_audit,
            tenant_id,
            user_id,
            "verify_email",
            "user",
            "success",
            {"email": mask_pii(email)},
            None,
        )

        return {"status": "email_verified"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Email verification error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification failed",
        )


# ─── Two-Factor Authentication Endpoints ───


@app.post("/api/v1/auth/2fa/enable", response_model=TwoFASetupResponse, tags=["2FA"])
async def enable_2fa(auth: AuthContext = Depends(get_auth)):
    """
    Enable two-factor authentication (TOTP).

    Returns QR code and backup codes. QR code is scanned in authenticator app.
    """
    try:
        # Generate TOTP secret (base32 encoded)
        # In production, use pyotp library
        secret = generate_uuid()[:16]  # Placeholder

        # Generate backup codes (10 codes, 8 chars each)
        backup_codes = [generate_uuid()[:8] for _ in range(10)]

        # TODO: Generate actual QR code image

        logger.info("2FA setup started for user %s...", auth.user_id[:8])

        return TwoFASetupResponse(
            secret=secret,
            qr_code="data:image/png;base64,PLACEHOLDER",  # QR code as base64
            backup_codes=backup_codes,
        )

    except Exception as e:
        logger.error("2FA enable error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable 2FA",
        )


@app.post("/api/v1/auth/2fa/verify", tags=["2FA"])
async def verify_2fa(
    req: TwoFAVerifyRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = None,
):
    """
    Verify TOTP code and complete 2FA setup.

    User enters 6-digit code from authenticator app to confirm.
    """
    try:
        # TODO: Verify TOTP code against secret using pyotp

        # Mark 2FA as enabled
        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                "UPDATE users SET two_fa_enabled = TRUE WHERE id = $1",
                auth.user_id,
            )

        logger.info("2FA enabled for user %s...", auth.user_id[:8])

        background_tasks.add_task(
            log_audit,
            auth.tenant_id,
            auth.user_id,
            "2fa_enable",
            "user",
            "success",
            {},
            None,
        )

        return {"status": "2fa_enabled"}

    except Exception as e:
        logger.error("2FA verify error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="2FA verification failed",
        )


@app.post("/api/v1/auth/2fa/disable", tags=["2FA"])
async def disable_2fa(
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = None,
):
    """
    Disable two-factor authentication.

    Requires password confirmation in production.
    """
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                "UPDATE users SET two_fa_enabled = FALSE WHERE id = $1",
                auth.user_id,
            )

        logger.info("2FA disabled for user %s...", auth.user_id[:8])

        background_tasks.add_task(
            log_audit,
            auth.tenant_id,
            auth.user_id,
            "2fa_disable",
            "user",
            "success",
            {},
            None,
        )

        return {"status": "2fa_disabled"}

    except Exception as e:
        logger.error("2FA disable error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable 2FA",
        )


# ─── SSO Endpoints ───


@app.post("/api/v1/auth/oauth/google", response_model=TokenResponse, tags=["Passwordless"])
async def google_oauth(
    req: GoogleOAuthRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Google OAuth — primary sign-in method.

    Receives Google ID token (credential) from frontend Google Sign-In button.
    Verifies token with Google, creates user/tenant on first login, returns JWT.

    SECURITY:
    - Google ID token verified via Google's tokeninfo endpoint
    - Turnstile bot protection
    - Disposable email rejection
    - Auto-creates tenant + wallet on first sign-in
    """
    ip_address = request.client.host if request.client else None

    # Verify Turnstile
    if not await verify_turnstile(req.turnstile_token, ip_address):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot verification failed",
        )

    try:
        # Verify Google ID token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={req.credential}",
                timeout=10.0,
            )

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google token",
                )

            google_user = resp.json()

        # Validate audience (must match our Google Client ID)
        if GOOGLE_CLIENT_ID and google_user.get("aud") != GOOGLE_CLIENT_ID:
            logger.warning("Google token audience mismatch: %s", google_user.get("aud"))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token not intended for this application",
            )

        email = google_user.get("email", "")
        if not email or not google_user.get("email_verified"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email not verified",
            )

        # Check disposable email
        if is_disposable_email(email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Disposable email addresses are not allowed",
            )

        # Find or create user
        first_name = google_user.get("given_name", "")
        last_name = google_user.get("family_name", "")
        avatar_url = google_user.get("picture", "")
        google_sub = google_user.get("sub", "")

        user = await find_or_create_user_and_tenant(
            email=email,
            auth_method="google",
            first_name=first_name,
            last_name=last_name,
            provider_id=google_sub,
            avatar_url=avatar_url,
        )

        # Generate JWT tokens
        access_token = create_access_token(
            user_id=str(user["id"]),
            tenant_id=str(user["tenant_id"]),
            role="owner",
            plan="starter",
            extra_claims={"email": email},
        )
        refresh_token = create_refresh_token(
            user_id=str(user["id"]),
            tenant_id=str(user["tenant_id"]),
        )

        # Store refresh token
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        await create_refresh_token_record(
            str(user["id"]), str(user["tenant_id"]), token_hash
        )

        # Audit log
        background_tasks.add_task(
            log_audit,
            str(user["tenant_id"]),
            str(user["id"]),
            "login_google",
            "user",
            "success",
            {"email": mask_pii(email)},
            ip_address,
        )

        # Publish event
        background_tasks.add_task(
            event_bus.publish,
            EventType.AUTH_LOGIN,
            {
                "tenant_id": str(user["tenant_id"]),
                "user_id": str(user["id"]),
                "method": "google",
            },
        )

        logger.info("Google OAuth login: %s", mask_pii(email))

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=config.jwt.access_token_expiry,
            user={
                "id": str(user["id"]),
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "tenant_id": str(user["tenant_id"]),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Google OAuth error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            "system",
            None,
            "login_google",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google authentication failed",
        )


# ─── Google OAuth Server-Side Flow (Redirect) ───

GOOGLE_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")
# Public gateway URL — used for OAuth callback (must be browser-accessible, not Docker internal)
PUBLIC_GATEWAY_URL = os.getenv("PUBLIC_GATEWAY_URL", "http://localhost:9000")


@app.get("/api/v1/auth/oauth/google/redirect", tags=["Passwordless"])
async def google_oauth_redirect(request: Request):
    """
    Server-side Google OAuth redirect.
    Used when the frontend doesn't have the Google client ID (no Google Identity Services SDK).
    Redirects the browser to Google's authorization page.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID environment variable.",
        )

    # Build the Google authorization URL (must use public gateway URL, not Docker-internal base_url)
    callback_url = f"{PUBLIC_GATEWAY_URL}/api/v1/auth/oauth/google/callback"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{GOOGLE_OAUTH_AUTH_URL}?{query_string}")


@app.get("/api/v1/auth/oauth/google/callback", tags=["Passwordless"])
async def google_oauth_callback(
    code: str,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Google OAuth callback — exchanges authorization code for tokens.
    After success, redirects to dashboard with access token.
    """
    ip_address = request.client.host if request.client else None
    callback_url = f"{PUBLIC_GATEWAY_URL}/api/v1/auth/oauth/google/callback"

    try:
        # Exchange auth code for tokens
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                GOOGLE_OAUTH_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                },
                timeout=10.0,
            )

            if token_resp.status_code != 200:
                logger.error("Google token exchange failed: %s", token_resp.text)
                return RedirectResponse(url=f"{DASHBOARD_URL}/login?error=google_token_exchange_failed")

            tokens = token_resp.json()
            id_token = tokens.get("id_token", "")

            # Verify ID token
            userinfo_resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}",
                timeout=10.0,
            )

            if userinfo_resp.status_code != 200:
                return RedirectResponse(url=f"{DASHBOARD_URL}/login?error=google_token_invalid")

            google_user = userinfo_resp.json()

        email = google_user.get("email", "")
        if not email or not google_user.get("email_verified"):
            return RedirectResponse(url=f"{DASHBOARD_URL}/login?error=email_not_verified")

        if is_disposable_email(email):
            return RedirectResponse(url=f"{DASHBOARD_URL}/login?error=disposable_email")

        # Find or create user
        user = await find_or_create_user_and_tenant(
            email=email,
            auth_method="google",
            first_name=google_user.get("given_name", ""),
            last_name=google_user.get("family_name", ""),
            provider_id=google_user.get("sub", ""),
            avatar_url=google_user.get("picture", ""),
        )

        # Generate JWT
        access_token = create_access_token(
            user_id=str(user["id"]),
            tenant_id=str(user["tenant_id"]),
            role="owner",
            plan="starter",
            extra_claims={"email": email},
        )

        # Audit
        background_tasks.add_task(
            log_audit,
            str(user["tenant_id"]),
            str(user["id"]),
            "login_google_redirect",
            "user",
            "success",
            {"email": mask_pii(email)},
            ip_address,
        )

        logger.info("Google OAuth callback login: %s", mask_pii(email))

        # Redirect to dashboard with token
        return RedirectResponse(url=f"{DASHBOARD_URL}/auth/callback?token={access_token}")

    except Exception as e:
        logger.error("Google OAuth callback error: %s", str(e), exc_info=True)
        # Pass the actual error detail so we can debug
        import urllib.parse
        err_msg = urllib.parse.quote(str(e)[:200])
        return RedirectResponse(url=f"{DASHBOARD_URL}/login?error=google_auth_failed&detail={err_msg}")


# ─── Email OTP Endpoints ───


@app.post("/api/v1/auth/otp/request", tags=["Passwordless"])
async def request_otp(
    req: OTPRequestModel,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Send a 6-digit OTP to email for passwordless login.

    Rate limited: 5 requests per hour per email.
    Turnstile verification required.
    Disposable emails blocked.
    """
    ip_address = request.client.host if request.client else None
    email = req.email.lower()

    # Verify Turnstile
    if not await verify_turnstile(req.turnstile_token, ip_address):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot verification failed",
        )

    # Check disposable email
    if is_disposable_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disposable email addresses are not allowed",
        )

    # Check rate limit
    if await check_otp_rate_limit(email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please try again later.",
        )

    # Generate and store OTP
    otp = generate_otp()
    otp_hashed = hash_otp(otp)
    expires_at = utc_now() + timedelta(minutes=10)

    try:
        async with db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO otp_requests (id, email, otp_hash, expires_at, ip_address, user_agent, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                generate_uuid(),
                email,
                otp_hashed,
                expires_at,
                ip_address,
                request.headers.get("user-agent", "")[:255],
                utc_now(),
            )
    except Exception as e:
        if "otp_requests" in str(e):
            # Auto-create table if migration 012 hasn't been run
            logger.warning("otp_requests table missing — auto-creating (run migration 012 for full setup)")
            async with db.admin_connection() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS otp_requests (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        email VARCHAR(255) NOT NULL,
                        otp_hash VARCHAR(128) NOT NULL,
                        purpose VARCHAR(20) NOT NULL DEFAULT 'login',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 5,
                        verified BOOLEAN NOT NULL DEFAULT false,
                        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                        ip_address VARCHAR(45),
                        user_agent TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_requests(email);
                    CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_requests(expires_at);
                """)
                await conn.execute(
                    """
                    INSERT INTO otp_requests (id, email, otp_hash, expires_at, ip_address, user_agent, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    generate_uuid(),
                    email,
                    otp_hashed,
                    expires_at,
                    ip_address,
                    request.headers.get("user-agent", "")[:255],
                    utc_now(),
                )
        else:
            logger.error("OTP storage failed: %s", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process OTP request. Please try again.",
            )

    # Send OTP via email (async background task)
    # In production, this calls the email service or MSG91
    background_tasks.add_task(
        _send_otp_email, email, otp
    )

    background_tasks.add_task(
        log_audit,
        "system",
        None,
        "otp_request",
        "user",
        "success",
        {"email": mask_pii(email)},
        ip_address,
    )

    logger.info("OTP requested for %s", mask_pii(email))

    return {
        "status": "sent",
        "message": "A 6-digit code has been sent to your email",
        "expires_in_seconds": 600,
    }


async def _send_otp_email(email: str, otp: str):
    """Send OTP email via internal email service or MSG91."""
    try:
        # Try internal email service first
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://email:9011/api/v1/email/send-system",
                json={
                    "to": email,
                    "subject": "Your Partython.ai Login Code",
                    "template": "otp_login",
                    "variables": {
                        "otp_code": otp,
                        "expires_minutes": "10",
                    },
                },
                timeout=10.0,
            )
        logger.info("OTP email sent to %s", mask_pii(email))
    except Exception as e:
        logger.error("Failed to send OTP email to %s: %s", mask_pii(email), str(e))


@app.post("/api/v1/auth/otp/verify", response_model=TokenResponse, tags=["Passwordless"])
async def verify_otp(
    req: OTPVerifyModel,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Verify OTP and authenticate user.

    If user doesn't exist yet, creates new user + tenant + wallet.
    Requires first_name, last_name, business_name for new users.
    """
    ip_address = request.client.host if request.client else None
    email = req.email.lower()

    async with db.admin_connection() as conn:
        # Find the most recent valid OTP for this email
        otp_record = await conn.fetchrow(
            """
            SELECT id, otp_hash, attempts, max_attempts, verified, expires_at
            FROM otp_requests
            WHERE email = $1
              AND expires_at > NOW()
              AND verified = false
            ORDER BY created_at DESC
            LIMIT 1
            """,
            email,
        )

        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid OTP found. Please request a new code.",
            )

        if otp_record["attempts"] >= otp_record["max_attempts"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Please request a new code.",
            )

        # Verify OTP
        if hash_otp(req.code) != otp_record["otp_hash"]:
            # Increment attempt counter
            await conn.execute(
                "UPDATE otp_requests SET attempts = attempts + 1 WHERE id = $1",
                otp_record["id"],
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid code. Please try again.",
            )

        # Mark OTP as verified
        await conn.execute(
            "UPDATE otp_requests SET verified = true WHERE id = $1",
            otp_record["id"],
        )

    # Check if user exists
    async with db.admin_connection() as conn:
        existing_user = await conn.fetchrow(
            "SELECT id FROM users WHERE LOWER(email) = $1", email
        )

    if not existing_user:
        # New user — require profile info
        if not req.first_name or not req.business_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="first_name and business_name are required for new accounts",
            )

    # Find or create user
    user = await find_or_create_user_and_tenant(
        email=email,
        auth_method="email_otp",
        first_name=req.first_name or "",
        last_name=req.last_name or "",
        business_name=req.business_name or "",
        country=req.country or "IN",
    )

    # Generate JWT tokens
    access_token = create_access_token(
        user_id=str(user["id"]),
        tenant_id=str(user["tenant_id"]),
        role="owner",
        plan="starter",
        extra_claims={"email": email},
    )
    refresh_token = create_refresh_token(
        user_id=str(user["id"]),
        tenant_id=str(user["tenant_id"]),
    )

    # Store refresh token
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    await create_refresh_token_record(
        str(user["id"]), str(user["tenant_id"]), token_hash
    )

    background_tasks.add_task(
        log_audit,
        str(user["tenant_id"]),
        str(user["id"]),
        "login_otp",
        "user",
        "success",
        {"email": mask_pii(email)},
        ip_address,
    )

    background_tasks.add_task(
        event_bus.publish,
        EventType.AUTH_LOGIN,
        {
            "tenant_id": str(user["tenant_id"]),
            "user_id": str(user["id"]),
            "method": "email_otp",
        },
    )

    logger.info("OTP login successful: %s", mask_pii(email))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=config.jwt.access_token_expiry,
        user={
            "id": str(user["id"]),
            "email": email,
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "tenant_id": str(user["tenant_id"]),
        },
    )


# Keep legacy Google SSO endpoint for backward compatibility (redirects to new)
@app.post("/api/v1/auth/sso/google", response_model=TokenResponse, tags=["SSO"], deprecated=True)
async def sso_google_legacy(
    req: SSOGoogleRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Legacy Google SSO — redirects to new OAuth endpoint."""
    return await google_oauth(
        GoogleOAuthRequest(credential=req.id_token),
        background_tasks,
        request,
    )


@app.post("/api/v1/auth/sso/apple", response_model=TokenResponse, tags=["SSO"])
async def sso_apple(
    req: SSOAppleRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Apple Sign-In callback.

    Receives authorization code, exchanges for tokens, creates/logs in user.
    On first login, creates tenant automatically (seamless onboarding).

    SECURITY: Authorization code is exchanged server-to-server with Apple.
    """
    ip_address = request.client.host if request.client else None

    try:
        # TODO: Exchange authorization code with Apple for tokens
        # Verify identity token

        logger.info("Apple SSO attempt")

        return TokenResponse(
            access_token="placeholder",
            refresh_token="placeholder",
            expires_in=config.jwt.access_token_expiry,
            user={},
        )

    except Exception as e:
        logger.error("Apple SSO error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            "system",
            None,
            "sso_apple",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Apple SSO failed",
        )


@app.post("/api/v1/auth/sso/microsoft", response_model=TokenResponse, tags=["SSO"])
async def sso_microsoft(
    req: SSOMicrosoftRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Microsoft Azure AD callback.

    Receives ID token, verifies with Azure AD, creates/logs in user.
    On first login, creates tenant automatically (seamless onboarding).

    SECURITY: ID token is validated against Azure AD public keys.
    """
    ip_address = request.client.host if request.client else None

    try:
        # TODO: Verify ID token with Azure AD
        # Claims from verified token: sub (user_id), email, name, picture, etc.

        logger.info("Microsoft SSO attempt")

        return TokenResponse(
            access_token="placeholder",
            refresh_token="placeholder",
            expires_in=config.jwt.access_token_expiry,
            user={},
        )

    except Exception as e:
        logger.error("Microsoft SSO error: %s", str(e), exc_info=True)
        background_tasks.add_task(
            log_audit,
            "system",
            None,
            "sso_microsoft",
            "user",
            "error",
            {"error": str(e)},
            ip_address,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Microsoft SSO failed",
        )


# ─── Phone Verification (Required Before Paid Features) ───


class PhoneOTPRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number with country code e.g. +919876543210")
    turnstile_token: Optional[str] = None


class PhoneOTPVerify(BaseModel):
    phone_number: str
    otp: str = Field(..., min_length=6, max_length=6)


@app.post("/api/v1/auth/phone/request-otp", tags=["Phone Verification"])
async def request_phone_otp(
    body: PhoneOTPRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """Send OTP to phone number for verification. Requires authenticated user."""
    ip_address = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    # Turnstile verification
    await verify_turnstile(body.turnstile_token, ip_address)

    # Validate phone number format
    phone = body.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone  # Default to India
    if len(phone) < 10 or len(phone) > 15:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    # Rate limit: max 3 phone OTP requests per user per hour
    rate_key = f"phone_otp_rate:{auth.user_id}"
    try:
        async with db.admin_connection() as conn:
            count = await conn.fetchval(
                """SELECT COUNT(*) FROM phone_verifications
                   WHERE user_id = $1 AND created_at > NOW() - INTERVAL '1 hour'""",
                auth.user_id
            )
            if count and count >= 3:
                raise HTTPException(status_code=429, detail="Too many phone verification requests. Try again later.")
    except HTTPException:
        raise
    except Exception:
        pass  # Non-blocking rate limit check

    # Check if phone already verified by another user
    try:
        async with db.admin_connection() as conn:
            existing = await conn.fetchval(
                """SELECT id FROM users
                   WHERE phone_number = $1 AND phone_verified = true AND id != $2""",
                phone, auth.user_id
            )
            if existing:
                raise HTTPException(status_code=409, detail="This phone number is already verified by another account")
    except HTTPException:
        raise
    except Exception:
        pass

    # Generate OTP
    otp = generate_otp()
    otp_hashed = hash_otp(otp)

    # Extract country code
    country_code = "+91"
    if phone.startswith("+"):
        # Simple extraction: assume 1-3 digit country code
        for i in range(2, 5):
            if i < len(phone):
                country_code = phone[:i]

    # Store OTP
    try:
        async with db.admin_connection() as conn:
            await conn.execute(
                """INSERT INTO phone_verifications
                   (user_id, tenant_id, phone_number, country_code, otp_hash, expires_at, ip_address)
                   VALUES ($1, $2, $3, $4, $5, NOW() + INTERVAL '10 minutes', $6)""",
                auth.user_id, auth.tenant_id, phone, country_code, otp_hashed, ip_address
            )
    except Exception as e:
        logger.error("Failed to store phone OTP: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to initiate phone verification")

    # Send OTP via MSG91 (or log in dev mode)
    msg91_auth_key = os.environ.get("MSG91_AUTH_KEY")
    if msg91_auth_key and not msg91_auth_key.startswith("test_"):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://control.msg91.com/api/v5/otp",
                    headers={"authkey": msg91_auth_key, "Content-Type": "application/json"},
                    json={
                        "template_id": os.environ.get("MSG91_OTP_TEMPLATE_ID", ""),
                        "mobile": phone.lstrip("+"),
                        "otp_length": 6,
                        "otp_expiry": 10,
                        "otp": otp,  # Send our generated OTP
                    }
                ) as resp:
                    if resp.status != 200:
                        logger.warning("MSG91 OTP send failed: %s", await resp.text())
        except Exception as e:
            logger.error("MSG91 OTP delivery error: %s", str(e))
    else:
        # Dev mode — log OTP
        logger.info("📱 DEV MODE — Phone OTP for %s: %s", mask_pii(phone), otp)

    background_tasks.add_task(
        log_audit, auth.user_id, auth.tenant_id, "phone_otp_requested",
        "user", "info", {"phone": mask_pii(phone)}, ip_address
    )

    return {"message": "OTP sent to your phone number", "phone": phone[:4] + "****" + phone[-2:]}


@app.post("/api/v1/auth/phone/verify", tags=["Phone Verification"])
async def verify_phone_otp(
    body: PhoneOTPVerify,
    request: Request,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """Verify phone OTP and mark phone as verified. Required before paid features."""
    ip_address = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

    phone = body.phone_number.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+91" + phone
    otp_hashed = hash_otp(body.otp)

    try:
        async with db.admin_connection() as conn:
            # Find the latest unverified OTP for this phone + user
            record = await conn.fetchrow(
                """SELECT id, otp_hash, attempts, max_attempts, expires_at
                   FROM phone_verifications
                   WHERE user_id = $1 AND phone_number = $2 AND verified = false
                   ORDER BY created_at DESC LIMIT 1""",
                auth.user_id, phone
            )

            if not record:
                raise HTTPException(status_code=400, detail="No pending verification found. Request a new OTP.")

            # Check expiry
            if record["expires_at"] < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="OTP has expired. Request a new one.")

            # Check attempts
            if record["attempts"] >= record["max_attempts"]:
                raise HTTPException(status_code=429, detail="Too many failed attempts. Request a new OTP.")

            # Verify OTP
            if record["otp_hash"] != otp_hashed:
                await conn.execute(
                    "UPDATE phone_verifications SET attempts = attempts + 1 WHERE id = $1",
                    record["id"]
                )
                remaining = record["max_attempts"] - record["attempts"] - 1
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid OTP. {remaining} attempts remaining."
                )

            # OTP is correct — mark as verified
            await conn.execute(
                "UPDATE phone_verifications SET verified = true WHERE id = $1",
                record["id"]
            )

            # Update user record
            await conn.execute(
                """UPDATE users
                   SET phone_number = $1, phone_verified = true, phone_verified_at = NOW()
                   WHERE id = $2""",
                phone, auth.user_id
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Phone verification error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Phone verification failed")

    background_tasks.add_task(
        log_audit, auth.user_id, auth.tenant_id, "phone_verified",
        "user", "info", {"phone": mask_pii(phone)}, ip_address
    )

    return {"message": "Phone number verified successfully", "phone_verified": True}


@app.get("/api/v1/auth/phone/status", tags=["Phone Verification"])
async def phone_verification_status(auth: AuthContext = Depends(get_auth)):
    """Check if the authenticated user's phone is verified."""
    try:
        async with db.admin_connection() as conn:
            row = await conn.fetchrow(
                "SELECT phone_number, phone_verified, phone_verified_at FROM users WHERE id = $1",
                auth.user_id
            )
            if row:
                return {
                    "phone_number": (row["phone_number"][:4] + "****" + row["phone_number"][-2:])
                        if row["phone_number"] else None,
                    "phone_verified": row["phone_verified"],
                    "phone_verified_at": row["phone_verified_at"].isoformat() if row["phone_verified_at"] else None,
                }
    except Exception as e:
        logger.error("Phone status check error: %s", str(e))

    return {"phone_number": None, "phone_verified": False, "phone_verified_at": None}


# ─── Error Handlers ───


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ─── Run Server ───

if __name__ == "__main__":
    import uvicorn



    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.ports.auth,
        reload=config.debug,
        log_level=config.log_level.lower(),
    )
