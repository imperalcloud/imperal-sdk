# Changelog

## 0.4.0 (2026-04-08)

### Multi-Model LLM Abstraction
- **LLMProvider** — unified multi-model provider with config resolution, client pool, automatic failover, and per-call usage tracking
- **MessageAdapter** — Anthropic ↔ OpenAI message format translation (tool_use, tool_result, assistant messages)
- **BYOLLM** — users bring their own LLM API keys (stored encrypted in ext_store)
- **Per-purpose routing** — different models for routing/execution/navigate tasks
- **Per-extension override** — admin configures specific model per extension
- **Usage tracking** — every LLM call recorded to Redis (`imperal:llm_usage:{user_id}:{date}`)
- **Failover** — automatic retry with configurable fallback provider on 500/429/timeout
- **Config resolution** — ENV vars (default) + Config Store Redis (override, no restart)
- **Zero direct anthropic imports** — all LLM calls go through `get_llm_provider()`

### New exports
- `LLMConfig` — provider configuration dataclass
- `LLMUsage` — usage tracking dataclass
- `MessageAdapter` — format translation utility
- `get_llm_provider()` — singleton access to LLMProvider

### Action Writer
- Added `llm_provider` and `llm_model` fields to action records

## 0.3.0 (2026-04-08)

### ActionResult + Event Publishing
- **ActionResult** — universal return type for `@chat.function` with `.success()` / `.error()` factory methods
- **Event Publisher** — automatic kernel event publishing for write/destructive actions
- **Deterministic Truth Gate** — ActionResult.status as ground truth, zero LLM verification
- **Template Resolver** — `{{steps.N.data.*}}` variable passing for automation chains

## 0.2.0 (2026-04-03)

### ChatExtension + Hub Routing
- **ChatExtension** — single entry point with LLM routing for extensions
- **Hub LLM Routing** — embeddings optimize, LLM decides (multilingual)
- **Context Window Management** — 6 configurable guards
- **KAV** — Kernel Action Verification for write/destructive actions
- **2-Step Confirmation** — user approval for sensitive actions

## 0.1.0 (2026-04-02)

- Initial release: Extension, Context, Auth, Tool registration, SDK CLI stubs
