"""
Service Registry and Discovery for Priya Global Platform

Production-grade service discovery with support for multiple deployment environments:
- LOCAL: Development (http://localhost:port)
- DOCKER: Container networking (http://service-name:port)
- KUBERNETES: Service DNS (http://service-name.namespace.svc.cluster.local:port)

Includes health check integration, service grouping, and environment-aware URL resolution.

ARCHITECTURE:
- 36 microservices across 5 namespaces (core, channels, business, advanced, ops)
- Automatic URL resolution based on ENVIRONMENT variable
- Health check caching (10s TTL) to avoid thundering herd
- Service metadata: name, ports, namespaces, descriptions
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("priya.service_registry")


class DeploymentEnvironment(Enum):
    """Deployment environment variants."""
    LOCAL = "local"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"


@dataclass
class ServiceInfo:
    """Service metadata and configuration."""
    name: str
    port: int
    namespace: str  # core, channels, business, advanced, ops
    description: str = ""
    health_check_path: str = "/health"

    def get_url(self, environment: DeploymentEnvironment) -> str:
        """Resolve service URL based on deployment environment."""
        if environment == DeploymentEnvironment.LOCAL:
            return f"http://localhost:{self.port}"

        elif environment == DeploymentEnvironment.DOCKER:
            # Docker DNS: service name maps to container hostname
            service_host = self.name.replace("_", "-")
            return f"http://{service_host}:{self.port}"

        elif environment == DeploymentEnvironment.KUBERNETES:
            # Kubernetes DNS: service.namespace.svc.cluster.local
            service_host = self.name.replace("_", "-")
            return f"http://{service_host}.{self.namespace}.svc.cluster.local:{self.port}"

        else:
            raise ValueError(f"Unknown environment: {environment}")


class ServiceRegistry:
    """
    Central service registry managing all 36 microservices.

    Handles:
    - Service discovery and URL resolution
    - Environment-aware configuration
    - Health check caching
    - Service grouping by namespace
    - Dependency tracking
    """

    def __init__(self, environment: str = "local"):
        """
        Initialize registry.

        Args:
            environment: 'local', 'docker', 'kubernetes', or 'development' (maps to docker)
        """
        # Map environment names to deployment environments
        env_map = {"development": "docker", "staging": "kubernetes", "production": "kubernetes"}
        resolved = env_map.get(environment.lower(), environment.lower())
        self.environment = DeploymentEnvironment(resolved)
        self._services: Dict[str, ServiceInfo] = {}
        self._health_cache: Dict[str, Tuple[bool, float]] = {}
        self._health_cache_ttl = 10  # seconds
        self._lock = asyncio.Lock()

        self._register_all_services()

    def _register_all_services(self):
        """Register all 36 services across 5 namespaces."""

        # ─── CORE NAMESPACE (9 services) ───
        # Platform foundation: auth, routing, configuration
        self._register(ServiceInfo(
            name="gateway",
            port=9000,
            namespace="core",
            description="API Gateway - central entry point for external traffic"
        ))
        self._register(ServiceInfo(
            name="auth",
            port=9001,
            namespace="core",
            description="Authentication & Authorization - JWT validation, tenant auth"
        ))
        self._register(ServiceInfo(
            name="tenant",
            port=9002,
            namespace="core",
            description="Tenant Management - multi-tenancy, account configuration"
        ))
        self._register(ServiceInfo(
            name="channel_router",
            port=9003,
            namespace="core",
            description="Channel Router - message routing across communication channels"
        ))
        self._register(ServiceInfo(
            name="ai_engine",
            port=9004,
            namespace="core",
            description="AI Engine - LLM integration, prompt management"
        ))
        self._register(ServiceInfo(
            name="memory",
            port=9034,
            namespace="core",
            description="Memory Service - conversation memory, customer knowledge, semantic recall"
        ))
        self._register(ServiceInfo(
            name="conversation",
            port=9028,
            namespace="core",
            description="Conversation Manager - chat history, context, threading"
        ))
        self._register(ServiceInfo(
            name="knowledge_base",
            port=9030,
            namespace="core",
            description="Knowledge Base - RAG, document indexing, search"
        ))
        self._register(ServiceInfo(
            name="contact_manager",
            port=9027,
            namespace="core",
            description="Contact Manager - customer data, segmentation"
        ))
        self._register(ServiceInfo(
            name="tenant_config",
            port=9042,
            namespace="core",
            description="Tenant Configuration - settings, customization, branding"
        ))

        # ─── CHANNELS NAMESPACE (10 services) ───
        # Communication channel integrations
        self._register(ServiceInfo(
            name="whatsapp",
            port=9010,
            namespace="channels",
            description="WhatsApp integration - messaging via WhatsApp Business API"
        ))
        self._register(ServiceInfo(
            name="email",
            port=9011,
            namespace="channels",
            description="Email Service - SMTP, SES integration, templates"
        ))
        self._register(ServiceInfo(
            name="sms",
            port=9015,
            namespace="channels",
            description="SMS Service - Exotel, Bandwidth, Vonage multi-carrier"
        ))
        self._register(ServiceInfo(
            name="voice",
            port=9012,
            namespace="channels",
            description="Voice Service - calling, IVR, voice AI"
        ))
        self._register(ServiceInfo(
            name="webchat",
            port=9014,
            namespace="channels",
            description="Web Chat - web widget, live chat integration"
        ))
        self._register(ServiceInfo(
            name="instagram",
            port=9013,
            namespace="channels",
            description="Instagram Integration - DM handling, story responses (via social service)"
        ))
        self._register(ServiceInfo(
            name="facebook",
            port=9013,
            namespace="channels",
            description="Facebook Integration - Messenger, page management (via social service)"
        ))
        self._register(ServiceInfo(
            name="telegram",
            port=9016,
            namespace="channels",
            description="Telegram Integration - Bot API, channels"
        ))
        self._register(ServiceInfo(
            name="line_service",
            port=9018,
            namespace="channels",
            description="LINE Integration - messaging, LIFF apps"
        ))
        self._register(ServiceInfo(
            name="twitter",
            port=9019,
            namespace="channels",
            description="Twitter Integration - DM handling, mentions"
        ))

        # ─── BUSINESS NAMESPACE (8 services) ───
        # Business operations and monetization
        self._register(ServiceInfo(
            name="billing",
            port=9020,
            namespace="business",
            description="Billing & Payments - Stripe, invoicing, subscriptions"
        ))
        self._register(ServiceInfo(
            name="analytics",
            port=9021,
            namespace="business",
            description="Analytics - metrics, dashboards, reporting"
        ))
        self._register(ServiceInfo(
            name="leads",
            port=9027,
            namespace="business",
            description="Leads Management - lead scoring, pipeline tracking"
        ))
        self._register(ServiceInfo(
            name="notification",
            port=9024,
            namespace="business",
            description="Notification Service - email, push, SMS alerts"
        ))
        self._register(ServiceInfo(
            name="appointment",
            port=9029,
            namespace="business",
            description="Appointment Scheduling - calendars, booking, reminders"
        ))
        self._register(ServiceInfo(
            name="ecommerce",
            port=9023,
            namespace="business",
            description="E-commerce - product catalog, orders, inventory"
        ))
        self._register(ServiceInfo(
            name="campaign",
            port=9022,
            namespace="business",
            description="Campaign Management - marketing automation, sequences"
        ))
        self._register(ServiceInfo(
            name="feedback",
            port=9025,
            namespace="business",
            description="Feedback & Surveys - NPS, customer satisfaction"
        ))
        self._register(ServiceInfo(
            name="wallet",
            port=9050,
            namespace="business",
            description="Wallet & Credits - prepaid wallet, Razorpay topups"
        ))

        # ─── ADVANCED NAMESPACE (6 services) ───
        # Advanced AI and analytics capabilities
        self._register(ServiceInfo(
            name="translation",
            port=9044,
            namespace="advanced",
            description="Translation Service - multilingual support, i18n"
        ))
        self._register(ServiceInfo(
            name="sentiment",
            port=9046,
            namespace="advanced",
            description="Sentiment Analysis - emotion detection, tone analysis"
        ))
        self._register(ServiceInfo(
            name="conversation_intel",
            port=9028,
            namespace="advanced",
            description="Conversation Intelligence - NLU, intent detection, entities"
        ))
        self._register(ServiceInfo(
            name="product_recommendation",
            port=9037,
            namespace="advanced",
            description="Product Recommendation - ML-based suggestions, personalization"
        ))
        self._register(ServiceInfo(
            name="voice_ai",
            port=9031,
            namespace="advanced",
            description="Voice AI - speech-to-text, text-to-speech, voice synthesis"
        ))
        self._register(ServiceInfo(
            name="ab_testing",
            port=9046,
            namespace="advanced",
            description="A/B Testing - experiment management, statistical analysis"
        ))
        self._register(ServiceInfo(
            name="rest_connector",
            port=9035,
            namespace="advanced",
            description="Universal REST API Connector - generic REST/webhook integration for any platform"
        ))
        self._register(ServiceInfo(
            name="developer_portal",
            port=9036,
            namespace="advanced",
            description="Developer Portal - API docs, developer accounts, plugin submissions, sandbox"
        ))

        # ─── OPS NAMESPACE (3 services) ───
        # Operations and infrastructure
        self._register(ServiceInfo(
            name="health_monitor",
            port=9039,
            namespace="ops",
            description="Health Monitor - service health, uptime tracking, alerting"
        ))
        self._register(ServiceInfo(
            name="cdn_manager",
            port=9040,
            namespace="ops",
            description="CDN Manager - content delivery, caching, DDoS protection"
        ))
        self._register(ServiceInfo(
            name="deployment",
            port=9041,
            namespace="ops",
            description="Deployment Service - CI/CD, blue-green deployments"
        ))

    def _register(self, service: ServiceInfo):
        """Register a service in the registry."""
        self._services[service.name] = service
        logger.debug(f"Registered service: {service.name} (port {service.port})")

    def get_service_url(self, service_name: str) -> str:
        """
        Get the resolved URL for a service.

        Args:
            service_name: Name of the service (e.g., 'auth', 'whatsapp')

        Returns:
            Full URL (http://...:port)

        Raises:
            ValueError: If service not found
        """
        if service_name not in self._services:
            raise ValueError(f"Unknown service: {service_name}")

        service = self._services[service_name]
        return service.get_url(self.environment)

    def get_service_info(self, service_name: str) -> ServiceInfo:
        """
        Get full metadata for a service.

        Args:
            service_name: Name of the service

        Returns:
            ServiceInfo object

        Raises:
            ValueError: If service not found
        """
        if service_name not in self._services:
            raise ValueError(f"Unknown service: {service_name}")

        return self._services[service_name]

    def get_services_by_namespace(self, namespace: str) -> Dict[str, ServiceInfo]:
        """
        Get all services in a namespace.

        Args:
            namespace: 'core', 'channels', 'business', 'advanced', or 'ops'

        Returns:
            Dict mapping service names to ServiceInfo objects
        """
        return {
            name: svc for name, svc in self._services.items()
            if svc.namespace == namespace
        }

    def get_all_services(self) -> Dict[str, ServiceInfo]:
        """Get all registered services."""
        return self._services.copy()

    def list_services_by_namespace(self) -> Dict[str, List[str]]:
        """
        List service names grouped by namespace.

        Returns:
            Dict mapping namespace -> list of service names
        """
        result = {}
        for namespace in ["core", "channels", "business", "advanced", "ops"]:
            services = self.get_services_by_namespace(namespace)
            result[namespace] = sorted(services.keys())

        return result

    async def is_service_healthy(
        self,
        service_name: str,
        http_client = None,
        use_cache: bool = True
    ) -> bool:
        """
        Check if a service is healthy by calling its /health endpoint.

        Args:
            service_name: Name of the service
            http_client: httpx.AsyncClient instance (required)
            use_cache: Whether to use cached health status

        Returns:
            True if service is healthy, False otherwise

        Raises:
            ValueError: If service not found or http_client not provided
        """
        if not http_client:
            raise ValueError("http_client is required")

        if service_name not in self._services:
            raise ValueError(f"Unknown service: {service_name}")

        # Check cache
        if use_cache and service_name in self._health_cache:
            is_healthy, timestamp = self._health_cache[service_name]
            if time.time() - timestamp < self._health_cache_ttl:
                return is_healthy

        # Perform health check
        service = self._services[service_name]
        url = service.get_url(self.environment)
        health_url = f"{url}{service.health_check_path}"

        try:
            response = await http_client.get(health_url, timeout=5.0)
            is_healthy = response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for {service_name}: {e}")
            is_healthy = False

        # Cache result
        async with self._lock:
            self._health_cache[service_name] = (is_healthy, time.time())

        return is_healthy

    async def check_all_health(
        self,
        http_client = None,
        timeout: int = 5
    ) -> Dict[str, bool]:
        """
        Check health of all services concurrently.

        Args:
            http_client: httpx.AsyncClient instance
            timeout: Individual request timeout in seconds

        Returns:
            Dict mapping service name -> health status
        """
        if not http_client:
            raise ValueError("http_client is required")

        tasks = []
        for service_name in self._services.keys():
            tasks.append(self.is_service_healthy(service_name, http_client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_status = {}
        for service_name, result in zip(self._services.keys(), results):
            if isinstance(result, bool):
                health_status[service_name] = result
            else:
                health_status[service_name] = False

        return health_status

    def clear_health_cache(self, service_name: Optional[str] = None):
        """
        Clear health check cache.

        Args:
            service_name: Clear specific service cache, or None to clear all
        """
        if service_name:
            self._health_cache.pop(service_name, None)
        else:
            self._health_cache.clear()

    def get_environment(self) -> str:
        """Get current deployment environment."""
        return self.environment.value

    def set_environment(self, environment: str):
        """Change deployment environment at runtime."""
        self.environment = DeploymentEnvironment(environment.lower())
        logger.info(f"Registry environment changed to: {environment}")

    def validate_service(self, service_name: str) -> bool:
        """Check if a service is registered."""
        return service_name in self._services

    def get_service_dependencies(self, service_name: str) -> Set[str]:
        """
        Get logical dependencies for a service.

        Returns services that a given service typically depends on.
        This is informational - actual dependencies are determined by
        inter-service calls.
        """
        dependencies = {
            # Core services - most depend on auth and tenant
            "auth": {"gateway"},
            "tenant": {"gateway"},
            "channel_router": {"gateway", "auth", "tenant"},
            "ai_engine": {"gateway", "auth", "knowledge_base", "memory"},
            "memory": {"gateway", "auth"},
            "conversation": {"gateway", "auth", "tenant"},
            "knowledge_base": {"gateway", "auth"},
            "contact_manager": {"gateway", "auth", "tenant"},
            "tenant_config": {"gateway", "auth"},

            # Channels - all depend on channel router
            "whatsapp": {"gateway", "auth", "channel_router"},
            "email": {"gateway", "auth", "channel_router"},
            "sms": {"gateway", "auth", "channel_router"},
            "voice": {"gateway", "auth", "channel_router"},
            "webchat": {"gateway", "auth", "channel_router"},
            "instagram": {"gateway", "auth", "channel_router"},
            "facebook": {"gateway", "auth", "channel_router"},
            "telegram": {"gateway", "auth", "channel_router"},
            "line_service": {"gateway", "auth", "channel_router"},
            "twitter": {"gateway", "auth", "channel_router"},

            # Business services
            "billing": {"gateway", "auth", "tenant"},
            "analytics": {"gateway", "auth", "tenant"},
            "leads": {"gateway", "auth", "contact_manager"},
            "notification": {"gateway", "auth"},
            "appointment": {"gateway", "auth", "tenant"},
            "ecommerce": {"gateway", "auth", "contact_manager"},
            "campaign": {"gateway", "auth", "tenant"},
            "feedback": {"gateway", "auth", "tenant"},

            # Advanced services
            "translation": {"gateway", "auth"},
            "sentiment": {"gateway", "auth"},
            "conversation_intel": {"gateway", "auth", "conversation"},
            "product_recommendation": {"gateway", "auth"},
            "voice_ai": {"gateway", "auth"},
            "ab_testing": {"gateway", "auth", "analytics"},

            # Ops services
            "health_monitor": set(),
            "cdn_manager": set(),
            "deployment": set(),
        }

        return dependencies.get(service_name, set())


# Global singleton instance
_registry: Optional[ServiceRegistry] = None


def get_registry(environment: Optional[str] = None) -> ServiceRegistry:
    """
    Get the global service registry instance.

    Args:
        environment: Deployment environment (only used on first call).
                    Defaults to ENVIRONMENT env var or 'local'.

    Returns:
        ServiceRegistry singleton
    """
    global _registry

    if _registry is None:
        import os
        env = environment or os.getenv("ENVIRONMENT", "local")
        _registry = ServiceRegistry(env)

    return _registry
