"""
Groq provider implementation for ultra-fast inference.

Supports:
  • llama-3.1-70b (fast, quality)
  • mixtral-8x7b (fastest)

Features:
  • Async client using groq SDK (OpenAI-compatible)
  • Optimized for speed (150-200ms latency)
  • Streaming support
  • Cost tracking
  • No standard pricing (often free tier available)
"""

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from groq import AsyncGroq, RateLimitError
except ImportError:
    raise ImportError(
        "Groq package required for Groq provider. "
        "Install with: pip install groq"
    )

from .base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    """Groq ultra-fast inference provider."""

    # Groq pricing (typically free or very cheap)
    MODEL_PRICING = {
        "llama-3.1-70b": {
            "input": 0.0,
            "output": 0.0,
        },
        "mixtral-8x7b": {
            "input": 0.0,
            "output": 0.0,
        },
        "llama-3.1-8b": {
            "input": 0.0,
            "output": 0.0,
        },
    }

    # Rate limiting configuration
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds

    def __init__(self):
        """Initialize Groq provider."""
        super().__init__("groq")

        api_key = os.getenv("GROQ_API_KEY")
        self.validate_api_key(api_key, "Groq")

        self.client = AsyncGroq(api_key=api_key)
        self.logger.info("groq_provider_initialized")

    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion using Groq API with automatic retry on rate limits.

        Groq uses OpenAI-compatible SDK, so message format is standard.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Groq model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response

        Raises:
            RuntimeError: If all retry attempts fail
        """
        retry_count = 0
        retry_delay = self.INITIAL_RETRY_DELAY

        while retry_count < self.MAX_RETRIES:
            try:
                tokens_input = self.estimate_tokens_messages(messages)

                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens or 2048,
                )

                content = response.choices[0].message.content
                tokens_output = self.estimate_tokens(content)

                cost = self._calculate_cost(model, tokens_input, tokens_output)
                self.log_call(model, tokens_input, tokens_output, cost)

                return content

            except RateLimitError as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    error_msg = self.format_error_message(e, "Groq")
                    self.log_call(model, tokens_input, 0, error=error_msg)
                    raise RuntimeError(f"Groq rate limit exceeded: {str(e)}")

                wait_time = retry_delay * (2 ** (retry_count - 1))
                self.logger.warning(
                    "rate_limit_retry",
                    extra={
                        "model": model,
                        "retry_count": retry_count,
                        "wait_seconds": wait_time,
                    },
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                error_msg = self.format_error_message(e, "Groq")
                self.logger.error(
                    "groq_completion_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"Groq completion failed: {str(e)}")

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion using Groq API.

        Args:
            messages: List of message dicts
            model: Groq model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Text chunks as they become available

        Raises:
            RuntimeError: If streaming fails
        """
        retry_count = 0
        retry_delay = self.INITIAL_RETRY_DELAY

        while retry_count < self.MAX_RETRIES:
            try:
                tokens_input = self.estimate_tokens_messages(messages)

                stream = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens or 2048,
                    stream=True,
                )

                accumulated_content = ""

                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        accumulated_content += content
                        yield content

                tokens_output = self.estimate_tokens(accumulated_content)
                cost = self._calculate_cost(model, tokens_input, tokens_output)
                self.log_call(model, tokens_input, tokens_output, cost)

                return

            except RateLimitError as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    error_msg = self.format_error_message(e, "Groq")
                    self.logger.error(
                        "groq_stream_rate_limit",
                        extra={
                            "model": model,
                            "error": error_msg,
                        },
                    )
                    raise RuntimeError(f"Groq rate limit exceeded: {str(e)}")

                wait_time = retry_delay * (2 ** (retry_count - 1))
                self.logger.warning(
                    "rate_limit_retry_stream",
                    extra={
                        "model": model,
                        "retry_count": retry_count,
                        "wait_seconds": wait_time,
                    },
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                error_msg = self.format_error_message(e, "Groq")
                self.logger.error(
                    "groq_stream_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"Groq streaming failed: {str(e)}")

    def _calculate_cost(
        self, model: str, tokens_input: int, tokens_output: int
    ) -> float:
        """
        Calculate estimated cost for Groq API call.

        Groq is typically free or has very low cost.

        Args:
            model: Model name
            tokens_input: Input tokens used
            tokens_output: Output tokens generated

        Returns:
            Estimated cost in USD (usually 0.0)
        """
        if model not in self.MODEL_PRICING:
            self.logger.warning(
                "unknown_model_pricing",
                extra={"model": model},
            )
            return 0.0

        pricing = self.MODEL_PRICING[model]
        input_cost = (tokens_input / 1000) * pricing["input"]
        output_cost = (tokens_output / 1000) * pricing["output"]

        return input_cost + output_cost
