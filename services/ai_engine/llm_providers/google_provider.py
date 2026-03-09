"""
Google Gemini provider implementation.

Supports:
  • gemini-2.0-flash (fastest, best for cost)
  • gemini-2.0-pro (highest quality)

Features:
  • Async client using google.generativeai
  • Message format conversion (OpenAI → Gemini)
  • Streaming support
  • Cost tracking
"""

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    raise ImportError(
        "Google generativeai package required for Google provider. "
        "Install with: pip install google-generativeai"
    )

from .base import BaseLLMProvider


class GoogleProvider(BaseLLMProvider):
    """Google Gemini model provider."""

    # Model pricing (as of latest update)
    MODEL_PRICING = {
        "gemini-2.0-flash": {
            "input": 0.0001,  # per 1K tokens
            "output": 0.0004,
        },
        "gemini-2.0-pro": {
            "input": 0.0015,
            "output": 0.006,
        },
        "gemini-1.5-flash": {
            "input": 0.0001,
            "output": 0.0004,
        },
        "gemini-1.5-pro": {
            "input": 0.0015,
            "output": 0.006,
        },
    }

    # Rate limiting configuration
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds

    def __init__(self):
        """Initialize Google provider."""
        super().__init__("google")

        api_key = os.getenv("GOOGLE_AI_KEY")
        self.validate_api_key(api_key, "Google")

        genai.configure(api_key=api_key)
        self.logger.info("google_provider_initialized")

    def _convert_messages_to_gemini(
        self, messages: List[Dict[str, str]]
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        """
        Convert OpenAI message format to Google Gemini format.

        Gemini doesn't have a separate system parameter like Anthropic,
        but uses the first message differently. We convert system role
        into a prefix for the first user message.

        Args:
            messages: List of message dicts in OpenAI format

        Returns:
            Tuple of (system_prompt, converted_messages)
        """
        if not messages:
            return None, []

        system_prompt = None
        converted = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role == "user":
                converted.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                converted.append({"role": "model", "parts": [content]})
            else:
                # Default to user role for unknown roles
                converted.append({"role": "user", "parts": [content]})

        return system_prompt, converted

    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion using Google Gemini API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Google model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response

        Raises:
            RuntimeError: If all retry attempts fail
        """
        retry_count = 0
        retry_delay = self.INITIAL_RETRY_DELAY

        system_prompt, gemini_messages = self._convert_messages_to_gemini(messages)

        while retry_count < self.MAX_RETRIES:
            try:
                tokens_input = self.estimate_tokens_messages(messages)

                gemini_model = genai.GenerativeModel(
                    model_name=model,
                    system_instruction=system_prompt,
                )

                generation_config = genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens or 2048,
                )

                response = await asyncio.to_thread(
                    gemini_model.generate_content,
                    gemini_messages,
                    generation_config=generation_config,
                )

                content = response.text
                tokens_output = self.estimate_tokens(content)

                cost = self._calculate_cost(model, tokens_input, tokens_output)
                self.log_call(model, tokens_input, tokens_output, cost)

                return content

            except ResourceExhausted as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    error_msg = self.format_error_message(e, "Google")
                    self.log_call(model, tokens_input, 0, error=error_msg)
                    raise RuntimeError(f"Google rate limit exceeded: {str(e)}")

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
                error_msg = self.format_error_message(e, "Google")
                self.logger.error(
                    "google_completion_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"Google completion failed: {str(e)}")

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion using Google Gemini API.

        Args:
            messages: List of message dicts
            model: Google model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Text chunks as they become available

        Raises:
            RuntimeError: If streaming fails
        """
        retry_count = 0
        retry_delay = self.INITIAL_RETRY_DELAY

        system_prompt, gemini_messages = self._convert_messages_to_gemini(messages)

        while retry_count < self.MAX_RETRIES:
            try:
                tokens_input = self.estimate_tokens_messages(messages)

                gemini_model = genai.GenerativeModel(
                    model_name=model,
                    system_instruction=system_prompt,
                )

                generation_config = genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens or 2048,
                )

                accumulated_content = ""

                response = await asyncio.to_thread(
                    gemini_model.generate_content,
                    gemini_messages,
                    generation_config=generation_config,
                    stream=True,
                )

                async for chunk in await asyncio.to_thread(
                    lambda: response
                ):
                    if chunk.text:
                        accumulated_content += chunk.text
                        yield chunk.text

                tokens_output = self.estimate_tokens(accumulated_content)
                cost = self._calculate_cost(model, tokens_input, tokens_output)
                self.log_call(model, tokens_input, tokens_output, cost)

                return

            except ResourceExhausted as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    error_msg = self.format_error_message(e, "Google")
                    self.logger.error(
                        "google_stream_rate_limit",
                        extra={
                            "model": model,
                            "error": error_msg,
                        },
                    )
                    raise RuntimeError(f"Google rate limit exceeded: {str(e)}")

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
                error_msg = self.format_error_message(e, "Google")
                self.logger.error(
                    "google_stream_error",
                    extra={
                        "model": model,
                        "error": error_msg,
                    },
                )
                raise RuntimeError(f"Google streaming failed: {str(e)}")

    def _calculate_cost(
        self, model: str, tokens_input: int, tokens_output: int
    ) -> float:
        """
        Calculate estimated cost for Google API call.

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
