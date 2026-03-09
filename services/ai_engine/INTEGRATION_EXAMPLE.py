"""
Integration Example: Using LLM Router in the Priya Global AI Engine Service

This module shows how to integrate the Multi-LLM Router into the existing
AI Engine service endpoints.

NOTE: This is example code showing best practices. Copy patterns as needed
into your actual service endpoints.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from llm_router import (
    LLMRouter,
    LLMRouterConfig,
    RoutingStrategy,
    LLMProvider,
)

logger = logging.getLogger(__name__)


# ============================================================================
# INITIALIZATION (Run at service startup)
# ============================================================================

def init_llm_router() -> LLMRouter:
    """
    Initialize the LLM router with configuration.

    In a real service, this would be called once at startup and stored
    in the service's dependency injection container.
    """
    config = LLMRouterConfig(
        default_strategy=RoutingStrategy.BALANCED,
        providers_enabled=[
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
            LLMProvider.GROQ,
            LLMProvider.GOOGLE,
        ],
        cost_budget_daily_usd=100.0,
        latency_threshold_ms=5000,
        fallback_order=[
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
            LLMProvider.GROQ,
            LLMProvider.GOOGLE,
        ],
    )

    router = LLMRouter(config)
    logger.info("llm_router_initialized")
    return router


# Global router instance (in real code, use dependency injection)
_router_instance: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Get the global router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = init_llm_router()
    return _router_instance


# ============================================================================
# EXAMPLE 1: Intent Classification
# ============================================================================

async def classify_intent_with_fallback(
    user_message: str,
    tenant_id: str,
) -> Dict[str, str]:
    """
    Classify user intent using cost-optimized LLM routing.

    This example shows how to:
    - Use cost-optimized strategy
    - Handle fallback failures
    - Track execution

    Args:
        user_message: Customer message text
        tenant_id: Tenant identifier for logging

    Returns:
        Dict with intent classification result
    """
    router = get_router()

    messages = [
        {
            "role": "system",
            "content": "You are an intent classifier. Respond with only: GREETING, COMPLAINT, PRICING, ORDER_STATUS, GENERAL, or ESCALATION",
        },
        {"role": "user", "content": user_message},
    ]

    try:
        response = await router.call_with_fallback(
            messages=messages,
            task_type="intent_classification",
            strategy=RoutingStrategy.COST_OPTIMIZED,
            temperature=0.2,  # Low temperature for deterministic output
            max_tokens=20,
        )

        intent = response.strip().upper()

        logger.info(
            "intent_classified",
            extra={
                "tenant_id": tenant_id,
                "intent": intent,
                "message_length": len(user_message),
            },
        )

        return {
            "intent": intent,
            "confidence": "high",
            "model": "cost_optimized",
        }

    except RuntimeError as e:
        logger.error(
            "intent_classification_failed",
            extra={
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        # Fallback to local classifier
        return {
            "intent": "GENERAL",
            "confidence": "low",
            "error": "LLM unavailable, using fallback",
        }


# ============================================================================
# EXAMPLE 2: Response Generation (Streaming)
# ============================================================================

async def generate_sales_response_streaming(
    customer_message: str,
    conversation_history: List[Dict[str, str]],
    tenant_id: str,
):
    """
    Generate sales response using quality-optimized routing.

    This example shows how to:
    - Use quality-optimized strategy
    - Implement streaming response
    - Build context from conversation history

    Args:
        customer_message: Latest customer message
        conversation_history: Previous messages in conversation
        tenant_id: Tenant identifier

    Yields:
        Response chunks as they become available
    """
    router = get_router()

    system_prompt = """You are a helpful sales assistant for an e-commerce company.
    - Be friendly and professional
    - Address customer concerns directly
    - Suggest relevant products when appropriate
    - Keep responses concise (under 200 tokens)"""

    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_history,
        {"role": "user", "content": customer_message},
    ]

    try:
        # Select best model for quality
        model = router.select_model(
            task_type="response_generation",
            strategy=RoutingStrategy.QUALITY_OPTIMIZED,
        )

        logger.info(
            "response_generation_started",
            extra={
                "tenant_id": tenant_id,
                "model": model.model_name,
            },
        )

        # Stream response
        response_stream = await router.call_provider(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
            stream=True,
        )

        async for chunk in response_stream:
            yield chunk

    except Exception as e:
        logger.error(
            "response_generation_failed",
            extra={
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        yield "I apologize, but I'm experiencing technical difficulties. Please try again in a moment."


# ============================================================================
# EXAMPLE 3: Batch Processing with Cost Optimization
# ============================================================================

async def batch_summarize_feedback(
    feedback_items: List[str],
    tenant_id: str,
) -> List[Dict[str, str]]:
    """
    Batch summarize customer feedback using cost-optimized routing.

    This example shows how to:
    - Process multiple items with consistent strategy
    - Handle mixed success/failure
    - Track costs across batch

    Args:
        feedback_items: List of customer feedback texts
        tenant_id: Tenant identifier

    Returns:
        List of summaries with metadata
    """
    router = get_router()
    results = []

    for i, feedback in enumerate(feedback_items):
        try:
            messages = [
                {
                    "role": "system",
                    "content": "Summarize the following customer feedback in 1-2 sentences.",
                },
                {"role": "user", "content": feedback},
            ]

            summary = await router.call_with_fallback(
                messages=messages,
                task_type="summarization",
                strategy=RoutingStrategy.COST_OPTIMIZED,
                temperature=0.5,
                max_tokens=100,
            )

            results.append({
                "original_length": len(feedback),
                "summary": summary,
                "status": "success",
            })

            logger.info(
                "feedback_summarized",
                extra={
                    "tenant_id": tenant_id,
                    "batch_index": i,
                    "original_length": len(feedback),
                },
            )

        except Exception as e:
            results.append({
                "original_length": len(feedback),
                "summary": None,
                "status": "failed",
                "error": str(e),
            })

            logger.warning(
                "feedback_summarization_failed",
                extra={
                    "tenant_id": tenant_id,
                    "batch_index": i,
                    "error": str(e),
                },
            )

    return results


# ============================================================================
# EXAMPLE 4: Latency-Critical Real-Time Response
# ============================================================================

async def generate_quick_reply(
    user_message: str,
    tenant_id: str,
) -> Dict[str, str]:
    """
    Generate a quick reply optimized for latency.

    This example shows how to:
    - Use latency-optimized strategy
    - Set tight time constraints
    - Handle timeout gracefully

    Args:
        user_message: Customer message
        tenant_id: Tenant identifier

    Returns:
        Quick response dict
    """
    router = get_router()

    messages = [
        {
            "role": "system",
            "content": "You are a fast chatbot. Answer in 1-2 sentences only.",
        },
        {"role": "user", "content": user_message},
    ]

    try:
        # Use latency-optimized strategy for real-time response
        response = await asyncio.wait_for(
            router.call_with_fallback(
                messages=messages,
                task_type="response_generation",
                strategy=RoutingStrategy.LATENCY_OPTIMIZED,
                temperature=0.6,
                max_tokens=50,
            ),
            timeout=3.0,  # 3-second timeout
        )

        return {
            "reply": response,
            "latency_optimized": True,
            "timed_out": False,
        }

    except asyncio.TimeoutError:
        logger.warning(
            "quick_reply_timeout",
            extra={"tenant_id": tenant_id},
        )
        return {
            "reply": "Thanks for your message! I'll get back to you shortly.",
            "latency_optimized": False,
            "timed_out": True,
        }

    except Exception as e:
        logger.error(
            "quick_reply_failed",
            extra={
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        return {
            "reply": "I'm having trouble responding right now. Please try again.",
            "error": str(e),
            "timed_out": False,
        }


# ============================================================================
# EXAMPLE 5: Cost Monitoring and Reporting
# ============================================================================

async def report_llm_costs(tenant_id: str) -> Dict[str, any]:
    """
    Generate LLM cost report for monitoring.

    This example shows how to:
    - Track costs across providers
    - Alert on budget overages
    - Report per-model usage

    Args:
        tenant_id: Tenant identifier

    Returns:
        Cost report dict
    """
    router = get_router()

    cost_report = router.get_cost_report()
    provider_status = router.get_provider_status()

    # Check if budget exceeded
    budget_exceeded = cost_report["daily_cost"] > cost_report["daily_budget"]

    if budget_exceeded:
        logger.warning(
            "daily_budget_exceeded",
            extra={
                "tenant_id": tenant_id,
                "daily_cost": cost_report["daily_cost"],
                "budget": cost_report["daily_budget"],
            },
        )

    return {
        "tenant_id": tenant_id,
        "daily_cost": cost_report["daily_cost"],
        "daily_budget": cost_report["daily_budget"],
        "budget_exceeded": budget_exceeded,
        "by_provider": cost_report["daily_cost_by_provider"],
        "by_model": cost_report["usage_by_model"],
        "provider_status": provider_status,
        "timestamp": cost_report["timestamp"],
    }


# ============================================================================
# EXAMPLE 6: Graceful Degradation
# ============================================================================

async def smart_response_with_fallback(
    user_message: str,
    priority_level: str,
    tenant_id: str,
) -> Dict[str, str]:
    """
    Generate response with strategy based on priority level.

    This example shows how to:
    - Adjust strategy based on importance
    - Handle failures gracefully
    - Maintain service availability

    Args:
        user_message: Customer message
        priority_level: "high", "normal", "low"
        tenant_id: Tenant identifier

    Returns:
        Response dict with strategy info
    """
    router = get_router()

    # Choose strategy based on priority
    if priority_level == "high":
        # High priority: use quality + fallback
        strategy = RoutingStrategy.QUALITY_OPTIMIZED
        max_retries = 3
    elif priority_level == "normal":
        # Normal: use balanced strategy
        strategy = RoutingStrategy.BALANCED
        max_retries = 2
    else:
        # Low priority: cost optimized
        strategy = RoutingStrategy.COST_OPTIMIZED
        max_retries = 1

    messages = [
        {
            "role": "system",
            "content": f"You are a helpful assistant. Priority level: {priority_level}",
        },
        {"role": "user", "content": user_message},
    ]

    attempt = 0
    last_error = None

    while attempt < max_retries:
        try:
            response = await router.call_with_fallback(
                messages=messages,
                task_type="response_generation",
                strategy=strategy,
                temperature=0.7,
                max_tokens=300,
            )

            logger.info(
                "smart_response_generated",
                extra={
                    "tenant_id": tenant_id,
                    "priority_level": priority_level,
                    "strategy": strategy.value,
                    "attempt": attempt + 1,
                },
            )

            return {
                "response": response,
                "success": True,
                "strategy": strategy.value,
                "attempts": attempt + 1,
            }

        except Exception as e:
            last_error = e
            attempt += 1

            logger.warning(
                "smart_response_retry",
                extra={
                    "tenant_id": tenant_id,
                    "attempt": attempt,
                    "priority_level": priority_level,
                    "error": str(e),
                },
            )

            if attempt < max_retries:
                # Wait before retry (exponential backoff)
                await asyncio.sleep(2 ** attempt)

    # All retries exhausted - return graceful fallback
    logger.error(
        "smart_response_exhausted",
        extra={
            "tenant_id": tenant_id,
            "priority_level": priority_level,
            "attempts": max_retries,
        },
    )

    fallback_responses = {
        "high": "I apologize for the difficulty. Let me connect you with a human agent.",
        "normal": "Thank you for your patience. I'm working on this and will respond shortly.",
        "low": "I'm temporarily unavailable. Please check back soon.",
    }

    return {
        "response": fallback_responses[priority_level],
        "success": False,
        "strategy": "fallback",
        "attempts": max_retries,
        "error": str(last_error),
    }


# ============================================================================
# MAIN ENTRY POINT FOR TESTING
# ============================================================================

async def main():
    """Run example usage of the LLM router."""
    print("\n=== LLM Router Integration Examples ===\n")

    # Example 1: Intent classification
    print("1. Intent Classification")
    result = await classify_intent_with_fallback(
        "Where is my order?",
        "tenant_123"
    )
    print(f"   Result: {result}\n")

    # Example 5: Cost reporting
    print("5. Cost Reporting")
    report = await report_llm_costs("tenant_123")
    print(f"   Daily cost: ${report['daily_cost']}")
    print(f"   Budget: ${report['daily_budget']}")
    print(f"   By provider: {report['by_provider']}\n")

    # Example 6: Smart response with fallback
    print("6. Smart Response (High Priority)")
    result = await smart_response_with_fallback(
        "I need urgent help with my account",
        "high",
        "tenant_123"
    )
    print(f"   Success: {result['success']}")
    print(f"   Strategy: {result['strategy']}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
