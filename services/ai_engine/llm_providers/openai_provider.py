"""
OpenAI provider implementation for GPT models.

Supports:
  • gpt-4o (latest vision model)
  • gpt-4o-mini (cost-optimized)
  • gpt-3.5-turbo (legacy fast model)

Features:
  • Async client with aiohttp
  • Exponential backoff for rate limiting
  • Streaming support
  • Cost tracking
"""

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI, RateLimitError
except ImportError:
    raise ImportError(
        "OpenAI package required for OpenAI provider. "
        "Install with: pip install openai"
    )

from .base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT model provider."""

    # Model pricing (as of latest update)
    MODEL_PRICING = {
        "gpt-4o": {
            "input": 0.005,  # per 1K tokens
            "output": 0.015,
        },
        "gpt-4o-mini": {
            "input": 0.00015,
            "output": 0.0006,
        },
        "gpt-3.5-turbo": {
            "input": 0.0005,
            "output": 0.0015,
        },
    }

    # Rate limiting configuration
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds

    def __init__(self):
        """Initialize OpenAI provider."""
        super().__init__("openai")

        api_key = os.getenv("OPENAI_API_KEY")
        self.validate_api_key(api_key, "OpenAI")

        self.client = AsyncOpenAI(api_key=api_key)
        self.logger.info("openai_provider_initialized")

    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion using OpenAI API with automatic retry on rate limits.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: OpenAI model name
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
                    error_msg = self.format_error_message(e, "OpenAI")
                    self.log_call(model, tokens_input, 0, error=error_msg)
                    raise RuntimeError(f"OpenAI rate limit exceeded: {str(e)}")

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
                error_msg = self.format_error_message(e, "OpenAI")
                self.logger.error(
                    "openai_completion_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"OpenAI completion failed: {str(e)}")

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion using OpenAI API.

        Args:
            messages: List of message dicts
            model: OpenAI model name
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
                    error_msg = self.format_error_message(e, "OpenAI")
                    self.logger.error(
                        "openai_stream_rate_limit",
                        extra={
                            "model": model,
                            "error": error_msg,
                        },
                    )
                    raise RuntimeError(f"OpenAI rate limit exceeded: {str(e)}")

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
                error_msg = self.format_error_message(e, "OpenAI")
                self.logger.error(
                    "openai_stream_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"OpenAI streaming failed: {str(e)}")

    def _calculate_cost(
        self, model: str, tokens_input: int, tokens_output: int
    ) -> float:
        """
        Calculate estimated cost for OpenAI API call.

        Args:
            model: Model name
            tokens_input: Input tokens used
            tokens_output: Output tokens generated

        Returns:
            Estimated cost in USD
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
