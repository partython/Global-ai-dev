"""
Base Pydantic Models for Priya Global Platform

Shared data structures used across all microservices.
Defines core response formats, pagination, error handling, and common types.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Generic Type Variable ───
T = TypeVar("T")


# ─── Enums ───

class SortOrder(str, Enum):
    """Sort direction for paginated queries."""
    ASC = "asc"
    DESC = "desc"


# ─── Base Models ───

class TenantModel(BaseModel):
    """
    Base model for all tenant-scoped entities.

    SECURITY: Every model in the platform inherits this.
    tenant_id is mandatory for row-level security (RLS) enforcement.
    """
    tenant_id: UUID = Field(..., description="Tenant UUID - used for RLS")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        """Calculate database offset."""
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        """Database limit."""
        return self.per_page


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard paginated response wrapper.

    Used by ALL list endpoints to provide consistent pagination metadata.
    """
    items: List[T] = Field(default_factory=list)
    total: int = Field(description="Total items across all pages")
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")

    @staticmethod
    def create(items: List[T], total: int, page: int, per_page: int) -> "PaginatedResponse[T]":
        """Factory method to create paginated response with calculated total_pages."""
        total_pages = (total + per_page - 1) // per_page  # Ceiling division
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )

    class Config:
        arbitrary_types_allowed = True


class RequestMetadata(BaseModel):
    """Metadata about an incoming request (for audit/logging)."""
    request_id: str = Field(description="Unique request identifier (UUID or trace ID)")
    tenant_id: UUID = Field(description="Tenant UUID from JWT or header")
    user_id: Optional[UUID] = Field(None, description="User UUID from JWT token")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


# ─── Response Models ───

class ErrorResponse(BaseModel):
    """
    Standard error response.

    SECURITY: Never includes stack traces or internal details in production.
    error_code: machine-readable code for client handling
    message: user-facing error description
    details: optional additional context (request_id, validation errors, etc.)
    """
    error_code: str = Field(description="Machine-readable error code")
    message: str = Field(description="User-facing error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "error_code": "TENANT_ISOLATION_ERROR",
                "message": "Access denied to requested resource",
                "request_id": "req_abc123"
            }
        }


class SuccessResponse(BaseModel, Generic[T]):
    """
    Standard success response wrapper.

    Used by endpoints that return data to provide consistent response format.
    """
    success: bool = Field(default=True)
    data: Optional[T] = Field(None, description="Response payload")
    message: Optional[str] = Field(None, description="Optional message")

    @staticmethod
    def create(data: Optional[T] = None, message: Optional[str] = None) -> "SuccessResponse[T]":
        """Factory method to create success response."""
        return SuccessResponse(success=True, data=data, message=message)

    class Config:
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {},
                "message": "Operation completed successfully"
            }
        }


# ─── Request/Response DTOs ───

class BaseDTO(BaseModel):
    """Base DTO with common configuration."""
    class Config:
        from_attributes = True
        validate_assignment = True


class CreateDTO(BaseDTO):
    """Base DTO for create operations (no IDs or timestamps)."""
    pass


class UpdateDTO(BaseDTO):
    """Base DTO for update operations (all fields optional)."""
    def dict_of_changes(self) -> Dict[str, Any]:
        """Return only non-None fields as dict (for PATCH operations)."""
        return self.model_dump(exclude_none=True)


class ResponseDTO(BaseDTO):
    """Base DTO for API responses (includes IDs and timestamps)."""
    id: UUID = Field(description="Resource ID")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


# ─── Health Check Models ───

class HealthCheck(BaseModel):
    """Service health check response."""
    status: str = Field(default="healthy", description="Service status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: Optional[str] = Field(None, description="Service version")
    dependencies: Optional[Dict[str, str]] = Field(None, description="Dependency health states")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2026-03-06T10:30:00Z",
                "version": "1.0.0",
                "dependencies": {
                    "database": "healthy",
                    "redis": "healthy"
                }
            }
        }
