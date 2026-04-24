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

Re-exports ToolDef from :mod:`imperal_sdk.extension` so ``from imperal_sdk.tool_def
import ToolDef`` works; the canonical definition lives in ``extension.py`` to
avoid circular imports with ``Extension`` and the v1 decorator surface.
"""
from __future__ import annotations

from imperal_sdk.extension import ToolDef

__all__ = ["ToolDef"]
