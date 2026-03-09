"""
Anthropic provider implementation for Claude models.

Supports:
  • claude-sonnet-4-20250514 (latest, high quality)
  • claude-haiku-4-20250414 (cost-optimized)

Features:
  • Async client
  • System message handling (Anthropic uses separate system parameter)
  • Streaming support
  • Cost tracking
  • Extended thinking support
"""

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from anthropic import AsyncAnthropic, RateLimitError
except ImportError:
    raise ImportError(
        "Anthropic package required for Anthropic provider. "
        "Install with: pip install anthropic"
    )

from .base import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude model provider."""

    # Model pricing (as of latest update)
    MODEL_PRICING = {
        "claude-sonnet-4-20250514": {
            "input": 0.003,  # per 1K tokens
            "output": 0.015,
        },
        "claude-haiku-4-20250414": {
            "input": 0.0008,
            "output": 0.004,
        },
        "claude-3-5-sonnet-20241022": {
            "input": 0.003,
            "output": 0.015,
        },
    }

    # Rate limiting configuration
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds

    def __init__(self):
        """Initialize Anthropic provider."""
        super().__init__("anthropic")

        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.validate_api_key(api_key, "Anthropic")

        self.client = AsyncAnthropic(api_key=api_key)
        self.logger.info("anthropic_provider_initialized")

    def _separate_system_message(
        self, messages: List[Dict[str, str]]
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Extract system message from messages list.

        Anthropic uses a separate 'system' parameter rather than a system role
        in the messages list. This extracts it if present.

        Args:
            messages: List of message dicts

        Returns:
            Tuple of (system_message, remaining_messages)
        """
        if not messages:
            return None, messages

        if messages[0].get("role") == "system":
            system_msg = messages[0].get("content")
            remaining = messages[1:]
            return system_msg, remaining

        return None, messages

    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion using Anthropic API.

        Handles Anthropic's separate system parameter and automatic retries.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Anthropic model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response

        Raises:
            RuntimeError: If all retry attempts fail
        """
        retry_count = 0
        retry_delay = self.INITIAL_RETRY_DELAY

        system_message, messages_without_system = self._separate_system_message(messages)

        while retry_count < self.MAX_RETRIES:
            try:
                tokens_input = self.estimate_tokens_messages(messages)

                call_kwargs = {
                    "model": model,
                    "messages": messages_without_system,
                    "temperature": temperature,
                    "max_tokens": max_tokens or 2048,
                }

                if system_message:
                    call_kwargs["system"] = system_message

                response = await self.client.messages.create(**call_kwargs)

                content = response.content[0].text
                tokens_output = self.estimate_tokens(content)

                cost = self._calculate_cost(model, tokens_input, tokens_output)
                self.log_call(model, tokens_input, tokens_output, cost)

                return content

            except RateLimitError as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    error_msg = self.format_error_message(e, "Anthropic")
                    self.log_call(model, tokens_input, 0, error=error_msg)
                    raise RuntimeError(f"Anthropic rate limit exceeded: {str(e)}")

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
                error_msg = self.format_error_message(e, "Anthropic")
                self.logger.error(
                    "anthropic_completion_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"Anthropic completion failed: {str(e)}")

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion using Anthropic API.

        Args:
            messages: List of message dicts
            model: Anthropic model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Text chunks as they become available

        Raises:
            RuntimeError: If streaming fails
        """
        retry_count = 0
        retry_delay = self.INITIAL_RETRY_DELAY

        system_message, messages_without_system = self._separate_system_message(messages)

        while retry_count < self.MAX_RETRIES:
            try:
                tokens_input = self.estimate_tokens_messages(messages)

                call_kwargs = {
                    "model": model,
                    "messages": messages_without_system,
                    "temperature": temperature,
                    "max_tokens": max_tokens or 2048,
                }

                if system_message:
                    call_kwargs["system"] = system_message

                accumulated_content = ""

                async with await self.client.messages.stream(**call_kwargs) as stream:
                    async for text in stream.text_stream:
                        accumulated_content += text
                        yield text

                tokens_output = self.estimate_tokens(accumulated_content)
                cost = self._calculate_cost(model, tokens_input, tokens_output)
                self.log_call(model, tokens_input, tokens_output, cost)

                return

            except RateLimitError as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    error_msg = self.format_error_message(e, "Anthropic")
                    self.logger.error(
                        "anthropic_stream_rate_limit",
                        extra={
                            "model": model,
                            "error": error_msg,
                        },
                    )
                    raise RuntimeError(f"Anthropic rate limit exceeded: {str(e)}")

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
                error_msg = self.format_error_message(e, "Anthropic")
                self.logger.error(
                    "anthropic_stream_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"Anthropic streaming failed: {str(e)}")

    def _calculate_cost(
        self, model: str, tokens_input: int, tokens_output: int
    ) -> float:
        """
        Calculate estimated cost for Anthropic API call.

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
