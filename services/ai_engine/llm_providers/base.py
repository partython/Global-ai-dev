"""
Abstract base class for LLM providers.

Defines the interface that all provider implementations must follow.
Includes common utilities for token counting and error handling.
"""

import abc
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseLLMProvider(abc.ABC):
    """
    Abstract base class for LLM provider implementations.

    All provider subclasses must implement the complete() and stream() methods.
    Token counting is handled via estimation based on character count.
    """

    def __init__(self, provider_name: str):
        """Initialize the base provider."""
        self.provider_name = provider_name
        self.logger = logging.getLogger(f"llm_provider.{provider_name}")

    @abc.abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text response
        """
        pass

    @abc.abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming completion for the given messages.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            Text chunks as they become available
        """
        pass

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count using character-based heuristic.

        Approximation: ~4 characters per token (reasonable for English).
        More accurate for actual token counting would require tokenizer library.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4

    @staticmethod
    def estimate_tokens_messages(messages: List[Dict[str, str]]) -> int:
        """
        Estimate token count for a list of messages.

        Accounts for message formatting overhead (~10 tokens per message).

        Args:
            messages: List of message dicts

        Returns:
            Estimated total token count
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += BaseLLMProvider.estimate_tokens(content)
            total += 10  # Overhead for message structure
        return total

    def validate_api_key(self, api_key: Optional[str], provider_name: str) -> None:
        """
        Validate that required API key is set.

        Args:
            api_key: The API key to validate
            provider_name: Name of the provider (for error message)

        Raises:
            RuntimeError: If API key is not set
        """
        if not api_key:
            raise RuntimeError(
                f"{provider_name} API key not set. "
                f"Please set the appropriate environment variable."
            )

    def log_call(
        self,
        model: str,
        tokens_input: int,
        tokens_output: int,
        cost: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Log a provider call with structured logging.

        Args:
            model: Model name
            tokens_input: Input tokens used
            tokens_output: Output tokens generated
            cost: Estimated cost in USD
            error: Error message if call failed
        """
        if error:
            self.logger.error(
                "provider_call_failed",
                extra={
                    "model": model,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "error": error,
                },
            )
        else:
            self.logger.info(
                "provider_call_success",
                extra={
                    "model": model,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "cost": round(cost, 6) if cost else None,
                },
            )

    @staticmethod
    def format_error_message(error: Exception, provider_name: str) -> str:
        """
        Format an error message for structured logging.

        Args:
            error: The exception that occurred
            provider_name: Name of the provider

        Returns:
            Formatted error message
        """
        error_type = type(error).__name__
        error_msg = str(error)
        return f"{provider_name} error ({error_type}): {error_msg}"
