"""LLM Provider Abstraction — ICNLI Multi-Model Support.

Unified interface for LLM calls. Supports:
1. Anthropic (Claude) — default, zero-overhead native SDK
2. OpenAI-compatible API — OpenAI, Ollama, vLLM, llama.cpp, LM Studio, etc.
3. Google Gemini — via OpenAI-compatible API endpoint
4. Air-gapped mode — local models via openai_compatible + LLM_BASE_URL

Config resolution hierarchy (first wins):
  1. User BYOLLM  — ext_store __llm__ lookup, cached 60s
  2. Extension override  — Config Store imperal:config:llm → extensions.{app_id}
  3. Purpose override   — Config Store → purpose.{routing|execution|navigate}
  4. Global default     — Config Store → default, then ENV

ENV vars:
  LLM_PROVIDER=anthropic (default) | openai | openai_compatible | google
  LLM_API_KEY=...  (fallback: ANTHROPIC_API_KEY)
  LLM_MODEL=...
  LLM_BASE_URL=...
  LLM_ROUTING_MODEL=...
  LLM_EXECUTION_MODEL=...
  LLM_NAVIGATE_MODEL=...
  LLM_FALLBACK_PROVIDER=...
  LLM_FALLBACK_API_KEY=...
  LLM_FALLBACK_MODEL=...
  LLM_FALLBACK_BASE_URL=...
  IMPERAL_ENCRYPTION_KEY=... (fallback: IMAP_ENCRYPTION_KEY)
  REDIS_URL=...
  IMPERAL_GATEWAY_URL=...
  IMPERAL_SERVICE_TOKEN=...
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ENV config
# ---------------------------------------------------------------------------
_ENV_PROVIDER      = os.getenv("LLM_PROVIDER", "anthropic")
_ENV_API_KEY       = os.getenv("LLM_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
_ENV_MODEL         = os.getenv("LLM_MODEL", "")
_ENV_BASE_URL      = os.getenv("LLM_BASE_URL", "")
_ENV_ROUTING_MODEL = os.getenv("LLM_ROUTING_MODEL", "")
_ENV_EXEC_MODEL    = os.getenv("LLM_EXECUTION_MODEL", "")
_ENV_NAV_MODEL     = os.getenv("LLM_NAVIGATE_MODEL", "")

_ENV_FB_PROVIDER   = os.getenv("LLM_FALLBACK_PROVIDER", "")
_ENV_FB_API_KEY    = os.getenv("LLM_FALLBACK_API_KEY", "")
_ENV_FB_MODEL      = os.getenv("LLM_FALLBACK_MODEL", "")
_ENV_FB_BASE_URL   = os.getenv("LLM_FALLBACK_BASE_URL", "")

_REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_GATEWAY_URL       = os.getenv("IMPERAL_GATEWAY_URL", "")
_SERVICE_TOKEN     = os.getenv("IMPERAL_SERVICE_TOKEN", "")

# Default models per provider
_PROVIDER_DEFAULTS: dict[str, dict] = {
    "anthropic": {
        "model": "claude-haiku-4-5-20251001",
        "routing_model": "claude-haiku-4-5-20251001",
    },
    "openai": {
        "model": "gpt-4o-mini",
        "routing_model": "gpt-4o-mini",
    },
    "openai_compatible": {
        "model": "llama3.1:8b",
        "routing_model": "llama3.1:8b",
    },
    "google": {
        "model": "gemini-2.0-flash",
        "routing_model": "gemini-2.0-flash",
    },
}

_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Config Store cache TTL (seconds)
_CONFIG_CACHE_TTL = 60
# BYOLLM cache TTL (seconds)
_BYOLLM_CACHE_TTL = 60


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    """Resolved LLM configuration for a single call."""
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    is_byollm: bool = False

    @property
    def client_key(self) -> str:
        """Stable key for client pool hashing."""
        key_hash = hashlib.sha256(self.api_key.encode()).hexdigest()[:12]
        return f"{self.provider}:{self.base_url or 'default'}:{key_hash}"


@dataclass
class LLMUsage:
    """Usage record for a single LLM call."""
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    is_byollm: bool = False
    is_failover: bool = False
    purpose: str = ""
    extension_id: str = ""
    user_id: str = ""
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _get_fernet():
    """Return a Fernet instance or None if key is unavailable."""
    key = os.getenv("IMPERAL_ENCRYPTION_KEY", "") or os.getenv("IMAP_ENCRYPTION_KEY", "")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        log.warning(f"LLMProvider: Fernet init failed: {e}")
        return None


def _decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string. Returns plaintext or original on error."""
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext  # already plaintext or bad key


def _encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string with Fernet. Returns ciphertext or original on error."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext
    try:
        return f.encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext


# ---------------------------------------------------------------------------
# LLMProvider — main class
# ---------------------------------------------------------------------------

class LLMProvider:
    """Multi-model LLM provider with config resolution, client pool, failover, usage tracking."""

    def __init__(self):
        # Legacy compat: expose provider_type / model / routing_model as attributes
        self.provider_type: str = _ENV_PROVIDER
        defaults = _PROVIDER_DEFAULTS.get(self.provider_type, _PROVIDER_DEFAULTS["anthropic"])
        self.model: str = _ENV_MODEL or defaults["model"]
        self.routing_model: str = _ENV_ROUTING_MODEL or defaults["routing_model"]

        # Client pool: client_key -> client instance
        self._client_pool: dict[str, Any] = {}

        # Config Store cache: { "config": {...}, "ts": float }
        self._config_cache: dict[str, Any] | None = None
        self._config_cache_ts: float = 0.0

        # BYOLLM cache: user_id -> { "config": LLMConfig|None, "ts": float }
        self._byollm_cache: dict[str, dict] = {}

        # Background Redis pubsub listener handle
        self._listener_task: asyncio.Task | None = None
        self._listener_started: bool = False

        # Per-action call log for LLM step tracking
        self._call_log: list[dict] = []

    # ------------------------------------------------------------------
    # Call log -- per-action LLM step tracking
    # ------------------------------------------------------------------

    def reset_call_log(self):
        self._call_log = []

    def get_call_log(self) -> list:
        return list(self._call_log)

    # ------------------------------------------------------------------
    # Public API — preserved for all call sites
    # ------------------------------------------------------------------

    async def create_message(
        self,
        messages: list,
        system: str = "",
        max_tokens: int = 1024,
        model: Optional[str] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[dict] = None,
        temperature: float = 0.0,
        # New optional context params (ignored by old callers)
        purpose: str = "",
        extension_id: str = "",
        user_id: str = "",
    ) -> Any:
        """Create a chat completion.

        Returns native Anthropic response object (or AnthropicCompat for non-Anthropic).
        Explicit `model` param overrides resolved model (backwards compat).
        """
        start_ms = int(time.monotonic() * 1000)

        # Resolve config
        cfg = await self._resolve(purpose=purpose, extension_id=extension_id, user_id=user_id)

        # Explicit model override (legacy callers pass model= directly)
        if model:
            cfg = LLMConfig(
                provider=cfg.provider,
                model=model,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                is_byollm=cfg.is_byollm,
            )

        # Ensure background invalidation listener is running
        self._ensure_listener()

        # Log resolved config for visibility
        _byollm_tag = " [BYOLLM]" if cfg.is_byollm else ""
        _purpose_tag = f" purpose={purpose}" if purpose else ""
        _ext_tag = f" ext={extension_id}" if extension_id else ""
        log.info(f"LLM call: {cfg.provider}/{cfg.model}{_purpose_tag}{_ext_tag}{_byollm_tag}")

        # Track last call config for action_writer (executor reads this)
        self._last_call_info = {"provider": cfg.provider, "model": cfg.model}

        is_failover = False
        import time as _t; _call_start = _t.time()
        try:
            resp = await self._call(cfg, messages, system, max_tokens, tools, tool_choice, temperature)
        except Exception as primary_err:
            log.warning(f"LLMProvider primary call failed ({cfg.provider}/{cfg.model}): {primary_err}, trying failover")
            failover_cfg = self._resolve_failover(cfg)
            if failover_cfg is None:
                raise
            try:
                resp = await self._call(failover_cfg, messages, system, max_tokens, tools, tool_choice, temperature)
                cfg = failover_cfg
                is_failover = True
            except Exception as fb_err:
                log.error(f"LLMProvider failover also failed ({failover_cfg.provider}/{failover_cfg.model}): {fb_err}")
                raise fb_err

        latency_ms = int(time.monotonic() * 1000) - start_ms

        # Fire-and-forget usage tracking
        if user_id:
            usage = LLMUsage(
                provider=cfg.provider,
                model=cfg.model,
                input_tokens=getattr(getattr(resp, "usage", None), "input_tokens", 0) or 0,
                output_tokens=getattr(getattr(resp, "usage", None), "output_tokens", 0) or 0,
                is_byollm=cfg.is_byollm,
                is_failover=is_failover,
                purpose=purpose,
                extension_id=extension_id,
                user_id=user_id,
                latency_ms=latency_ms,
            )
            asyncio.ensure_future(self._track_usage(usage))

        # Append to per-action call log
        _call_ms = int((_t.time() - _call_start) * 1000)
        _usage = getattr(resp, "usage", None)
        self._call_log.append({"purpose": purpose or "default", "provider": cfg.provider, "model": cfg.model, "input_tokens": getattr(_usage, "input_tokens", 0) if _usage else 0, "output_tokens": getattr(_usage, "output_tokens", 0) if _usage else 0, "latency_ms": _call_ms, "is_failover": is_failover})

        return resp

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    async def _resolve(self, purpose: str = "", extension_id: str = "", user_id: str = "") -> LLMConfig:
        """Resolve LLM config. Hierarchy: BYOLLM → ext override → purpose override → global default."""

        # 1. User BYOLLM
        if user_id:
            byollm = await self._resolve_byollm(user_id)
            if byollm is not None:
                return byollm

        # Load Config Store (cached)
        config_store = await self._load_config_store()

        # 2. Extension override
        if extension_id and config_store:
            ext_cfg = config_store.get("extensions", {}).get(extension_id)
            if ext_cfg:
                return self._config_from_store(ext_cfg)

        # 3. Purpose override
        if purpose and config_store:
            purpose_cfg = config_store.get("purpose", {}).get(purpose)
            if purpose_cfg:
                return self._config_from_store(purpose_cfg)

        # 3b. ENV purpose override (LLM_ROUTING_MODEL etc.)
        if purpose:
            env_purpose_model = {
                "routing": _ENV_ROUTING_MODEL,
                "execution": _ENV_EXEC_MODEL,
                "navigate": _ENV_NAV_MODEL,
            }.get(purpose, "")
            if env_purpose_model:
                return LLMConfig(
                    provider=_ENV_PROVIDER,
                    model=env_purpose_model,
                    api_key=_ENV_API_KEY,
                    base_url=_ENV_BASE_URL,
                )

        # 4. Global default from Config Store
        if config_store:
            default_cfg = config_store.get("default")
            if default_cfg:
                return self._config_from_store(default_cfg)

        # 5. ENV fallback
        return self._env_default_config()

    def _env_default_config(self) -> LLMConfig:
        """Build LLMConfig from ENV vars."""
        provider = _ENV_PROVIDER
        defaults = _PROVIDER_DEFAULTS.get(provider, _PROVIDER_DEFAULTS["anthropic"])
        model = _ENV_MODEL or defaults["model"]
        base_url = _ENV_BASE_URL
        if provider == "google" and not base_url:
            base_url = _GOOGLE_BASE_URL
        return LLMConfig(
            provider=provider,
            model=model,
            api_key=_ENV_API_KEY,
            base_url=base_url,
        )

    def _config_from_store(self, cfg: dict) -> LLMConfig:
        """Build LLMConfig from a Config Store dict entry."""
        provider = cfg.get("provider", _ENV_PROVIDER)
        defaults = _PROVIDER_DEFAULTS.get(provider, _PROVIDER_DEFAULTS["anthropic"])
        model = cfg.get("model", "") or defaults["model"]
        api_key = _decrypt(cfg.get("api_key", "")) or _ENV_API_KEY
        base_url = cfg.get("base_url", "")
        if provider == "google" and not base_url:
            base_url = _GOOGLE_BASE_URL
        return LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

    async def _resolve_byollm(self, user_id: str) -> LLMConfig | None:
        """Lookup user's BYOLLM config from ext_store. Cached 60s."""
        now = time.monotonic()
        cached = self._byollm_cache.get(user_id)
        if cached and (now - cached["ts"]) < _BYOLLM_CACHE_TTL:
            return cached["config"]

        config = None
        try:
            config = await self._fetch_byollm(user_id)
        except Exception as e:
            log.debug(f"LLMProvider: BYOLLM fetch failed for {user_id}: {e}")

        self._byollm_cache[user_id] = {"config": config, "ts": now}
        return config

    async def _fetch_byollm(self, user_id: str) -> LLMConfig | None:
        """Fetch BYOLLM config from Auth Gateway ext_store."""
        if not _GATEWAY_URL or not _SERVICE_TOKEN:
            return None

        import httpx
        url = f"{_GATEWAY_URL.rstrip('/')}/v1/internal/store/__llm__/query"
        payload = {
            "where": {"user_id": user_id},
            "limit": 1,
            "extension_id": "__system__",
            "user_id": user_id,
            "tenant_id": "",
        }
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"X-Service-Token": _SERVICE_TOKEN},
            )
            if resp.status_code != 200:
                return None
            results = resp.json()
            if not results:
                return None
            doc = results[0]
            data = doc.get("data", {})

        provider = data.get("provider", "")
        if not provider:
            return None
        model = data.get("model", "") or _PROVIDER_DEFAULTS.get(provider, {}).get("model", "")
        api_key = _decrypt(data.get("api_key", ""))
        base_url = data.get("base_url", "")
        if provider == "google" and not base_url:
            base_url = _GOOGLE_BASE_URL

        return LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            is_byollm=True,
        )

    async def _load_config_store(self) -> dict | None:
        """Load LLM config from Redis Config Store. Cached 60s."""
        now = time.monotonic()
        if self._config_cache is not None and (now - self._config_cache_ts) < _CONFIG_CACHE_TTL:
            return self._config_cache

        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(_REDIS_URL, decode_responses=True)
            raw = await r.get("imperal:config:llm")
            await r.aclose()
            if raw:
                self._config_cache = json.loads(raw)
                self._config_cache_ts = now
                return self._config_cache
        except Exception as e:
            log.debug(f"LLMProvider: Config Store load failed: {e}")

        return None

    def _resolve_failover(self, primary: LLMConfig) -> LLMConfig | None:
        """Return failover config. BYOLLM fails → platform default. System fails → ENV fallback."""
        if primary.is_byollm:
            # User BYOLLM failed — fall back to platform default (no BYOLLM flag)
            return self._env_default_config()

        # System config failed — try ENV fallback provider
        if _ENV_FB_PROVIDER:
            fb_base = _ENV_FB_BASE_URL
            if _ENV_FB_PROVIDER == "google" and not fb_base:
                fb_base = _GOOGLE_BASE_URL
            fb_defaults = _PROVIDER_DEFAULTS.get(_ENV_FB_PROVIDER, _PROVIDER_DEFAULTS["anthropic"])
            return LLMConfig(
                provider=_ENV_FB_PROVIDER,
                model=_ENV_FB_MODEL or fb_defaults["model"],
                api_key=_ENV_FB_API_KEY or _ENV_API_KEY,
                base_url=fb_base,
            )

        return None  # No failover configured

    # ------------------------------------------------------------------
    # Provider dispatch
    # ------------------------------------------------------------------

    async def _call(self, cfg: LLMConfig, messages, system, max_tokens, tools, tool_choice, temperature) -> Any:
        """Dispatch to the correct provider backend."""
        if cfg.provider == "anthropic":
            return await self._call_anthropic(cfg, messages, system, max_tokens, tools, tool_choice, temperature)
        else:
            return await self._call_openai(cfg, messages, system, max_tokens, tools, tool_choice, temperature)

    async def _call_anthropic(self, cfg: LLMConfig, messages, system, max_tokens, tools, tool_choice, temperature) -> Any:
        """Native Anthropic SDK call — zero overhead."""
        client = self._get_client(cfg)
        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if temperature > 0:
            kwargs["temperature"] = temperature
        return await client.messages.create(**kwargs)

    async def _call_openai(self, cfg: LLMConfig, messages, system, max_tokens, tools, tool_choice, temperature) -> Any:
        """OpenAI-compatible call via MessageAdapter."""
        from imperal_sdk.runtime.message_adapter import MessageAdapter

        client = self._get_client(cfg)
        oai_messages = MessageAdapter.to_openai_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = MessageAdapter.to_openai_tools(tools)
        if tool_choice:
            oai_tc = MessageAdapter.to_openai_tool_choice(tool_choice)
            if oai_tc is not None:
                kwargs["tool_choice"] = oai_tc

        resp = await client.chat.completions.create(**kwargs)
        return MessageAdapter.from_openai_response(resp, cfg.model)

    # ------------------------------------------------------------------
    # Client pool
    # ------------------------------------------------------------------

    def _get_client(self, cfg: LLMConfig) -> Any:
        """Get or create a client from the pool. Keyed by provider+base_url+api_key_hash."""
        key = cfg.client_key
        if key in self._client_pool:
            return self._client_pool[key]

        client = self._create_client(cfg)
        self._client_pool[key] = client
        return client

    def _create_client(self, cfg: LLMConfig) -> Any:
        """Create a new client for the given config."""
        if cfg.provider == "anthropic":
            import anthropic
            api_key = cfg.api_key or os.getenv("ANTHROPIC_API_KEY", "")
            return anthropic.AsyncAnthropic(api_key=api_key)

        # OpenAI / openai_compatible / google — all use AsyncOpenAI
        from openai import AsyncOpenAI
        base_url = cfg.base_url
        if cfg.provider == "google" and not base_url:
            base_url = _GOOGLE_BASE_URL
        elif cfg.provider in ("openai",) and not base_url:
            base_url = None  # Use OpenAI default
        elif cfg.provider == "openai_compatible" and not base_url:
            base_url = "http://localhost:11434/v1"

        kwargs: dict[str, Any] = {
            "api_key": cfg.api_key or "not-needed",
        }
        if base_url:
            kwargs["base_url"] = base_url
        return AsyncOpenAI(**kwargs)

    # ------------------------------------------------------------------
    # Usage tracking (fire-and-forget)
    # ------------------------------------------------------------------

    async def _track_usage(self, usage: LLMUsage) -> None:
        """Write usage metrics to Redis. Fire-and-forget — never raises."""
        try:
            import redis.asyncio as aioredis
            from datetime import date

            r = aioredis.from_url(_REDIS_URL, decode_responses=True)
            day = date.today().isoformat()
            key = f"imperal:llm_usage:{usage.user_id}:{day}"

            pipe = r.pipeline()
            pipe.hincrby(key, "input_tokens",  usage.input_tokens)
            pipe.hincrby(key, "output_tokens", usage.output_tokens)
            pipe.hincrby(key, "calls", 1)
            if usage.purpose:
                pipe.hincrby(key, f"calls:{usage.purpose}", 1)
            if usage.model:
                pipe.hincrby(key, f"tokens:{usage.model}", usage.input_tokens + usage.output_tokens)
            if usage.is_byollm:
                pipe.hincrby(key, "byollm_calls", 1)
            if usage.is_failover:
                pipe.hincrby(key, "failover_calls", 1)
            pipe.hincrby(key, "total_latency_ms", usage.latency_ms)
            pipe.expire(key, 90 * 86400)  # 90-day retention
            await pipe.execute()
            await r.aclose()
        except Exception as e:
            log.debug(f"LLMProvider: usage tracking failed: {e}")

    # ------------------------------------------------------------------
    # Background invalidation listener
    # ------------------------------------------------------------------

    def _ensure_listener(self) -> None:
        """Start background Redis pubsub listener if not already running."""
        if self._listener_started:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._listener_task = loop.create_task(self._invalidation_listener())
                self._listener_started = True
        except RuntimeError:
            pass  # No event loop yet

    async def _invalidation_listener(self) -> None:
        """Subscribe to imperal:config:invalidate:* and flush BYOLLM cache entries."""
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(_REDIS_URL, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.psubscribe("imperal:config:invalidate:*")
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                channel: str = message.get("channel", "")
                # channel format: imperal:config:invalidate:{user_id}
                parts = channel.rsplit(":", 1)
                if len(parts) == 2:
                    user_id = parts[1]
                    if user_id in self._byollm_cache:
                        del self._byollm_cache[user_id]
                        log.debug(f"LLMProvider: BYOLLM cache invalidated for {user_id}")
                # Also flush Config Store cache on wildcard system invalidation
                if "config:invalidate:__system__" in channel:
                    self._config_cache = None
                    self._config_cache_ts = 0.0
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug(f"LLMProvider: invalidation listener error: {e}")
            self._listener_started = False  # Allow restart


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_provider_instance: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Get singleton LLM provider instance. API unchanged for all call sites."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = LLMProvider()
        log.info(
            f"LLM Provider initialized: {_provider_instance.provider_type}, "
            f"model={_provider_instance.model}"
        )
    return _provider_instance


def get_routing_model() -> str:
    """Get the model name to use for routing/classification."""
    return get_llm_provider().routing_model


def is_air_gapped() -> bool:
    """Check if running in air-gapped mode (local models, no external API calls)."""
    return _ENV_PROVIDER == "openai_compatible"
