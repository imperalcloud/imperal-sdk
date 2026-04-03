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

    @property
    def tools(self) -> dict[str, ToolDef]:
        return self._tools

    @property
    def signals(self) -> dict[str, SignalDef]:
        return self._signals

    @property
    def schedules(self) -> dict[str, ScheduleDef]:
        return self._schedules

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
