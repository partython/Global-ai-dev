"""
Global Platform Configuration
Reads from environment variables with sensible defaults.
Every service imports this for consistent configuration.

CRITICAL: PSI AI runs on ports 5001-5009.
Global platform uses ports 9000-9027. ZERO overlap.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DatabaseConfig:
    """PostgreSQL connection config with multi-tenant support."""
    host: str = os.getenv("PG_HOST", "localhost")
    port: int = int(os.getenv("PG_PORT", "5432"))
    name: str = os.getenv("PG_DATABASE", "priya_global")
    user: str = os.getenv("PG_USER", "priya_admin")
    password: str = os.getenv("PG_PASSWORD", "")
    pool_min: int = int(os.getenv("PG_POOL_MIN", "2"))
    pool_max: int = int(os.getenv("PG_POOL_MAX", "20"))
    ssl_mode: str = os.getenv("PG_SSL_MODE", "require")

    @property
    def dsn(self) -> str:
        # NOTE: Password comes from PG_PASSWORD environment variable (never hardcoded)
        # This DSN string is only used internally; never logged or exposed in URLs
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}?sslmode={self.ssl_mode}"

    @property
    def dsn_async(self) -> str:
        # NOTE: Password comes from PG_PASSWORD environment variable (never hardcoded)
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class RedisConfig:
    """Redis/ElastiCache config."""
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: str = os.getenv("REDIS_PASSWORD", "")
    db: int = int(os.getenv("REDIS_DB", "0"))
    ssl: bool = os.getenv("REDIS_SSL", "false").lower() == "true"

    @property
    def url(self) -> str:
        proto = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{proto}://{auth}{self.host}:{self.port}/{self.db}"


def _load_key(env_var: str, file_env_var: str) -> str:
    """Load a key from env var directly or from a file path."""
    # First try direct value
    val = os.getenv(env_var, "")
    if val:
        return val
    # Then try file path
    file_path = os.getenv(file_env_var, "")
    if file_path and os.path.isfile(file_path):
        with open(file_path, "r") as f:
            return f.read().strip()
    return ""


@dataclass
class JWTConfig:
    """JWT authentication config."""
    secret_key: str = _load_key("JWT_SECRET_KEY", "JWT_SECRET_KEY_FILE")  # RS256 private key
    public_key: str = _load_key("JWT_PUBLIC_KEY", "JWT_PUBLIC_KEY_FILE")  # RS256 public key

    def __post_init__(self):
        """Validate JWT keys are set in production."""
        env = os.getenv("ENVIRONMENT", "development")
        if env in ("production", "staging"):
            if not self.secret_key or not self.public_key:
                raise RuntimeError(
                    "CRITICAL: JWT_SECRET_KEY and JWT_PUBLIC_KEY must be set "
                    "in production/staging. Cannot start with empty JWT keys."
                )
    algorithm: str = "RS256"
    access_token_expiry: int = int(os.getenv("JWT_ACCESS_EXPIRY", "900"))  # 15 min
    refresh_token_expiry: int = int(os.getenv("JWT_REFRESH_EXPIRY", "604800"))  # 7 days
    issuer: str = os.getenv("JWT_ISSUER", "priya-global")


@dataclass
class AWSConfig:
    """AWS service configuration."""
    region: str = os.getenv("AWS_REGION", "ap-south-1")
    access_key: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    secret_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    s3_bucket: str = os.getenv("S3_BUCKET", "priya-global-media")
    s3_region: str = os.getenv("S3_REGION", "ap-south-1")
    ses_region: str = os.getenv("SES_REGION", "ap-south-1")
    cognito_pool_id: str = os.getenv("COGNITO_POOL_ID", "")
    cognito_client_id: str = os.getenv("COGNITO_CLIENT_ID", "")


@dataclass
class AIConfig:
    """AI/LLM provider configuration."""
    anthropic_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_key: str = os.getenv("OPENAI_API_KEY", "")
    google_ai_key: str = os.getenv("GOOGLE_AI_KEY", "")
    primary_model: str = os.getenv("PRIMARY_LLM", "claude-3-5-sonnet-20241022")
    secondary_model: str = os.getenv("SECONDARY_LLM", "gpt-4o")
    tertiary_model: str = os.getenv("TERTIARY_LLM", "gemini-1.5-pro")
    cost_model: str = os.getenv("COST_LLM", "gpt-4o-mini")


@dataclass
class SecurityConfig:
    """Security settings - NEVER compromise these."""
    cors_origins: list = field(default_factory=lambda: os.getenv(
        "CORS_ORIGINS", "https://app.priyaai.com,http://localhost:3000"
    ).split(","))
    rate_limit_starter: int = 100   # req/min
    rate_limit_growth: int = 500
    rate_limit_enterprise: int = 2000
    bcrypt_rounds: int = 12
    max_login_attempts: int = 5
    lockout_duration: int = 900  # 15 min
    session_max_concurrent: int = 5
    pii_masking_enabled: bool = True
    content_security_policy: str = "default-src 'self'; script-src 'self'"


@dataclass
class ServicePorts:
    """
    Port assignments for ALL services.
    Source of truth: docker-compose.yml
    CRITICAL: PSI AI uses 5001-5009. We use 9000-9050.
    """
    gateway: int = 9000
    auth: int = 9001
    tenant: int = 9002
    channel_router: int = 9003
    ai_engine: int = 9004
    whatsapp: int = 9010
    email: int = 9011
    voice: int = 9012
    social: int = 9013
    webchat: int = 9014
    sms: int = 9015
    telegram: int = 9016
    billing: int = 9020
    analytics: int = 9021
    marketing: int = 9022
    ecommerce: int = 9023
    notification: int = 9024
    plugins: int = 9025
    handoff: int = 9026
    leads: int = 9027
    conversation_intel: int = 9028
    appointments: int = 9029
    knowledge: int = 9030
    voice_ai: int = 9031
    video: int = 9032
    rcs: int = 9033
    memory: int = 9034
    rest_connector: int = 9035
    developer_portal: int = 9036
    marketplace: int = 9037
    compliance: int = 9038
    health_monitor: int = 9039
    cdn_manager: int = 9040
    deployment: int = 9041
    tenant_config: int = 9042
    worker: int = 9043
    translation: int = 9044
    workflow: int = 9045
    advanced_analytics: int = 9046
    ai_training: int = 9047
    wallet: int = 9050


@dataclass
class PlatformConfig:
    """Master configuration aggregating all sub-configs."""
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    jwt: JWTConfig = field(default_factory=JWTConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ports: ServicePorts = field(default_factory=ServicePorts)

    # Platform metadata
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    platform_name: str = os.getenv("PLATFORM_NAME", "Priya AI")  # placeholder, rename later

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


# Singleton config instance
config = PlatformConfig()
