# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any, Callable

# ToolDef is the canonical tool shape — its source of truth is tool_def.py.
# Re-exported here so legacy ``from imperal_sdk.extension import ToolDef``
# imports (SDK internals, extensions, tests) continue to work unchanged.
from imperal_sdk.tool_def import ToolDef  # noqa: F401 re-export

@dataclass
class SignalDef:
    name: str
    func: Callable

@dataclass
class ScheduleDef:
    name: str
    func: Callable
    cron: str

@dataclass
class LifecycleHook:
    name: str
    func: Callable
    version: str = ""  # only for on_upgrade

@dataclass
class HealthCheckDef:
    func: Callable

@dataclass
class WebhookDef:
    path: str
    func: Callable
    method: str = "POST"
    secret_header: str = ""

@dataclass
class EventHandlerDef:
    event_type: str
    func: Callable

@dataclass
class ExposedMethod:
    name: str
    func: Callable
    action_type: str = "read"

@dataclass
class TrayDef:
    """System tray item — icon + badge + optional dropdown panel in the OS top bar."""
    tray_id: str
    func: Callable
    icon: str = "Circle"
    tooltip: str = ""

class Extension:
    """Imperal Cloud Extension.

    Supports two authoring surfaces:

    * **v1 (instance-based, legacy imperative)** — ``ext = Extension("app"); @ext.tool("name")``.
      The decorator is an instance method; tools land in ``self._tools`` on
      that particular object. Backward-compatible, still exercised in tests.
    * **v2 (class-based, Webbee Single Voice)** — ``class MyExt(Extension): @ext.tool(...)``
      with ``ext`` imported from ``imperal_sdk``. The class-level decorator
      stamps ``_tool_meta`` on each method; :meth:`__init_subclass__` collects
      them into ``cls._tools_registry`` and runs the companion-tool
      (I-STATUS-TOOL-MUST-EXIST) check. Raises at class-def time on contract
      violations so the kernel never attempts to load a malformed extension.
    """

    # v2 class-level registry, populated by __init_subclass__. Each concrete
    # subclass gets its own dict (shadowed at class-def time) — never shared.
    _tools_registry: dict[str, Callable] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Collect v2 ``@ext.tool``-decorated methods into ``cls._tools_registry``.

        Runs once per subclass at class-definition time. Discovery is based on
        the ``_tool_meta`` attribute stamped by :func:`imperal_sdk.decorators.ext.tool`.
        After collection, runs the status_tool existence check
        (I-STATUS-TOOL-MUST-EXIST) so malformed extensions fail loud during
        module import rather than at first-dispatch.

        Also rejects ``_system_prompt`` class attribute at class-def time
        (I-LOADER-REJECT-SYSTEM-PROMPT) — ChatExtension and per-extension
        system prompts were removed in v2.0.0; Webbee Narrator renders all
        user-facing prose kernel-side.
        """
        super().__init_subclass__(**kwargs)
        # v2.0 hard reject: ``_system_prompt`` class attribute. Must run BEFORE
        # tool-registry wiring so the loader gets a precise error even for
        # otherwise-malformed extensions.
        if "_system_prompt" in cls.__dict__:
            raise TypeError(
                f"Extension {cls.__name__} defines _system_prompt class attribute. "
                "ChatExtension and _system_prompt removed in SDK v2.0.0. "
                "Extensions are pure tool providers; Webbee Narrator writes all user-facing prose. "
                "See migration guide: docs/dev/sdk-v2-migration.md"
            )
        registry: dict[str, Callable] = {}
        # Walk the subclass namespace only. We deliberately skip inherited
        # members so each subclass declares its own tools explicitly; mixing
        # tool definitions across MRO is out-of-scope for v2.
        for attr_name, attr_val in list(cls.__dict__.items()):
            if callable(attr_val) and hasattr(attr_val, "_tool_meta"):
                registry[attr_name] = attr_val
        cls._tools_registry = registry
        cls._validate_status_tool_pairs()

    @classmethod
    def _validate_status_tool_pairs(cls) -> None:
        """Enforce I-STATUS-TOOL-MUST-EXIST on ``cls._tools_registry``.

        For every tool marked ``long_running=True``, verify the declared
        ``status_tool`` name is itself a registered tool on the same class.
        Raises :class:`ValueError` at class-def / instantiation time.
        """
        registry = getattr(cls, "_tools_registry", {}) or {}
        for name, tool_fn in registry.items():
            meta = getattr(tool_fn, "_tool_meta", {}) or {}
            if not meta.get("long_running"):
                continue
            st_name = meta.get("status_tool")
            if st_name and st_name not in registry:
                raise ValueError(
                    f"Tool {cls.__name__}.{name} declares status_tool="
                    f"{st_name!r} but no such tool exists in this extension. "
                    f"Declare a companion tool with that name that returns "
                    f"TaskStatus. Available tools: {sorted(registry.keys())}. "
                    "(Invariant I-STATUS-TOOL-MUST-EXIST)"
                )

    def __init__(
        self,
        app_id: str | None = None,
        version: str = "0.1.0",
        capabilities: list[str] | None = None,
        migrations_dir: str | None = None,
        config_defaults: dict | None = None,
    ):
        # Defense-in-depth: re-run the status_tool pair check on instantiation
        # in case the registry was mutated post class-def (rare, but covered
        # by test_long_running_status_tool_must_exist_in_extension which
        # invokes BrokenExt() inside its pytest.raises block).
        type(self)._validate_status_tool_pairs()

        # v2 class-based subclasses may omit app_id at construction time and
        # rely on a class-level attribute; preserve v1 positional shape by
        # defaulting to the class name.
        if app_id is None:
            app_id = getattr(type(self), "app_id", None) or type(self).__name__
        self.app_id = app_id
        self.version = version
        self.capabilities = capabilities or []
        self.migrations_dir = migrations_dir
        self._tools: dict[str, ToolDef] = {}
        self._signals: dict[str, SignalDef] = {}
        self._schedules: dict[str, ScheduleDef] = {}
        self.config_defaults = config_defaults or {}
        self._lifecycle: dict[str, LifecycleHook] = {}
        self._health_check: HealthCheckDef | None = None
        self._webhooks: dict[str, WebhookDef] = {}
        self._event_handlers: list[EventHandlerDef] = []
        self._exposed: dict[str, ExposedMethod] = {}
        self._panels: dict[str, dict] = {}
        self._tray: dict[str, "TrayDef"] = {}
        # v1.6.0 ctx.cache — per-extension Pydantic model registry. Scoped to
        # this Extension instance: the same name in different extensions
        # refers to different classes. Invariant:
        # I-CACHE-MODEL-ON-EXTENSION-INSTANCE.
        self._cache_models: dict[str, type] = {}

    def __setattr__(self, name: str, value: Any) -> None:
        """Guard against instance-level ``_system_prompt`` assignment.

        Catches subclasses that set ``self._system_prompt = ...`` inside their
        own ``__init__`` (after ``super().__init__()``) and any external
        mutation. The class-def form is rejected in :meth:`__init_subclass__`.
        Invariant I-LOADER-REJECT-SYSTEM-PROMPT.
        """
        if name == "_system_prompt":
            raise TypeError(
                f"Extension {type(self).__name__} sets _system_prompt instance attribute. "
                "ChatExtension and _system_prompt removed in SDK v2.0.0."
            )
        super().__setattr__(name, value)

    def tool(self, name: str, scopes: list[str] | None = None, description: str = ""):
        """Register a tool that the AI assistant can call."""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = ToolDef(
                name=name,
                func=func,
                scopes=scopes or [],
                description=description or func.__doc__ or "",
            )
            return func
        return decorator

    def signal(self, name: str):
        """Register a signal handler for platform events."""
        def decorator(func: Callable) -> Callable:
            self._signals[name] = SignalDef(name=name, func=func)
            return func
        return decorator

    def schedule(self, name: str, cron: str):
        """Register a scheduled task."""
        def decorator(func: Callable) -> Callable:
            self._schedules[name] = ScheduleDef(name=name, func=func, cron=cron)
            return func
        return decorator

    def skeleton(
        self,
        section_name: str,
        *,
        alert: bool = False,
        ttl: int = 300,
        description: str = "",
    ):
        """Register a skeleton refresh tool by section name (recommended DX).

        Sugar over :meth:`tool` that applies the platform's naming convention:

        - The decorated function is registered as ``skeleton_refresh_<section_name>``.
        - When ``alert=True``, a paired ``skeleton_alert_<section_name>`` tool is
          also expected (register it separately with ``@ext.tool`` OR the kernel
          will simply skip change alerts if absent).
        - ``ttl`` is a hint to platform operators — the authoritative TTL lives
          in the Registry row (or the kernel's auto-derive default of 300s).

        The kernel's skeleton workflow discovers this section automatically via
        the ``skeleton_refresh_<X>`` naming convention — no Registry migration
        required. See `imperal_sdk/docs/skeleton.md` §"Skeleton Refresh Tools"
        for the end-to-end contract and invariants
        (I-SKEL-AUTO-DERIVE-1, I-SKEL-SUMMARY-VALUES-1, I-SKEL-LIVE-INVALIDATE,
        I-PURGE-SKELETON-SCOPE).

        Return contract: refresh function MUST return ``{"response": <dict>}``
        where the dict surfaces scalar fields (counts, flags, short strings) at
        the top level so the intent classifier can read them directly from the
        user's envelope. Idempotent — safe to run on every tick.

        Example::

            @ext.skeleton("monitors", alert=True, ttl=300)
            async def refresh_monitors(ctx) -> dict:
                items = await ctx.store.query("wt_monitors", where={"owner_id": ctx.user.id})
                critical = sum(1 for m in items.data if m.data.get("status") == "critical")
                return {"response": {
                    "total":    len(items.data),
                    "critical": critical,
                    "warning":  sum(1 for m in items.data if m.data.get("status") == "warning"),
                    "ok":       sum(1 for m in items.data if m.data.get("status") == "ok"),
                }}
        """
        if not section_name or not isinstance(section_name, str):
            raise ValueError("skeleton: section_name must be a non-empty string")
        # Keep section_name flat (no colons, wildcards, or separators) — the
        # kernel's purge helper rejects these characters defence-in-depth, and
        # they would break the Redis key path ``imperal:skeleton:{app}:{user}:{section}``.
        if any(c in section_name for c in "*?[]:/"):
            raise ValueError(
                f"skeleton: section_name {section_name!r} must not contain "
                "wildcard/separator characters (* ? [ ] : /)"
            )
        tool_name = f"skeleton_refresh_{section_name}"
        desc = description or f"Skeleton refresh: {section_name}"

        def decorator(func: Callable) -> Callable:
            self._tools[tool_name] = ToolDef(
                name=tool_name,
                func=func,
                scopes=[],  # skeleton refresh runs with system scopes ["*"]
                description=desc,
            )
            # Stash convention metadata for the validator + tooling.
            # Private attribute; extensions MUST NOT read this directly.
            ttl_val = int(ttl) if ttl else 300
            self._tools[tool_name]._skeleton = {  # type: ignore[attr-defined]
                "section_name": section_name,
                "alert_on_change": bool(alert),
                "ttl": ttl_val,
            }
            return func
        return decorator

    def cache_model(self, name: str):
        """Register a Pydantic model as a ``ctx.cache`` value shape.

        The model name is scoped to this :class:`Extension` instance — the
        same name in different extensions refers to different classes.
        ``ctx.cache.set(key, value, ttl_seconds=60)`` will reverse-lookup the
        class of ``value`` in this registry and refuse to persist anything
        whose type is not registered.

        Constraints:

        - ``cls`` must subclass ``pydantic.BaseModel`` — raises ``TypeError``.
        - ``name`` must be unique within the extension — duplicates raise
          ``ValueError``.

        Example::

            from pydantic import BaseModel

            class InboxSummary(BaseModel):
                unread: int
                latest_subject: str

            @ext.cache_model("inbox_summary")
            class _InboxSummary(InboxSummary):
                pass

        Invariant: I-CACHE-MODEL-ON-EXTENSION-INSTANCE.
        """
        from pydantic import BaseModel

        def decorator(cls):
            if not isinstance(cls, type) or not issubclass(cls, BaseModel):
                raise TypeError(
                    f"@{self.app_id}.cache_model: {getattr(cls, '__name__', cls)!r}"
                    " must be a Pydantic BaseModel subclass"
                )
            if name in self._cache_models:
                raise ValueError(
                    f"cache model {name!r} already registered for {self.app_id!r}"
                )
            self._cache_models[name] = cls
            return cls

        return decorator

    def _resolve_cache_model_name(self, cls) -> str | None:
        """Reverse-lookup the registered name for a Pydantic class.

        Returns the registered name if ``cls`` was registered via
        :meth:`cache_model`, else ``None``. Used by
        :class:`imperal_sdk.cache.CacheClient` to compute the Redis key
        prefix before a set/get round-trip.
        """
        for model_name, registered_cls in self._cache_models.items():
            if registered_cls is cls:
                return model_name
        return None

    def on_install(self, func: Callable) -> Callable:
        """Register install hook. Called once when user installs extension."""
        self._lifecycle["on_install"] = LifecycleHook(name="on_install", func=func)
        return func

    def on_upgrade(self, version: str):
        """Register version-specific upgrade hook."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle[f"on_upgrade:{version}"] = LifecycleHook(
                name="on_upgrade", func=func, version=version,
            )
            return func
        return decorator

    def on_uninstall(self, func: Callable) -> Callable:
        """Register uninstall hook. Clean up user data."""
        self._lifecycle["on_uninstall"] = LifecycleHook(name="on_uninstall", func=func)
        return func

    def on_enable(self, func: Callable) -> Callable:
        """Register enable hook. Called when admin enables for user/tenant."""
        self._lifecycle["on_enable"] = LifecycleHook(name="on_enable", func=func)
        return func

    def on_disable(self, func: Callable) -> Callable:
        """Register disable hook."""
        self._lifecycle["on_disable"] = LifecycleHook(name="on_disable", func=func)
        return func

    def health_check(self, func: Callable) -> Callable:
        """Register health check. Called every 60s by kernel."""
        self._health_check = HealthCheckDef(func=func)
        return func

    def webhook(self, path: str, method: str = "POST", secret_header: str = ""):
        """Register webhook endpoint. Routes POST /v1/ext/{app_id}/webhook/{path}.

        Also registers __webhook__{path} as a ToolDef so DirectCallWorkflow
        can dispatch it without LLM routing. The handler receives:
            ctx       — minimal context (user_id="__webhook__")
            headers   — dict of request headers (hop-by-hop stripped)
            body      — raw request body as string
            query_params — dict of URL query parameters

        Secret verification must be done inside the handler using secret_header.
        """
        def decorator(func: Callable) -> Callable:
            self._webhooks[path] = WebhookDef(
                path=path, func=func, method=method, secret_header=secret_header,
            )
            # Register as a ToolDef so DirectCallWorkflow can dispatch via /call
            tool_name = f"__webhook__{path}"
            self._tools[tool_name] = ToolDef(
                name=tool_name,
                func=func,
                description=f"Webhook handler for path: {path}",
            )
            return func
        return decorator

    def on_event(self, event_type: str):
        """Subscribe to a platform event."""
        def decorator(func: Callable) -> Callable:
            self._event_handlers.append(EventHandlerDef(event_type=event_type, func=func))
            return func
        return decorator

    def expose(self, name: str, action_type: str = "read"):
        """Expose a method for inter-extension calls via ctx.extensions.call()."""
        def decorator(func: Callable) -> Callable:
            self._exposed[name] = ExposedMethod(name=name, func=func, action_type=action_type)
            return func
        return decorator

    def tray(self, tray_id: str, icon: str = "Circle", tooltip: str = ""):
        """Declare a system tray item in the OS top bar.

        The handler returns a UINode tree with badge and optional dropdown panel.
        Called via /call endpoint as __tray__{tray_id}.

        Example::

            @ext.tray("unread", icon="Mail", tooltip="Unread messages")
            async def tray_unread(ctx, **kwargs):
                count = await ctx.store.count("messages", where={"read": False})
                return ui.Stack([
                    ui.Badge(str(count), color="red" if count > 0 else "gray"),
                ])
        """
        def decorator(func: Callable) -> Callable:
            async def wrapper(ctx, **params):
                result = await func(ctx, **params)
                if hasattr(result, 'to_dict'):
                    return {"ui": result.to_dict(), "tray_id": tray_id, "icon": icon}
                return result
            self._tools[f"__tray__{tray_id}"] = ToolDef(
                name=f"__tray__{tray_id}", func=wrapper,
                description=f"Tray: {tooltip or tray_id}",
            )
            self._tray[tray_id] = TrayDef(
                tray_id=tray_id, func=wrapper, icon=icon, tooltip=tooltip,
            )
            return func
        return decorator

    def panel(self, panel_id: str, slot: str = "main", title: str = "",
              icon: str = "", refresh: str = "manual", **kwargs):
        """Declare a UI panel. Handler returns UINode tree.
        Panel fetched via /call endpoint with function __panel__{panel_id}."""
        def decorator(func: Callable) -> Callable:
            async def wrapper(ctx, **params):
                result = await func(ctx, **params)
                if hasattr(result, 'to_dict'):
                    return {"ui": result.to_dict(), "panel_id": panel_id}
                return result
            self._tools[f"__panel__{panel_id}"] = ToolDef(
                name=f"__panel__{panel_id}", func=wrapper,
                description=f"Panel: {title or panel_id}",
            )
            self._panels[panel_id] = {"slot": slot, "title": title, "icon": icon, "refresh": refresh, **kwargs}
            return func
        return decorator

    def widget(self, widget_id: str, slot: str = "dashboard.stats",
               label: str = "", icon: str = "", **kwargs):
        """Declare a UI widget for injection points."""
        def decorator(func: Callable) -> Callable:
            async def wrapper(ctx, **params):
                result = await func(ctx, **params)
                if hasattr(result, 'to_dict'):
                    return {"ui": result.to_dict(), "widget_id": widget_id}
                return result
            self._tools[f"__widget__{widget_id}"] = ToolDef(
                name=f"__widget__{widget_id}", func=wrapper,
                description=f"Widget: {label or widget_id}",
            )
            return func
        return decorator

    @property
    def tools(self) -> dict[str, ToolDef]:
        return self._tools

    @property
    def signals(self) -> dict[str, SignalDef]:
        return self._signals

    @property
    def schedules(self) -> dict[str, ScheduleDef]:
        return self._schedules

    @property
    def lifecycle(self) -> dict[str, LifecycleHook]:
        return self._lifecycle

    @property
    def webhooks(self) -> dict[str, WebhookDef]:
        return self._webhooks

    @property
    def event_handlers(self) -> list[EventHandlerDef]:
        return self._event_handlers

    @property
    def exposed(self) -> dict[str, ExposedMethod]:
        return self._exposed

    @property
    def tray_items(self) -> dict[str, "TrayDef"]:
        return self._tray

    @property
    def panels(self) -> dict[str, dict]:
        return self._panels

    async def call_tool(self, name: str, ctx: Any, **kwargs) -> Any:
        """Call a registered tool with context."""
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return await self._tools[name].func(ctx, **kwargs)

    async def call_signal(self, name: str, ctx: Any, **kwargs) -> Any:
        """Call a registered signal handler."""
        if name not in self._signals:
            raise ValueError(f"Unknown signal: {name}")
        return await self._signals[name].func(ctx, **kwargs)
