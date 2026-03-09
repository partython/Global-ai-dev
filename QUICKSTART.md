# Multi-LLM Router - Quick Start Guide

Get the LLM Router running in 5 minutes.

## 1. Install Dependencies

```bash
pip install openai anthropic google-generativeai groq pydantic
```

## 2. Set Environment Variables

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_AI_KEY="AIza..."
export GROQ_API_KEY="gsk_..."
```

## 3. Initialize the Router

```python
from services.ai_engine.llm_router import (
    LLMRouter,
    LLMRouterConfig,
    RoutingStrategy,
    LLMProvider,
)

# Create config
config = LLMRouterConfig(
    default_strategy=RoutingStrategy.BALANCED,
    providers_enabled=[
        LLMProvider.OPENAI,
        LLMProvider.ANTHROPIC,
    ],
    cost_budget_daily_usd=100.0,
)

# Initialize router
router = LLMRouter(config)
```

## 4. Make Your First Call

```python
import asyncio

async def main():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"}
    ]

    # Route to best model and call
    response = await router.call_with_fallback(
        messages=messages,
        task_type="response_generation",
        strategy=RoutingStrategy.BALANCED,
    )

    print(f"Response: {response}")

# Run
asyncio.run(main())
```

## 5. Check Costs

```python
# Get cost report
report = router.get_cost_report()

print(f"Daily cost: ${report['daily_cost']}")
print(f"Daily budget: ${report['daily_budget']}")
print(f"By provider: {report['daily_cost_by_provider']}")
```

## Common Patterns

### Cost-Optimized Calls
```python
response = await router.call_with_fallback(
    messages=messages,
    task_type="summarization",
    strategy=RoutingStrategy.COST_OPTIMIZED,
)
```

### Fast Responses
```python
response = await router.call_with_fallback(
    messages=messages,
    task_type="intent_classification",
    strategy=RoutingStrategy.LATENCY_OPTIMIZED,
)
```

### Streaming
```python
model = router.select_model("response_generation")
stream = await router.call_provider(
    model=model,
    messages=messages,
    stream=True,
)

async for chunk in stream:
    print(chunk, end="", flush=True)
```

### Direct Model Selection
```python
# Use specific model
model = router.MODEL_REGISTRY["gpt-4o"]

response = await router.call_provider(
    model=model,
    messages=messages,
)
```

## Configuration Options

```python
LLMRouterConfig(
    # Routing strategy (default: BALANCED)
    default_strategy=RoutingStrategy.COST_OPTIMIZED,

    # Enabled providers
    providers_enabled=[
        LLMProvider.OPENAI,
        LLMProvider.ANTHROPIC,
        LLMProvider.GROQ,
    ],

    # Daily budget in USD
    cost_budget_daily_usd=100.0,

    # Max latency threshold in ms
    latency_threshold_ms=5000,

    # Provider fallback order
    fallback_order=[
        LLMProvider.OPENAI,
        LLMProvider.ANTHROPIC,
        LLMProvider.GROQ,
        LLMProvider.GOOGLE,
    ],
)
```

## Model Selection Strategy

**COST_OPTIMIZED**
- Cheapest model
- Best for: batch processing, summarization
- Example: gpt-4o-mini ($0.00015 input)

**LATENCY_OPTIMIZED**
- Fastest model
- Best for: real-time chat, instant responses
- Example: mixtral-8x7b (150ms)

**QUALITY_OPTIMIZED**
- Premium models
- Best for: complex tasks, nuanced requests
- Example: gpt-4o ($0.005 input)

**BALANCED** (Default)
- Weighted: cost (40%) + latency (40%) + quality (20%)
- Best for: most use cases
- Example: gemini-2.0-flash or gpt-4o-mini

## Supported Task Types

- `intent_classification` - Detect user intent
- `response_generation` - Generate text
- `summarization` - Compress content
- `entity_extraction` - Find entities
- `sentiment_analysis` - Detect emotion
- `translation` - Translate text
- `vision` - Process images (Claude only)

## Provider Status

```python
status = router.get_provider_status()

for provider, info in status.items():
    print(f"{provider}: {info['state']} (available: {info['available']})")
```

## Error Handling

```python
try:
    response = await router.call_with_fallback(
        messages=messages,
        task_type="response_generation",
    )
except RuntimeError as e:
    print(f"All providers failed: {e}")
    # Handle failure gracefully
```

## Logging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Or specific logger
logger = logging.getLogger("llm_provider")
logger.setLevel(logging.DEBUG)
```

## Troubleshooting

**"API key not set"**
- Set environment variable: `export OPENAI_API_KEY="sk-..."`

**"Rate limit exceeded"**
- Reduce request frequency
- Router will auto-retry with exponential backoff

**"No providers available"**
- Check API keys are set
- Check provider status with `get_provider_status()`

**"Budget exceeded"**
- Daily limit hit
- Increase `cost_budget_daily_usd` or use cheaper models

## Next Steps

1. Read **LLMROUTER_USAGE_GUIDE.md** for detailed docs
2. Check **INTEGRATION_EXAMPLE.py** for 6 real-world patterns
3. Review **llm_providers/README.md** for provider details

## API Reference

### LLMRouter

```python
# Select best model
model = router.select_model(
    task_type: str,
    strategy: RoutingStrategy = None,
    requirements: Dict = None,
) -> LLMModel

# Call specific model
response = await router.call_provider(
    model: LLMModel,
    messages: List[Dict],
    temperature: float = 0.7,
    max_tokens: int = None,
    stream: bool = False,
) -> str | AsyncIterator[str]

# Call with automatic fallback
response = await router.call_with_fallback(
    messages: List[Dict],
    task_type: str,
    strategy: RoutingStrategy = None,
    temperature: float = 0.7,
    max_tokens: int = None,
) -> str

# Get cost report
report = router.get_cost_report() -> Dict

# Get provider status
status = router.get_provider_status() -> Dict
```

## File Structure

```
services/ai_engine/
├── llm_router.py              # Main router
└── llm_providers/
    ├── __init__.py
    ├── base.py                # Base class
    ├── openai_provider.py     # OpenAI
    ├── anthropic_provider.py  # Anthropic
    ├── google_provider.py     # Google
    └── groq_provider.py       # Groq
```

## Full Documentation

- **LLMROUTER_USAGE_GUIDE.md** - Complete reference
- **llm_providers/README.md** - Provider details
- **INTEGRATION_EXAMPLE.py** - Real-world examples
- **LLM_ROUTER_SUMMARY.md** - Implementation summary

---

Need help? Check the full documentation or example code above.
