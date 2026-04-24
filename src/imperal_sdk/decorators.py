# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Module-level ``@ext.tool`` decorator for v2.0.0 class-based Extensions.

v2.0 pattern::

    from imperal_sdk import ext, Extension
    from pydantic import BaseModel

    class NoteResult(BaseModel):
        note_id: str
        created: bool

    class NotesExtension(Extension):
        @ext.tool(
            description="Create a new note with the given title in the user's notebook",
            output_schema=NoteResult,
        )
        async def create_note(self, title: str) -> NoteResult:
            ...

This decorator stamps metadata on the raw function as ``fn._tool_meta``.
:meth:`Extension.__init_subclass__` sweeps the class namespace, discovers any
function carrying ``_tool_meta``, and collects them into the class-level
``cls._tools_registry: dict[str, fn]`` map. A second pass validates that every
``long_running=True`` tool's declared ``status_tool`` resolves to a companion
tool on the same extension (class-def + instantiation time).

Invariants enforced:

* I-TOOL-SCHEMA-REQUIRED — ``output_schema`` kwarg mandatory (``TypeError``)
* I-TOOL-DESC-MINIMUM   — ``description`` must be >= 20 chars (``ValueError``)
* I-LONG-RUNNING-STATUS-REQUIRED — ``long_running=True`` demands ``status_tool``
* I-STATUS-TOOL-MUST-EXIST — ``status_tool`` name resolves on the same ext
  (enforced by :class:`imperal_sdk.extension.Extension.__init_subclass__` +
  ``__init__``)

The v1 instance-based surface (``ext = Extension("app"); @ext.tool("name")``)
is untouched — that decorator lives on :class:`Extension` itself and does not
require the v2 fields. Both surfaces produce the same :class:`ToolDef` shape.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Sentinel used to distinguish "kwarg not passed" from "kwarg passed as None".
# Avoids silent footgun where ``output_schema=None`` would be accepted.
_MISSING: Any = object()


class _ExtNamespace:
    """Module-level namespace exposing ``@ext.tool`` + (future) v2 decorators.

    Kept as a singleton instance (not a class) so ``ext.tool(...)`` reads
    naturally. The v1 instance-based ``Extension("app").tool(name)`` remains
    the supported surface for legacy/imperative extensions; ``ext`` is
    strictly the v2 class-based surface.
    """

    __slots__ = ()

    def tool(
        self,
        description: str = "",
        *,
        output_schema: Any = _MISSING,
        long_running: bool = False,
        estimated_duration_s: int | None = None,
        status_tool: str | None = None,
        llm_backed: bool = False,
        cost_credits: int = 0,
        scopes: list[str] | None = None,
    ) -> Callable[[Callable], Callable]:
        """v2.0 ``@ext.tool`` decorator — hard-breaking from v1.

        Validation fires at class-definition time (i.e. the decorator call
        itself), so malformed tool declarations surface as the module
        imports — before any kernel load attempt.
        """
        # I-TOOL-SCHEMA-REQUIRED
        if output_schema is _MISSING or output_schema is None:
            raise TypeError(
                "output_schema is required for all @ext.tool in v2.0.0. "
                "Pass a Pydantic BaseModel subclass describing the tool's "
                "return shape — the Webbee Narrator uses it to ground prose."
            )

        # I-TOOL-DESC-MINIMUM
        if not isinstance(description, str) or len(description) < 20:
            got = len(description) if isinstance(description, str) else 0
            raise ValueError(
                f"tool description must be >= 20 chars; got {got}. "
                "Description is read by the Webbee Routing LLM to understand "
                "what this tool does — make it specific and action-oriented."
            )

        # I-LONG-RUNNING-STATUS-REQUIRED
        if long_running and not (isinstance(status_tool, str) and status_tool):
            raise ValueError(
                "status_tool is required when long_running=True. "
                "Declare a companion tool that returns TaskStatus. "
                "See spec I-LONG-RUNNING-STATUS-REQUIRED."
            )

        # Soft warn: estimated_duration_s is strongly recommended for UX
        # (progress bar ETA) but not required at SDK level.
        if long_running and estimated_duration_s is None:
            logger.warning(
                "long_running=True without estimated_duration_s — "
                "Webbee will display 'no ETA' in the status card. "
                "Recommend setting an upper-bound estimate in seconds.",
            )

        def wrapper(fn: Callable) -> Callable:
            # Store the full metadata dict for structured access + loader
            # introspection. Also mirror each field as a direct attribute on
            # the function object — ToolDef-like duck-typing keeps call sites
            # that look up ``getattr(tool, "llm_backed", False)`` happy without
            # forcing them through ``_tool_meta``.
            fn._tool_meta = {  # type: ignore[attr-defined]
                "description": description,
                "output_schema": output_schema,
                "long_running": long_running,
                "estimated_duration_s": estimated_duration_s,
                "status_tool": status_tool,
                "llm_backed": llm_backed,
                "cost_credits": cost_credits,
                "scopes": list(scopes) if scopes else [],
            }
            fn.description = description                   # type: ignore[attr-defined]
            fn.output_schema = output_schema               # type: ignore[attr-defined]
            fn.long_running = long_running                 # type: ignore[attr-defined]
            fn.estimated_duration_s = estimated_duration_s # type: ignore[attr-defined]
            fn.status_tool = status_tool                   # type: ignore[attr-defined]
            fn.llm_backed = llm_backed                     # type: ignore[attr-defined]
            fn.cost_credits = cost_credits                 # type: ignore[attr-defined]
            fn.scopes = list(scopes) if scopes else []     # type: ignore[attr-defined]
            return fn

        return wrapper


# Module-level singleton. Importable as ``from imperal_sdk import ext``.
ext = _ExtNamespace()

__all__ = ["ext"]
