# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""ChatExtension — single entry point with LLM routing for extensions."""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from imperal_sdk.context import Context as _Context

from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.chat.handler import handle_message, TaskCancelled
from imperal_sdk.chat.prompt import build_system_prompt, build_messages, inject_language

log = logging.getLogger(__name__)


# Words that indicate write/destructive actions — used for backwards-compatible
# action_type detection when no explicit action_type is set on a function.
# Identity pattern — system_prompt must NOT contain self-identification.
# The kernel injects OS identity (assistant_name) automatically.
_IDENTITY_PATTERN = re.compile(r"\byou are (?:a |an |the )", re.IGNORECASE)

_ACTION_WORDS = ("send", "create", "delete", "update", "archive", "reply", "forward", "remove", "move", "trash")

@dataclass
class FunctionDef:
    """Federal v4.0.0 — typed function declaration.

    The kernel reads ``chain_callable`` from the manifest to pick typed
    dispatch (direct ``app/func(args)`` call) vs. legacy ChatExtension
    LLM-router delegation. Default ``True`` for any ``action_type`` other
    than ``"read"`` so the kernel can deterministically execute writes
    without giving the LLM a chance to summarise instead.

    ``effects`` declares the side-effect surface (``["create:note"]``,
    ``["delete:folder"]``, etc.) so the chain narrator + audit ledger
    can describe exactly what changed without re-deriving from text.
    """
    name: str
    func: Callable
    description: str
    params: dict = field(default_factory=dict)
    action_type: str = "read"  # "read", "write", or "destructive"
    event: str = ""  # event name for ActionResult publishing (e.g. "mail.sent")
    event_schema: type | None = None  # Pydantic BaseModel for typed event data
    chain_callable: bool = True  # federal v4.0.0 — kernel uses typed dispatch
    effects: list[str] = field(default_factory=list)  # ["create:note", "delete:folder", ...]
    _pydantic_model: type | None = None  # auto-detected Pydantic BaseModel class
    _pydantic_param: str = ""  # parameter name that receives the model instance
    _return_model: type | None = None  # auto-detected return Pydantic model

class ChatExtension:
    def __init__(self, ext, tool_name: str, description: str, system_prompt: str = "",
                 model: "str | None" = None, max_rounds: int = 10):
        self.ext = ext
        self.tool_name = tool_name
        self.description = description
        self.system_prompt = system_prompt
        # Sprint 2 (2026-04-28): the `model=` parameter is deprecated.
        # LLM resolution moved to kernel ctx-injection (see ctx._llm_configs)
        # in Sprint 1.2. Removing the constructor argument entirely is
        # scheduled for SDK 4.0.0 — until then we keep it for backward
        # compat but emit a class-level WARN-once when it's explicitly
        # passed. The flag is on the CLASS (not instance) so 11
        # extensions don't each warn at boot.
        if model is not None:
            if not getattr(ChatExtension, "_model_deprecation_warned", False):
                log.warning(
                    f"ChatExtension(tool_name={tool_name!r}, model=...): "
                    "the `model=` parameter is deprecated since SDK 3.3.0. "
                    "LLM model resolution moved to kernel ctx-injection (see "
                    "ctx._llm_configs). Will be removed in SDK 4.0.0. "
                    "Remove `model=` from extension app.py."
                )
                ChatExtension._model_deprecation_warned = True
            self.model = model
        else:
            self.model = ""  # historical default no longer meaningful
        self.max_rounds = max_rounds
        self._functions: dict[str, FunctionDef] = {}
        _self = self

        # SDK IDENTITY GUARD: warn developers about self-identification in prompts.
        if system_prompt and _IDENTITY_PATTERN.search(system_prompt):
            log.warning(
                f"[SDK] ChatExtension '{tool_name}': system_prompt contains 'You are ...' — "
                "this will be overridden by kernel OS identity. "
                "Use a neutral capability description instead. "
                "Example: 'Notes module — manage user notes and folders.'"
            )
        ext._chat_extensions = getattr(ext, "_chat_extensions", {})
        ext._chat_extensions[tool_name] = self
        # SCOPES MIGRATION (session 27): auto-registered chat entry tool no longer injects
        # wildcard. Granted capability set = union(Extension.capabilities, per-tool scopes).
        # If developer declares neither, loader falls back to ["*"] with WARN — migration signal.
        @ext.tool(tool_name, scopes=[], description=description)
        async def _entry_point(ctx, message="", **kwargs):
            return await _self._handle(ctx, message, **kwargs)

    def function(self, name: str, description: str, params: dict | None = None,
                 action_type: str = "read", event: str = "",
                 event_schema: type | None = None,
                 chain_callable: bool | None = None,
                 effects: list[str] | None = None):
        """Register a chat function (federal v4.0.0 contract).

        Args:
            name: Function name (used in tool_use calls).
            description: What this function does, ≥20 chars (V16). Shown to LLM.
            params: Parameter definitions dict. SDK auto-derives from a Pydantic
                BaseModel param annotation when omitted (V17 federal rule —
                no ``**kwargs`` or untyped handlers).
            action_type: ``"read"``, ``"write"``, or ``"destructive"``. Drives
                KAV verification and the 2-step confirmation gate.
            event: Event name for ActionResult publishing.
            event_schema: Optional Pydantic BaseModel class for typed event data.
            chain_callable: Federal v4.0.0 — when ``True`` the kernel issues a
                direct typed call ``app/func(args)`` instead of delegating to
                the ChatExtension LLM router. Defaults to ``True`` for
                ``action_type in ("write","destructive")`` so writes never get
                lost in LLM paraphrase.
            effects: Side-effect surface list — ``["create:note"]``,
                ``["delete:folder"]``, etc. Used by chain narrator + audit ledger.
        """
        if chain_callable is None:
            chain_callable = action_type in ("write", "destructive")

        def decorator(func: Callable) -> Callable:
            # Auto-detect Pydantic BaseModel params + return type
            resolved_params = params
            _detected_model = None
            _detected_param = ""
            _detected_return_model = None
            try:
                import typing as _typing
                hints = _typing.get_type_hints(func)
                ret_ann = hints.get("return")
                if ret_ann is not None:
                    try:
                        from pydantic import BaseModel as _BM
                        if isinstance(ret_ann, type) and issubclass(ret_ann, _BM):
                            _detected_return_model = ret_ann
                    except (TypeError, ImportError):
                        pass
            except Exception:
                pass
            if resolved_params is None:
                import inspect
                sig = inspect.signature(func)
                for pname, param in sig.parameters.items():
                    if pname in ("ctx", "self"):
                        continue
                    ann = param.annotation
                    if ann != inspect.Parameter.empty:
                        # PEP 563: from __future__ import annotations → strings
                        if isinstance(ann, str):
                            try:
                                ann = eval(ann, func.__globals__)
                            except Exception:
                                continue
                        try:
                            from pydantic import BaseModel
                            if isinstance(ann, type) and issubclass(ann, BaseModel):
                                schema = ann.model_json_schema()
                                resolved_params = {}
                                for field_name, field_info in schema.get("properties", {}).items():
                                    resolved_params[field_name] = {
                                        "type": field_info.get("type", "string"),
                                        "description": field_info.get("description", field_info.get("title", "")),
                                    }
                                    if field_name not in schema.get("required", []):
                                        resolved_params[field_name]["default"] = field_info.get("default")
                                _detected_model = ann
                                _detected_param = pname
                                break
                        except (TypeError, ImportError):
                            pass
            if resolved_params is None:
                resolved_params = {}

            self._functions[name] = FunctionDef(
                name=name, func=func, description=description,
                params=resolved_params, action_type=action_type, event=event,
                event_schema=event_schema,
                chain_callable=chain_callable,
                effects=list(effects or []),
                _pydantic_model=_detected_model, _pydantic_param=_detected_param,
                _return_model=_detected_return_model,
            )
            return func
        return decorator

    @property
    def functions(self) -> dict[str, FunctionDef]:
        return self._functions

    def _make_chat_result(self, response: str, handled: bool = False,
                          message_type: str = "text", intercepted: bool = False,
                          task_cancelled: bool = False, action_meta: dict = None,
                          narration_emission: dict | None = None) -> dict:
        """Build return dict using ChatResult for typed construction.

        narration_emission: when the LLM completed the turn via
            EMIT_NARRATION_TOOL (P2 Task 27), this carries the parsed
            NarrationEmission as a plain dict (.model_dump()). None for
            free-form text responses or on parse failure.
        """
        from imperal_sdk.types.chat_result import ChatResult, FunctionCall as FC

        fcs = []
        for fc_dict in self._functions_called:
            fcs.append(FC(
                name=fc_dict.get("name", ""),
                params=fc_dict.get("params", {}),
                action_type=fc_dict.get("action_type", "read"),
                success=fc_dict.get("success", False),
                result=fc_dict.get("result"),
                intercepted=fc_dict.get("intercepted", False),
                event=fc_dict.get("event", ""),
            ))

        cr = ChatResult(
            response=response,
            handled=handled,
            functions_called=fcs,
            had_successful_action=any(
                fc.success and fc.action_type in ("write", "destructive")
                for fc in fcs
            ),
            message_type=message_type,
            action_meta=action_meta or {},
            intercepted=intercepted,
            task_cancelled=task_cancelled,
            narration_emission=narration_emission,
        )
        return cr.to_dict()

    def _get_action_type(self, func_name: str) -> str:
        """Return the action_type for a function. Falls back to name-based detection."""
        if func_name in self._functions:
            at = self._functions[func_name].action_type
            if at != "read":
                return at
            # Backwards compat: if still "read" (default), check name for write words
            if any(w in func_name.lower() for w in _ACTION_WORDS):
                return "write"
            return "read"
        # Unknown function — try name-based detection
        if any(w in func_name.lower() for w in _ACTION_WORDS):
            return "write"
        return "read"

    def _build_tool_schemas(self) -> list[dict]:
        tools = []
        for fn in self._functions.values():
            properties = {}
            required = []
            for pname, pdef in fn.params.items():
                prop = {"type": pdef.get("type", "string")}
                if "description" in pdef: prop["description"] = pdef["description"]
                if "enum" in pdef: prop["enum"] = pdef["enum"]
                properties[pname] = prop
                if "default" not in pdef: required.append(pname)
            tools.append({"name": fn.name, "description": fn.description,
                         "input_schema": {"type": "object", "properties": properties, "required": required}})
        return tools

    def _build_system_prompt(self, ctx) -> str:
        return build_system_prompt(self.system_prompt, ctx, self.tool_name)

    def _build_messages(self, history, message, context_window=20, keep_recent=6):
        return build_messages(history, message, context_window, keep_recent)

    async def _handle(self, ctx: _Context, message: str = "", **kwargs) -> dict:
        # ICNLI v7 — propagate SM slice from kernel-supplied skeleton to ctx attr.
        try:
            if isinstance(getattr(ctx, "skeleton", None), dict) and "_session_memory_slice" in ctx.skeleton:
                setattr(ctx, "session_memory_slice", ctx.skeleton["_session_memory_slice"])
        except Exception:
            pass
        return await handle_message(self, ctx, message, **kwargs)
