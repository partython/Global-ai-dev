"""
Authentication Middleware for FastAPI Services

Every service uses this middleware to:
1. Extract JWT from Authorization header
2. Validate token and extract tenant_id
3. Inject tenant context into request state
4. Enforce RBAC permissions

SECURITY: This is the gateway guard. Every request must pass through here.
No exceptions. No bypasses.
"""

import bcrypt
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.security import validate_access_token

logger = logging.getLogger("priya.auth")

# HTTP Bearer scheme for Swagger UI integration
bearer_scheme = HTTPBearer(auto_error=False)


class AuthContext:
    """
    Authenticated request context.
    Available in every authenticated endpoint via Depends(get_auth).
    """

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        role: str,
        plan: str,
        permissions: list[str],
        email: Optional[str] = None,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.plan = plan
        self.permissions = permissions
        self.email = email

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        if self.role == "owner":
            return True  # Owner has all permissions
        return permission in self.permissions

    def require_permission(self, permission: str):
        """Raise 403 if user doesn't have permission."""
        if not self.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required",
            )

    def require_role(self, *allowed_roles: str):
        """Raise 403 if user doesn't have one of the allowed roles."""
        if self.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {self.role} not authorized. Required: {', '.join(allowed_roles)}",
            )


async def get_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthContext:
    """
    Dependency that extracts and validates JWT token.

    Usage in endpoints:
        @router.get("/something")
        async def something(auth: AuthContext = Depends(get_auth)):
            # auth.tenant_id, auth.user_id, auth.role available
            pass
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    claims = validate_access_token(token)

    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Store auth context in request state for logging/tracing
    auth = AuthContext(
        user_id=claims["sub"],
        tenant_id=claims["tenant_id"],
        role=claims["role"],
        plan=claims["plan"],
        permissions=claims.get("permissions", []),
        email=claims.get("email"),
    )

    request.state.auth = auth
    request.state.tenant_id = claims["tenant_id"]

    return auth


# ─── Permission-Based Dependencies ───

def require_role(*roles: str):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.post("/admin-only", dependencies=[Depends(require_role("owner", "admin"))])
        async def admin_endpoint(): ...
    """
    async def _check(auth: AuthContext = Depends(get_auth)):
        auth.require_role(*roles)
        return auth
    return _check


def require_permission(permission: str):
    """
    Dependency factory for permission-based access control.

    Usage:
        @router.delete("/customers/:id", dependencies=[Depends(require_permission("customers.delete"))])
        async def delete_customer(): ...
    """
    async def _check(auth: AuthContext = Depends(get_auth)):
        auth.require_permission(permission)
        return auth
    return _check


# ─── Optional Auth (for public endpoints that behave differently when authenticated) ───

async def get_optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[AuthContext]:
    """Returns AuthContext if token present and valid, None otherwise."""
    if credentials is None:
        return None

    claims = validate_access_token(credentials.credentials)
    if claims is None:
        return None

    return AuthContext(
        user_id=claims["sub"],
        tenant_id=claims["tenant_id"],
        role=claims["role"],
        plan=claims["plan"],
        permissions=claims.get("permissions", []),
    )


# ─── API Key Auth (for developer/webhook endpoints) ───

from ..models.api_key import APIKeyContext, APIKeyScope
from ..core.database import db
import re
import hashlib


async def get_api_key_auth(
    request: Request,
    x_api_key: Optional[str] = None,
) -> APIKeyContext:
    """
    Authenticate via API key (X-API-Key header).
    Used for developer endpoints and webhook integrations.

    API Key Format: priya_{environment}_{tenant_id_prefix}_{random_32_chars}
    Example: priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

    Returns:
        APIKeyContext with tenant_id, scopes, rate limits, and permissions

    Raises:
        HTTPException 401: Missing or invalid API key
        HTTPException 403: Key expired, revoked, or insufficient scopes
        HTTPException 429: Rate limit exceeded
    """
    # Get API key from X-API-Key header only
    # SECURITY: API keys must not be passed in URL parameters (logged in URLs/referrer headers)
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required in X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Validate format (case-sensitive for security)
    api_key_pattern = r"^priya_[a-z]+_[a-z0-9]+_[a-z0-9]{32}$"
    if not re.match(api_key_pattern, api_key):
        logger.warning(f"Invalid API key format attempted")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
        )

    # Extract tenant_id prefix from key
    # Format: priya_{env}_{tenant_id_prefix}_{random}
    parts = api_key.split("_")
    if len(parts) < 4:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
        )

    tenant_id_prefix = parts[2]  # The tenant identifier

    # Look up API key by prefix, then verify with bcrypt (consistent with generation)
    # NOTE: We cannot use SHA256 for lookup because keys are stored as bcrypt hashes.
    # Instead, we look up by prefix and verify with bcrypt.checkpw()
    key_prefix = api_key[:12]  # pk_live_XXXX or pk_test_XXXX prefix for lookup

    try:
        # Look up API key candidates by prefix, then verify with bcrypt
        async with db.admin_connection() as conn:
            key_candidates = await conn.fetch(
                """
                SELECT
                    id as key_id,
                    tenant_id,
                    key_hash,
                    scopes,
                    rate_limit_rpm,
                    rate_limit_rph,
                    burst_size,
                    status,
                    expires_at,
                    last_used_at,
                    created_at
                FROM api_keys
                WHERE key_prefix = $1 AND status != 'revoked'
                """,
                key_prefix,
            )

        # Verify the full key against each candidate's bcrypt hash
        key_record = None
        for candidate in key_candidates:
            try:
                if bcrypt.checkpw(api_key.encode("utf-8"), candidate["key_hash"].encode("utf-8")):
                    key_record = candidate
                    break
            except (ValueError, TypeError):
                continue

        if not key_record:
            logger.warning(f"API key lookup failed (key not found)")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        # Check key status
        if key_record["status"] == "revoked":
            logger.warning(f"API key used but revoked: {key_record['key_id']}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has been revoked",
            )

        if key_record["status"] == "expired":
            logger.warning(f"API key used but expired: {key_record['key_id']}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has expired",
            )

        # Check expiration date
        if key_record["expires_at"] and key_record["expires_at"] < datetime.now(timezone.utc):
            logger.warning(f"API key expired: {key_record['key_id']}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has expired",
            )

        # Extract scopes
        scopes = [APIKeyScope(s) for s in (key_record["scopes"] or [])]
        if not scopes:
            logger.warning(f"API key has no scopes: {key_record['key_id']}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has no permissions configured",
            )

        # Build rate limit config
        from ..models.api_key import RateLimitConfig
        rate_limit = RateLimitConfig(
            requests_per_minute=key_record["rate_limit_rpm"] or 60,
            requests_per_hour=key_record["rate_limit_rph"] or 3600,
            burst_size=key_record["burst_size"] or 10,
        )

        # Check rate limit
        allowed, rate_headers = await check_api_key_rate_limit(
            key_id=key_record["key_id"],
            rate_limit=rate_limit,
        )

        if not allowed:
            logger.warning(f"API key rate limit exceeded: {key_record['key_id']}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers=rate_headers or {},
            )

        # Update last used timestamp (async, non-blocking)
        request.state.api_key_update = {
            "key_id": key_record["key_id"],
            "timestamp": datetime.now(timezone.utc),
        }

        # Log API key usage for audit
        await log_api_key_usage(
            key_id=key_record["key_id"],
            tenant_id=key_record["tenant_id"],
            request=request,
            rate_limit_remaining=rate_limit.requests_per_minute - 1,  # Approximate
        )

        # Return authenticated context
        return APIKeyContext(
            tenant_id=key_record["tenant_id"],
            key_id=key_record["key_id"],
            scopes=scopes,
            rate_limit=rate_limit,
            expires_at=key_record["expires_at"],
            can_read=APIKeyScope.READ in scopes or APIKeyScope.ADMIN in scopes,
            can_write=APIKeyScope.WRITE in scopes or APIKeyScope.ADMIN in scopes,
            is_admin=APIKeyScope.ADMIN in scopes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key authentication error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error",
        )


async def check_api_key_rate_limit(
    key_id: str,
    rate_limit: "RateLimitConfig",
) -> tuple[bool, Optional[Dict[str, str]]]:
    """
    Check if API key is within rate limits using Redis.

    Returns:
        (allowed: bool, headers: dict with rate limit info or None)
    """
    try:
        import redis.asyncio as redis
        from ..core.config import config

        redis_client = redis.from_url(config.redis.url, decode_responses=True)

        # Get current minute and hour windows
        now = int(time.time())
        minute_window = now // 60
        hour_window = now // 3600

        minute_key = f"rl:apikey:{key_id}:min:{minute_window}"
        hour_key = f"rl:apikey:{key_id}:hour:{hour_window}"

        # Check minute limit
        minute_count = await redis_client.incr(minute_key)
        if minute_count == 1:
            await redis_client.expire(minute_key, 60)

        if minute_count > rate_limit.requests_per_minute:
            return False, {
                "X-RateLimit-Limit": str(rate_limit.requests_per_minute),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(now + 60),
                "Retry-After": "60",
            }

        # Check hour limit
        hour_count = await redis_client.incr(hour_key)
        if hour_count == 1:
            await redis_client.expire(hour_key, 3600)

        if hour_count > rate_limit.requests_per_hour:
            return False, {
                "X-RateLimit-Limit": str(rate_limit.requests_per_hour),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(now + 3600),
                "Retry-After": "3600",
            }

        await redis_client.close()

        return True, {
            "X-RateLimit-Limit": str(rate_limit.requests_per_minute),
            "X-RateLimit-Remaining": str(
                max(0, rate_limit.requests_per_minute - minute_count)
            ),
            "X-RateLimit-Reset": str(now + 60),
        }

    except Exception as e:
        logger.error(f"Rate limit check error: {e}")
        # Fail CLOSED - reject requests if rate limit service is unavailable
        # This prevents request floods when Redis is down
        return False, {
            "X-RateLimit-Error": "Rate limit service unavailable",
            "Retry-After": "60",
        }


async def log_api_key_usage(
    key_id: str,
    tenant_id: str,
    request: Request,
    rate_limit_remaining: int,
):
    """Log API key usage for audit trail (non-blocking)"""
    try:
        from ..models.api_key import APIKeyAuditLog

        # Extract IP address, handling proxies
        client_ip = request.client.host if request.client else "unknown"
        if forwarded_for := request.headers.get("X-Forwarded-For"):
            client_ip = forwarded_for.split(",")[0].strip()

        # This would be inserted into audit_logs table
        # Implementation depends on database, done asynchronously
        # For now, just log it
        logger.info(
            f"API key usage: key_id={key_id} tenant={tenant_id} "
            f"method={request.method} path={request.url.path} "
            f"client={client_ip}"
        )

    except Exception as e:
        logger.error(f"Error logging API key usage: {e}")
        # Don't fail request on logging errors


from datetime import datetime
