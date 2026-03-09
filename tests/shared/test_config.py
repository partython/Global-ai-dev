"""
Comprehensive tests for shared.core.config module.

Tests configuration loading from environment variables, default values,
database/Redis/JWT formatting, and all config sections.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from shared.core.config import (
    DatabaseConfig,
    RedisConfig,
    JWTConfig,
    AWSConfig,
    AIConfig,
    SecurityConfig,
    ServicePorts,
    PlatformConfig,
    config,
)


class TestDatabaseConfig:
    """Test PostgreSQL database configuration."""

    @pytest.mark.unit
    def test_database_config_default_values(self):
        """Database config loads correct defaults when env vars not set."""
        db = DatabaseConfig()
        assert db.host == "localhost"
        assert db.port == 5432
        assert db.name == "priya_global"
        assert db.user == "priya_admin"
        assert db.password == ""
        assert db.pool_min == 2
        assert db.pool_max == 20
        assert db.ssl_mode == "require"

    @pytest.mark.unit
    def test_database_config_from_environment(self):
        """Database config reads from environment variables."""
        with patch.dict(os.environ, {
            "PG_HOST": "db.example.com",
            "PG_PORT": "5433",
            "PG_DATABASE": "test_db",
            "PG_USER": "test_user",
            "PG_PASSWORD": "secret123",
            "PG_POOL_MIN": "5",
            "PG_POOL_MAX": "50",
            "PG_SSL_MODE": "prefer",
        }):
            db = DatabaseConfig()
            assert db.host == "db.example.com"
            assert db.port == 5433
            assert db.name == "test_db"
            assert db.user == "test_user"
            assert db.password == "secret123"
            assert db.pool_min == 5
            assert db.pool_max == 50
            assert db.ssl_mode == "prefer"

    @pytest.mark.unit
    def test_database_dsn_format(self):
        """Database DSN is formatted correctly for synchronous connections."""
        db = DatabaseConfig()
        dsn = db.dsn
        assert dsn.startswith("postgresql://")
        assert "priya_admin@localhost:5432/priya_global" in dsn
        assert "sslmode=require" in dsn

    @pytest.mark.unit
    def test_database_dsn_async_format(self):
        """Database async DSN uses asyncpg driver."""
        db = DatabaseConfig()
        dsn_async = db.dsn_async
        assert dsn_async.startswith("postgresql+asyncpg://")
        assert "priya_admin@localhost:5432/priya_global" in dsn_async
        assert "sslmode" not in dsn_async  # asyncpg handles SSL differently

    @pytest.mark.unit
    def test_database_dsn_with_custom_password(self):
        """DSN properly escapes and includes password."""
        with patch.dict(os.environ, {
            "PG_PASSWORD": "p@ss:word",
        }):
            db = DatabaseConfig()
            assert "p@ss:word@" in db.dsn

    @pytest.mark.unit
    def test_database_pool_config_limits(self):
        """Pool min/max are numeric and reasonable."""
        with patch.dict(os.environ, {
            "PG_POOL_MIN": "1",
            "PG_POOL_MAX": "100",
        }):
            db = DatabaseConfig()
            assert db.pool_min == 1
            assert db.pool_max == 100
            assert db.pool_min < db.pool_max


class TestRedisConfig:
    """Test Redis/ElastiCache configuration."""

    @pytest.mark.unit
    def test_redis_config_default_values(self):
        """Redis config loads correct defaults."""
        redis = RedisConfig()
        assert redis.host == "localhost"
        assert redis.port == 6379
        assert redis.password == ""
        assert redis.db == 0
        assert redis.ssl is False

    @pytest.mark.unit
    def test_redis_config_from_environment(self):
        """Redis config reads from environment variables."""
        with patch.dict(os.environ, {
            "REDIS_HOST": "redis.example.com",
            "REDIS_PORT": "6380",
            "REDIS_PASSWORD": "redis_pass",
            "REDIS_DB": "1",
            "REDIS_SSL": "true",
        }):
            redis = RedisConfig()
            assert redis.host == "redis.example.com"
            assert redis.port == 6380
            assert redis.password == "redis_pass"
            assert redis.db == 1
            assert redis.ssl is True

    @pytest.mark.unit
    def test_redis_url_without_ssl(self):
        """Redis URL uses redis:// scheme without SSL."""
        redis = RedisConfig()
        url = redis.url
        assert url.startswith("redis://")
        assert "localhost:6379/0" in url
        assert "rediss" not in url

    @pytest.mark.unit
    def test_redis_url_with_ssl(self):
        """Redis URL uses rediss:// scheme with SSL enabled."""
        with patch.dict(os.environ, {"REDIS_SSL": "true"}):
            redis = RedisConfig()
            url = redis.url
            assert url.startswith("rediss://")

    @pytest.mark.unit
    def test_redis_url_with_password(self):
        """Redis URL includes auth when password is set."""
        with patch.dict(os.environ, {
            "REDIS_PASSWORD": "secret123",
        }):
            redis = RedisConfig()
            url = redis.url
            assert ":secret123@" in url

    @pytest.mark.unit
    def test_redis_url_without_password(self):
        """Redis URL omits auth when password is empty."""
        redis = RedisConfig()
        url = redis.url
        assert "redis://localhost:6379/0" == url

    @pytest.mark.unit
    def test_redis_ssl_parsing_case_insensitive(self):
        """Redis SSL setting is case-insensitive."""
        for value in ["true", "True", "TRUE", "yes", "1"]:
            with patch.dict(os.environ, {"REDIS_SSL": value}):
                redis = RedisConfig()
                assert redis.ssl is True, f"Failed for value: {value}"

        for value in ["false", "False", "no", "0", ""]:
            with patch.dict(os.environ, {"REDIS_SSL": value}):
                redis = RedisConfig()
                assert redis.ssl is False, f"Failed for value: {value}"


class TestJWTConfig:
    """Test JWT authentication configuration."""

    @pytest.mark.unit
    def test_jwt_config_default_values(self):
        """JWT config has secure defaults."""
        jwt = JWTConfig()
        assert jwt.algorithm == "RS256"
        assert jwt.access_token_expiry == 900  # 15 min
        assert jwt.refresh_token_expiry == 604800  # 7 days
        assert jwt.issuer == "priya-global"

    @pytest.mark.unit
    def test_jwt_config_from_environment(self):
        """JWT config reads keys and timeouts from environment."""
        with patch.dict(os.environ, {
            "JWT_SECRET_KEY": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
            "JWT_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBg...",
            "JWT_ACCESS_EXPIRY": "1800",
            "JWT_REFRESH_EXPIRY": "2592000",
            "JWT_ISSUER": "custom-issuer",
        }):
            jwt = JWTConfig()
            assert jwt.secret_key == "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
            assert jwt.public_key == "-----BEGIN PUBLIC KEY-----\nMIIBIjANBg..."
            assert jwt.access_token_expiry == 1800
            assert jwt.refresh_token_expiry == 2592000
            assert jwt.issuer == "custom-issuer"

    @pytest.mark.unit
    def test_jwt_algorithm_always_rs256(self):
        """JWT algorithm is always RS256 (cannot be overridden)."""
        jwt = JWTConfig()
        assert jwt.algorithm == "RS256"

    @pytest.mark.unit
    def test_jwt_token_expiry_is_integer(self):
        """Token expiry values parse as integers."""
        with patch.dict(os.environ, {
            "JWT_ACCESS_EXPIRY": "3600",
            "JWT_REFRESH_EXPIRY": "1209600",
        }):
            jwt = JWTConfig()
            assert isinstance(jwt.access_token_expiry, int)
            assert isinstance(jwt.refresh_token_expiry, int)


class TestAWSConfig:
    """Test AWS service configuration."""

    @pytest.mark.unit
    def test_aws_config_default_values(self):
        """AWS config has sensible defaults."""
        aws = AWSConfig()
        assert aws.region == "ap-south-1"
        assert aws.s3_bucket == "priya-global-media"
        assert aws.s3_region == "ap-south-1"
        assert aws.ses_region == "ap-south-1"

    @pytest.mark.unit
    def test_aws_config_from_environment(self):
        """AWS config reads all services from environment."""
        with patch.dict(os.environ, {
            "AWS_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "S3_BUCKET": "custom-bucket",
            "S3_REGION": "eu-west-1",
            "SES_REGION": "eu-west-1",
            "COGNITO_POOL_ID": "ap-south-1_abc123",
            "COGNITO_CLIENT_ID": "client_123",
        }):
            aws = AWSConfig()
            assert aws.region == "us-east-1"
            assert aws.access_key == "AKIAIOSFODNN7EXAMPLE"
            assert aws.s3_bucket == "custom-bucket"
            assert aws.s3_region == "eu-west-1"
            assert aws.ses_region == "eu-west-1"
            assert aws.cognito_pool_id == "ap-south-1_abc123"


class TestAIConfig:
    """Test AI/LLM provider configuration."""

    @pytest.mark.unit
    def test_ai_config_default_models(self):
        """AI config has default models set."""
        ai = AIConfig()
        assert ai.primary_model == "claude-3-5-sonnet-20241022"
        assert ai.secondary_model == "gpt-4o"
        assert ai.tertiary_model == "gemini-1.5-pro"
        assert ai.cost_model == "gpt-4o-mini"

    @pytest.mark.unit
    def test_ai_config_from_environment(self):
        """AI config reads API keys and model selections."""
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-ant-123",
            "OPENAI_API_KEY": "sk-proj-456",
            "GOOGLE_AI_KEY": "AIzaSyD-789",
            "PRIMARY_LLM": "gpt-4-turbo",
            "SECONDARY_LLM": "claude-opus",
            "TERTIARY_LLM": "gemini-2-pro",
            "COST_LLM": "gpt-4-mini",
        }):
            ai = AIConfig()
            assert ai.anthropic_key == "sk-ant-123"
            assert ai.openai_key == "sk-proj-456"
            assert ai.google_ai_key == "AIzaSyD-789"
            assert ai.primary_model == "gpt-4-turbo"


class TestSecurityConfig:
    """Test security configuration."""

    @pytest.mark.unit
    def test_security_config_defaults(self):
        """Security config has strong defaults."""
        sec = SecurityConfig()
        assert sec.bcrypt_rounds == 12
        assert sec.max_login_attempts == 5
        assert sec.lockout_duration == 900  # 15 min
        assert sec.session_max_concurrent == 5
        assert sec.pii_masking_enabled is True
        assert "default-src 'self'" in sec.content_security_policy

    @pytest.mark.unit
    def test_security_cors_origins_parsing(self):
        """CORS origins are parsed from comma-separated env var."""
        with patch.dict(os.environ, {
            "CORS_ORIGINS": "https://example.com,https://app.example.com,http://localhost:3000",
        }):
            sec = SecurityConfig()
            assert len(sec.cors_origins) == 3
            assert "https://example.com" in sec.cors_origins
            assert "http://localhost:3000" in sec.cors_origins

    @pytest.mark.unit
    def test_security_rate_limits(self):
        """Rate limit tiers are configured correctly."""
        sec = SecurityConfig()
        assert sec.rate_limit_starter == 100  # Cheapest plan
        assert sec.rate_limit_growth == 500
        assert sec.rate_limit_enterprise == 2000  # Most expensive


class TestServicePorts:
    """Test service port assignments."""

    @pytest.mark.unit
    def test_service_ports_no_overlap(self):
        """All service ports are unique."""
        ports = ServicePorts()
        port_values = [
            ports.gateway, ports.auth, ports.tenant, ports.channel_router,
            ports.whatsapp, ports.email, ports.voice, ports.social,
            ports.webchat, ports.sms, ports.ai_engine, ports.sales_engine,
            ports.ecommerce, ports.analytics, ports.notification, ports.media,
            ports.marketplace, ports.billing,
        ]
        assert len(port_values) == len(set(port_values)), "Duplicate ports found!"

    @pytest.mark.unit
    def test_service_ports_in_range(self):
        """All service ports are in 9000-9027 range."""
        ports = ServicePorts()
        port_values = [
            ports.gateway, ports.auth, ports.tenant, ports.channel_router,
            ports.whatsapp, ports.email, ports.voice, ports.social,
            ports.webchat, ports.sms, ports.ai_engine, ports.sales_engine,
            ports.ecommerce, ports.analytics, ports.notification, ports.media,
            ports.marketplace, ports.billing,
        ]
        for port in port_values:
            assert 9000 <= port <= 9027, f"Port {port} out of range"

    @pytest.mark.unit
    def test_service_ports_no_psi_overlap(self):
        """Service ports don't overlap with PSI AI (5001-5009)."""
        ports = ServicePorts()
        port_values = [getattr(ports, attr) for attr in dir(ports) if not attr.startswith("_")]
        for port in port_values:
            assert not (5001 <= port <= 5009), f"Port {port} overlaps with PSI AI range"

    @pytest.mark.unit
    def test_gateway_port_is_9000(self):
        """Gateway always listens on 9000."""
        ports = ServicePorts()
        assert ports.gateway == 9000


class TestPlatformConfig:
    """Test master platform configuration."""

    @pytest.mark.unit
    def test_platform_config_aggregates_all_sections(self):
        """Platform config includes all sub-configs."""
        cfg = PlatformConfig()
        assert isinstance(cfg.db, DatabaseConfig)
        assert isinstance(cfg.redis, RedisConfig)
        assert isinstance(cfg.jwt, JWTConfig)
        assert isinstance(cfg.aws, AWSConfig)
        assert isinstance(cfg.ai, AIConfig)
        assert isinstance(cfg.security, SecurityConfig)
        assert isinstance(cfg.ports, ServicePorts)

    @pytest.mark.unit
    def test_platform_config_default_environment(self):
        """Platform defaults to development environment."""
        cfg = PlatformConfig()
        assert cfg.environment == "development"
        assert cfg.debug is False
        assert cfg.is_production is False

    @pytest.mark.unit
    def test_platform_config_production_detection(self):
        """Platform correctly detects production environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            cfg = PlatformConfig()
            assert cfg.is_production is True
            assert cfg.environment == "production"

    @pytest.mark.unit
    def test_platform_config_debug_mode(self):
        """Platform debug mode is configurable."""
        with patch.dict(os.environ, {"DEBUG": "true"}):
            cfg = PlatformConfig()
            assert cfg.debug is True

    @pytest.mark.unit
    def test_platform_config_log_level(self):
        """Platform log level is configurable."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            cfg = PlatformConfig()
            assert cfg.log_level == "DEBUG"

    @pytest.mark.unit
    def test_platform_config_is_singleton_like(self):
        """Global config instance is accessible."""
        assert config is not None
        assert isinstance(config, PlatformConfig)
        assert hasattr(config, "db")
        assert hasattr(config, "redis")

    @pytest.mark.unit
    def test_platform_name_customizable(self):
        """Platform name defaults to 'Priya AI' but is customizable."""
        cfg = PlatformConfig()
        assert cfg.platform_name == "Priya AI"

        with patch.dict(os.environ, {"PLATFORM_NAME": "Priya Healthcare"}):
            cfg2 = PlatformConfig()
            assert cfg2.platform_name == "Priya Healthcare"

    @pytest.mark.security
    def test_config_no_hardcoded_secrets(self):
        """Configuration doesn't contain hardcoded production secrets."""
        cfg = PlatformConfig()
        # Check that secrets default to empty strings
        assert cfg.jwt.secret_key == ""  # Must be set via env
        assert cfg.aws.access_key == ""
        assert cfg.redis.password == ""

    @pytest.mark.unit
    def test_config_with_multiple_environment_overrides(self):
        """Multiple environment variables work together correctly."""
        with patch.dict(os.environ, {
            "PG_HOST": "prod-db.example.com",
            "REDIS_HOST": "prod-cache.example.com",
            "ENVIRONMENT": "production",
            "DEBUG": "false",
            "LOG_LEVEL": "WARNING",
        }):
            cfg = PlatformConfig()
            assert cfg.db.host == "prod-db.example.com"
            assert cfg.redis.host == "prod-cache.example.com"
            assert cfg.is_production is True
            assert cfg.debug is False
            assert cfg.log_level == "WARNING"
