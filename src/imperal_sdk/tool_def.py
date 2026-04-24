# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""ToolDef — canonical tool shape used by both v1 instance-based and v2 class-based surfaces.

v2.0.0 adds six new fields (output_schema, long_running, estimated_duration_s,
status_tool, llm_backed, cost_credits) to support Webbee Single Voice contract:

- Routing LLM reads ``description`` (>= 20 chars) to pick a tool.
- Narrator grounds its prose against ``output_schema``.
- Kernel dispatcher uses ``long_running``/``status_tool`` pair for the
  pre-ACK / status-poll flow (see spec §7 I-LONG-RUNNING-STATUS-REQUIRED).
- ``llm_backed`` marks tools that internally call ``purpose="execution"``
  LLM — surfaces to billing + federal BYOLLM overrides.
- ``cost_credits`` feeds the pre-ACK confirmation gate.

The v1 ``Extension("app").tool(name)`` instance decorator continues to produce
ToolDef with the same core fields (``name``, ``func``, ``scopes``,
``description``) and defaults for the new fields — fully backward-compatible.

This module is the canonical source of truth for ``ToolDef``. ``extension.py``
re-exports the symbol so legacy imports such as
``from imperal_sdk.extension import ToolDef`` continue to work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ToolDef:
    name: str
    func: Callable
    scopes: list[str] = field(default_factory=list)
    description: str = ""
    # v2.0.0 fields (Webbee Single Voice contract). All have safe defaults so
    # v1 ``Extension("app").tool(name)`` instance-based registrations remain
    # valid — only the v2 class-based ``@ext.tool`` decorator enforces them.
    output_schema: type | None = None          # Pydantic BaseModel subclass (required in v2)
    long_running: bool = False
    estimated_duration_s: int | None = None
    status_tool: str | None = None             # Companion tool name on same Extension
    llm_backed: bool = False                   # Calls purpose="execution" LLM internally
    cost_credits: int = 0                      # Pre-ACK confirmation gate


__all__ = ["ToolDef"]
