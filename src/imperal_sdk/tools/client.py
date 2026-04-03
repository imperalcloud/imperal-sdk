# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Inter-extension communication via kernel syscalls."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolInfo:
    """Tool metadata returned by discover()."""
    app_id: str
    activity_name: str
    name: str
    description: str
    domains: list[str]
    required_scopes: list[str]
    relevance: float


@dataclass
class ToolResult:
    """Result from calling another extension's tool."""
    response: str | dict
    app_id: str
    tool_name: str


class ToolsClient:
    """Inter-extension communication via kernel syscalls.

    All calls route through kernel execute_sdk_tool, ensuring:
    - RBAC enforcement (caller scopes checked)
    - Audit trail (all cross-extension calls logged)
    - Capability boundary respected
    - Skeleton signal fired after execution

    In runtime mode (inside kernel), uses a direct callable.
    In SDK external mode (future), can use HTTP.
    """

    def __init__(self, execute_fn: Callable | None = None, user_info: dict | None = None, extension_id: str = ""):
        self._execute_fn = execute_fn
        self._user_info = user_info or {}
        self._extension_id = extension_id

    async def discover(self, query: str, top_k: int = 3) -> list[ToolInfo]:
        """Semantic search across all registered tools.

        Returns ranked list filtered by caller's scopes.

        Example:
            tools = await ctx.tools.discover("case analysis")
            for tool in tools:
                print(f"{tool.name} ({tool.relevance:.2f})")
        """
        if self._execute_fn is None:
            return []

        result = await self._execute_fn({
            "tool_name": "discover_tools",
            "message": query,
            "user": self._user_info,
            "context": {"top_k": top_k},
        })

        response = result.get("response", {})
        tools_data = response.get("tools", []) if isinstance(response, dict) else []
        return [
            ToolInfo(
                app_id=t.get("app_id", ""),
                activity_name=t.get("activity_name", ""),
                name=t.get("name", ""),
                description=t.get("description", ""),
                domains=t.get("domains", []),
                required_scopes=t.get("required_scopes", []),
                relevance=t.get("relevance", 0.0),
            )
            for t in tools_data
        ]

    async def call(self, activity_name: str, params: dict) -> ToolResult:
        """Call another extension's tool through the kernel.

        Full RBAC + audit + skeleton signal path.

        Example:
            result = await ctx.tools.call("tool_sharelock_chat", {"message": "analyze case 42"})
            print(result.response)
        """
        if self._execute_fn is None:
            return ToolResult(response="Tools client not initialized", app_id="", tool_name=activity_name)

        result = await self._execute_fn({
            "tool_name": activity_name,
            "user": self._user_info,
            "message": params.get("message", ""),
            "context": params,
        })

        response = result.get("response", "")
        parts = activity_name.split("_", 2)
        app_id = parts[1] if len(parts) >= 2 else ""

        return ToolResult(response=response, app_id=app_id, tool_name=activity_name)
