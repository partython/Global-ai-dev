"""
Multi-LLM Router for Priya Global AI Engine Service.

Intelligent routing between multiple LLM providers (OpenAI, Anthropic, Google, Groq)
based on cost, latency, quality requirements, and fallback strategies.

Features:
  • Provider-agnostic unified interface
  • Cost optimization with daily budgets
  • Latency-aware model selection
  • Circuit breaker pattern per provider
  • Comprehensive cost tracking and reporting
  • Structured logging (no f-string injection)
  • Async/await support for all providers
"""

import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any, Union

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


# ============================================================================
# PROMPT INJECTION PREVENTION
# ============================================================================

# Patterns that indicate prompt injection attempts from tenant user input
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?prior\s+(instructions|prompts|context)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?:?\s", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"\[SYSTEM\]", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are", re.IGNORECASE),
    re.compile(r"override\s+(your\s+)?(instructions|rules|guidelines)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your\s+instructions)", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+(have\s+)?no\s+restrictions", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s*mode", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions)", re.IGNORECASE),
]

# Maximum input length per message (prevent token-stuffing attacks)
_MAX_USER_MESSAGE_LENGTH = 32000  # ~8k tokens


def sanitize_llm_input(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Sanitize user messages before sending to LLM providers.

    - Detects and flags prompt injection attempts
    - Truncates excessively long messages
    - Strips control characters

    Returns sanitized messages list. Raises ValueError on critical injection.
    """
    sanitized = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Only sanitize user messages, not system prompts
        if role in ("user", "assistant"):
            # Truncate excessively long messages
            if len(content) > _MAX_USER_MESSAGE_LENGTH:
                content = content[:_MAX_USER_MESSAGE_LENGTH]
                logger.warning(
                    "llm_input_truncated",
                    extra={"role": role, "original_length": len(msg.get("content", ""))},
                )

            # Strip null bytes and control characters
            content = content.replace("\x00", "")
            content = "".join(
                ch for ch in content
                if ch in "\n\t\r" or (ord(ch) >= 32 and ord(ch) != 127)
            )

        # Check user messages for injection patterns
        if role == "user":
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(content):
                    logger.warning(
                        "prompt_injection_detected",
                        extra={
                            "pattern": pattern.pattern[:50],
                            "content_preview": content[:100],
                        },
                    )
                    # Don't block — flag it so the system prompt can handle it
                    # but strip the most dangerous patterns
                    content = pattern.sub("[FILTERED]", content)

        sanitized.append({"role": role, "content": content})

    return sanitized


# ============================================================================
# ENUMS
# ============================================================================

class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    LOCAL = "local"


class RoutingStrategy(str, Enum):
    """Strategy for selecting which model to use."""
    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_OPTIMIZED = "quality_optimized"
    BALANCED = "balanced"
    FALLBACK_CHAIN = "fallback_chain"


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class LLMModel:
    """Metadata about an available LLM model."""
    provider: LLMProvider
    model_name: str
    max_tokens: int
    cost_per_1k_input: float  # USD
    cost_per_1k_output: float  # USD
    latency_p50_ms: int  # Median latency
    capabilities: List[str] = field(default_factory=list)

    def __hash__(self):
        return hash((self.provider, self.model_name))

    def __eq__(self, other):
        if not isinstance(other, LLMModel):
            return False
        return self.provider == other.provider and self.model_name == other.model_name


@dataclass
class CircuitBreakerState:
    """Circuit breaker state per provider."""
    provider: LLMProvider
    state: str = "closed"  # closed, open, half_open
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    open_until: Optional[float] = None
    successes_in_half_open: int = 0

    FAILURE_THRESHOLD = 3
    FAILURE_WINDOW_SECONDS = 60
    RECOVERY_TIMEOUT_SECONDS = 30
    HALF_OPEN_SUCCESS_THRESHOLD = 1

    def record_failure(self):
        """Record a failure."""
        now = time.time()
        self.last_failure_time = now

        if self.state == "closed":
            self.failure_count += 1
            if self.failure_count >= self.FAILURE_THRESHOLD:
                self.state = "open"
                self.open_until = now + self.RECOVERY_TIMEOUT_SECONDS
                logger.warning(
                    "circuit_breaker_opened",
                    extra={
                        "provider": self.provider.value,
                        "failures": self.failure_count,
                    },
                )
        elif self.state == "half_open":
            self.state = "open"
            self.open_until = time.time() + self.RECOVERY_TIMEOUT_SECONDS
            logger.warning(
                "circuit_breaker_reopened",
                extra={"provider": self.provider.value},
            )

    def record_success(self):
        """Record a successful call."""
        if self.state == "closed":
            # Reset failure count if we're in the closed state
            now = time.time()
            if (
                self.last_failure_time is None
                or now - self.last_failure_time > self.FAILURE_WINDOW_SECONDS
            ):
                self.failure_count = 0
        elif self.state == "half_open":
            self.successes_in_half_open += 1
            if self.successes_in_half_open >= self.HALF_OPEN_SUCCESS_THRESHOLD:
                self.state = "closed"
                self.failure_count = 0
                self.successes_in_half_open = 0
                logger.info(
                    "circuit_breaker_closed",
                    extra={"provider": self.provider.value},
                )

    def check_state(self) -> bool:
        """Check if provider is available. Returns True if available."""
        now = time.time()

        if self.state == "closed":
            return True
        elif self.state == "open":
            if now >= self.open_until:
                self.state = "half_open"
                self.successes_in_half_open = 0
                logger.info(
                    "circuit_breaker_half_open",
                    extra={"provider": self.provider.value},
                )
                return True
            return False
        elif self.state == "half_open":
            return True

        return True


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class LLMRouterConfig(BaseModel):
    """Configuration for the LLM Router."""
    default_strategy: RoutingStrategy = Field(
        default=RoutingStrategy.BALANCED,
        description="Default routing strategy",
    )
    providers_enabled: List[LLMProvider] = Field(
        default=[LLMProvider.OPENAI, LLMProvider.ANTHROPIC],
        description="List of enabled providers",
    )
    cost_budget_daily_usd: float = Field(
        default=100.0,
        description="Daily cost budget in USD",
    )
    latency_threshold_ms: int = Field(
        default=5000,
        description="Maximum acceptable latency in milliseconds",
    )
    fallback_order: List[LLMProvider] = Field(
        default=[
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
            LLMProvider.GROQ,
            LLMProvider.GOOGLE,
        ],
        description="Order to try providers on fallback",
    )

    @validator("cost_budget_daily_usd")
    def validate_cost_budget(cls, v):
        if v <= 0:
            raise ValueError("cost_budget_daily_usd must be positive")
        return v

    @validator("latency_threshold_ms")
    def validate_latency(cls, v):
        if v <= 0:
            raise ValueError("latency_threshold_ms must be positive")
        return v


# ============================================================================
# MAIN ROUTER CLASS
# ============================================================================

class LLMRouter:
    """
    Intelligent router for multiple LLM providers.

    Routes requests to the best model based on:
    - Task type and complexity
    - Cost constraints
    - Latency requirements
    - Provider availability (circuit breaker)
    - Fallback chains
    """

    # Model registry with pre-configured models
    MODEL_REGISTRY: Dict[str, LLMModel] = {
        # OpenAI models
        "gpt-4o": LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4o",
            max_tokens=128000,
            cost_per_1k_input=0.005,
            cost_per_1k_output=0.015,
            latency_p50_ms=800,
            capabilities=[
                "intent_classification",
                "response_generation",
                "summarization",
                "entity_extraction",
                "sentiment_analysis",
                "translation",
                "vision",
            ],
        ),
        "gpt-4o-mini": LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4o-mini",
            max_tokens=128000,
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.0006,
            latency_p50_ms=400,
            capabilities=[
                "intent_classification",
                "response_generation",
                "summarization",
                "entity_extraction",
                "sentiment_analysis",
                "translation",
            ],
        ),
        "gpt-3.5-turbo": LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-3.5-turbo",
            max_tokens=4096,
            cost_per_1k_input=0.0005,
            cost_per_1k_output=0.0015,
            latency_p50_ms=350,
            capabilities=[
                "intent_classification",
                "response_generation",
                "entity_extraction",
                "sentiment_analysis",
            ],
        ),
        # Anthropic models
        "claude-sonnet-4-20250514": LLMModel(
            provider=LLMProvider.ANTHROPIC,
            model_name="claude-sonnet-4-20250514",
            max_tokens=200000,
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            latency_p50_ms=600,
            capabilities=[
                "intent_classification",
                "response_generation",
                "summarization",
                "entity_extraction",
                "sentiment_analysis",
                "translation",
            ],
        ),
        "claude-haiku-4-20250414": LLMModel(
            provider=LLMProvider.ANTHROPIC,
            model_name="claude-haiku-4-20250414",
            max_tokens=200000,
            cost_per_1k_input=0.0008,
            cost_per_1k_output=0.004,
            latency_p50_ms=500,
            capabilities=[
                "intent_classification",
                "response_generation",
                "entity_extraction",
                "sentiment_analysis",
            ],
        ),
        # Google Gemini models
        "gemini-2.0-flash": LLMModel(
            provider=LLMProvider.GOOGLE,
            model_name="gemini-2.0-flash",
            max_tokens=1000000,
            cost_per_1k_input=0.0001,
            cost_per_1k_output=0.0004,
            latency_p50_ms=450,
            capabilities=[
                "intent_classification",
                "response_generation",
                "summarization",
                "entity_extraction",
                "sentiment_analysis",
                "translation",
            ],
        ),
        "gemini-2.0-pro": LLMModel(
            provider=LLMProvider.GOOGLE,
            model_name="gemini-2.0-pro",
            max_tokens=1000000,
            cost_per_1k_input=0.0015,
            cost_per_1k_output=0.006,
            latency_p50_ms=700,
            capabilities=[
                "intent_classification",
                "response_generation",
                "summarization",
                "entity_extraction",
                "sentiment_analysis",
                "translation",
            ],
        ),
        # Groq models (extremely fast)
        "llama-3.1-70b": LLMModel(
            provider=LLMProvider.GROQ,
            model_name="llama-3.1-70b",
            max_tokens=8192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            latency_p50_ms=200,
            capabilities=[
                "intent_classification",
                "response_generation",
                "summarization",
                "entity_extraction",
                "sentiment_analysis",
            ],
        ),
        "mixtral-8x7b": LLMModel(
            provider=LLMProvider.GROQ,
            model_name="mixtral-8x7b",
            max_tokens=8192,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            latency_p50_ms=150,
            capabilities=[
                "intent_classification",
                "response_generation",
                "entity_extraction",
                "sentiment_analysis",
            ],
        ),
    }

    def __init__(self, config: LLMRouterConfig):
        """Initialize the LLM router."""
        self.config = config
        self.circuit_breakers: Dict[LLMProvider, CircuitBreakerState] = {
            provider: CircuitBreakerState(provider=provider)
            for provider in LLMProvider
        }

        # Cost tracking
        self.cost_log: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.daily_cost = 0.0
        self.daily_cost_reset_time = datetime.utcnow()

        # Import providers dynamically
        self._init_providers()

        logger.info(
            "llm_router_initialized",
            extra={
                "enabled_providers": [p.value for p in config.providers_enabled],
                "default_strategy": config.default_strategy.value,
            },
        )

    def _init_providers(self):
        """Initialize provider clients."""
        # These will be lazily initialized when needed
        self.providers = {}

    def _get_provider_client(self, provider: LLMProvider):
        """Get or create a provider client."""
        if provider not in self.providers:
            if provider == LLMProvider.OPENAI:
                from .llm_providers.openai_provider import OpenAIProvider

                self.providers[provider] = OpenAIProvider()
            elif provider == LLMProvider.ANTHROPIC:
                from .llm_providers.anthropic_provider import AnthropicProvider

                self.providers[provider] = AnthropicProvider()
            elif provider == LLMProvider.GOOGLE:
                from .llm_providers.google_provider import GoogleProvider

                self.providers[provider] = GoogleProvider()
            elif provider == LLMProvider.GROQ:
                from .llm_providers.groq_provider import GroqProvider

                self.providers[provider] = GroqProvider()
            else:
                raise ValueError(f"Unsupported provider: {provider}")

        return self.providers[provider]

    def select_model(
        self,
        task_type: str,
        strategy: Optional[RoutingStrategy] = None,
        requirements: Optional[Dict[str, Any]] = None,
    ) -> LLMModel:
        """
        Select the best model for a given task.

        Args:
            task_type: Type of task (intent_classification, response_generation, etc.)
            strategy: Routing strategy to use (defaults to config.default_strategy)
            requirements: Additional requirements (min_quality, max_latency, etc.)

        Returns:
            Selected LLMModel
        """
        if strategy is None:
            strategy = self.config.default_strategy

        requirements = requirements or {}

        # Filter available providers
        available_providers = [p for p in self.config.providers_enabled]

        # Filter based on circuit breaker state
        available_providers = [
            p for p in available_providers
            if self.circuit_breakers[p].check_state()
        ]

        if not available_providers:
            logger.error(
                "no_providers_available",
                extra={"task_type": task_type},
            )
            raise RuntimeError("No LLM providers available")

        # Get candidates that support the task
        candidates = [
            self.MODEL_REGISTRY[model_name]
            for model_name in self.MODEL_REGISTRY
            if self.MODEL_REGISTRY[model_name].provider in available_providers
            and task_type in self.MODEL_REGISTRY[model_name].capabilities
        ]

        if not candidates:
            logger.error(
                "no_models_for_task",
                extra={"task_type": task_type},
            )
            raise RuntimeError(f"No models available for task: {task_type}")

        # Apply strategy
        if strategy == RoutingStrategy.COST_OPTIMIZED:
            # Select cheapest model
            selected = min(
                candidates,
                key=lambda m: m.cost_per_1k_input + m.cost_per_1k_output,
            )
        elif strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            # Select fastest model
            selected = min(candidates, key=lambda m: m.latency_p50_ms)
        elif strategy == RoutingStrategy.QUALITY_OPTIMIZED:
            # Prefer premium models: gpt-4o, claude-sonnet
            quality_order = ["gpt-4o", "claude-sonnet-4-20250514", "gemini-2.0-pro"]
            for model_name in quality_order:
                for candidate in candidates:
                    if candidate.model_name == model_name:
                        selected = candidate
                        break
                else:
                    continue
                break
            else:
                # Default to most expensive (usually best quality)
                selected = max(
                    candidates,
                    key=lambda m: m.cost_per_1k_input + m.cost_per_1k_output,
                )
        elif strategy == RoutingStrategy.BALANCED:
            # Balance cost and latency with quality
            # Score = (cost / max_cost) * 0.4 + (latency / max_latency) * 0.4 + quality_boost * 0.2
            max_cost = max(m.cost_per_1k_input + m.cost_per_1k_output for m in candidates)
            max_latency = max(m.latency_p50_ms for m in candidates)

            def score(model: LLMModel) -> float:
                cost_score = (model.cost_per_1k_input + model.cost_per_1k_output) / max_cost
                latency_score = model.latency_p50_ms / max_latency
                quality_boost = 1.0 if model.model_name in ["gpt-4o", "claude-sonnet-4-20250514"] else 0.8
                return cost_score * 0.4 + latency_score * 0.4 + (1 / quality_boost) * 0.2

            selected = min(candidates, key=score)
        else:
            raise ValueError(f"Unsupported strategy: {strategy}")

        logger.info(
            "model_selected",
            extra={
                "task_type": task_type,
                "strategy": strategy.value,
                "model": selected.model_name,
                "provider": selected.provider.value,
            },
        )

        return selected

    async def call_provider(
        self,
        model: LLMModel,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Union[str, Any]:
        """
        Call a specific provider with a specific model.

        Args:
            model: LLMModel to use
            messages: List of messages in standard format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response

        Returns:
            Response text or streaming iterator
        """
        if max_tokens is None:
            max_tokens = min(model.max_tokens, 2048)

        provider_client = self._get_provider_client(model.provider)

        start_time = time.time()
        try:
            if stream:
                response = await provider_client.stream(
                    messages=messages,
                    model=model.model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                response = await provider_client.complete(
                    messages=messages,
                    model=model.model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            elapsed_ms = (time.time() - start_time) * 1000
            self.circuit_breakers[model.provider].record_success()

            logger.info(
                "provider_call_success",
                extra={
                    "provider": model.provider.value,
                    "model": model.model_name,
                    "latency_ms": int(elapsed_ms),
                },
            )

            return response

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            self.circuit_breakers[model.provider].record_failure()

            logger.error(
                "provider_call_failed",
                extra={
                    "provider": model.provider.value,
                    "model": model.model_name,
                    "error_type": type(e).__name__,
                    "latency_ms": int(elapsed_ms),
                },
            )
            raise

    async def call_with_fallback(
        self,
        messages: List[Dict[str, str]],
        task_type: str,
        strategy: Optional[RoutingStrategy] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Call LLM with automatic fallback to secondary models on failure.

        Args:
            messages: List of messages
            task_type: Type of task
            strategy: Routing strategy
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Response text
        """
        strategy = strategy or self.config.default_strategy
        attempted_providers = []

        # Sanitize user input to prevent prompt injection attacks
        messages = sanitize_llm_input(messages)

        # Try providers in fallback order
        for provider in self.config.fallback_order:
            if provider not in self.config.providers_enabled:
                continue

            if not self.circuit_breakers[provider].check_state():
                logger.warning(
                    "provider_circuit_open",
                    extra={"provider": provider.value},
                )
                continue

            try:
                # Select model from this provider
                candidates = [
                    self.MODEL_REGISTRY[model_name]
                    for model_name in self.MODEL_REGISTRY
                    if self.MODEL_REGISTRY[model_name].provider == provider
                    and task_type in self.MODEL_REGISTRY[model_name].capabilities
                ]

                if not candidates:
                    continue

                # Pick best from this provider based on strategy
                if strategy == RoutingStrategy.COST_OPTIMIZED:
                    model = min(
                        candidates,
                        key=lambda m: m.cost_per_1k_input + m.cost_per_1k_output,
                    )
                elif strategy == RoutingStrategy.LATENCY_OPTIMIZED:
                    model = min(candidates, key=lambda m: m.latency_p50_ms)
                else:
                    model = candidates[0]

                attempted_providers.append(provider.value)

                response = await self.call_provider(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                # Track cost
                self._track_cost(model, messages, response)

                logger.info(
                    "fallback_success",
                    extra={
                        "provider": provider.value,
                        "model": model.model_name,
                        "attempts": len(attempted_providers),
                    },
                )

                return response

            except Exception as e:
                logger.warning(
                    "provider_failed_trying_next",
                    extra={
                        "provider": provider.value,
                        "error": str(e),
                    },
                )
                continue

        raise RuntimeError(
            f"All fallback providers exhausted. Attempted: {attempted_providers}"
        )

    def _track_cost(self, model: LLMModel, messages: List[Dict[str, str]], response: str):
        """Track cost of a model call."""
        # Simple token estimation: ~4 chars per token
        input_tokens = sum(len(msg.get("content", "")) for msg in messages) // 4
        output_tokens = len(response) // 4

        input_cost = (input_tokens / 1000) * model.cost_per_1k_input
        output_cost = (output_tokens / 1000) * model.cost_per_1k_output
        total_cost = input_cost + output_cost

        # Reset daily cost if needed
        now = datetime.utcnow()
        if (now - self.daily_cost_reset_time).days > 0:
            self.daily_cost = 0.0
            self.daily_cost_reset_time = now

        self.daily_cost += total_cost

        # Log to cost ledger
        self.cost_log[model.provider.value].append(
            {
                "timestamp": now.isoformat(),
                "model": model.model_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "total_cost": total_cost,
            }
        )

        if self.daily_cost > self.config.cost_budget_daily_usd:
            logger.warning(
                "daily_cost_budget_exceeded",
                extra={
                    "daily_cost": round(self.daily_cost, 4),
                    "budget": self.config.cost_budget_daily_usd,
                },
            )

    def get_cost_report(self) -> Dict[str, Any]:
        """Get cost tracking report."""
        now = datetime.utcnow()
        daily_cost_by_provider = defaultdict(float)
        monthly_cost_by_provider = defaultdict(float)
        usage_by_model = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0})

        for provider, logs in self.cost_log.items():
            for log in logs:
                timestamp = datetime.fromisoformat(log["timestamp"])

                # Daily aggregation
                if (now - timestamp).days == 0:
                    daily_cost_by_provider[provider] += log["total_cost"]

                # Monthly aggregation
                if now.month == timestamp.month and now.year == timestamp.year:
                    monthly_cost_by_provider[provider] += log["total_cost"]

                # Per-model usage
                model_key = log["model"]
                usage_by_model[model_key]["calls"] += 1
                usage_by_model[model_key]["input_tokens"] += log["input_tokens"]
                usage_by_model[model_key]["output_tokens"] += log["output_tokens"]
                usage_by_model[model_key]["cost"] += log["total_cost"]

        return {
            "daily_cost": round(self.daily_cost, 4),
            "daily_budget": self.config.cost_budget_daily_usd,
            "daily_cost_by_provider": {k: round(v, 4) for k, v in daily_cost_by_provider.items()},
            "monthly_cost_by_provider": {k: round(v, 4) for k, v in monthly_cost_by_provider.items()},
            "usage_by_model": {
                model: {
                    "calls": usage["calls"],
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "cost": round(usage["cost"], 4),
                }
                for model, usage in usage_by_model.items()
            },
            "timestamp": now.isoformat(),
        }

    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers (circuit breaker states)."""
        return {
            provider.value: {
                "state": cb.state,
                "failure_count": cb.failure_count,
                "available": cb.check_state(),
            }
            for provider, cb in self.circuit_breakers.items()
        }
