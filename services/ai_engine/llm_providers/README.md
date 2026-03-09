# LLM Providers Package

This package contains provider-specific implementations for multiple LLM services.

## Structure

```
llm_providers/
├── __init__.py           # Package exports
├── base.py               # Abstract base class
├── openai_provider.py    # OpenAI GPT implementation
├── anthropic_provider.py # Anthropic Claude implementation
├── google_provider.py    # Google Gemini implementation
└── groq_provider.py      # Groq fast inference implementation
```

## Base Provider Interface

All providers inherit from `BaseLLMProvider` and implement two async methods:

```python
class BaseLLMProvider(abc.ABC):
    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a completion."""
        pass

    async def stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming completion."""
        pass
```

## Provider Specifications

### OpenAIProvider

**Supported Models:**
- `gpt-4o` - Latest vision-capable model
- `gpt-4o-mini` - Cost-optimized variant
- `gpt-3.5-turbo` - Fast, older model

**Features:**
- Official `openai` library
- Async client with aiohttp
- Exponential backoff on rate limits (max 3 retries)
- Cost tracking with official pricing

**Environment Variable:**
```bash
export OPENAI_API_KEY="sk-..."
```

**Pricing (per 1K tokens):**
- gpt-4o: $0.005 input, $0.015 output
- gpt-4o-mini: $0.00015 input, $0.0006 output
- gpt-3.5-turbo: $0.0005 input, $0.0015 output

**Latency (p50):**
- gpt-4o: 800ms
- gpt-4o-mini: 400ms
- gpt-3.5-turbo: 350ms

### AnthropicProvider

**Supported Models:**
- `claude-sonnet-4-20250514` - Latest Claude Sonnet
- `claude-haiku-4-20250414` - Fast, compact model
- `claude-3-5-sonnet-20241022` - Previous generation

**Features:**
- Official `anthropic` library
- Async client
- System message handling (separate `system` parameter)
- Streaming with async context managers
- Rate limit retry logic (max 3 retries)

**Environment Variable:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Pricing (per 1K tokens):**
- claude-sonnet-4-20250514: $0.003 input, $0.015 output
- claude-haiku-4-20250414: $0.0008 input, $0.004 output

**Latency (p50):**
- claude-sonnet-4-20250514: 600ms
- claude-haiku-4-20250414: 500ms

**Special Handling:**
Anthropic uses a separate `system` parameter instead of a "system" role message.
The provider automatically extracts system messages from the messages list and
passes them via the `system` parameter.

```python
# Input messages:
messages = [
    {"role": "system", "content": "You are helpful..."},
    {"role": "user", "content": "Hello"}
]

# Sent to Anthropic as:
# client.messages.create(
#     system="You are helpful...",
#     messages=[{"role": "user", "content": "Hello"}]
# )
```

### GoogleProvider

**Supported Models:**
- `gemini-2.0-flash` - Fastest, best for cost
- `gemini-2.0-pro` - Highest quality
- `gemini-1.5-flash` - Previous generation
- `gemini-1.5-pro` - Previous generation

**Features:**
- `google.generativeai` library
- Message format conversion (OpenAI → Gemini)
- Threading adapter for synchronous library
- Cost tracking with official pricing

**Environment Variable:**
```bash
export GOOGLE_AI_KEY="AIza..."
```

**Pricing (per 1K tokens):**
- gemini-2.0-flash: $0.0001 input, $0.0004 output
- gemini-2.0-pro: $0.0015 input, $0.006 output

**Latency (p50):**
- gemini-2.0-flash: 450ms
- gemini-2.0-pro: 700ms

**Special Handling:**
Google's `google.generativeai` library is synchronous. The provider uses
`asyncio.to_thread()` to run calls in a thread pool without blocking the
event loop.

```python
response = await asyncio.to_thread(
    gemini_model.generate_content,
    messages,
    generation_config=config
)
```

### GroqProvider

**Supported Models:**
- `llama-3.1-70b` - Fast, high quality
- `mixtral-8x7b` - Fastest
- `llama-3.1-8b` - Lightweight

**Features:**
- `groq` SDK (OpenAI-compatible API)
- Async client with standard message format
- Ultra-fast inference (150-200ms latency)
- Typically free or very low cost

**Environment Variable:**
```bash
export GROQ_API_KEY="gsk_..."
```

**Pricing (per 1K tokens):**
- All models: Free tier or $0.0

**Latency (p50):**
- llama-3.1-70b: 200ms
- mixtral-8x7b: 150ms

**Note:**
Groq uses the same message format as OpenAI, making it a drop-in replacement
for cost optimization while maintaining quality.

## Token Estimation

All providers use character-based token estimation:

```python
estimated_tokens = len(text) // 4  # ~4 characters per token
```

This is a reasonable approximation for English text but less accurate for:
- Code (tokens are typically shorter)
- Non-Latin scripts (variable length)
- Technical terminology (often multi-token)

For exact token counts, use provider-specific tokenizers:
- OpenAI: `tiktoken`
- Anthropic: `anthropic` library
- Google: `google.generativeai`
- Groq: `tiktoken`

## Error Handling

Each provider implements standard error handling:

**Rate Limit Errors:**
- Caught: `RateLimitError`
- Behavior: Exponential backoff retry (max 3 times)
- Delay: `2^(attempt-1)` seconds (1s, 2s, 4s)

**Other Errors:**
- Logged with structured format
- Re-raised as `RuntimeError` with original message
- Includes provider name and model in error context

## Streaming Response Format

Streaming yields text chunks as they become available:

```python
async for chunk in await provider.stream(messages, model):
    print(chunk, end="", flush=True)
```

All providers accumulate chunks for cost calculation at the end of the stream.

## Cost Tracking

Each provider tracks costs based on token usage:

```python
input_cost = (input_tokens / 1000) * cost_per_1k_input
output_cost = (output_tokens / 1000) * cost_per_1k_output
total_cost = input_cost + output_cost
```

Costs are logged via structured logging:

```python
{
    "level": "INFO",
    "event": "provider_call_success",
    "model": "gpt-4o",
    "tokens_input": 150,
    "tokens_output": 250,
    "cost": 0.00475
}
```

## API Key Configuration

All providers require API keys set as environment variables:

```bash
# .env file
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GOOGLE_AI_KEY="AIza..."
GROQ_API_KEY="gsk_..."
```

**Security Notes:**
- API keys are loaded in `__init__()` and validated
- Missing keys raise `RuntimeError` with clear message
- Keys are never logged or included in error messages
- Store `.env` files securely (add to `.gitignore`)

## Testing Providers

### Mock Testing

```python
from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
async def test_openai_provider():
    provider = OpenAIProvider()

    with patch('openai.AsyncOpenAI.chat.completions.create') as mock:
        mock.return_value = AsyncMock(
            choices=[AsyncMock(message=AsyncMock(content="Test"))]
        )

        result = await provider.complete(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o"
        )

        assert result == "Test"
```

### Integration Testing

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.integration
async def test_openai_real_call():
    """Test with real API call (requires valid API key)."""
    provider = OpenAIProvider()

    result = await provider.complete(
        messages=[{"role": "user", "content": "Say 'Hello'"}],
        model="gpt-4o-mini",
        max_tokens=10
    )

    assert len(result) > 0
    assert "hello" in result.lower()
```

## Performance Benchmarks

Typical latencies (p50, p95) for a 100-token prompt:

| Provider | Model | p50 | p95 |
|----------|-------|-----|-----|
| Groq | mixtral-8x7b | 150ms | 200ms |
| Groq | llama-3.1-70b | 200ms | 300ms |
| OpenAI | gpt-4o-mini | 400ms | 600ms |
| Google | gemini-2.0-flash | 450ms | 700ms |
| Anthropic | claude-haiku-4 | 500ms | 800ms |
| OpenAI | gpt-4o | 800ms | 1200ms |
| Google | gemini-2.0-pro | 700ms | 1000ms |
| Anthropic | claude-sonnet-4 | 600ms | 900ms |

## Troubleshooting

**"API key not set" error**
```
Solution: Set the appropriate environment variable
export OPENAI_API_KEY="sk-..."
```

**"Rate limit exceeded" error**
```
Solution: Reduce request rate or upgrade plan
The provider will automatically retry with exponential backoff
```

**"Unknown model" error**
```
Solution: Check model name against supported models list
for each provider
```

**Streaming hangs**
```
Solution: Ensure async event loop is running
Use asyncio.run() or within async context
```

**Threading errors with Google**
```
Solution: Google provider uses asyncio.to_thread()
Ensure Python 3.9+ (introduced in 3.9)
```

## Adding a New Provider

To add a new LLM provider:

1. Create `new_provider.py` in this directory
2. Inherit from `BaseLLMProvider`
3. Implement `complete()` and `stream()` methods
4. Add to `__init__.py` exports
5. Add to `llm_router.py` MODEL_REGISTRY
6. Add environment variable documentation

```python
# new_provider.py
from .base import BaseLLMProvider

class NewLLMProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__("new_provider")
        # Initialize client with API key

    async def complete(self, messages, model, temperature, max_tokens):
        # Implementation
        pass

    async def stream(self, messages, model, temperature, max_tokens):
        # Implementation
        pass
```

## References

- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Anthropic API Documentation](https://docs.anthropic.com)
- [Google Gemini API Documentation](https://ai.google.dev)
- [Groq API Documentation](https://console.groq.com/docs)

## License

Part of the Priya Global AI Engine service.
