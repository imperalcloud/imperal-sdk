# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class ToolDef:
    name: str
    func: Callable
    scopes: list[str] = field(default_factory=list)
    description: str = ""

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
    """Imperal Cloud Extension."""

    def __init__(
        self,
        app_id: str,
        version: str = "0.1.0",
        capabilities: list[str] | None = None,
        migrations_dir: str | None = None,
        config_defaults: dict | None = None,
    ):
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
