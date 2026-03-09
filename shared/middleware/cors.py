"""
Centralized CORS (Cross-Origin Resource Sharing) Configuration
for Priya Global Multi-Tenant AI Sales Platform

This module provides a single source of truth for CORS policies across all services.
Environment-aware configuration:
- Production: Only specific whitelisted domains
- Staging: Staging domains + internal development
- Development: Localhost on all ports

SECURITY NOTES:
- Never use allow_methods=["*"] or allow_headers=["*"] in production
- Explicitly list all required HTTP methods
- Expose only necessary response headers
- Credentials are always required (cookies, auth headers)
"""

from typing import Dict, List


# Allowed HTTP methods for all services
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

# Standard headers required across the platform
ALLOWED_HEADERS = [
    "Content-Type",          # Request content type
    "Authorization",         # JWT tokens (Bearer)
    "X-API-Key",            # API key authentication
    "X-Tenant-ID",          # Tenant isolation
    "X-Request-ID",         # Request tracing
    "Accept",               # Content negotiation
    "Accept-Language",      # Language preference
    "Origin",               # CORS origin
    "User-Agent",           # Client identification (read-only)
]

# Response headers that clients are allowed to read
EXPOSED_HEADERS = [
    "X-Request-ID",         # Request tracing ID
    "X-RateLimit-Limit",    # Rate limit maximum
    "X-RateLimit-Remaining", # Rate limit remaining
    "X-RateLimit-Reset",    # Rate limit reset time (Unix timestamp)
    "Retry-After",          # When to retry (in seconds)
    "Content-Type",         # Response content type
    "Content-Length",       # Response size
]


def get_cors_config(environment: str = None) -> Dict:
    """
    Get CORS middleware configuration based on environment.

    Args:
        environment: One of "production", "staging", "development"
                    If None, reads from ENVIRONMENT env var (defaults to "development")

    Returns:
        Dictionary with CORSMiddleware parameters ready for FastAPI app.add_middleware()

    Examples:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from shared.middleware.cors import get_cors_config

        app = FastAPI()
        cors_config = get_cors_config(environment="production")
        app.add_middleware(CORSMiddleware, **cors_config)
    """
    import os

    if environment is None:
        environment = os.getenv("ENVIRONMENT", "development").lower()

    environment = environment.lower()

    # Production: Strict whitelist only
    if environment == "production":
        allowed_origins = [
            "https://api.priyaai.com",          # API domain
            "https://app.priyaai.com",          # Frontend domain
            "https://dashboard.priyaai.com",    # Admin dashboard
            "https://priyaai.com",              # Bare domain
            "https://www.priyaai.com",          # www subdomain
        ]

    # Staging: Staging domains + internal
    elif environment == "staging":
        allowed_origins = [
            "https://api-staging.priyaai.com",
            "https://app-staging.priyaai.com",
            "https://dashboard-staging.priyaai.com",
            "http://localhost:3000",            # Local dev against staging
            "http://localhost:3001",
            "http://localhost:8000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        ]

    # Development: All localhost variants (for flexible local development)
    else:  # development
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
            "http://localhost:8000",
            "http://localhost:8080",
            "http://localhost:5000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:8080",
            # For WebSocket development (same origins)
            "ws://localhost:3000",
            "ws://localhost:3001",
            "ws://127.0.0.1:3000",
            "ws://127.0.0.1:3001",
        ]

    return {
        "allow_origins": allowed_origins,
        "allow_credentials": True,              # Allow cookies, auth headers
        "allow_methods": ALLOWED_METHODS,       # Explicitly listed
        "allow_headers": ALLOWED_HEADERS,       # Explicitly listed
        "expose_headers": EXPOSED_HEADERS,      # Client-readable response headers
        "max_age": 3600,                       # Browser can cache preflight for 1 hour
    }


def get_allowed_origins(environment: str = None) -> List[str]:
    """Get just the list of allowed origins for the environment."""
    config = get_cors_config(environment)
    return config["allow_origins"]


def is_origin_allowed(origin: str, environment: str = None) -> bool:
    """Check if a given origin is allowed in the environment."""
    allowed = get_allowed_origins(environment)
    return origin in allowed
