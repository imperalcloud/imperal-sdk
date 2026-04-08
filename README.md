# Imperal SDK

SDK for building extensions on the Imperal Cloud ICNLI platform.

## Install

```bash
pip install imperal-sdk
```

## Quick Start

```python
from imperal_sdk import Extension, ChatExtension, ActionResult

ext = Extension("my-extension")
chat = ChatExtension(ext, "my_tool", "My extension", system_prompt="You help users.")

@chat.function("greet", description="Greet the user", params={"name": {"type": "string"}})
async def greet(ctx, name="World"):
    return ActionResult.success({"greeting": f"Hello, {name}!"}, summary=f"Greeted {name}")

if __name__ == "__main__":
    ext.run()
```

## Multi-Model LLM Support

The SDK supports multiple LLM providers. Extensions use `get_llm_provider()` for all LLM calls — the platform handles provider routing, failover, and usage tracking transparently.

**Supported providers:** Anthropic (Claude), OpenAI (GPT), Google (Gemini), any OpenAI-compatible API (Ollama, vLLM, LM Studio).

**BYOLLM:** Users can bring their own LLM API keys. Configure via Panel Settings → AI Provider.

**Per-purpose routing:** Different models for different tasks:
- `routing` — fast/cheap model for intent classification
- `execution` — accurate model for tool use in extensions
- `navigate` — conversational model for general chat

```python
from imperal_sdk import get_llm_provider

provider = get_llm_provider()
resp = await provider.create_message(
    messages=[{"role": "user", "content": "Hello"}],
    purpose="execution",        # routing | execution | navigate
    extension_id="my-ext",      # per-extension model override
    user_id="imp_u_xxx",        # BYOLLM lookup
)
```

## Key Components

- **Extension** — base class for all extensions
- **ChatExtension** — LLM-powered chat interface with function calling
- **ActionResult** — universal return type for chat functions (`.success()` / `.error()`)
- **Context** — execution context with user info, config, skeleton, storage
- **get_llm_provider()** — unified LLM access with multi-model routing and failover

## Configuration

Environment variables:

```bash
LLM_PROVIDER=anthropic          # anthropic | openai | openai_compatible | google
LLM_MODEL=claude-haiku-4-5-20251001
LLM_API_KEY=sk-ant-...
LLM_ROUTING_MODEL=...           # optional: model for routing
LLM_EXECUTION_MODEL=...         # optional: model for execution
LLM_NAVIGATE_MODEL=...          # optional: model for navigation
LLM_FALLBACK_PROVIDER=openai    # optional: failover provider
LLM_FALLBACK_MODEL=gpt-4.1-mini
LLM_FALLBACK_API_KEY=sk-...
```

## License

AGPL-3.0
