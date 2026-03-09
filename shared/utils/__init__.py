"""
Priya Global Platform - Shared Utilities Package

Provides common functionality used across all microservices:
- Error handling and custom exceptions
- Input validation and sanitization
- Pagination helpers and utilities
- Response formatting

USAGE:
    from shared.utils import (
        # Errors
        NotFoundError,
        ValidationError,
        TenantIsolationError,
        global_exception_handler,
        # Validators
        validate_email,
        validate_phone,
        sanitize_input,
        # Pagination
        paginate,
        apply_sorting,
        PaginationHelper,
    )
"""

# ─── Errors ───
from .errors import (
    ConflictError,
    DatabaseError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    PriyaBaseError,
    RateLimitError,
    ServiceUnavailableError,
    TenantIsolationError,
    UnauthorizedError,
    ValidationError,
    global_exception_handler,
)

# ─── Pagination ───
from .pagination import (
    PaginationHelper,
    apply_sorting,
    calculate_offset,
    calculate_total_pages,
    paginate,
)

# ─── Validators ───
from .validators import (
    sanitize_input,
    validate_country_code,
    validate_email,
    validate_language_code,
    validate_phone,
    validate_tenant_id,
    validate_url,
    validate_username,
    validate_uuid,
)

__all__ = [
    # Error classes
    "PriyaBaseError",
    "NotFoundError",
    "UnauthorizedError",
    "ForbiddenError",
    "ValidationError",
    "ConflictError",
    "RateLimitError",
    "ServiceUnavailableError",
    "DatabaseError",
    "ExternalServiceError",
    "TenantIsolationError",
    "global_exception_handler",
    # Pagination
    "paginate",
    "apply_sorting",
    "PaginationHelper",
    "calculate_offset",
    "calculate_total_pages",
    # Validators
    "validate_email",
    "validate_phone",
    "validate_tenant_id",
    "validate_url",
    "sanitize_input",
    "validate_username",
    "validate_country_code",
    "validate_language_code",
    "validate_uuid",
]
